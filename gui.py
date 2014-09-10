#graphical user interface for IGP Render Controller
#Written for Python 3.4
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

host = 'localhost'
port = 2020


class ClientSocket(object):
    '''Wrapper for socket to handle command-response protocol for interacting with
    the render controller server.'''

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))

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
        if not command == 'get_all_attrs': print('sending command', command) #debug
        self._sendmsg(command)
        #check that the command was valid
        cmd_ok = ast.literal_eval(self._recvall())
        if not cmd_ok:
            return 'Invalid command'
        #if command was valid, send associated arguments
        if not command == 'get_all_attrs': print('sending kwargs', str(kwargs))
        self._sendmsg(kwargs)
        #collect the return string (True/False for success/fail or requested data)
        return_str = self._recvall()
        if not command == 'get_all_attrs': print('received return_str', return_str)
        self.socket.close()
        return return_str
        


def cmdtest():
    '''a basic test of client server command-response protocol'''
    command = 'cmdtest'
    kwargs = {'1':'one', '2':'two'}
    return_str = ClientSocket().send_cmd(command, kwargs)
    print(return_str)

def check_slot_open(index):
    '''Returns true if queue slot is open.'''
    command = 'check_slot_open'
    kwargs = {'index':index}
    check = ClientSocket().send_cmd(command, kwargs)
    if check == 'True':
        return True
    else:
        return False

def get_job_status(index):
    '''Returns the status string for a given job.'''
    kwargs = {'index':index}
    status = ClientSocket().send_cmd('get_status', kwargs)
    return status

def get_config_vars():
    '''Gets current values for global config variables from server.'''
    cfgvars = ClientSocket().send_cmd('get_config_vars')
    return cfgvars

def quit():
    '''Terminates status thread and mainloop, then sends exit call.'''
    statthread.end()
    #masterwin.destroy()
    raise SystemExit




#----------CONFIG VARIABLES----------
#client-specific config settings
#these do not affect the server
gui_cfg = cfgfile.ConfigFile(filename='gui_config.json')
print('GUI config file: ' + str(gui_cfg.filepath()))

def set_gui_defaults():
    '''Restores GUI config file variables to default values. Also use for creating
    the initial config file.'''
    #default values for fields in the input window
    default_path = '/mnt/data/test_render/test_render.blend'
    default_startframe = 1
    default_endframe = 4
    default_render_engine = 'blender'
    return (default_path, default_startframe, default_endframe, 
            default_render_engine)

if not gui_cfg.exists():
    print('No GUI config file found, creating one from defaults.')
    guisettings = gui_cfg.write(set_gui_defaults())
else:
    print('GUI config file found, reading...')
    try:
        guisettings = gui_cfg.read()
        if not len(guisettings) == len(set_gui_defaults()):
            raise IndexError
    except:
        print('GUI config file corrupt or incorrect. Creating new')
        guisettings = gui_cfg.write(set_gui_defaults())

#server-specific config variables    
#most of these aren't directly used by the GUI, but are needed for the prefs window
computers, fast, farm, renice_list, macs, maxqueuelength, blenderpath_mac, blenderpath_linux, terragenpath_mac, terragenpath_linux, allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, log_basepath = get_config_vars()


#XXX Some additional config stuff, decide where to put it later
#XXX Get rid of LightBlueBGColor if you're not going to use it.
LightBlueBGColor = 'white'
MidBGColor = '#%02x%02x%02x' % (190, 190, 190)
LightBGColor = '#%02x%02x%02x' % (232, 232, 232)
#DarkBGColor = '#%02x%02x%02x' % (50, 50, 50)
HighlightColor = '#%02x%02x%02x' % (74, 139, 222)




#----------GUI----------

