#Fifth major revison of IGP render controller
#must run in python 3
import queue
import threading
import time
import cfgfile
import subprocess
import os
import socket
import ast

class Job(object):
    '''Represents a render job.'''

    def __init__(self):
        #initialize all attrs for client updates
        self.status = 'Empty'
        self.starttime = None #time render() called
        self.stoptime = None #time masterthread stopped
        self.complist = []
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in computers:
            self.compstatus[computer] = self._reset_compstatus(computer)
        self.path = None
        self.startframe = None
        self.endframe = None
        self.extraframes = []
        self.render_engine = None
        self.totalframes = []
        self.progress = None


    def _reset_compstatus(self, computer):
        '''Returns a compstatus dict containing default values'''
        if computer in self.complist:
            pool = True
        else:
            pool = False
        return { 'active':False, 'frame':None, 'pid':None, 'timer':None, 
                 'progress':0.0, 'error':None, 'pool':pool}
    

    def exists(self):
        '''Returns true if specified job exists.'''
        if self.path:
            return True
        else:
            return False


    def get_job_status(self):
        '''Retuns the status of a job.'''
        return self.status


    def get_job_progress(self):
        '''Returns the percent complete for the job.'''
        if self.status == 'Rendering' or self.status == 'Stopped':
            n = 0
            for i in self.totalframes:
                if i != 0:
                    n += 1
            self.progress = float(n) / len(self.totalframes) * 100
        elif self.status == 'Finished':
            self.progress = 100.0
        else:
            self.progress = 0.0
        return self.progress


    def get_comp_status(self, computer):
        '''Returns the contents of self.compstatus for a given computer.'''
        return self.compstatus[computer]


    def enqueue(self, path, startframe, endframe, render_engine, complist, 
                extraframes=[]):
        '''Create a new job and place it in queue.'''
        self.path = path
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes
        self.render_engine = render_engine
        self.complist = complist
        for computer in self.complist:
            self.compstatus[computer]['pool'] = True

        print('enqueued')
        #Fill list of total frames with zeros
        #used for tracking percent complete
        self.totalframes = []
        for i in range(self.startframe, self.endframe + len(self.extraframes) + 1):
            self.totalframes.append(0)

        #create LifoQueue and put frames
        self.queue = queue.LifoQueue(0)
        framelist = list(range(self.startframe, self.endframe + 1))
        framelist.reverse()
        for frame in framelist:
            self.queue.put(frame)

        #check for duplicates in start-end range
        if len(self.extraframes) > 0:
            for frame in self.extraframes:
                if frame in framelist:
                    self.extraframes.remove(i)
        #render extraframes first, lowest number first
        #check again to make sure there are still extraframes
        if len(self.extraframes) > 0:
            self.extraframes.sort().reverse()
            for frame in self.extraframes:
                self.queue.put(frame)

        self.status = 'Waiting'
        return True


    def render(self):
        '''Starts a render for a given job.'''
        print('entered render()') #debug
        if self.status != 'Waiting':
            print('Job status is not "Waiting". Aborting render.')
            return 'Job status is not "Waiting". Aborting render.'
        self.status = 'Rendering'
        self.starttime = self._start_timer()
        #create log entry

        self.skiplist = []
        self.killflag = False

        master = threading.Thread(target=self._masterthread, args=())
        master.start()
        return 'success'


    def _masterthread(self):
        '''Main thread to control render process and create renderthreads.'''


        '''{ 'active':False, 'frame':None,
            'pid':None, 'timer':None, 'progress':0.0, 'error':None }'''
    
        print('started _masterthread()') #debug
        self.threads_active = False
    
        while True:
            if self.killflag == True:
                print('Kill flag detected, breaking render loop.')
                #deal with log & render timer
                break
    
            if self.queue.empty() and not self._threadsactive():
                print('Render done at detector.') #debug
                self.status = 'Finished'
                self.stoptime = time.time()
                #write status to log
                break
    
            for computer in computers:
                time.sleep(0.01)
                if self.compstatus[computer]['pool'] == False:
                    continue
                if not self.compstatus[computer]['active'] == True and \
                not computer in self.skiplist:
                    #break loop if queue becomes empty after new computer is added
                    if self.queue.empty():
                        break
                    else:
                        frame = self.queue.get()
                        with threadlock:
                            self.compstatus[computer]['active'] = True
                            self.compstatus[computer]['frame'] = frame
                            self.compstatus[computer]['timer'] = time.time()
                            self.threads_active = True
                        print('creating renderthread') #debug
                        rthread = threading.Thread(target=self._renderthread,
                                    args=(frame, computer, self.queue))
                        rthread.start()
    
                #ignore computers in skiplist
                elif computer in self.skiplist:
                    continue
                #if computer is active, check its timeout status
                elif time.time() - self.compstatus[computer]['timer'] > timeout:
                    frame = self.compstatus[computer]['frame']
                    print('Frame ' + str(frame) + ' on ' + computer + 
                          ' timed out in render loop. Adding to skiplist')
                    #write to error log
                    self.skiplist.append(computer)
                    print('skiplist:', self.skiplist)#debug
                    self.kill_thread(computer)
                    with threadlock:
                        self.compstatus[computer]['active'] = False
                        self.compstatus[computer]['error'] = 'timeout'

        print('_masterthread() terminating') #debug


    def _threadsactive(self):
        '''Returns true if instances of _renderthread() are active.'''
        for computer in self.compstatus:
            if self.compstatus[computer]['active'] == True:
                return True
        print('_threadsactive() returning false') #debug
        return False


    def _renderthread(self, frame, computer, framequeue):
        print('started _renderthread()', frame, computer ) #debug
    
        if computer in macs:
            renderpath = blenderpath_mac
        else:
            renderpath = blenderpath_linux
    
        command = subprocess.Popen( 'ssh igp@' + computer + ' "' + renderpath +
                ' -b ' + self.path + ' -f ' + str(frame) + ' & pgrep -n blender"', 
                stdout=subprocess.PIPE, shell=True )
    
        for line in iter(command.stdout.readline, ''):
            #convert byte object to unicode string
            #necessary for Python 3.x compatibility
            line = line.decode('UTF-8')
            if line and verbose:
                with threadlock:
                    print(line)
    
            if line.find('Fra:') >= 0 and line.find('Tile') >0:
                progress = self._parseline(line, frame, computer)
                with threadlock:
                    self.compstatus[computer]['progress'] = progress
    
            #detect PID at first line
            elif line.strip().isdigit():
                pid = line
                print('PID detected: ', pid)#debug
                with threadlock:
                    self.compstatus[computer]['pid'] = pid
                if computer in renice_list:
                    subprocess.call('ssh igp@' + computer + ' "renice 20 -p ' + 
                                     str(pid) + '"', shell=True)
                with threadlock:
                    if len(self.skiplist) > 0:
                        skipcomp = self.skiplist.pop(0)
                        with threadlock:
                            self.compstatus[skipcomp] = \
                            self._reset_compstatus(skipcomp)

            elif time.time() - self.compstatus[computer]['timer'] > timeout:
                print('_renderthread timed out on ' + computer)
                break
    
            #detect if frame has finished rendering
            elif line.find('Saved:') >= 0 and line.find('Time') >= 0:
                self.totalframes.append(frame)
                if 0 in self.totalframes:
                    self.totalframes.remove(0)
                framequeue.task_done()
                with threadlock:
                    self.compstatus[computer] = self._reset_compstatus(computer)

                #get final rendertime from blender's output
                rendertime = line[line.find('Time'):].split(' ')[1]
                print('Frame ' + str(frame) + ' finished after ' + str(rendertime))
                break
    
        #NOTE omitting stderr checking for now
        print('_renderthread() terminated', frame, computer) #debug


    def _parseline(self, line, frame, computer):
        '''Parses render progress and returns it in a compact form.'''
        tiles, total = line.split('|')[-1].split(' ')[-1].split('/')
        tiles = float(tiles)
        total = float(total)
        percent = tiles / total * 100
        return percent

    def _start_timer(self):
        '''Returns start time for a render job.'''
        if self.status == 'Stopped':
            #account for time elapsed since render was stopped
            starttime = time.time() - (self.stoptime - self.starttime)
        else:
            starttime = time.time()
        return starttime

    def get_times(self):
        '''Returns elapsed time, avg time per frame, and estimated time remaining.
        Units are float seconds.'''
        if not self.starttime:
            return (0, 0, 0)
        if self.status == 'Rendering':
            elapsed_time = time.time() - self.starttime
            frames_completed = 0
            for i in self.totalframes:
                if i != 0:
                    frames_completed += 1
            if frames_completed == 0:
                avg_time = 0
            else:
                avg_time = elapsed_time / frames_completed
            rem_time = avg_time * (len(self.totalframes) - frames_completed)
        else:
            elapsed_time = self.stoptime - self.starttime
            avg_time = elapsed_time / len(self.totalframes)
            rem_time = 0
        return (elapsed_time, avg_time, rem_time)

    def get_attrs(self):
        '''Returns dict containing all status-related attributes and times to
        update analogous Job() objects on clients.'''
        attrdict = {'status':self.status,
                    'starttime':self.starttime,
                    'stoptime':self.stoptime,
                    'complist':self.complist,
                    'compstatus':self.compstatus,
                    'path':self.path,
                    'startframe':self.startframe,
                    'endframe':self.endframe,
                    'extraframes':self.extraframes,
                    'render_engine':self.render_engine,
                    'totalframes':self.totalframes,
                    'progress':self.get_job_progress(),
                    'times':self.get_times()}
        return attrdict

    def add_computer(self, computer):
        if not self.exists():
            return 'Add failed, job does not exist.'
        elif self.compstatus[computer]['pool'] == True:
            return 'Add failed, computer already in pool.'
        else:
            self.complist.append(computer)
            self.compstatus[computer]['pool'] = True
            return 'success'

    def remove_computer(self, computer):
        if not self.exists():
            return 'Add failed, job does not exist.'
        elif self.compstatus[computer]['pool'] == False:
            return 'Add failed, computer is not in pool.'
        else:
            self.complist.remove(computer)
            self.compstatus[computer]['pool'] = False
            return 'success'

    def kill_thread(self, computer):
        '''Attempts to terminate active render thread on a specified computer.'''
        if not self.status == 'Rendering':
            return 'Failed, cannot kill frame unless render is in progress.'
        if not self.compstatus[computer]['active'] == True:
            return 'No thread assigned to computer'
        try:
            frame = self.compstatus[computer]['frame']
            pid = self.compstatus[computer]['pid']
        except:
            return 'Failed, something wrong with pid or frame info.'
        with threadlock:
            self.queue.put(frame)
        subprocess.call('ssh igp@'+computer+' "kill '
            +str(pid)+'"', shell=True)
        with threadlock:
            self.compstatus[computer]['active'] = False
            self.compstatus[computer]['error'] = 'killed'
        return 'Sent kill command for pid ' + str(pid) + ' on ' + computer

    def kill_now(self):
        '''Kills job and all currently rendering frames'''
        if not self.status == 'Rendering':
            return 'Kill failed, job is not rendering.'
        self.killflag = True
        for computer in computers:
            if self.compstatus[computer]['active'] == True:
                self.kill_thread(computer)
        self.status = 'Stopped'
        self.stoptime = time.time()
        return 'Killed job and all associated processes'

    def kill_later(self):
        '''Kills job but allows any currently rendering frames to finish.'''
        if not self.status == 'Rendering':
            return 'Kill failed, job is not rendering.'
        self.killflag = True
        self.status = 'Stopped'
        self.stoptime = time.time()
        return 'Killed job but all currently-rendering frames will continue.'






