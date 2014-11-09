#Rewrite of checkframes.py for Python 3.4 and to be less idiotic

'''
#####################################################################
Copyright 2014 James Adson

This file is part of IGP Render Controller.  
IGP Render Controller is free software: you can redistribute it 
and/or modify it under the terms of the GNU General Public License 
as published by the Free Software Foundation, either version 3 of 
the License, or any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
#####################################################################
'''


'''This module contains methods to check a directory of rendered frames for any 
missing items between a specified start and end range.'''

import os

class Framechecker(object):
    '''Master object for this module. This must be instantiated with a valid path
    and integer start and end frames before any other method in this module
    can be used.'''
    #list of file extensions to accept by default, user can override by passing
    #an alternate list of extensions (including period) as an arg.
    default_exts = ['.jpg', '.jpeg', '.png', '.exr']

    def __init__(self, path, startframe, endframe, 
                 allowed_extensions=default_exts):
        self.path = path
        self.startframe = startframe
        self.endframe = endframe
        self.allowed_extensions = allowed_extensions
        #now try to get directory contents
        if not os.path.isdir(self.path):
            raise ValueError('Path must be a directory')
        self.dir_contents = os.listdir(self.path)
        #make sure there are some files we can parse
        for item in self.dir_contents:
            self.base, self.ext = os.path.splitext(item)
            if self.ext in self.allowed_extensions:
                filesok = True
                break
            else:
                filesok = False
        if not filesok:
            raise RuntimeError('No suitable files found in directory.')

    def calculate_indices(self, filename=None):
        '''Attempts to determine the slice indices needed to isolate sequential
        file numbers within a typical filename. Assuming the sequential numbers go 
        to the end of the file base name, traverse the base name backwards looking 
        for the first non-numerical character. Assume the adjacent number is the 
        beginning of the sequential numbers. Returns a tuple with left and right
        indices as integers. Returns false if nothing was found.

        Optinal basename arg changes the value of self.base. Used to account for
        changes in filename length during iteration.'''
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
        #loop finished with nothing found
        raise RuntimeError('Unable to parse filename:', self.base)

    #def generate_lists(self, left, right):
    def generate_lists(self):
        '''Given left and right slice indices, returns lists of directory contents,
        frames expected, frames found and frames missing.'''
        frames_expected = []
        frames_found = []
        frames_missing = []
        #generate list of expected frames
        for frame in range(self.startframe, self.endframe + 1):
            frames_expected.append(frame)
        #generate list of found frames, i.e. a list of sequential file numbers
        for item in self.dir_contents:
            #ignore hidden files
            if item[0] == '.':
                continue
            #ignore files that don't have allowed extensions
            if not os.path.splitext(item)[-1] in self.allowed_extensions:
                continue
            self.filename = item
            left, right = self.calculate_indices(filename=item)
            frame = int(item[left:right])
            frames_found.append(frame)
        #now compare to get list of missing frames
        for frame in frames_expected:
            if not frame in frames_found:
                frames_missing.append(frame)
        return (self.filename, self.dir_contents, frames_expected, frames_found, 
                frames_missing)


if __name__ == '__main__':
    #XXX Need to put GUI elements from gui.py back in here so it can be run as standalone application
    print('you need to put the GUI or command line interface back in here derp')