class MasterWin(tk.Tk):
    def __init__(self):
        tk.Tk.__init__(self)
        self.bind('<Command-q>', lambda x: quit()) 
        self.bind('<Control-q>', lambda x: quit())
        self.config(bg=LightBGColor)
        self.geometry('1257x720')
        #create dictionaries to hold job-specific GUI elements
        #format is { 'index' : object }
        self.jobboxes = {}
        self.comppanels = {}
        self._build_main()

    def _build_main(self):
        '''Creates the main window elements.'''
        topbar = tk.Frame(self, bg=MidBGColor)
        topbar.pack(fill=tk.BOTH)
        ttk.Button(topbar, text='Check Missing Frames', command=self._checkframes, 
            style='Toolbutton').pack(padx=(25, 5), pady=15, side=tk.LEFT)
        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X)

        midblock = tk.Frame(self, bg=LightBGColor)
        midblock.pack(padx=15, pady=(10, 20), expand=True, fill=tk.BOTH)
        
        left_frame = tk.Frame(midblock, bg=LightBGColor)
        left_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        tk.Label(left_frame, text='Queue:', bg=LightBGColor).pack(padx=5, 
            anchor=tk.W)
        left_frame_inner = tk.LabelFrame(left_frame, bg=LightBGColor)
        left_frame_inner.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
        
        self.jobbox_frame = tk.Frame(left_frame_inner, bg=LightBlueBGColor, 
            width=260)
        self.jobbox_frame.pack(expand=True, fill=tk.BOTH)
        jobbtns = tk.Frame(left_frame_inner, bg=LightBGColor)
        jobbtns.pack(fill=tk.X)
        ttk.Separator(jobbtns).pack(fill=tk.X)
        RectButton(jobbtns, text='+', command=self._new_job).pack(side=tk.LEFT)
        RectButton(jobbtns, text='-', command=self._delete_job).pack(side=tk.LEFT)
        
        self.right_frame = ttk.LabelFrame(midblock, width=921)
        self.right_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.BOTH)
        
        
        #footer = tk.Frame(self, bg=LightBGColor)
        #footer.pack(fill=tk.BOTH)
        #tk.Label(footer, text='', bg=LightBGColor).pack()

    def update(self, serverjobs):
        '''Takes dict containing all server job info and updates 
        children based on that.'''
        for index in serverjobs:
            if not index in self.jobboxes:
                self._create_job(index)
                print('Created new job object at ', index)
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
            self.jobboxes[index].update(attrdict['status'], attrdict['startframe'], 
                attrdict['endframe'], attrdict['path'], attrdict['progress'], 
                attrdict['times'])
            #update comp panel
            self.comppanels[index].update(attrdict)

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
        #XXX Need safety checking here
        for index in self.jobboxes:
            if self.jobboxes[index].selected == True:
                break
        kwargs = {'index':index}
        reply = ClientSocket().send_cmd('clear_job', kwargs)
        print(reply)

    def _create_job(self, index):
        '''Creates GUI elements for a given index.'''
        #create job box
        self.jobboxes[index] = SmallBox(master=self.jobbox_frame, 
            index=index)
        #create comp panel
        self.comppanels[index] = ComputerPanel(master=self.right_frame, 
            index=index)
        #select the most recently added job
        #XXX This might be annoying or worse if another client adds a job while
        #you're editing. Probably should have a different way of doing this.
        #self.select_job(index)

    def _remove_job(self, index):
        '''Permanently removes GUI elements for a given index.'''
        #delete job box
        self.jobboxes[index].destroy()
        del self.jobboxes[index]
        #delete comp panel
        self.comppanels[index].destroy()
        del self.comppanels[index]

    def select_job(self, index):
        for i in self.jobboxes:
            if not i == index and self.jobboxes[i].selected == True:
                self.deselect_job(i)
        self.jobboxes[index].select()
        self.comppanels[index].pack(padx=10, pady=10)

    def deselect_job(self, index):
        self.jobboxes[index].deselect()
        self.comppanels[index].pack_forget()

    def _checkframes(self):
        '''Opens check missing frames window.'''
        self.checkwin = MissingFramesWindow()


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
        ttk.Button(buttonbox, text='Stop', command=self._kill_render).pack(
            side=tk.LEFT)
        ttk.Button(buttonbox, text='Resume', command=self._resume_render).pack(
            side=tk.LEFT)
        #now create the main array of computer boxes
        self._create_computer_array()

    def _create_computer_array(self):
        self.compframe = ttk.Frame(self)
        self.compframe.pack()
        self.compcubes = {}
        #changing the number of cols should automatically generate the rest
        #of the layout correctly. Put this in GUI config?
        cols = 3
        rows = len(computers) // cols
        #extra rows are needed if the number of computers isn't evenly divisible
        #by the number of columns
        extra_rows = len(computers) % cols
        end = len(computers)
        i = 0
        for col in range(0, cols):
            for row in range(0, rows + extra_rows):
                self.compcubes[computers[i]] = CompCube(master=self.compframe,
                    computer=computers[i], index=self.index)
                self.compcubes[computers[i]].grid(row=row, column=col, padx=5)
                i += 1
                if i == end: break

    def _edit(self):
        '''Edits job information.'''
        status = get_job_status(self.index)
        if status == 'Rendering' or status == 'Stopped':
            Dialog('Cannot edit job while it is rendering or stopped.').warn()
            return
        editjob = InputWindow(self.index)

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
        if Dialog('Allow currently rendering frames to finish?').yesno():
            kill_now = False
        else:
            kill_now = True
        kwargs = {'index':self.index, 'kill_now':kill_now}
        reply = ClientSocket().send_cmd('kill_render', kwargs)
        print(reply)

    def _resume_render(self):
        if get_job_status(self.index) != 'Stopped':
            Dialog('Cannot resume a render unless its status is "Stopped"').warn()
            return
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('resume_render', kwargs)
        print(reply)

    def update(self, attrdict):
        '''Calls the update methods for all child elements.'''
        self.bigbox.update(attrdict['status'], attrdict['startframe'], 
            attrdict['endframe'], attrdict['path'], attrdict['progress'], 
            attrdict['times'])
        for computer in computers:
            compstatus = attrdict['compstatus'][computer]
            self.compcubes[computer].update(compstatus['frame'], 
                compstatus['progress'], compstatus['pool'])


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
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m '
                +str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h '
                +str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr


