#!/usr/bin/env python -> Type[Job -> Type[Job]
import logging
import sqlite3
import threading
import os.path
import time
from typing import Sequence, Dict, Any, Type, List, Optional
from uuid import uuid4
from collections import OrderedDict
from . import job
from .exceptions import JobNotFoundError, NodeNotFoundError, JobStatusError

logger = logging.getLogger("controller")


class Config(object):
    """Singleton configuration object."""

    def __init__(self):
        raise RuntimeError("Config class cannot be instantiated")

    @classmethod
    def set_all(cls, attrs: Dict[str, Any]) -> None:
        """Sets attributes from a dictionary."""
        for key, val in attrs.items():
            logger.debug("Set config %s=%s" % (key, val))
            setattr(cls, key, val)

    @classmethod
    def get(cls, attr: str, default: Any = None) -> Any:
        """Getter method that allows setting a default value."""
        if hasattr(cls, attr):
            return getattr(cls, attr)
        if default:
            return default
        raise AttributeError(attr)


class RenderQueue(object):
    """
    Ordered iterable that represents a queue of render jobs.

    Extends behavior of OrderedDict to allow accessing elements by both index and key, plus some
    higher level methods specific to render jobs.
    """

    def __init__(self):
        self.jobs = OrderedDict()
        self.index = 0

    def __iter__(self):
        self.index = 0
        return self

    def __next__(self) -> Type[job.Job]:
        if self.index >= len(self.jobs):
            raise StopIteration
        i = self.index
        self.index += 1
        return tuple(self.jobs.values())[i]

    def __len__(self) -> int:
        return len(self.jobs)

    def __repr__(self) -> str:
        return str(tuple(self.jobs.values()))

    def __getitem__(self, item: int) -> Type[job.Job]:
        """Returns job by position.  This is the same as get_by_index()."""
        return tuple(self.jobs.values())[item]

    def append(self, job: Type[job.Job]) -> None:
        self.jobs[job.id] = job

    def pop(self, id: str) -> Type[job.Job]:
        """Remove and return a job by id."""
        return self.jobs.pop(id)

    def get_by_id(self, id: str) -> Type[job.Job]:
        """Returns job identified by id, else raises KeyError."""
        return self.jobs.get(id)

    def get_by_position(self, index: int) -> Type[job.Job]:
        """Returns job located at given position, else raises IndexError."""
        return self.__getitem__(index)

    def insert(self, job: Type[job.Job], index: int) -> None:
        """Inserts a job at a specific position."""
        items = list(self.jobs.items())
        items.insert(index, (job.id, job))
        self.jobs = OrderedDict(items)

    def keys(self) -> List[str]:
        return [job.id for job in self.jobs.values()]

    def values(self) -> List[Type[job.Job]]:
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
            if j.status == "Finished":
                finished.append((j.id, j))
            else:
                unfinished.append((j.id, j))
        self.jobs = OrderedDict(unfinished + finished)

    def get_next_waiting(self) -> Optional[Type[job.Job]]:
        """Returns first item in queue with status Waiting. If none found, returns None."""
        for j in self.jobs.values():
            if j.status == "Waiting":
                return j
        return None

    def count_status(self, status: str) -> int:
        """Returns the number of jobs with matching status."""
        n = 0
        for j in self.jobs:
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


