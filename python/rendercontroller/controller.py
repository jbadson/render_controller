import logging
import threading
import os.path
import time
from typing import Sequence, Dict, Any, Type, List, Optional
from uuid import uuid4
from collections import OrderedDict
from .job import RenderJob
from .database import StateDatabase
from .util import Config
from .exceptions import JobNotFoundError, NodeNotFoundError, JobStatusError
from .status import WAITING, RENDERING, STOPPED, FINISHED, FAILED

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

    def __next__(self) -> Type[RenderJob]:
        if self.index >= len(self.jobs):
            raise StopIteration
        i = self.index
        self.index += 1
        return tuple(self.jobs.values())[i]

    def __len__(self) -> int:
        return len(self.jobs)

    def __str__(self) -> str:
        return f"RenderQueue{tuple(f'{k}:{v}' for k, v in self.jobs.items())}"

    def __getitem__(self, item: int) -> Type[RenderJob]:
        """Returns job by position.  This is the same as get_by_index()."""
        return tuple(self.jobs.values())[item]

    def __contains__(self, id) -> bool:
        if id in self.jobs:
            return True
        return False

    def append(self, job: Type[RenderJob]) -> None:
        self.jobs[job.id] = job

    def pop(self, id: str) -> Type[RenderJob]:
        """Remove and return a job by id."""
        return self.jobs.pop(id)

    def get_by_id(self, id: str) -> Type[RenderJob]:
        """Returns job identified by id, else raises KeyError."""
        return self.jobs[id]

    def get_by_position(self, index: int) -> Type[RenderJob]:
        """Returns job located at given position, else raises IndexError."""
        return self.__getitem__(index)

    def insert(self, job: Type[RenderJob], index: int) -> None:
        """Inserts a job at a specific position."""
        items = list(self.jobs.items())
        items.insert(index, (job.id, job))
        self.jobs = OrderedDict(items)

    def keys(self) -> List[str]:
        return [job.id for job in self.jobs.values()]

    def values(self) -> List[Type[RenderJob]]:
        return list(self.jobs.values())

    def move(self, id: str, index: int) -> None:
        """Moves job specified by `id` to a new position."""
        job = self.jobs.pop(id)
        self.insert(job, index)

    def sort_by_status(self) -> None:
        """Sorts the queue by status. Finished jobs go to end, all others keep their ordering"""
        unfinished = []
        finished = []
        for j in self.jobs.values():
            if j.status == FINISHED:
                finished.append((j.id, j))
            else:
                unfinished.append((j.id, j))
        self.jobs = OrderedDict(unfinished + finished)

    def get_next_waiting(self) -> Optional[Type[RenderJob]]:
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
        if self.queue.count_status(RENDERING) == 0:
            return True
        return False

    def enable_autostart(self) -> None:
        """Enable automatic rendering jobs in the render queue."""
        self.config.autostart = True
        logger.info("Enabled autostart")

    def disable_autostart(self) -> None:
        """Disable automatic rendering of jobs in the render queue."""
        self.config.autostart = False
        logger.info("Disabled autostart")

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
        :param list nodes: List of render nodes to enable for this job.
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

    def start(self, job_id: str) -> None:
        """Starts a render job."""
        # TODO raise exception if fails
        try:
            self.queue.get_by_id(job_id).render()
        except KeyError:
            logger.exception("Failed to start '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def start_next(self) -> Optional[str]:
        """Starts next job in queue and return job ID.  If no jobs in queue, returns None."""
        job = self.queue.get_next_waiting()
        if job:
            job.render()
            return job.id
        return None

    def stop(self, job_id: str, kill: bool = True) -> None:
        """
        Stops a render job.

        :param str job_id: ID of job to stop.
        :param bool kill: Kill active render processes. If False,
            currently rendering frames will be allowed to finish.
        """
        try:
            self.queue.get_by_id(job_id).stop()
        except KeyError:
            logger.exception("Failed to stop '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def enqueue(self, job_id: str) -> None:
        """Places a stopped job back in the render queue."""
        # FIXME is this necessary?  Re-evaluate logic of WAITING vs STOPPED
        pass
        """
        try:
            self.server.resume_render(job_id, startnow=False)
        except KeyError:
            logger.exception("Failed to resume '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)
            """

    def delete(self, job_id: str) -> None:
        """Deletes a render job.  Job must not be rendering."""
        try:
            job = self.queue.get_by_id(job_id)
        except KeyError:
            logger.exception("Failed to delete '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)
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
        logger.debug("Enable %s for %s" % (node, job_id))
        # FIXME redundant - RenderJob also checks that node is in render_nodes -- also disable_node
        if node not in self.render_nodes:
            raise NodeNotFoundError("Node '%s' not found" % node)
        try:
            self.queue.get_by_id(job_id).enable_node(node)
        except KeyError:
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def disable_node(self, job_id: str, node: str) -> None:
        """
        Disables a render node for a given job.

        :param str job_id: ID of job to modify.
        :param str node: Name of render node.
        """
        logger.debug("Disable %s for %s" % (node, job_id))
        if node not in self.render_nodes:
            raise NodeNotFoundError("Node '%s' not found" % node)
        try:
            self.queue.get_by_id(job_id).disable_node(node)
        except KeyError:
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def get_all_job_data(self) -> List[Dict[str, Any]]:
        """Returns complete status info about all jobs on server."""
        data = []
        for job in self.queue.values():
            data.append(self.get_job_data(job.id))
        return data

    def get_job_data(self, job_id: str) -> Dict:
        """Returns details for a render job."""
        try:
            job = self.queue.get_by_id(job_id)
        except KeyError:
            raise JobNotFoundError(f"Job {job_id} not found")
        return job.dump()

    def shutdown(self) -> None:
        """Prepares controller for clean shutdown."""
        logger.debug("Shutting down controller")
        for job in self.queue.values():
            job.stop()
        self.task_thread.shutdown()
        self.save_state()

    def save_state(self) -> None:
        raise NotImplementedError


class TaskThread(object):
    """Thread to perform periodic background tasks."""

    def __init__(self, controller: Type[RenderController]):
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
            # Check for pending actions every 10 sec, but subdivide the loop to prevent shutdown delays
            for i in range(20):
                time.sleep(0.5)
                if self.stop:
                    break
            if self.controller.autostart:
                if self.controller.idle:
                    self.controller.start_next()
