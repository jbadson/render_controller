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
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in computers:
            self.compstatus[computer] = self._reset_compstatus(computer)


    def _reset_compstatus(self, computer):
        '''Returns a compstatus dict containing default values'''
        return { 'active':False, 'frame':None, 'pid':None, 'timer':None, 
                 'progress':0.0, 'error':None }
    

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
        elif self.status == 'Done':
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
    
            for computer in self.complist:
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

#list to contain all instances of Job()
renderjobs = []

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
    timeout = 1000 
    
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
allowed_commands= ['cmdline_render']

def cmdline_render(kwargs={}):
    '''Handles command line render requests.
    Simplified version that combines enqueue() and render() in one step'''
    path = kwargs['path']
    startframe = int(kwargs['start'])
    endframe = int(kwargs['end'])
    complist = kwargs['computers'].split(',')

    jobcmd = Job()
    renderjobs.append(jobcmd)
    jobcmd.enqueue(path, startframe, endframe, 'blender', complist)
    jobcmd.render()
    print('renderjobs', renderjobs)
    while not jobcmd.get_job_status() == 'Finished':
        reply = jobcmd.get_job_progress()
        time.sleep(0.1)
    return reply


def statusthread():
    '''simple thread to print the progress % of each job to the terminal'''
    print('starting status thread') #debug
    while True:
        #global renderjobs
        if len(renderjobs) > 0:
            for job in renderjobs:
                if job.get_job_status() == 'Rendering':
                    percent = job.get_job_progress()
                    print('Rendering, ' + str(percent) + '% complete.')
                    for computer in computers:
                        compstat = job.get_comp_status(computer)
                        if compstat['active']:
                            print('Frame ' + str(compstat['frame']) + ':' + str(compstat['progress']) + '%')
                        
        time.sleep(2)


class ClientThread(threading.Thread):
    '''Subclass of threading.Thread to encapsulate client connections'''
    def __init__(self, clientsocket):
        self.clientsocket = clientsocket
        threading.Thread.__init__(self, target=self._clientthread)

    def _clientthread(self):
        print('_clientthread() started') #debug
        while True:
            data = self.clientsocket.recv(4096)
            if not data:
                break
            print('Data', data) #debug
            data = eval(data.decode('UTF-8'))
            print(data)
            print(type(data))
            self.clientsocket.sendall(bytes('Message Received', 'UTF-8'))
            command = data['command']
            #delete command key, leaving args
            del data['command']
            print('kwargs:', data)
            if not command in allowed_commands:
                #refuse commands that aren't in approved list
                self.clientsocket.sendall(bytes('Invalid command, terminating.', 'UTF-8'))
                break
            else:
                #call function(kwargs) as command(data)
                eval(command)(kwargs=data)
            break

        self.clientsocket.close()
        print('_clientthread() terminated')#debug


if __name__ == '__main__':
    #start the status reporter thread
    statthread = threading.Thread(target=statusthread)
    statthread.start()

    #socket server to handle interface interactions
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = socket.gethostname()
    port = 2020
    s.bind((host, port))
    s.listen(5)
    print('Server now running on ' + host + ' port ' + str(port))
    while True:
        clientsocket, address = s.accept()
        print('Client connected from ', address)
        client_thread = ClientThread(clientsocket)
        client_thread.start()

    s.close()