class BigBox(_statusbox, ttk.LabelFrame):
    '''Large status box for top of comp panel.'''
    def __init__(self, master=None, index=None):
        self.index = index
        self.progress = tk.IntVar()
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

        self.extraslabel = tk.Label(toprow, font=self.font, text='None')
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
        self.pathlabel = tk.Label(pathrow, font=self.font, 
            text='filename')
        self.pathlabel.pack(padx=5, side=tk.LEFT)

        middlerow = tk.Frame(container)
        middlerow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Progressbar(middlerow, length=810, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(side=tk.LEFT)
        tk.Label(middlerow, font=self.font, text='%').pack(side=tk.RIGHT)
        self.proglabel = tk.Label(middlerow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.RIGHT)

        bottomrow = tk.Frame(container)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(bottomrow, font=self.font, text='Time elapsed:').pack(side=tk.LEFT)
        self.elapsed_time_lbl = tk.Label(bottomrow, text='')
        self.elapsed_time_lbl.pack(side=tk.LEFT)
        tk.Label(bottomrow, text='Avg. time/frame:').pack(side=tk.LEFT, padx=(220, 
            0))
        self.avg_time_lbl = tk.Label(bottomrow, text='')
        self.avg_time_lbl.pack(side=tk.LEFT)
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)
        tk.Label(bottomrow, font=self.font, text='Time remaining:').pack(
            side=tk.RIGHT)

    def update(self, status, startframe, endframe, path, progress, times):
        self.statuslbl.config(text=status)
        self.startlabel.config(text=str(startframe))
        self.endlabel.config(text=str(endframe))
        self.pathlabel.config(text=path)
        self.progress.set(progress)
        self.proglabel.config(text=str(round(progress, 1)))
        elapsed_time = self.format_time(times[0])
        avg_time = self.format_time(times[1])
        time_rem = self.format_time(times[2])
        self.elapsed_time_lbl.config(text=elapsed_time)
        self.avg_time_lbl.config(text=avg_time)
        self.rem_time_lbl.config(text=time_rem)


