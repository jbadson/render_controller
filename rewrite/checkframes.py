#trying for a more object oriented approach
#store data as object attributes instead of global vars
#keep GUI functions separate from logic functions
#send data to class methods as args, receive it as return args
#package multiple return args as tuples

import Tkinter as tk
import ttk
import os
import subprocess
import ScrolledText as st


#job for testing purposes
allowed_filetypes = ['.jpg', '.jpeg', '.png', '.exr']
class Job(object):
    def __init__(self, index):
        self.path = '/mnt/data/test_render/blendfiles/test_render.blend'
        self.startframe = 1
        self.endframe = 10

job1 = Job(1)


#-----------real module elements start here----------

#computational elements should be separate from GUI elements

class MissingFrames(object):
    '''Represents an instance of the check_missing_frames window and all
    associated data and methods.'''

    def __init__(self):
        self.path = None
        self.basepath = None
        self.renderpath = None
        self.startframe = None
        self.endframe = None
        self.leftbreak = None
        self.leftbreak = None
        pass

    def completed(self):
        '''Returns true if self.check() has been run at least once.'''
        if self.leftbreak and self.rightbreak:
            return True
        else:
            return False

    def get_renderpath(self, path):
        '''Attempts to find path to render folder for an existing job.'''
        self.path = path
        self.basepath = os.path.dirname(self.path)
        if os.path.exists(os.path.split(self.basepath)[0] + '/render/'):
            self.renderpath = os.path.split(self.basepath)[0] + '/render/'
        else:
            self.renderpath = self.basepath

        return self.renderpath


    def check(self, renderpath, startframe, endframe):
        '''Checks specified directory for a suitable file, parses filename, and 
        returns left and right indices of sequential filenumber portion of the 
        filename.'''
        self.renderpath = renderpath
        self.startframe = startframe
        self.endframe = endframe

        self.dir_contents = os.listdir(self.renderpath)
        self.dir_contents.sort()

        for i in self.dir_contents:
            if os.path.splitext(i)[-1] in allowed_filetypes:
                self.filename = i
                self.base, self.ext = os.path.splitext(i)
                print self.filename, self.base, self.ext
                filesok = True
                break
            else:
                filesok = False

        if filesok == False:
            print('No suitable files found. Check path and try again.')
            return False

        length = range(len(self.base))
        length.reverse()
        for i in length:
            if not self.base[i].isdigit():
                self.leftbreak = i + 1
                #assuming sequential #s go to end of filename
                self.rightbreak = len(self.base)
                self.sequentials = self.filename[self.leftbreak:self.rightbreak]
                print self.leftbreak, self.rightbreak, self.sequentials
                break
        return (self.leftbreak, self.rightbreak)


    def generate_lists(self, leftbreak, rightbreak):
        self.leftbreak = leftbreak
        self.rightbreak = rightbreak
        self.sequentials = self.filename[self.leftbreak:self.rightbreak]

        self.frames_expected = []
        self.frames_found = []
        self.frames_missing = []

        for frame in range(self.startframe, self.endframe + 1):
            self.frames_expected.append(frame)

        for filename in self.dir_contents:
            #ignore files that aren't images
            if os.path.splitext(filename)[-1] in allowed_filetypes:
                frame = int(filename[self.leftbreak:self.rightbreak])
                self.frames_found.append(frame)

        for frame in self.frames_expected:
            if not frame in self.frames_found:
                self.frames_missing.append(frame)

        return (self.dir_contents, self.frames_expected, self.frames_found, 
                self.frames_missing)
            





#window opens here
cf_window = tk.Tk() #stand-in for toplevel window
checkjob = tk.IntVar()
check_path = tk.StringVar()
check_startframe = tk.StringVar()
check_endframe = tk.StringVar()

#create the basic object when window opens
framecheck = MissingFrames()

#GUI functions
def select_job(index):
    if index == 0:
        return

    path = Job(index).path
    startframe = Job(index).startframe
    endframe = Job(index).endframe
    renderpath = framecheck.get_renderpath(path)
    
    check_path.set(renderpath)
    check_startframe.set(startframe)
    check_endframe.set(endframe)


def check_directory():
    renderpath = check_path.get()
    if not renderpath:
        return
    if not os.path.exists(renderpath):
        print('Path does not exist.')
        return
    try:
        startframe = int(check_startframe.get())
        endframe = int(check_endframe.get())
    except ValueError:
        print('Start and end frames must be integers.')
        return
    leftbreak, rightbreak = framecheck.check(renderpath, startframe, endframe)
    lists = framecheck.generate_lists(leftbreak, rightbreak)
    put_text(lists)

