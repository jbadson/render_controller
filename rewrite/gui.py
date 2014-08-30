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
        print('sending msglen:', msglen, 'msg:', msg) #debug
        self.socket.sendall(msglen)
        self.socket.sendall(msg)

    def send_cmd(self, command, kwargs={}):
        '''Sends a command to the server. Command must be a UTF-8 string.
        Associated args should be supplied as a dict. Returns a string'''
        #send command first, wait for response, then send args
        print('sending command', command) #debug
        self._sendmsg(command)
        #check that the command was valid
        cmd_ok = ast.literal_eval(self._recvall())
        if not cmd_ok:
            return 'Invalid command'
        #if command was valid, send associated arguments
        print('sending kwargs', str(kwargs))
        self._sendmsg(str(kwargs))
        #collect the return string (True/False for success/fail or requested data)
        return_str = self._recvall()
        print('received return_str', return_str)
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

def enqueue():
    '''Enqueues a job on the server.'''
    #XXX INPUTS MUST BE THE CORRECT TYPE
    index = 1
    path = '/mnt/data/test_render/test_render.blend'
    startframe = 1
    endframe = 2
    extraframes = []
    render_engine = 'blender'
    complist = ['conundrum']

    if not check_slot_open(index):
        print('Queue slot already occupied.')
        return

    render_args = { 'index':index,
                    'path':path, 
                    'startframe':startframe,
                    'endframe':endframe, 
                    'extraframes':extraframes, 
                    'render_engine':render_engine,
                    'complist':complist }
    reply = ClientSocket().send_cmd('enqueue', render_args)
    print(reply)

    
cmdtest()
#get_all_attrs()

#testing that it correctly identifies full queue slot and doesn't overwrite
enqueue()
time.sleep(2)
enqueue()
