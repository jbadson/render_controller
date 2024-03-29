import os
from typing import Dict, Any, List


def get_file_type(entry: os.DirEntry) -> str:
    """Returns a one-character string representing the file type of `entry`."""
    if entry.is_dir():
        return "d"
    elif entry.is_file():
        return "f"
    elif entry.is_symlink():
        return "l"
    else:
        return ""


def list_dir(directory: str) -> List[Dict[str, Any]]:
    """Presents the output of os.scandir() as something JSON-serializable."""
    contents = []
    for i in os.scandir(directory):
        contents.append(
            {
                "name": i.name,
                "path": i.path,
                "type": get_file_type(i),
                "size": i.stat().st_size,
                "atime": i.stat().st_atime,
                "mtime": i.stat().st_mtime,
                "ctime": i.stat().st_ctime,
                "ext": os.path.splitext(i.name)[1],
            }
        )
    return contents


def format_time(time: float) -> str:
    """Formats time like {days}d {hours}h {min}m {sec}s."""
    m, s = time // 60, time % 60
    h, m = m // 60, m % 60
    d, h = h // 24, h % 24
    timestr = f"{round(s, 1)}s"
    if time >= 60:
        timestr = f"{int(m)}m {int(s)}s"
    if time >= 3600:
        timestr = f"{int(h)}h " + timestr
    if time >= 86400:
        timestr = f"{int(d)}d " + timestr
    return timestr


class Config(object):
    """Singleton configuration object."""

    listen_addr: str
    listen_port: int
    autostart: bool
    log_level: str
    log_file_path: str
    work_dir: str
    file_browser_base_dir: str
    node_timeout: int
    render_nodes: List[str]
    macs: List[str]
    blenderpath_mac: str
    blenderpath_linux: str

    def __init__(self):
        raise RuntimeError("Config class cannot be instantiated")

    @classmethod
    def set_all(cls, attrs: Dict[str, Any]) -> None:
        """Sets attributes from a dictionary."""
        for key, val in attrs.items():
            setattr(cls, key, val)

    @classmethod
    def get(cls, attr: str, default: Any = None) -> Any:
        """Getter method that allows setting a default value."""
        if hasattr(cls, attr):
            return getattr(cls, attr)
        return default


class MultiCounter(object):
    """An object that can hold a collection of named counters, with associated convenience methods.

    If `strict` is set to True, then counters must be initialized by the set() or reset() methods
    before use.  If `strict` is False, then calling get(), inc(), or dec() on an unrecognized counter
    will cause that counter to be first initialized as zero before the requested operation is performed.
    """

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.counters = {}

    def _init_if_unknown(self, counter):
        if not self.strict and counter not in self.counters:
            self.counters[counter] = 0

    def set(self, counter: str, value: int) -> None:
        self.counters[counter] = value

    def get(self, counter: str) -> int:
        self._init_if_unknown(counter)
        return self.counters[counter]

    def inc(self, counter: str) -> None:
        self._init_if_unknown(counter)
        self.counters[counter] += 1

    def dec(self, counter: str) -> None:
        self._init_if_unknown(counter)
        self.counters[counter] -= 1

    def reset(self, counter: str) -> None:
        self.counters[counter] = 0

    def reset_all(self) -> None:
        for key in self.counters:
            self.counters[key] = 0


class MagicBool(object):
    """Mocks a boolean object, but changes value after it's been accessed a set number of accesses.

    Allows an infinite loop to be stopped after a set number of iterations for testing purposes."""

    def __init__(self, initial_value=False, max_count=1):
        self.initial = initial_value
        self.max_count = max_count
        self.call_count = 0

    def __bool__(self):
        self.call_count += 1  # Want to keep track of call count even after state flips.
        if self.call_count > self.max_count:
            return not self.initial
        return self.initial

    def reset(self):
        self.call_count = 0
