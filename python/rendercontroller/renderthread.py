import time
import threading
import logging
import shutil
import subprocess
import os.path
import re
import shlex
from typing import Type, Optional
from rendercontroller.constants import (
    WAITING,
    RENDERING,
    FINISHED,
    FAILED,
    LOG_EVERYTHING,
)
from rendercontroller.util import Config


class RenderThread(object):
    """Base class for thread objects that handle rendering a single frame with a particular render engine.

    At a minimum, subclasses must implement the `worker` and `stop` methods, and assign values to the
    public instance variables described below.

        status: str = Status of render process: WAITING, RENDERING, FINISHED, or FAILED.
        progress: float = Percent progress of this render process.

    Timers: This class includes two built-in timers: a render timer and a timeout timer. The render timer
    measures the total time taken to render a frame. The timeout timer measures the time since the last
    update received from the render process. The base class does not implement any action when the timeout
    limit is exceeded, so subclasses should implement it as appropriate.
    """

    def __init__(
        self, config: Type[Config], job_id: str, node: str, path: str, frame: int
    ):
        self.config = config
        self.node = node
        self.path = path
        self.frame = frame
        self.status = WAITING
        self.progress: float = 0.0
        self.logger = logging.getLogger(
            f"{job_id} {os.path.basename(self.path)} {self.__class__.__name__} frame {frame} on {node}"
        )
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.time_start: float = 0.0
        self.time_stop: float = 0.0
        self.timeout_timer: float = 0.0

    def elapsed_time(self) -> float:
        """Returns time taken to render the frame in seconds."""
        if not self.time_start:
            return 0.0
        if self.time_stop:
            return self.time_stop - self.time_start
        return time.time() - self.time_start

    def start(self) -> None:
        """Spawns worker thread and starts the render."""
        self.time_start = time.time()
        self.timeout_timer = time.time()
        self.thread.start()

    def is_timed_out(self) -> bool:
        """Returns True if `timeout_timer` exceeds the value for `node_timeout` set in config.

        The purpose of the timeout timer is to catch edge cases where the render node hangs or network
        connectivity is interrupted, but for whatever reason the process does not explicitly fail.
        The `node_timeout` threshold represents the maximum time we will wait between successive updates
        from the node, *not* the max total render time.

        Subclasses may choose whether and how to make use of this in their `worker()` implementation,
        but generally this method should be called every time an update is received from the server, and
        if it returns True the caller should treat the frame as failed.
        """
        if (
            self.timeout_timer
            and time.time() - self.timeout_timer > self.config.node_timeout
        ):
            return True
        return False

    def stop_render_timer(self) -> None:
        self.time_stop = time.time()

    def stop(self) -> None:
        """Must be implemented by subclasses.  This method should terminate the active render process."""
        raise NotImplementedError

    def worker(self) -> None:
        """Must be implemented by subclasses.

        This method will be executed in a new threading.Thread. It must execute the render process update
        the `status` and `progress` instance variables.  It must also call stop_render_timer() when the
        render process exits.
        """
        raise NotImplementedError


