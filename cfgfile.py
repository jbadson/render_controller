#Creates & reads a config file
#Should work for any list or dict input 
#NOTE: all dict keys must be strings for json.dump and json.load

import json
import os.path

if __name__ == '__main__':
    print('This module contains methods to read and write simple JSON configuration'
           + ' files.')
    print('By default config files will be created in the same directory as this '
           + 'file.')
    print('Alternatively, a path (including filename) may be specified as an '
           + 'optional argument.')

#get current directory of this file, use this as default location for config files 
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
        '''Returns the current directory, filename, and path if no args are given.
        Otherwise changes the directory path and/or filename.'''
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
        '''Checks for a config file. Returns true if found.'''
        if os.path.exists(self.path):
            return True
        else:
            return False
    
    def write(self, cfgsettings):
        '''Writes a new config file from an array or dict object passed as param.'''
        cfgfile = open(self.path, 'w')
        cfgfile.write(json.dumps(cfgsettings, indent=1))
        cfgfile.close()
        return cfgsettings
    
    def read(self):
        '''Reads a config file and returns its contents as a list.'''
        cfgfile = open(self.path, 'r')
        cfgsettings = json.load(cfgfile)
        cfgfile.close()
        return cfgsettings
