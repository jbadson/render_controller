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
import time
import logging
import threading
import os
import yaml
from . import framechecker
from . import tk_extensions as tkx
from . import socketwrapper as sw


log_file_path = '/var/log/rendercontroller/gui.log'
logger = logging.getLogger('rcontroller.gui')
logger.setLevel(logging.DEBUG)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')
console_formatter = logging.Formatter('%(levelname)s %(name)s: %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')
console.setFormatter(console_formatter)
logger.addHandler(console)


illegal_characters = [';', '&'] #not allowed in path

def quit(event=None):
    '''Terminates status thread and mainloop, then sends exit call.'''
    StatusThread.stop = True
    raise SystemExit


#----------CONFIG VARIABLES----------
cfg_file_required_fields = {
    'host',
    'port',
    'default_path',
    'default_startframe',
    'default_endframe',
    'default_render_engine',
    'input_win_cols',
    'comp_status_panel_cols',
    'refresh_interval',
}

class Config(object):
    '''Represents contents of config file as attributes.'''

    DEFAULT_DIR = "/etc/rendercontroller"
    DEFAULT_FILENAME = 'gui.conf'

    def __init__(self, cfg_path=None):
        '''Args:
        cfg_path -- Path to server config file
        '''
        if cfg_path:
            self.cfg_path = cfg_path
        else:
            self.cfg_path = os.path.join(self.DEFAULT_DIR, self.DEFAULT_FILENAME)
        if not os.path.exists(self.cfg_path):
            raise RuntimeError('Config file not found at {}'.format(self.cfg_path))
        self.load()

    def load(self):
        '''Loads the config file and populates attributes.'''
        with open(self.cfg_path, 'r') as f:
            cfg = yaml.load(f.read())
        missing = cfg_file_required_fields.difference(set(cfg.keys()))
        if missing:
            raise KeyError('Config file missing required fields(s): {}'.format(', '.join(missing)))
        self.from_dict(cfg)

    def from_dict(self, dictionary):
        '''Sets attributes from a dictionary 

        Args:
        dictionary -- Dict to be converted to attrs
        '''
        self.dictionary = dictionary
        for key in dictionary:
            self.__setattr__(key, dictionary[key])

    def get_server_cfg(self):
        '''Gets config info from the server.'''
        try:
            servercfg = sw.ClientSocket(
                self.host, self.port).send_cmd('get_config_vars')
        except:
            logger.exception('Failed to get server config')
            return False
        self.from_dict(servercfg)
        return True



#----------GUI----------

class _gui_(object):
    '''Master class for gui-related objects. Holds methods 
    related to output formatting and other common tasks.'''
    MidBGColor = '#%02x%02x%02x' % (190, 190, 190)
    LightBGColor = '#%02x%02x%02x' % (232, 232, 232)
    HighlightColor = '#%02x%02x%02x' % (74, 139, 222)

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

    def get_job_status(self, index):
        '''Returns the status string for a given job.'''
        status = self.socket.send_cmd('get_status', index)
        return status