class SmallBox(_statusbox, tk.Frame):
    '''Small job status box for the left window pane.'''
    def __init__(self, master=None, index='0'):
        self.index = index
        self.selected = False
        self.bgcolor = 'white'
        self.progress = tk.IntVar()
        self.font='TkSmallCaptionFont'
        tk.Frame.__init__(self, master=master)
        self.pack()
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

        ttk.Progressbar(self, length=250, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(padx=5)

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
            masterwin.select_job(self.index)
        else:
            masterwin.deselect_job(self.index)

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
            try:
                child.config(bg=color)
            #XXX progress bar will throw an exception, so ignoring it
            except:
                pass
            if len(child.winfo_children()) > 0:
                for babby in child.winfo_children():
                    babby.config(bg=color)

    def update(self, status, startframe, endframe, path, progress, times):
        filename = os.path.basename(path)
        self.statuslbl.config(text=status)
        self.namelabel.config(text=filename)
        self.progress.set(progress)
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
        ttk.Progressbar(mainblock, length=230, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.progress).pack(padx=5, pady=5)
        bottomrow = tk.Frame(mainblock, bg=self.bgcolor)
        bottomrow.pack(expand=True, fill=tk.X)
        tk.Label(bottomrow, text='Frame:', font=self.font, bg=self.bgcolor).pack(
            side=tk.LEFT)
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
        tk.Checkbutton(buttonblock, text='Use', variable=self.pool, 
            command=self._toggle_pool_state).pack()
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

class RectButton(tk.Frame):
    '''Subclass of tkinter Frame that looks and behaves like a rectangular 
    button.'''
    bgcolor = '#%02x%02x%02x' % (235, 235, 235)
    highlight = '#%02x%02x%02x' % (74, 139, 222)

    def __init__(self, master, text='Button', command=None, bg=bgcolor):
        RectButton.bgcolor = bg
        self.command = command
        tk.LabelFrame.__init__(self, master, borderwidth=1, relief=tk.GROOVE, 
            bg=RectButton.bgcolor)
        self.lbl = tk.Label(self, text=text, bg=RectButton.bgcolor)
        self.lbl.pack(expand=True, fill=tk.BOTH, padx=3)
        self.bind('<Button-1>', self._select)
        self.lbl.bind('<Button-1>', self._select)
        self.bind('<ButtonRelease-1>', self._execute)
        self.lbl.bind('<ButtonRelease-1>', self._execute)
        self.bind('<Leave>', self._deselect)
        self.lbl.bind('<Leave>', self._deselect)

    def _select(self, event=None):
        '''Changes the background color to the highlight color'''
        self.selected = True
        self.config(bg=RectButton.highlight)
        self.lbl.config(bg=RectButton.highlight)
        self.update_idletasks()

    def _deselect(self, event=None):
        self.selected = False
        self.config(bg=RectButton.bgcolor)
        self.lbl.config(bg=RectButton.bgcolor)
        return

    def _execute(self, event=None):
        '''Returns the button bgcolor to it's original state.'''
        if self.command and self.selected == True:
            self.command()
        self._deselect()


class InputWindow(tk.Toplevel):
    '''New window to handle input for new job or edit an existing one.'''
    def __init__(self, index=None):
        self.index = index
        self.tk_path = tk.StringVar()
        self.tk_startframe = tk.StringVar()
        self.tk_endframe = tk.StringVar()
        self.tk_extraframes = tk.StringVar()
        self.tk_render_engine = tk.StringVar()
        self.tk_complist = tk.StringVar()
        #put in default values
        self.tk_path.set(guisettings[0])
        self.tk_startframe.set(guisettings[1])
        self.tk_endframe.set(guisettings[2])
        self.tk_render_engine.set(guisettings[3])
        tk.Toplevel.__init__(self)
        self.config(bg='gray90')
        container = ttk.LabelFrame(self)
        container.pack(padx=10, pady=10)
        self._build(container)

    def _build(self, master):
        pathrow = ttk.Frame(master)
        pathrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Label(pathrow, text='Path:').grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(pathrow, textvariable=self.tk_path, width=60).grid(row=1, 
            column=0, sticky=tk.W)
        ttk.Button(pathrow, text='Browse', command=self._get_path).grid(row=1, 
            column=1, sticky=tk.W)

        framesrow = ttk.Frame(master)
        framesrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Label(framesrow, text='Start frame:').grid(row=0, column=0, 
            sticky=tk.W)
        ttk.Label(framesrow, text='End frame:').grid(row=0, column=1, padx=5,
            sticky=tk.W)
        ttk.Label(framesrow, text='Extra frames:').grid(row=0, column=2, padx=5,
            sticky=tk.W)
        ttk.Entry(framesrow, textvariable=self.tk_startframe, width=12).grid(row=1, 
            column=0, sticky=tk.W)
        ttk.Entry(framesrow, textvariable=self.tk_endframe, width=12).grid(row=1, 
            column=1, padx=5, sticky=tk.W)
        ttk.Entry(framesrow, textvariable=self.tk_extraframes, width=40).grid(row=1,
            column=2, padx=5, sticky=tk.W)

        rengrow = ttk.LabelFrame(master, text='Render Engine')
        rengrow.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Radiobutton(rengrow, variable=self.tk_render_engine, 
            text='Blender', value='blender').pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Radiobutton(rengrow, variable=self.tk_render_engine, 
            text='Terragen', value='terragen').pack(side=tk.LEFT, padx=5, pady=5)

        self.compboxes = ttk.LabelFrame(master, text='Computers')
        self.compboxes.pack(expand=True, fill=tk.X, padx=10, pady=5)
        self._compgrid(self.compboxes)

        buttons = ttk.Frame(master)
        buttons.pack(expand=True, fill=tk.X, padx=10, pady=5)
        ttk.Button(buttons, text='OK', command=self._enqueue).pack(side=tk.LEFT)
        ttk.Button(buttons, text='Cancel', command=self.destroy).pack(side=tk.LEFT, 
            padx=5)

    def _compgrid(self, master):
        '''Generates grid of computer checkboxes.'''
        #create variables for computer buttons
        self.compvars = {}
        for computer in computers:
            self.compvars[computer] = tk.IntVar()
            self.compvars[computer].set(0)
        #First row is for select/deselect all buttons
        ttk.Button(master, text='Select All', command=self._check_all).grid(row=0, 
            column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Button(master, text='Deselect All', command=self._uncheck_all).grid( 
            row=0, column=1, padx=5, pady=5, sticky=tk.W)
        #generate a grid with specified number of columns
        cols = 5
        rows = len(computers) // cols
        i = 0
        for row in range(1, rows + 2):
            for col in range(0, cols):
                print('compgrid', computers[i], row, col)
                ttk.Checkbutton(master, text=computers[i], 
                    variable=self.compvars[computers[i]]).grid(row=row, column=col,
                    padx=5, pady=5, sticky=tk.W)
                i += 1
                if i == len(computers): break

    def _check_all(self):
        '''Sets all computer buttons to the checked state.'''
        self._uncheck_all()
        for computer in computers:
            self.compvars[computer].set(1)

    def _uncheck_all(self):
        '''Sets all computer buttons to the unchecked state.'''
        for computer in computers:
            self.compvars[computer].set(0)

    def _get_path(self):
        path = tk_filedialog.askopenfilename(title='Open File')
        self.tk_path.set(path)
        
    def _enqueue(self):
        '''Places a new job in queue.'''
        if not check_slot_open(self.index):
            if not Dialog('Overwrite existing queue contents?').yesno():
                self.destroy()
                return
        path = self.tk_path.get()
        #if this is a new job, create index based on filename
        if not self.index:
            self.index = os.path.basename(path)
        startframe = int(self.tk_startframe.get())
        endframe = int(self.tk_endframe.get())
        extraframes = []
        if self.tk_extraframes.get() != '':
            extraframes = self.tk_extraframes.get().split(',')
        render_engine = self.tk_render_engine.get()
        complist = []
        for computer in self.compvars:
            if self.compvars[computer].get() == 1:
                complist.append(computer)
        self.destroy()
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('create_job', kwargs)
        if not reply:
            print('Failed to create job.')
            return
        render_args = { 'index':self.index,
                        'path':path, 
                        'startframe':startframe,
                        'endframe':endframe, 
                        'extraframes':extraframes, 
                        'render_engine':render_engine,
                        'complist':complist }
        reply = ClientSocket().send_cmd('enqueue', render_args)
        print(reply)


class MissingFramesWindow(tk.Toplevel):
    def __init__(self):
        tk.Toplevel.__init__(self)
        #self.chkf = checkframes.CheckFrames(allowed_extensions=allowed_filetypes)
        self.checkjob = tk.IntVar()
        self.check_path = tk.StringVar()
        self.check_startframe = tk.StringVar()
        self.check_endframe = tk.StringVar()
        self.checked = False
        self._build_window()

    def _build_window(self):
        outerframe = tk.Frame(self)
        outerframe.pack(padx=10, pady=10)
        
        jobButtonBlock = tk.Frame(outerframe)
        jobButtonBlock.pack()
        
        tk.Label(jobButtonBlock, text='Existing Job:').pack(side=tk.LEFT)
        #ttk.Radiobutton(jobButtonBlock, text='None', variable=self.checkjob, 
        #    value=0, command=lambda: select_job(0)).pack(side=tk.LEFT)
        #ttk.Radiobutton(jobButtonBlock, text='1', variable=self.checkjob, value=1, 
        #    command=lambda: select_job(1)).pack(side=tk.LEFT)
        
        tk.Label(outerframe, text='Directory to check:').pack()
        tk.Entry(outerframe, width=50, textvariable=self.check_path).pack()
        
        tk.Label(outerframe, text='Start frame:').pack()
        tk.Entry(outerframe, width=20, textvariable=self.check_startframe).pack()
        
        tk.Label(outerframe, text='End frame:').pack()
        tk.Entry(outerframe, width=20, textvariable=self.check_endframe).pack()
        
        nameleft = tk.Label(outerframe)
        nameleft.pack()
        nameseq = tk.Label(outerframe)
        nameseq.pack()
        nameright = tk.Label(outerframe)
        nameright.pack()
        
        self.slider_left = ttk.Scale(outerframe, from_=0, to=100, orient=tk.HORIZONTAL, 
            length=300, command=self._update_sliders)
        self.slider_left.pack()
        self.slider_right = ttk.Scale(outerframe, from_=0, to=100, orient=tk.HORIZONTAL, 
            length=300, command=self._update_sliders)
        self.slider_right.pack()
        
        ttk.Button(outerframe, text='OK', command=self._recheck_directory).pack()
        
        outputframe = tk.LabelFrame(outerframe)
        outputframe.pack(padx=5, pady=5)
        
        dirconts = tk_st.ScrolledText(outputframe, width=20, height=5)
        dirconts.pack(side=tk.LEFT)
        
        expFrames = tk_st.ScrolledText(outputframe, width=20, height=5)
        expFrames.pack(side=tk.LEFT)
        
        foundFrames = tk_st.ScrolledText(outputframe, width=20, height=5)
        foundFrames.pack(side=tk.LEFT)
        
        missingFrames = tk_st.ScrolledText(outputframe, width=20, height=5)
        missingFrames.pack(side=tk.LEFT)
        
        ttk.Button(outerframe, text='Start', command=self._start).pack()

        #XXX some temp settings
        self.check_path.set('/Users/igp/test_render/render/')
        self.check_startframe.set('1')
        self.check_endframe.set('15')

    def _start(self):
        renderpath = self.check_path.get()
        if not renderpath:
            print('no path')#debug
            return
        if not os.path.exists(renderpath):
            print('path does not exist')#debug
            return
        try:
            startframe = int(self.check_startframe.get())
            endframe = int(self.check_endframe.get())
        except ValueError:
            print('Start and end frames must be integers')#debug
            return
        #XXX Need to format allowed_filetypes correctly, then pass those along too.
        self.checker = framechecker.Framechecker(renderpath, startframe, endframe)
        left, right = self.checker.calculate_indices()
        lists = self.checker.generate_lists(left, right)
        self._put_text(lists)
        self.checked = True
        

    def _recheck_directory(self):
        '''If the script didn't parse the filenames correctly, get new indices
        from the sliders the user has used to isolate the sequential numbers.'''
        if not self.checked:
            print('must check before rechecking')#debug
            return
        left = int(self.slider_left.get())
        right = int(self.slider_right.get())
        lists = self.checker.generate_lists(left, right)
        self._put_text(lists)

    def _update_sliders(self):
        pass

    def _put_text(self, lists):
        print(lists)


class HRule(ttk.Separator):
    '''Preconfigured subclass of ttk.Separator'''
    def __init__(self, master):
        ttk.Separator.__init__(self, master, orient=tk.HORIZONTAL)
        self.pack(padx=40, pady=10, fill=tk.X)


class StatusThread(threading.Thread):
    '''Obtains current status info from all queue slots on server and updates
    GUI accordingly.'''
    def __init__(self):
        self.stop = False
        threading.Thread.__init__(self, target=self._statusthread)

    def end(self):
        '''Terminates the status thread cleanly.'''
        self.stop = True

    def _statusthread(self):
        while True:
            if self.stop == True:
                break
            serverjobs = ClientSocket().send_cmd('get_all_attrs')
            masterwin.update(serverjobs)
            #refresh interval in seconds
            time.sleep(0.5)



if __name__ == '__main__':
    masterwin = MasterWin()
    statthread = StatusThread()
    statthread.start()
    masterwin.mainloop()
