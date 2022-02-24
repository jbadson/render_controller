import threading
import time
import os.path
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional, Any
from rendercontroller.constants import (
    WAITING,
    RENDERING,
    STOPPED,
    FINISHED,
    FAILED,
    BLENDER,
    TERRAGEN,
)
from rendercontroller.renderthread import (
    RenderThread,
    BlenderRenderThread,
    Terragen3RenderThread,
)
from rendercontroller.util import format_time, Config
from rendercontroller.exceptions import JobStatusError, NodeNotFoundError
from rendercontroller.database import StateDatabase


class Executor(object):
    """Manages the execution of a render process on a particular node.

    Deep lore: Why does this class even exist? The plan has long been to remove the SSH dependency and
    run a client on render nodes to manage render processes locally. It's not clear if that will ever
    materialize because SSH has worked well enough for our purposes so far, but this class was added in
    the spirit of modularity to provide a generic interface between the frame distribution logic and the
    render execution logic. If and when the client is implemented, the RenderThreads will live there,
    which is why we don't want RenderJob to invoke them directly.
    """

    def __init__(self, config: Type[Config], job_id: str, path: str, node: str):
        self.config = config
        self.job_id = job_id
        self.node = node
        self.path = path
        self.idle: bool = True
        self.thread: Optional[RenderThread] = None
        # Guess render engine based on file extension.
        if self.path.lower().endswith(".blend"):
            self.engine = BLENDER
        elif self.path.lower().endswith(".tgd"):
            self.engine = TERRAGEN
        else:
            raise ValueError("Could not determine render engine from filename.")

    @property
    def status(self) -> str:
        if self.thread:
            return self.thread.status
        return WAITING

    @property
    def progress(self) -> float:
        if self.thread:
            return self.thread.progress
        return 0.0

    @property
    def frame(self) -> Optional[int]:
        if self.thread:
            return self.thread.frame
        return None

    def elapsed_time(self) -> float:
        if self.thread:
            return self.thread.elapsed_time()
        return 0.0

    def is_idle(self) -> bool:
        # FIXME Still not sure how to deal with this.  Executor is idle if thread does not exist, or if thread.status
        # is finished or stopped (waiting implies it's about to start).  But still need way for mainloop to register
        # that a thread has finished. Going with ack_done for now, but not sure it's the right approach.
        return self.idle

    def ack_done(self) -> None:
        """Tells Executor that the calling function has registered that render has finished or was stopped.

        This is necessary to ensure the calling function has had an opportunity to perform necessary cleanup
        tasks before this Executor is marked as idle and ready to accept another frame.
        """
        if self.thread and self.thread.status == RENDERING:
            raise RuntimeError("Render is not done.")
        self.idle = True

    def render(self, frame: int) -> None:
        if self.thread and self.thread.status == RENDERING:
            raise RuntimeError("Node already has an active render process.")
        if self.engine == BLENDER:
            self.thread = BlenderRenderThread(
                config=self.config,
                job_id=self.job_id,
                node=self.node,
                path=self.path,
                frame=frame,
            )
        elif self.engine == TERRAGEN:
            self.thread = Terragen3RenderThread(
                config=self.config,
                job_id=self.job_id,
                node=self.node,
                path=self.path,
                frame=frame,
            )
        else:
            raise RuntimeError("No suitable RenderThread subclass found.")
        self.idle = False
        self.thread.start()

    def stop(self) -> None:
        if self.thread:
            self.thread.stop()


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
        self._stop: bool
        self.master_thread: threading.Thread
        self._reset_render_state()

        # frames_completed cannot simply be a count because frames may fail and be reassigned
        # out of order, and we must know this in order to correctly restore a job from disk.
        self.frames_completed = set(frames_completed)

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
        self.node_status: Dict[str, Executor] = {}
        for node in config.render_nodes:
            self.node_status[node] = Executor(self.config, self.id, self.path, node)

        self.logger = logging.getLogger(
            f"{self.id} {os.path.basename(self.path)} RenderJob"
        )
        self.logger.info(
            f"placed in queue to render frames {self.start_frame}-{self.end_frame} on nodes {', '.join(self.nodes_enabled)} with ID {self.id}"
        )
        if self.status == RENDERING:
            self._set_status(WAITING)
            self.render()

    def _set_status(self, status: str) -> None:
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
        self._set_status(RENDERING)
        self._start_timer()
        self.master_thread.start()

    def stop(self) -> None:
        """Stops the render and attempts to terminate all active render processes."""
        self.logger.info("Stopping job.")
        self._stop = True
        # Ensure all rendering frames are put back in queue.  Do not leave this to
        # _mainloop because there is a chance frames could be missed depending on
        # where in the two iterations the _stop flag is detected.
        for executor in self.node_status.values():
            executor.stop()
            frame = executor.frame
            if frame:
                self.queue.put(frame)
        if self.master_thread and self.master_thread.is_alive():
            self.logger.debug(f"Waiting for master thread to exit.")
            self.master_thread.join()
        self._stop_timer()
        self._set_status(STOPPED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Stopped render after {format_time(elapsed)}. Avg time per frame: {format_time(avg)}. "
            + "It may take a few moments for all render processes to terminate."
        )

    def reset_waiting(self) -> None:
        """If job has been stopped, reset status to waiting so it can be started by autostart."""
        if self.status != STOPPED:
            raise JobStatusError(self.status)
        self._set_status(WAITING)

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
        rem = (
            (self.end_frame - self.start_frame + 1) - len(self.frames_completed)
        ) * avg
        return elapsed, avg, rem

    def dump(self) -> Dict[str, Any]:
        """Returns dict of key job parameters."""
        elapsed, avg, rem = self.get_times()
        return {
            "id": self.id,
            "path": self.path,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "nodes_enabled": sorted(self.nodes_enabled),
            "status": self.status,
            "time_start": self.time_start,
            "time_stop": self.time_stop,
            "time_elapsed": elapsed,
            "time_avg_per_frame": avg,
            "time_remaining": rem,
            "frames_completed": sorted(self.frames_completed),
            "progress": self.get_progress(),
            "node_status": self.get_nodes_status(),
        }

    def frames_rendering(self) -> bool:
        """Returns True if any frames are currently rendering, else False."""
        for executor in self.node_status.values():
            if not executor.is_idle():
                return True
        return False

    def get_nodes_status(self) -> Dict:
        """Returns a dict containing status for each node.

        Similar to self.node_status but modified for external use."""
        ret = {}
        for node, executor in self.node_status.items():
            ret[node] = {
                "frame": executor.frame,
                "progress": executor.progress,
                "enabled": True if node in self.nodes_enabled else False,
                "rendering": True if not executor.is_idle() else False,
            }
        return ret

    def _reset_render_state(self) -> None:
        """Resets internal state in preparation for rendering."""
        self._stop = False
        self.master_thread = threading.Thread(target=self._mainloop, daemon=True)

    def _start_timer(self) -> None:
        """Starts the render timer by setting the `time_start` instance variable.

        For a brand new job, the `time_start` is simply now, but under certain circumstances a correction factor is
        applied.  This is because jobs can be stopped and resumed, and the server can be shut down and restarted, but
        render time calculations should reflect only the time the job was actually rendering. Rather than attempting
        to account for this in each calculation, we offset the `time_start` by an appropriate amount to correct for it.
        """
        # `time_offset` is used when restoring from disk. It is the render time elapsed before the server shut down.
        correction = self.time_offset
        if not self.time_start:
            # Render has never been started, so server downtime is irrelevant.
            correction = 0.0
        if self.time_start and self.time_stop:
            # Job was stopped or finished. Server downtime is irrelevant but, we must still
            # account for the render time that has already elapsed.
            # FIXME this works when restoring a job, but not when restarting a stopped job.
            # In that case, offset should be time.time() - self.stop_time
            correction = self.time_stop - self.time_start
            self.time_stop = 0.0
        self.time_start = time.time() - correction
        self.time_offset = 0.0
        self.logger.debug(f"Started job timer: {self.time_start}")
        self.db.update_job_time_start(self.id, self.time_start)

    def _stop_timer(self) -> None:
        self.time_stop = time.time()
        self.logger.debug(f"Stopped job timer: {self.time_stop}")
        self.db.update_job_time_stop(self.id, self.time_stop)

    def _render_finished(self) -> None:
        self._stop_timer()
        self._set_status(FINISHED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Finished render in {format_time(elapsed)}. Avg time per frame: {format_time(avg)}."
        )

    def _frame_finished(self, node: str):
        executor = self.node_status[node]
        self.queue.task_done()
        self.logger.info(
            f"Finished frame {executor.frame} on {node} after {format_time(executor.elapsed_time())}."
        )
        self.frames_completed.add(executor.frame)
        executor.ack_done()
        self.db.update_job_frames_completed(self.id, self.frames_completed)
        # Frame successfully finished, try to pop a node from skip list
        self._pop_skipped_node()

    def _frame_failed(self, node: str):
        executor = self.node_status[node]
        self.logger.warning(f"Failed to render {executor.frame} on {node}.")
        self.queue.put(executor.frame)
        self.logger.debug(f"Returned frame {executor.frame} to queue.")
        self.skip_list.append(node)
        self.logger.debug(f"Added {node} to skip list.")
        executor.ack_done()

    def _pop_skipped_node(self):
        if not self.skip_list:
            return
        node = self.skip_list.pop(0)
        self.logger.debug(f"Released {node} from skip list.")

    def _mainloop(self) -> None:
        """Master thread to manage multiple RenderThreads."""
        self.logger.debug("Started master thread.")
        while not self._stop:
            time.sleep(0.01)
            if self.queue.empty() and not self.frames_rendering():
                self._render_finished()
                break

            if len(self.skip_list) > 0 and len(self.skip_list) >= len(
                self.nodes_enabled
            ):
                self.logger.debug(f"All nodes are in skip list. Releasing oldest one.")
                self._pop_skipped_node()

            # Iterate through nodes, assign frames, and check status
            for node in self.config.render_nodes:
                time.sleep(0.01)
                if self._stop:
                    # Cleanup is handled by the stop() method.
                    break
                # Check status of all nodes, not just enabled.  User may disable a node after a frame
                # has been assigned, so we need to continue monitoring status until RenderThread ends.
                executor = self.node_status[node]
                if not executor.is_idle():
                    if executor.status == FINISHED:
                        self._frame_finished(node)
                    elif executor.status == FAILED:
                        self._frame_failed(node)
                    continue
                # Now check if any enabled nodes are ready for a new frame.
                if node in self.nodes_enabled:
                    if node in self.skip_list:
                        continue
                    if self.queue.empty():
                        # All frames assigned, but not necessarily done rendering.
                        # Continue iterating until all Executors report done.
                        continue
                    # Node is idle, assign next frame
                    frame = self.queue.get()
                    self.logger.info(f"Sending frame {frame} to {node}.")
                    # TODO Implement terragen thread?
                    executor.render(frame)

        self.logger.debug("Master thread exited.")
