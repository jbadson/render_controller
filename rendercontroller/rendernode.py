#client to manage processes on render nodes

#XXX Next step: line 80 - figure out regex for progress check

import threading
import subprocess
import time #XXX remove later
import socketwrapper as sw

allowed_commands = ['cmdtest', 'rendering', 'get_progress']


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
        # NOTE: for starters, allow only one render thread at a time
        self.renderthread = None
        self.blenderpath = 'blender' #XXX: should be sent by server when ready
        self.server = sw.Server(
            self, port=2030, allowed_commands=allowed_commands
            )
        self.server.start()
        #object to hold all render processes

    def cmdtest(self, args=None):
        print('cmdtest() called with args: %s' %args)
        return 'cmdtest() success'

    def rendering(self):
        '''Returns True if a renderthread exists.'''
        if self.renderthread:
            return True
        else:
            return False

    def get_progress(self):
        if not self.renderthread:
            return 0.0
        else:
            return self.renderthread.get_progress()

    def start_blender(self, path, frame):
        command = [self.blenderpath, '-b', path, '-f', frame]
        rt = RenderThread(self, command)
        self.renderthreads.append(rt)
        rt.start()


# XXX Simplified thread for now.  Add features as stuff is tested and
# as I figure out what's needed

class RenderThread(threading.Thread):
    '''Subclass of threading.Thread to handle render processes.'''
    def __init__(self, command):
        self.progress = 0.0
        threading.Thread.__init__(
            target=self._worker, args=(command)
            )

    def _worker(self, command): # Only for blender right now
        rprocess = subprocess.Popen(command, stdout=subprocess.PIPE)

        for line in iter(rprocess.stdout.readline, ''):
            if not line:
                # pipe broken, assume render failed
                print('Pipe broken')
                # XXX Need to handle failed frame here

            # NOTE: Timer handled by server

            # Calculate progress based on tiles
            elif line.find('Fra:' >= 0 and line.find('Title') > 0:
                self.progress = self._parseline(line, frame)
            # Detect if frame has finished rendering
            elif line.find('Saved:' >= 0 and line.find('Time') >= 0:
                # XXX Report finished frame to server
                break

    def _parseline(self, line, frame):
        '''Parses Blender cycles  progress and returns a float percent complete.'''
        #NOTE: Try to do this with regex instead?
        tiles, total = line.split('|')[-1].split(' ')[-1].split('/')
        tiles = float(tiles)
        total = float(total)
        percent = tiles / total * 100
        return percent            

    def get_progress(self):
        '''Returns progress as a float percent.'''
        return self.progress




if __name__ == '__main__':
    print('Starting render client')
    renderclient = RenderClient()

'''
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
'''