class MasterWin(_gui_, tk.Tk):
    '''This is the master class for this module. To create a new GUI,
    create an instance of this class then call the mainloop() method on it.
    Other classes and methods within this module are not intended to be used
    without an instance of MasterWin and will probably break if you try.'''
    def __init__(self):
        tk.Tk.__init__(self)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.title('IGP Render Controller Client')
        self.config(bg=_gui_.LightBGColor)
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
        #initialize local config variables
        try:
            self.cfg = Config() #config properties to be used by all children
        except:
            logger.exception('Error loading config file')
            ttk.Label(self.setupframe, 
                text='Error loading config file. See log for details.').pack()
            return
        #put default values where they go
        self.socket = sw.ClientSocket(self.cfg.host, self.cfg.port)
        self.socket.setup(host=self.cfg.host, port=self.cfg.port)
        #self.statthread = StatusThread(masterwin=self, config=self.cfg, 
        #                               socket=self.socket)
        self.tk_host.set(self.socket.host)
        self.tk_port.set(self.socket.port)
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
        newhost = self.tk_host.get()
        newport = int(self.tk_port.get())
        self.cfg.host = newhost
        self.cfg.port = newport
        self.socket.setup(newhost, newport)
        #get the server config variables
        if not self.cfg.get_server_cfg():
            self.server_errlabel = ttk.Label(self, text='Server connection failed')
            self.server_errlabel.pack()
            return
        # If a server error msg was set on prev. run, remove it
        if hasattr(self, 'server_errlabel'):
            self.server_errlabel.destroy()
        self.verbosity = tk.IntVar()
        self.verbosity.set(self.cfg.verbose)
        self.autostart = tk.IntVar()
        self.autostart.set(self.cfg.autostart)
        self.setupframe.destroy()
        self._build_main()
        self.statthread = StatusThread(
            masterwin=self, config=self.cfg, host=newhost, port=newport
            )
        self.statthread.start()
        self.unbind('<Return>')
        self.unbind('<KP_Enter>')

    def _build_main(self):
        '''Creates the main window elements.'''
        topbar = tk.Frame(self, bg=_gui_.MidBGColor)
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
            topbar, text='Kill Processes', command=self.killall,
            style='Toolbutton'
            ).pack(padx=5, side=tk.LEFT)
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        midblock = tk.Frame(self, bg=_gui_.LightBGColor)
        midblock.pack(padx=15, pady=(10, 20), expand=True, fill=tk.BOTH)
        
        left_frame = tk.Frame(midblock, bg=_gui_.LightBGColor)
        left_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        tk.Label(
            left_frame, text='Queue:', bg=_gui_.LightBGColor
            ).pack(padx=5, anchor=tk.W)
        left_frame_inner = tk.LabelFrame(left_frame, bg=_gui_.LightBGColor)
        left_frame_inner.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        
        self.jobbox_frame = tk.Frame(left_frame_inner, width=260)
        self.jobbox_frame.pack(expand=True, fill=tk.BOTH)
        jobbtns = tk.Frame(left_frame_inner, bg=_gui_.LightBGColor)
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
        _extra_info = serverjobs['__STATEVARS__']
        self.verbosity.set(_extra_info['verbose'])
        self.autostart.set(_extra_info['autostart'])
        del serverjobs['__STATEVARS__']
        #retrieve and display and messages from the server
        msg = serverjobs['__MESSAGE__']
        del serverjobs['__MESSAGE__']
        if msg:
            Dialog(msg).info()
        #create local job instances for any new jobs on server
        for index in serverjobs:
            if not index in self.jobboxes:
                self._create_job(index)
        #delete any local jobs that are no longer on the server
        dellist = []
        for index in self.jobboxes:
            if not index in serverjobs:
                #can't directly delete here b/c dict length will change,
                #raising an exception
                dellist.append(index)
        for index in dellist:
            self._remove_job(index)
        #now update GUI elements
        for index in serverjobs:
            attrdict = serverjobs[index]
            #update job box
            self.jobboxes[index].update(
                attrdict['status'], attrdict['startframe'], 
                attrdict['endframe'], attrdict['path'], attrdict['progress'], 
                attrdict['times'], attrdict['queuetime']
                )
            #update comp panel
            self.comppanels[index].update(attrdict)
        #attempt re-sorting job boxes
        self.sort_jobboxes()
        #XXX testing for prog bars
        #this does seem to fix the issue of lagging updates
        #self.update_idletasks()


    def _new_job(self):
        '''Opens an instance of InputWindow to create a new job on the 
        server. GUI elements are not created directly by this function. 
        They are created by self.update() when called by the status thread 
        to ensure that the GUI state is only changed if the server state was 
        successfully changed.'''
        newjob = InputWindow(config=self.cfg, socket=self.socket)

    def _delete_job(self):
        '''Deletes the selected job from the server. GUI elements are not 
        removed directly by this function. They are deleted by self.update() 
        when called by the status thread to ensure that the GUI state is 
        only changed if the server state was successfully changed.'''
        nojobs = True
        for index in self.jobboxes:
            if self.jobboxes[index].selected:
                nojobs = False
                break
        if nojobs: #do nothing if no job is selected
            return
        if self.get_job_status(index) == 'Rendering':
            Dialog("Can't delete a job while it's rendering.").warn()
            return
        if not Dialog('Delete ' + index + ' from the queue?').confirm():
            return
        reply = self.socket.send_cmd('clear_job', index)
        print(reply)

    def _create_job(self, index):
        '''Creates GUI elements for a given index.'''
        #create job box
        self.jobboxes[index] = SmallBox(
            masterwin=self, master=self.jobbox_frame, index=index
            )
        self.jobboxes[index].pack()
        #let sort_jobboxes pack everything in the correct place
        #put box in list (at top for now)
        self.boxlist.insert(0, self.jobboxes[index])
        #create comp panel
        self.comppanels[index] = ComputerPanel(
            master=self.right_frame, index=index, config=self.cfg,
            socket=self.socket)

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
        '''Sort job boxes chronologically and by status.'''
        #XXX Doing this a bit more simply.  Move finished jobs to bottom,
        #otherwise ignore status and sort from oldest to newest
        finishedjobs = []
        otherjobs = []
        for i in self.jobboxes:
            if self.jobboxes[i].status == 'Finished':
                finishedjobs.append(self.jobboxes[i])
            else:
                otherjobs.append(self.jobboxes[i])
        if len(finishedjobs) > 1:
            finishedjobs = self.sort_chrono(finishedjobs)
        if len(otherjobs) > 1:
            otherjobs = self.sort_chrono(otherjobs)
        boxlist = otherjobs + finishedjobs
        #do not update if nothing has changed
        if boxlist == self.boxlist:
            return
        else:
            self.boxlist = boxlist
        for i in self.jobboxes:
            self.jobboxes[i].pack_forget()
        for box in boxlist:
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
        #newlist.reverse()
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
                    self.cfg, job['path'], job['startframe'], job['endframe']
                    )
                return
        self.checkwin = MissingFramesWindow(self.cfg)

    def _toggle_verbose(self):
        '''Toggles verbose reporting state on the server.'''
        reply = self.socket.send_cmd('toggle_verbose')
        print(reply)

    def _toggle_autostart(self):
        '''Toggles the autostart state on the server.'''
        reply = self.socket.send_cmd('toggle_autostart')
        print(reply)

    def killall(self):
        '''Creates instance of KillProcWindow to kill render processes
        on specified computers.'''
        KillProcWindow(self.socket, self.cfg)
    

