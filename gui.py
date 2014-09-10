#graphical user interface for IGP Render Controller
#must run in python 3
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.filedialog as tk_filedialog
import tkinter.messagebox as tk_msgbox
import socket
import time
import threading
import os.path
import ast
import json
import cfgfile

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




#----------GUI----------
#----Initialize GUI----
root = tk.Tk()
#root.geometry('800x500')
root.bind('<Command-q>', lambda x: quit()) 
root.bind('<Control-q>', lambda x: quit())

localjobs = {} #dict to hold all instances of JobObject currently in the GUI

#---GUI Classes---
class StatusThread(threading.Thread):
    '''Obtains current status info from all queue slots on server and updates
    GUI accordingly.'''
    def __init__(self):
        self.stop = False
        threading.Thread.__init__(self, target=self._statusthread)
        self.localjobs = {} #dict to hold instances of JobObject

    def end(self):
        '''Terminates the status thread cleanly.'''
        self.stop = True

    def _statusthread(self):
        while True:
            global localjobs
            if self.stop == True:
                break
            attrdict = ClientSocket().send_cmd('get_all_attrs')
            serverjobs = []
            for index in attrdict:
                serverjobs.append(index)
                if not index in localjobs:
                    localjobs[index] = JobObject(index)
                    print('Adding job to localjobs', index)
            #delete any local jobs that are no longer on server
            dellist = []
            for index in localjobs:
                if not index in serverjobs:
                    dellist.append(index)
            for index in dellist:
                localjobs[index].delete()
                del localjobs[index]
            #now do updates
            for index in attrdict:
                localjobs[index].update(attrdict[index])
            #update frequency in seconds
            time.sleep(0.5)



class Dialog(object):
    '''Wrapper for tkMessageBox that displays text passed as message string'''
    def __init__(self, message):
        self.msg = message
    def warn(self):
        '''Displays a box with a single OK button.'''
        tk_msgbox.showwarning('Warning', self.msg)
    def confirm(self):
        '''Displays a box with OK and Cancel buttons. Returns True if OK.'''
        if tk_msgbox.askokcancel('Confirm', self.msg, icon='warning'):
            return True
        else:
            return False
    def yesno(self):
        '''Displays a box with Yes and No buttons. Returns True if Yes.'''
        if tk_msgbox.askyesno('Confirm', self.msg, icon='info'):
            return True
        else:
            return False

#
#class StatusTab(tk.LabelFrame):
#
#    def __init__(self, index, master=None):
#        tk.LabelFrame.__init__(self, master, bg='gray90')
#        #self.pack()
#
#        '''need the following info for each box:
#            computer
#            frame
#            progress %
#            in/out of pool'''
#
#        #internal index needed for sending job-specific commands
#        self.index = index
#        #dict of tk variables for progress bars
#        self.compdata = {}
#        #dict to hold tk.Label objects for frame number and % complete
#        #for ease of reference later
#        self.frameno = {}
#        self.frameprog = {}
#        self.jobstat = JobStatusBox(self.index, master=self)
#        self.jobstat.draw_bigbox()
#        buttonbar = ttk.Frame(self)
#        buttonbar.pack(padx=5, pady=5, expand=True, fill=tk.X)
#        ttk.Button(buttonbar, text='Edit', command=self._input).pack( \
#            side=tk.LEFT)
#        ttk.Button(buttonbar, text='Start', command=self._start).pack(side=tk.LEFT)
#        ttk.Button(buttonbar, text='Stop', command=self._kill_render).pack( \
#            side=tk.LEFT)
#        ttk.Button(buttonbar, text='Resume', command=self._resume_render).pack( \
#            side=tk.LEFT)
#        #ttk.Button(buttonbar, text='Remove', command=self._clear_job).pack( \
#        #XXX Testing way to dynamically create/remove queue items
#        ttk.Button(buttonbar, text='Remove', command=lambda: delete_job(self.index)).pack( \
#
#            side=tk.RIGHT)
#        #encapsulate computer boxes in canvas to make it scrollable
#        #canvframe = ttk.LabelFrame(self)
#        #canvframe.pack(expand=True, fill=tk.BOTH)
#        #determine height of canvas based on number of computer boxes to be rendered
#        #canvheight = len(computers) * 70
#        #self.canv = tk.Canvas(canvframe, height=canvheight, 
#        #    scrollregion=(0,0,450,canvheight))
#        #self.scrollbar = ttk.Scrollbar(canvframe, orient=tk.VERTICAL)
#        #self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
#        #self.scrollbar.config(command=self.canv.yview)
#        #self.canv.config(yscrollcommand=self.scrollbar.set)
#
#
#
#        self.compframe = tk.Frame(self)
#        self.compframe.pack(expand=True, fill=tk.BOTH)
#        #for computer in computers:
#        #    self.compdata[computer] = {} 
#        #    self.compdata[computer]['frame'] = tk.IntVar(0)
#        #    self.compdata[computer]['progress'] = tk.IntVar(0)
#        #    self.compdata[computer]['pool'] = tk.IntVar(0)
#        #    self.frameno[computer] = None
#        #    self.frameprog[computer] = None
#        cols = 2
#        rows = len(computers) // cols
#        i = 0
#        end = len(computers) - 10
#        for row in range(0, rows):
#            print(row)
#            for col in range(0, cols):
#                print(col)
                #CompCube(master=self, computer=computers[i]).grid(row=row, column=col)
