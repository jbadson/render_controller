import threading
import time
import os.path
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional
from .renderthread import RenderThread, BlenderRenderThread
from .util import format_time, Config
from .exceptions import JobStatusError, NodeNotFoundError
from .database import StateDatabase
from .status import WAITING, RENDERING, STOPPED, FINISHED, FAILED

logger = logging.getLogger("job")


class RenderJob(object):
    def __init__(
        self,
        config: Type[Config],
        db: Type[StateDatabase],
        id: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: Sequence[str],
        status: str = WAITING,
        time_start: float = 0.0,
        time_stop: float = 0.0,
        time_offset: float = 0.0,
        frames_completed: Optional[List[int]] = None,
    ):
        self.config = config
        self.db = db
        self.id = id
        self.path = path
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.nodes_enabled = set(render_nodes)
        self.status = status
        self.time_start = time_start
        self.time_stop = time_stop
        self.time_offset = time_offset
        # frames_completed cannot simply be a count because frames may fail and be reassigned
        # out of order, and we must know this in order to correctly restore a job from disk.
        self.frames_completed = frames_completed if frames_completed else []

        # LiFo queue because if a frame fails while rendering, we want to re-try it first.
        self.queue = queue.LifoQueue()
        frames = list(range(self.start_frame, self.end_frame + 1))
        frames.reverse()
        for frame in frames:
            if frame not in self.frames_completed:
                self.queue.put(frame)

        self.skip_list = []
        self.node_status = {}
        for node in config.render_nodes:
            self._set_node_status(node)

        self.logger = logger.getChild(os.path.basename(self.path))
        self.logger.info(
            f"placed in queue to render frames {self.start_frame}-{self.end_frame} on nodes {', '.join(self.nodes_enabled)} with ID {self.id}"
        )

        self.master_thread = threading.Thread(target=self._thread, daemon=True)
        self._stop = False

        if self.status == RENDERING:
            # FIXME Can't decide if this should happen here, or if we should reset status and make caller re-start the render.
            self.set_status(WAITING)
            self.render()

    def set_status(self, status: str) -> None:
        """Sets job status and updates it in database."""
        self.status = status
        self.db.update_job_status(self.id, status)

    def render(self) -> None:
        """Starts the render."""
        if self.status == RENDERING:
            raise JobStatusError("Job is already rendering.")
        self.set_status(RENDERING)
        self._start_timer()
        self.master_thread.start()

    def stop(self) -> None:
        """Stops the render and attempts to terminate all current render processes."""
        self._stop = True

    def enable_node(self, node: str) -> None:
        """Enables a node for rendering on this job."""
        if node not in self.config.render_nodes:
            raise NodeNotFoundError(f"'{node}' is not in list of known render nodes")
        if node in self.nodes_enabled:
            return
        self.nodes_enabled.add(node)
        self.db.update_nodes(self.id, tuple(self.nodes_enabled))

    def disable_node(self, node: str) -> None:
        """Disables a node for rendering on this job."""
        if node not in self.config.render_nodes:
            raise NodeNotFoundError(f"'{node}' is not in list of known render nodes")
        if node not in self.nodes_enabled:
            return
        self.nodes_enabled.remove(node)
        self.db.update_nodes(self.id, tuple(self.nodes_enabled))

    def get_progress(self) -> float:
        """Returns percent complete."""
        if self.status == RENDERING and self.start_frame >= self.end_frame:
            # Do not divide by zero
            return 0.0
        return len(self.frames_completed) / (self.end_frame - self.start_frame) * 100

    def get_times(self) -> Tuple[float, float, float]:
        """Returns tuple of (elapsed_time, avg_time_per_frame, est_time_remaining) in seconds."""
        if not self.time_start:
            return 0.0, 0.0, 0.0
        if self.time_stop:
            elapsed = self.time_stop - self.time_start
        else:
            elapsed = time.time() - self.time_start
        if len(self.frames_completed) > 0:
            avg = elapsed / len(self.frames_completed)
        else:
            avg = 0.0
        rem = ((self.end_frame - self.start_frame) - len(self.frames_completed)) * avg
        return elapsed, avg, rem

    def dump(self) -> Dict:
        """Returns dict of key job parameters."""
        elapsed, avg, rem = self.get_times()
        return {
            "id": self.id,
            "path": self.path,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "render_nodes": tuple(self.nodes_enabled),
            "status": self.status,
            "time_start": self.time_start,
            "time_stop": self.time_stop,
            "time_elapsed": elapsed,
            "time_avg_per_frame": avg,
            "time_remaining": rem,
            "frames_completed": self.frames_completed,
            "progress": self.get_progress(),
            "node_status": self.get_node_status(),
        }

    def render_threads_active(self) -> bool:
        """Returns True if any RenderThreads are currently assigned, else False."""
        for node in self.node_status.items():
            if node["thread"] is not None:
                return True
        return False

    def get_node_status(self) -> Dict:
        """Returns a dict containing status for each node.

        Similar to self.node_status but modified for external use."""
        ret = {}
        for node, data in self.node_status.items():
            ret[node] = {
                "frame": data["frame"],
                "progress": data["progress"],
                "enabled": True if node in self.nodes_enabled else False,
                "rendering": True if data["thread"] is not None else False,
            }

    def _set_node_status(
        self,
        node: str,
        frame: Optional[str] = None,
        thread: Optional[Type[RenderThread]] = None,
        progress: int = 0.0,
    ) -> None:
        self.node_status[node] = {
            "frame": frame,
            "thread": thread,
            "progress": progress,
        }

    def _start_timer(self) -> None:
        offset = self.time_offset  # Used when restoring job from disk
        if self.time_start and self.time_stop:
            # If render was previously stopped, we don't care how long it's been.
            offset = self.time_stop - self.time_start
        self.time_start = time.time() - offset
        self.time_offset = 0
        self.db.update_job_time_start(self.id, self.time_start)

    def _stop_timer(self) -> None:
        self.time_stop = time.time()
        self.db.update_job_time_stop(self.id, self.time_stop)

    def _thread(self) -> None:
        """Master thread to manage multiple RenderThreads."""
        self.logger.debug("Started master thread.")
        while not self._stop:
            if self.queue.empty() and not self.render_threads_active():
                logger.debug("Render finished at detector.")
                self._stop_timer()
                self.set_status(FINISHED)
                elapsed, avg, rem = self.get_times()
                self.logger.info(
                    f"Finished render in {format_time(elapsed)}. Avg time per frame: {format_time(avg)}."
                )
                break

            # If all nodes are in skip list, release oldest one.
            if (
                len(self.skip_list) == len(self.nodes_enabled)
                and len(self.nodes_enabled) > 0
            ):
                logger.info("All nodes are in skip list. Releasing oldest one.")
                self._set_node_status(self.skip_list.pop(0))

            # Iterate through nodes, check status, and assign frames
            for node in self.nodes_enabled:
                if self.queue.empty():
                    # If queue empties during iteration, return to outer loop and wait for completion.
                    break
                if node in self.skip_list:
                    continue
                if self.node_status[node]["thread"] is not None:
                    t = self.node_status[node]["thread"]
                    if t.status == RENDERING:
                        self.node_status[node]["progress"] = t.progress
                    elif t.status == FINISHED:
                        self.queue.task_done()
                        self.logger.info(
                            f"Finished frame {t.frame} on {node} after {format_time(t.render_time)}."
                        )
                        self.frames_completed.append(t.frame)
                        self._set_node_status(node)
                        self.db.update_job_frames_completed(
                            self.id, self.frames_completed
                        )
                    elif t.status == FAILED:
                        self.queue.put(t.frame)
                        self.logger.warning(f"Failed to render {t.frame} on {node}.")
                        self.skip_list.append(node)
                        self.logger.debug(f"Added {node} to skip list.")
                        self._set_node_status(node)
                    continue
                # Node is ready to go. Get next frame and start render.
                frame = self.queue.get()
                logger.info(f"Sending frame {frame} to {node}.")
                # TODO Implement terragen thread?
                t = BlenderRenderThread(node, self.path, frame)
                self._set_node_status(node, frame, t)
                t.start()
        logger.debug("Master thread exited.")