class ComputerPanel(_gui_, ttk.Frame):
    '''Main job info panel with computer boxes.'''
    def __init__(self, master, index, config, socket):
        '''config is Config instance from parent.
        socket is ClientSocket instance from parent'''
        self.index = index
        self.cfg = config
        #self.socket = sw.ClientSocket(self.cfg.host, self.cfg.port)
        self.socket = socket
        ttk.Frame.__init__(self, master=master)
        #Create the main job status box at the top of the panel
        self.bigbox = BigBox(master=self, index=self.index)
        self.bigbox.pack(expand=True, fill=tk.X, padx=5)
        #Create job control buttons
        buttonbox = ttk.Frame(self)
        buttonbox.pack(anchor=tk.W, expand=True, fill=tk.X, padx=5, pady=5)
        ttk.Button(buttonbox, text='Edit', command=self._edit
            ).pack(side=tk.LEFT)
        ttk.Button(buttonbox, text='Start', command=self._start
            ).pack(side=tk.LEFT)
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
        self.cols = self.cfg.comp_status_panel_cols
        n = 0 #index of computer in computers list
        row = 0 #starting position
        while n < len(self.cfg.rendernodes):
            (x, y) = self._getcoords(n, row)
            self.compcubes[self.cfg.rendernodes[n]] = CompCube(
                socket=self.socket, master=self.compframe, 
                computer=self.cfg.rendernodes[n], index=self.index
                )
            self.compcubes[self.cfg.rendernodes[n]].grid(row=y, column=x, padx=5)
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
        attrs = self.socket.send_cmd('get_attrs', self.index)
        denystatuses = ['Rendering', 'Stopped', 'Paused']
        if attrs['status'] in denystatuses:
            Dialog('Job cannot be edited.').warn()
            return
        paths = attrs['path']
        editjob = InputWindow(
            config=self.cfg, socket=self.socket, index=self.index, 
            paths=paths, start=attrs['startframe'], 
            end=attrs['endframe'], extras=attrs['extraframes'], 
            complist=attrs['complist']
            )

    def _start(self):
        '''Starts the render.'''
        if not self.get_job_status(self.index) == 'Waiting':
            Dialog('Cannot start render unless status is "Waiting"').warn()
            return
        reply = self.socket.send_cmd('start_render', self.index)
        print(reply)

    def _kill_render(self):
        '''Kill the current render.'''
        if self.get_job_status(self.index) != 'Rendering':
            Dialog('Cannot stop a render unless its status is "Rendering"'
                ).warn()
            return
        confirm = Dialog('Stopping render. Allow currently rendering frames '
                         'to finish?').yesnocancel()
        if confirm == 'cancel':
            return
        elif confirm == 'yes':
            kill_now = False
        elif confirm == 'no':
            kill_now = True
        reply = self.socket.send_cmd('kill_render', self.index, kill_now)
        print(reply)

    def _resume_render(self):
        resumestatuses = ['Stopped', 'Paused']
        if self.get_job_status(self.index) not in resumestatuses:
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
        reply = self.socket.send_cmd('resume_render', self.index, startnow)
        print(reply)

    def _set_priority(self, value='Normal'):
        print('value:', value)
        print('self.tk_priority', self.tk_priority.get())
        reply = self.socket.send_cmd('set_job_priority', self.index, value)
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
        for computer in self.cfg.rendernodes:
            if computer in attrdict['complist']:
                pool = True
            else:
                pool = False
            compstatus = attrdict['compstatus'][computer]
            self.compcubes[computer].update(
                compstatus['frame'], compstatus['progress'], pool,
                compstatus['active'], compstatus['error'])



