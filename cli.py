#command line interface for IGP Render Controller
#must run in python 3

'''
#####################################################################
Copyright 2014 James Adson

This file is part of IGP Render Controller.  
IGP Render Controller is free software: you can redistribute it 
and/or modify it under the terms of the GNU General Public License 
as published by the Free Software Foundation, either version 3 of 
the License, or any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
#####################################################################
'''

'''THIS MODULE IS NOT CURRENTLY WORKING. I'LL UPDATE IT TO USE THE CURRENT
CLIENT-SERVER PROTOCOL AS SOON AS I GET THE GUI SQUARED AWAY.'''

import sys
import socket
import json
import ast

print(sys.argv)

class ClientSocket(object):
    '''Wrapper for socket to handle command-response protocol for interacting 
    with the render controller server.'''
    HOST = 'localhost'
    PORT = 2020

    def setup(host, port):
        ClientSocket.HOST = host
        ClientSocket.PORT = port

    def __init__(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((ClientSocket.HOST, ClientSocket.PORT))

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
        data = json.loads(''.join(chunks))
        return data

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for server.
        Message must be compatible with json.dumps/json.loads.'''
        #now doing everything in json for web interface convenience
        message = json.dumps(message)
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
        if not command == 'get_attrs': print('sending command', command) #debug
        self._sendmsg(command)
        #check that the command was valid
        cmd_ok = ast.literal_eval(self._recvall())
        if not cmd_ok:
            return 'Invalid command'
        #if command was valid, send associated arguments
        if not command == 'get_attrs': print('sending kwargs', str(kwargs))
        self._sendmsg(kwargs)
        #collect the return string (True/False for success/fail or requested data)
        return_str = self._recvall()
        if not command == 'get_attrs': print('received return_str', return_str)
        self.socket.close()
        return return_str

def cmdtest():
    '''a basic test of client server command-response protocol'''
    command = 'cmdtest'
    kwargs = {'1':'one', '2':'two'}
    return_str = ClientSocket().send_cmd(command, kwargs)
    print(return_str)


class Cli(object):
    '''Master object for command line interface.'''

    def __init__(self):
        self.serverjobs = self.get_all()

    def get_all(self):
        '''Gets all attributes for all jobs on server.'''
        serverjobs = ClientSocket().send_cmd('get_attrs')
        return serverjobs

    def list_jobs(self):
        '''Returns a list of all jobs on the server.'''
        jobs = []
        for job in self.serverjobs.keys():
            if not job == '__STATEVARS__':
                jobs.append(job)
        return jobs

    def print_job_stats(self, job_id):
        '''Returns a list of key stats about a given job ID

        start, end, path, status, progress'''

        if not job_id in self.serverjobs:
            print('Job ID not found.')
            return
        else:
            job = self.serverjobs[job_id]
        print('Filename: %s\tStatus: %s\tProgress: %s' % (job_id, job['status'], job['progress']))
        print('Start: %s\tEnd: %s\tExtra frames: %s' % (job['startframe'], 
              job['endframe'], job['extraframes']))
        #print(


        

#---------CLI STUFF---------
helpstring = (
                'IGP Render Controller Command Line Interface\n' +
                'Arguments and options:\n' +
                '-p         :path to file for rendering\n' +
                '-s         :start frame\n' +
                '-e         :end frame\n' +
                '-c         :list of computers to render on\n' +
                '--status   :get status for a given job number\n'
                )


if __name__ == '__main__':
    reply = ClientSocket().send_cmd('cmdtest')
    print(reply)
    cli = Cli()
    for i in cli.list_jobs():
        cli.print_job_stats(i)

'''
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
'''
