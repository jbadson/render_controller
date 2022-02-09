from typing import Dict, Any


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
