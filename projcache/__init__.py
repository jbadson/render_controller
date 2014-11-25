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

    def __init__(self, projectdir, blendpath, renderdir):
        '''Args:
        projectdir = Absolute path to the project's base directory. This 
            directory and its conents will be cached locally on each machine.
        blendpath = Relative path from projectdir to .blend file to be rendered.
        renderdir = Relative path from projectdir to directory where rendered 
            frames will be saved.
        paths_relative: Optional. Change to True if blend file's paths have
            already been converted to relative. Otherwise prevents cache()
            from being executed until make_paths_relative() successfully
            finishes.'''  
        self.projectdir = projectdir
        if self.projectdir[-1] == '/':
            #path.split will give an empty string if there's a trailing slash
            self.projectdir = self.projectdir[0:-1]
        self.basepath, self.dirname = os.path.split(self.projectdir)
        self.blendpath = blendpath #RELATIVE path
        self.renderdir = renderdir #RELATIVE path

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

    def cache(self, computer):
        '''Copies the project directory to the ~/rendercache directory
        on the specified computer.'''

        '''NOTE: The below command assumes the server is mounted on the target
        machine in the same location.  It would also be possible to use rsync
        or scp to copy directly from the machine this script is running on.'''

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

class Interactive(object):
    '''Interactive command line interface for FileCacher.'''
    def __init__(self, mode):
        '''mode: 'send' copies files to computers, 'retrieve' copies rendered
        frames back to the shared project render folder'''
        
        print('This utility will attempt to convert all paths in a given blend '
              'file\n to relative, then copy the contents of the project '
              'directory to\n the ~/rendercache/ directory on each specified '
              'computer.\n')
    
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
                fc.cache(computer)
            else:
                print('Retrieving frames from %s' %computer)
                fc.retrieve_frames(computer)


if __name__ == '__main__':
    projpath = '/mnt/data/test_render/cachetest'
    blendfile = 'cachetest.blend'
    renderpath = 'render'
    fc = FileCacher(projpath, blendfile, renderpath)
    #fc.make_paths_relative()
    #fc.cache('sneffels')
    fc.retrieve_frames('sneffels')
