#!/usr/bin/env python3

import argparse
import sys
from . import server, controller, job

def main() -> int:
    parser = argparse.ArgumentParser(
        "A multi-engine network rendering utility.")
    parser.add_argument("-c", "--config-file",
        help=f"Path to config file. Default: {server.CONFIG_FILE_PATH}")
    args = parser.parse_args()
    return(server.main(args.config_file))

if __name__ == '__main__':
    sys.exit(main())
