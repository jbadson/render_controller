#Simple server/client classes and methods for the IGP render controller
#Written for Python 3.4
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

#----OVERVIEW----
'''
Client-server command-response protocol:

### Client ###      ### Server ###
send command   -->  receive command
                        |
                    validate command
                        |
receive report <--  report validation
    |
    |
send cmd args  -->  execute command w/args
                        |
                        |
receive result <--  report return string/result

Each connection from a client receives its own instance of ClientThread. This
thread checks the command against a list of valid commands, reports success or
failure of validation to the client, then executes the command with arguments 
supplied as a JSON string. It then reports the 
data returned from the function to the client. This can be a simple 
success/fail indicator, or it can be whatever data the client has requested 
also formatted as a JSON string. JSON was originally used for web portability,
but that's probably not going to happen so it could be removed if needed.

For this reason, there are some rules for functions that directly carry out 
requests from client threads:

    1. The name of the function must be in the allowed_commands list.

    2. The function must return something on completion. It can be any type of 
       object as long as it's compatible with python's json.dumps and 
       json.loads.

'''

import threading
import socket
import json
import ast
import logging

logger = logging.getLogger('rcontroller.socketwrapper')

class Server(object):
    '''Basic server. Listens on specified port. Incoming connections are 
    assigned an instance of ClientThread.'''

    def __init__(self, master, port, allowed_commands):
        '''master: Class that created this object. Defines the namespace for
            methods called by ClientThread in response to received commands.
        allowed_commands: List of commands (function/method names as strings)
            that are allowed to be executed by ClientThread. These must be
            in the namespace of master.'''
        self.master = master
        self.port = port
        self.allowed_commands = allowed_commands

    def start(self):
        '''Binds the port and starts the server main loop.'''
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host = '' #all interfaces
        hostname = socket.gethostname()
        self.sock.bind((host, self.port))
        self.sock.listen(5)
        self.listening = True
        print('Server now running on %s port %s' %(hostname, self.port))
        print('Press Crtl + C to stop...')
        while True:
            try:
                clientsock, address = self.sock.accept()
                client_thread = ClientThread(self.master, clientsock, 
                                             self.allowed_commands)
                client_thread.start()
            except KeyboardInterrupt:
                print('Shutting down server')
                self.sock.close()
                self.listening = False
                return

    def islistening(self):
        '''Returns true if the server's main loop is active.'''
        if self.listening:
            return True
        else:
            return False


class ClientThread(threading.Thread):
    '''Subclass of threading.Thread to handle incoming client connections'''

    def __init__(self, master, sock, allowed_commands):
        '''
        master: Parent class that defines the namespace for the methods 
            executed in response to commands.
        sock: Instance of socket.socket currently in use.
        allowed_commands: List of commands (function/method names as strings)
            that are permitted. These must be in the namespace of master.
        '''
        self.master = master
        self.sock = sock
        self.allowed_commands = allowed_commands
        threading.Thread.__init__(self, target=self._clientthread)

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for client.    
        Message must be compatible with json.dumps/json.loads.'''
        #now converting everything to a json string for web interface 
        #convenience
        message = json.dumps(message)
        msg = bytes(message, 'UTF-8')
        msglen = str(len(msg))
        #first 8 bytes contains message length 
        while len(msglen) < 8:
            msglen = '0' + msglen
        msglen = bytes(msglen, 'UTF-8')
        self.sock.sendall(msglen)
        logger.debug('sending "{}"'.format(msglen))
        self.sock.sendall(msg)
        logger.debug('sending "{}"'.format(msg))

    def _recvall(self):
        '''Receives a message of a specified length, returns original type.'''
        #first 8 bytes contain msg length
        msglen = int(self.sock.recv(8).decode('UTF-8'))
        bytes_recvd = 0
        chunks = []
        while bytes_recvd < msglen:
            chunk = self.sock.recv(2048)
            logger.debug('recv: "{}"'.format(chunk))
            if not chunk:
                break
            chunks.append(chunk.decode('UTF-8'))
            bytes_recvd += len(chunk)
        data = json.loads(''.join(chunks))
        return data

    def _clientthread(self):
        try:
            cmddict = self._recvall()
            command = cmddict['__cmd__']
            #validate command first
            if not command in self.allowed_commands:
                logger.warning('Received invalid request: {}'.format(command))
                return
            args = cmddict['__args__']
            kwargs = cmddict['__kwargs__']
            return_str = eval('self.master.{}'.format(command))(*args, **kwargs)
            #send the return string (T/F for success or fail, or other requested 
            #data)
            self._sendmsg(return_str)
        finally:
            self.sock.close()

class ClientSocket(object):
    '''Wrapper for socket to handle command-response protocol for interacting 
    with server's ClientThread instances.'''

    def __init__(self, host, port):
        self.host = host
        self.port = port

    def setup(self, host, port):
        self.host = host
        self.port = port

    def getaddr(self):
        '''Returns a tuple containing the host and port assigned to the
        instance.'''
        return (self.host, self.port)

    def _recvall(self):
        '''Receives message of specified length, returns it as a string.'''
        #first 8 bytes contain msg length
        msglen = int(self.socket.recv(8).decode('UTF-8'))
        bytes_recvd = 0
        chunks = []
        while bytes_recvd < msglen:
            chunk = self.socket.recv(2048)
            logger.debug('recv: "{}"'.format(chunk))
            if not chunk:
                break
            chunks.append(chunk.decode('UTF-8'))
            bytes_recvd += len(chunk)
        data = json.loads(''.join(chunks))
        return data

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for server.
        Message must be UTF-8 string'''
        msg = bytes(message, 'UTF-8')
        msglen = str(len(msg))
        #first 8 bytes contains message length 
        while len(msglen) < 8:
            msglen = '0' + msglen
        msglen = bytes(msglen, 'UTF-8')
        logger.debug('sending "{}"'.format(msglen))
        self.socket.sendall(msglen)
        logger.debug('sending "{}"'.format(msg))
        self.socket.sendall(msg)

    def send_cmd(self, command, *args, **kwargs):
        '''Sends a command to the server. Command must be a UTF-8 string.
        Positional and keword args are passed as-is.
        Returns a string'''
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd = json.dumps({'__cmd__': command, '__args__': args, '__kwargs__': kwargs})
        try:
            self.socket.connect((self.host, self.port))
            self._sendmsg(cmd)
            return_str = self._recvall()
        finally:
            self.socket.close()
        return return_str
