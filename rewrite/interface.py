#command line interface for IGP Render Controller
#must run in python 3
import sys
import socket

print(sys.argv)

host = 'localhost'
port = 2020

#defunct
def send_command_old(function, args):
    '''Creates a socket to start a render.
    args must be passed as a string'''
    command = function + '(' + args + ')'
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bytes(command, 'UTF-8'))
    reply = s.recv(4096)
    print('Response form server: ', reply)
    s.close()


def send_command(command, kwargs={}):
    '''Passes a dict containing a keyword command and args to the server.
    supplied args should be in a dictionary''' 
    data = command + str(kwargs)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bytes(data, 'UTF-8'))
    #reply = s.recv(4096)
    #print('Response from server: ', reply)
    s.close()


helpstring = (
                'IGP Render Controller Command Line Interface\n' +
                'Arguments and options:\n' +
                '--main          :start main Render Controller process\n' +
                '-p       :path to file for rendering\n' +
                '-s      :start frame\n' +
                '-e        :end frame\n' +
                '-c  :list of computers to render on\n'
                )

required_args = ['-p', '-s', '-e', '-c']
render_args = { 'path':None, 'start':None, 'end':None, 'computers':None }

#if command line options have been specified, parse them
if len(sys.argv) > 1:
    #check that all required arguments are present, then start a render
    for i in required_args:
        if not i in sys.argv:
            print('Missing required argument. Do it again.')
            print(helpstring)
            quit()

    for i in range(len(sys.argv)):
        if sys.argv[i] == '-p':
            render_args['path'] = sys.argv[i+1]
        elif sys.argv[i] == '-s':
            render_args['start'] = sys.argv[i+1]
        elif sys.argv[i] == '-e':
            render_args['end'] = sys.argv[i+1]
        elif sys.argv[i] == '-c':
            render_args['computers'] = sys.argv[i+1]

    #render_args = str(render_args)
    print(render_args)
    send_command('cmd_render', kwargs=render_args)
