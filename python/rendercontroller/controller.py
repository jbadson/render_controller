import logging
import threading
import os.path
import time
import inspect
from typing import Sequence, Dict, Any, Type, List, Optional
from uuid import uuid4
from collections import OrderedDict
from rendercontroller.job import RenderJob
from rendercontroller.database import StateDatabase
from rendercontroller.util import Config
from rendercontroller.exceptions import JobNotFoundError, NodeNotFoundError, JobStatusError
from rendercontroller.status import WAITING, RENDERING, STOPPED, FINISHED, FAILED

logger = logging.getLogger("controller")


class RenderQueue(object):
    """
    Ordered iterable that represents a queue of render jobs.

    This is something like a hybrid of a list and an OrderedDict, which allows accessing
    elements both by index and key and adds some higher level methods specific to render jobs.
    """

    def __init__(self):
        self.jobs = OrderedDict()
        self.index = 0

    def __iter__(self):
        self.index = 0
        return self

    def __next__(self) -> RenderJob:
        if self.index >= len(self.jobs):
            raise StopIteration
        i = self.index
        self.index += 1
        return tuple(self.jobs.values())[i]

    def __len__(self) -> int:
        return len(self.jobs)

    def __str__(self) -> str:
        return f"RenderQueue{tuple(f'{k}:{v}' for k, v in self.jobs.items())}"

    def __getitem__(self, item: int) -> RenderJob:
        """Returns job by position.  This is the same as get_by_index()."""
        return tuple(self.jobs.values())[item]

    def __contains__(self, id) -> bool:
        if id in self.jobs:
            return True
        return False

    def append(self, job: RenderJob) -> None:
        self.jobs[job.id] = job

    def pop(self, id: str) -> RenderJob:
        """Remove and return a job by id."""
        return self.jobs.pop(id)

    def get_by_id(self, id: str) -> RenderJob:
        """Returns job identified by id, else raises KeyError."""
        return self.jobs[id]

    def get_by_position(self, index: int) -> RenderJob:
        """Returns job located at given position, else raises IndexError."""
        return self.__getitem__(index)

    def insert(self, job: RenderJob, index: int) -> None:
        """Inserts a job at a specific position."""
        items = list(self.jobs.items())
        items.insert(index, (job.id, job))
        self.jobs = OrderedDict(items)

    def keys(self) -> List[str]:
        return [job.id for job in self.jobs.values()]

    def values(self) -> List[RenderJob]:
        return list(self.jobs.values())

    def move(self, id: str, index: int) -> None:
        """Moves job specified by `id` to a new position."""
        job = self.jobs.pop(id)
        self.insert(job, index)

    def get_next_waiting(self) -> Optional[RenderJob]:
        """Returns first item in queue with status Waiting. If none found, returns None."""
        for j in self.jobs.values():
            if j.status == WAITING:
                return j
        return None

    def count_status(self, status: str) -> int:
        """Returns the number of jobs with matching status."""
        n = 0
        for j in self.jobs.values():
            if j.status == status:
                n += 1
        return n

    def get_position(self, id: str) -> int:
        """Returns position of job in queue."""
        n = 0
        for i in self.jobs.keys():
            if i == id:
                return n
            n += 1
        raise KeyError(id)


