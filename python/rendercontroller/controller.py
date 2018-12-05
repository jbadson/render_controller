#!/usr/bin/env python3
import logging
from typing import Sequence, Dict, Any, Type
from uuid import uuid4
from . import job
from .exceptions import JobNotFoundError, NodeNotFoundError


logger = logging.getLogger("controller")


class Config(object):
    """Singleton configuration object."""

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


class RenderController(object):
    """
    Manages render jobs.

    Right now this is a janky hack to decouple the old RenderServer from
    its custom network protocol so we can have a REST API and web front end.
    Eventually it will replace RenderServer and everything will be much
    less terrible.
    """

    def __init__(self, config: Type[Config]) -> None:
        # self.jobs = OrderedDict()
        # This is bad but will get things moving until I have time to
        # rewrite all the terrible stuff in RenderServer.
        job.CONFIG = config
        self.server = job.RenderServer()
        self.render_nodes = set(config.render_nodes)

    def new_job(
        self, path: str, start_frame: int, end_frame: int, render_engine: str, nodes: Sequence[str]
    ) -> str:
        """
        Creates a new render job and places it in queue.

        :param str path: Path to project file.
        :param int start_frame: Start frame number.
        :param int end_frame: End frame number.
        :param str render_engine: Render engine.
        :param list nodes: List of render nodes to enable for this job.
        :return str: ID of newly created job.
        """
        job_id = uuid4().hex
        result = self.server.enqueue({
            "index": job_id,
            "path": path,
            "startframe": start_frame,
            "endframe": end_frame,
            "extraframes": None , # Deprecated
            "render_engine": render_engine,
            "complist": nodes,
        })
        if result != job_id:
            raise RuntimeError(result)
        return job_id

    def start(self, job_id: str) -> None:
        """Starts a render job."""
        # TODO raise exception if fails
        self.server.start_render(job_id)

    def stop(self, job_id: str, kill: bool = True) -> None:
        """
        Stops a render job

        :param str job_id: ID of job to stop.
        :param bool kill: Kill active render processes. Default True.
            If False, currently rendering frames will be allowed to finish.
        """
        self.server.kill_render(job_id, kill)

    def resume(self, job_id: str, startnow: bool = False) -> None:
        """
        Changes a job's status from "Stopped" or "Paused" to "Waiting".
        If startnow == True, start rendering immediately. Otherwise,
        job will be placed in queue to start in the normal order.
        """
        self.server.resume_render(job_id, startnow)

    def delete(self, job_id: str) -> None:
        """Deletes a render job.  Job must not be rendering."""
        self.server.clear_job(job_id)

    def toggle_autostart(self) -> None:
        """
        Toggles state of autostart param.  Autostart determines whether
        the next job in queue will start rendering automatically when the
        preceding one finishes.
        """
        self.server.toggle_autostart()

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

    def get_status(self) -> Dict[str, Any]:
        """
        Returns a list of dicts with server state and summary
        of each job in queue.
        """
        data = self.server.get_attrs()
        # Rearrange data to format for new API
        data.pop("__MESSAGE__")
        statevars = data.pop("__STATEVARS__")
        ret = {"state": statevars}
        # In RenderServer, filename is the index but not the ID
        # ID is only used internally and might not be reliable. For now,
        # continue to use filename as the primary key, but will change
        # in the future.
        jobs = []
        for filename, job in data.items():
            jobs.append(
                {
                    "id": filename,
                    "file_path": job["path"],
                    "status": job["status"],
                    "progress": job["progress"],
                    "time_remaining": job["times"][2],
                }
            )
        ret["jobs"] = jobs
        return ret

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
            "status": data["status"],
            "progress": data["progress"],
            "time_avg": data["times"][1],
            "time_elapsed": data["times"][0],
            "time_remaining": data["times"][2],
            "node_status": self._reformat_node_list(
                data["complist"], data["compstatus"]
            ),
        }
        return ret

    def shutdown(self) -> None:
        """Prepares controller for clean shutdown."""
        self.server.shutdown_server()