#----------GLOBAL VARIABLES----------
threadlock = threading.RLock()



#----------DEFAULTS / CONFIG FILE----------
def set_defaults():
    '''Restores all config settings to default values. Used for creating
            initial config file or restoring it if corrupted.'''

    #create list of all computers available for rendering
    computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache', 
        'conundrum', 'paradox'] 
    
    #list of computers in the 'fast' group
    fast = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente'] 
    #list of computers in the 'farm' group
    farm = ['lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache'] 
    
    #list of computer to renice processes to lowest priority. 
    #Can be changed from prefs window.
    renice_list = ['conundrum', 'paradox', 'sherman'] 
    
    #computers running OSX. Needed because blender uses different path
    macs = ['conundrum', 'paradox', 'sherman'] 
    
    #path to blender executable on OSX computers
    blenderpath_mac = '/Applications/blender.app/Contents/MacOS/blender' 
    
    #path to blender executable on Linux computers
    blenderpath_linux = '/usr/local/bin/blender' 
    
    terragenpath_mac = ('/mnt/data/software/terragen_rendernode/osx/terragen3.app' +
                       '/Contents/MacOS/Terragen_3')
    
    terragenpath_linux = '/mnt/data/software/terragen_rendernode/linux/terragen'
    
    #allowed file extensions (last 3 chars only) for check_missing_files
    allowed_filetypes = ['png', 'jpg', 'peg', 'gif', 'tif', 'iff', 'exr', 'PNG', 
        'JPG', 'PEG', 'GIF', 'TIF', 'IFF', 'EXR'] 
    
    #timeout for failed machine in seconds
    timeout = 30
    
    #start next job when current one finishes. 1=yes, 0=no, on by default
    startnext = 1 
    
    #maximum number of simultaneous renders for the start_next_job() function
    maxglobalrenders = 1 

    #terminal output verbose. 0 = normal, 1 = write everything from render 
    #stdout to terminal
    verbose = 0

    #default path, start, and end frame to put in New / Edit job window
    default_path = '/mnt/data/test_render/test_render.blend'
    default_start = 1
    default_end = 3

    #default render engine. Can be 'blender' or 'terragen'
    default_renderer = 'blender'

    defaults = [computers, fast, farm, renice_list, macs, blenderpath_mac, 
            blenderpath_linux, terragenpath_mac, terragenpath_linux, 
            allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, 
            default_path, default_start, default_end, default_renderer]

    return defaults

