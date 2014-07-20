#rewrite of check_missing_frames module to simplify and make enqueue extra frames work
from Tkinter import *
import tkFileDialog
import tkMessageBox
import ttk
from os import path, _exit
import ScrolledText as st
import subprocess

#tkinter variables
check_path = StringVar()
check_start = StringVar()
check_end = StringVar()
checkjob = IntVar()

#other global variables
checkframes = dict()

#functions
#check_frames_window <-- opens cfwin toplevel
#put_text <-- happens when job button clicked
#get_framecheck_path <-- browse button
#get_breaks <-- happens when start button invoked
#chkclose <-- happens on crtl+w, close button invoked
#get_slider <-- happens when sliders clicked
#getlist <-- happens when update invoked & at end of get_breaks, enqueue_missing_frames
#enqueue_missing_frames <-- when corresponding button invoked


def parse_filename():
	path = check_path.get()
	dir_contents = subprocess.check_output('ls', path).split()

	for line in dir_contents:
		if line[-3:] in allowed_filetypes:
			filename = line
			name, ext = line.split('.')
			filesok = True #parsable filename was found
			break
		else:
			filesok = False
	if filesok == False: #no parsable filenames were found
		tkMessageBox.showwarning('Error', 'No suitable files found in directory. Check path and try again.')
		return 0, 0

	#traverse filename backwards to avoid non-sequential numbers earlier in filename (assume sequentials always come last)
	n = len(name)
	while n > 0:
		if not name[n].isdigit():
			leftbreak = n + 1
			rightbreak = len(filename) - len(ext) - 1 #assuming sequential #s go to end of name
			break
		n -= 1

	populate_lists(leftbreak, rightbreak, dir_contents=dir_contents)
	return leftbreak, rightbreak
	

def manual_parse():
	try:
		selection = text.get(SEL_FIRST, SEL_LAST)
		leftbreak = filename.find(selection)
		rightbreak = leftbreak + len(selection)
	except:
		tkMessageBox.showwarning('Error', 'No text selected. Select the part of the filename corresponding to the sequential frame number.')
		leftbreak, rightbreak = 0, 0

	populate_lists(leftbreak, rightbreak)
	return leftbreak, rightbreak

def populate_lists(leftbreak, rightbreak, **kwargs):
	if kwargs: #assume kwargs contains dir_contents
		dir_contents = kwarg[0]


##Different idea##
def parse_filename(filename):
	return leftbreak, rightbreak
def parse_manually(filename):
	return leftbreak, rightbreak
def populate_lists(dir_contents, frames_expected, frames_missing)
	return
def main():
	#get dir_contents
	if something in textbox:
		parse_manually()
	else:
		parse_filename()
	populate_lists()
	


def main(): #change name later
	#check if there is anything in filename parsing box
	if filename = str(text.get(0.0, END).strip()):
		leftbreak, rightbreak = parse_manually(check_text)
	else:
		path = check_path.get()
		dir_contents = subprocess.check_output('ls', path).split()

		for line in dir_contents:
			if line[-3:] in allowed_filetypes:
				filename = line
				filesok = True #parsable filename found
				break
			else:
				filesok = False
		if filesok == False:
			tkMessageBox.showwarning('Error', 'No suitable files found in directory. Check path and try again.')
			return

		leftbreak, rightbreak = parse_filename(filename)

		#traverse filename backwards to avoid non-sequential numbers earlier in filename (assume sequentials always come last)
		n = len(name)
		while n > 0:
			if not name[n].isdigit():
				leftbreak = n + 1
				rightbreak = len(filename) - len(ext) - 1 #assuming sequential #s go to end of name
				break
			n -= 1

	

	

cfwin = Toplevel()
cfwin.title('Check for Missing Frames')
cfwin.config(bg='gray90')

Label(cfwin, text='Compare the contents of a directory against a generated file list to search for missing frames.', bg='gray90').grid(row=0, column=0, padx=10, pady=10, sticky=W)

cfframe = LabelFrame(cfwin, bg='gray90')
cfframe.grid(row=1, column=0, padx=10, pady=10)
Label(cfframe, text='Check existing job:', bg='gray90').grid(row=0, column=0, padx=5, pady=5, sticky=E)
bbox = Frame(cfframe)
bbox.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky=W)
ttk.Radiobutton(bbox, text='None', variable=checkjob, value=0, command=put_text, style='Toolbutton').grid(row=0, column=1, sticky=W)

for i in range(1, queueslots + 1):
	if Job(i).checkSlotFree():
		btnstate = 'disabled' #disable job buttons for empty queue slots
	else:
		btnstate = 'normal'
	ttk.Radiobutton(bbox, text=str(i), variable=checkjob, value=i, command=put_text, state=btnstate, style='Toolbutton').grid(row=0, column=i+1, sticky=W)
	
