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
    """
    Presents the output of os.scandir() as something JSON-serializable.
    """
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


def format_time(time):
    """Converts time in decimal seconds to human-friendly strings.
    format is ddhhmmss.s"""
    if time < 60:
        newtime = [round(time, 1)]
    elif time < 3600:
        m, s = time / 60, time % 60
        newtime = [int(m), round(s, 1)]
    elif time < 86400:
        m, s = time / 60, time % 60
        h, m = m / 60, m % 60
        newtime = [int(h), int(m), round(s, 1)]
    else:
        m, s = time / 60, time % 60
        h, m = m / 60, m % 60
        d, h = h / 24, h % 24
        newtime = [int(d), int(h), int(m), round(s, 1)]
    if len(newtime) == 1:
        timestr = str(newtime[0]) + "s"
    elif len(newtime) == 2:
        timestr = str(newtime[0]) + "m " + str(newtime[1]) + "s"
    elif len(newtime) == 3:
        timestr = (
            str(newtime[0]) + "h " + str(newtime[1]) + "m " + str(newtime[2]) + "s"
        )
    else:
        timestr = (
            str(newtime[0])
            + "d "
            + str(newtime[1])
            + "h "
            + str(newtime[2])
            + "m "
            + str(newtime[3])
            + "s"
        )
    return timestr


class Config(object):
    """Singleton configuration object."""

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
        if default:
            return default
        raise AttributeError(attr)