def define_global_config_vars(settings):
    '''Defines/updates global variables from config settings.'''
    global cfgsettings
    global computers
    global fast
    global farm
    global renice_list
    global macs
    global blenderpath_mac
    global blenderpath_linux
    global terragenpath_mac
    global terragenpath_linux
    global allowed_filetypes
    global timeout
    global startnext
    global maxglobalrenders
    global verbose
    global default_path
    global default_start
    global default_end
    global default_renderer

    print('Updating global config variables.')
    cfgsettings = settings
    computers = settings[0]
    fast = settings[1]
    farm = settings[2]
    renice_list = settings[3]
    macs = settings[4]
    blenderpath_mac = settings[5]
    blenderpath_linux = settings[6]
    terragenpath_mac = settings[7]
    terragenpath_linux = settings[8]
    allowed_filetypes = settings[9]
    timeout = settings[10]
    startnext = settings[11]
    maxglobalrenders = settings[12]
    verbose = settings[13]
    default_path = settings[14]
    default_start = settings[15]
    default_end = settings[16]
    default_renderer = settings[17]

#check for a config file
if not cfgfile.check():
    print('No config file found. Creating one from defaults.')
    cfgsettings = cfgfile.write(set_defaults())
else:
    print('Config file found. Reading...')
    try:
        cfgsettings = cfgfile.read()
    except:
        print('Config file corrupt or damaged. Creating new...')
        cfgsettings = cfgfile.write(set_defaults())

    #verify that config file contains appropriate number of entries
    #avoids error if config file is out of date with script version
    defaults = set_defaults()
    if not len(defaults) == len(cfgsettings):
        print('Config file length mismatch. Overwriting with default values...')
        cfgsettings = cfgfile.write(defaults)