#                tk.Label(self, text=computers[i]).grid(row=row, column=col)
#                i += 1
#                if i == end: break
#
#
#
#            #self._comp_status_box(self.compframe, computers[i])
#        #self.canv.create_window(0, 0, window=self.compframe, anchor=tk.NW)
#        #self.canv.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
#
#    def _input(self):
#        self.inputwin = InputWindow(self.index)
#
#    def _start(self):
#        '''Starts the render.'''
#        if not get_job_status(self.index) == 'Waiting':
#            Dialog('Cannot start render unless status is "Waiting"').warn()
#            return
#        kwargs = {'index':self.index}
#        reply = ClientSocket().send_cmd('start_render', kwargs)
#        print(reply)
#
#    def _comp_status_box(self, master, computer):
#        '''Render progress/status box for a given computer.'''
#        compbox = tk.LabelFrame(master, bg='gray90')
#        compbox.pack(padx=5, pady=5, expand=True, fill=tk.X)
#        leftblock = ttk.Frame(compbox)
#        leftblock.pack(side=tk.LEFT)
#
#        toprow = ttk.Frame(leftblock)
#        toprow.pack(fill=tk.X, padx=5, pady=5)
#        ttk.Label(toprow, text=computer).pack(side=tk.LEFT)
#        ttk.Label(toprow, text='Frame: ').pack(side=tk.LEFT, padx=15)
#        self.frameno[computer] = ttk.Label(toprow, text='')
#        self.frameno[computer].pack(side=tk.LEFT)
#
#        ttk.Label(toprow, text='% Complete').pack(side=tk.RIGHT)
#        self.frameprog[computer] = ttk.Label(toprow, text='0.0')
#        self.frameprog[computer].pack(side=tk.RIGHT)
#
#        ttk.Progressbar(leftblock, length=380, mode='determinate',
#            orient=tk.HORIZONTAL, variable=self.compdata[computer]['progress'])\
#            .pack(padx=5, pady=5)
#
#        rightblock = ttk.Frame(compbox)
#        rightblock.pack(side=tk.LEFT)
#        ttk.Checkbutton(rightblock, text='Pool', 
#            variable=self.compdata[computer]['pool'],
#            command=lambda: self._toggle_comp(computer)).pack()
#        ttk.Button(rightblock, text='Kill', 
#            command=lambda: self._kill_thread(computer)).pack()
#
#    def _toggle_comp(self, computer):
#        '''Adds or removes a computer from the pool.'''
#        if check_slot_open(self.index):
#            return
#        kwargs = {'index':self.index, 'computer':computer}
#        reply = ClientSocket().send_cmd('toggle_comp', kwargs)
#        print(reply)
#
#    def _kill_thread(self, computer):
#        kwargs = {'index':self.index, 'computer':computer}
#        reply = ClientSocket().send_cmd('kill_single_thread', kwargs)
#        print(reply)
#
#    def _kill_render(self):
#        '''Kill the current render.'''
#        if get_job_status(self.index) != 'Rendering':
#            Dialog('Cannot stop a render unless its status is "Rendering"').warn()
#            return
#        if Dialog('Allow currently rendering frames to finish?').yesno():
#            kill_now = False
#        else:
#            kill_now = True
#        kwargs = {'index':self.index, 'kill_now':kill_now}
#        reply = ClientSocket().send_cmd('kill_render', kwargs)
#        print(reply)
#
#    def _resume_render(self):
#        if get_job_status(self.index) != 'Stopped':
#            Dialog('Cannot resume a render unless its status is "Stopped"').warn()
#            return
#        kwargs = {'index':self.index}
#        reply = ClientSocket().send_cmd('resume_render', kwargs)
#        print(reply)
#
#    def _clear_job(self):
#        '''Replaces the current Job instance and replaces it with a blank one.'''
#        status = get_job_status(self.index)
#        if status == 'Empty':
#            Dialog('Cannot remove an empty job.').warn()
#            return
#        if status == 'Rendering':
#            Dialog('Cannot remove a job while rendering. Stop the render then try' +
#                    ' again.').warn()
#        if not Dialog('Clear all job information and reset queue slot to ' +
#                        'defaults?').yesno():
#            return
#        kwargs = {'index':self.index}
#        reply = ClientSocket().send_cmd('clear_job', kwargs)
#        print(reply)
#
#    def update_status(self, computer, pool, frame, progress):
#        '''Updates render progress stats for a given computer.'''
#        #disable until other stuff is working
#        return
#        self.frameno[computer].config(text=str(frame))
#        self.frameprog[computer].config(text=str(round(progress, 1)))
#        self.compdata[computer]['progress'].set(int(progress))
#        if pool == False:
#            self.compdata[computer]['pool'].set(0)
#        else:
#            self.compdata[computer]['pool'].set(1)

    #def draw_bigbox(self):
        '''Creates a large status box to go at the top of a job tab.'''
        '''
        self.kind = 'bigbox'
        self.font = 'TkDefaultFont'
        toprow = tk.Frame(self)
        toprow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(toprow, font=self.font, text='Job ' + str(self.index) + 
            ':').pack(side=tk.LEFT)
        self.statuslbl = tk.Label(toprow, font=self.font, text='Empty')
        self.statuslbl.pack(side=tk.LEFT)
        self.namelabel = tk.Label(toprow, font=self.font, text='filename')
        self.namelabel.pack(padx=5, side=tk.LEFT)
        self.extraslabel = tk.Label(toprow, font=self.font, text='None')
        self.extraslabel.pack(side=tk.RIGHT)
        tk.Label(toprow, font=self.font, text='Extras:').pack(side=tk.RIGHT)
        self.endlabel = tk.Label(toprow, font=self.font, text='1000  ')
        self.endlabel.pack(side=tk.RIGHT)
        tk.Label(toprow, font=self.font, text='End:').pack(side=tk.RIGHT)
        self.startlabel = tk.Label(toprow, font=self.font, text='0000  ')
        self.startlabel.pack(side=tk.RIGHT)
        tk.Label(toprow, font=self.font, text='Start:').pack(side=tk.RIGHT)

        middlerow = tk.Frame(self)
        middlerow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Progressbar(middlerow, length=425, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(side=tk.LEFT)
        tk.Label(middlerow, font=self.font, text='%').pack(side=tk.RIGHT)
        self.proglabel = tk.Label(middlerow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.RIGHT)

        bottomrow = tk.Frame(self)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(bottomrow, font=self.font, text='Elapsed:').pack(side=tk.LEFT)
        self.elapsed_time_lbl = tk.Label(bottomrow, text='')
        self.elapsed_time_lbl.pack(side=tk.LEFT)
        tk.Label(bottomrow, text='   Avg. time/frame:').pack(side=tk.LEFT)
        self.avg_time_lbl = tk.Label(bottomrow, text='')
        self.avg_time_lbl.pack(side=tk.LEFT)
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)
        tk.Label(bottomrow, font=self.font, text='Remaining:').pack(side=tk.RIGHT)
        '''



