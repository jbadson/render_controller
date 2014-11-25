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

import socket
import json
import ast
import argparse


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
        #var to contain all current server job attributes
        self.serverjobs = ClientSocket().send_cmd('get_attrs')
        #now need a list with integer job IDs to make it easier to select jobs
        #from the command line
        self.job_ids = sorted(self.serverjobs.keys())
        #remove the metadata
        self.job_ids.remove('__STATEVARS__')


    def list_all(self):
        print('\nListing all jobs on %s:%s' 
              %(ClientSocket.HOST, ClientSocket.PORT))
        print('ID\tFilename')
        print('-'*60)
        for i in range(len(self.job_ids)):
            print('%s:\t%s' %(i, self.job_ids[i]))

    def print_job_stats(self, job_id):
        index = self.job_ids[job_id]
        job = self.serverjobs[index]
        elapsed, avg, remaining = job['times']
        print('\nFilename\t\tStatus\t\tProgress (%)\tElapsed\tAvg.\tRemaining')
        print('-'*60)
        print('%s\t%s\t\t%s\t\t%s\t%s\t%s' 
              %(index, job['status'], job['progress'], elapsed, avg, remaining))

    def print_comp_status(self, job_id):
        index = self.job_ids[job_id]
        #job = self.serverjobs[index]
        cs = self.serverjobs[index]['compstatus']
        self.print_job_stats(job_id)
        print('\nComputer\tFrame\tProgress\tActive\tError')
        print('-'*60)
        for comp in self.serverjobs[index]['complist']:
            #print(comp)
            #print(cs[comp])
            print('%s\t%s\t%s\t%s\t%s' 
                  %(comp, cs[comp]['frame'], cs[comp]['progress'], 
                  cs[comp]['active'], cs[comp]['error']))




        




if __name__ == '__main__':
    cli = Cli()
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', default=False, 
        dest='listall', help='List all items in render queue.')
    parser.add_argument('--jstat', action='store', default=-1,
        dest='jstat', help='Print basic status info for job with given ID.',
        metavar='ID', type=int)
    parser.add_argument('--comps', action='store', default=-1, dest='compstat',
        metavar='ID', type=int, help='List all computers with their assigned '
        'frames and progress for a given job ID')

    args = parser.parse_args()
    print('ARGS:', args)

    if args.listall:
        cli.list_all()
    if args.jstat >= 0:
        cli.print_job_stats(args.jstat)
    if args.compstat >= 0:
        cli.print_comp_status(args.compstat)