#now define variables in main based on cfgsettings
define_global_config_vars(cfgsettings)

def update_cfgfile():
    cfgsettings = [computers, fast, farm, renice_list, macs, blenderpath_mac, 
            blenderpath_linux, terragenpath_mac, terragenpath_linux, 
            allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, 
            default_path, default_start, default_end, default_renderer]
    print('Updating config file.')
    cfgfile.write(cfgsettings)

def quit():
    '''Forces immediate exit without waiting for loops to terminate.'''
    os._exit(1)




#----------SERVER INTERFACE----------

'''
Client-server command-response protocol:

### Client ###      ### Server ###
send command   -->  receive command
                        |
                    validate command
                        |
receive report <--  report validation
    |
    |
send cmd args  -->  execute command w/args
                        |
                        |
receive result <--  report return string/result

Each connection from a client receives its own instance of ClientThread. This
thread checks the command against a list of valid commands, reports success or
failure of validation to the client, then executes the command with arguments 
supplied in a dict (kwargs). It then reports the string returned from the function
to the client. This can be a simple success/fail indicator, or it can be whatever
data the client has requested.

For this reason, there are some rules for functions that directly carry out 
requests from client threads:

    1. The name of the function must be in the allowed_commands list.

    2. The function must accept the kwargs argument, even if it isn't used.

    3. The function must return a string on completeion.
'''