class BlenderRenderThread(RenderThread):
    """Handles rendering a single frame in Blender.

    Works with Cycles and Eevee, tested with Blender version 2.93.7 on MacOS and Linux.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pid: Optional[int] = None
        # Allow multiple regex patterns to support the different Blender output formats
        self.patterns = (
            re.compile("Rendered ([0-9]+)/([0-9]+) Tiles"),  # Cycles
            re.compile("Rendering\s+([0-9]+)\s+/\s+([0-9]+)\s+samples"),  # Eevee
        )
        if self.node in self.config.macs:
            self.execpath = self.config.blenderpath_mac
        else:
            self.execpath = self.config.blenderpath_linux

    def stop(self) -> None:
        """Stops the render.

        Sends a kill command to the remote render process by SSH.  This is not ideal, but unless and until
        we have a remote client to manage render processes, it will have to do."""
        if not self.status == RENDERING:
            return
        if not self.pid:
            self.logger.warning(
                "Thread is rendering but no pid value is set. Unable to kill process."
            )
            return
        kill_thread = threading.Thread(target=self._ssh_kill_thread)
        kill_thread.start()

    def _ssh_kill_thread(self):
        """Encapsulates ssh kill command in a new thread in case SSH connection is slow."""
        self.logger.info(f"Attempting to kill pid={self.pid}")
        subprocess.call([shutil.which("ssh"), self.node, f"kill {self.pid}"])
        self.logger.debug("ssh kill thread exited")

    def worker(self) -> None:
        """Runs in a new threading.Thread and renders the specified frame."""
        self.logger.debug("Started worker thread.")
        self.status = RENDERING
        if self.node in self.config.macs:
            # Blender may be upper case in MacOS, but Linux pgrep implementations may lack -i option.
            pgrep = "pgrep -i -n blender"
        else:
            pgrep = "pgrep -n blender"
        cmd = f"{shlex.quote(self.execpath)} -b -noaudio {shlex.quote(self.path)} -f {self.frame} & {pgrep}"
        proc = subprocess.Popen(
            [shutil.which("ssh"), self.node, cmd], stdout=subprocess.PIPE
        )
        for line in iter(proc.stdout.readline, ""):
            if self.status != RENDERING:
                break
            if self.is_timed_out():
                self.status = FAILED
                self.logger.warning("Failed to render: timed out")
                break
            self.parse_line(line)
        self.stop_render_timer()
        self.logger.debug("Worker thread exited.")

    def parse_line(self, bline: bytes) -> None:
        try:
            line: str = bline.decode("UTF-8").strip("\n")
        except UnicodeDecodeError:
            self.logger.exception(f"Failed to decode line to UTF-8")
            return
        if not line:  # Broken pipe
            self.status = FAILED
            self.logger.warning("Failed to render: broken pipe.")
            return
        self.logger.log(level=LOG_EVERYTHING, msg=f'STDOUT "{line}"')
        # Try to get progress from rendered parts
        if line.startswith("Fra:"):
            for regex in self.patterns:
                m = regex.search(line)
                if m:
                    rendered, total = m.group(1), m.group(2)
                    self.progress = int(rendered) / int(total) * 100
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


class Terragen3RenderThread(RenderThread):
    """Handles rendering a single frame in Terragen 3.

    Terragen 3 is quite outdated, so this class is only being included to avoid removing a major feature without
    prior warning.  It's not clear if support for Terragen 4 will be added or if Terragen will be dropped entirely.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pid: Optional[int] = None
        if self.node in self.config.macs:
            self.execpath = self.config.terragenpath_mac
        else:
            self.execpath = self.config.terragenpath_linux

    def stop(self) -> None:
        """Stops the render.

        Sends a kill command to the remote render process by SSH.  This is not ideal, but unless and until
        we have a remote client to manage render processes, it will have to do."""
        if not self.status == RENDERING:
            return
        if not self.pid:
            self.logger.warning(
                "Thread is rendering but no pid value is set. Unable to kill process."
            )
            return
        kill_thread = threading.Thread(target=self._ssh_kill_thread)
        kill_thread.start()

    def _ssh_kill_thread(self):
        """Encapsulates ssh kill command in a new thread in case SSH connection is slow."""
        self.logger.info(f"Attempting to kill pid={self.pid}")
        subprocess.call([shutil.which("ssh"), self.node, f"kill {self.pid}"])
        self.logger.debug("ssh kill thread exited")

    def worker(self) -> None:
        """Runs in a new threading.Thread and renders the specified frame."""
        self.logger.debug("Started worker thread.")
        self.status = RENDERING
        if self.node in self.config.macs:
            # Terragen may be upper case in MacOS, but Linux pgrep implementations may lack -i option.
            pgrep = "pgrep -i -n terragen"
        else:
            pgrep = "pgrep -n terragen"
        cmd = (
            f"{shlex.quote(self.execpath)} -p {shlex.quote(self.path)} -hide "
            + f"-exit -r -f {self.frame} & {pgrep} & wait"
        )
        proc = subprocess.Popen(
            [shutil.which("ssh"), self.node, cmd], stdout=subprocess.PIPE
        )
        for line in iter(proc.stdout.readline, ""):
            if self.status != RENDERING:
                break
            if self.is_timed_out():
                self.status = FAILED
                self.logger.warning("Failed to render: timed out")
                break
            self.parse_line(line)
        self.stop_render_timer()
        self.logger.debug("Worker thread exited.")

    def parse_line(self, bline: bytes) -> None:
        try:
            line: str = bline.decode("UTF-8")
        except UnicodeDecodeError:
            self.logger.exception(f"Failed to decode line to UTF-8")
            return
        if not line:  # Broken pipe
            self.status = FAILED
            self.logger.warning("Failed to render: broken pipe.")
            return
        self.logger.log(level=LOG_EVERYTHING, msg=f'STDOUT "{line}"')
        # Terragen prints percent progress during render pass, so try to find that.
        if line.startswith("Rendering"):
            # NOTE: terragen ALWAYS has at least 2 passes, so progress will go to 100% at least twice.
            # We could track pass names, but probably not worth the effort since it doesn't affect
            # overall render progress.
            for part in line.split():
                if "%" in part:
                    self.progress = float(part[:-1])
                    return

        # Try to detect PID
        if line.strip().isdigit():
            pid = int(line.strip())
            # Terragen echos the frame number at the start of the render, so we must ignore that.
            # If PID happens to be the same as the frame number, then this just means we cannot automatically
            # kill the remote render process if job is stopped. Not ideal, but not the end of the world.
            if pid != self.frame:
                self.pid = pid
                self.logger.info(f"Detected pid={self.pid}.")
            return

        # Detect if frame has finished rendering
        if line.startswith("Finished"):
            self.status = FINISHED
            self.logger.debug("Detected frame finished.")
