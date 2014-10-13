#graphical user interface for IGP Render Controller
#Written for Python 3.4

'''
#####################################################################
Copyright 2014 James Adson

This file is part of IGP Render Controller.  
IGP Render Controller is free software: you can redistribute it 
and/or modify it under the terms of the GNU General Public License 
as published by the Free Software Foundation, either version 3 of 
the License, or any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
#####################################################################
'''

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.filedialog as tk_filedialog
import tkinter.messagebox as tk_msgbox
import tkinter.scrolledtext as tk_st
import socket
import time
import threading
import os.path
import ast
import json
import cfgfile
import framechecker
import tk_extensions as tkx

illegal_characters = [' ', ';', '&'] #not allowed in path

class ClientSocket(object):
    '''Wrapper for socket to handle command-response protocol for interacting 
    with the render controller server.'''
    HOST = 'localhost'
    PORT = 2020

    def setup(host, port):
        ClientSocket.HOST = host
        ClientSocket.PORT = port

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((ClientSocket.HOST, ClientSocket.PORT))

    def _recvall(self):
        '''Receives message of specified length, returns it as a string.'''
        #first 8 bytes contain msg length
        msglen = int(self.socket.recv(8).decode('UTF-8'))
        bytes_recvd = 0
        chunks = []
        while bytes_recvd < msglen:
            chunk = self.socket.recv(2048)
            if not chunk:
                break
            chunks.append(chunk.decode('UTF-8'))
            bytes_recvd += len(chunk)
        #now having everything be json object for web interface convenience
        data = json.loads(''.join(chunks))
        return data

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for server.
        Message must be compatible with json.dumps/json.loads.'''
        #now doing everything in json for web interface convenience
        message = json.dumps(message)
        msg = bytes(message, 'UTF-8')
        msglen = str(len(msg))
        #first 8 bytes contains message length 
        while len(msglen) < 8:
            msglen = '0' + msglen
        msglen = bytes(msglen, 'UTF-8')
        self.socket.sendall(msglen)
        self.socket.sendall(msg)

    def send_cmd(self, command, kwargs={}):
        '''Sends a command to the server. Command must be a UTF-8 string.
        Associated args should be supplied as a dict. Returns a string'''
        #send command first, wait for response, then send args
        #don't print anything if command is request for status update
        if not command == 'get_attrs': print('sending command', command) #debug
        self._sendmsg(command)
        #check that the command was valid
        cmd_ok = ast.literal_eval(self._recvall())
        if not cmd_ok:
            return 'Invalid command'
        #if command was valid, send associated arguments
        if not command == 'get_attrs': print('sending kwargs', str(kwargs))
        self._sendmsg(kwargs)
        #collect the return string (True/False for success/fail or requested data)
        return_str = self._recvall()
        if not command == 'get_attrs': print('received return_str', return_str)
        self.socket.close()
        return return_str


def cmdtest():
    '''a basic test of client server command-response protocol'''
    command = 'cmdtest'
    kwargs = {'1':'one', '2':'two'}
    return_str = ClientSocket().send_cmd(command, kwargs)
    print(return_str)

def job_exists(index):
    '''Returns true if index is in use on server.'''
    command = 'job_exists'
    kwargs = {'index':index}
    reply = ClientSocket().send_cmd(command, kwargs)
    return reply

def get_job_status(index):
    '''Returns the status string for a given job.'''
    kwargs = {'index':index}
    status = ClientSocket().send_cmd('get_status', kwargs)
    return status

def quit(event=None):
    '''Terminates status thread and mainloop, then sends exit call.'''
    StatusThread.stop = True
    raise SystemExit


#----------CONFIG VARIABLES----------
class Config(object):
    '''Object to hold global configuration variables as class attributes. 
    There are two divisions: local (GUI) and server. The local variables are 
    stored in gui_config.json and affect only GUI-related features. Server 
    variables are obtained from the server and changes to them will affect 
    all users.'''
    def __init__(self):
        self.cfg = cfgfile.ConfigFile(filename='gui_config.json')
        if not self.cfg.exists():
            print('No GUI config file found, creating one from defaults.')
            guisettings = self.cfg.write(self.defaults())
        else:
            print('GUI config file found, reading...')
            try:
                guisettings = self.cfg.read()
                if not len(guisettings) == len(self.defaults()):
                    raise IndexError
            except Exception:
                print('GUI config file corrupt or incorrect. Creating new')
                guisettings = self.cfg.write(self.defaults())
        (
        Config.default_path, Config.default_startframe, 
        Config.default_endframe, Config.default_render_engine,
        Config.input_win_cols, Config.comp_status_panel_cols,
        Config.default_host, Config.default_port, Config.refresh_interval
        ) = guisettings

    def defaults(self):
        '''Restores GUI config file variables to default values. Also used 
        for creating the initial config file.'''
        #default values for fields in the input window
        default_path = '/mnt/data/test_render/test_render.blend'
        default_startframe = 1
        default_endframe = 4
        default_render_engine = 'blend'
        #numbers of colums for widget arrays
        input_win_cols = 5
        comp_status_panel_cols = 3
        #default server setup info
        default_host = 'localhost'
        default_port = 2020
        refresh_interval = 0.5 #StatusThread update freq. in seconds
        return (default_path, default_startframe, default_endframe, 
                default_render_engine, input_win_cols, comp_status_panel_cols,
                default_host, default_port, refresh_interval)

    def get_server_cfg(self):
        '''Gets config info from the server. Most of these aren't directly
        used by the GUI, but are here for the preferences window.'''
        try:
            servercfg = ClientSocket().send_cmd('get_config_vars')
        except Exception as e:
            return e
        (
        Config.computers, Config.renice_list, 
        Config.macs, Config.blenderpath_mac, Config.blenderpath_linux, 
        Config.terragenpath_mac, Config.terragenpath_linux, 
        Config.allowed_filetypes, Config.timeout, Config.serverport,
        Config.autostart, Config.verbose, Config.log_basepath 
        ) = servercfg
        return False
    
    #def get_gui_vars(self):
        '''Returns an n-tuple of all current GUI config vars.'''
        '''
        return (
            Config.default_path, Config.default_startframe, 
            Config.default_endframe, Config.default_render_engine,
            Config.input_win_cols, Config.comp_status_panel_cols,
            Config.default_host, Config.default_port, Config.refresh_interval
            )'''




#----------GUI----------
#XXX Some additional config stuff, decide where to put it later
#XXX Get rid of LightBlueBGColor if you're not going to use it.
LightBlueBGColor = 'white'
MidBGColor = '#%02x%02x%02x' % (190, 190, 190)
ttkNtbkBGColor = '#%02x%02x%02x' % (223, 223, 223)
LightBGColor = '#%02x%02x%02x' % (232, 232, 232)
#DarkBGColor = '#%02x%02x%02x' % (50, 50, 50)
HighlightColor = '#%02x%02x%02x' % (74, 139, 222)


class MasterWin(tk.Tk):
    '''This is the master class for this module. To create a new GUI,
    create an instance of this class then call the mainloop() method on it.
    Other classes and methods within this module are not intended to be used
    without an instance of MasterWin and will probably break if you try.'''
    def __init__(self):
        tk.Tk.__init__(self)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.title('IGP Render Controller Client')
        self.config(bg=LightBGColor)
        self.minsize(width=1257, height=730)
        #create dictionaries to hold job-specific GUI elements
        #format is {'index':object}
        self.firstrun = True
        self.jobboxes = {}
        self.boxlist = [] #ordered list of job boxes (for sorting)
        self.comppanels = {}
        #at startup, display startup frame first
        self._setup_panel()

    def _setup_panel(self):
        '''Gets server connection info from the user.'''
        self.setupframe = ttk.Frame(self)
        self.setupframe.pack(padx=50, pady=50)
        self.tk_host = tk.StringVar()
        self.tk_port = tk.StringVar()
        self.statthread = StatusThread(masterwin=self)
        #initialize local config variables
        Config()
        #put default values where they go
        ClientSocket.setup(host=Config.default_host, port=Config.default_port)
        self.tk_host.set(ClientSocket.HOST)
        self.tk_port.set(ClientSocket.PORT)
        ttk.Label(
            self.setupframe, text='Connection Setup', font='TkCaptionFont'
            ).grid(row=0, column=0, columnspan=2, pady=10)
        ttk.Label(self.setupframe, text='Server address:').grid(
            row=1, column=0, sticky=tk.E, pady=5
            )
        ttk.Entry(self.setupframe, width=30, textvariable=self.tk_host).grid(
            row=1, column=1, sticky=tk.W, padx=5, pady=5
            )
        ttk.Label(self.setupframe, text='Port:').grid(
            row=2, column=0, sticky=tk.E, pady=5
            )
        ttk.Entry(self.setupframe, width=10, textvariable=self.tk_port).grid(
            row=2, column=1, sticky=tk.W, padx=5, pady=5
            )
        ttk.Button(
            self.setupframe, text='Connect', command=self._apply_setup
            ).grid(row=3, column=0, columnspan=2, padx=10, pady=10)
        self.bind('<Return>', self._apply_setup)
        self.bind('<KP_Enter>', self._apply_setup)

    def _apply_setup(self, event=None):
        '''Apply server config info then build the main window.'''
        print('setup done') #debug
        #configure host and port class attributes
        ClientSocket.setup(host=self.tk_host.get(), port=int(self.tk_port.get()))
        #get the server config variables
        msg = Config().get_server_cfg()
        if msg:
            print('Could not retrieve config vars form server:', msg)
            ttk.Label(
                self, text='Server connection failed: ' + str(msg)
                ).pack()
            return
        self.verbosity = tk.IntVar()
        self.verbosity.set(Config.verbose)
        self.autostart = tk.IntVar()
        self.autostart.set(Config.autostart)
        self.setupframe.destroy()
        self._build_main()
        self.statthread.start()
        self.unbind('<Return>')
        self.unbind('<KP_Enter>')

    def _build_main(self):
        '''Creates the main window elements.'''
        topbar = tk.Frame(self, bg=MidBGColor)
        topbar.pack(fill=tk.BOTH)
        ttk.Checkbutton(
            topbar, text='Verbose', command=self._toggle_verbose,
            variable=self.verbosity, style='Toolbutton'
            ).pack(padx=(25, 5), pady=10, side=tk.LEFT)
        ttk.Checkbutton(
            topbar, text='Autostart', command=self._toggle_autostart,
            variable=self.autostart, style='Toolbutton'
            ).pack(padx=5, side=tk.LEFT)
        ttk.Button(
            topbar, text='Check Missing Frames', command=self._checkframes, 
            style='Toolbutton'
            ).pack(padx=5, side=tk.LEFT)
        ttk.Button(
            topbar, text='Preferences', command=PrefsWin, style='Toolbutton'
            ).pack(padx=5, side=tk.LEFT)
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        midblock = tk.Frame(self, bg=LightBGColor)
        midblock.pack(padx=15, pady=(10, 20), expand=True, fill=tk.BOTH)
        
        left_frame = tk.Frame(midblock, bg=LightBGColor)
        left_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        tk.Label(
            left_frame, text='Queue:', bg=LightBGColor
            ).pack(padx=5, anchor=tk.W)
        left_frame_inner = tk.LabelFrame(left_frame, bg=LightBGColor)
        left_frame_inner.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        
        self.jobbox_frame = tk.Frame(left_frame_inner, bg=LightBlueBGColor, 
                                     width=260)
        self.jobbox_frame.pack(expand=True, fill=tk.BOTH)
        jobbtns = tk.Frame(left_frame_inner, bg=LightBGColor)
        jobbtns.pack(fill=tk.X)
        ttk.Separator(jobbtns).pack(fill=tk.X)
        tkx.RectButton(jobbtns, text='+', command=self._new_job
            ).pack(side=tk.LEFT)
        tkx.RectButton(jobbtns, text='-', command=self._delete_job
            ).pack(side=tk.LEFT)
        
        self.right_frame = ttk.LabelFrame(midblock, width=921)
        self.right_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.BOTH)

    def update(self, serverjobs):
        '''Takes dict containing all server job info and updates 
        children based on that.'''
        #get the extra stuff first
        self.serverjobs = serverjobs
        _extra_info = serverjobs['_EXTRA_']
        self.verbosity.set(_extra_info['verbose'])
        self.autostart.set(_extra_info['autostart'])
        del serverjobs['_EXTRA_']
        #create local job instances for any new jobs on server
        for index in serverjobs:
            if not index in self.jobboxes:
                self._create_job(index)
        #delete any local jobs that are no longer on the server
        dellist = []
        for index in self.jobboxes:
            if not index in serverjobs:
                #can't directly delete here b/c dict length will change-->exception
                dellist.append(index)
        for index in dellist:
            self._remove_job(index)
        #now update GUI elements
        for index in serverjobs:
            attrdict = serverjobs[index]
            #update job box
            self.jobboxes[index].update(
                attrdict['status'], attrdict['startframe'], attrdict['endframe'], 
                attrdict['path'], attrdict['progress'], attrdict['times'],
                attrdict['queuetime']
                )
            #update comp panel
            self.comppanels[index].update(attrdict)
        #attempt re-sorting job boxes
        self.sort_jobboxes()
        #XXX testing for prog bars
        #this does seem to fix the issue of lagging updates
        #self.update_idletasks()


    def _new_job(self):
        '''Opens an instance of InputWindow to create a new job on the server.

        GUI elements are not created directly by this function. They are created 
        by self.update() when called by the status thread to ensure that the GUI 
        state is only changed if the server state was successfully changed.'''
        newjob = InputWindow()

    def _delete_job(self):
        '''Deletes the selected job from the server.

        GUI elements are not removed directly by this function. They are deleted
        by self.update() when called by the status thread to ensure that the GUI 
        state is only changed if the server state was successfully changed.'''
        nojobs = True
        for index in self.jobboxes:
            if self.jobboxes[index].selected:
                nojobs = False
                break
        if nojobs: #do nothing if no job is selected
            return
        if get_job_status(index) == 'Rendering':
            Dialog("Can't delete a job while it's rendering.").warn()
            return
        if not Dialog('Delete ' + index + ' from the queue?').confirm():
            return
        kwargs = {'index':index}
        reply = ClientSocket().send_cmd('clear_job', kwargs)
        print(reply)

    def _create_job(self, index):
        '''Creates GUI elements for a given index.'''
        #create job box
        self.jobboxes[index] = SmallBox(masterwin=self, master=self.jobbox_frame, 
                                        index=index)
        self.jobboxes[index].pack()
        #let sort_jobboxes pack everything in the correct place
        #put box in list (at top for now)
        self.boxlist.insert(0, self.jobboxes[index])
        #create comp panel
        self.comppanels[index] = ComputerPanel(master=self.right_frame, 
                                               index=index)

    def _remove_job(self, index):
        '''Permanently removes GUI elements for a given index.'''
        #delete job box
        self.jobboxes[index].destroy()
        self.boxlist.remove(self.jobboxes[index])
        del self.jobboxes[index]
        #delete comp panel
        self.comppanels[index].destroy()
        del self.comppanels[index]

    def sort_jobboxes(self):
        '''Sorts the job status boxes vertically according to sorting rules.
        First sorts by status, then by queuetime.'''
        boxlist = []
        done, stopped, waiting, paused, rendering = [], [], [], [], []
        #first sort boxes into categories by status
        for i in self.jobboxes:
            box = self.jobboxes[i]
            if box.status == 'Rendering':
                rendering.append(box)
            elif box.status == 'Paused':
                paused.append(box)
            elif box.status == 'Waiting':
                waiting.append(box)
            elif box.status == 'Stopped':
                stopped.append(box)
            else:
                done.append(box)
        #sort boxes within each category chronologically
        if len(rendering) > 1:
            rendering = self.sort_chrono(rendering)
        if len(paused) > 1:
            paused = self.sort_chrono(paused)
        if len(waiting) > 1:
            waiting = self.sort_chrono(waiting)
        if len(stopped) > 1:
            stopped = self.sort_chrono(stopped)
        if len(done) > 1:
            done = self.sort_chrono(done)
        boxlist = rendering + paused + waiting + stopped + done
        if boxlist == self.boxlist:
            return
        else:
            self.boxlist = boxlist
        for index in self.jobboxes:
            self.jobboxes[index].pack_forget()
        for box in self.boxlist:
            box.pack()
        if self.firstrun:
            self.select_job(self.boxlist[0].index)
            self.firstrun = False

    def sort_chrono(self, sortlist):
        '''Takes a list of SmallBox instances in any order, returns the list
        sorted chronologically by queue time.'''
        boxes = {}
        for box in sortlist:
            boxes[box.queuetime] = box
        qtimes = sorted(boxes.keys())
        newlist = []
        for time in qtimes:
            newlist.append(boxes[time])
        newlist.reverse()
        return newlist

    def select_job(self, index):
        for i in self.jobboxes:
            if not i == index and self.jobboxes[i].selected:
                self.deselect_job(i)
        self.jobboxes[index].select()
        self.comppanels[index].pack(padx=10, pady=10)

    def deselect_job(self, index):
        self.jobboxes[index].deselect()
        self.comppanels[index].pack_forget()

    def _checkframes(self):
        '''Opens check missing frames window. If a job is currently selected,
        data for that job will be put into the corresponding fields in the
        new window.'''
        for index in self.jobboxes:
            if self.jobboxes[index].selected:
                print(index, 'selected, populating checkframes fields')
                job = self.serverjobs[index]
                self.checkwin = MissingFramesWindow(
                    job['path'], job['startframe'], job['endframe']
                    )
                return
        self.checkwin = MissingFramesWindow()

    def _toggle_verbose(self):
        '''Toggles verbose reporting state on the server.'''
        reply = ClientSocket().send_cmd('toggle_verbose')
        print(reply)

    def _toggle_autostart(self):
        '''Toggles the autostart state on the server.'''
        reply = ClientSocket().send_cmd('toggle_autostart')
        print(reply)


class ComputerPanel(ttk.Frame):
    '''Main job info panel with computer boxes.'''
    def __init__(self, master, index):
        self.index = index
        ttk.Frame.__init__(self, master=master)
        #Create the main job status box at the top of the panel
        self.bigbox = BigBox(master=self, index=self.index)
        self.bigbox.pack(expand=True, fill=tk.X, padx=5)
        #Create job control buttons
        buttonbox = ttk.Frame(self)
        buttonbox.pack(anchor=tk.W, padx=5, pady=5)
        ttk.Button(buttonbox, text='Edit', command=self._edit).pack(side=tk.LEFT)
        ttk.Button(buttonbox, text='Start', command=self._start).pack(side=tk.LEFT)
        ttk.Button(
            buttonbox, text='Stop', command=self._kill_render
            ).pack(side=tk.LEFT)
        ttk.Button(
            buttonbox, text='Resume', command=self._resume_render
            ).pack(side=tk.LEFT)
        ttk.Label(buttonbox, text='Priority:').pack(side=tk.LEFT, padx=(5, 0))
        self.tk_priority = tk.StringVar()
        self.primenu = ttk.OptionMenu(
            buttonbox, self.tk_priority, 'Normal', 'Normal', 'High', 
            command=self._set_priority
            )
        self.primenu.pack(side=tk.LEFT, pady=(0, 2))
        self._create_computer_array()

    def _create_computer_array(self):
        self.compframe = ttk.Frame(self)
        self.compframe.pack()
        self.compcubes = {}
        #changing the number of cols should automatically generate the rest
        #of the layout correctly. 
        self.cols = Config.comp_status_panel_cols
        n = 0 #index of computer in computers list
        row = 0 #starting position
        while n < len(Config.computers):
            (x, y) = self._getcoords(n, row)
            self.compcubes[Config.computers[n]] = CompCube(
                master=self.compframe, computer=Config.computers[n], 
                index=self.index
                )
            self.compcubes[Config.computers[n]].grid(row=y, column=x, padx=5)
            n += 1
            if x == self.cols - 1:
                row += 1

    def _getcoords(self, n, row):
        '''Returns coordinates (column, row) for computer box.
        n = index of that computer in the list.
        row = current row
        cols = number of columns in layout'''
        x = n - self.cols * row
        y = n - n + row
        return (x, y)

    def _edit(self):
        '''Edits job information.'''
        kwargs = {'index':self.index}
        attrs = ClientSocket().send_cmd('get_attrs', kwargs)
        denystatuses = ['Rendering', 'Stopped', 'Paused']
        if attrs['status'] in denystatuses:
            Dialog('Job cannot be edited.').warn()
            return
        editjob = InputWindow(
            index=self.index, path=attrs['path'], start=attrs['startframe'],
            end=attrs['endframe'], extras=attrs['extraframes'],
            engine=attrs['render_engine'], complist=attrs['complist']
            )

    def _start(self):
        '''Starts the render.'''
        if not get_job_status(self.index) == 'Waiting':
            Dialog('Cannot start render unless status is "Waiting"').warn()
            return
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('start_render', kwargs)
        print(reply)

    def _kill_render(self):
        '''Kill the current render.'''
        if get_job_status(self.index) != 'Rendering':
            Dialog('Cannot stop a render unless its status is "Rendering"').warn()
            return
        confirm = Dialog('Stopping render. Allow currently rendering frames to '
                         'finish?').yesnocancel()
        if confirm == 'cancel':
            return
        elif confirm == 'yes':
            kill_now = False
        elif confirm == 'no':
            kill_now = True
        kwargs = {'index':self.index, 'kill_now':kill_now}
        reply = ClientSocket().send_cmd('kill_render', kwargs)
        print(reply)

    def _resume_render(self):
        resumestatuses = ['Stopped', 'Paused']
        if get_job_status(self.index) not in resumestatuses:
            Dialog('Can only resume renders that have been stopped or '
                   'paused.').warn()
            return
        reply = Dialog('Start render now? Otherwise job will be placed in '
            'queue to render later.').yesnocancel()
        if reply == 'yes':
            startnow = True
        elif reply == 'no':
            startnow = False
        else:
            return
        kwargs = {'index':self.index, 'startnow':startnow}
        reply = ClientSocket().send_cmd('resume_render', kwargs)
        print(reply)

    def _set_priority(self, value='Normal'):
        print('value:', value)
        print('self.tk_priority', self.tk_priority.get())
        kwargs = {'index':self.index, 'priority':value}
        reply = ClientSocket().send_cmd('set_job_priority', kwargs)
        print(reply)

    def update(self, attrdict):
        '''Calls the update methods for all child elements.'''
        if attrdict['priority'] != self.tk_priority.get():
            self.tk_priority.set(attrdict['priority'])
        self.bigbox.update(
            attrdict['status'], attrdict['startframe'], 
            attrdict['endframe'], attrdict['extraframes'], attrdict['path'], 
            attrdict['progress'], attrdict['times']
            )
        for computer in Config.computers:
            compstatus = attrdict['compstatus'][computer]
            self.compcubes[computer].update(
                compstatus['frame'], compstatus['progress'], compstatus['pool']
                )


class _statusbox(object):
    '''Master class for status box-related objects. Holds shared methods related to
    output formatting.'''
    def format_time(self, time):
        '''Converts time in decimal seconds to human-friendly strings.
        format is ddhhmmss.s'''
        if time < 60:
            newtime = [round(time, 1)]
        elif time < 3600:
            m, s = time / 60, time % 60
            newtime = [int(m), round(s, 1)]
        elif time < 86400:
            m, s = time / 60, time % 60
            h, m = m / 60, m % 60
            newtime = [int(h), int(m), round(s, 1)]
        else:
            m, s = time / 60, time % 60
            h, m = m / 60, m % 60
            d, h = h / 24, h % 24
            newtime = [int(d), int(h), int(m), round(s, 1)]
        if len(newtime) == 1:
            timestr = str(newtime[0])+'s'
        elif len(newtime) == 2:
            timestr = str(newtime[0])+'m '+str(newtime[1])+'s'
        elif len(newtime) == 3:
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m ' +
                       str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h ' + 
                       str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr

    def getcolor(self, status):
        if status == 'Rendering':
            color = 'DarkGreen'
            barcolor = '#00E600'
        elif status == 'Waiting':
            color = 'DarkGoldenrod'
            barcolor = '#F5DC00'
        elif status == 'Paused':
            color = 'DarkOrchid'
            barcolor = '#9932CC'
        elif status =='Stopped':
            color = 'FireBrick'
            barcolor = '#F01E1E'
        elif status == 'Finished':
            color = 'DarkGray'
            barcolor = '#646464'
        #barcolor = None
        return (color, barcolor)



class BigBox(_statusbox, ttk.LabelFrame):
    '''Large status box for top of comp panel.'''
    def __init__(self, master=None, index=None):
        self.index = index
        self.font = 'TkDefaultFont'
        ttk.LabelFrame.__init__(self, master=master)
        self._build()

    def _build(self):
        #container is used to control background color
        container = tk.Frame(self)
        container.pack(expand=True, fill=tk.BOTH)
        toprow = tk.Frame(container)
        toprow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(toprow, font=self.font, text='Status:').pack(side=tk.LEFT)
        self.statuslbl = tk.Label(toprow, font=self.font, text='Empty')
        self.statuslbl.pack(side=tk.LEFT)

        self.extraslabel = tk.Label(toprow, font=self.font, text='None', 
                                    wraplength=400)
        self.extraslabel.pack(side=tk.RIGHT)
        tk.Label(toprow, font=self.font, text='Extra frames:').pack(side=tk.RIGHT)
        self.endlabel = tk.Label(toprow, font=self.font, text='1000')
        self.endlabel.pack(side=tk.RIGHT, padx=(0, 30))
        tk.Label(toprow, font=self.font, text='End frame:').pack(side=tk.RIGHT)
        self.startlabel = tk.Label(toprow, font=self.font, text='0000')
        self.startlabel.pack(side=tk.RIGHT, padx=(0, 30))
        tk.Label(toprow, font=self.font, text='Start frame:').pack(side=tk.RIGHT)

        pathrow = tk.Frame(container)
        pathrow.pack(padx=5, anchor=tk.W)
        tk.Label(pathrow, text='Path:').pack(side=tk.LEFT)
        self.pathlabel = tk.Label(pathrow, font=self.font, text='filename')
        self.pathlabel.pack(padx=5, side=tk.LEFT)

        middlerow = tk.Frame(container)
        middlerow.pack(padx=5, expand=True, fill=tk.X)
        self.pbar = tkx.Progressbar(middlerow, length=810, bgcolor='white')
        self.pbar.pack(side=tk.LEFT)
        tk.Label(middlerow, font=self.font, text='%').pack(side=tk.RIGHT)
        self.proglabel = tk.Label(middlerow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.RIGHT)

        bottomrow = tk.Frame(container)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(
            bottomrow, font=self.font, text='Time elapsed:'
            ).pack(side=tk.LEFT)
        self.elapsed_time_lbl = tk.Label(bottomrow, text='')
        self.elapsed_time_lbl.pack(side=tk.LEFT)
        tk.Label(
            bottomrow, text='Avg. time/frame:'
            ).pack(side=tk.LEFT, padx=(220, 0))
        self.avg_time_lbl = tk.Label(bottomrow, text='')
        self.avg_time_lbl.pack(side=tk.LEFT)
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)
        tk.Label(
            bottomrow, font=self.font, text='Time remaining:'
            ).pack(side=tk.RIGHT)

    def update(self, status, startframe, endframe, extraframes, 
               path, progress, times):
        self.status = status
        color, barcolor = self.getcolor(status)
        self.statuslbl.config(text=status, fg=color)
        self.startlabel.config(text=str(startframe))
        self.endlabel.config(text=str(endframe))
        #max length for path is ~90 chars
        if len(path) > 90:
            tkx.Tooltip(self.pathlabel, text=path)
            start = len(path) - 90
            path = '...' + path[start:]
        self.pathlabel.config(text=path)
        if extraframes:
            extraframes.reverse()
            extras = ', '.join(str(i) for i in extraframes)
        else:
            extras = 'None'
        self.extraslabel.config(text=extras)
        self.pbar.set(progress, barcolor)
        self.proglabel.config(text=str(round(progress, 1)))
        elapsed_time = self.format_time(times[0])
        avg_time = self.format_time(times[1])
        time_rem = self.format_time(times[2])
        self.elapsed_time_lbl.config(text=elapsed_time)
        self.avg_time_lbl.config(text=avg_time)
        self.rem_time_lbl.config(text=time_rem)


class SmallBox(_statusbox, tk.Frame):
    '''Small job status box for the left window pane.'''
    def __init__(self, masterwin, master=None, index='0'):
        self.masterwin = masterwin
        self.index = index
        self.status = 'Empty'
        self.queuetime = 0
        self.selected = False
        self.bgcolor = 'white'
        self.font='TkSmallCaptionFont'
        tk.Frame.__init__(self, master=master)
        self._draw()

    def _draw(self):
        '''Creates a small status box for the left window pane.'''
        toprow = tk.Frame(self, bg=self.bgcolor)
        toprow.pack(padx=5, expand=True, fill=tk.X)
        self.namelabel = tk.Label(toprow, font=self.font, text='filename' + ':', 
                                  bg=self.bgcolor)
        self.namelabel.pack(side=tk.LEFT)
        self.statuslbl = tk.Label(toprow, font=self.font, text='Empty', 
                                  bg=self.bgcolor)
        self.statuslbl.pack(side=tk.RIGHT)

        self.pbar = tkx.Progressbar(self, length=250, bgcolor='white')
        self.pbar.pack(padx=5)

        bottomrow = tk.Frame(self, bg=self.bgcolor)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        self.proglabel = tk.Label(bottomrow, font=self.font, text='0.0', 
                                  bg=self.bgcolor)
        self.proglabel.pack(side=tk.LEFT)
        tk.Label(bottomrow, font=self.font, text='% Complete', 
                 bg=self.bgcolor).pack(side=tk.LEFT)
        tk.Label(bottomrow, font=self.font, text='Remaining', 
                 bg=self.bgcolor).pack(side=tk.RIGHT)
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, text='0d0h0m0s', 
                                     bg=self.bgcolor)
        self.rem_time_lbl.pack(side=tk.RIGHT)
        for child in self.winfo_children():
            child.bind('<Button-1>', self.toggle)
            if len(child.winfo_children()) > 0:
                for babby in child.winfo_children():
                    babby.bind('<Button-1>', self.toggle)

    def toggle(self, event=None):
        '''Switches between selected and deselected state.'''
        if not self.selected:
            self.masterwin.select_job(self.index)
        else:
            self.masterwin.deselect_job(self.index)

    def select(self):
        '''Changes background colors to selected state.'''
        self.selected = True
        self._changecolor(HighlightColor)

    def deselect(self):
        '''Changes background colors to deselected state.'''
        self.selected = False
        self._changecolor(self.bgcolor)

    def _changecolor(self, color):
        '''Changes background color to the specified color.'''
        self.config(bg=color)
        for child in self.winfo_children():
            child.config(bg=color)
            if len(child.winfo_children()) > 0:
                for babby in child.winfo_children():
                    babby.config(bg=color)

    def update(self, status, startframe, endframe, path, progress, times, 
               queuetime):
        #info needed for sorting boxes in GUI
        self.status = status
        color, barcolor = self.getcolor(self.status)
        self.queuetime = queuetime
        filename = os.path.basename(path)
        if len(filename) > 25:
            #if filename is too long, trucate label & put whole name in tooltip
            tkx.Tooltip(self.namelabel, text=filename)
            filename = filename[0:25] + '...'
        self.statuslbl.config(text=status, fg=color)
        self.namelabel.config(text=filename)
        self.pbar.set(progress, barcolor)
        self.proglabel.config(text=str(round(progress, 1)))
        time_rem = self.format_time(times[2])
        self.rem_time_lbl.config(text=time_rem)


class CompCube(_statusbox, tk.LabelFrame):
    '''Class representing box to display computer status.'''
    def __init__(self, index, computer, master=None):
        self.index = index
        self.computer = computer
        self.bgcolor = 'white' 
        self.font = 'TkSmallCaptionFont'
        self.progress = tk.IntVar()
        self.pool = tk.IntVar()
        ttk.LabelFrame.__init__(self, master)
        mainblock = tk.Frame(self)
        mainblock.pack(side=tk.LEFT)
        tk.Label(mainblock, text=computer, bg=self.bgcolor).pack(anchor=tk.W)
        ttk.Progressbar(
            mainblock, length=230, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.progress
            ).pack(padx=5, pady=5)
        bottomrow = tk.Frame(mainblock, bg=self.bgcolor)
        bottomrow.pack(expand=True, fill=tk.X)
        tk.Label(
            bottomrow, text='Frame:', font=self.font, bg=self.bgcolor
            ).pack(side=tk.LEFT)
        self.frameno = tk.Label(bottomrow, text='0', font=self.font, 
                                bg=self.bgcolor, fg='black')
        self.frameno.pack(side=tk.LEFT)
        tk.Label(bottomrow, text='% Complete', font=self.font, 
                 bg=self.bgcolor).pack(side=tk.RIGHT)
        self.frameprog = tk.Label(bottomrow, text='0.0', font=self.font, 
                                  bg=self.bgcolor)
        self.frameprog.pack(side=tk.RIGHT) 
        buttonblock = tk.Frame(self)
        buttonblock.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        tk.Checkbutton(
            buttonblock, text='Use', variable=self.pool, 
            command=self._toggle_pool_state
            ).pack()
        tk.Button(buttonblock, text='Kill', command=self._kill_thread).pack()

    def _toggle_pool_state(self):
        '''Adds or removes the computer from the pool.'''
        kwargs = {'index':self.index, 'computer':self.computer}
        reply = ClientSocket().send_cmd('toggle_comp', kwargs)
        print(reply)

    def _kill_thread(self):
        kwargs = {'index':self.index, 'computer':self.computer}
        reply = ClientSocket().send_cmd('kill_single_thread', kwargs)
        print(reply)

    def update(self, frame, progress, pool):
        self.progress.set(progress)
        self.frameno.config(text=str(frame))
        self.frameprog.config(text=str(round(progress, 1)))
        self.pool.set(pool)


class InputWindow(tk.Toplevel):
    '''New window to handle input for new job or edit an existing one.
    If passed optional arguments, these will be used to populate the fields
    in the new window.'''
    def __init__(self, index=None, path=None, start=None, end=None, extras=None, 
                 engine=None, complist=None):
        tk.Toplevel.__init__(self)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.bind('<Return>', self._enqueue)
        self.bind('<KP_Enter>', self._enqueue)
        self.bind('<Escape>', lambda x: self.destroy())
        self.config(bg='gray90')
        self.index = index
        if not self.index:
            path = Config.default_path
            start = Config.default_startframe
            end = Config.default_endframe
            engine = Config.default_render_engine
        #initialize tkinter variables
        self.tk_path = tk.StringVar()
        self.tk_startframe = tk.StringVar()
        self.tk_endframe = tk.StringVar()
        self.tk_extraframes = tk.StringVar()
        self.tk_render_engine = tk.StringVar()
        self.complist = complist
        #populate text fields
        self.tk_path.set(path)
        self.tk_startframe.set(start)
        self.tk_endframe.set(end)
        self.tk_render_engine.set(engine)
        if extras:
            self.tk_extraframes.set(' '.join(str(i) for i in extras))
        container = ttk.LabelFrame(self)
        container.pack(padx=10, pady=10)
        self._build(container)

    def _build(self, master):
        pathrow = ttk.Frame(master)
        pathrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Label(
            pathrow, text='Path:').grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(
            pathrow, textvariable=self.tk_path, width=60
            ).grid(row=1, column=0, sticky=tk.W)
        ttk.Button(
            pathrow, text='Browse', command=self._get_path
            ).grid(row=1, column=1, sticky=tk.W)

        framesrow = ttk.Frame(master)
        framesrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Label(
            framesrow, text='Start frame:'
            ).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(
            framesrow, text='End frame:'
            ).grid(row=0, column=1, padx=5, sticky=tk.W)
        ttk.Label(
            framesrow, text='Extra frames:'
            ).grid(row=0, column=2, padx=5, sticky=tk.W)
        ttk.Entry(
            framesrow, textvariable=self.tk_startframe, width=12
            ).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(
            framesrow, textvariable=self.tk_endframe, width=12
            ).grid(row=1, column=1, padx=5, sticky=tk.W)
        ttk.Entry(
            framesrow, textvariable=self.tk_extraframes, width=40
            ).grid(row=1, column=2, padx=5, sticky=tk.W)

        rengrow = ttk.LabelFrame(master, text='Render Engine')
        rengrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Radiobutton(
            rengrow, variable=self.tk_render_engine, 
            text='Blender', value='blend'
            ).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Radiobutton(
            rengrow, variable=self.tk_render_engine, 
            text='Terragen', value='tgd'
            ).pack(side=tk.LEFT, padx=5, pady=5)

        self.compboxes = ttk.LabelFrame(master, text='Computers')
        self.compboxes.pack(expand=True, fill=tk.X, padx=10, pady=5)
        self._compgrid(self.compboxes)

        buttons = ttk.Frame(master)
        buttons.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Button(buttons, text='OK', command=self._enqueue).pack(side=tk.LEFT)
        ttk.Button(
            buttons, text='Cancel', command=self.destroy
            ).pack(side=tk.LEFT, padx=5)

    def _compgrid(self, master):
        '''Generates grid of computer checkboxes.'''
        #create variables for computer buttons
        self.compvars = {}
        for computer in Config.computers:
            self.compvars[computer] = tk.IntVar()
            self.compvars[computer].set(0)
        if self.complist:
            for comp in self.complist:
                self.compvars[comp].set(1)
        #First row is for select/deselect all buttons
        ttk.Button(
            master, text='Select All', command=self._check_all
            ).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(
            master, text='Deselect All', command=self._uncheck_all
            ).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        #generate a grid with specified number of columns
        self.cols = Config.input_win_cols
        n = 0 #index of computer in computers list
        row = 0 #starting position
        while n < len(Config.computers):
            (x, y) = self._getcoords(n, row)
            ttk.Checkbutton(
                master, text=Config.computers[n], 
                variable=self.compvars[Config.computers[n]]
                ).grid(row=y+1, column=x, padx=5, pady=5, sticky=tk.W)
            n += 1
            if x == self.cols - 1:
                row += 1
            
    def _getcoords(self, n, row):
        '''Returns coordinates (column, row) for complist checkbox.
        n = index of that computer in the list.
        row = current row
        cols = number of columns in layout'''
        x = n - self.cols * row
        y = n - n + row 
        return (x, y)

    def _check_all(self):
        '''Sets all computer buttons to the checked state.'''
        self._uncheck_all()
        for computer in Config.computers:
            self.compvars[computer].set(1)

    def _uncheck_all(self):
        '''Sets all computer buttons to the unchecked state.'''
        for computer in Config.computers:
            self.compvars[computer].set(0)

    def _get_path(self):
        path = tk_filedialog.askopenfilename(title='Open File')
        self.tk_path.set(path)
        
    def _enqueue(self, event=None):
        '''Places a new job in queue.'''
        path = self.tk_path.get()
        #verify that path exists and is accessible from the server
        if not self._path_exists(path):
            Dialog('Path is not accessible from the server.').warn()
            return
        for char in illegal_characters:
            if char in path:
                Dialog('Illegal characters in path.').warn()
                return
        #if this is a new job, create index based on filename
        if not self.index:
            self.index = os.path.basename(path)
            if job_exists(self.index):
                if not Dialog('Job with the same index already exists. '
                              'Overwrite?').yesno():
                    return
                if get_job_status(self.index) == 'Rendering':
                    Dialog("Can't overwrite a job while it's rendering.").warn()
                    return
        startframe = int(self.tk_startframe.get())
        endframe = int(self.tk_endframe.get())
        extras = self.tk_extraframes.get()
        if extras:
            #check if list is comma-delimited
            if ',' in extras:
                extraframes = extras.split(',')
            else:
                extraframes = extras.split()
            #make sure list contains only numbers
            try:
                extraframes = [int(i) for i in extraframes]
            except ValueError:
                Dialog('Extra frames must be integers in a space or '
                       'comma-separated list.').warn()
                return
            #remove any duplicates and any frames inside the start-end range
            extraframes = list(set(extraframes))
            for i in range(startframe, endframe + 1):
                if i in extraframes:
                    extraframes.remove(i)
            print('extraframes:', extraframes) #debug
        else:
            extraframes = []
        render_engine = self.tk_render_engine.get()
        if not path.endswith(render_engine):
            Dialog('Incorrect render engine for file type.').warn()
            return
        complist = []
        for computer in self.compvars:
            if self.compvars[computer].get() == 1:
                complist.append(computer)
        self.destroy()
        render_args = {
            'index':self.index,
            'path':path, 
            'startframe':startframe,
            'endframe':endframe, 
            'extraframes':extraframes, 
            'render_engine':render_engine,
            'complist':complist 
            }
        print('extraframes:', extraframes, type(extraframes))#debug
        reply = ClientSocket().send_cmd('enqueue', render_args)
        print(reply)

    def _path_exists(self, path):
        kwargs = {'path':path}
        reply = ClientSocket().send_cmd('check_path_exists', kwargs)
        return reply


class MissingFramesWindow(tk.Toplevel):
    def __init__(self, renderpath=None, startframe=None, endframe=None):
        tk.Toplevel.__init__(self)
        self.config(bg=LightBGColor)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.bind('<Return>', self._start)
        self.bind('<KP_Enter>', self._start)
        self.bind('<Escape>', lambda x: self.destroy())
        self.renderpath = renderpath
        self.startframe = startframe
        self.endframe = endframe
        self.checkjob = tk.IntVar()
        self.check_path = tk.StringVar()
        self.check_startframe = tk.StringVar()
        self.check_endframe = tk.StringVar()
        self.checked = False
        ttk.Label(
            self, text='Compare the contents of a directory against a '
            'generated file list to search for missing frames.'
            ).pack(padx=15, pady=(10, 0), anchor=tk.W)
        self._build_window()

    def _build_window(self):
        outerframe = ttk.LabelFrame(self)
        outerframe.pack(padx=15, pady=(0, 10))
        ttk.Label(
            outerframe, text='Directory to check:'
            ).grid(row=0, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(
            outerframe, width=50, textvariable=self.check_path
            ).grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        ttk.Button(
            outerframe, text='Browse', command=self._browse_path
            ).grid(row=0, column=3, padx=5, pady=5)
        ttk.Label(
            outerframe, text='Start frame:'
            ).grid(row=1, column=0, sticky=tk.E, padx=5, pady=(20, 5))
        ttk.Entry(
            outerframe, width=20, textvariable=self.check_startframe
            ).grid(row=1, column=1, sticky=tk.W, padx=5, pady=(20, 5))
        ttk.Label(
            outerframe, text='End frame:'
            ).grid(row=2, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(
            outerframe, width=20, textvariable=self.check_endframe
            ).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        sliderframe = ttk.LabelFrame(outerframe, text='Adjust filename parsing')
        sliderframe.grid(row=1, rowspan=3, column=2, columnspan=2, padx=5, 
                         pady=5, sticky=tk.W)
        self.nameleft = tk.Label(sliderframe, bg=LightBGColor)
        self.nameleft.grid(row=0, column=0, sticky=tk.E)
        self.nameseq = tk.Label(sliderframe, bg=LightBGColor)
        self.nameseq.grid(row=0, column=1)
        self.nameright = tk.Label(sliderframe, bg=LightBGColor)
        self.nameright.grid(row=0, column=2, sticky=tk.W)
        self.slider_left = ttk.Scale(
            sliderframe, from_=0, to=100, orient=tk.HORIZONTAL, 
            length=260, command=self._update_sliders
            )
        self.slider_left.grid(row=2, column=0, columnspan=3, padx=5)
        self.slider_right = ttk.Scale(
            sliderframe, from_=0, to=100, orient=tk.HORIZONTAL, 
            length=260, command=self._update_sliders
            )
        self.slider_right.grid(row=3, column=0, columnspan=3, padx=5)
        ttk.Button(
            sliderframe, text='OK', command=self._recheck_directory
            ).grid(row=4, column=1, padx=5, pady=5)

        ttk.Button(
            outerframe, text='Start', command=self._start
            ).grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        outputframe = ttk.LabelFrame(outerframe)
        outputframe.grid(padx=5, pady=5, row=4, column=0, columnspan=4)
        ttk.Label(
            outputframe, text='Directory contents:'
            ).grid(row=0, column=0, sticky=tk.W)
        self.dirconts = tk_st.ScrolledText(outputframe, width=35, height=15)
        self.dirconts.grid(row=1, column=0)
        ttk.Label(outputframe, text='Found:').grid(row=0, column=1, sticky=tk.W)
        self.expFrames = tk_st.ScrolledText(outputframe, width=15, height=15)
        self.expFrames.grid(row=1, column=1)
        ttk.Label(outputframe, text='Expected:').grid(row=0, column=2, sticky=tk.W)
        self.foundFrames = tk_st.ScrolledText(outputframe, width=15, height=15)
        self.foundFrames.grid(row=1, column=2)
        ttk.Label(outputframe, text='Missing:').grid(row=0, column=3, sticky=tk.W)
        self.missingFrames = tk_st.ScrolledText(outputframe, width=15, height=15)
        self.missingFrames.grid(row=1, column=3)
        ttk.Button(
            self, text='Done', command=self.destroy, style='Toolbutton'
            ).pack(padx=15, pady=(0, 15), anchor=tk.W)
        #Insert initial text field values
        self.check_path.set(self.renderpath)
        self.check_startframe.set(self.startframe)
        self.check_endframe.set(self.endframe)

    def _browse_path(self):
        path = tk_filedialog.askdirectory()
        #put original contents back into entry field if user cancels dialog
        if not path:
            path = self.check_path.get()
        #search for a 'render' directory one directory below
        #XXX use pathlib.PurePath to recursively search for render/ dir
        self.check_path.set(path)

    def _start(self, event=None):
        renderpath = self.check_path.get()
        if not renderpath:
            print('no path')#debug
            return
        if not os.path.exists(renderpath):
            print('path does not exist')#debug
            return
        for char in illegal_characters:
            if char in renderpath:
                print('Illegal characters in path')#debug
                return
        try:
            startframe = int(self.check_startframe.get())
            endframe = int(self.check_endframe.get())
        except ValueError:
            print('Start and end frames must be integers')#debug
            return
        self.checker = framechecker.Framechecker(
            renderpath, startframe, endframe,
            allowed_extensions=Config.allowed_filetypes
            )
        self.left, self.right = self.checker.calculate_indices()
        lists = self.checker.generate_lists(self.left, self.right)
        self._put_text(lists)
        self.checked = True
        #change the key bindings so they do the contextually correct thing
        self.bind('<Return>', self._recheck_directory)
        self.bind('<KP_Enter>', self._recheck_directory)

    def _recheck_directory(self, event=None):
        '''If the script didn't parse the filenames correctly, get new indices
        from the sliders the user has used to isolate the sequential numbers.'''
        if not self.checked:
            print('must check before rechecking')#debug
            return
        self.left = int(self.slider_left.get())
        self.right = int(self.slider_right.get())
        lists = self.checker.generate_lists(self.left, self.right)
        self._put_text(lists)

    def _update_sliders(self, event=None):
        '''Changes the text highlighting in the fields above the sliders in
        response to user input.'''
        if not self.checked:
            return
        self.left = int(self.slider_left.get())
        self.right = int(self.slider_right.get())
        self.nameleft.config(text=self.filename[0:self.left], bg=LightBGColor)
        self.nameseq.config(text=self.filename[self.left:self.right], 
                            bg='DodgerBlue')
        self.nameright.config(text=self.filename[self.right:], bg=LightBGColor)

    def _put_text(self, lists):
        '''Populates the scrolled text boxes with relevant data and configures
        the sliders.'''
        self.filename, dir_contents, expected, found, missing = lists
        self.dirconts.delete(0.0, tk.END)
        self.expFrames.delete(0.0, tk.END)
        self.foundFrames.delete(0.0, tk.END)
        self.missingFrames.delete(0.0, tk.END)
        #set up the sliders
        self.slider_left.config(to=len(self.filename))
        self.slider_right.config(to=len(self.filename))
        self.slider_left.set(self.left)
        self.slider_right.set(self.right)
        self.nameleft.config(text=self.filename[0:self.left], bg=LightBGColor)
        self.nameseq.config(text=self.filename[self.left:self.right], 
                            bg='DodgerBlue')
        self.nameright.config(text=self.filename[self.right:], bg=LightBGColor)
        #put text in the scrolled text fields
        for item in dir_contents:
            self.dirconts.insert(tk.END, item + '\n')
        for frame in expected:
            self.expFrames.insert(tk.END, str(frame) + '\n')
        for frame in found:
            self.foundFrames.insert(tk.END, str(frame) + '\n')
        for frame in missing:
            self.missingFrames.insert(tk.END, str(frame) + '\n')

class PrefsWin(tk.Toplevel):
    def __init__(self):
        tk.Toplevel.__init__(self)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.bind('<Return>', self._apply)
        self.bind('<KP_Enter>', self._apply)
        self.bind('<Escape>', lambda x: self.destroy())
        self._get_local_vars()
        #create window elements
        self.nb = ttk.Notebook(self)
        self.nb.pack()
        self.nb.add(self._local_pane(), text='Local Settings', sticky=tk.N)
        self.nb.add(self._server_pane(), text='Server Settings')
        btnbar = ttk.Frame(self)
        btnbar.pack(anchor=tk.W, expand=True, fill=tk.X)
        ttk.Button(
            btnbar, text='Ok', command=self._apply, style='Toolbutton'
            ).pack(side=tk.LEFT, padx=(15, 5), pady=(0, 15))
        ttk.Button(
            btnbar, text='Cancel', command=self.destroy, style='Toolbutton'
            ).pack(side=tk.LEFT, padx=5, pady=(0, 15))
        ttk.Button(
            btnbar, text='Restore Defaults', command=self._restore_defaults, 
            style='Toolbutton'
            ).pack(side=tk.LEFT, padx=5, pady=(0, 15))

    def _get_local_vars(self):
        '''Sets tkinter variables to the current global values.'''
        #initialize tkinter variables
        self.path = tk.StringVar()
        self.startframe = tk.StringVar()
        self.endframe = tk.StringVar()
        self.render_engine = tk.StringVar()
        self.comppanel_cols = tk.IntVar()
        self.input_cols = tk.IntVar()
        self.host = tk.StringVar()
        self.port = tk.StringVar()
        self.refresh_interval = tk.IntVar()
        self.path.set(Config.default_path)
        self.startframe.set(Config.default_startframe)
        self.endframe.set(Config.default_endframe)
        self.render_engine.set(Config.default_render_engine)
        self.input_cols.set(Config.input_win_cols)
        self.comppanel_cols.set(Config.comp_status_panel_cols)
        self.host.set(Config.default_host)
        self.port.set(Config.default_port)
        #convert refresh_interval in sec. to frequency (Hz) for display
        self.refresh_interval.set(1 / Config.refresh_interval)

    def _get_server_vars(self):
        '''Gets current server vars and sets tkinter vars from them.'''
        msg = Config().get_server_cfg()
        if msg:
            print('Failed to get latest server config. Using previous '
                  'values.', msg)
        self.renice = {}
        self.macs = {}
        for comp in Config.computers:
            self.renice[comp] = tk.IntVar()
            if comp in Config.renice_list:
                self.renice[comp].set(1)
            self.macs[comp] = tk.IntVar()
            if comp in Config.macs:
                self.macs[comp].set(1)
        self.blenderpath_mac = tk.StringVar()
        self.blenderpath_linux = tk.StringVar()
        self.terragenpath_mac = tk.StringVar()
        self.terragenpath_linux = tk.StringVar()
        self.allowed_filetypes = tk.StringVar()
        self.timeout = tk.StringVar()
        self.autostart = tk.IntVar()
        self.verbose = tk.IntVar()
        self.log_basepath = tk.StringVar()
        self.serverport = tk.StringVar()

        self.blenderpath_mac.set(Config.blenderpath_mac)
        self.blenderpath_linux.set(Config.blenderpath_linux)
        self.terragenpath_mac.set(Config.terragenpath_mac)
        self.terragenpath_linux.set(Config.terragenpath_linux)
        self.allowed_filetypes.set(Config.allowed_filetypes)
        self.timeout.set(Config.timeout)
        self.serverport.set(Config.serverport)
        #XXX this autostart is runtime-changeable, need DEFAULT
        #maybe just need to pass this to server to update cfgfile without
        #updating runtime state
        self.autostart.set(Config.autostart)
        #XXX same as autostart above
        self.verbose.set(Config.verbose)
        self.log_basepath.set(Config.log_basepath)


    def _local_pane(self):
        '''Pane for local preferences (does not affect server).'''
        #self.lpane = tk.LabelFrame(self.nb, bg=LightBGColor)
        lpane = ttk.Frame(self.nb)
        fr1 = ttk.LabelFrame(lpane, text='Connection Defaults')
        #fr1.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        fr1.grid(row=0, column=0, sticky=tk.NSEW, padx=10, pady=5)
        ttk.Label(fr1, text='Update Frequency'
            ).grid(row=0, column=0, padx=5, pady=5)
        self.freqlabel = ttk.Label(fr1, text=str(self.refresh_interval.get())+' Hz')
        self.freqlabel.grid(row=1, column=0, padx=5, pady=0)
        #self.freqscale = ttk.Scale(
        #    fr1, from_=1, to=10, orient=tk.HORIZONTAL, 
        #    variable=self.refresh_interval
        #    )
        #self.freqscale.grid(row=1, column=0, padx=5, pady=5)
        tkx.MarkedScale(
            fr1, start=1, end=10, variable=self.refresh_interval,
            command=self._freqscale_callback
            ).grid(row=2, column=0, padx=5, pady=5)
        ttk.Separator(fr1, orient=tk.VERTICAL
            ).grid(row=0, rowspan=3, column=1, sticky=tk.NS, padx=20)
        ttk.Label(fr1, text='Host:'
            ).grid(row=0, column=2, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(fr1, width=15, textvariable=self.host
            ).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        ttk.Label(fr1, text='Port:'
            ).grid(row=1, column=2, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(fr1, width=15, textvariable=self.port
            ).grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)

        fr2 = ttk.LabelFrame(lpane, text='New / Edit Job Window Defaults')
        #fr2.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        fr2.grid(row=1, column=0, sticky=tk.NSEW, padx=10, pady=5)
        ttk.Label(fr2, text='Start frame:'
            ).grid(row=0, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(fr2, width=15, textvariable=self.startframe
            ).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(fr2, text='End frame:'
            ).grid(row=1, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(fr2, width=15, textvariable=self.endframe
            ).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(fr2, text='Path:'
            ).grid(row=2, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Entry(fr2, width=30, textvariable=self.path
            ).grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        ttk.Label(fr2, text='Render engine:'
            ).grid(row=3, column=0, sticky=tk.E, padx=5, pady=5)
        ttk.Radiobutton(
            fr2, text='Blender', variable=self.render_engine, value='blend'
            ).grid(row=3, column=1, padx=5, pady=5)
        ttk.Radiobutton(
            fr2, text='Terragen', variable=self.render_engine, value='tgd'
            ).grid(row=3, column=2, sticky=tk.W, padx=5, pady=5)

        fr3 = ttk.LabelFrame(lpane, text='GUI Layout: Columns')
        #fr3.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        fr3.grid(row=0, rowspan=2, column=1, sticky=tk.NSEW, padx=10, pady=5)
        ttk.Label(fr3, text='Main Status Panel'
            ).pack()
        #compcol_scale = ttk.Scale(
        #    fr3, from_=1, to=10, orient=tk.HORIZONTAL, 
        #    variable=self.comppanel_cols
        #    )
        #compcol_scale.grid(row=1, column=0, padx=5, pady=5)
        self.pcolslabel = ttk.Label(fr3, text=str(self.comppanel_cols.get())+' cols')
        self.pcolslabel.pack()
        tkx.MarkedScale(
            fr3, start=1, end=10, variable=self.comppanel_cols,
            command=self._panelcols_scale_callback
            ).pack()
        ttk.Separator(fr3, orient=tk.HORIZONTAL
            ).pack(expand=True, fill=tk.X)
        ttk.Label(fr3, text='New Job Checkboxes'
            ).pack()
        #inputcol_scale = ttk.Scale(
        #    fr3, from_=1, to=10, orient=tk.HORIZONTAL, variable=self.input_cols
        #    )
        #inputcol_scale.grid(row=1, column=2, padx=5, pady=5)
        self.inputcolslabel = ttk.Label(fr3, text=str(self.input_cols.get())+' cols')
        self.inputcolslabel.pack()
        tkx.MarkedScale(
            fr3, start=1, end=10, variable=self.input_cols,
            command=self._inputcols_scale_callback
            ).pack()
        return lpane

    def _freqscale_callback(self, event=None):
        freq = str(self.refresh_interval.get())
        self.freqlabel.config(text=freq+' Hz')

    def _panelcols_scale_callback(self, event=None):
        cols = str(self.comppanel_cols.get())
        self.pcolslabel.config(text=cols+' cols')

    def _inputcols_scale_callback(self, event=None):
        cols = str(self.input_cols.get())
        self.inputcolslabel.config(text=cols+' cols')
        

    def _server_pane(self):
        '''Pane for server-specific preferences.'''
        #self.spane = tk.LabelFrame(self.nb, bg=LightBGColor)
        self._get_server_vars()
        spane = ttk.Frame(self.nb)
        #ttk.Label(spane, text='Server settings').pack()
        self._complist_frame(spane
            ).grid(row=0, rowspan=3, column=0, padx=10, pady=5)
        fr1 = ttk.Frame(spane)
        fr1.grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(fr1, text='Render Timeout'
            ).grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(fr1, width=5, textvariable=self.timeout
            ).grid(row=1, column=0, padx=5, pady=5)
        ttk.Separator(fr1, orient=tk.VERTICAL
            ).grid(row=0, rowspan=2, column=1, sticky=tk.NS, padx=20)
        ttk.Label(
            fr1, text='Default Server Port'
            ).grid(row=0, column=2, padx=5, pady=5)
        ttk.Entry(fr1, width=5, textvariable=self.serverport
            ).grid(row=1, column=2, padx=5, pady=5)

        fr2 = ttk.LabelFrame(spane, text='Server Startup Settings')
        fr2.grid(row=1, column=1, padx=10, pady=5, sticky=tk.EW)
        ttk.Checkbutton(fr2, text='Autostart enabled', variable=self.autostart
            ).grid(row=0, column=0, padx=5, pady=5)
        ttk.Checkbutton(fr2, text='Verbose enabled', variable=self.verbose
            ).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(fr2, text='Render log directory:'
            ).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(fr2, width=30, textvariable=self.log_basepath
            ).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        pathspane = ttk.LabelFrame(spane, text='Render Engine Paths')
        pathspane.grid(row=2, column=1, padx=10, pady=5)
        ttk.Label(pathspane, text='Blender OSX'
            ).grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(pathspane, width=40, textvariable=self.blenderpath_mac
            ).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(pathspane, text='Blender Linux'
            ).grid(row=1, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(pathspane, width=40, textvariable=self.blenderpath_linux
            ).grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(pathspane, text='Terragen OSX'
            ).grid(row=2, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(pathspane, width=40, textvariable=self.terragenpath_mac
            ).grid(row=2, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Label(pathspane, text='Terragen Linux'
            ).grid(row=3, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(pathspane, width=40, textvariable=self.terragenpath_linux
            ).grid(row=3, column=1, padx=5, pady=5, sticky=tk.W)
        return spane

    def _complist_frame(self, master):
        cframe = ttk.LabelFrame(master, text='Computers')
        ttk.Label(cframe, text='Computer').grid(row=0, column=0, sticky=tk.W)
        ttk.Label(cframe, text='OSX').grid(row=0, column=1)
        ttk.Label(cframe, text='Renice').grid(row=0, column=2)
        for i in range(len(Config.computers)):
            ttk.Label(
                cframe, text=Config.computers[i]
                ).grid(row=i+1, column=0, sticky=tk.W, padx=5)
            ttk.Checkbutton(cframe, variable=self.macs[Config.computers[i]]
                ).grid(row=i+1, column=1)
            ttk.Checkbutton(cframe, variable=self.renice[Config.computers[i]]
                ).grid(row=i+1, column=2)

        return cframe

    def _apply(self, event=None):
        print("_apply() called, this doesn't exist yet")
        self.destroy()

    def _restore_defaults(self):
        print("_restore_defaults() called, doesn't exist yet")


class HRule(ttk.Separator):
    '''Preconfigured subclass of ttk.Separator'''
    def __init__(self, master):
        ttk.Separator.__init__(self, master, orient=tk.HORIZONTAL)
        self.pack(padx=40, pady=10, fill=tk.X)


class Dialog(object):
    '''Wrapper for tkMessageBox that displays text passed as message string'''
    def __init__(self, message):
        self.msg = message
    def warn(self):
        '''Displays a box with a single OK button.'''
        tk_msgbox.showwarning('Warning', self.msg)
    def confirm(self):
        '''Displays a box with OK and Cancel buttons. Returns True if OK.'''
        if tk_msgbox.askokcancel('Confirm', self.msg, icon='warning', 
                                 default='ok'):
            return True
        else:
            return False
    def yesno(self):
        '''Displays a box with Yes and No buttons. Returns True if Yes.'''
        if tk_msgbox.askyesno('Confirm', self.msg, icon='info'):
            return True
        else:
            return False
    def yesnocancel(self):
        '''Displays a box with Yes, No, and Cancel buttons. Returns strings
        'yes', 'no', or 'cancel'.'''
        reply = tk_msgbox.askquestion('Confirm', self.msg, icon='info', 
                                      type='yesnocancel')
        return reply


class StatusThread(threading.Thread):
    '''Obtains current status info from all queue slots on server and updates
    GUI accordingly.'''
    stop = False
    def __init__(self, masterwin):
        self.masterwin = masterwin
        threading.Thread.__init__(self, target=self._statusthread)

    def _statusthread(self):
        while True:
            if StatusThread.stop:
                print('stopping statusthread')
                break
            try:
                serverjobs = ClientSocket().send_cmd('get_attrs')
            except Exception as e:
                print('Could not connect to server:', e)
                time.sleep(Config.refresh_interval)
                continue
            try:
                self.masterwin.update(serverjobs)
            except Exception as e:
                print('MasterWin.update() failed:', e.__class__.__name__+':', e)
            #refresh interval in seconds
            time.sleep(Config.refresh_interval)



if __name__ == '__main__':
    masterwin = MasterWin()
    masterwin.mainloop()
