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

host = 'localhost'
port = 2020

#--------CLIENT-RELATED CLASSES--------
class ReceiveThread(threading.Thread):

    def __init__(self):
        self.stop = False
        threading.Thread.__init__(self, target=self._receivethread)

    def end(self):
        self.stop = True

    def _receivethread(self):
        print('starting _receivethread')
        while True:
            command = 'get_status' 
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            sock.sendall(bytes(command, 'UTF-8'))
            reply = sock.recv(4096)
            if reply:
                statdict = eval(reply.decode('UTF-8'))
                parse_update(statdict)
            time.sleep(0.1)
            sock.close()
            #putting stop here should mean that socket is properly closed
            if self.stop == True:
                print('_receivethread terminated')
                break



#--------CLIENT-RELATED FUNCTIONS--------
def send_command(command, kwargs={}):
    '''Passes a dict containing a keyword command and args to the server.
    supplied args should be in a dictionary''' 
    data = command + str(kwargs)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bytes(data, 'UTF-8'))
    #do not wait for reply, this is handled by another function
    s.close()

def quit():
    '''Shuts down status thread first, then attempts to quit.'''
    statthread.end()
    #os._exit(1)
    raise SystemExit



#--------GUI--------

#---GUI Classes---
class StatusTab(tk.LabelFrame):

    def __init__(self, master=None):
        tk.LabelFrame.__init__(self, master)
        self.pack()

        '''need the following info for each box:
            computer
            frame
            progress %
            in/out of pool'''

        #dict of tk variables for progress bars
        self.compdata = {}
        #dict to hold tk.Label objects for frame number and % complete
        #for ease of reference later
        self.frameno = {}
        self.frameprog = {}
        for computer in computers:
            self.compdata[computer] = {} 
            self.compdata[computer]['frame'] = tk.IntVar(0)
            self.compdata[computer]['progress'] = tk.IntVar(0)
            self.compdata[computer]['pool'] = tk.IntVar(0)
            self.frameno[computer] = None
            self.frameprog[computer] = None
            self._comp_status_box(self, computer)

    def _comp_status_box(self, master, computer):
        '''Render progress/status box for a given computer.'''
        compbox = tk.LabelFrame(master)
        compbox.pack(padx=5, pady=5)
        leftblock = tk.Frame(compbox)
        leftblock.pack(side=tk.LEFT)

        toprow = tk.Frame(leftblock)
        toprow.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(toprow, text=computer).pack(side=tk.LEFT)
        tk.Label(toprow, text='Frame: ').pack(side=tk.LEFT, padx=15)
        self.frameno[computer] = tk.Label(toprow, text='')
        self.frameno[computer].pack(side=tk.LEFT)

        tk.Label(toprow, text='% Complete').pack(side=tk.RIGHT)
        self.frameprog[computer] = tk.Label(toprow, text='0.0')
        self.frameprog[computer].pack(side=tk.RIGHT)

        ttk.Progressbar(leftblock, length=400, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.compdata[computer]['progress'])\
            .pack(padx=5, pady=5)

        rightblock = tk.Frame(compbox)
        rightblock.pack(side=tk.LEFT)
        tk.Checkbutton(rightblock, text='Pool', 
            variable=self.compdata[computer]['pool']).pack()
        tk.Button(rightblock, text='Kill').pack()

    def update_status(self, computer, pool, frame, progress):
        '''Updates render progress stats for a given computer.'''
        self.frameno[computer].config(text=str(frame))
        self.frameprog[computer].config(text=str(round(progress, 1)))
        #update progress bar
        self.compdata[computer]['progress'].set(int(progress))
        if pool == False:
            self.compdata[computer]['pool'].set(0)
        else:
            self.compdata[computer]['pool'].set(1)


