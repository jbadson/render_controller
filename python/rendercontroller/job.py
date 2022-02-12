import threading
import time
import os.path
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional, Any
from rendercontroller.renderthread import RenderThread, BlenderRenderThread
from rendercontroller.util import format_time, Config
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError
from rendercontroller.database import StateDatabase
from rendercontroller.status import WAITING, RENDERING, STOPPED, FINISHED, FAILED



class RenderJob(object):
    def __init__(
        self,
        config: Type[Config],
        db: StateDatabase,
        id: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: List[str],
        status: str = WAITING,
        time_start: float = 0.0,
        time_stop: float = 0.0,
        time_offset: float = 0.0,
        frames_completed: Sequence[int] = (),
    ):
        self.config = config
        self.db = db
        self.id = id
        self.path = path
        if start_frame > end_frame:
            raise ValueError("End frame cannot be less than start frame.")
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.nodes_enabled: List[str] = render_nodes
        self.status = status
        self.time_start = time_start
        self.time_stop = time_stop
        self.time_offset = time_offset
        self._stop = False

        # frames_completed cannot simply be a count because frames may fail and be reassigned
        # out of order, and we must know this in order to correctly restore a job from disk.
        # Must also be mutable and ordered, so ensure it's a list.
        # FIXME why does it have to be ordered?
        self.frames_completed = list(frames_completed)

        # LiFo because we want to be able to put and re-render failed frames before moving on to others.
        self.queue: queue.LifoQueue = queue.LifoQueue()
        frames = list(range(self.start_frame, self.end_frame + 1))
        frames.reverse()
        for frame in frames:
            if frame not in self.frames_completed:
                self.queue.put(frame)

        # Nodes are added to skip_list when they fail to render a frame. This temporarily disables
        # the node to prevent the scheduler from continuously trying to assign frames to a node
        # that is having some kind of problem.  Nodes are removed from skip_list in FiFo order for
        # each frame successfully rendered on another node, or if all nodes end up in skip_list.
        self.skip_list: List[str] = []
        self.node_status: Dict[str, dict] = {}
        for node in config.render_nodes:
            self._set_node_status(node)

        self.logger = logging.getLogger(f"RenderJob: {os.path.basename(self.path)}")
        self.logger.info(
            f"placed in queue to render frames {self.start_frame}-{self.end_frame} on nodes {', '.join(self.nodes_enabled)} with ID {self.id}"
        )
        self._reset_render_state()
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
        if self.time_start or self.time_stop:
            # Resuming a render
            self.logger.debug("Resetting render state.")
            self._reset_render_state()
        self.set_status(RENDERING)
        self._start_timer()
        self.master_thread.start()

    def stop(self) -> None:
        """Stops the render and attempts to terminate all active render processes."""
        self.logger.info("Stopping job.")
        self._stop = True
        # Ensure all rendering frames are put back in queue.  Do not leave this to
        # _mainloop because there is a chance frames could be missed depending on
        # where in the two iterations the _stop flag is detected.
        for node in self.node_status:
            thread = self.node_status[node]["thread"]
            if thread:
                # Don't care what thread.status is because the existence of thread implies
                # completion hasn't been detected in _mainloop even if thread is finished.
                # If all else fails, it's better to re-render a frame than to skip one.
                thread.stop()
                self.queue.put(thread.frame)
        if self.master_thread and self.master_thread.is_alive():
            self.logger.debug(f"Waiting for master thread to exit.")
            self.master_thread.join()
        self._stop_timer()
        self.set_status(STOPPED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Stopped render after {format_time(elapsed)}. Avg time per frame: {format_time(avg)}. "
            + "It may take a few moments for all render processes to terminate."
        )

    def enable_node(self, node: str) -> None:
        """Enables a node for rendering on this job."""
        if node not in self.config.render_nodes:
            raise NodeNotFoundError(f"'{node}' is not in list of known render nodes")
        if node in self.nodes_enabled:
            return
        self.nodes_enabled.append(node)
        self.logger.info(f"Enabled {node} for rendering.")
        self.db.update_nodes(self.id, self.nodes_enabled)

    def disable_node(self, node: str) -> None:
        """Disables a node for rendering on this job."""
        if node not in self.config.render_nodes:
            raise NodeNotFoundError(f"'{node}' is not in list of known render nodes")
        if node not in self.nodes_enabled:
            return
        self.nodes_enabled.remove(node)
        self.logger.info(f"Disabled {node} for rendering.")
        self.db.update_nodes(self.id, self.nodes_enabled)

    def get_progress(self) -> float:
        """Returns percent complete."""
        return (
            len(self.frames_completed) / (self.end_frame - self.start_frame + 1) * 100
        )

    def get_times(self) -> Tuple[float, float, float]:
        """Returns tuple of (elapsed_time, avg_time_per_frame, est_time_remaining) in seconds.

        If job is rendering but no frames have yet finished, avg_time_per_frame and est_time_remaining
        will both be 0.0. This is obviously not accurate, but less messy than dealing with infinities
        or multiple return types."""
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
        rem = ((self.end_frame - self.start_frame + 1) - len(self.frames_completed)) * avg
        return elapsed, avg, rem

    def dump(self) -> Dict[str, Any]:
        """Returns dict of key job parameters."""
        elapsed, avg, rem = self.get_times()
        return {
            "id": self.id,
            "path": self.path,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "render_nodes": sorted(self.nodes_enabled),
            "status": self.status,
            "time_start": self.time_start,
            "time_stop": self.time_stop,
            "time_elapsed": elapsed,
            "time_avg_per_frame": avg,
            "time_remaining": rem,
            "frames_completed": self.frames_completed,
            "progress": self.get_progress(),
            "node_status": self.get_nodes_status(),
        }

    def render_threads_active(self) -> bool:
        """Returns True if any RenderThreads are currently assigned, else False."""
        for node in self.node_status.values():
            if node["thread"] is not None:
                return True
        return False

    def get_nodes_status(self) -> Dict:
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
        return ret

    def _reset_render_state(self) -> None:
        """Resets internal state in preparation for rendering."""
        self._stop = False
        self.master_thread = threading.Thread(target=self._mainloop, daemon=True)
        for node in self.config.render_nodes:
            self._set_node_status(node)

    def _set_node_status(
        self,
        node: str,
        frame: Optional[int] = None,
        thread: Optional[RenderThread] = None,
        progress: float = 0.0,
    ) -> None:
        self.node_status[node] = {
            "frame": frame,
            "thread": thread,
            "progress": progress,
        }

    def _start_timer(self) -> None:
        """Starts the render timer."""
        # self.time_offset is used when restoring a job from disk that was actively rendering when
        # the server shut down.  It represents the elapsed render time before the server was shut
        # down, and is used to correct the new start_time so that subsequent calculations do not
        # include the time while the server was offline.
        if not self.time_start:
            # Render has never been started, so server downtime is irrelevant.
            self.time_offset = 0.0
        if self.time_start and self.time_stop:
            # Job was stopped or finished. Server downtime is irrelevant but, we must still
            # account for the render time that has already elapsed.
            #FIXME this works when restoring a job, but not when restarting a stopped job.
            # In that case, offset should be time.time() - self.stop_time
            self.time_offset = self.time_stop - self.time_start
            self.time_stop = 0.0
        self.time_start = time.time() - self.time_offset
        self.time_offset = 0.0
        self.logger.debug(f"Started job timer: {self.time_start}")
        self.db.update_job_time_start(self.id, self.time_start)

    def _stop_timer(self) -> None:
        self.time_stop = time.time()
        self.logger.debug(f"Stopped job timer: {self.time_stop}")
        self.db.update_job_time_stop(self.id, self.time_stop)

    def _render_finished(self) -> None:
        self._stop_timer()
        self.set_status(FINISHED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Finished render in {format_time(elapsed)}. Avg time per frame: {format_time(avg)}."
        )

    def _frame_finished(self, node: str, thread: RenderThread):
        self.queue.task_done()
        self.logger.info(
            f"Finished frame {thread.frame} on {node} after {format_time(thread.render_time)}."
        )
        self.frames_completed.append(thread.frame)
        self._set_node_status(node)
        self.db.update_job_frames_completed(self.id, self.frames_completed)
        # Frame successfully finished, try to pop a node from skip list
        self._pop_skipped_node()

    def _frame_failed(self, node: str, thread: RenderThread):
        self.queue.put(thread.frame)
        self.logger.warning(f"Failed to render {thread.frame} on {node}.")
        self.skip_list.append(node)
        self.logger.debug(f"Added {node} to skip list.")
        self._set_node_status(node)

    def _pop_skipped_node(self):
        if not self.skip_list:
            return
        node = self.skip_list.pop(0)
        self._set_node_status(node)
        self.logger.debug(f"Released {node} from skip list.")

    def _mainloop(self) -> None:
        """Master thread to manage multiple RenderThreads."""
        self.logger.debug("Started master thread.")
        while not self._stop:
            time.sleep(0.01)
            if self.queue.empty() and not self.render_threads_active():
                self._render_finished()
                break

            if len(self.skip_list) >= len(self.nodes_enabled):
                self.logger.debug(f"All nodes are in skip list. Releasing oldest one.")
                self._pop_skipped_node()

            # Iterate through nodes, assign frames, and check status
            for node in self.nodes_enabled:
                time.sleep(0.01)
                if self._stop:
                    # Cleanup is handled by the stop() method.
                    break
                if node in self.skip_list:
                    continue
                if self.node_status[node]["thread"]:
                    t = self.node_status[node]["thread"]
                    if t.status == RENDERING:
                        self.node_status[node]["progress"] = t.progress
                    elif t.status == FINISHED:
                        self._frame_finished(node, t)
                    elif t.status == FAILED:
                        self._frame_failed(node, t)
                    continue
                # Node is idle, assign next frame.
                if not self.queue.empty():
                    frame = self.queue.get()
                    self.logger.info(f"Sending frame {frame} to {node}.")
                    # TODO Implement terragen thread?
                    t = BlenderRenderThread(self.config, node, self.path, frame)
                    self._set_node_status(node, frame, t)
                    t.start()

        self.logger.debug("Master thread exited.")