Label(cfframe, text='Directory to check:', bg='gray90').grid(row=1, column=0, padx=5, pady=5, sticky=E)
checkin = Entry(cfframe, textvariable=check_path, width=50, highlightthickness=0)
checkin.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=W)
ttk.Button(cfframe, text='Browse', command=get_framecheck_path).grid(row=1, column=4, padx=5, pady=5, sticky=W)

Label(cfframe, text='Start frame:', bg='gray90').grid(row=2, column=0, padx=5, pady=5, sticky=E)
startent = Entry(cfframe, textvariable=check_start, width=20, highlightthickness=0)
startent.grid(row=2, column=1, padx=5, pady=5, sticky=W)

Label(cfframe, text='End frame:', bg='gray90').grid(row=3, column=0, padx=5, pady=5, sticky=E)
endent = Entry(cfframe, textvariable=check_end, width=20, highlightthickness=0)
endent.grid(row=3, column=1, padx=5, pady=5, sticky=W)

startbtn = ttk.Button(cfframe, text='Start', width=10, command=get_breaks)
startbtn.grid(row=4, column=1, padx=5, pady=5, sticky=W)
cfwin.bind('<Return>', lambda x: startbtn.invoke())
cfwin.bind('<KP_Enter>', lambda x: startbtn.invoke())
cfwin.bind('<Command-w>', lambda x: chkclose())
cfwin.bind('<Control-w>', lambda x: chkclose())


confirmframe = LabelFrame(cfframe, text='Adjust Filename Parsing', bg='gray90')
confirmframe.grid(row=2, rowspan=3 , column=2, columnspan=3, padx=10, pady=5, ipady=5, sticky=W)
Label(confirmframe, text='If filename was parsed incorrectly, select the region containing sequential frame number and click OK.', bg='gray90').grid(row=0, column=0, columnspan=3)

confirmtext = Text(confirmframe, width=30, height=1, relief=GROOVE)
confirmtext.grid(row=0, column=0, padx=10, pady=10)
ttk.Button(confirmframe, text='OK', command=manual_parse).grid(row=1, column=0, padx=10, pady=5)

#nameframe = Frame(confirmframe, bg='gray90', highlightthickness=0)
#nameframe.grid(row=1, column=0, columnspan=3)
#nameleft = Label(nameframe, fg='gray50', highlightthickness=0, bg='gray90')
#nameleft.grid(row=1, column=0, sticky=E)
#
#nameseq = Label(nameframe, fg='white', highlightthickness=0, bg='gray90')
#nameseq.grid(row=1, column=1)
#
#nameright = Label(nameframe, fg='gray50', highlightthickness=0, bg='gray90')
#nameright.grid(row=1, column=2, sticky=W)
#
#slider_left = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, length=300, command=lambda x: get_slider())
#slider_left.grid(row=2, column=0, columnspan=3)
#
#slider_right = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, length=300, command=lambda x: get_slider())
#slider_right.grid(row=3, column=0, columnspan=3)

#ttk.Button(confirmframe, text='Update', command=getlist).grid(row=4, column=0, columnspan=3)
	

	
resultframe = LabelFrame(cfframe, text='Result', bg='gray90')
resultframe.grid(row=5, column=0, columnspan=5, padx=10, pady=5, ipady=5)

Label(resultframe, text='Directory contents:', bg='gray90').grid(row=0, column=0, padx=5, sticky=W)
dirconts = st.ScrolledText(resultframe, width=38, height=10, highlightthickness=0, bd=4) #directory contents
dirconts.frame.config(border=2, relief=GROOVE)
dirconts.grid(row=1, column=0, padx=5, sticky=W)

Label(resultframe, text='Found:', bg='gray90').grid(row=0, column=1, padx=5, sticky=W)
foundfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #found frame numbers after parsing
foundfrms.frame.config(border=2, relief=GROOVE)
foundfrms.grid(row=1, column=1, padx=5, sticky=W)

Label(resultframe, text='Expected:', bg='gray90').grid(row=0, column=2, padx=5, sticky=W)
expfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #expected frames
expfrms.frame.config(border=2, relief=GROOVE)
expfrms.grid(row=1, column=2, padx=5, sticky=W)

Label(resultframe, text='Missing:', bg='gray90').grid(row=0, column=3, padx=5, sticky=W)
missfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #missing frames
missfrms.frame.config(border=2, relief=GROOVE)
missfrms.grid(row=1, column=3, padx=5, sticky=W)

#ttk.Button(cfframe, text='Send frames to queue', command=enqueue_missing_frames, style='Toolbutton').grid(row=6, column=3, padx=10, pady=5, sticky=E)
ttk.Button(cfframe, text='Close', command=chkclose, style='Toolbutton').grid(row=6, column=4, padx=10, pady=5, sticky=E)
