import logging
import yaml

from . import socketwrapper as sw

logger = logging.getLogger('rcontroller.util')

class Config(object):
    """Object to hold configuration data as parameters."""

    def __init__(self):
        self._dict = {}
        self._protected = set(dir(self))

    def _check(self, attrs):
        """Raises AttributeError if attrs contains a protected value."""
        check = self._protected.intersection(set(attrs))
        if len(check) > 0:
            raise AttributeError(
                'Cannot overload protected attribute(s): {}'.format(', '.join(check))
            )

    def dump(self):
        """Returns config values as dict."""
        return self._dict

    def set_from_dict(self, dictionary):
        """
        Sets attributes based on dictionary.

        Args:
        dictionary -- Dict to be converted to attrs
        """
        self._check(dictionary.keys())
        self._dict.update(dictionary)
        for key, val in dictionary.items():
            logger.info('Set config {}={}'.format(key, val))
            self.__setattr__(key, val)

    def set_from_file(self, path, required_fields=[]):
        """
        Loads config parameters from file.

        Args:
        path -- (str) Path to config file.
        required_fields -- (list) List of required parameter names.
        """
        with open(path, 'r') as f:
            cfg = yaml.load(f.read())
        if required_fields:
            diff = set(required_fields).difference(set(cfg.keys()))
            if len(diff) > 0:
                raise KeyError(
                    'Missing required config parameter(s): {}'.format(
                        ', '.join(diff))
                )
        self.set_from_dict(cfg)

    def set_from_server(self, host, port):
        """
        Retrieves and sets config info from render server.

        Args:
        host -- (str) Hostname or IP of render server.
        port -- (int) Server connection port.
        """
        socket = sw.ClientSocket(host, port)
        cfg = socket.send_cmd('get_config_vars')
        self.set_from_dict(cfg)
