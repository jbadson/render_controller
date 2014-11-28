'''Moves a given directory and its contents from the data server
to the ~/rendercache/ directory on a given computer.'''

import subprocess
import os.path
import platform
import time


'''---NOTES---
INPUTS NEEDED:
    path to blendfile -> needed for pathfix to run on
    path to project directory
    computer or list of computers

RETURNS
    new path to blendfile for renderscript to act on
'''



class FileCacher(object):
    '''Moves Blender project files to local storage on rendernodes to
    speed up rendering of large scenes and reduce server IO.'''

    def __init__(self, projectdir, blendpath, renderdir, computers=None):
        '''
        projectdir: Absolute path to the project's base directory. This 
            directory and its conents will be cached locally on each machine.
        blendpath: Relative path from projectdir to .blend file to be rendered.
        renderdir: Relative path from projectdir to directory where rendered 
            frames will be saved.
        computers: list of computers that will have files cached on them.  If
            no computers are specified, they will have to be provided when files
            are cached or retrieved.'''  
        self.projectdir = projectdir
        if self.projectdir[-1] == '/':
            #path.split will give an empty string if there's a trailing slash
            self.projectdir = self.projectdir[0:-1]
        self.basepath, self.dirname = os.path.split(self.projectdir)
        self.blendpath = blendpath #RELATIVE path
        self.renderdir = renderdir #RELATIVE path
        self.computers = computers #list of all computers data has been cached on

    def make_paths_relative(self):
        '''Launches blender with a python script to make all paths in the 
        file relative. Returns true if successful.

        IMPORTANT: The blender GUI MUST BE ABLE TO OPEN in order for this
        to work, i.e. this part of the script must either be run locally
        or via ssh with X11 forwarding.'''
        #assuming the pathfixer file is in the same directory as this file:
        pathfixer = os.path.join(os.path.dirname(os.path.realpath(__file__)), 
                                 'pathfix.py')
        #get the correct path to the blender executable based on operating system:
        if platform.system() == 'Darwin':
            blendexe = '/Applications/blender.app/Contents/MacOS/blender'
        elif platform.system() == 'Linux':
            blendexe = 'blender'
        else:
            raise OSError('Unable to match blender executable path to operating '
                          'system')
        #get the absolute path to the blend file
        blendpath = os.path.join(self.projectdir, self.blendpath)
        command = ('%s  %s --python %s' %(blendexe, blendpath, pathfixer))
        print('make_paths_relative() command:', command) #debug
        output = subprocess.check_output(command, shell=True)
        output = output.decode('UTF-8')
        #print(output, type(output))
        if output.find('Abort') >= 0:
            return output
        elif output.find('Cannot set relative paths') >= 0:
            return output
        else:
            return 0

    def get_render_path(self):
        '''Returns a relative path to the file to be rendered.'''
        renderpath = os.path.join('~/rendercache/', self.dirname, self.blendpath)
        return renderpath

    def cache_single(self, computer):
        '''Copies the project directory to the ~/rendercache directory
        on the specified computer.'''

        '''NOTE: The below command assumes the server is mounted on the target
        machine in the same location.  It would also be possible to use rsync
        or scp to copy directly from the machine this script is running on.'''
        if not computer in self.computers:
            self.computers.append(computer)
        #want to exclude any rendered frames with initial copy
        command = (
            'ssh igp@%s "rsync -au --exclude=%s --delete %s ~/rendercache/"' 
            %(computer, self.renderdir, self.projectdir)
            )
        print('cache() command:', command) #debug
        try:
            subprocess.call(command, shell=True)
        except Exception as e:
            #throws exception if a path is inaccessible or user lacks permissions
            return e
        return 0

    def cache_all(self, computers=None):
        '''Copies project directory to a list of computers.  If no list is given,
        it will use self.computers.  If self.computers is also null, an exception
        will be raised.  Returns 0 if successful, otherwise returns a list in the
        format computer:error.'''
        if not computers:
            computers = self.computers
        if not computers:
            raise RuntimeError('No computer list found')
        #remove any duplicate entries so we don't send commands twice
        computers = set(computers)
        errors = []
        for computer in computers:
            result = self.cache_single(computer)
            if result:
                errors.append('%s: %s' %(computer, result))
        if errors:
            return errors
        else:
            return 0

    def retrieve_frames(self, computer):
        '''Copies rendered frames from local ~/rendercache directory
        back to server.'''
        renderdir = os.path.join('~/rendercache/', self.dirname, self.renderdir)
        savedir = os.path.join(self.projectdir, self.renderdir)
        command = (
            'ssh igp@%s "rsync -au %s/ %s"' 
            %(computer, renderdir, savedir)
            )
        print('retrieve_frames() command:', command) #debug
        try:
            subprocess.call(command, shell=True)
        except Exception as e:
            return e
        return 0

    def retrieve_all(self, computers=None):
        '''Copies rendered frames from cache directories on a list of computers
        back to the server.  If no computer list is specified, will use 
        self.computers. Returns 0 on success or a list of errors on failure.'''
        if not computers:
            computers = self.computers
        if not computers:
            raise RuntimeError('No computer list found')
        #remove any duplicate entries so we don't send commands twice
        computers = set(computers)
        errors = []
        for computer in computers:
            result = self.retrieve_frames(computer)
            if result:
                errors.append('%s: %s' %(computer, result))
        if errors:
            return errors
        else:
            return 0

class Interactive(object):
    '''Interactive command line interface for FileCacher.'''
    def __init__(self, mode=None):
        '''mode: 'send' copies files to computers, 'retrieve' copies rendered
        frames back to the shared project render folder.  If no mode is
        is specified, user will be prompted.'''
        
        print('This utility will attempt to convert all paths in a given blend '
              'file\n to relative, then copy the contents of the project '
              'directory to\n the ~/rendercache/ directory on each specified '
              'computer or retrieve rendered frames from that location.\n')

        if not mode:
            reply = input('Mode (S to send, R to retrieve): ')
            if reply == 'S':
                mode = 'send'
            elif reply == 'R':
                mode = 'retrieve'
            else:
                print('Mode not recognized, quitting.')
    
        project_path = input('Absolute path to project root directory: ')
        blendfile = input('Relative path from project root to blend file: ')
        renderpath = input('Relative path from project root to rendered frames '
                           'directory: ')
        complist = input('Computers: ').split()
        print(
            '\nConfirm:'
            '\nProject directory: %s'
            '\nBlend file: %s'
            '\nRender directory: %s'
            '\nComputers: %s'
            %(project_path, blendfile, renderpath, complist)
            )
        if not input('Correct? (Y/n): '):
            print('Cancelled')
            return
        fc = FileCacher(project_path, blendfile, renderpath)
        if mode == 'send':
            if input('\nAttempt to fix paths in blend file? (Y/n): '):
                fc.make_paths_relative()
        for computer in complist:
            if mode == 'send':
                print('Copying files to %s' %computer)
                fc.cache_single(computer)
            else:
                print('Retrieving frames from %s' %computer)
                fc.retrieve_frames(computer)


if __name__ == '__main__':
    interface = Interactive()
