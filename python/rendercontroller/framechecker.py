#!/usr/bin/env python3
"""
Script to check a directory of sequentially-numbered files for missing items between a given start and end value.
"""


import os
import sys
import argparse


class Framechecker(object):

    # list of file extensions to accept by default, user can override by passing
    # an alternate list of extensions (including period) as an arg.
    default_exts = [".jpg", ".jpeg", ".png", ".exr"]

    def __init__(self, path, startframe, endframe, allowed_extensions=None):
        self.path = path
        self.startframe = startframe
        self.endframe = endframe
        self.allowed_extensions = allowed_extensions or self.default_exts
        # now try to get directory contents
        if not os.path.isdir(self.path):
            raise ValueError("Path must be a directory")
        self.dir_contents = os.listdir(self.path)
        # make sure there are some files we can parse
        for item in self.dir_contents:
            self.base, self.ext = os.path.splitext(item)
            if self.ext in self.allowed_extensions:
                filesok = True
                break
            else:
                filesok = False
        if not filesok:
            raise RuntimeError("No suitable files found in directory.")

    def calculate_indices(self, filename=None):
        """Attempts to determine the slice indices needed to isolate sequential
        file numbers within a typical filename. Assuming the sequential numbers go 
        to the end of the file base name, traverse the base name backwards looking 
        for the first non-numerical character. Assume the adjacent number is the 
        beginning of the sequential numbers. Returns a tuple with left and right
        indices as integers. Returns false if nothing was found.

        Optinal basename arg changes the value of self.base. Used to account for
        changes in filename length during iteration."""
        if filename:
            self.base, self.ext = os.path.splitext(filename)
        i = len(self.base) - 1
        while i >= 0:
            char = self.base[i]
            if not char.isdigit():
                left = i + 1
                right = len(self.base)
                return (left, right)
            i -= 1
        # loop finished with nothing found
        raise RuntimeError("Unable to parse filename:", self.base)

    def generate_lists(self):
        """Given left and right slice indices, returns lists of directory contents,
        frames expected, frames found and frames missing."""
        frames_expected = []
        frames_found = []
        frames_missing = []
        # generate list of expected frames
        for frame in range(self.startframe, self.endframe + 1):
            frames_expected.append(frame)
        # generate list of found frames, i.e. a list of sequential file numbers
        for item in self.dir_contents:
            # ignore hidden files
            if item[0] == ".":
                continue
            # ignore files that don't have allowed extensions
            if not os.path.splitext(item)[-1] in self.allowed_extensions:
                continue
            self.filename = item
            left, right = self.calculate_indices(filename=item)
            frame = int(item[left:right])
            frames_found.append(frame)
        # now compare to get list of missing frames
        for frame in frames_expected:
            if not frame in frames_found:
                frames_missing.append(frame)
        return (
            self.filename,
            self.dir_contents,
            frames_expected,
            frames_found,
            frames_missing,
        )


def main() -> int:
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("-s", "--start", help="Start value", type=int, required=True)
    parser.add_argument("-e", "--end", help="End value", type=int, required=True)
    parser.add_argument(
        "DIRECTORY", help="Directory containing sequentially-numbered files.", type=str
    )

    args = parser.parse_args()
    fc = Framechecker(args.DIRECTORY, args.start, args.end)
    fc.calculate_indices()
    name, dirconts, expected, found, missing = fc.generate_lists()
    if not missing:
        print("No missing frames found")
        return 0
    print(f"Possible missing frames: {str(missing)[1:-1]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
