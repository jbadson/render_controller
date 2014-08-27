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

host = 'localhost'
port = 2020

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

#---Instantiate GUI---
root = tk.Tk()
root.config(bg='gray90')
#use internal quit function instead of OSX
root.bind('<Command-q>', lambda x: quit()) 
root.bind('<Control-q>', lambda x: quit())

#---Tkinter variables---
tk_path = tk.StringVar()
tk_startframe = tk.StringVar()
tk_endframe = tk.StringVar()
tk_complist = tk.StringVar()
#progress bar variable
tk_prog = tk.IntVar(0.0)


#set some temp defaults
tk_path.set('/mnt/data/test_render/test_render.blend')
tk_startframe.set('1')
tk_endframe.set('4')
tk_complist.set('massive,sneffels')




#---GUI Functions---
def update_gui():
    root.update_idletasks()
    root.after(80, update_gui)


def startrender():
    render_args = {
                    'path':tk_path.get(),
                    'start':tk_startframe.get(),
                    'end':tk_endframe.get(),
                    'computers':tk_complist.get(),
                    }

    print(render_args)
    send_command('cmd_render', kwargs=render_args)


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
            MainWindow.update_tab(job, statdict[job]['compstatus'])

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




class TabWindow(object):

    def __init__(self):
        '''Initializes a ttk Notebook (tabbed window) interface.'''
        self.notebook = ttk.Notebook(height=650, width=550, padding=0)
        self.notebook.pack(padx=10, pady=10)
        #dict of tabs for future reference
        self.tabs = {}
        #list of currently rendering computers, updated from script data

    def maketab(self, tab_id=0):
        '''Creates a new instance of JobBox and appends it as a tab. 
        Must specify an integer tab ID number.'''
        self.tabs[tab_id] = JobBox(master=root)
        self.notebook.add(self.tabs[tab_id], text='Tab ' + str(tab_id))

    def update_tab(self, tab_id, compstatus):
        '''Updates computers in a given tab based on contents of compstatus dict.'''
        for computer in computers:
            pool = compstatus[computer]['pool']
            frame = compstatus[computer]['frame']
            progress = compstatus[computer]['progress']
            self.tabs[tab_id].update_status(computer, pool, frame, progress)
            

class JobBox(tk.LabelFrame):

    def __init__(self, master=None):
        tk.LabelFrame.__init__(self, master)
        self.pack()
        tk.Label(self, text='This is a job box').pack()

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

        topline = tk.Frame(leftblock)
        topline.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(topline, text=computer).pack(side=tk.LEFT)
        tk.Label(topline, text='Frame: ').pack(side=tk.LEFT, padx=15)
        self.frameno[computer] = tk.Label(topline, text='')
        self.frameno[computer].pack(side=tk.LEFT)

        tk.Label(topline, text='% Complete').pack(side=tk.RIGHT)
        self.frameprog[computer] = tk.Label(topline, text='0.0')
        self.frameprog[computer].pack(side=tk.RIGHT)

        ttk.Progressbar(leftblock, length=400, mode='determinate',
            orient=tk.HORIZONTAL, variable=self.compdata[computer]['progress'])\
            .pack(padx=5, pady=5)

        rightblock = tk.Frame(compbox)
        rightblock.pack(side=tk.LEFT)
        ttk.Checkbutton(rightblock, text='Pool', 
            variable=self.compdata[computer]['pool']).pack()
        ttk.Button(rightblock, text='Kill').pack()

    def update_status(self, computer, pool, frame, progress):
        '''Updates render progress stats for a given computer.'''
        #update text fields
        self.frameno[computer].config(text=str(frame))
        self.frameprog[computer].config(text=str(round(progress, 1)))
        #update progress bar
        self.compdata[computer]['progress'].set(int(progress))
        if pool == False:
            self.compdata[computer]['pool'].set(0)
        else:
            self.compdata[computer]['pool'].set(1)

        



#put all this crap in a different window
bob = tk.Toplevel()
bob.bind('<Command-q>', lambda x: quit()) 
bob.bind('<Control-q>', lambda x: quit())
tk.Entry(bob, textvariable=tk_path, width=30).pack()
tk.Entry(bob, textvariable=tk_startframe, width=10).pack()
tk.Entry(bob, textvariable=tk_endframe, width=10).pack()
tk.Entry(bob, textvariable=tk_complist, width=30).pack()
ttk.Button(bob, text='Start', command=startrender).pack()

ttk.Progressbar(bob, length='200', mode='determinate', orient=tk.HORIZONTAL, variable=tk_prog).pack()

outbox = tk.Text(bob, width=70, height=70)
outbox.pack()
outbox.insert(tk.END, 'this is text')




#need some basic data to initialize the GUI
#This will need to be grabbed from the server
computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache', 
        'conundrum', 'paradox'] 
maxqueuelength = 4

MainWindow = TabWindow()
for i in range(1, maxqueuelength):
    MainWindow.maketab(tab_id=i)

update_gui()
statthread = ReceiveThread()
statthread.start()
root.mainloop()