class JobObject(object):
    def __init__(self, index):
        self.index = index
        self.selected = False
        self._create_gui_elements()

    def _create_gui_elements(self):
        self.smallbox = SmallBox(master=jobbox_frame, index=self.index)
        self._computer_panel()
        self.select()

    def select(self):
        '''Displays the _computer_panel in the GUI'''
        #deselect all other jobs
        for index in localjobs:
            if not index == self.index:
                localjobs[index].deselect()
        self.selected = True
        self.comppanel.pack(padx=10, pady=10)
        self.smallbox.select()
        print('height:', jobbox_frame.winfo_height())
        print('width:', jobbox_frame.winfo_width())
        print('root height:', root.winfo_height())
        print('root width:', root.winfo_width())

    def deselect(self):
        '''Removes the _computer_panel from the GUI'''
        self.selected = False
        self.comppanel.pack_forget()
        self.smallbox.deselect()

    def delete(self):
        self.smallbox.destroy()
        self.smallbox.hrule.destroy()
        self.comppanel.pack_forget()

    def _computer_panel(self):
        '''Array of computer status boxes for right frame.'''
        self.comppanel = ttk.Frame(right_frame)
        #NOTE Do not pack comppanel unless the job is selected
        self.bigbox = BigBox(master=self.comppanel, index=self.index)
        self.bigbox.pack(expand=True, fill=tk.X, padx=5)

        buttonbox = ttk.Frame(self.comppanel)
        buttonbox.pack(anchor=tk.W, padx=5, pady=5)
        ttk.Button(buttonbox, text='Edit', command=self._edit).pack(side=tk.LEFT)
        ttk.Button(buttonbox, text='Start', command=self._start).pack(side=tk.LEFT)
        ttk.Button(buttonbox, text='Stop', command=self._kill_render).pack(
            side=tk.LEFT)
        ttk.Button(buttonbox, text='Resume', command=self._resume_render).pack(
            side=tk.LEFT)

        self.compframe = ttk.Frame(self.comppanel)
        self.compframe.pack()
        self.compcubes = {}
        #changing the number of cols should automatically generate the rest
        #of the layout correctly
        cols = 3
        rows = len(computers) // cols
        #extra rows are needed if the number of computers isn't evenly divisible
        #by the number of columns
        extra_rows = len(computers) % cols
        end = len(computers)
        i = 0
        for col in range(0, cols):
            for row in range(0, rows + extra_rows):
                try:
                    self.compcubes[computers[i]] = CompCube(master=self.compframe,
                        computer=computers[i], index=self.index)
                    self.compcubes[computers[i]].grid(row=row, column=col, padx=5)
                except IndexError:
                    #this is blank space if there are no computers left
                    print('Got index error while building compcubes, ignoring')
                    pass
                i += 1
                if i == end: break
        #put in some buttons in a temp location


    def _edit(self):
        '''Edits job information.'''
        #XXX Not sure what will happen if I change filename, might break indexing
        #it seems to work. Index should be independent of filename except at job
        #creation
        InputWindow(self.index)

    def _start(self):
        '''Starts the render.'''
        if not get_job_status(self.index) == 'Waiting':
            Dialog('Cannot start render unless status is "Waiting"').warn()
            return
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('start_render', kwargs)
        print(reply)

    def toggle_comp(self, computer):
        '''Adds or removes a computer from the pool.'''
        if check_slot_open(self.index):
            return
        kwargs = {'index':self.index, 'computer':computer}
        reply = ClientSocket().send_cmd('toggle_comp', kwargs)
        print(reply)

    def kill_thread(self, computer):
        kwargs = {'index':self.index, 'computer':computer}
        reply = ClientSocket().send_cmd('kill_single_thread', kwargs)
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
        self.smallbox.update(attrdict['status'], attrdict['startframe'], 
            attrdict['endframe'], attrdict['path'], attrdict['progress'], 
            attrdict['times'])
        self.bigbox.update(attrdict['status'], attrdict['startframe'], 
            attrdict['endframe'], attrdict['path'], attrdict['progress'], 
            attrdict['times'])
        for computer in computers:
            compstatus = attrdict['compstatus'][computer]
            self.compcubes[computer].update(compstatus['frame'], 
                compstatus['progress'], compstatus['pool'])



