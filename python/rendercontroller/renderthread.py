import time
import threading
import logging
import shutil
import subprocess
import os.path
import re
import shlex
from typing import Type, Optional
from rendercontroller.util import Config
from rendercontroller.status import WAITING, RENDERING, STOPPED, FINISHED, FAILED



class RenderThread(object):
    """Base class for thread objects that handle rendering a single frame on a particular render engine.

    At a minimum, subclasses must implement the worker() and stop() methods and some way to set values for
    public attributes listed below.

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
        self.pid: Optional[int] = None
        self.progress: float = 0.0
        self.logger = logging.getLogger(
            f"{self.__class__.__name__}: {os.path.basename(self.path)} frame {frame} on {self.node}"
        )
        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.time_start: float = 0.0
        self.time_stop: float = 0.0

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

    def stop(self) -> None:
        """Stops the render."""
        raise NotImplementedError

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

    def __init__(self, config: Type[Config], node: str, path: str, frame: int):
        # TODO Expose status as property, let master thread reach in and get it when needed.  No need for retqueue.
        super().__init__(node, path, frame)
        self.regex = re.compile("Rendered ([0-9]+)/([0-9]+) Tiles")
        if node in config.macs:
            self.execpath = config.blenderpath_mac
        else:
            self.execpath = config.blenderpath_linux

    def stop(self) -> None:
        """Stops the render.

        Sends a kill command to the remote render process by SSH.  This is not ideal, but unless and until
        we have a remote client to manage render processes, it will have to do."""
        if not self.status == RENDERING:
            return
        if not self.pid:
            self.logger.warning("Thread is rendering but no pid value is set. Unable to kill process.")
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
        #FIXME uncomment when done
        #self.logger.debug(f"BLENDER OUTPUT: {line}")
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
