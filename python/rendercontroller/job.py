import threading
import time
import os.path
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional, Any, Set
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
from rendercontroller.database import StateDatabase, DBFILE_NAME


threadlock = threading.Lock()


class Executor(object):
    """Manages the execution of a render process on a particular node.

    Deep lore: Why does this class even exist? The plan has long been to remove the SSH dependency and
    run a client on render nodes to manage render processes locally. It's not clear if that will ever
    materialize because SSH has worked well enough for our purposes so far, but this class was added in
    the spirit of modularity to provide a generic interface between the frame distribution logic and the
    render execution logic. If and when the client is implemented, the RenderThreads will live there,
    which is why we don't want RenderJob to invoke them directly.
    """

    def __init__(
        self,
        config: Type[Config],
        job_id: str,
        path: str,
        node: str,
        enabled: bool = False,
    ):
        self.config = config
        self.job_id = job_id
        self.node = node
        self.path = path
        self.enabled = enabled
        self.idle: bool = True
        self.thread: Optional[RenderThread] = None

        self.logger = logging.getLogger(
            f"{job_id} {os.path.basename(path)} Executor.{node}"
        )

        # Guess render engine based on file extension.
        if self.path.lower().endswith(".blend"):
            self.engine = BLENDER
        elif self.path.lower().endswith(".tgd"):
            self.engine = TERRAGEN
        else:
            raise ValueError("Could not determine render engine from filename.")
        self.logger.debug(f"Set render engine to {self.engine}")

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

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def is_enabled(self) -> bool:
        # FIXME this is redundant, along with is_idle.  Pick a convention and stick to it.
        return self.enabled

    def is_idle(self) -> bool:
        """Returns True if node is ready to render a frame.

        This implies that the node is not only technically able to accept a new frame, but also if it has finished
        rendering a frame, that the caller has called `ack_done()` to signify that any post-render tasks have been
        completed and the node should be made available for rendering.
        """
        return self.idle

    def ack_done(self) -> None:
        """Acknowledges that a frame has finished rendering.

        This is necessary to ensure the caller has had an opportunity to perform necessary post-render tasks before
        the node is marked as idle and ready to accept another frame.
        """
        if self.thread and self.thread.status == RENDERING:
            raise RuntimeError("Render is not done.")
        self.logger.debug("Caller acknowledged frame done.")
        self.idle = True

    def render(self, frame: int) -> None:
        """Renders a frame"""
        if self.thread and self.thread.status == RENDERING:
            raise RuntimeError("Node already has an active render process.")
        self.logger.debug(f"Assigned frame {frame}")
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
        """Shuts down the executor."""
        if self.thread:
            self.logger.debug("RenderThread exists, stopping.")
            self.thread.stop()
        self.logger.debug("Executor terminated.")


