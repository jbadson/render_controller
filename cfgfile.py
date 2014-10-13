'''This module contains methods for creating, reading, and manipulating
simple configuration files in JSON format.

Any of the basic data types (strings, numbers, lists, tuples, dictionaries) 
can be used with one caveat - dictionary keys must be strings.  If a dict 
with non-string keys is supplied, json.dumps will automatically convert the 
keys to strings, which will not be converted back to the original type when 
the file is read.

Note: Files are not edited in place.  After the initial file is created,
each subsequent call of the write() method overwrites the existing file.
Also note that nothing is actually written to the disk until the write() 
method is called.

#####################################################################
Copyright 2014 James Adson
    
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
#####################################################################
'''

import json
import os.path
from os import remove as os_remove


#Use this file's current directory as the default location to save new files 
default_dirpath = os.path.dirname(os.path.realpath(__file__))
default_filename = 'config.json'

class ConfigFile(object):
    def __init__(self, dirpath=default_dirpath, filename=default_filename):
        self.dirpath = dirpath
        if not os.path.exists(dirpath):
            raise ValueError('Path does not exist')
        else:
            self.dirpath = dirpath
        self.filename = filename
        self.path = os.path.join(self.dirpath, self.filename)

    def filepath(self, dirpath=None, filename=None):
        '''If no args are supplied, returns teh current directory, path, and
        filename. If one or more arguments are supplied, changes the values
        to the ones supplied.'''
        if dirpath:
            if not os.path.exists(dirpath):
                raise ValueError('Path does not exist')
            else:
                self.dirpath = dirpath
        if filename:
            self.filename = filename
        if dirpath or filename:
            self.path = os.path.join(self.dirpath, self.filename)
        return (self.dirpath, self.filename, self.path)

    def exists(self):
        '''Returns true if a file exists at the location specified by the
        path attribute.'''
        if os.path.exists(self.path):
            return True
        else:
            return False
    
    def write(self, data):
        '''Accepts data in any basic type (string, number, list, tuple, dict) as
        an argument, formats it as JSON, and writes it to the disk at the
        specified path.'''
        with open(self.path, 'w') as cfgfile:
            cfgfile.write(json.dumps(data, indent=1))
        return data
    
    def read(self):
        '''Reads a config file and returns its contents in the same data type
        as the original.'''
        with open(self.path, 'r') as cfgfile:
            data = json.load(cfgfile)
        return data

    def delete(self):
        '''Deletes the config file.'''
        if not self.exists():
            raise RuntimeError('Config file does not exist.')
        else:
            os_remove(self.path)



if __name__ == '__main__':
    print('This module contains methods to read and write simple JSON configuration'
           + ' files.')
    print('By default config files will be created in the same directory as this '
           + 'file.')
    print('Alternatively, a path (including filename) may be specified as an '
           + 'optional argument.')