class BigBox(_gui_, ttk.LabelFrame):
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
        tk.Label(toprow, font=self.font, text='Extra frames:'
            ).pack(side=tk.RIGHT)
        self.endlabel = tk.Label(toprow, font=self.font, text='1000')
        self.endlabel.pack(side=tk.RIGHT, padx=(0, 30))
        tk.Label(toprow, font=self.font, text='End frame:').pack(side=tk.RIGHT)
        self.startlabel = tk.Label(toprow, font=self.font, text='0000')
        self.startlabel.pack(side=tk.RIGHT, padx=(0, 30))
        tk.Label(toprow, font=self.font, text='Start frame:'
            ).pack(side=tk.RIGHT)

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
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, 
                                     text='0d0h0m0s')
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


class SmallBox(_gui_, tk.Frame):
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
        self.namelabel = tk.Label(
            toprow, font=self.font, text='filename:', bg=self.bgcolor
            )
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
        self.rem_time_lbl = tk.Label(
            bottomrow, font=self.font, text='0d0h0m0s', bg=self.bgcolor
            )
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
        self._changecolor(_gui_.HighlightColor)

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


class CompCube(_gui_, ttk.LabelFrame):
    '''Class representing box to display computer status.'''
    def __init__(self, socket, index, computer, master=None):
        self.index = index
        self.socket = socket
        self.computer = computer
        #self.bgcolor = 'white' 
        #change color to white when frame assigned
        self.bgcolor = _gui_.LightBGColor 
        self.font = 'TkSmallCaptionFont'
        self.progress = tk.IntVar()
        self.pool = tk.IntVar()
        ttk.LabelFrame.__init__(self, master)
        mainblock = tk.Frame(self, bg=self.bgcolor)
        mainblock.pack(expand=True, fill=tk.X)
        leftblock = tk.Frame(mainblock, bg=self.bgcolor)
        leftblock.pack(side=tk.LEFT)
        tk.Label(leftblock, text=computer, bg=self.bgcolor).pack(anchor=tk.W)
        ttk.Progressbar(
            leftblock, length=230, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.progress
            ).pack(padx=5, pady=5)
        bottomrow = tk.Frame(leftblock, bg=self.bgcolor)
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
        buttonblock = tk.Frame(mainblock, bg=self.bgcolor)
        buttonblock.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        tk.Checkbutton(
            buttonblock, text='Use', variable=self.pool, 
            command=self._toggle_pool_state, bg=self.bgcolor,
            ).pack()
        tk.Button(buttonblock, text='Kill', command=self._kill_thread,
                  highlightbackground=self.bgcolor, highlightthickness=0
                  ).pack()
        errblock = tk.Frame(self, bg=self.bgcolor)
        errblock.pack(expand=True, fill=tk.X)
        tk.Label(errblock, text='Status:', font=self.font).pack(side=tk.LEFT)
        self.statlabel = tk.Label(errblock, text='', font=self.font)
        self.statlabel.pack(side=tk.LEFT)
        tk.Label(errblock, text='     Last error:', font=self.font
            ).pack(side=tk.LEFT)
        self.errlabel = tk.Label(errblock, text='None', font=self.font)
        self.errlabel.pack(side=tk.LEFT)

    def _toggle_pool_state(self):
        '''Adds or removes the computer from the pool.'''
        reply = self.socket.send_cmd('toggle_comp', self.index, self.computer)
        print(reply)

    def _kill_thread(self):
        reply = self.socket.send_cmd('kill_single_thread', self.index, 
                                     self.computer)
        print(reply)

    def _change_bgcolor(self, bgcolor):
        if bgcolor == self.bgcolor:
            #don't try to change colors if status hasn't changed
            return
        self.bgcolor = bgcolor
        for child in self.winfo_children():
            child.config(bg=bgcolor)
            for babby in child.winfo_children():
                try:
                    babby.config(bg=bgcolor, highlightbackground=bgcolor)
                #progressbar will throw exception because it lacks bg option
                except:
                    print('caught exception in CompCube._change_bgcolor, '
                          'ignoring.')
                    continue
                for subbabby in babby.winfo_children():
                    subbabby.config(bg=bgcolor)
        #self.frameno.config(bg=bgcolor)
        #self.frameprog.config(bg=bgcolor)

    def update(self, frame, progress, pool, active, error):
        if active:
            #self._change_bgcolor('white')
            self.statlabel.config(text='Active')
        else:
            #self._change_bgcolor(_gui_.LightBGColor)
            #Job._thread_failed() leaves frame assigned while status inactive
            if frame:
                self.statlabel.config(text='FAILED')
            else:
                self.statlabel.config(text='Inactive')
        self.progress.set(progress)
        self.frameno.config(text=str(frame))
        self.frameprog.config(text=str(round(progress, 1)))
        self.pool.set(pool)
        if error:
            self.errlabel.config(text=error)


