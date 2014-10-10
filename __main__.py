#!/usr/local/bin/python3

'''IGP Render Controller Version 5'''


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


import sys
import server
import gui

helptext = (
'IGP Render Controller\n'
'Execute with no options to start the GUI client.\n'
'-s --server\tStart the server.\n'
'-h --help\tDisplay this help message.\n'
)

if '--server' in sys.argv or '-s' in sys.argv:
    renderserver = server.Server()
elif '-h' in sys.argv or '--help' in sys.argv:
    print(helptext)
else:
    masterwin = gui.MasterWin()
    masterwin.mainloop()


