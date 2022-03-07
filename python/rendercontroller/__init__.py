import argparse
import sys
from . import server, controller, job, framechecker

__version__ = "2.0.0"


def main() -> int:
    parser = argparse.ArgumentParser("A multi-engine network rendering utility.")
    parser.add_argument(
        "-c",
        "--config-file",
        help=f"Path to config file. Default: {server.CONFIG_FILE_PATH}",
        default=server.CONFIG_FILE_PATH,
    )
    parser.add_argument(
        "-v", "--version", help="Print server version and exit.", action="store_true"
    )
    args = parser.parse_args()
    if args.version:
        print(__version__)
        return 0
    return server.main(args.config_file)


if __name__ == "__main__":
    sys.exit(main())