#
##----------TKINTER GUI----------
#
#
#import tkinter as tk
#import tkinter.ttk as ttk
#import tkinter.font as tkfont
#import tkinter.filedialog as tkFileDialog
#import tkinter.scrolledtext as st
#import tkinter.messagebox as tk_msgbox
#
##----GUI CLASSES----
#
#class ClickFrame(tk.Frame):
#    '''version of tkinter Frame that functions as a button when clicked
#
#    creates a new argument - index - that identifies which box was clicked''' 
#
#    def __init__(self, master, index, **kw):
#        tk.Frame.__init__(self, master, **kw)
#        self.index = index
#        self.bind('<Button-1>', lambda x: set_job(self.index))
#
#
#class ClickLabel(tk.Label):
#    '''version of tkinter Label that functions as a button when clicked'''
#
#    def __init__(self, master, index, **kw):
#        tk.Label.__init__(self, master, **kw)
#        self.index = index
#        self.bind('<Button-1>', lambda x: set_job(self.index))
#
#
#class FramesHoverLabel(ClickLabel):
#    '''version of ClickLabelthat also has a hover binding'''
#
#    def __init__(self, master, index, **kw):
#        ClickLabel.__init__(self, master, index, **kw)
#        self.bind('<Enter>', lambda x: extraballoon(x, index))
#
#
#class NameHoverLabel(ClickLabel):
#    '''version of clicklabel that also has a hover binding'''
#
#    def __init__(self, master, index, **kw):
#        ClickLabel.__init__(self, master, index, **kw)
#        self.bind('<Enter>', lambda x: nameballoon(x, index))
#
#
#class ClickCanvas(tk.Canvas):
#    '''version of tkinter Canvas that functions like a button when clicked'''
#
#    def __init__(self, master, index, **kw):
#        tk.Canvas.__init__(self, master, **kw)
#        self.index = index
#        self.bind('<Button-1>', lambda x: set_job(self.index))
#
#
#class ClickProg(ttk.Progressbar):
#    '''version of ttk progress bar that does stuff when clicked'''
#
#    def __init__(self, master, index, **kw):
#        ttk.Progressbar.__init__(self, master, **kw)
#        self.bind('<Button-1>', lambda x: set_job(index))
##
#
#class JobBox(object):
#    '''GUI element representing a single job in the queue frame.'''
#
#    def __init__(self, master, index):
#        container = ClickFrame(master, index=index, bd=2, relief=tk.GROOVE)
#        container.pack(padx=5, pady=5)
#        ClickCanvas(container, width=121, height=21, highlightthickness=0, 
#            index=index).grid(row=0, column=0)
#        NameHoverLabel(container, text='Filename', wraplength=130, anchor=tk.W, 
#            index=index).grid(row=0, column=1)
#        ClickLabel(container, text='Startframe', index=index).grid(row=0, column=2)
#        ClickLabel(container, text='Endframe', index=index).grid(row=0, column=3)
#        FramesHoverLabel(container, text='Extraframes', index=index).grid(row=0, 
#            column=4)
#        
#        timecanv = ClickCanvas(container, name='timecanv_'+str(i), width=615, 
#            height=20, highlightthickness=0, index=index)
#        timecanv.grid(row=1, column=0, columnspan=8, sticky=tk.W)
#        timecanv.create_text(35, 10, text='Total time:')
#        timecanv.create_text(240, 10, text='Avg/frame:')
#        timecanv.create_text(448, 10, text='Remaining:')
#
#        ClickProg(container, length=500, index=index).grid(row=2, column=0, 
#            columnspan=8, sticky=tk.W)
#        perdone = ClickCanvas(container, width=110, height=20, index=i, 
#            highlightthickness=0)
#        perdone.grid(row=2, column=7, sticky=tk.E, padx=3) 
#        perdone.create_text(55, 9, text='0% Complete')
#
#        buttonframe = ClickFrame(container, index=index, bd=0)
#        buttonframe.grid(row=3, column=0, columnspan=8, sticky=tk.W)
#        tk.Button(buttonframe, text='New / Edit').pack(side=tk.LEFT)
#        tk.Button(buttonframe, text='Start').pack(side=tk.LEFT)
#        tk.Button(buttonframe, text='Stop').pack(side=tk.LEFT)
#        tk.Button(buttonframe, text='Resume').pack(side=tk.LEFT)
#        tk.Button(buttonframe, text='Remove Job').pack(side=tk.RIGHT)
#        
#
#
#
##----GUI FUNCTIONS----
#
#
#def update_gui():
#    '''Refreshes GUI'''
#    root.update_idletasks()
#    root.after(80, update)
#
#def set_job(index):
#    print('This is setjob', index)
#
#root = tk.Tk()
#root.title('IGP Render Controller Mk. V')
#root.config(bg='gray90')
#root.minsize(1145, 400)
#root.geometry('1145x525')
##use internal quit function instead of OSX
#root.bind('<Command-q>', lambda x: quit()) 
#root.bind('<Control-q>', lambda x: quit())
##ttk.Style().theme_use('clam') #use clam theme for widgets in Linux
#
#smallfont = tkfont.Font(family='System', size='10')
#
##test font width & adjust font size to make sure everything fits with 
##different system fonts
#fontwidth = smallfont.measure('abc ijk 123.456')
#newsize = 10
#if fontwidth > 76:
#    while fontwidth > 76:
#        newsize -= 1
#        smallfont = tkfont.Font(family='System', size=newsize)
#        fontwidth = smallfont.measure('abc ijk 123.456')
#
#
#topbar = tk.Frame(root)
#topbar.pack(padx=10, pady=10, anchor=tk.W)
#tk.Label(topbar, text='This is topbar').pack()
#
#main_container = tk.LabelFrame(root)
#main_container.pack(padx=10, pady=10, anchor=tk.W)
#
#
#for i in range(1, 5 + 1):
#    jobbox = JobBox(main_container, i)
#
#root.mainloop()