class BigBox(ttk.LabelFrame):
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
        ttk.Progressbar(middlerow, length=830, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(side=tk.LEFT)
        tk.Label(middlerow, font=self.font, text='%').pack(side=tk.RIGHT)
        self.proglabel = tk.Label(middlerow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.RIGHT)

        bottomrow = tk.Frame(container)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        tk.Label(bottomrow, font=self.font, text='Time elapsed:').pack(side=tk.LEFT)
        self.elapsed_time_lbl = tk.Label(bottomrow, text='')
        self.elapsed_time_lbl.pack(side=tk.LEFT)
        tk.Label(bottomrow, text='Avg. time/frame:').pack(side=tk.LEFT, padx=(220, 0))
        self.avg_time_lbl = tk.Label(bottomrow, text='')
        self.avg_time_lbl.pack(side=tk.LEFT)
        self.rem_time_lbl = tk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)
        tk.Label(bottomrow, font=self.font, text='Time remaining:').pack(side=tk.RIGHT)

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


class SmallBox(tk.Frame):
    '''Small job status box for the left window pane.'''
    def __init__(self, master=None, index='0'):
        self.index = index
        self.bgcolor = 'white'
        self.progress = tk.IntVar()
        self.kind = 'smallbox'
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
                print('double nesting in draw')
                for babby in child.winfo_children():
                    babby.bind('<Button-1>', self.toggle)
        self.hrule = HRule(jobbox_frame)

    def toggle(self, event=None):
        '''Switches between selected and deselected state.'''
        if localjobs[self.index].selected == False:
            localjobs[self.index].select()
        else:
            localjobs[self.index].deselect()

    def select(self):
        '''Changes background colors to selected state.'''
        self._changecolor(HighlightColor)

    def deselect(self):
        '''Changes background colors to deselected state.'''
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
                print('double nesting in toggle')
                for babby in child.winfo_children():
                    babby.config(bg=color)

    def update(self, status, startframe, endframe, path, progress, times):
        if path:
            filename = os.path.basename(path)
        else:
            filename = ''
        self.statuslbl.config(text=status)
        self.namelabel.config(text=filename)
        self.progress.set(progress)
        self.proglabel.config(text=str(round(progress, 1)))
        if self.kind == 'smallbox':
            time_rem = self.format_time(times[2])
            self.rem_time_lbl.config(text=time_rem)
        else:
            elapsed_time = self.format_time(times[0])
            avg_time = self.format_time(times[1])
            time_rem = self.format_time(times[2])
            self.elapsed_time_lbl.config(text=elapsed_time)
            self.avg_time_lbl.config(text=avg_time)
            self.rem_time_lbl.config(text=time_rem)


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





