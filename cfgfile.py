#Creates & reads a config file
#Should work for any list or dict input 

if __name__ == '__main__':
    print('This module contains methods to read and write simple JSON configuration files.')

#actions needed:
'''
check for existing config file:
    create if missing
    read if present

overwrite config file with defaults
    could just delete config file and force recreate on next load (wouldn't affect current situation)

create periodic backups?
    only really useful for computer list
'''

from json import dumps, load
from os import path



#Config file goes in the same directory as main
cfgpath = 'config.json'

def check():
    '''Checks for a config file. Returns true if found.'''
    if path.exists(cfgpath):
        return True
    else:
        return False

def write(cfgsettings):
    '''Writes a new config file from an array or dict object passed as param.'''

    cfgfile = open('config.json', 'w')
    cfgfile.write(dumps(cfgsettings, indent=1))
    cfgfile.close()
    return cfgsettings

def read():
    '''Reads a config file and returns its contents as a list.'''

    cfgfile = open('config.json', 'r')
    cfgsettings = load(cfgfile)
    cfgfile.close()
    #strings will be converted to unicode, but doesn't seem to matter
    return cfgsettings
