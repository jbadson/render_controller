# EZ-batch render script version 2.0
#by Eric Lobato 08/28/2013 for Terragen
#Working and Tested
import os
import Queue
from threading import Thread
######VARIABLES FOR CHANGING######

print ("\n\n****Important! All computers must be running the same version of Terragen. Update all machines to the latest version before starting any long renders.****\n")

path = raw_input ('Absolute path to terragen file: ')

startframe = int(raw_input ('Start frame: '))

endframe = int(raw_input('End frame: '))

machines = raw_input ('Machines (use all, fast, slow, or specifiy individually): ')

if machines == 'all':
	ComputerList = ['massive', 'sneffels', 'the-holy-cross', 'bierstadt', 'sherman', 'eldiente', 'lindsey', 'humberto', 'wetterhorn', 'lincoln', 'snowmass', 'tabeguache' ]
else:
	if machines == 'slow':
		ComputerList = ['lindsey', 'wetterhorn', 'lincoln', 'snowmass', 'humberto', 'tabeguache', 'eldiente' ]
	else:
		if machines == 'fast':
			ComputerList = ['massive', 'sneffels', 'the-holy-cross', 'bierstadt', 'sherman' ]
		else:
			ComputerList = str.split(machines)

print ("\nThe script will render frames %s to %s on: " % (startframe, endframe))
print ', '.join(ComputerList)

confirm = raw_input ('Proceed? (Y/n): ')

print ("\n\n")

if confirm != 'Y':
	quit()

print ("Doing stuff... \n\n")

######SCRIPT STUFF######

q= Queue.Queue(endframe-startframe+1)
for i in range(startframe, endframe+1): q.put(str(i))

def render(computername):
	while not q.empty():
		#if computer is mac use mac version of terragen
		macs = ['massive', 'sneffels', 'sherman', 'the-holy-cross' ]
		if computername in macs:
			#command for macs
			os.system("ssh igp@" + computername + " /./mnt/data/software/terragen3/terragen3_mac/terragen3.app/Contents/MacOS/Terragen_3 -p "+ str(path) + " -exit -r -f " + q.get() + " & wait")
                        q.task_done()
		else:
			#print computername
			# /./mnt/data/software/terragen3/Terragen3-Linux-30070/terragen -p +"filepath -exit -r  startframe-endframe"
			os.system("ssh igp@" + computername + " /./mnt/data/software/Terragen3-Linux-30110/terragen -p "+ str(path) + " -exit -r -f " + q.get() + " & wait")  
			q.task_done()

def computers():
	for i in ComputerList:   
 		try: 
    			Thread(target=render, args=(i,)).start()
		except Exception, errtxt:
			print errtxt

computers()
######################################
