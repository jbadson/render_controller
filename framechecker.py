#Rewrite of checkframes.py for Python 3.4 and to be less idiotic
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

    def __init__(self, path, startframe, endframe, allowed_extensions=default_exts):
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
            else:
                filesok = False
        if not filesok:
            raise RuntimeError('No suitable files found in directory.')

    def calculate_indices(self):
        '''Attempts to determine the slice indices needed to isolate sequential
        file numbers within a typical filename. Assuming the sequential numbers go 
        to the end of the file base name, traverse the base name backwards looking 
        for the first non-numerical character. Assume the adjacent number is the 
        beginning of the sequential numbers. Returns a tuple with left and right
        indices as integers. Returns false if nothing was found.'''
        i = len(self.base) - 1
        while i >= 0:
            char = self.base[i]
            if not char.isdigit():
                self.left = i + 1
                self.right = len(self.base)
                print(self.left, self.right)#debug
                return (self.left, self.right)
            i -= 1
        #loop finished with nothing found
        return False

    def generate_lists(self, left, right):
        '''Given left and right slice indices, returns lists of directory contents,
        frames expected, frames found and frames missing.'''
        self.left = left
        self.right = right
        frames_expected = []
        frames_found = []
        frames_missing = []
        #generate list of expected frames
        for frame in range(self.startframe, self.endframe + 1):
            frames_expected.append(frame)
        #generate list of found frames, i.e. a list of sequential file numbers
        #found by parsing dir_contents according to provided indices
        for item in self.dir_contents:
            #ignore files that don't have allowed extensions
            if os.path.splitext(item)[-1] in self.allowed_extensions:
                self.filename = item
                frame = int(item[self.left:self.right])
                frames_found.append(frame)
        #now compare to get list of missing frames
        for frame in frames_expected:
            if not frame in frames_found:
                frames_missing.append(frame)
        return(self.filename, self.dir_contents, frames_expected, frames_found, 
                frames_missing)


if __name__ == '__main__':
    #XXX Need to put GUI elements from gui.py back in here so it can be run as standalone application
    print('you need to put the GUI or command line interface back in here derp')
