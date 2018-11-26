#!/usr/bin/env python3

import logging
import http.server
from http import HTTPStatus
import json
from json import JSONDecodeError
import yaml
import socketserver
import urllib.parse
from typing import Sequence, Optional
from .controller import RenderController, Config

CONFIG_FILE_PATH = "/etc/rendercontroller.conf"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}

logger = logging.getLogger("server")


class ParsedPath(object):
    def __init__(self, parts: Sequence[str], query: Optional[str]) -> None:
        self.parts: Sequence[str] = parts
        self.query: Optional[str] = query
        self.endpoint = self.parts[0] if self.parts else ""


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Overrides parent method to customize logging."""
        logger.exception(
            "TCP server caught exception while handling"
            + "request %s from %s" % (request, client_address[0])
        )


class HttpHandler(http.server.SimpleHTTPRequestHandler):
    """
    Handles HTTP requests for a REST-type API.

    By convention, GET requests may not change the state of the server.
    POST requests may.

    :param set[str] endpoints: Set of API endpoints this class handles.
    :param str origin: CORS domain to allow with
                       Access-Control-Allow-Origin header.
    :param RenderController controller: Instance of RenderController
    """

    get_endpoints = {"status", "job"}
    post_endpoints = {"enqueue", "start", "stop", "delete", "autostart"}

    def __init__(self, *args, **kwargs):
        self._parsed_path = None
        super().__init__(*args, **kwargs)

    @classmethod
    def configure(cls, controller, origin):
        cls.controller = controller
        cls.origin = origin

    def log_message(self, format, *args):
        """Override to allow logging to file."""
        logger.debug("%s:%s" % (self.address_string(), format % args))

    def log_error(self, format, *args):
        """Override to allow logging to file."""
        logger.error(format, *args)

    def parse_path(self):
        """Parses path and sets related instance variables."""
        if not self._parsed_path:
            ppath = urllib.parse.urlparse(self.path)
            self._parsed_path = ParsedPath(
                ppath.path.strip("/").split("/"), ppath.query
            )
        return self._parsed_path

    def do_GET(self):
        """Handles HTTP GET requests."""
        path = self.parse_path()
        logger.debug("path parts: %s, query: '%s'" % (path.parts, path.query))
        if path.endpoint in self.get_endpoints:
            getattr(self, path.endpoint)()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid endpoint")

    def do_POST(self):
        """Handles HTTP POST requests."""
        path = self.parse_path()
        logger.debug("path parts: %s, query: '%s'" % (path.parts, path.query))
        if path.endpoint in self.post_endpoints:
            getattr(self, path.endpoint)()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Invalid endpoint")

    def send_json(self, data, code=HTTPStatus.OK):
        """
        Sends a response serialized as JSON

        :param data: Response data. Can be any JSON-serializable type.
        :param int code: HTTP response code.
        """
        bdata = bytes(json.dumps(data), "UTF-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("Content-Length", len(bdata))
        self.send_header("Access-Control-Allow-Origin", self.origin)
        self.end_headers()
        self.wfile.write(bdata)

    def status(self):
        """Returns list of all jobs and with basic summary data."""
        # self.send_json(summary_data)
        self.send_json(self.controller.get_status())

    def job(self):
        """Returns full info for a job"""
        try:
            job_id = self.parse_path().parts[1]
        except IndexError:
            return self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not specified")
        job_data = self.controller.get_job_status(job_id)
        if not job_data:
            return self.send_error(HTTPStatus.BAD_REQUEST, "Job ID not found")
        self.send_json(job_data)

    def enqueue(self):
        """Creates a new render job and places it in queue."""
        msglen = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(msglen)
        if not data:
            return self.send_error(HTTPStatus.BAD_REQUEST, "No data")
        try:
            data = json.loads(data)
        except JSONDecodeError:
            return self.send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR, "Unable to decode data"
            )
        logger.debug(data)
        # New server enqueue func should do:
        #   1. Validate required fields
        #   2. Create job
        #   3. Place in queue
        #   4. Return nullable job ID and error
        path = data.get("path", None)
        start = data.get("start", None)
        end = data.get("end", None)
        engine = data.get("engine", None)
        nodes = data.get("nodes", None)
        extras = data.get("extraframes", None)
        job_id, error = None
        try:
            job_id = self.controller.new_job(path, start, end, engine, nodes, extras)
        except Exception as e:
            logger.exception("Error while creating job")
            error = str(e)
        self.send_json({"job_id": job_id, "error": error})

    def start(self):
        """Starts a render job."""
        # Just return 200 if OK
        pass

    def stop(self):
        """Stops a render job."""
        # Just return 200 if OK
        pass

    def resume(self):
        """Resumes a stopped render."""
        # TODO Might be better to do this with start (if called on stopped job)
        pass

    def killproc(self):
        """Kills a render process on a node."""
        # TODO Decide if this is even necessary. This isn't a process control tool.
        pass

    def delete(self):
        """Deletes a render job."""
        pass

    def autostart(self):
        """Toggles state of server autostart mode."""
        pass


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
    HttpHandler.configure(controller, Config.cors_origin)
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
