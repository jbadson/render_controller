#command line interface for IGP Render Controller
#must run in python 3

'''THIS MODULE IS NOT CURRENTLY WORKING. I'LL UPDATE IT TO USE THE CURRENT
CLIENT-SERVER PROTOCOL AS SOON AS I GET THE GUI SQUARED AWAY.'''

import sys
import socket

print(sys.argv)

host = 'localhost'
port = 2020


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

def get_status(job):
    '''Gets status for a given job.'''

    command = 'get_status'
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(bytes(command, 'UTF-8'))
    reply = s.recv(4096)
    if reply:
        statdict = eval(reply.decode('UTF-8'))
    else:
        return
    s.close()

    #now parse the dict
    if not job in statdict:
        print('Invalid job number, try again.')
        return
    if not statdict[job]:
        print('Queue slot ' + str(job) + ' is empty.')
        return
    data = statdict[job]
    path = data['path']
    start = data['startframe']
    end = data['endframe']
    extras = data['extraframes']
    complist = data['complist']
    #render_engine = data['render_engine']
    status = data['status']
    progress = data['progress']
    compstatus = data['compstatus']

    print('\nJob:\t' + str(job) + '\t|\tStatus: ' + status + '\t|\t' 
            + str(round(progress, 2)) + '% complete')
    print('-' * 70)
    print('Frames ' + str(start) + '-' + str(end) + ' + ' +str(extras))
    print('Path: ' + path)
    print('Rendering on:')
    for comp in complist:
        print(comp + '\t | Frame: ' + str(compstatus[comp]['frame']) + '\t | ' +
                str(round(compstatus[comp]['progress'], 2)) + '%')
    print('-' * 70 + '\n')


helpstring = (
                'IGP Render Controller Command Line Interface\n' +
                'Arguments and options:\n' +
                '-p         :path to file for rendering\n' +
                '-s         :start frame\n' +
                '-e         :end frame\n' +
                '-c         :list of computers to render on\n' +
                '--status   :get status for a given job number\n'
                )

required_args = ['-p', '-s', '-e', '-c']
render_args = {} 
job = None

#if command line options have been specified, parse them
if len(sys.argv) > 1:
    #check that all required arguments are present, then start a render
    #for i in required_args:
    #    if not i in sys.argv:
    #        print('Missing required argument. Do it again.')
    #        print(helpstring)
    #        quit()

    for i in range(len(sys.argv)):
        if sys.argv[i] == '-h' or sys.argv[i] == '--help':
            print(helpstring)
            raise SystemExit

        elif sys.argv[i] == '-p':
            render_args['path'] = sys.argv[i+1]
        elif sys.argv[i] == '-s':
            render_args['start'] = sys.argv[i+1]
        elif sys.argv[i] == '-e':
            render_args['end'] = sys.argv[i+1]
        elif sys.argv[i] == '-c':
            render_args['computers'] = sys.argv[i+1]
        elif sys.argv[i] == '--status':
            job = int(sys.argv[i+1])

    if render_args:
        print(render_args)
        send_command('cmd_render', kwargs=render_args)
    elif job != None:
        print('Attempting to get status for job ' + str(job))
        get_status(job)