class CompCube(tk.LabelFrame):
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
            command=(lambda: localjobs[self.index].toggle_comp(computer))).pack()
        tk.Button(buttonblock, text='Kill', command=(lambda: 
            localjobs[self.index].kill_thread(computer))).pack()

    def update(self, frame, progress, pool):
        self.progress.set(progress)
        self.frameno.config(text=str(frame))
        self.frameprog.config(text=str(round(progress, 1)))
        self.pool.set(pool)



class InputWindow(tk.Toplevel):
    '''New window to handle input for new job or edit an existing one.'''
    def __init__(self, index=None):
        #if get_job_status(self.index) == 'Rendering':
        #    return
        #for editing an existing job, accept existing index
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
        #if not check_slot_open(self.index):
        #    if not Dialog('Overwrite existing queue contents?').yesno():
        #        self.destroy()
        #        return
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


def quit():
    '''Terminates status thread and mainloop, then sends exit call.'''
    stat_thread.end()
    root.quit()
    raise SystemExit


def create_job():
    '''GUI elements are not created directly by this function. They are created 
    from the status thread to ensure that the GUI state is only changed if the 
    server state was successfully changed.'''
    reply = ClientSocket().send_cmd('create_job')
    print(reply)


def delete_job():
    '''GUI elements are not removed directly by this function. They are deleted
    from the status thread to ensure that the GUI state is only changed if the 
    server state was successfully changed.'''
    for index in localjobs:
        if localjobs[index].selected == True:
            break
    kwargs = {'index':index}
    reply = ClientSocket().send_cmd('clear_job', kwargs)
    print(reply)



