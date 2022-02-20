import time
import threading
import logging
import shutil
import subprocess
import os.path
import re
import shlex
from typing import Type, Optional
from rendercontroller.constants import WAITING, RENDERING, STOPPED, FINISHED, FAILED
from rendercontroller.util import Config


class RenderThread(object):
    """Base class for thread objects that handle rendering a single frame with a particular render engine.

    At a minimum, subclasses must implement the `worker` and `stop` methods, and assign values to the
    public instance variables described below.

        status: str = Status of render process: status.WAITING, status.RENDERING, status.FINISHED, or status.FAILED.
        progress: float = Percent progress of this render process.
        time_stop: float = Epoch time when this render processes ended.
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
        log_base = f"{job_id} {os.path.basename(self.path)} {self.__class__.__name__} "
        instance_info = f"{self.__class__.__name__} frame {frame} on {node}: "
        self.logger = logging.getLogger(log_base + instance_info)
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.time_start: float = 0.0
        self.time_stop: float = 0.0

    def elapsed_time(self) -> float:
        """Returns time taken to render the frame in seconds."""
        if self.time_stop:
            return self.time_start - self.time_stop
        return self.time_start - time.time()

    def start(self) -> None:
        """Spawns worker thread and starts the render."""
        self.time_start = time.time()
        self.thread.start()

    def stop(self) -> None:
        """Must be implemented by subclasses.

        This method should terminate the active render process and ensure the `time_stop` instance variable is set.
        """
        raise NotImplementedError

    def worker(self) -> None:
        """Must be implemented by subclasses.

        This method will be executed in a new threading.Thread. It must execute the render process and ensure
        values are assigned to the `status`, `progress`, and `time_stop` instance variables.
        """
        raise NotImplementedError


class BlenderRenderThread(RenderThread):
    """Handles rendering a single frame in Blender.

    Only verified to work with Cycles render engine up to version 2.93.7 on Linux and MacOS.
    """

    def __init__(self, *args, **kwargs):
        # TODO Expose status as property, let master thread reach in and get it when needed.  No need for retqueue.
        super().__init__(*args, **kwargs)
        self.pid: Optional[int] = None
        self.patterns = (
            re.compile("Rendered ([0-9]+)/([0-9]+) Tiles"), # Cycles
            re.compile("Rendering\s+([0-9]+)\s+/\s+([0-9]+)\s+samples"), # Eevee
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
        self.logger.debug("Started worker thread.")
        # TODO timeout timer? (might be better to put this in master thread)
        self.status = RENDERING
        cmd = f"{shlex.quote(self.execpath)} -b -noaudio {shlex.quote(self.path)} -f {self.frame} & pgrep -i -n blender"
        proc = subprocess.Popen(
            [shutil.which("ssh"), self.node, cmd], stdout=subprocess.PIPE
        )
        for line in iter(proc.stdout.readline, ""):
            if self.status != RENDERING:
                break
            self.parse_line(line)
        self.time_stop = time.time()
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
        # FIXME uncomment when done
        # self.logger.debug(f"BLENDER OUTPUT: {line}")
        # Try to get progress from tiles
        if line.startswith("Fra:"):
            for regex in self.patterns:
                m = regex.search(line)
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
