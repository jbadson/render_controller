#client to manage processes on render nodes

import threading
import subprocess
import time #XXX remove later
import socketwrapper as sw

allowed_commands = ['cmdtest']


'''Info needed by server:
    pid *might not really need, server can just send kill cmd to client
    Some unique identifier for this job/frame
    Status (rendering / done) others?
    Percent complete
    Error messages
'''

class RenderClient(object):
    '''Handles requests from the render server and executes tasks on the
    local machine.'''

    def __init__(self):
        self.server = sw.Server(self, port=2030, 
                                allowed_commands=allowed_commands)
        self.server.start()
        #object to hold all render processes
        self.renderthreads = []

    def cmdtest(self, kwargs):
        print('cmdtest() called')
        for arg in kwargs:
            print('arg:', arg, kwargs[arg])
        return 'cmdtest() success'

    def start_blender(self, kwargs):
        command = [blenderpath, '-b', kwargs['path'], '-f', kwargs['frame']]
        rt = RenderThread(self, command)
        rt.start()




class RenderThread(threading.Thread):
    '''Subclass of threading.Thread to handle render processes.'''
    def __init__(self, command):
        '''Command is a list of args to be passed to the
        subprocess.Popen constructor.'''
        self.command = command
        self.started = False
        self.child = None #will become the child process
        self.output = None
        threading.Thread.__init__(self, target=self._worker)

    def _worker(self):
        self.child = subprocess.Popen(self.command, stdout=subprocess.PIPE)
        self.started = True
        for line in iter(self.child.stdout.readline, ''):
            if not line:
                print('RenderThread terminating')
                break
            else:
                self.output = line

    def kill(self):
        '''Kills the child process associated with this thread.'''
        self.child.kill()

    def getoutput(self):
        '''Returns the last line written to stdout by the child process.
        Will return an empty string when process terminates.'''
        return self.output

    def getpid(self):
        '''Returns the process id of the blender instance. Returns 0 if
        process has not yet started.'''
        if self.started:
            return self.child.pid
        else:
            return 0





if __name__ == '__main__':
    print('Starting render client')
    #renderclient = RenderClient()

    #XXX For now just testing the RenderThread
    command = [
        '/Applications/blender.app/Contents/MacOS/blender',
        '-b', '/mnt/data/test_render/test_render.blend', 
        '-s', '1', '-e', '5', '-a'
        ]
    t = RenderThread(command)
    t.start()
    while True:
        pid = t.getpid()
        if pid:
            break
    print('pid', pid)
    n = 0
    while n < 5:
        print(t.getoutput())
        time.sleep(1)
        n += 1
    t.kill()
    print('killed process')
