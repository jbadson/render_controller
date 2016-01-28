
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.filedialog as tk_filedialog
import tkinter.messagebox as tk_msgbox
import tkinter.scrolledtext as tk_st
import time
import threading
import traceback
import os.path
import cfgfile
import framechecker
import tk_extensions as tkx
import projcache
import socketwrapper as sw


illegal_characters = [';', '&'] #not allowed in path



### Variables that need defining from server
refresh_interval = 1
debug = True # Print detailed exception info to stdout

def handle_exception(exception, message=None):
    """If debugging is enabled, prints exception and traceback information to stdout.
    If a message is passed as an arg, prints that too. Returns silently if debug is false.
    Keyword args:
    message -- Optional message to be printed with the exception info. (str)"""
    if not debug:
        return
    else:
        print('Exception: %s' %exception)
        if message:
            print(message)
        traceback.print_tb(exception.__traceback__)
        print("Exception handled in exception_msg")
        del exception


def quit(event=None):
    """Attempts to make the GUI exit immediately by stopping the status thread."""



class StatusThread(threading.Thread):
    """Obtains information about the state of the server and uses it to update GUI elements.
    Keyword args:
    masterwin -- Instance of MasterWin that will receive updates.
    """
    self.stop = False
    def __init__(self, masterwin):
        self.socket = sw.ClientSocket(host, port)
        threading.Thread.__init-_(self, target=self._statusthread)

    def stop(self):
        """Shuts down the status thread."""
        self.stop = True

    def _statusthread(self):
        while True:
            if self.stop:
                print('stopping statusthread')
                break
            try:
                serverjobs = self.socket.send_cmd('get_attrs')
                self.masterwin.update(serverjobs)
            except Exception as e:
                exception_msg(e)
            time.sleep(refresh_interval)


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
        return (color, barcolor)

    def get_job_status(self, index):
        '''Returns the status string for a given job.'''
        status = self.socket.send_cmd('get_status', index)
        return status


class MasterWin(_gui_, tk.Tk):
    """Subclass of tkinter.Tk. This is the parent of all other GUI objects."""
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
        self.tk_username = tk.StringVar()
        self.tk_host = tk.StringVar()
        self.tk_port = tk.StringVar()
        #initialize local config variables
        self.cfg = Config() #config properties to be used by all children
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
            ).grid(row=4, column=0, columnspan=2, padx=10, pady=10)
        self.bind('<Return>', self._apply_setup)
        self.bind('<KP_Enter>', self._apply_setup)

    def _apply_setup(self, event=None):
        '''Apply server config info then build the main window.'''
        print('setup done') #debug
        #configure host and port class attributes
        global host,port
        newhost = self.tk_host.get()
        newport = int(self.tk_port.get())
        self.cfg.host = newhost
        self.cfg.port = newport
        self.socket.setup(newhost, newport)
        #get the server config variables
        msg = self.cfg.get_server_cfg()
        if msg:
            print('Could not retrieve config vars form server:', msg)
            ttk.Label(
                self, text='Server connection failed: ' + str(msg)
                ).pack()
            return
        self.verbosity = tk.IntVar()
        self.verbosity.set(self.cfg.verbose)
        self.autostart = tk.IntVar()
        self.autostart.set(self.cfg.autostart)
        self.username = self.tk_username.get()
        self.setupframe.destroy()
        self._build_main()
        self.statthread = StatusThread(
            masterwin=self, config=self.cfg, host=newhost, port=newport
            )
        self.statthread.start()
        self.unbind('<Return>')
        self.unbind('<KP_Enter>')
