import threading
import time
import os.path
import shlex
import shutil
import subprocess
import re
import queue
import logging
from typing import Type, List, Tuple, Sequence, Dict, Optional
from .util import format_time, Config

logger = logging.getLogger("job")

# Job statuses
WAITING = "Waiting"
RENDERING = "Rendering"
STOPPED = "Stopped"
FINISHED = "Finished"
FAILED = "Failed"


class RenderThread(object):
    """Base class for thread objects that handle rendering a single frame on a particular render engine.

    At a minimum, subclasses must implement the worker() method and some way to set values for public
    attributes listed below.

    Attributes:
        status = Status of render process (one of WAITING, RENDERING, FINISHED, FAILED).
        pid = Process ID of render process on remote render node.
        progress = Float percent progress of render for this frame.
        time_stop = Epoch time when render finished.
    """

    def __init__(self, node: str, path: str, frame: int):
        self.node = node
        self.path = path
        self.frame = frame
        self.status = WAITING
        self.pid = None
        self.progress = 0.0
        self.logger = logger.getChild(
            f"{os.path.basename(self.path)}:frame {frame} on {self.node}"
        )
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.time_start = 0
        self.time_stop = 0

    @property
    def render_time(self) -> float:
        """Returns time in seconds to render the frame."""
        if self.time_stop:
            return self.time_start - self.time_stop
        return self.time_start - time.time()

    def start(self) -> None:
        """Spawns worker thread and starts the render."""
        self.time_start = time.time()
        self.thread.start()

    def worker(self) -> None:
        """Must be implemented by subclasses.

        This method will be launched in a new threading.Thread. It must execute the
        render process and populate the status, pid, progress, and time_stop attributes,
        or delegate those tasks to other methods.
        """
        raise NotImplementedError


class BlenderRenderThread(RenderThread):
    """Handles rendering a single frame in Blender.

    Only verified to work with Cycles render engine up to version 2.93.7 on Linux and MacOS.
    """

    def __init__(self, node: str, path: str, frame: int):
        # TODO Expose status as property, let master thread reach in and get it when needed.  No need for retqueue.
        super().__init__(node, path, frame)
        self.regex = re.compile("Rendered ([0-9]+)/([0-9]+) Tiles")

    def worker(self) -> None:
        self.logger.debug("Started worker thread.")
        # TODO timeout timer? (might be better to put this in master thread)
        self.status = RENDERING
        cmd = f"{shutil.which('blender')} -b -noaudio {shlex.quote(self.path)} -f {self.frame} & pgrep -n blender"
        proc = subprocess.Popen(
            [shutil.which("ssh"), self.node, cmd], stdout=subprocess.PIPE
        )
        for line in iter(proc.stdout.readline, ""):
            self.parse_line(line)
        self.time_stop = time.time()
        self.logger.debug("Worker thread exited.")

    def parse_line(self, line: bytes) -> None:
        line = line.decode("UTF-8")
        if not line:  # Broken pipe
            self.status = FAILED
            self.logger.warning("Failed to render: broken pipe.")
            return
        self.logger.debug(line)
        # Try to get progress from tiles
        if line.startswith("Fra:"):
            m = self.regex.search(line)
            if m:
                tiles, total = m.group(1), m.group(2)
                self.progress = int(tiles) / int(total) * 100
                return
        # Detect PID from first return line
        # Convoluted because Popen.pid is the local ssh process, not the remote blender process.
        if line.strip().isdigit():
            self.pid = int(line.strip())
            self.logger.info(f"Detected pid={self.pid}.")
            return

        # Detect if frame has finished rendering
        if line.startswith("Saved:"):
            self.status = FINISHED
            self.logger.debug("Detected frame saved.")


class RenderJob(object):
    def __init__(
        self,
        config: Type[Config],
        id: str,
        path: str,
        start_frame: int,
        end_frame: int,
        render_nodes: List[str],
        status: str = WAITING,
        time_start: float = 0.0,
        time_stop: float = 0.0,
        time_offset: float = 0.0,
        frames_completed: Optional[List[int]] = None,
    ):
        self.config = config
        self.id = id
        self.path = path
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.nodes_enabled = render_nodes
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
            self.render()

    def render(self) -> None:
        """Starts the render."""
        self.status = RENDERING
        self._start_timer()
        self.master_thread.start()

    def stop(self) -> None:
        """Stops the render and attempts to terminate all current render processes."""
        self._stop = True

    def enable_node(self, node: str) -> None:
        """Enables a node for rendering on this job."""
        if node not in self.nodes_enabled:
            self.nodes_enabled.append(node)

    def disable_node(self, node: str) -> None:
        """Disables a node for rendering on this job."""
        if node in self.nodes_enabled:
            self.nodes_enabled.remove(node)

    def get_progress(self) -> float:
        """Returns percent complete."""
        return len(self.frames_completed) / (self.end_frame - self.start_frame) * 100

    def get_nodes_progress(self) -> Dict:
        """Returns dict of percent progress for each node."""
        ret = {}
        for node in self.node_status:
            ret[node] = self.node_status[node]["progress"]
        return ret

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
            "render_nodes": self.nodes_enabled,
            "status": self.status,
            "time_start": self.time_start,
            "time_stop": self.time_stop,
            "time_elapsed": elapsed,
            "time_avg_per_frame": avg,
            "time_remaining": rem,
            "frames_completed": self.frames_completed,
            "progress": self.get_progress(),
        }

    def render_threads_active(self) -> bool:
        """Returns True if any RenderThreads are currently assigned, else False."""
        for node in self.node_status.items():
            if node["thread"] is not None:
                return True
        return False

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
            # Resuming a stopped render
            offset = self.time_stop - self.time_start
        self.time_start = time.time() - offset
        self.time_offset = 0

    def _stop_timer(self) -> None:
        self.time_stop = time.time()

    def _thread(self) -> None:
        """Master thread to manage multiple RenderThreads."""
        self.logger.debug("Started master thread.")
        while not self._stop:
            if self.queue.empty() and not self.render_threads_active():
                logger.debug("Render finished at detector.")
                self._stop_timer()
                self.status = FINISHED
                elapsed, avg, rem = self.get_times()
                self.logger.info(f"Finished render in {elapsed}. Avg time per frame: {avg}.")
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
                        self._set_node_status(node)
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