class JobStatusBox(ttk.LabelFrame):
    '''Small status boxes for each job.
    Shows an abbreviated dataset compared to the main job info at top of tab.'''

    def __init__(self, index, master=None):
        self.index = index
        self.progress = tk.IntVar(0) 
        self.font='TkSmallCaptionFont'
        ttk.LabelFrame.__init__(self, master)
        self.pack(padx=10, pady=0)
        self._build(self)

    def _build(self, master):
        toprow = ttk.Frame(master)
        toprow.pack(padx=5, expand=tk.TRUE, fill=tk.X)
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

        self.namelabel = ttk.Label(master, font=self.font, text='filename')
        self.namelabel.pack(padx=5, fill=tk.X)
        ttk.Progressbar(master, length=250, mode='determinate', 
            orient=tk.HORIZONTAL, variable=self.progress).pack(padx=5)

        bottomrow = ttk.Frame(master)
        bottomrow.pack(padx=5, expand=tk.TRUE, fill=tk.X)
        self.proglabel = ttk.Label(bottomrow, font=self.font, text='0.0')
        self.proglabel.pack(side=tk.LEFT)
        ttk.Label(bottomrow, font=self.font, text='% Complete').pack(side=tk.LEFT)
        ttk.Label(bottomrow, font=self.font, text='Remaining').pack(side=tk.RIGHT)
        self.timelabel = ttk.Label(bottomrow, font=self.font, text='0d0h0m0s')
        self.timelabel.pack(side=tk.RIGHT)


    def update(self, status, startframe, endframe, filename, progress, time_rem):
        self.statuslbl.config(text=status)
        self.startlabel.config(text=str(startframe) + '   ')
        self.endlabel.config(text=str(endframe))
        self.namelabel.config(text=filename)
        self.progress.set(progress)
        self.proglabel.config(text=str(round(progress, 1)))
        self.timelabel.config(text=time_rem)

#---GUI Initialization---
root = tk.Tk()
#root.config(bg='gray90')
#use internal quit function instead of OSX
root.bind('<Command-q>', lambda x: quit()) 
root.bind('<Control-q>', lambda x: quit())


#---Tkinter variables---
tk_path = tk.StringVar()
tk_startframe = tk.StringVar()
tk_endframe = tk.StringVar()
tk_extraframes = tk.StringVar()
tk_render_engine = tk.StringVar()
tk_complist = tk.StringVar()
#progress bar variable
tk_prog = tk.IntVar(0.0)



#---GUI Functions---
def update_gui():
    root.update_idletasks()
    root.after(80, update_gui)


#def startrender():
#    '''enqueue and start render in one go.'''
#    render_args = {
#                    'path':tk_path.get(),
#                    'start':tk_startframe.get(),
#                    'end':tk_endframe.get(),
#                    'computers':tk_complist.get(),
#                    }
#
#    print(render_args)
#    send_command('cmd_render', kwargs=render_args)


def enqueue():
    kwargs = { 'index':1,
                'path':tk_path.get(),
                'startframe':tk_startframe.get(),
                'endframe':tk_endframe.get(),
                'extraframes':tk_extraframes.get(),
                'render_engine':tk_render_engine.get(),
                'complist':tk_complist.get(),
                }

    print(kwargs)
    send_command('enqueuejob', kwargs)

def start_render():
    kwargs = {'index':1}
    send_command('rendrstart', kwargs) 