def recheck_directory():
    '''Checks directory again if filename parsing is adjusted.'''

    if not framecheck.completed():
        print("Can't recheck before you check.")
        return
    leftbreak = int(slider_left.get())
    rightbreak = int(slider_right.get())
    lists = framecheck.generate_lists(leftbreak, rightbreak)
    put_text(lists)

def put_text(lists):
    dir_contents = lists[0]
    frames_expected = lists[1]
    frames_found = lists[2]
    frames_missing = lists[3]

    filename = framecheck.filename
    leftbreak = framecheck.leftbreak
    rightbreak = framecheck.rightbreak
    sequentials = framecheck.sequentials
    slidelength = len(filename)

    print slidelength
    slider_left.config(to=slidelength)
    slider_right.config(to=slidelength)
    slider_left.set(leftbreak)
    slider_right.set(rightbreak)
    nameleft.config(text=filename[0:leftbreak], bg='white')
    nameseq.config(text=sequentials, bg='DodgerBlue')
    nameright.config(text=filename[rightbreak:], bg='white')

    dirconts.delete(0.0, tk.END)
    expFrames.delete(0.0, tk.END)
    foundFrames.delete(0.0, tk.END)
    missingFrames.delete(0.0, tk.END)

    for i in dir_contents:
        dirconts.insert(tk.END, str(i) + '\n')

    for i in frames_expected:
        expFrames.insert(tk.END, str(i) + '\n')

    for i in frames_found:
        foundFrames.insert(tk.END, str(i) + '\n')

    for i in frames_missing:
        missingFrames.insert(tk.END, str(i) + '\n')

    if not frames_missing:
        missingFrames.insert(tk.END, 'None')
    
def update_sliders():
    if not framecheck.filename:
        return
    else:
        filename = framecheck.filename

    leftbreak = int(slider_left.get())
    rightbreak = int(slider_right.get())
    sequentials = filename[leftbreak:rightbreak]
    nameleft.config(text=filename[0:leftbreak], bg='white')
    nameseq.config(text=sequentials, bg='DodgerBlue')
    nameright.config(text=filename[rightbreak:], bg='white')






#GUI elements
outerframe = tk.Frame(cf_window)
outerframe.pack(padx=10, pady=10)

jobButtonBlock = tk.Frame(outerframe)
jobButtonBlock.pack()

tk.Label(jobButtonBlock, text='Existing Job:').pack(side=tk.LEFT)
ttk.Radiobutton(jobButtonBlock, text='None', variable=checkjob, value=0, 
    command=lambda: select_job(0)).pack(side=tk.LEFT)
ttk.Radiobutton(jobButtonBlock, text='1', variable=checkjob, value=1, 
    command=lambda: select_job(1)).pack(side=tk.LEFT)

tk.Label(outerframe, text='Directory to check:').pack()
tk.Entry(outerframe, width=50, textvariable=check_path).pack()

tk.Label(outerframe, text='Start frame:').pack()
tk.Entry(outerframe, width=20, textvariable=check_startframe).pack()

tk.Label(outerframe, text='End frame:').pack()
tk.Entry(outerframe, width=20, textvariable=check_endframe).pack()

nameleft = tk.Label(outerframe)
nameleft.pack()
nameseq = tk.Label(outerframe)
nameseq.pack()
nameright = tk.Label(outerframe)
nameright.pack()

slider_left = ttk.Scale(outerframe, from_=0, to=100, orient=tk.HORIZONTAL, 
    length=300, command=lambda x: update_sliders())
slider_left.pack()
slider_right = ttk.Scale(outerframe, from_=0, to=100, orient=tk.HORIZONTAL, 
    length=300, command=lambda x: update_sliders())
slider_right.pack()

ttk.Button(outerframe, text='OK', command=recheck_directory).pack()

outputframe = tk.LabelFrame(outerframe)
outputframe.pack(padx=5, pady=5)

dirconts = st.ScrolledText(outputframe, width=20, height=5)
dirconts.pack(side=tk.LEFT)

expFrames = st.ScrolledText(outputframe, width=20, height=5)
expFrames.pack(side=tk.LEFT)

foundFrames = st.ScrolledText(outputframe, width=20, height=5)
foundFrames.pack(side=tk.LEFT)

missingFrames = st.ScrolledText(outputframe, width=20, height=5)
missingFrames.pack(side=tk.LEFT)

ttk.Button(outerframe, text='Start', command=check_directory).pack()










cf_window.mainloop()