class HRule(ttk.Separator):
    '''Preconfigured subclass of ttk.Separator'''
    def __init__(self, master):
        ttk.Separator.__init__(self, master, orient=tk.HORIZONTAL)
        self.pack(padx=40, pady=10, fill=tk.X)

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

#class Toolbar(tk.Canvas):
#    def __init__(self, master, height=0, width=0):
#        tk.Canvas.__init__(self, master, height=height, width=width, borderwidth=0, highlightthickness=0)
#        limit = height #vertical gradient
#        r2, g2, b2 = 290, 290, 290
#        r1, g1, b1 = 131, 131, 131
#        r_ratio = float(r2-r1) / limit
#        g_ratio = float(g2-g1) / limit
#        b_ratio = float(b2-b1) / limit
#        for i in range(limit):
#            r = int(r1 + (r_ratio * i))
#            g = int(g1 + (g_ratio * i))
#            b = int(b1 + (b_ratio * i))
#            color = "#%02x%02x%02x" % (r, g, b)
#            self.create_line(0, i, width, i, tags=('gradient'), fill=color)
#        self.tag_lower('gradient')

#LightBlueBGColor = '#%02x%02x%02x' % (222, 228, 234)
#XXX Just get rid of the below ref if it works
LightBlueBGColor = 'white'
MidBGColor = '#%02x%02x%02x' % (190, 190, 190)
LightBGColor = '#%02x%02x%02x' % (232, 232, 232)
DarkBGColor = '#%02x%02x%02x' % (50, 50, 50)
HighlightColor = '#%02x%02x%02x' % (74, 139, 222)
root.config(bg=LightBGColor)


topbar = tk.Frame(root, bg=MidBGColor)
#topbar = Toolbar(root, height=50, width=1200)
#topbar = tk.Canvas(root, height=100, width=500)
#topbar.create_rectangle(0,0,100,100)
topbar.pack(fill=tk.BOTH)
#inner_frame = tk.Frame(topbar, bg='')
#inner_frame.pack(padx=10, pady=10)
#topbar.create_window(0, 0, inner_frame)
#tk.Label(inner_frame, text='lekjer').pack()
tk.Label(topbar, text='Other options go here', bg=MidBGColor).pack()
ttk.Separator(topbar).pack(fill=tk.X)

midblock = tk.Frame(root, bg=LightBGColor)
midblock.pack(padx=15, pady=10, expand=True, fill=tk.BOTH)

left_frame = tk.Frame(midblock, bg=LightBGColor)
left_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)
tk.Label(left_frame, text='Queue:', bg=LightBGColor).pack(padx=5, anchor=tk.W)
left_frame_inner = tk.LabelFrame(left_frame, bg=LightBGColor)
left_frame_inner.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.Y)

jobbox_frame = tk.Frame(left_frame_inner, bg=LightBlueBGColor)
jobbox_frame.pack(expand=True, fill=tk.BOTH)
jobbtns = tk.Frame(left_frame_inner, bg=LightBGColor)
jobbtns.pack(fill=tk.X)
ttk.Separator(jobbtns).pack(fill=tk.X)
RectButton(jobbtns, text='+', command=InputWindow).pack(side=tk.LEFT)
RectButton(jobbtns, text='-', command=delete_job).pack(side=tk.LEFT)

right_frame = ttk.LabelFrame(midblock)
right_frame.pack(padx=5, side=tk.LEFT, expand=True, fill=tk.BOTH)


footer = tk.Frame(root, bg=LightBGColor)
footer.pack(fill=tk.BOTH)
tk.Label(footer, text='', bg=LightBGColor).pack()



stat_thread = StatusThread()
stat_thread.start()
root.mainloop()
