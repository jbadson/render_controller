#command line interface for IGP Render Controller

import sys
import socket

print(sys.argv)

host = 'localhost'
port = 2020


def send_command(function, args):
    '''Creates a socket to start a render.
    args must be passed as a string'''
    command = function + '(' + args + ')'
    print('Attempting to send command: ' + command)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.send(bytes(command, 'UTF-8'))


helpstring = (
                'IGP Render Controller Command Line Interface\n' +
                'Arguments and options:\n' +
                '--main          :start main Render Controller process\n' +
                '--path       :path to file for rendering\n' +
                '--start      :start frame\n' +
                '--end        :end frame\n' +
                '--computers  :list of computers to render on\n'
                )

required_args = ['--path', '--start', '--end', '--computers']
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
        if sys.argv[i] == '--path':
            render_args['path'] = sys.argv[i+1]
        elif sys.argv[i] == '--start':
            render_args['start'] = sys.argv[i+1]
        elif sys.argv[i] == '--end':
            render_args['end'] = sys.argv[i+1]
        elif sys.argv[i] == '--computers':
            render_args['computers'] = sys.argv[i+1]

    render_args = str(render_args)
    print(render_args)
    send_command('cmdline_render', render_args)
