#graphical user interface for IGP Render Controller
#must run in python 3
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as tkfont
import tkinter.filedialog as tk_filedialog
import tkinter.messagebox as tk_msgbox
import socket

host = 'localhost'
port = 2020


def send_command(function, args):
    '''Creates a socket to start a render.
    args must be passed as a string'''
    command = function + '(' + args + ')'
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bytes(command, 'UTF-8'))
    reply = s.recv(4096)
    print('Response form server: ', reply)
    s.close()

#---Instantiate GUI---
root = tk.Tk()
root.geometry('800x600')

#---Tkinter variables---
tk_path = tk.StringVar()
tk_startframe = tk.StringVar()
tk_endframe = tk.StringVar()
tk_complist = tk.StringVar()

#set some temp defaults
tk_path.set('/mnt/data/test_render/test_render.blend')
tk_startframe.set('1')
tk_endframe.set('1')
tk_complist.set('conundrum')



#---GUI Functions---
def startrender():
    render_args = {
                    'path':tk_path.get(),
                    'start':tk_startframe.get(),
                    'end':tk_endframe.get(),
                    'computers':tk_complist.get(),
                    }

    render_args = str(render_args)
    print(render_args)
    send_command('cmdline_render', render_args)




tk.Entry(root, textvariable=tk_path, width=30).pack()
tk.Entry(root, textvariable=tk_startframe, width=10).pack()
tk.Entry(root, textvariable=tk_endframe, width=10).pack()
tk.Entry(root, textvariable=tk_complist, width=30).pack()
ttk.Button(root, text='Start', command=startrender).pack()


root.mainloop()