class InputWindow(_gui_, tk.Toplevel):
    '''New window to handle input for new job or edit an existing one.
    If passed optional arguments, these will be used to populate the fields
    in the new window.
    '''
    def __init__(
            self, config, socket, index=None, paths=None, 
            start=None, end=None, extras=None, complist=None
            ):
        '''config is Config instance belonginng to parent'''
        tk.Toplevel.__init__(self)
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.bind('<Escape>', lambda x: self.destroy())
        self.config(bg='gray90')
        self.index = index
        self.cfg = config
        self.socket = socket
        if not self.index:
            start = self.cfg.default_startframe
            end = self.cfg.default_endframe
        #if resuming a job, create instance variables
        #self.socket = sw.ClientSocket(self.cfg.host, self.cfg.port)
        #initialize tkinter variables
        #self.tk_path = tk.StringVar()
        self.tk_startframe = tk.StringVar()
        self.tk_endframe = tk.StringVar()
        self.tk_extraframes = tk.StringVar()
        self.complist = complist
        #populate text fields
        #self.tk_path.set(path)
        self.tk_startframe.set(start)
        self.tk_endframe.set(end)
        if extras:
            self.tk_extraframes.set(' '.join(str(i) for i in extras))
        container = ttk.LabelFrame(self)
        container.pack(padx=10, pady=10)
        self._build(container, paths)

    def _build(self, master, paths):
        self.rows = [] #list to hold row objects for sorting
        self.pathrow = PathBlock(master, self.cfg)
        self.pathrow.set_path(paths)
        self.rows.append(self.pathrow)

        framesrow = ttk.Frame(master)
        self.rows.append(framesrow)
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

        self.compboxes = ttk.LabelFrame(master, text='Nodes')
        self.rows.append(self.compboxes)
        self._compgrid(self.compboxes)

        buttons = ttk.Frame(master)
        self.rows.append(buttons)
        ttk.Button(buttons, text='OK', command=self._process_inputs
            ).pack(side=tk.LEFT)
        ttk.Button(
            buttons, text='Cancel', command=self.destroy
            ).pack(side=tk.LEFT, padx=5)
        for row in self.rows:
            row.pack(expand=True, fill=tk.X, padx=10, pady=5)

    def _compgrid(self, master):
        '''Generates grid of computer checkboxes.'''
        #create variables for computer buttons
        self.compvars = {}
        for computer in self.cfg.rendernodes:
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
        self.cols = self.cfg.input_win_cols
        n = 0 #index of computer in computers list
        row = 0 #starting position
        while n < len(self.cfg.rendernodes):
            (x, y) = self._getcoords(n, row)
            ttk.Checkbutton(
                master, text=self.cfg.rendernodes[n], 
                variable=self.compvars[self.cfg.rendernodes[n]]
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
        for computer in self.cfg.rendernodes:
            self.compvars[computer].set(1)

    def _uncheck_all(self):
        '''Sets all computer buttons to the unchecked state.'''
        for computer in self.cfg.rendernodes:
            self.compvars[computer].set(0)

    def _process_inputs(self, event=None):
        try:
            startframe = int(self.tk_startframe.get())
            endframe = int(self.tk_endframe.get())
        except ValueError:
            Dialog('Frame numbers must be integers.').warn()
            return
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
        complist = []
        for computer in self.compvars:
            if self.compvars[computer].get() == 1:
                complist.append(computer)
        self._process_path(startframe, endframe, extraframes, complist)    
    
    def _process_path(self, startframe, endframe, extraframes, 
                             complist):
        path = self.pathrow.get_path()
        #verify that path exists and is accessible from the server
        if not self.path_exists(path):
            Dialog('Path is not accessible from the server.').warn()
            return
        if not self.path_legal(path):
            Dialog('Illegal characters in path.').warn()
            return
        #if this is a new job, create index based on filename
        if not self.index:
            self.index = os.path.basename(path)
            if self.job_exists(self.index):
                if not Dialog('Job with the same index already exists. '
                              'Overwrite?').yesno():
                    return
                if self.get_job_status(self.index) == 'Rendering':
                    Dialog("Can't overwrite a job while it's rendering."
                           ).warn()
                    return
        #set the render enging based on the file suffix
        if path.endswith('blend'):
            render_engine = 'blend'
        elif path.endswith('tgd'):
            render_engine = 'tgd'
        else:
            Dialog('File extension not recognized. Project file must end with '
                   '".blend" for Blender or ".tgd" for Terragen files.').warn()
            return
        self._enqueue(path, startframe, endframe, extraframes, render_engine,
                      complist)
    
    
    def _enqueue(self, path, startframe, endframe, extraframes, render_engine, 
                 complist):
        render_args = {
            'index':self.index,
            'path':path, 
            'startframe':startframe,
            'endframe':endframe, 
            'extraframes':extraframes, 
            'render_engine':render_engine,
            'complist':complist,
            }
        reply = self.socket.send_cmd('enqueue', render_args)
        print(reply)
        self.destroy()

    def job_exists(self, index):
        '''Returns true if index is in use on server.'''
        reply = self.socket.send_cmd('job_exists', index)
        return reply

    def path_legal(self, path):
        '''Returns False if there are illegal characters in path.  Otherwise
        returns True.'''
        for char in illegal_characters:
            if char in path:
                return False
        return True

    def path_exists(self, path):
        reply = self.socket.send_cmd('check_path_exists', path)
        return reply

class PathBlock(ttk.Frame):
    '''Path input UI elements.'''
    def __init__(self, master, config):
        ttk.Frame.__init__(self, master=master)
        self.cfg = config
        self._path = None #indicates no path was set by parent
        self.tk_path = tk.StringVar()
        ttk.Label(
            self, text='Path:').grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(
            self, textvariable=self.tk_path, width=60
            ).grid(row=1, column=0, sticky=tk.W)
        ttk.Button(
            self, text='Browse', command=self._browse_path
            ).grid(row=1, column=1, sticky=tk.W)

    def _browse_path(self):
        oldpath = self.tk_path.get()
        if self._path:
            path = tk_filedialog.askopenfilename(
                title='Open File', initialdir=os.path.dirname(self._path)
                )
        else:
            path = tk_filedialog.askopenfilename(title='Open File')
        #if user clicks cancel, put the old path back in the input field
        if not path:
            path = oldpath
        else:
            self._path = path
        self.tk_path.set(path)

    def set_path(self, path):
        if path:
            #only want to set this value if a NEW path is being specified
            self._path = path
        else:
            path = self.cfg.default_path
        self.tk_path.set(path)

    def get_path(self):
        '''Returns contents of path field.'''
        return self.tk_path.get()


    def _browse_rootdir(self):
        rootdir = tk_filedialog.askdirectory(title='Project Root Directory')
        self.tk_rootpath.set(rootdir)

    def _browse_filepath(self):
        rootdir = self.tk_rootpath.get()
        if rootdir:
            filepath = tk_filedialog.askopenfilename(title='Open File', 
                                                     initialdir=rootdir)
            filepath = os.path.relpath(filepath, start=rootdir)
        else:
            filepath = tk_filedialog.askopenfilename(title='Open File')
        self.tk_filepath.set(filepath)

    def _browse_renderdir(self):
        rootdir = self.tk_rootpath.get()
        if rootdir:
            renderdir = tk_filedialog.askdirectory(
                title='Rendered Frames Directory', initialdir=rootdir
                )
            renderdir = os.path.relpath(renderdir, start=rootdir)
        else:
            renderdir = tk_filedialog.askdirectory(
                title='Rendered Frames Directory'
                )
        self.tk_renderdirpath.set(renderdir)

    def set_paths(self, rootdir, filepath, renderdir):
        if rootdir:
            self.tk_rootpath.set(rootdir)
            self.tk_filepath.set(filepath)
            self.tk_renderdirpath.set(renderdir)
        else: #don't want to put 'None' string in text fields
            return

    def get_paths(self):
        '''Returns absolute path to project root directory and relative paths
        to blendfile and rendered frames directory.'''
        rootdir = self.tk_rootpath.get()
        filepath = self.tk_filepath.get()
        renderdir = self.tk_renderdirpath.get()
        #make sure filepath & renderdir are relative paths
        if os.path.isabs(filepath) or os.path.isabs(renderdir):
            return 1
        #make sure they're in the root project directory
        if filepath.startswith('..') or renderdir.startswith('..'):
            return 2
        return (rootdir, filepath, renderdir)



class KillProcWindow(tk.Toplevel):
    '''Interface for sending kill process commands to nodes.'''
    def __init__(self, socket, config):
        tk.Toplevel.__init__(self)
        self.config(bg=_gui_.LightBGColor)
        self.socket = socket
        self.cfg = config
        self.bind('<Command-q>', quit) 
        self.bind('<Control-q>', quit)
        self.bind('<Return>', self._killall)
        self.bind('<KP_Enter>', self._killall)
        self.bind('<Escape>', lambda x: self.destroy())
        self.process = tk.StringVar() # Tk variable to hold process name
        self.process.set('blender')
        ttk.Label(
            self, text='Attempt to kill all instances of the specified program '
            'on the following computers.'
            ).pack(padx=15, pady=(10, 0), anchor=tk.W)
        self._build_window()

    def _build_window(self):
        outerframe = ttk.LabelFrame(self)
        outerframe.pack(padx=15, pady=(0, 10))
        progframe = ttk.LabelFrame(outerframe, text='Program')
        progframe.pack(padx=15, pady=(0, 10), expand=True, fill=tk.X)
        ttk.Radiobutton(
            progframe, text='Blender', variable=self.process, value='blender'
            ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            progframe, text='Terragen', variable=self.process, value='terragen'
            ).pack(side=tk.LEFT)
        compframe = ttk.LabelFrame(outerframe, text='Nodes')
        compframe.pack(padx=10, pady=(0, 10), expand=True, fill=tk.X)
        self._compgrid(compframe)
        buttonframe = ttk.Frame(self)
        buttonframe.pack(
            padx=15, pady=(0, 15), anchor=tk.W, expand=True, fill=tk.X
            )
        ttk.Button(
            buttonframe, text='Kill all processes', style='Toolbutton', 
            command=self._killall
            ).pack(padx=0, pady=0, side=tk.LEFT)
        ttk.Button(
            buttonframe, text='Cancel', command=self.destroy, style='Toolbutton'
            ).pack(padx=10, pady=0, side=tk.LEFT)

    def _compgrid(self, master):
        '''Generates grid of computer checkboxes.'''
        #create variables for computer buttons
        self.compvars = {}
        for computer in self.cfg.rendernodes:
            self.compvars[computer] = tk.IntVar()
            self.compvars[computer].set(0)
        #First row is for select/deselect all buttons
        ttk.Button(
            master, text='Select All', command=self._check_all
            ).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(
            master, text='Deselect All', command=self._uncheck_all
            ).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        #generate a grid with specified number of columns
        self.cols = self.cfg.input_win_cols
        n = 0 #index of computer in computers list
        row = 0 #starting position
        while n < len(self.cfg.rendernodes):
            (x, y) = self._getcoords(n, row)
            ttk.Checkbutton(
                master, text=self.cfg.rendernodes[n], 
                variable=self.compvars[self.cfg.rendernodes[n]]
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
        for computer in self.cfg.rendernodes:
            self.compvars[computer].set(1)

    def _uncheck_all(self):
        '''Sets all computer buttons to the unchecked state.'''
        for computer in self.cfg.rendernodes:
            self.compvars[computer].set(0)

    def _killall(self, callback=None):
        '''Sends the kill all command to the server'''
        complist = []
        for comp in self.cfg.rendernodes:
            if self.compvars[comp].get() == 1:
                complist.append(comp)
        procname = self.process.get()
        print('procname: ', procname)
        if not Dialog('Kill all instances of %s on %s?' 
            %(procname, ', '.join(complist))).confirm():
            return
        else:
            reply = self.socket.send_cmd('killall', complist, procname)
        print(reply)
        self.destroy()



class MissingFramesWindow(tk.Toplevel):
    '''UI for utility to check for missing frames within a specified start-end
    range in a given directory.'''
    def __init__(self, config, renderpath='', startframe='', 
                 endframe=''):
        tk.Toplevel.__init__(self)
        self.config(bg=_gui_.LightBGColor)
        self.cfg = config
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
        ttk.Label(outputframe, text='Expected:'
            ).grid(row=0, column=1, sticky=tk.W)
        self.expFrames = tk_st.ScrolledText(outputframe, width=15, height=15)
        self.expFrames.grid(row=1, column=1)
        ttk.Label(outputframe, text='Found:'
            ).grid(row=0, column=2, sticky=tk.W)
        self.foundFrames = tk_st.ScrolledText(outputframe, width=15, height=15)
        self.foundFrames.grid(row=1, column=2)
        ttk.Label(outputframe, text='Missing:'
            ).grid(row=0, column=3, sticky=tk.W)
        self.missingFrames = tk_st.ScrolledText(outputframe, width=15, 
                                                height=15)
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
            allowed_extensions=self.cfg.allowed_filetypes
            )
        self.left, self.right = self.checker.calculate_indices()
        lists = self.checker.generate_lists()
        self._put_text(lists)

    def _put_text(self, lists):
        '''Populates the scrolled text boxes with relevant data.'''
        self.filename, dir_contents, expected, found, missing = lists
        self.dirconts.delete(0.0, tk.END)
        self.expFrames.delete(0.0, tk.END)
        self.foundFrames.delete(0.0, tk.END)
        self.missingFrames.delete(0.0, tk.END)
        #put text in the scrolled text fields
        for item in dir_contents:
            self.dirconts.insert(tk.END, item + '\n')
        for frame in expected:
            self.expFrames.insert(tk.END, str(frame) + '\n')
        for frame in found:
            self.foundFrames.insert(tk.END, str(frame) + '\n')
        for frame in missing:
            self.missingFrames.insert(tk.END, str(frame) + '\n')





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
        if tk_msgbox.askyesno('Confirm', self.msg, icon='question'):
            return True
        else:
            return False
    def yesnocancel(self):
        '''Displays a box with Yes, No, and Cancel buttons. Returns strings
        'yes', 'no', or 'cancel'.'''
        reply = tk_msgbox.askquestion('Confirm', self.msg, icon='info', 
                                      type='yesnocancel')
        return reply
    def info(self):
        '''Displays a box with just an OK button.'''
        tk_msgbox.showinfo('Alert', self.msg, icon='info')


class StatusThread(threading.Thread):
    '''Obtains current status info from all queue slots on server and updates
    GUI accordingly.'''
    stop = False
    def __init__(self, masterwin, config, host, port):
        '''masterwin = parent instance of MasterWin
        config = instance of Config from parent''' 
        self.masterwin = masterwin
        self.cfg = config
        #Must have its own instance of ClientSocket to prevent
        #asynchronous calls to socket.close().
        self.socket = sw.ClientSocket(host, port)
        threading.Thread.__init__(self, target=self._statusthread)

    def _statusthread(self):
        while True:
            if StatusThread.stop:
                print('stopping statusthread')
                break
            try:
                serverjobs = self.socket.send_cmd('get_attrs')
            except Exception as e:
                print('Could not connect to server:', e)
                time.sleep(self.cfg.refresh_interval)
                continue
            try:
                self.masterwin.update(serverjobs)
            except Exception as e:
                print('MasterWin.updat() failed: %s:%s' 
                      %(e.__class__.__name__, e))
            #refresh interval in seconds
            time.sleep(self.cfg.refresh_interval)



def main():
    try:
        logfile = logging.FileHandler(log_file_path)
        logfile.setLevel(logging.INFO)
        logfile.setFormatter(file_formatter)
        logger.addHandler(logfile)
    except PermissionError:
        print('WARNING Permissions error writing log file at {}. '\
              'Will log to console only.'.format(log_file_path))
    masterwin = MasterWin()
    masterwin.mainloop()


if __name__ == '__main__':
    main()