class RenderJob(object):
    """Represents a project to be rendered."""

    def __init__(
        self,
        config: Type[Config],
        id: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: Tuple[str, ...],
        status: str = WAITING,
        time_start: float = 0.0,
        time_stop: float = 0.0,
        time_offset: float = 0.0,
        frames_completed: Optional[Set[int]] = None,
    ):
        self.config = config
        self.id = id
        self.path = path
        if start_frame > end_frame:
            raise ValueError("End frame cannot be less than start frame.")
        self.start_frame = start_frame
        self.end_frame = end_frame
        for node in render_nodes:
            if node not in self.config.render_nodes:
                raise NodeNotFoundError(f"'{node}' not in configured render nodes")
        self.status = status
        self.time_start = time_start
        self.time_stop = time_stop
        self.time_offset = time_offset

        self._stop: bool = False
        self._test_obj = (
            None  # Unit tests may use this to inject an instrumentation object.
        )
        self.db = StateDatabase(os.path.join(self.config.work_dir, DBFILE_NAME))
        self.master_thread: threading.Thread
        self.executors: Dict[str, Executor] = {}
        self.logger = logging.getLogger(
            f"{self.id} {os.path.basename(self.path)} RenderJob"
        )

        # In order to restore a partially-rendered job from disk, we need to know exactly which frames
        # have already been rendered. This cannot be a simple count because various race conditions exist
        # which may cause the sequence of completed frames to be discontinuous at certain times.
        self.frames_completed = frames_completed if frames_completed else set()

        # LiFo because we want to be able to put and re-render failed frames before moving on to others.
        self.queue: queue.LifoQueue = queue.LifoQueue()
        frames = list(range(self.start_frame, self.end_frame + 1))
        frames.reverse()
        for frame in frames:
            if frame not in self.frames_completed:
                self.queue.put(frame)

        # Nodes are added to skip_list when they fail to render a frame.  Nodes are not assigned
        # new frames while in the list. This is to prevent the frame from being continually reassigned
        # to the offline node, which can result in it not being successfully re-rendered until all other
        # frames have finished, or in certain cases a deadlock.
        self.skip_list: List[str] = []

        self._reset_render_state(render_nodes)
        self.logger.info(
            f"placed in queue to render frames {self.start_frame}-{self.end_frame} on nodes "
            f"{', '.join(self.get_enabled_nodes())} with ID {self.id}"
        )
        if self.status == RENDERING:
            self._set_status(WAITING)
            self.render()

    def _set_status(self, status: str) -> None:
        """Sets job status and updates it in database."""
        with threadlock:  # This method can be called from both public methods and master_thread.
            self.status = status
            self.db.update_job_status(self.id, status)

    def render(self) -> None:
        """Starts the render."""
        if self.status == RENDERING:
            raise JobStatusError("Job is already rendering.")
        if self.time_start or self.time_stop:
            # Resuming a render
            self.logger.debug("Resetting render state.")
            self._reset_render_state(self.get_enabled_nodes())
        self._set_status(RENDERING)
        self._start_timer()
        self.master_thread.start()

    def stop(self) -> None:
        """Stops the render and attempts to terminate all active render processes."""
        if self.status != RENDERING:
            raise JobStatusError("Job is not rendering.")
        self.logger.info("Stopping job.")
        self._stop = True
        for executor in self.executors.values():
            executor.stop()
        if self.master_thread.is_alive():
            self.logger.debug(f"Waiting for master thread to exit.")
            self.master_thread.join()
        self._stop_timer()
        self._set_status(STOPPED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Stopped render after {format_time(elapsed)}. Avg time per frame: {format_time(avg)}."
        )

    def reset_waiting(self) -> None:
        """If job has been stopped, reset status to waiting so it can be started by autostart."""
        if self.status != STOPPED:
            raise JobStatusError(self.status)
        self._set_status(WAITING)

    def enable_node(self, node: str) -> None:
        """Enables a node for rendering on this job."""
        try:
            ex = self.executors[node]
        except KeyError:
            raise NodeNotFoundError(f"'{node}' is not a recognized render node.")
        if ex.is_enabled():
            return
        ex.enable()
        self.logger.info(f"Enabled {node} for rendering.")
        self.db.update_nodes(self.id, self.get_enabled_nodes())

    def disable_node(self, node: str) -> None:
        """Disables a node for rendering on this job."""
        try:
            ex = self.executors[node]
        except KeyError:
            raise NodeNotFoundError(f"'{node}' is not a recognized render node.")
        if not ex.is_enabled():
            return
        ex.disable()
        self.logger.info(f"Disabled {node} for rendering.")
        self.db.update_nodes(self.id, self.get_enabled_nodes())

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
        """Returns dict of all necessary information to define this job's current state."""
        elapsed, avg, rem = self.get_times()
        return {
            "id": self.id,
            "path": self.path,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
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

    def executors_active(self) -> bool:
        """Returns True if any frames are currently rendering, else False."""
        for executor in self.executors.values():
            if not executor.is_idle():
                return True
        return False

    def get_enabled_nodes(self) -> Tuple[str, ...]:
        return tuple(ex.node for ex in self.executors.values() if ex.is_enabled())

    def get_nodes_status(self) -> Dict:
        """Returns a dict containing status for each render node."""
        ret = {}
        for node, executor in self.executors.items():
            ret[node] = {
                "frame": executor.frame,
                "progress": executor.progress,
                "enabled": executor.is_enabled(),
                "rendering": not executor.is_idle(),
            }
        return ret

    def _reset_render_state(self, nodes_enabled: Sequence[str]) -> None:
        """Resets internal state in preparation for rendering."""
        self._stop = False
        for node in self.config.render_nodes:
            enable = True if node in nodes_enabled else False
            self.executors[node] = Executor(
                self.config, self.id, self.path, node, enable
            )
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
            correction = self.time_stop - self.time_start
            self.time_stop = 0.0
        self.time_start = time.time() - correction
        self.time_offset = 0.0
        self.logger.debug(f"Started job timer: {self.time_start}")
        self.db.update_job_time_start(self.id, self.time_start)

    def _stop_timer(self) -> None:
        """Stops the render timer."""
        with threadlock:  # This method can be called from both public methods and master_thread
            self.time_stop = time.time()
            self.logger.debug(f"Stopped job timer: {self.time_stop}")
            self.db.update_job_time_stop(self.id, self.time_stop)

    def _render_finished(self) -> None:
        """Marks the render as finished."""
        self._stop_timer()
        self._set_status(FINISHED)
        elapsed, avg, rem = self.get_times()
        self.logger.info(
            f"Finished render in {format_time(elapsed)}. Avg time per frame: {format_time(avg)}."
        )

    def _frame_finished(self, executor: Executor) -> None:
        """Marks a frame as finished and prepares the node to receive a new frame."""
        self.queue.task_done()
        self.logger.info(
            f"Finished frame {executor.frame} on {executor.node} after {format_time(executor.elapsed_time())}."
        )
        self.frames_completed.add(executor.frame)
        executor.ack_done()
        self.db.update_job_frames_completed(self.id, self.frames_completed)
        # Frame successfully finished, try to pop a node from skip list
        self._pop_skipped_node()

    def _frame_failed(self, executor: Executor) -> None:
        """Marks a frame as failed and returns it to queue."""
        self.logger.warning(f"Failed to render {executor.frame} on {executor.node}.")
        self.queue.put(executor.frame)
        self.logger.debug(f"Returned frame {executor.frame} to queue.")
        if not self._stop:
            # Doesn't count if failure was because job is being terminated.
            self.skip_list.append(executor.node)
            self.logger.debug(f"Added {executor.node} to skip list.")
        executor.ack_done()

    def _pop_skipped_node(self):
        """Removes the oldest node from the skip list."""
        if not self.skip_list:
            return
        node = self.skip_list.pop(0)
        self.logger.debug(f"Released {node} from skip list.")

    def _executor_is_ready(self, executor: Executor) -> bool:
        if not executor.is_idle():
            # Check if executor is done and collect exit status.
            if executor.status == FINISHED:
                self._frame_finished(executor)
            elif executor.status == FAILED:
                self._frame_failed(executor)
                return False
            else:
                # Executor still rendering
                return False
        if not executor.is_enabled():
            return False
        if executor.node in self.skip_list:
            return False
        if self._stop:
            # Do not assign new frames, but keep going until all executors finish.
            return False
        return True

    def _mainloop(self) -> None:
        """Runs in a new threading.Thread.  Manages the rendering of all the frames for this job."""
        self.logger.debug("Started master thread.")
        # Counts only used for unit testing.
        if self._test_obj:
            self._test_obj.reset("outer_count")
            self._test_obj.reset("inner_count")
        while True:
            time.sleep(0.01)
            if self._test_obj:
                self._test_obj.inc("outer_count")
            if self._stop:
                # Stop requested, but keep going until all executors have finished and we have ack'd them.
                if not self.executors_active():
                    self.logger.debug("All executors done. Stopping mainloop")
                    break
            elif self.queue.empty() and not self.executors_active():
                self._render_finished()
                break

            if self.skip_list and len(self.skip_list) >= len(self.get_enabled_nodes()):
                self.logger.debug(f"All nodes are in skip list. Releasing oldest one.")
                self._pop_skipped_node()

            # Iterate through nodes, check status, and assign frames.
            if self._test_obj:
                self._test_obj.reset("inner_count")
            for node in self.config.render_nodes:
                if self._test_obj:
                    self._test_obj.inc("inner_count")
                executor = self.executors[node]
                if self._executor_is_ready(executor) and not self.queue.empty():
                    frame = self.queue.get()
                    self.logger.info(f"Sending frame {frame} to {node}.")
                    executor.render(frame)

        self.logger.debug("Master thread exited.")