class StateDatabase(object):
    """Interface for SQLite Database to store server state."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        # FIXME Might be better to have conn as instance variable. Would that lock the db file?

    def initialize(self) -> None:
        jobs_schema = [
            "id TEXT UNIQUE",
            "status TEXT",
            "path TEXT",
            "start_frame INTEGER",
            "end_frame INTEGER",
            "render_nodes BLOB",
            "time_start REAL",
            "time_stop REAL",
            "frames_completed BLOB",
            "queue_position INTEGER",
        ]
        self.execute(f"CREATE TABLE IF NOT EXISTS jobs ({', '.join(jobs_schema)})")

    def insert_job(
        self,
        id: str,
        status: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: Sequence[str],
        time_start: float,
        time_stop: float,
        frames_completed: Sequence[int],
        queue_position: int,
    ) -> None:
        frames_completed = ",".join([str(i) for i in frames_completed])
        render_nodes = ",".join(render_nodes)
        self.execute(
            f"INSERT INTO jobs VALUES ('{id}', '{status}', '{path}', {start_frame}, {end_frame}, "
            + f"'{render_nodes}', {time_start}, {time_stop}, '{frames_completed}', {queue_position})",
            commit=True,
        )

    def update_job_status(self, id: str, status: str) -> None:
        self.execute(f"UPDATE jobs SET status='{status}' WHERE id='{id}'", commit=True)

    def update_job_time_stop(self, id: str, time_stop: float) -> None:
        self.execute(
            f"UPDATE jobs SET time_stop={time_stop} WHERE id='{id}'", commit=True
        )

    def update_job_frames_completed(self, id: str, frames_completed: List[int]) -> None:
        frames_completed = ",".join([str(i) for i in frames_completed])
        self.execute(
            f"UPDATE jobs SET frames_completed='{frames_completed}' WHERE id='{id}'",
            commit=True,
        )

    def update_job_queue_position(self, id: str, queue_position: int) -> None:
        self.execute(
            f"UPDATE jobs SET queue_position={queue_position} WHERE id='{id}'",
            commit=True,
        )

    def update_node(self, job_id: str, render_nodes: Sequence) -> None:
        render_nodes = ",".join(render_nodes)
        self.execute(
            f"UPDATE jobs SET render_nodes='{render_nodes}' WHERE id='{job_id}'",
            commit=True,
        )

    def _parse_job_row(self, row: Sequence) -> Dict:
        return {
            "id": row[0],
            "status": row[1],
            "path": row[2],
            "start_frame": row[3],
            "end_frame": row[4],
            "render_nodes": row[5].split(","),
            "time_start": row[6],
            "time_stop": row[7],
            "frames_completed": [int(i) for i in row[8].split(",")],
            "queue_position": row[9],
        }

    def get_job(self, id) -> Dict:
        job = self.execute(f"SELECT * FROM jobs WHERE id='{id}'")
        if len(job) > 1:
            raise KeyError("Multiple jobs found with same id.")
        return self._parse_job_row(job[0])

    def get_all_jobs(self) -> List:
        # FIXME Ordering is based on insertion order, NOT queue position.
        jobs = self.execute("SELECT * FROM jobs")
        ret = []
        for j in jobs:
            ret.append(self._parse_job_row(j))
        return ret

    def remove_job(self, id) -> None:
        self.execute(f"DELETE FROM jobs WHERE id='{id}'", commit=True)

    def execute(self, query: str, commit: bool = False) -> List:
        # FIXME make this sane. Just want to get something working for now.
        con = sqlite3.connect(self.filepath)
        cursor = con.cursor()
        cursor.execute(query)
        ret = cursor.fetchall()
        if commit:
            con.commit()
        con.close()
        return ret


class RenderController(object):
    """
    Manages render jobs.

    Right now this is a janky hack to decouple the old RenderServer from
    its custom network protocol so we can have a REST API and web front end.
    Eventually it will replace RenderServer and everything will be much
    less terrible.
    """

    def __init__(self, config: Type[Config]) -> None:
        # This is bad but will get things moving until I have time to
        # rewrite all the terrible stuff in RenderServer.
        self.config = config
        # Inject dependency until job module is rewritten or replaced
        job.CONFIG = config
        self.server = job.RenderServer()
        # New Stuff Here
        self.queue = RenderQueue()
        self.db = StateDatabase(
            os.path.join(self.config.work_dir, "rcontroller.sqlite")
        )
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
        if self.queue.count_status("Rendering") == 0:
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
        render_engine: str,
        render_nodes: Sequence[str],
        render_params: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Creates a new render job and places it in queue.

        :param str path: Path to project file.
        :param int start_frame: Start frame number.
        :param int end_frame: End frame number.
        :param str render_engine: Render engine.
        :param list nodes: List of render nodes to enable for this job.
        :param dict render_params: Optional dict of render-engine-specific
            parameters. Implementation is up to the render engine handler.
        :return str: ID of newly created job.
        """
        job_id = uuid4().hex
        self.server.enqueue(
            {
                "index": job_id,
                "path": path,
                "startframe": start_frame,
                "endframe": end_frame,
                "extraframes": None,  # Deprecated
                "render_engine": render_engine,
                "complist": nodes,
                "render_params": render_params,
            }
        )
        return job_id

    def start(self, job_id: str) -> None:
        """Starts a render job."""
        # TODO raise exception if fails
        try:
            self.server.start_render(job_id)
        except KeyError:
            logger.exception("Failed to start '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def start_next(self) -> Optional[str]:
        """Starts next job in queue and return job ID.  If no jobs in queue, returns None."""
        job = self.queue.get_next_waiting()
        if job:
            self.start(job.id)
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
            self.server.kill_render(job_id, kill)
        except KeyError:
            logger.exception("Failed to stop '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def enqueue(self, job_id: str) -> None:
        """Places a stopped job back in the render queue."""
        try:
            self.server.resume_render(job_id, startnow=False)
        except KeyError:
            logger.exception("Failed to resume '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def delete(self, job_id: str) -> None:
        """Deletes a render job.  Job must not be rendering."""
        try:
            status = self.server.get_status(job_id)
            if status == "Rendering":
                raise JobStatusError("Cannot delete job while it is rendering")
            self.server.clear_job(job_id)
        except KeyError:
            logger.exception("Failed to delete '%s': KeyError" % job_id)
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def enable_node(self, job_id: str, node: str) -> None:
        """
        Enables a render node for a given job.

        :param str job_id: ID of job to modify.
        :param str node: Name of render node.
        """
        logger.debug("Enable %s for %s" % (node, job_id))
        if node not in self.render_nodes:
            raise NodeNotFoundError("Node '%s' not found" % node)
        try:
            self.server.renderjobs[job_id].add_computer(node)
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
            self.server.renderjobs[job_id].remove_computer(node)
        except KeyError:
            raise JobNotFoundError("Job '%s' not found" % job_id)

    def get_summary(self) -> List[Dict[str, Any]]:
        """
        Returns summary info about all jobs on server.
        """
        jobs = []
        for id, job in self.server.renderjobs.items():
            data = job.get_attrs()
            jobs.append(
                {
                    "id": id,
                    "file_path": data["path"],
                    "status": data["status"],
                    "progress": data["progress"],
                    "time_elapsed": data["times"][0],
                    "time_remaining": data["times"][2],
                    "time_created": data["queuetime"],
                }
            )
        return jobs

    def get_status(self) -> List[Dict[str, Any]]:
        """Returns complete status info about all jobs on server."""
        data = []
        for id in self.server.renderjobs:
            data.append(self.get_job_status(id))
        return data

    def _reformat_node_list(self, complist, compstatus):
        node_status = {}
        for node, info in compstatus.items():
            node_status[node] = {
                "rendering": info["active"],
                "enabled": True if node in complist else False,
                "frame": info["frame"],
                "progress": info["progress"],
            }
        return node_status

    def get_job_status(self, job_id: str) -> Dict:
        """Returns details for a render job."""
        # Rearrange data to match new format
        data = self.server.get_attrs(job_id)
        if data == "Index not found.":
            raise JobNotFoundError("Job '%s' not found" % job_id)
        ret = {
            "id": job_id,
            "file_path": data["path"],
            "start_frame": data["startframe"],
            "end_frame": data["endframe"],
            "render_engine": data["render_engine"],
            "render_params": data["render_params"],
            "status": data["status"],
            "progress": data["progress"],
            "time_avg": data["times"][1],
            "time_elapsed": data["times"][0],
            "time_remaining": data["times"][2],
            "time_created": data["queuetime"],
            "node_status": self._reformat_node_list(
                data["complist"], data["compstatus"]
            ),
        }
        return ret

    def shutdown(self) -> None:
        """Prepares controller for clean shutdown."""
        logger.debug("Shutting down controller")
        self.task_thread.shutdown()
        self.save_state()
        self.server.shutdown_server()

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
