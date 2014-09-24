#!/usr/local/bin/python3

'''IGP Render Controller Version 5'''
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


