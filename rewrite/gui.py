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
        data = ''.join(chunks)
        return data

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for server.
        Message must be a UTF-8 string.'''
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
        self._sendmsg(str(kwargs))
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

def get_all_attrs():
    '''Gets attributes for all Job() instances on the server.'''
    attrdict = ClientSocket().send_cmd('get_all_attrs')
    attrdict = ast.literal_eval(attrdict)
    print(type(attrdict))

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


#def get_config():
#    '''Get contents of config file from server.'''
    

    


#----------GUI----------

#need some basic data to initialize the GUI
#This will need to be grabbed from the server
computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache', 
        'conundrum', 'paradox'] 

maxqueuelength = 5



#----Initialize GUI----
root = tk.Tk()
root.bind('<Command-q>', lambda x: quit()) 
root.bind('<Control-q>', lambda x: quit())








#---GUI Classes---
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
            attrdict = ClientSocket().send_cmd('get_all_attrs')
            attrdict = ast.literal_eval(attrdict)
            for job in attrdict:
                stats = attrdict[job]
                #if stats['status'] == 'Empty':
                #    continue
                #update the small (left pane) job status box
                job_stat_boxes[job].update(stats['status'], stats['startframe'], 
                        stats['endframe'], stats['path'], stats['progress'], 
                        stats['times'])
                #update the large (top of tab) job status box
                tabs[job].jobstat.update(stats['status'], stats['startframe'], 
                        stats['endframe'], stats['path'], stats['progress'], 
                        stats['times'])
                #update the status for each computer
                for computer in stats['compstatus']:
                    compstats = stats['compstatus'][computer]
                    tabs[job].update_status(computer, compstats['pool'], 
                        compstats['frame'], compstats['progress'])
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


class StatusTab(tk.LabelFrame):

    def __init__(self, index, master=None):
        tk.LabelFrame.__init__(self, master, bg='gray90')
        self.pack()

        '''need the following info for each box:
            computer
            frame
            progress %
            in/out of pool'''

        #internal index needed for sending job-specific commands
        self.index = index
        #dict of tk variables for progress bars
        self.compdata = {}
        #dict to hold tk.Label objects for frame number and % complete
        #for ease of reference later
        self.frameno = {}
        self.frameprog = {}
        #self._job_main_info_box(self)
        self.jobstat = JobStatusBox(self.index, master=self)
        self.jobstat.draw_bigbox()
        buttonbar = ttk.Frame(self)
        buttonbar.pack(padx=5, pady=5, expand=True, fill=tk.X)
        ttk.Button(buttonbar, text='New / Edit', command=self._input).pack( \
            side=tk.LEFT)
        ttk.Button(buttonbar, text='Start', command=self._start).pack(side=tk.LEFT)
        ttk.Button(buttonbar, text='Stop', command=self._kill_render).pack( \
            side=tk.LEFT)
        ttk.Button(buttonbar, text='Resume', command=self._resume_render).pack( \
            side=tk.LEFT)
        ttk.Button(buttonbar, text='Remove', command=self._clear_job).pack( \
            side=tk.RIGHT)
        #encapsulate computer boxes in canvas to make it scrollable
        canvframe = ttk.LabelFrame(self)
        canvframe.pack(expand=True, fill=tk.BOTH)
        #determine height of canvas based on number of computer boxes to be rendered
        canvheight = len(computers) * 70
        self.canv = tk.Canvas(canvframe, height=canvheight, 
            scrollregion=(0,0,450,canvheight))
        self.scrollbar = ttk.Scrollbar(canvframe, orient=tk.VERTICAL)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.scrollbar.config(command=self.canv.yview)
        self.canv.config(yscrollcommand=self.scrollbar.set)
        self.compframe = tk.Frame(self.canv)
        for computer in computers:
            self.compdata[computer] = {} 
            self.compdata[computer]['frame'] = tk.IntVar(0)
            self.compdata[computer]['progress'] = tk.IntVar(0)
            self.compdata[computer]['pool'] = tk.IntVar(0)
            self.frameno[computer] = None
            self.frameprog[computer] = None
            self._comp_status_box(self.compframe, computer)
        self.compframe.pack(expand=True, fill=tk.BOTH)
        self.canv.create_window(0, 0, window=self.compframe, anchor=tk.NW)
        self.canv.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

    def _input(self):
        self.inputwin = InputWindow(self.index)

    def _start(self):
        '''Starts the render.'''
        if not get_job_status(self.index) == 'Waiting':
            Dialog('Cannot start render unless status is "Waiting"').warn()
            return
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('start_render', kwargs)
        print(reply)

    def _comp_status_box(self, master, computer):
        '''Render progress/status box for a given computer.'''
        compbox = tk.LabelFrame(master, bg='gray90')
        compbox.pack(padx=5, pady=5, expand=True, fill=tk.X)
        leftblock = ttk.Frame(compbox)
        leftblock.pack(side=tk.LEFT)

        toprow = ttk.Frame(leftblock)
        toprow.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(toprow, text=computer).pack(side=tk.LEFT)
        ttk.Label(toprow, text='Frame: ').pack(side=tk.LEFT, padx=15)
        self.frameno[computer] = ttk.Label(toprow, text='')
        self.frameno[computer].pack(side=tk.LEFT)

        ttk.Label(toprow, text='% Complete').pack(side=tk.RIGHT)
        self.frameprog[computer] = ttk.Label(toprow, text='0.0')
        self.frameprog[computer].pack(side=tk.RIGHT)

        ttk.Progressbar(leftblock, length=380, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.compdata[computer]['progress'])\
            .pack(padx=5, pady=5)

        rightblock = ttk.Frame(compbox)
        rightblock.pack(side=tk.LEFT)
        ttk.Checkbutton(rightblock, text='Pool', 
            variable=self.compdata[computer]['pool'],
            command=lambda: self._toggle_comp(computer)).pack()
        ttk.Button(rightblock, text='Kill', 
            command=lambda: self._kill_thread(computer)).pack()

    def _toggle_comp(self, computer):
        '''Adds or removes a computer from the pool.'''
        if check_slot_open(self.index):
            return
        kwargs = {'index':self.index, 'computer':computer}
        reply = ClientSocket().send_cmd('toggle_comp', kwargs)
        print(reply)

    def _kill_thread(self, computer):
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

    def _clear_job(self):
        '''Replaces the current Job instance and replaces it with a blank one.'''
        status = get_job_status(self.index)
        if status == 'Empty':
            Dialog('Cannot remove an empty job.').warn()
            return
        if status == 'Rendering':
            Dialog('Cannot remove a job while rendering. Stop the render then try' +
                    ' again.').warn()
        if not Dialog('Clear all job information and reset queue slot to ' +
                        'defaults?').yesno():
            return
        kwargs = {'index':self.index}
        reply = ClientSocket().send_cmd('clear_job', kwargs)
        print(reply)

    def update_status(self, computer, pool, frame, progress):
        '''Updates render progress stats for a given computer.'''
        self.frameno[computer].config(text=str(frame))
        self.frameprog[computer].config(text=str(round(progress, 1)))
        self.compdata[computer]['progress'].set(int(progress))
        if pool == False:
            self.compdata[computer]['pool'].set(0)
        else:
            self.compdata[computer]['pool'].set(1)



class JobStatusBox(ttk.LabelFrame):

    def __init__(self, index, master=None):
        self.index = index
        self.progress = tk.IntVar(0) 
        ttk.LabelFrame.__init__(self, master)
        self.pack(padx=5, pady=0, fill=tk.X)

    def draw_smallbox(self):
        '''Creates a small status box for the left window pane.'''
        self.kind = 'smallbox'
        self.font='TkSmallCaptionFont'
        toprow = ttk.Frame(self)
        toprow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Label(toprow, font=self.font, text='Job ' + str(self.index) + 
                    ':').pack(side=tk.LEFT)
        self.statuslbl = ttk.Label(toprow, font=self.font, text='Empty')
        self.statuslbl.pack(side=tk.LEFT)
        self.endlabel = ttk.Label(toprow, font=self.font, text='1000')
        self.endlabel.pack(side=tk.RIGHT)
        ttk.Label(toprow, font=self.font, text='End:').pack(side=tk.RIGHT)
        self.startlabel = ttk.Label(toprow, font=self.font, text='0000   ')
        self.startlabel.pack(side=tk.RIGHT)
        ttk.Label(toprow, font=self.font, text='Start:').pack(side=tk.RIGHT)

        self.namelabel = ttk.Label(self, font=self.font, text='filename')
        self.namelabel.pack(padx=5, fill=tk.X)
        ttk.Progressbar(self, length=250, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(padx=5)

        bottomrow = ttk.Frame(self)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        self.proglabel = ttk.Label(bottomrow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.LEFT)
        ttk.Label(bottomrow, font=self.font, text='% Complete').pack(side=tk.LEFT)
        ttk.Label(bottomrow, font=self.font, text='Remaining').pack(side=tk.RIGHT)
        self.rem_time_lbl = ttk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)

    def draw_bigbox(self):
        '''Creates a large status box to go at the top of a job tab.'''
        self.kind = 'bigbox'
        self.font = 'TkDefaultFont'
        toprow = ttk.Frame(self)
        toprow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Label(toprow, font=self.font, text='Job ' + str(self.index) + 
                    ':').pack(side=tk.LEFT)
        self.statuslbl = ttk.Label(toprow, font=self.font, text='Empty')
        self.statuslbl.pack(side=tk.LEFT)
        self.namelabel = ttk.Label(toprow, font=self.font, text='filename')
        self.namelabel.pack(padx=5, side=tk.LEFT)
        self.extraslabel = ttk.Label(toprow, font=self.font, text='None')
        self.extraslabel.pack(side=tk.RIGHT)
        ttk.Label(toprow, font=self.font, text='Extras:').pack(side=tk.RIGHT)
        self.endlabel = ttk.Label(toprow, font=self.font, text='1000  ')
        self.endlabel.pack(side=tk.RIGHT)
        ttk.Label(toprow, font=self.font, text='End:').pack(side=tk.RIGHT)
        self.startlabel = ttk.Label(toprow, font=self.font, text='0000  ')
        self.startlabel.pack(side=tk.RIGHT)
        ttk.Label(toprow, font=self.font, text='Start:').pack(side=tk.RIGHT)

        middlerow = ttk.Frame(self)
        middlerow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Progressbar(middlerow, length=425, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(side=tk.LEFT)
        ttk.Label(middlerow, font=self.font, text='%').pack(side=tk.RIGHT)
        self.proglabel = ttk.Label(middlerow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.RIGHT)

        bottomrow = ttk.Frame(self)
        bottomrow.pack(padx=5, expand=True, fill=tk.X)
        ttk.Label(bottomrow, font=self.font, text='Elapsed:').pack(side=tk.LEFT)
        self.elapsed_time_lbl = ttk.Label(bottomrow, text='')
        self.elapsed_time_lbl.pack(side=tk.LEFT)
        ttk.Label(bottomrow, text='   Avg. time/frame:').pack(side=tk.LEFT)
        self.avg_time_lbl = ttk.Label(bottomrow, text='')
        self.avg_time_lbl.pack(side=tk.LEFT)
        self.rem_time_lbl = ttk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.rem_time_lbl.pack(side=tk.RIGHT)
        ttk.Label(bottomrow, font=self.font, text='Remaining:').pack(side=tk.RIGHT)

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

    def update(self, status, startframe, endframe, path, progress, times):
        if path:
            filename = os.path.basename(path)
        else:
            filename = ''
        self.statuslbl.config(text=status)
        self.startlabel.config(text=str(startframe) + '   ')
        self.endlabel.config(text=str(endframe))
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


class InputWindow(tk.Toplevel):
    '''New window to handle input for new job or edit an existing one.'''
    def __init__(self, index):
        self.index = index
        if get_job_status(self.index) == 'Rendering':
            return
        self.tk_path = tk.StringVar()
        self.tk_startframe = tk.StringVar()
        self.tk_endframe = tk.StringVar()
        self.tk_extraframes = tk.StringVar()
        self.tk_render_engine = tk.StringVar()
        self.tk_complist = tk.StringVar()
        #set some temp defaults
        self.tk_path.set('/mnt/data/test_render/test_render.blend')
        self.tk_startframe.set('1')
        self.tk_endframe.set('4')
        self.tk_render_engine.set('blender')
        self.tk_complist.set('massive')
        tk.Toplevel.__init__(self)
        container = ttk.LabelFrame(self)
        container.pack(padx=10, pady=10)
        self._build(container)

    def _build(self, master):
        ttk.Label(master, text='Path:').pack()
        ttk.Entry(master, textvariable=self.tk_path, width=40).pack(padx=10)
        ttk.Label(master, text='Start frame:').pack()
        ttk.Entry(master, textvariable=self.tk_startframe).pack()
        ttk.Label(master, text='End frame:').pack()
        ttk.Entry(master, textvariable=self.tk_endframe).pack()
        ttk.Label(master, text='Extra frames:').pack()
        ttk.Entry(master, textvariable=self.tk_extraframes).pack()
        ttk.Radiobutton(master, variable=self.tk_render_engine, 
            text='Blender', value='blender').pack()
        ttk.Radiobutton(master, variable=self.tk_render_engine, 
            text='Terragen', value='terragen').pack()
        ttk.Label(master, text='Computer list:').pack()
        ttk.Entry(master, textvariable=self.tk_complist).pack()

        buttons = tk.Frame(self)
        buttons.pack()
        ttk.Button(buttons, text='Enqueue', command=self._enqueue).pack()
        ttk.Button(buttons, text='Cancel', command=self.destroy).pack()

    def _compgrid(self, master):
        '''Generates grid of computer checkboxes.'''
        #generate dict of buttons
        self.compbuttons = {}
        #place the buttons
        row1 = tk.Frame(master)
        row1.pack()
        for 
        


    def _enqueue(self):
        '''Places a new job in queue.'''
        if not check_slot_open(self.index):
            if not Dialog('Overwrite existing queue contents?').yesno():
                self.destroy()
                return
        path = self.tk_path.get()
        startframe = int(self.tk_startframe.get())
        endframe = int(self.tk_endframe.get())
        extraframes = []
        if self.tk_extraframes.get() != '':
            extraframes = self.tk_extraframes.get().split(',')
        render_engine = self.tk_render_engine.get()
        complist = self.tk_complist.get().split(',')
        self.destroy()
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








main_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
main_window.pack(ipadx=30)
main_window.bind('<Command-q>', lambda x: quit()) 
main_window.bind('<Control-q>', lambda x: quit())

left_pane = ttk.Frame()
#pad left side evenly
ttk.Label(left_pane, text='', width=1).pack(side=tk.LEFT, fill=tk.X) 
left_frame = ttk.LabelFrame(left_pane)
left_frame.pack(side=tk.LEFT, ipady=5, expand=True, fill=tk.BOTH)
ttk.Label(left_frame, text='Render Queue').pack()
job_stat_boxes = {}

main_notebook = ttk.Notebook(width=450)
tabs = {}
for i in range(1, maxqueuelength + 1):
    job_stat_boxes[i] = JobStatusBox(master=left_frame, index=i)
    job_stat_boxes[i].draw_smallbox()
    tabs[i] = StatusTab(i)
    main_notebook.add(tabs[i], text='Job ' + str(i))

#pad bottom of left pane for even spacing
#ttk.Label(left_pane, text='', width=5).pack(pady=0)
main_window.add(left_pane)
main_window.add(main_notebook)





stat_thread = StatusThread()
stat_thread.start()
root.mainloop()