class RenderController(object):
    """
    Manages render jobs.

    Right now this is a janky hack to decouple the old RenderServer from
    its custom network protocol so we can have a REST API and web front end.
    Eventually it will replace RenderServer and everything will be much
    less terrible.
    """

    def __init__(self, config: Type[Config]) -> None:
        # TODO Update docstrings once all old job stuff is removed
        # This is bad but will get things moving until I have time to
        # rewrite all the terrible stuff in RenderServer.
        self.config = config
        # Inject dependency until job module is rewritten or replaced
        # job.CONFIG = config
        # self.server = job.RenderServer()
        # New Stuff Here
        self.queue = RenderQueue()
        self.db = StateDatabase(
            os.path.join(self.config.work_dir, "rcontroller.sqlite")
        )
        self.db.initialize()
        self.task_thread = TaskThread(self)
        self.task_thread.start()
        # Try to restore jobs from database
        jobs = self.db.get_all_jobs()
        if jobs:
            self.restore_jobs(jobs)

    @property
    def render_nodes(self) -> Sequence[str]:
        """List of render nodes."""
        return self.config.render_nodes

    @property
    def autostart(self) -> bool:
        """State of autostart mode."""
        return self.config.autostart

    @property
    def idle(self) -> bool:
        """Returns True if no jobs are currently rendering."""
        for job in self.queue.values():
            if job.status == RENDERING:
                return False
        return True

    def enable_autostart(self) -> None:
        """Enable automatic rendering jobs in the render queue."""
        self.config.autostart = True
        logger.info("Enabled autostart")

    def disable_autostart(self) -> None:
        """Disable automatic rendering of jobs in the render queue."""
        self.config.autostart = False
        logger.info("Disabled autostart")

    def restore_jobs(self, jobs: List[Dict]):
        for j in jobs:
            logger.info(f"Restoring job {j['id']} from disk.")
            job = RenderJob(
                config=self.config,
                db=self.db,
                id=j["id"],
                path=j["path"],
                start_frame=j["start_frame"],
                end_frame=j["end_frame"],
                render_nodes=j["render_nodes"],
                status=j["status"],
                time_start=j["time_start"],
                time_stop=j["time_stop"],
                time_offset=time.time() - j["time_start"],
                frames_completed=j["frames_completed"],
            )
            self.queue.append(job)

    def new_job(
        self,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: List[str],
    ) -> str:
        """
        Creates a new render job and places it in queue.

        :param str path: Path to project file.
        :param int start_frame: Start frame number.
        :param int end_frame: End frame number.
        :param list render_nodes: List of render nodes to enable for this job.
        :return str: ID of newly created job.
        """
        job = RenderJob(
            config=self.config,
            db=self.db,
            id=uuid4().hex,
            path=path,
            start_frame=start_frame,
            end_frame=end_frame,
            render_nodes=render_nodes,
        )
        self.queue.append(job)
        # Note: Database insertion, deletion and queue changes are performed by this class.
        # DB updates are delegated to RenderJob instances.
        self.db.insert_job(
            job.id,
            job.status,
            path,
            start_frame,
            end_frame,
            render_nodes,
            0.0,
            0.0,
            [],
            self.queue.get_position(job.id),
        )
        return job.id

    def _try_get_job(self, job_id: str) -> RenderJob:
        """Returns an instance of RenderJob matching job_id, otherwise throws JobNotFoundError."""
        try:
            return self.queue.get_by_id(job_id)
        except KeyError:
            caller = inspect.stack()[1].function
            logger.error(f"_try_get_job() invoked by {caller}() caught KeyError on '{job_id}'")
        raise JobNotFoundError(f"Job {job_id} not found")

    def start(self, job_id: str) -> None:
        """Starts a render job."""
        # TODO raise exception if fails
        self._try_get_job(job_id).start()

    def start_next(self) -> Optional[str]:
        """Starts next job in queue and return job ID.  If no jobs in queue, returns None."""
        job = self.queue.get_next_waiting()
        if job:
            job.render()
            return job.id
        return None

    def stop(self, job_id: str, ) -> None:
        """
        Stops a render job.

        :param str job_id: ID of job to stop.
        """
        self._try_get_job(job_id).stop()

    def reset_waiting(self, job_id: str) -> None:
        """For a job that has been stopped, reset the status to waiting so it can be started by autostart.

        Job will retain its original queue position."""
        self._try_get_job(job_id).reset_waiting()

    def delete(self, job_id: str) -> None:
        """Deletes a render job.  Job must not be rendering."""
        job = self._try_get_job(job_id)
        if job.status == RENDERING:
            raise JobStatusError("Cannot delete job while it is rendering.")
        self.queue.pop(job_id)
        # Note: Database insertion, deletion and queue changes are performed by this class.
        # DB updates are delegated to RenderJob instances.
        self.db.delete_job(job_id)

    def enable_node(self, job_id: str, node: str) -> None:
        """
        Enables a render node for a given job.

        :param str job_id: ID of job to modify.
        :param str node: Name of render node.
        """
        self._try_get_job(job_id).enable_node(node)

    def disable_node(self, job_id: str, node: str) -> None:
        """
        Disables a render node for a given job.

        :param str job_id: ID of job to modify.
        :param str node: Name of render node.
        """
        self._try_get_job(job_id).disable_node(node)

    def get_all_job_data(self) -> List[Dict[str, Any]]:
        """Returns complete status info about all jobs on server."""
        data = []
        for job in self.queue.values():
            data.append(self.get_job_data(job.id))
        return data

    def get_job_data(self, job_id: str) -> Dict[str, Any]:
        """Returns details for a render job."""
        return self._try_get_job(job_id).dump()

    def shutdown(self) -> None:
        """Prepares controller for clean shutdown."""
        logger.debug("Shutting down controller")
        for job in self.queue.values():
            if job.status == RENDERING:
                job.stop()
        self.task_thread.shutdown()


class TaskThread(object):
    """Thread to perform periodic background tasks."""

    def __init__(self, controller: RenderController):
        self.controller = controller
        self.stop = False
        self._thread = threading.Thread(target=self.mainloop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def running(self) -> bool:
        return self._thread.is_alive()

    def shutdown(self) -> None:
        logger.debug("Attempting to terminate task thread.")
        self.stop = True
        self._thread.join()  # Wait for any cleanup tasks to finish
        logger.debug("Terminated task thread.")

    def mainloop(self) -> None:
        logger.debug("Starting task thread.")
        while not self.stop:
            time.sleep(1)
            if self.controller.autostart:
                if self.controller.idle:
                    self.controller.start_next()
