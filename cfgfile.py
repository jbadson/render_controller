#Creates & reads a config file
#Should work for any list or dict input 

#from json import dumps, load
#from os import path

import json
import os

if __name__ == '__main__':
    print('This module contains methods to read and write simple JSON configuration'
            + ' files.')
    print('By default config files will be created in the same directory as this file.')
    print('Alternatively, a path may be specified as an optional argument.')

#get current directory of this file, use this as default location for config files 
default_path = os.path.dirname(os.path.realpath(__file__)) + '/config.json'

def check(path=default_path):
    '''Checks for a config file. Returns true if found.'''
    if os.path.exists(path):
        return True
    else:
        return False

def write(cfgsettings, path=default_path):
    '''Writes a new config file from an array or dict object passed as param.'''

    cfgfile = open(path, 'w')
    cfgfile.write(json.dumps(cfgsettings, indent=1))
    cfgfile.close()
    return cfgsettings

def read(path=default_path):
    '''Reads a config file and returns its contents as a list.'''

    cfgfile = open(path, 'r')
    cfgsettings = json.load(cfgfile)
    cfgfile.close()
    #strings will be converted to unicode, but doesn't seem to matter
    return cfgsettings
