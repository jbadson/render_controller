#Fifth major revison of IGP render controller
#must run in python 3
import queue
import threading
import time
import cfgfile
import subprocess
import os
import socket

class Job(object):
    '''Represents a render job.'''

    def __init__(self):
        '''Attributes: index = int job identifier.'''
        self.status = 'Empty'
        self.complist = []
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in computers:
            self.compstatus[computer] = self._reset_compstatus(computer)


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
        try:
            if self.path:
                return True
            else:
                return False
        except:
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
        '''Create a new job and place it in queue.
        Returns true if successful.'''
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
            return False
        self.status = 'Rendering'
        #start render timer
        #create log entry

        self.skiplist = []
        self.killflag = False

        master = threading.Thread(target=self._masterthread, args=())
        master.start()


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
                #stop render timer
                #write status to log
                break
    
            #for computer in self.complist:
            #trying something different
            for computer in computers:
                if self.compstatus[computer]['pool'] == False:
                    continue
                if not self.compstatus[computer]['active'] and \
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
    
                #if computer was busy or in skiplist, check it's timeout
                elif time.time() - self.compstatus[computer]['timer'] > timeout:
                    frame = self.compstatus[computer]['frame']
                    print('Frame ' + str(frame) + ' on ' + computer + 
                          ' timed out in render loop. Retrying')
                    #write to error log
                    self.skiplist.append(computer)
                    self.queue.put(self.compstatus[computer]['frame'])
                    #send kill process command
                    with threadlock:
                        self.compstatus[computer]['active'] = False
                        self.compstatus[computer]['error'] = 'timeout'

            time.sleep(0.01)
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
                ' -b ' + self.path + ' -f ' + str(frame) + '"', 
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
                with threadlock:
                    self.compstatus[computer]['pid'] = pid
                if computer in renice_list:
                    subprocess.call('ssh igp@' + computer + ' "renice 20 -p ' + 
                                     str(pid) + '"', shell=True)
                with threadlock:
                    if len(skiplist) > 0:
                        skipcomp = skiplist.pop(0)
                        with threadlock:
                            self.compstatus[skipcomp] = \
                            self._reset_compstatus(skipcomp)
    
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












#---------GLOBAL VARIABLES----------
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

#list of allowed commands for the server to receive
#must be exactly 10 characters long
allowed_commands= ['cmd_render', 'get_status', 'enqueuejob', 'rendrstart']
#queue to hold replies
replyqueue = queue.Queue()

def cmd_render(kwargs={}):
    '''Handles command line render requests.
    Simplified version that combines enqueue() and render() in one step'''
    path = kwargs['path']
    startframe = int(kwargs['start'])
    endframe = int(kwargs['end'])
    complist = kwargs['computers'].split(',')

    job = Job()
    #renderjobs[id(job)] = job
    #look for an empty queue slot, put the job there
    #XXX This will have to be done differently later to accomodate more renders
    for i in renderjobs:
        if not renderjobs[i]:
            renderjobs[i] = job
            print('Enqueued at slot ' + str(i))
            break

    job.enqueue(path, startframe, endframe, 'blender', complist)
    job.render()
    print('renderjobs', renderjobs)


def get_status(kwargs={}):
    '''Testing way to return current job status over socket.'''
    statdict = {}
    for job in renderjobs:
        if not renderjobs[job].exists():
            continue
        statdict[job] = { 'status':renderjobs[job].get_job_status(), 
                        'path':renderjobs[job].path, 
                        'startframe':renderjobs[job].startframe, 
                        'endframe':renderjobs[job].endframe,
                        'extraframes':renderjobs[job].extraframes, 
                        'complist':renderjobs[job].complist,
                        'render_engine':renderjobs[job].render_engine, 
                        'progress':renderjobs[job].get_job_progress(),
                        'compstatus':renderjobs[job].compstatus }

    statstr = str(statdict)
    print('putting statstr in queue')
    replyqueue.put(str(statstr))
    return statstr

def enqueuejob(kwargs={}):
    '''Place a new job in queue.'''
    index = kwargs['index']
    path = kwargs['path']
    start = int(kwargs['startframe'])
    end = int(kwargs['endframe'])
    extras = kwargs['extraframes']
    if extras != '':
        extras = extras.split(',')
    else:
        extras = []
    render_engine = kwargs['render_engine']
    complist = kwargs['complist'].split(',')

    #XXX Need check here to make sure we're not overwriting queue
    renderjobs[index].enqueue(path, start, end, render_engine, complist, extras)
    print('Enqueued new job at slot ' + str(index))

def rendrstart(kwargs={}):
    index = kwargs['index']
    renderjobs[index].render()
    print('Starting render for job ' + str(index))

#def statusthread():
#    '''simple thread to print the progress % of each job to the terminal'''
#    print('starting status thread') #debug
#    while True:
#        if len(renderjobs) > 0:
#            for job in renderjobs:
#                if renderjobs[job].get_job_status() == 'Rendering':
#                    percent = renderjobs[job].get_job_progress()
#                    print('Rendering, ' + str(percent) + '% complete.')
#                    for computer in computers:
#                        compstat = renderjobs[job].get_comp_status(computer)
#                        if compstat['active']:
#                            print('Frame ' + str(compstat['frame']) + ':' 
#                                    + str(compstat['progress']) + '%')
#                        
#        time.sleep(2)


class ClientThread(threading.Thread):
    '''Subclass of threading.Thread to encapsulate client connections'''
    def __init__(self, clientsocket):
        self.clientsocket = clientsocket
        threading.Thread.__init__(self, target=self._clientthread)

    def _clientthread(self):
        #print('_clientthread() started') #debug
        while True:
            data = self.clientsocket.recv(4096)
            if not data:
                break

            data = data.decode('UTF-8')
            print(data)
            #first 10 characters are the command string
            #can be 'get_status', 'cmd_render'
            command = data[0:10]
            if not command in allowed_commands:
                #refuse commands that aren't in approved list
                print('Invalid command received', command)
                print('#'*50)
                print(data)
                self.clientsocket.sendall(bytes('Invalid command, terminating.',                                                    'UTF-8'))
                break
            else:
                if len(data) > 10:
                    kwargs = eval(data[10:])
                else:
                    kwargs = None
                print('kwargs:', kwargs)
                #call function as command(kwargs)
                eval(command)(kwargs=kwargs)

            if not replyqueue.empty():
                reply = replyqueue.get()
                self.clientsocket.sendall(bytes(reply, 'UTF-8'))
                print('sending reply', reply)
            break

        self.clientsocket.close()
        #print('_clientthread() terminated')#debug


if __name__ == '__main__':
    #start the status reporter thread
    #statthread = threading.Thread(target=statusthread)
    #statthread.start()

    #list to contain all render Job instances
    #fixed queue of 5 for simplicity's sake for now
    maxqueuelength = 6
    renderjobs = {}
    for i in range(1, maxqueuelength):
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


