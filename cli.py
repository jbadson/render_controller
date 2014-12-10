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
        self.statevars = self.job_ids
        self.job_ids.remove('__STATEVARS__')
        self.job_ids.remove('__MESSAGE__')
        self.fprint = FPrinter() #formatted printer object


    def list_jobs(self):
        print('Listing all jobs on %s:%s\n' 
              %(ClientSocket.HOST, ClientSocket.PORT))
        self.fprint.jlist_header()
        for i in range(len(self.job_ids)):
            fname = self.job_ids[i]
            status = self.serverjobs[fname]['status']
            prog = self.serverjobs[fname]['progress']
            self.fprint.jlist(i, fname, status, prog)

    def print_single_job(self, job_id):
        print('Full status info for ID %s\n' %job_id)
        self._print_job_stats(job_id)

    def list_all(self):
        print('Printing full status info for all jobs on %s:%s' 
              %(ClientSocket.HOST, ClientSocket.PORT))
        for i in range(len(self.job_ids)):
            self.fprint.job_separator(i)
            self._print_job_stats(i)

    def _print_job_stats(self, job_id):
        index = self.job_ids[job_id]
        job = self.serverjobs[index]
        elapsed, avg, remaining = job['times']
        self.fprint.jobsummary(index, job['status'], job['progress'], elapsed, 
                               avg, remaining)
        print('\nComputer status info:\n')
        self.fprint.complist_header()
        for comp in self.serverjobs[index]['complist']:
            cs = self.serverjobs[index]['compstatus'][comp]
            self.fprint.complist(comp, cs['frame'], cs['progress'], cs['active'],
                                 cs['error'])

    def test(self):
        print('test thingy done')





class FPrinter(object):
    '''Prints formatted data to stdout.'''

    def format_time(self, time):
        '''Converts time in decimal seconds to human-friendly strings.
        format is ddhhmmss.s'''
        if time < 60:
            newtime = [round(time, 1)]
        elif time < 3600:
            m, s = time / 60, time % 60
            newtime = [int(m), round(s, 1)]
        elif time < 86400:
            m, s = time / 60, time % 60
            h, m = m / 60, m % 60
            newtime = [int(h), int(m), round(s, 1)]
        else:
            m, s = time / 60, time % 60
            h, m = m / 60, m % 60
            d, h = h / 24, h % 24
            newtime = [int(d), int(h), int(m), round(s, 1)]
        if len(newtime) == 1:
            timestr = str(newtime[0])+'s'
        elif len(newtime) == 2:
            timestr = str(newtime[0])+'m '+str(newtime[1])+'s'
        elif len(newtime) == 3:
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m ' +
                       str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h ' + 
                       str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr

    def jobsummary(self, filename, status, progress, time_elapsed, 
                   time_avg, time_remaining):    
        header = ('Filename', 'Status', 'Progress', 'Elapsed', 'Avg./Fr.',
                  'Remaining')
        formatstr = '{:<20} {:<10} {:<9} {:<10} {:<10} {:<10}'

        etime = self.format_time(time_elapsed)
        avtime = self.format_time(time_avg)
        remtime = self.format_time(time_remaining)
        print(formatstr.format(*header))
        print('-'*70)
        print(formatstr.format(filename, status, round(progress, 1), etime, 
              avtime, remtime))

    def jlist_header(self):
        formatstr = '{:<4} {:<30} {:<10} {:<10}'
        print(formatstr.format('ID', 'Filename', 'Status', 'Progress'))
        print('-'*70)

    def jlist(self, job_id, filename, status, progress):
        formatstr = '{:<4} {:<30} {:<10} {:<10}'
        print(formatstr.format(job_id, filename, status, round(progress, 1)))

    def complist_header(self):
        formatstr = '{:<20} {:<10} {:<10} {:<10} {}'
        print(formatstr.format('Computer', 'Frame', 'Progress', 'Active', 'Error'))
        print('-'*70)

    def complist(self, computer, frame, progress, active, error):
        formatstr = '{!s:<20} {!s:<10} {!s:<10} {!s:<10} {}'
        print(formatstr.format(computer, frame, progress, active, error))

    def job_separator(self, job_id):
        print('\n%s ID: %s %s' %('#'*30, job_id, '#'*30))



        




if __name__ == '__main__':
    cli = Cli()
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', default=False, 
        dest='joblist', help='List all items in render queue.')
    parser.add_argument('--listall', action='store_true', default=False,
        dest='listall', help='Print full status info for all jobs in queue.')
    parser.add_argument('--stats', action='store', default=-1,
        dest='jstat', help='Print full status info for job with given ID.',
        metavar='ID', type=int)
    parser.add_argument('--test', action='store_true', default=False,
        dest='test', help='Test feature. Does whatever I need it to.')
    #parser.add_argument('--comps', action='store', default=-1, dest='compstat',
    #    metavar='ID', type=int, help='List all computers with their assigned '
    #    'frames and progress for a given job ID')

    args = parser.parse_args()

    if args.joblist:
        cli.list_jobs()
    if args.jstat >= 0:
        cli.print_single_job(args.jstat)
    if args.listall:
        cli.list_all()
    if args.test:
        cli.test()
    #if args.compstat >= 0:
    #    cli.print_comp_status(args.compstat)