class ClientThread(threading.Thread):
    '''Subclass of threading.Thread to encapsulate client connections'''

    def __init__(self, clientsocket):
        self.clientsocket = clientsocket
        threading.Thread.__init__(self, target=self._clientthread)

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for client.    
        Message must be a UTF-8 string.'''
        msg = bytes(message, 'UTF-8')
        msglen = str(len(msg))
        #first 8 bytes contains message length 
        while len(msglen) < 8:
            msglen = '0' + msglen
        msglen = bytes(msglen, 'UTF-8')
        self.clientsocket.sendall(msglen)
        self.clientsocket.sendall(msg)

    def _recvall(self):
        '''Receives a message of a specified length, returns it as a string.'''
        #first 8 bytes contain msg length
        msglen = int(self.clientsocket.recv(8).decode('UTF-8'))
        bytes_recvd = 0
        chunks = []
        while bytes_recvd < msglen:
            chunk = self.clientsocket.recv(2048)
            if not chunk:
                break
            chunks.append(chunk.decode('UTF-8'))
            bytes_recvd += len(chunk)
        data = ''.join(chunks)
        return data

    def _clientthread(self):
        command = self._recvall()
        #don't print anything if request is for status update
        if not command == 'get_all_attrs': print('received command', command)
        #validate command first
        if not command in allowed_commands:
            self._sendmsg('False')
            if not command == 'get_all_attrs': print('command invalid')
            return
        else:
            self._sendmsg('True')
            if not command == 'get_all_attrs': print('comamnd valid')
        #now get the args
        kwargs = self._recvall()
        if not command == 'get_all_attrs': print('received kwargs', kwargs)
        if kwargs:
            kwargs = ast.literal_eval(kwargs)
        else:
            kwargs = {}
        return_str = eval(command)(kwargs)
        if not command == 'get_all_attrs': print('sending return_str', return_str)
        #send the return string (T/F for success or fail, or other requested data)
        self._sendmsg(return_str)
        self.clientsocket.close()






#---Functions to carry out command requests from clients---

#list of permitted commands
#must match function names exactly
allowed_commands= ['cmdtest', 'get_all_attrs', 'check_slot_open', 'enqueue',
    'start_render', 'toggle_comp', 'kill_single_thread', 'kill_render']

def cmdtest(kwargs):
    '''a basic test of client-server command-response protocol'''
    print('cmdtest() called')
    for arg in kwargs:
        print('arg:', arg, kwargs[arg])
    return 'cmdtest() success'

def get_all_attrs(kwargs):
    '''Returns dict of attributes for all Job instances.'''
    attrdict = {}
    for i in renderjobs:
        attrdict[i] = renderjobs[i].get_attrs()
    return str(attrdict)

def check_slot_open(kwargs):
    '''Returns True if queue slot is open.'''
    index = kwargs['index']
    for job in renderjobs:
        print(job, renderjobs[job].exists())
    if renderjobs[index].exists() == False:
        return 'True'
    else:
        return 'False'

def enqueue(kwargs):
    '''Enqueue a job from client.'''
    index = kwargs['index']
    path = kwargs['path']
    startframe = kwargs['startframe']
    endframe = kwargs['endframe']
    extras = kwargs['extraframes']
    render_engine = kwargs['render_engine']
    complist = kwargs['complist']

    for i in kwargs:
        print(i, type(kwargs[i]))

    reply = renderjobs[index].enqueue(path, startframe, endframe, 
                                render_engine, complist, extraframes=extras)
    if reply:
        return ('Job enqueued at position ' + str(index))
    else:
        return 'Enqueue failed'

def start_render(kwargs):
    '''Start a render at the request of client.'''
    index = kwargs['index']
    reply = renderjobs[index].render()
    return reply

def toggle_comp(kwargs):
    index = kwargs['index']
    computer = kwargs['computer']
    if renderjobs[index].get_comp_status(computer)['pool'] == True:
        reply = renderjobs[index].remove_computer(computer)
    else:
        reply = renderjobs[index].add_computer(computer)
    return reply

def kill_single_thread(kwargs):
    index = kwargs['index']
    computer = kwargs['computer']
    reply = renderjobs[index].kill_thread(computer)
    return reply

def kill_render(kwargs):
    index = kwargs['index']
    kill_now = kwargs['kill_now']
    if kill_now == True:
        reply = renderjobs[index].kill_now()
    else:
        reply = renderjobs[index].kill_later()
    return reply







if __name__ == '__main__':
    maxqueuelength = 5
    renderjobs = {}
    for i in range(1, maxqueuelength + 1):
        renderjobs[i] = Job()

    #socket server to handle interface interactions
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = socket.gethostname()
    port = 2020
    s.bind((host, port))
    s.listen(5)
    print('Server now running on ' + host + ' port ' + str(port))
    print('Press Crtl + C to stop...')
    while True:
        try:
            clientsocket, address = s.accept()
            #print('Client connected from ', address)
            client_thread = ClientThread(clientsocket)
            client_thread.start()
        except KeyboardInterrupt:
            print('Shutting down server')
            #close the server socket cleanly if user interrupts the loop
            s.close()
            quit()
    s.close()