def parse_update(statdict):
    '''Parses update dictionary from server, updates GUI elements

    statdict [i] = { 'status':renderjobs[job].get_job_status(), 
            'path':renderjobs[job].path, 
            'startframe':renderjobs[job].startframe, 
            'endframe':renderjobs[job].endframe,
            'extraframes':renderjobs[job].extraframes, 
            'complist':renderjobs[job].complist,
            'render_engine':renderjobs[job].render_engine, 
            'progress':renderjobs[job].get_job_progress(),
            'compstatus':renderjobs[job].compstatus }
    '''

    if len(statdict) == 0:
        return

    #update the computer status boxes for each job
    for job in statdict:
        if statdict[job]:
            status = statdict[job]['status']
            startframe = statdict[job]['startframe']
            endframe = statdict[job]['endframe']
            filename = os.path.basename(statdict[job]['path'])
            progress = statdict[job]['progress']
            #time_rem = statdict[job]['time_rem']
            time_rem = '0d0h0m0s' #placeholder
            jobstats[job].update(status, startframe, endframe, filename, 
                                progress, time_rem) 
            for computer in computers:
                pool = statdict[job]['compstatus'][computer]['pool']
                frame = statdict[job]['compstatus'][computer]['frame']
                progress = statdict[job]['compstatus'][computer]['progress']
                tabs[job].update_status(computer, pool, frame, progress)



    #XXX leaving this here for testing, delete when done
    job = statdict[1]
    tk_prog.set(job['progress'])
    outbox.delete(0.0, tk.END)
    outbox.insert(tk.END, job['status'] + '\n')
    outbox.insert(tk.END, job['path'] + '\n')
    outbox.insert(tk.END, str(job['startframe']) + '\n')
    outbox.insert(tk.END, str(job['endframe']) + '\n')
    outbox.insert(tk.END, str(job['extraframes']) + '\n')
    outbox.insert(tk.END, job['render_engine'] + '\n')
    outbox.insert(tk.END, str(job['complist']) + '\n')
    outbox.insert(tk.END, 'Computer list:\n')
    compstatus = job['compstatus']
    for computer in compstatus:
        if computer in job['complist']:
            outbox.insert(tk.END, computer + ' |Frame:' + 
                            str(compstatus[computer]['frame']) + ' |Progress: ' + 
                            str(int(compstatus[computer]['progress'])) + '%' + '\n')


#Testing stuff, delete when done
#put all this crap in a different window
bob = tk.Toplevel()
bob.bind('<Command-q>', lambda x: quit()) 
bob.bind('<Control-q>', lambda x: quit())
tk.Entry(bob, textvariable=tk_path, width=30).pack()
tk.Entry(bob, textvariable=tk_startframe, width=10).pack()
tk.Entry(bob, textvariable=tk_endframe, width=10).pack()
tk.Entry(bob, textvariable=tk_complist, width=30).pack()
ttk.Button(bob, text='Start', command=start_render).pack()
ttk.Button(bob, text='Enqueue', command=enqueue).pack()

ttk.Progressbar(bob, length='200', mode='determinate', orient=tk.HORIZONTAL, 
                variable=tk_prog).pack()

outbox = tk.Text(bob, width=70, height=70)
outbox.pack()
outbox.insert(tk.END, 'this is text')

#some variables we're going to skip
tk_extraframes.set('')
tk_render_engine.set('blender')

#need some basic data to initialize the GUI
#This will need to be grabbed from the server
computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache', 
        'conundrum', 'paradox'] 
maxqueuelength = 6

#set some temp defaults
tk_path.set('/mnt/data/test_render/test_render.blend')
tk_startframe.set('1')
tk_endframe.set('4')
tk_complist.set('massive,sneffels')

main_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
main_window.pack(ipadx=30)

left_pane = ttk.Frame()
ttk.Label(left_pane, text='', width=1).pack(side=tk.LEFT, fill=tk.X) #to pad left side evenly
left_frame = ttk.LabelFrame(left_pane)
left_frame.pack(side=tk.LEFT, ipady=5, expand=tk.TRUE, fill=tk.BOTH)
ttk.Label(left_frame, text='Render Queue').pack()
jobstats = {}

main_notebook = ttk.Notebook(width=450)
tabs = {}
for i in range(1, maxqueuelength):
    jobstats[i] = JobStatusBox(master=left_frame, index=i)
    tabs[i] = StatusTab()
    main_notebook.add(tabs[i], text='Job ' + str(i))

#pad bottom of left pane for even spacing
#ttk.Label(left_pane, text='', width=5).pack(pady=0)
main_window.add(left_pane)
main_window.add(main_notebook)

update_gui()
statthread = ReceiveThread()
statthread.start()
root.mainloop()

