#!/usr/bin/env python3

import logging
import http.server
from http import HTTPStatus
import json
from json import JSONDecodeError
import os
import yaml
import socketserver
import urllib.parse
from typing import Sequence, Optional, Dict, List, Any, Callable, Type
from .controller import RenderController, Config
from .exceptions import JobNotFoundError, NodeNotFoundError

CONFIG_FILE_PATH = "/etc/rendercontroller.conf"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}

logger = logging.getLogger("server")


def get_file_type(entry: os.DirEntry) -> str:
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
            }
        )
    return contents


class ParsedPath(object):
    def __init__(self, parts: Sequence[str], query: Optional[str]) -> None:
        self.parts: Sequence[str] = parts
        self.query: Optional[str] = query
        self.endpoint = self.parts[0] if self.parts else None
        self.option = self.parts[1] if len(self.parts) > 1 else None
        self.target = self.parts[2] if len(self.parts) > 2 else None


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Overrides parent method to customize logging."""
        logger.exception(
            "TCP server caught exception while handling "
            + "request %s from %s" % (request, client_address[0])
        )


class HttpHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handles HTTP requests for a REST-type API.

    :param RenderController controller: Instance of RenderController
    :param str origin: CORS domain to allow with
        Access-Control-Allow-Origin header.
    :param str fileserver_base_dir: Base directory of the shared filesystem
        that contains render project files.
    :param set[str] get_endpoints: Set of allowed GET endpoints.
    :param set[str] post_endpoints: Set of allowed POST endpoints.
    :param dict[str, str] job_handlers: Mapping of job endpoint options
        to handler method names.
    :param dict[str, str] node_handlers: Mapping of node endpoint options
        to handler method names.
    :param dict[str, str] storage_handlers: Mapping of storage endpoint options
        to handler method names.
    :param dict[str, str] config_handlers: Mapping of config endpoint options
        to handler method names.
    """

    controller = None
    origin = "*"
    fileserver_base_dir = "/dev/null"
    get_endpoints = {"job", "node", "config"}
    post_endpoints = {"job", "node", "storage", "config"}
    job_handlers = {
        "summary": "job_summary",
        "status": "job_status",
        "start": "start_job",
        "stop": "stop_job",
        "enqueue": "enqueue_job",
        "delete": "delete_job",
        "new": "new_job",
    }
    node_handlers = {
        "list": "list_nodes",
        "enable": "enable_node",
        "disable": "disable_node",
    }
    storage_handlers = {"ls": "list_directory"}
    config_handlers = {"autostart": "configure_autostart"}

    def __init__(self, *args, **kwargs) -> None:
        self._parsed_path: Optional[ParsedPath] = None
        super().__init__(*args, **kwargs)

    @classmethod
    def configure(
        cls, controller: RenderController, origin: str, fileserver_base_dir: str
    ) -> None:
        cls.controller = controller
        cls.origin = origin
        cls.fileserver_base_dir = fileserver_base_dir

    def log_message(self, format: str, *args) -> None:
        """Override parent method to allow logging to file."""
        logger.debug("%s:%s" % (self.address_string(), format % args))

    def log_error(self, format: str, *args) -> None:
        """Override parent method to allow logging to file."""
        logger.error(format, *args)

    def send_error(
        self, code: int, message: Optional[str] = None, explain: Optional[str] = None
    ) -> None:
        """Override parent method to format error response as JSON."""
        try:
            shortmsg, longmsg = self.responses[code]
        except KeyError:
            shortmsg, longmsg = "???", "???"
        if message is None:
            message = shortmsg
        if explain is None:
            explain = longmsg
        ret = {"error_code": code, "message": message}
        if explain is not None:
            ret["explanation"] = explain
        self.log_error("code %d, message %s", code, message)
        self.send_response(code, message)
        self.send_header("Connection", "close")
        body = None
        if code >= 200 and code not in (
            HTTPStatus.NO_CONTENT,
            HTTPStatus.RESET_CONTENT,
            HTTPStatus.NOT_MODIFIED,
        ):
            body = bytes(json.dumps(ret), "UTF-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", int(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    @property
    def parsed_path(self) -> ParsedPath:
        """Parses path and sets related instance variables."""
        if not self._parsed_path:
            ppath = urllib.parse.urlparse(self.path)
            self._parsed_path = ParsedPath(
                ppath.path.strip("/").split("/"), ppath.query
            )
        return self._parsed_path

    def do_GET(self) -> None:
        """Handles HTTP GET requests."""
        logger.debug(
            "path parts: %s, query: '%s'"
            % (self.parsed_path.parts, self.parsed_path.query)
        )
        if self.parsed_path.endpoint in self.get_endpoints:
            getattr(self, self.parsed_path.endpoint)()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid endpoint")

    def do_POST(self) -> None:
        """Handles HTTP POST requests."""
        logger.debug(
            "path parts: %s, query: '%s'"
            % (self.parsed_path.parts, self.parsed_path.query)
        )
        if self.parsed_path.endpoint in self.post_endpoints:
            getattr(self, self.parsed_path.endpoint)()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid endpoint")

    def do_OPTIONS(self) -> None:
        """Provides CORS headers to OPTIONS requests."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", 0)
        self.send_header("Access-Control-Allow-Origin", self.origin)
        self.send_header("Access-Control-Allow-Credentials", True)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "origin, content-type, request"
        )
        self.end_headers()

    def send_all_headers(
        self,
        code: int = HTTPStatus.OK,
        content_type: str = "text/html",
        content_length: int = 0,
    ) -> None:
        """
        Sends a complete set of headers.

        :param int code: HTTP status code.
        :param str content_type: HTTP Content-Type header value.
        :param int content_length: Length of content in bytes.
        """
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", content_length)
        self.send_header("Access-Control-Allow-Origin", self.origin)
        self.send_header("Access-Control-Allow-Credentials", True)
        self.end_headers()

    def send_json(self, data: Any, code: int = HTTPStatus.OK) -> None:
        """
        Sends a response serialized as JSON

        :param data: Response data. Can be any JSON-serializable type.
        :param int code: HTTP response code.
        """
        bdata = bytes(json.dumps(data), "UTF-8")
        self.send_all_headers(code, "application/json; charset=UTF-8", len(bdata))
        self.wfile.write(bdata)

    def receive_json(self) -> Any:
        """Receives JSON from a request and returns an object."""
        msglen = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(msglen)
        if not data:
            return self.send_error(HTTPStatus.BAD_REQUEST, "No data")
        try:
            data = json.loads(data)
        except JSONDecodeError:
            return self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Failed to decode JSON"
            )
        logger.debug(data)
        return data

    def exec_handler(self, handlers: Dict[str, str]) -> None:
        """
        Validates path parts and executes a handler from a dict of handlers

        :param dict handlers: Map of options to their handler methods.
        """
        if not self.parsed_path.option:
            logger.warning("No option in '%s'" % self.parsed_path)
            return self.send_error(HTTPStatus.BAD_REQUEST, "Option not specified")
        try:
            func = getattr(self, handlers[self.parsed_path.option])
        except KeyError:
            logger.warning("Endpoint option not found in '%s'" % self.parsed_path)
            return self.send_error(HTTPStatus.NOT_FOUND, "Invalid endpoint option")
        return func()

    def job(self) -> None:
        """Handles requests for the `job` endpoint."""
        self.exec_handler(self.job_handlers)

    def job_summary(self) -> None:
        """Sends summary info about jobs in server."""
        self.send_json(self.controller.get_summary())

    def job_status(self) -> None:
        """Sends info about a render job."""
        if self.parsed_path.target:
            data = self.controller.get_job_status(self.parsed_path.target)
        else:
            data = self.controller.get_status()
        if not data:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        self.send_json(data)

    def start_job(self) -> None:
        """Starts a render job."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
        # FIXME Fails messily if job status is wrong
        try:
            self.controller.start(self.parsed_path.target)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        self.send_all_headers()

    def stop_job(self):
        """Stops a render job."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
        # For now, always kill all rendering frames immediately.
        # We can restore the old functionality if requested.
        try:
            self.controller.stop(self.parsed_path.target, True)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        self.send_all_headers()

    def enqueue_job(self):
        """Places a stopped job back in the render queue."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
        try:
            self.controller.enqueue(self.parsed_path.target)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        self.send_all_headers()

    def delete_job(self):
        """Deletes a render job."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
        try:
            self.controller.delete(self.parsed_path.target)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        self.send_all_headers()

    def new_job(self):
        """Creates a new render job and places it in queue."""
        data = self.receive_json()
        try:
            path = data["path"]
            start = int(data["start_frame"])
            end = int(data["end_frame"])
            engine = data["render_engine"]
            nodes = data["nodes"]
        except KeyError:
            logger.exception("New job request missing required data")
            return self.send_error(HTTPStatus.BAD_REQUEST, "Missing required data")
        try:
            job_id = self.controller.new_job(path, start, end, engine, nodes)
        except Exception as e:
            logger.exception("Error while creating job")
            error = str(e)
            # TODO: Be more specific
            return self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"Failed to create job",
                "Server caught {error}",
            )
        self.send_json({"job_id": job_id})

    def node(self) -> None:
        """Handles requests for the `node` endpoint."""
        self.exec_handler(self.node_handlers)

    def list_nodes(self) -> None:
        """Sends a list of configured render nodes."""
        self.send_json(self.controller.render_nodes)

    def enable_node(self) -> None:
        """Enables a node for rendering."""
        if not self.parsed_path.target:
            return self.send_error(HTTPStatus.BAD_REQUEST, "No node specified")
        try:
            job_id = self.parsed_path.parts[3]
        except IndexError:
            return self.send_error(HTTPStatus.BAD_REQUEST, "No job ID specified")
        try:
            self.controller.enable_node(job_id, self.parsed_path.target)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        except NodeNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Node not found")
        self.send_all_headers()

    def disable_node(self) -> None:
        """Disables a node for rendering."""
        if not self.parsed_path.target:
            self.send_error(HTTPStatus.BAD_REQUEST, "No node specified")
            return
        try:
            job_id = self.parsed_path.parts[3]
        except IndexError:
            self.send_error(HTTPStatus.BAD_REQUEST, "No job ID specified")
        try:
            self.controller.disable_node(job_id, self.parsed_path.target)
        except JobNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        except NodeNotFoundError:
            return self.send_error(HTTPStatus.NOT_FOUND, "Node not found")
        self.send_all_headers()

    def storage(self) -> None:
        """Handles requests for the `storage` endpoint."""
        self.exec_handler(self.storage_handlers)

    def list_directory(self) -> None:
        """
        Sends contents of a directory on the local (shared) filesystem.

        Requires path to be passed as a JSON object to avoid problems
        with non-URL-legal path elements.

        If the user-supplied path does not start with the base path
        as set in the config file, it will be appended to it.
        """
        data = self.receive_json()
        path = os.path.normpath(data.get("path", "") or "")
        logger.debug("normalized path: %s" % path)
        if path.startswith(".."):
            logger.warning("Request to browse illegal path: '%s'" % path)
            return self.send_error(HTTPStatus.BAD_REQUEST, "Invalid path")
        if not path.startswith(self.fileserver_base_dir):
            # Don't use os.path.join() because it replaces abs path root.
            path = os.path.normpath(self.fileserver_base_dir + "/" + path)
        logger.debug("absolute path: %s" % path)
        try:
            contents = list_dir(path)
        except:
            logger.exception("Caught exception while browsing filesystem")
            return self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Filesystem error")
        self.send_json({"current": path, "contents": contents})

    def config(self) -> None:
        """Handles requests for the `config` endpoint."""
        self.exec_handler(self.config_handlers)

    def configure_autostart(self) -> None:
        """Gets or sets the autostart mode."""
        if not self.parsed_path.target:
            # Send current state
            self.send_json({"autostart": self.controller.autostart})
            return
        if self.parsed_path.target == "enable":
            self.controller.enable_autostart()
        elif self.parsed_path.target == "disable":
            self.controller.disable_autostart()
        else:
            logger.error("Invalid autostart target '%s'" % self.parsed_path.target)
            return self.send_error(HTTPStatus.NOT_FOUND, "Invalid target")
        self.send_all_headers()


def main(config_path: str) -> int:
    try:
        with open(CONFIG_FILE_PATH) as f:
            conf = yaml.load(f.read())
    except:
        logging.exception(f"Unable to read config file at {config_path}")
        return 1
    Config.set_all(conf)
    console = logging.StreamHandler()
    try:
        logfile = logging.FileHandler(Config.log_file_path)
        logging.basicConfig(
            level=LOG_LEVELS[Config.log_level],
            format=LOG_FORMAT,
            datefmt=LOG_DATE_FORMAT,
            handlers=[console, logfile],
        )
    except PermissionError:
        logging.exception(
            f"Insufficient permissions to write to log file at {Config.log_file_path}"
        )
        return 1

    controller = RenderController(Config)
    HttpHandler.configure(controller, Config.cors_origin, Config.fileserver_base_dir)
    server = TCPServer((Config.listen_addr, Config.listen_port), HttpHandler)
    logger.info(f"Listening on {Config.listen_addr}:{Config.listen_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # TODO also need to catch sigterm and shut down cleanly
        controller.shutdown()
    except:
        logging.exception("Uncaught exception. Server shutting down.")
        return 1
    return 0
