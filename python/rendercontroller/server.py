import logging
import http.server
from http import HTTPStatus
import json
from json import JSONDecodeError
import os
import yaml
import signal
import selectors
import socketserver
import urllib.parse
from typing import Sequence, Optional, Dict, List, Any, Union
from rendercontroller.controller import RenderController
from rendercontroller.exceptions import JobNotFoundError, NodeNotFoundError
from rendercontroller.util import Config, list_dir
from rendercontroller.constants import LOG_EVERYTHING

CONFIG_FILE_PATH = "/etc/rendercontroller.conf"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "everything": LOG_EVERYTHING,
}

logging.addLevelName(LOG_EVERYTHING, "EVERYTHING")
logger = logging.getLogger("server")


class ParsedPath(object):
    def __init__(self, parts: Sequence[str], query: Optional[str]) -> None:
        self.parts: Sequence[str] = parts
        self.query: Optional[str] = query
        self.endpoint = self.parts[0] if self.parts else None
        self.option = self.parts[1] if len(self.parts) > 1 else None
        self.target = self.parts[2] if len(self.parts) > 2 else None


class ShutdownableTCPServer(socketserver.TCPServer):
    """
    socketserver.BaseServer uses an arcane loop termination process in serve_forever that is prone to deadlocking.
    It has been discussed in many issues (#13749, #12463, #2302, etc.) over more than a decade, but there seems to
    be no consensus as to whether the problem even really exists, much less a solution.  Since it has become a problem
    for me, and I have not found a better way to solve it, I am overriding it with a simpler mechanism that seems to
    work for my purposes.  I make no guarantees about the reasonableness or pythonic purity of this solution.
    """

    def __init__(self, *args, **kwargs):
        self._stop = False
        super().__init__(*args, **kwargs)

    def shutdown(self):
        """Overrides parent method with simpler shutdown flag."""
        self._stop = True

    def serve_forever(self, poll_interval=0.5):
        """Essentially the same as the parent method but without multi-step shutdown dunder stuff."""
        with selectors.PollSelector() as selector:
            selector.register(self, selectors.EVENT_READ)

            while not self._stop:
                ready = selector.select(poll_interval)
                # bpo-35017: shutdown() called during select(), exit immediately.
                if self._stop:
                    break
                if ready:
                    self._handle_request_noblock()
                self.service_actions()
        logger.debug("serve_forever() exited")


class TCPServer(ShutdownableTCPServer):
    allow_reuse_address = True

    def __init__(self, controller: RenderController, *args, **kwargs):
        self.controller = controller
        super().__init__(*args, **kwargs)
        signal.signal(signal.SIGTERM, self._signal_handler())

    def handle_error(self, request, client_address):
        """Overrides parent method to customize logging."""
        logger.exception(
            "TCP server caught exception while handling "
            + "request %s from %s" % (request, client_address[0])
        )

    def _signal_handler(self):
        """Closure to give handler function instance context."""

        def handler(signum, frame):
            """
            signum -- Signal number.
            frame -- Stack frame (not used, but is required by interface).
            """
            logger.debug(f"Caught signal {signum}")
            if signum == 15:
                self.stop()

        return handler

    def stop(self):
        logger.info("Shutting down")
        self.controller.shutdown()
        logger.debug("Attempting to stop TCP server")
        # super().shutdown()
        self.server_close()
        self.shutdown()


class HttpHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handles HTTP requests for a REST-type API.

    :param RenderController controller: Instance of RenderController
    :param str origin: CORS domain to allow with
        Access-Control-Allow-Origin header.
    :param str file_browser_base_dir: Base directory of the shared filesystem
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

    controller: RenderController
    origin: str
    file_browser_base_dir: str
    get_endpoints = {"job", "node", "config"}
    post_endpoints = {"job", "node", "storage", "config"}
    job_handlers = {
        "new": "new_job",
        "info": "job_data",
        "start": "start_job",
        "stop": "stop_job",
        "delete": "delete_job",
        "reset_status": "reset_job_status",
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
        if self.controller is None:
            raise AttributeError("Class attribute controller not configured")
        super().__init__(*args, **kwargs)

    @classmethod
    def configure(
        cls, controller: RenderController, file_browser_base_dir: str
    ) -> None:
        cls.controller = controller
        cls.origin = "*"  # API has no access control, so limiting this adds no value.
        cls.file_browser_base_dir = file_browser_base_dir

    def log_message(self, format: str, *args) -> None:
        """Override parent method to allow logging to file."""
        if not args[0].startswith("GET /job/info"):
            # Avoid spamming console with thousands of WebUI update requests
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
            self.send_header("Content-Length", str(len(body)))
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
        if not self.path.startswith("/job/info"):
            # Avoid spamming console with thousands of WebUI update requests
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
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Allow-Origin", self.origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
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
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", self.origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
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

    def job_data(self) -> None:
        """Sends info about a render job."""
        data: Union[Dict[str, Any], List[Dict[str, Any]]]
        if self.parsed_path.target:
            # Send data for specified job
            data = self.controller.get_job_data(self.parsed_path.target)
            if not data:
                return self.send_error(HTTPStatus.NOT_FOUND, "Job ID not found")
        else:
            # No job ID specified, so send data about *all* jobs
            data = self.controller.get_all_job_data()
        self.send_json(data)

    def start_job(self) -> None:
        """Starts a render job."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
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
        try:
            self.controller.stop(self.parsed_path.target)
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

    def reset_job_status(self):
        """For a stopped job, resets status to waiting so it can be started by autostart."""
        if not self.parsed_path.target:
            logger.warning("Job ID not specified in '%s'" % self.parsed_path)
            self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
            return
        try:
            self.controller.reset_waiting(self.parsed_path.target)
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
            nodes = data["nodes"]
        except KeyError:
            logger.exception("New job request missing required data")
            return self.send_error(HTTPStatus.BAD_REQUEST, "Missing required data")
        try:
            job_id = self.controller.new_job(path, start, end, nodes)
        except Exception as e:
            logger.exception("Error while creating job")
            error = str(e)
            return self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "Failed to create job",
                f"Server caught {error}",
            )
        self.send_json({"job_id": job_id})

    def node(self) -> None:
        """Handles requests for the `node` endpoint."""
        self.exec_handler(self.node_handlers)

    def list_nodes(self) -> None:
        """Sends a list of configured render nodes."""
        self.send_json(self.controller.render_nodes)

    def enable_node(self) -> None:
        """Enables a node for rendering on a particular job."""
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
        """Disables a node for rendering on a particular job."""
        if not self.parsed_path.target:
            self.send_error(HTTPStatus.BAD_REQUEST, "No node specified")
            return
        try:
            job_id = self.parsed_path.parts[3]
        except IndexError:
            return self.send_error(HTTPStatus.BAD_REQUEST, "No job ID specified")
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
        if not path.startswith(self.file_browser_base_dir):
            # Don't use os.path.join() because it replaces abs path root.
            path = os.path.normpath(self.file_browser_base_dir + "/" + path)
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
        with open(config_path) as f:
            conf = yaml.safe_load(f.read())
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
    HttpHandler.configure(controller, Config.file_browser_base_dir)
    server = TCPServer(
        controller=controller,
        server_address=(Config.listen_addr, Config.listen_port),
        RequestHandlerClass=HttpHandler,
    )
    logger.info(f"Listening on {Config.listen_addr}:{Config.listen_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    except:
        logging.exception("Server exited with unhandled exception.")
        return 1
    logger.debug("Server exited normally")
    return 0
