#Fourth major revision of IGP render controller by Jim Adson
#Core render module based on original renderscript by Eric Lobato

import Queue
import subprocess
from threading import Thread, RLock 
from Tkinter import *
import time
import tkMessageBox
import tkFileDialog
import tkFont
import ttk
from os import path, _exit
import ScrolledText as st



class Job(object):
	'''represents a render job in a single queue slot'''

	def __init__(self, index):
		'''populate all variables for a given index from the global renderJobs dict'''
		self.index = index
		self.render_data = renderJobs[self.index]
		self.path = renderJobs[self.index][0]
		self.startframe = renderJobs[self.index][1]
		self.endframe = renderJobs[self.index][2]
		self.extraframes = renderJobs[self.index][3]
		self.computerList = renderJobs[self.index][4]
		self.threads = renderJobs[self.index][5]
		self.currentFrames = renderJobs[self.index][6]
		self.totalFrames = renderJobs[self.index][7]
		self.status = renderJobs[self.index][8]
		self.termout = renderJobs[self.index][10]
		self.timestart = renderJobs[self.index][11]

		if killflags[self.index] == 1:
			self.status = 'Stopped'


	def checkSlotFree(self):
		'''returns true if the specified queue slot is empty'''

		if self.path == '':
			return True
		else:
			return False


	def update(self):
		'''updates global renderJobs and self.render_data'''

		with threadlock:
			self.render_data = [self.path, self.startframe, self.endframe, self.extraframes, self.computerList, self.threads, self.currentFrames, self.totalFrames, self.status, self.index, self.termout, self.timestart]
		with threadlock:
			renderJobs[self.index] = self.render_data



	def clear(self):
		'''removes a job from the queue and clears all dictionary fields'''

		threadlock.acquire()
		self.path = ''
		self.startframe = 0
		self.endframe = 0
		self.extraframes = []		
		self.computerList = []
		self.threads = {}
		self.currentFrames = {}
		self.totalFrames = []
		self.status = 'Empty'
		self.termout = ''
		self.timestart = ''
		self.update()
		threadlock.release()

		Status(self.index).purgeGlobalJobstat()
		Status(self.index).clearAllBoxes()
		RenderTimer(self.index).clear()

		with threadlock:
			killflags[self.index] = 0

		if self.status == 'Stopped':
			while not queue['q'+str(self.index)].empty(): #flush the queue
				with threadlock:
					queue['q'+str(self.index)].get()
				with threadlock:
					queue['q'+str(self.index)].task_done()



	def enqueue(self):
		'''adds a new job to an open queue slot, or overwrites an existing job'''

		if not self.checkSlotFree(): 
			if self.status == 'Rendering':
				Dialog(3).warn()
				return False
			if self.status == 'Stopped':
				Dialog(14).warn()
				return False
			if not Dialog(2).confirm():
				return False
			if self.status == 'Finished':
				self.clear()

		if not pathInput.get():
			Dialog(5).warn()
			return False


		
		self.path = pathInput.get()
		if not path.exists(self.path): 
			Dialog(10).warn()
			return False


		try:
			self.startframe = int(startInput.get())
			self.endframe = int(endInput.get())
		except:
			Dialog(1).warn()
			return False


		if not self.endframe >= self.startframe:
			Dialog(4).warn()
			return False

		self.extraframes = []
		for frame in extrasInput.get().split():
			try:
				if frame != 0:
					self.extraframes.append(int(frame))
			except:
				Dialog(7).warn()
				return False

		if self.extraframes != []:
			for i in self.extraframes:
				if i-1 in range(self.endframe - self.startframe + 1):
					Dialog(2).warn()
					return False

		self.computerList = [] #complicated because comp names have to be strings but vars can't
		for i in range(len(compvars)):
			if compvars[i].get():
				self.computerList.append(computers[i])

		if self.computerList == []:
			Dialog(5).warn()
			return False

		for computer in self.computerList:
			if computer in extracomps: #confirm that extra computers are available
				if not Dialog(4).confirm():
					return False

		for i in range(self.startframe, self.endframe + 1 + len(self.extraframes)):
			self.totalFrames.append(0) #fill totalFrames list with zeros so that len(totalFrames) returns total number to be rendered. Used for calculating percent complete.


		with threadlock:
			killflags[self.index] = 0 #reset killflag just in case

		self.status = 'Waiting'
		self.update()
		return True


	def render(self):
		'''creates a queue of frames and assigns them to RenderThreads()'''

		if self.status != 'Waiting':
			Dialog(8).warn()
			return

		self.status = 'Rendering'
		RenderTimer(self.index).start()
		RenderLog(self.index).render_started()

		with threadlock:
			queue['q'+str(self.index)] = Queue.LifoQueue(0) #Last-in First-out queue, no max size
	
		framelist = range(self.startframe, self.endframe + 1)
		framelist.reverse() #Reverse order for LifoQueue

		for frame in framelist:
			with threadlock:
	        		queue['q'+str(self.index)].put(frame)

		if len(self.extraframes) > 0:
			self.extraframes.reverse() #render lower frame numbers first
			for frame in self.extraframes:
				with threadlock:
					queue['q'+str(self.index)].put(frame)

		self.update()
		global skiplists
		with threadlock:
			skiplists[self.index] = []

		def masterthread(): #master thread to control RenderThreads 
			global compflags

			#---RENDER LOOP---
			while not queue['q'+str(self.index)].empty():
				if killflags == 1:
					break
			
				self.computerList = renderJobs[self.index][4]
				for computer in self.computerList:
					if compflags[str(self.index)+'_'+computer] == 0: #no active thread 
						if computer in skiplists[self.index]: #skip flag raised
							continue
						elif queue['q'+str(self.index)].empty(): #break loop if queue becomes empty after a new computer is added
							break
						else:
							frame = queue['q'+str(self.index)].get()
				
						with threadlock:
							compflags[str(self.index)+'_'+computer] = 1 #set compflag as active
							#moving add currentFrames here b/c of multple renderthread sending issue.
							self.currentFrames[computer] = [frame, time.time()] #add to currentFrames & start timeout timer
							renderJobs[self.index][6] = self.currentFrames 
				
						RenderThread(self.index, self.path, computer, frame).create()
						#if skiplists[self.index]:
						#	with threadlock:
						#		skiplists[self.index].pop(0) #remove oldest entry from skip list
			
					else: #if thread is active on computer or computer was skipped
						if not computer in self.currentFrames: #computer has not been sent a frame 
							with threadlock:
								compflags[str(self.index)+'_'+computer] = 0 #reset compflag, send back to loop
							time.sleep(0.01)
							continue
			
						else: #computer has been sent a frame
							if time.time() - self.currentFrames[computer][-1] > timeout: #timeout exceeded
								frame = self.currentFrames[computer][0]
								print('ERROR:Job:'+str(self.index)+'|Fra:'+str(frame)+'|'+computer+'|Timed out in render loop. Retrying')
								RenderLog(self.index).error(computer, frame, 3, '') #error code 3, no output line
								with threadlock:
									skiplists[self.index].append(computer) #add computer to skiplist
								try:
									subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)
								except: #skip kill command if threads entry is blank (ssh timeout)
									pass
								with threadlock:
									queue['q'+str(self.index)].put(frame) #return frame to queue
									compflags[str(self.index)+'_'+computer] = 0 #reset compflag to try again on next round
									del self.currentFrames[computer] #remove currentFrames entry
					time.sleep(0.01)
			
			#---FINISH LOOP---
			#Waits for remaining renders to finish, catches any errors
			while queue['q'+str(self.index)].empty():
				if killflags[self.index] == 1:
					break
			
				self.currentFrames = renderJobs[self.index][6] #force update of currentFrames
				if not self.currentFrames: #break loop if all frames have been returned (RenderThread deletes currentFrames entry when frame is saved)
					break
			
				for computer in self.currentFrames: #timeout function for remaining renders
					if self.currentFrames[computer][0] in self.totalFrames: #terminate loop if frame is finished (fixes re-entrant loop fuckery)
						del self.currentFrames[computer]
						break

					if time.time() - self.currentFrames[computer][-1] > timeout:
						frame = self.currentFrames[computer][0]
						print('ERROR:Job:'+str(self.index)+'|Fra:'+str(frame)+'|'+computer+'|Timed out in finish loop. Retrying')
						RenderLog(self.index).error(computer, frame, 3, '') #error code 3, no output line
						with threadlock:
							skiplists[self.index].append(computer)
						try:
							subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)
						except: #skip kill command if threads entry is blank (ssh timeout)
							pass
			
						with threadlock:
							queue['q'+str(self.index)].put(self.currentFrames[computer][0])
							compflags[str(self.index)+'_'+computer] = 0
							del self.currentFrames[computer]
						time.sleep(0.01)
						break #force restart of for loop b/c len(self.currentFrames) changed during iteration

				time.sleep(0.01)
			
			if not queue['q'+str(self.index)].empty(): #catch any frames that were returned to queue in finish loop
				stragglers = Thread(target=masterthread, args=())
				stragglers.start()

			else: #Render is done, clean up
				print('Job:'+str(self.index)+'|Finished rendering.')
				RenderLog(self.index).render_finished()
				self.status = 'Finished'
				with threadlock:
					renderJobs[self.index][8] = self.status

				for computer in computers: #reset all compflags
					with threadlock:
						compflags[str(self.index)+'_'+computer] = 0 
				return


		master = Thread(target=masterthread, args=())
		master.start()


	def add_computer(self, comp):
		'''add computer to the render pool'''
		self.comp = comp
		if self.comp in self.computerList: 
			Dialog(12).warn()
			return

		with threadlock:
			renderJobs[self.index][4].append(self.comp)

		print('Job:'+str(self.index)+'|Added '+self.comp+' to the render pool.')



	def remove_computer(self, comp):
		'''remove computer from the render pool'''
		self.comp = comp
		if not self.comp in self.computerList:
			Dialog(13).warn()
			return

		with threadlock:
			renderJobs[self.index][4].remove(self.comp)

		print('Job:'+str(self.index)+'|Removed '+self.comp+' from the render pool.')



	def kill(self):
		'''kills an in-progress render'''

		if self.status != 'Rendering':
			Dialog(9).warn()
			return

		if not Dialog(1).confirm():
			return

		with threadlock:
			killflags[self.index] = 1

		print('Job:'+str(self.index)+'|Render stopped by user.')

		for computer in computers: #prevent any new frames being sent
			with threadlock:
				compflags[str(self.index)+'_'+computer] = 1 

		for computer in self.threads:
			subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)
			subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True) #sending twice b/c stuff is getting missed

		while not queue['q'+str(self.index)].empty(): #flush the queue
			with threadlock:
				queue['q'+str(self.index)].get()
			with threadlock:
				queue['q'+str(self.index)].task_done()
			time.sleep(0.001)

		for computer in computers: #reset compflags
			with threadlock:
				compflags[str(self.index)+'_'+computer] = 0

		RenderLog(self.index).render_killed()

		threadlock.acquire()
		self.status = 'Stopped'
		self.update()
		threadlock.release()



	def kill_thread(self, computer):
		'''kills an individual render thread'''

		if self.status != 'Rendering':
			return

		if not Dialog(6).confirm():
			return

		if not computer in self.threads:
			Dialog(16).warn()
			return

		try:
			frame = self.currentFrames[computer][0]
			with threadlock:
				queue['q'+str(self.index)].put(frame) #return frame to queue
		except:
			print('No thread found to kill.')
			return

		subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)
		subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)

		print('Job:'+str(self.index)+'|Killed process on '+computer+'|Returning frame '+str(frame)+' to queue.')
		RenderLog(self.index).thread_killed(computer, frame)

		with threadlock:
			compflags[str(self.index)+'_'+computer] = 0
			


	def resume(self):
		'''resumes a stopped render job'''

		if self.status != 'Stopped':
			Dialog(6).warn()
			return

		self.status = 'Rendering'
		with threadlock:
			killflags[self.index] = 0 #reset killflag

		resumeFrames = []
		for computer in self.currentFrames: #using currentFrames because self.computerlist can change between stop and resume 
			if self.currentFrames[computer][0]: #if frame was assigned before render stopped
				resumeFrames.append(self.currentFrames[computer][0]) #[0] is frame, [1] is timer

		resumeFrames.sort()
		if self.startframe in self.totalFrames:
			self.startframe = max(resumeFrames)

		if len(self.extraframes) > 0:
			for frame in self.totalFrames:
				if frame in self.extraframes:
					self.extraframes.remove(frame)

			for frame in resumeFrames:
				if frame in self.extraframes:
					self.extraframes.remove(frame)
		else:
			self.extraframes = resumeFrames[:-1]

		with threadlock:
			queue['q'+str(self.index)] = None #destroy queue object

		RenderTimer(self.index).clear()

		print('Job:'+str(self.index)+'|Render resumed by user.')
		RenderLog(self.index).render_resumed()


		result = tkMessageBox.askquestion('Resume Options', 'Start render now? Click No to enqueue job for later.')
		if result == 'yes':
			self.status = 'Waiting'
			self.update()
			self.render()
		else:
			self.status = 'Waiting'
			self.update()
			return




class RenderThread(object):
	'''creates a thread to render a single frame on a specified computer'''

	def __init__(self, index, path, computer, frame):
		self.index = index
		self.path = path
		self.computer = computer
		self.frame = frame


	def create(self): 
		'''creates a thread for a single frame on a specified computer'''

		t = Thread(target=self.send_command, args=())
		t.start()


	def send_command(self): #this is for Blender. Later rename and add sibling classes for Terragen and Ludvig's script
		'''sends the render command via ssh'''

		global skiplists

		with threadlock: 
			renderJobs[self.index][6][self.computer] = [self.frame, time.time()] #start timeout timer

		print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|Sent') #need to add timestamp
		RenderLog(self.index).frame_sent(self.computer, self.frame)

		if self.computer in macs:
			blenderpath = blenderpath_mac #/Applications/blender.app/Contents/MacOS/blender 
		else:
			blenderpath = blenderpath_linux #/usr/local/bin/blender

		command = subprocess.Popen('ssh igp@'+self.computer+' "'+blenderpath+' -b '+self.path+' -f '+str(self.frame)+' & pgrep -n blender"', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

		self.output = ''
		for line in iter(command.stdout.readline, ''):
			if line:
				with threadlock:
					renderJobs[self.index][6][self.computer] = [self.frame, time.time()] #reset timer every time an update is received

                        if line.find('Fra:') >= 0:
                                self.parseline(line, self.frame, self.computer, self.index)
	
			elif line.strip().isdigit(): #detect PID at first line
				pid = int(line)
				with threadlock:
					renderJobs[self.index][5][self.computer] = pid
				if self.computer in renice_list: #renice process to lowest priority on specified comps 
					subprocess.call('ssh igp@'+self.computer+' "renice 20 -p '+str(pid)+'"', shell=True)
					print('reniced PID '+str(pid)+' to pri 20 on '+self.computer) #for debugging
				if skiplists[self.index]:
					with threadlock:
						skiplists[self.index].pop(0) #remove oldest entry from skip list
						print('frame sent. Removing oldest item from skiplist') #debugging

	
			elif line.find('Saved:') >= 0:

				rendertime = line[line.find('Time'):].split(' ')[1] #grabs final render time string from blender's output
				print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|Received after '+rendertime) 
				RenderLog(self.index).frame_received(self.computer, self.frame, rendertime)
				with threadlock:
					compflags[str(self.index)+'_'+self.computer] = 0
				with threadlock:
					if 0 in renderJobs[self.index][7]: #total frames
						renderJobs[self.index][7].remove(0) #remove a placeholder
					renderJobs[self.index][7].append(self.frame)
					try:
						del renderJobs[self.index][6][self.computer] #delete currentFrames entry
					except:
						print 'failed to delete currentFrames entry for ', self.computer #debugging
						pass

				with threadlock:
					queue['q'+str(self.index)].task_done() 
                        else:
                                self.output = self.output + line

			if not verbose: #use normal terminal output
				pass 
			else: #verbose terminal output
				if line:
					print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|STDOUT: '+line)

		for line in iter(command.stderr.readline, ''):
			if line: #assume any text in STDERR means connection/render failure
				with threadlock:
					queue['q'+str(self.index)].put(self.frame)
				with threadlock:
					compflags[str(self.index)+'_'+self.computer] = 0 #reset compflag to try again on next round
				with threadlock:
					skiplists[self.index].append(self.computer)
					print('Text in stderr. Adding '+self.computer+' to skiplist') #debugging

				print('ERROR:Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|STDERR: '+line) 
				RenderLog(self.index).error(self.computer, self.frame, 3, line) #error code 1

		if self.check_warn(self.output):
			with threadlock:
				queue['q'+str(self.index)].put(self.frame)
			with threadlock:
				compflags[str(self.index)+'_'+self.computer] = 0 #reset compflag to try again on next round

			print('ERROR|Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|Blender returned a warning. Offending line: '+self.output)
			RenderLog(self.index).error(self.computer, self.frame, 2, line) #error code 2




	def parseline(self, line, frame, computer, index): #prints render progress in compact form
		self.line = line

	        if self.line.find('Tile') >= 0:
	                tiles, total = self.line.split('|')[-1].split(' ')[-1].split('/')
	                tiles = int(tiles)
	                total = int(total)
	                percent = float(tiles) / total * 100
			self.termout = [self.computer, self.frame, tiles, total, percent] #doing it this way to try to fix frame -1 issue
			with threadlock:
				renderJobs[self.index][10] = self.termout


	def check_warn(self, output):
		'''returns true if blender throws a warning'''
	        if self.output.find('Warning:') >= 0:
	                return True 
		elif self.output.find('Error:') >= 0:
			return True 
	        else:
	                return False 





class RenderTimer(object):
	'''times a render job'''

	def __init__(self, index):
		self.index = index
		self.totalFrames = renderJobs[self.index][7]
		self.status = renderJobs[self.index][8]


	def start(self):
		'''starts a render timer'''
		with threadlock:
			ttime[self.index][0] = time.time()


	def get(self): 
		'''returns total elapsed time for a render'''

		if self.status != 'Rendering':
			rendertime = ttime[self.index][1] - ttime[self.index][0]
		else:
			with threadlock:
				ttime[self.index][1] = time.time()
			rendertime = ttime[self.index][1] - ttime[self.index][0]

		return rendertime


	def avgFrameTime(self):
		'''calculates average render time per frame'''
		finished_frames = 0
		for i in self.totalFrames:
			if i != 0:
				finished_frames += 1

		if finished_frames == 0:
			avgtime = 0 
			return avgtime

		avgtime = self.get() / finished_frames 
		return avgtime


	def estTimeRemaining(self):
		'''estimates total time remaining for render'''
		frames_remaining = 0
		for i in self.totalFrames:
			if i == 0:
				frames_remaining += 1


		avgtime = self.avgFrameTime()
		est_remaining = frames_remaining * avgtime
		return est_remaining


	def clear(self):
		'''clears totaltime for current index'''
		with threadlock:
			ttime[self.index] = [0, 0]


	def convert(self, time):
		'''converts time in seconds to more readable format'''
		self.time = time #time in float or int seconds

		if self.time < 60:
			newtime = [round(self.time, 2)]

		elif self.time < 3600:
			m, s = self.time / 60, self.time % 60
			newtime = [int(m), round(s, 2)]

		elif self.time < 86400:
			m, s = self.time / 60, self.time % 60
			h, m = m / 60, m % 60
			newtime = [int(h), int(m), round(s, 2)]

		else:
			m, s = self.time / 60, self.time % 60
			h, m = m / 60, m % 60
			d, h = h / 24, h % 24
			newtime = [int(d), int(h), int(m), round(s, 2)]

		seconds = newtime[-1]
		if not type(seconds) == int: #pad zeros in seconds field
			sec, dec = str(seconds).split('.')
			if len(sec) < 2:
				sec = '0'+sec
			if len(dec) < 2:
				dec = '0'+dec
			newtime[-1] = sec+'.'+dec

		if len(newtime) == 1:
			timestr = str(newtime[0])+'s'
		elif len(newtime) == 2:
			timestr = str(newtime[0])+'m '+str(newtime[1])+'s'
		elif len(newtime) == 3:
			timestr = str(newtime[0])+'h '+str(newtime[1])+'m '+str(newtime[2])+'s'
		else:
			timestr = str(newtime[0])+'d '+str(newtime[1])+'h '+str(newtime[2])+'m '+str(newtime[3])+'s'
		return timestr




class RenderLog(Job):
	'''class to handle logging functions for a rendering job'''

	hrule = '='*80 #for printing a thick horizontal line in the log
	delim = ', ' #delimiter to join computer lists into more readable format


	def __init__(self, index):
		Job.__init__(self, index)
		self.timestart = renderJobs[self.index][11]
		if not self.timestart: #set the start time only when the class is called for the first time
			self.timestart = subprocess.check_output('date +%m-%d-%H-%M', shell=True).strip()
			with threadlock:
				renderJobs[self.index][11] = self.timestart
		self.filename = self.path.split('/')[-1]
		self.log_path = '/mnt/data/renderlogs/'+self.filename.split('.')[0]+'.'+str(self.timestart)


	def render_started(self):

		if len(self.extraframes) > 0: 
		        subprocess.call('date "+'+RenderLog.hrule+'\nRender started at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '+str(self.startframe)+' - '+str(self.endframe)+' plus '+str(self.extraframes)+'\nOn: '+RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule+'\n" > '+self.log_path, shell=True)
		else:
	        	subprocess.call('date "+'+RenderLog.hrule+'\nRender started at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '+str(self.startframe)+' - '+str(self.endframe)+'\nOn: '+RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule+'\n" > '+self.log_path, shell=True)


	def frame_sent(self, computer, frame):
		self.computer = computer
		self.frame = frame
		subprocess.call('date "+Sent frame '+str(self.frame)+' of '+str(len(self.totalFrames))+' to '+self.computer+' at %H:%M:%S on %m-%d-%Y" >> '+self.log_path, shell=True)

	def frame_received(self, computer, frame, rendertime):
		self.computer = computer
		self.frame = frame
		self.rendertime = rendertime
		subprocess.call('date "+Received frame '+str(self.frame)+' of '+str(len(self.totalFrames))+' from '+self.computer+' at %H:%M:%S on %m-%d-%Y after '+self.rendertime+'" >> '+self.log_path, shell=True)

	def error(self, computer, frame, code, line):
		self.computer = computer
		self.frame = frame
		self.code = code
		self.line = line

		if self.code == 1: #text in stderr
			self.err = 'Text in STDERR: '+str(self.line) #str() just in case line is a number

		if self.code == 2: #failed check_warn()
			self.err = 'Blender returned a warning. Offending line: '+str(self.line)

		if self.code == 3: #computer timed out
			self.err = 'Computer timed out.'

		subprocess.call('date "+ERROR: frame'+str(self.frame)+' failed to render on '+self.computer+' at %H:%M:%S on %m-%d-%Y. Reason: '+self.err+'" >> '+self.log_path, shell=True)


	def complist_changed(self):
		self.computerList = renderJobs[self.index][4] #force an update
		subprocess.call('date "+Computer list changed at %H:%M:%S on %m-%d-%Y. Now rendering on: '+RenderLog.delim.join(self.computerList)+'." >> '+self.log_path, shell=True)


	def render_finished(self):
		tt = RenderTimer(self.index).get()
		totaltime = RenderTimer(self.index).convert(tt)
		subprocess.call('date "+'+RenderLog.hrule+'\nRender finished at %H:%M:%S on %m-%d-%Y\nTotal render time was '+totaltime+'.\n'+RenderLog.hrule+'" >> '+self.log_path, shell=True)


	def render_killed(self):
		subprocess.call('date "+'+RenderLog.hrule+'\nRender stopped by user at %H:%M:%S on %m-%d-%Y. Current frames: '+str(self.currentFrames)+'. Most recent PIDs: '+str(self.threads)+'." >> '+self.log_path, shell=True)

	def render_resumed(self):
		if len(self.extraframes) > 0: 
		        subprocess.call('date "+'+RenderLog.hrule+'\nRender resumed by user at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '+str(self.startframe)+' - '+str(self.endframe)+' plus '+str(self.extraframes)+'\nOn: '+RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule+'\n" >> '+self.log_path, shell=True)
		else:
	        	subprocess.call('date "+'+RenderLog.hrule+'\nRender resumed by user at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '+str(self.startframe)+' - '+str(self.endframe)+'\nOn: '+RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule+'\n" >> '+self.log_path, shell=True)

	def thread_killed(self, computer, frame):
		self.computer = computer
		self.frame = frame
		subprocess.call('date "+User killed render thread on '+self.computer+' at %H:%M:%S on %m-%d-%Y. Returning frame '+str(self.frame)+' to queue." >> '+self.log_path, shell=True)




class Status(Job):
	'''class representing the status of a queued or rendering job'''

	def __init__(self, index):
		Job.__init__(self, index)
		self.filename = self.path.split('/')[-1]



	def get_status(self):
		return self.status


	def globalJobstat(self):
		'''populates global job status box'''

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'+str(self.index)).delete('all')

		if self.status == 'Empty':
			color = 'gray70'
			jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'+str(self.index)).create_rectangle(0, 0, 120, 20, fill=color)
			jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'+str(self.index)).create_text(60, 10, text='Job '+str(self.index)+' '+self.status)
			return


		finished_frames = 0 #number of frames finished
		for i in self.totalFrames:
			if i != 0:
				finished_frames += 1

		if len(self.totalFrames) != 0:
			percent_complete = int(finished_frames / float(len(self.totalFrames)) * 100)
		else:
			percent_complete = 0

		if percent_complete == 100:
			self.status = 'Finished' 
			with threadlock:
				renderJobs[self.index][8] = self.status

		if killflags[self.index] == 1:
			self.status = 'Stopped'

		complist = '' #computerList in more readable format
		if self.computerList == computers:
			complist = 'All'
		elif self.computerList == fast:
			complist = 'Fast'
		elif self.computerList == farm:
			complist = 'Farm'
		else:
			for comp in self.computerList:
				complist = complist + comp + ', '
			complist = complist[:-2]

		if self.status == 'Rendering':
			color = 'SpringGreen'
		elif self.status == 'Waiting':
			color = 'Khaki'
		elif self.status == 'Finished':
			color = 'CornflowerBlue'
		elif self.status =='Stopped':
			color = 'Tomato'

		if self.extraframes == []:
			extras = 'None  '
		else: #truncate long list of extraframes
			self.extraframes.sort()
			if len(self.extraframes) <= 2:
				extraset = []
				for frame in self.extraframes:
					extraset.append(str(frame))
				extras = RenderLog.delim.join(extraset)

			else:
				extras = str(self.extraframes[0])+', '+str(self.extraframes[1])+'...'

		if len(self.filename) > 17: #truncate long filenames
			self.filename = self.filename[0:16]+'...'

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'+str(self.index)).create_rectangle(0, 0, 120, 20, fill=color)
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'+str(self.index)).create_text(60, 10, text='Job '+str(self.index)+' '+self.status)

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.filenam_'+str(self.index)).config(text=self.filename)
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.startfram_'+str(self.index)).config(text='Start: '+str(self.startframe))
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.endfram_'+str(self.index)).config(text='End: '+str(self.endframe))
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.extrafram_'+str(self.index)).config(text='Extras: '+str(extras))

		tt = RenderTimer(self.index).get()
		at = RenderTimer(self.index).avgFrameTime()
		tl = RenderTimer(self.index).estTimeRemaining()

		totaltime = RenderTimer(self.index).convert(tt)
		avgtime = RenderTimer(self.index).convert(at)
		timeleft = RenderTimer(self.index).convert(tl)

		if len(totaltime) > 14 or len(avgtime) > 14 or len(timeleft) > 14: #Change font size if too many characters for fields
			timefont = smallfont
			charwidth = 7 #approx character width for smallfont 
		else:
			timefont = 'TkDefaultFont' 
			charwidth = 9 #approx character width for defaultfont

		ttx = 35 + 29 + int(charwidth * len(totaltime) / 2)
		atx = 240 + 42 + int(charwidth * len(avgtime) / 2)
		tlx = 448 + 48 + int(charwidth * len(timeleft) / 2)

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).delete('all')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(35, 10, text='Total time:')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(ttx, 10, text=str(totaltime), font=timefont)
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(250, 10, text='Avg/frame:')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(atx, 10, text=str(avgtime), font=timefont)
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(466, 10, text='Remaining:')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(tlx, 10, text=str(timeleft), font=timefont)

		Status(self.index).drawTotalBar()
		


	def purgeGlobalJobstat(self):
		'''resets all text fields in global queue status for a given index'''
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.filenam_'+str(self.index)).config(text='')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.startfram_'+str(self.index)).config(text='')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.endfram_'+str(self.index)).config(text='')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.extrafram_'+str(self.index)).config(text='')

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).delete('all')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(35, 10, text='Total time:')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(250, 10, text='Avg/frame:')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'+str(self.index)).create_text(466, 10, text='Remaining:')

		Status(self.index).clearTotalBar()



	def drawBar(self):
		'''updates individual computer progress bars, current frames, and % completed'''

		if not self.termout:
			return

		self.computer = self.termout[0]
		self.frame = self.termout[1]
		self.percent = int(self.termout[-1])

		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').delete('all')
		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').create_text(5, 10, anchor=W, text=self.computer)
		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').create_text(130, 10, anchor=W, text='Frame:')
		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').create_text(180, 10, anchor=W, text=self.frame) 
		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').create_text(279, 10, anchor=E, text=self.percent)
		statframe.nametowidget(self.computer+'_statbox.'+self.computer+'_compdata').create_text(280, 10, anchor=W, text='% Complete')

		progvars[self.computer].set(self.percent)



	def fillAllBars(self):
		'''sets computer progress bar to 100%'''
		for computer in computers:
			if computer in self.threads: #if computer recently rendered a frame
				self.termout[0] = computer
				self.termout[-1] = 100
				self.drawBar()
			else:
				statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').delete('all')
				statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(5, 10, anchor=W, text=computer)
				statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(130, 10, anchor=W, text='Frame:')
				statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(280, 10, anchor=W, text='% Complete')
				progvars[computer].set(0)



	def clearAllBoxes(self):
		'''clears computer progress bars and statboxes'''
		for computer in computers:
			statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').delete('all')
			statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(5, 10, anchor=W, text=computer)
			statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(130, 10, anchor=W, text='Frame:')
			statframe.nametowidget(computer+'_statbox.'+computer+'_compdata').create_text(280, 10, anchor=W, text='% Complete')
			progvars[computer].set(0)



	def drawTotalBar(self):
		'''draws & updates total render progress bar'''

		finished_frames = 0
		for i in self.totalFrames:
			if i != 0:
				finished_frames += 1

		if len(self.totalFrames) != 0:
			percent_complete = finished_frames / float(len(self.totalFrames)) * 100 
		else:
			percent_complete = 0

		totalprog[self.index].set(int(percent_complete))

		pct = PaddedNumber(int(percent_complete)).percent()
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'+str(self.index)).delete('all')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'+str(self.index)).create_text(55, 9, text=pct+'% Complete')



	def drawJoblight(self):
		'''draws status light & job number in statbox'''
		if killflags[self.index] == 1:
			self.status = 'Stopped'

		if self.status == 'Empty':
			color = 'gray90'
		elif self.status == 'Rendering':
			color = 'SpringGreen'
		elif self.status == 'Waiting':
			color = 'Khaki'
		elif self.status == 'Finished':
			color = 'CornflowerBlue'
		elif self.status =='Stopped':
			color = 'Tomato'

		if not self.filename:
			self.filename = 'No file selected.'

		if len(self.filename) > 30: #truncate long filenames
			self.filename = self.filename[0:30]+'...'

		joblabel.delete('all')
		joblight.delete('all')
		filelabel.delete('all')

		joblabel.create_rectangle(0, 0, 80, 30, fill=color, outline='gray70')
		joblabel.create_text(40, 15, text='Job '+str(self.index), font='TkCaptionFont')

		joblight.create_rectangle(-1, 0, 120, 30, fill=color, outline='gray70')
		joblight.create_text(60, 15, text=self.status, font='TkCaptionFont')

		filelabel.create_rectangle(0, 0, 260, 30, fill='gray90', outline='gray70')
		filelabel.create_text(130, 15, text=self.filename, font='TkCaptionFont')

		self.drawToggleButtons() 



	def drawToggleButtons(self):
		'''creates and updates computer toggle buttons in statboxes'''

		incolor = 'SpringGreen' #color for computers that are in render pool
		outcolor = 'Khaki' #color for computers that are not in render pool

		for computer in computers:
			statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').delete('all')
			statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').create_text(20, 10, text='Pool', font=smallfont)
			if computer in self.computerList:
				statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').create_rectangle(2, 20, 37, 37, fill=incolor, outline='gray50')
				statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').create_text(20, 29, text='In', font=smallfont)
			else:
				statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').create_rectangle(2, 20, 37, 37, fill=outcolor, outline='gray50')
				statframe.nametowidget(computer+'_statbox.'+computer+'_togglebtn').create_text(20, 29, text='Out', font=smallfont)




	def clearTotalBar(self): 
		'''clears contents of total progress bar'''

		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'+str(self.index)).delete('all')
		jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'+str(self.index)).create_text(55, 9, text='0% Complete')
		with threadlock:
			totalprog[self.index].set(0)





class PaddedNumber(object): #renamed from Percent(object).pad()
	'''padded number strings for display in the GUI'''

	def __init__(self, number):
		self.number = number #must be an integer

	def percent(self): #use monospace font for proper effect
		'''pad integer percent with blank space to fill three char widths'''

		percent_padded = str(self.number)
		if len(percent_padded) == 1:
			percent_padded = '  '+percent_padded
		elif len(percent_padded) == 2:
			percent_padded = ' '+percent_padded
		return percent_padded




class Dialog(object):
	'''dialog boxes with various messages'''

	def __init__(self, msg):
		self.msg = msg #integer representing type of message to be displayed

	def warn(self):
		'''creates warning popup with only OK button'''
		if self.msg == 1: 
			txt = 'Frame numbers must be integers.'
		elif self.msg == 2: 
			txt = 'Extra frames are in the start-end frame range.'
		elif self.msg == 3: 
			txt = 'Cannot modify a queue item while it is rendering.'
		elif self.msg == 4:
			txt = 'End frame must be greater than or equal to start frame.'
		elif self.msg == 5:
			txt = 'Path, Start frame, End frame, and Computers must be specified' 
		elif self.msg == 6:
			txt = 'Render must be stopped before it can be resumed.'
		elif self.msg == 7:
			txt = 'Extra frames must be integers separated by spaces only.'
		elif self.msg == 8:
			txt = 'Render cannot be started unless job status is Waiting.'
		elif self.msg == 9:
			txt = 'Job is not currently rendering.' 
		elif self.msg == 10:
			txt = 'File path invalid or inaccessible.'
		elif self.msg == 11:
			txt = 'Queue slot is already empty.'
		elif self.msg == 12:
			txt = 'Computer is already in render pool.'
		elif self.msg == 13:
			txt = 'Computer is not in current render pool.'
		elif self.msg == 14:
			txt = 'Cannot change start, end, or extra frames once render as been started. Use buttons in main window to change computer list or create a new queue item.'
		elif self.msg == 15:
			txt = 'Cannot remove a job while rendering.  Stop render first.'
		elif self.msg == 16:
			txt = 'No render thread currently assigned to this computer.'

		tkMessageBox.showwarning('Achtung!', txt)

	def confirm(self):
		'''creates popup with OK and Cancel buttons, returns true if user clicks OK'''

		if self.msg == 1:
			txt = 'Stop the current render?  All progress on currently-rendering frames will be lost.'
		elif self.msg == 2:
			txt = 'Overwrite existing queue contents?'
		elif self.msg == 3:
			txt = 'Delete this queue item?'
		elif self.msg == 4:
			txt = 'Laptops or other extra computers are checked. Are you sure these are available for rendering?'
		elif self.msg == 5:
			txt = 'Are you sure you want to remove the last computer from the pool?'
		elif self.msg == 6:
			txt = 'Kill the render thread on this computer?'
		
		if tkMessageBox.askokcancel('Achtung!', txt, icon='warning'):
			return True
		else:
			return False




class ClickFrame(Frame):
	'''version of tkinter Frame that functions as a button when clicked

	creates a new argument - index - that identifies which box was clicked''' 

	def __init__(self, master, index, **kw):
		apply(Frame.__init__, (self, master), kw)
		self.index = index
		self.bind('<Button-1>', lambda x: set_job(self.index))


class ClickLabel(Label):
	'''version of tkinter Label that functions as a button when clicked'''

	def __init__(self, master, index, **kw):
		apply(Label.__init__, (self, master), kw)
		self.index = index
		self.bind('<Button-1>', lambda x: set_job(self.index))


class FramesHoverLabel(ClickLabel):
	'''version of ClickLabelthat also has a hover binding'''

	def __init__(self, master, index, **kw):
		ClickLabel.__init__(self, master, index, **kw)
		self.bind('<Enter>', lambda x: extraballoon(x, index))


class NameHoverLabel(ClickLabel):
	'''version of clicklabel that also has a hover binding'''

	def __init__(self, master, index, **kw):
		ClickLabel.__init__(self, master, index, **kw)
		self.bind('<Enter>', lambda x: nameballoon(x, index))


class ClickCanvas(Canvas):
	'''version of tkinter Canvas that functions like a button when clicked'''

	def __init__(self, master, index, **kw):
		apply(Canvas.__init__, (self, master), kw)
		self.index = index
		self.bind('<Button-1>', lambda x: set_job(self.index))


class ClickProg(ttk.Progressbar):
	'''version of ttk progress bar that does stuff when clicked'''

	def __init__(self, master, index, **kw):
		apply(ttk.Progressbar.__init__, (self, master), kw)
		self.bind('<Button-1>', lambda x: set_job(index))


class DoubleButton(Button):
	'''version of tkinter Button that takes an index argument and passes it to a function different from the button's command function'''

	def __init__(self, master, index, **kw):
		apply(Button.__init__, (self, master), kw)
		self.index = index
		self.bind('<Button-1>', lambda x: set_job(self.index))


class AdRemButton(Button):
	'''version of tkinter button that takes a computer argument and passes it to another function'''

	def __init__(self, master, computer, val, **kw):
		apply(Button.__init__, (self, master), kw)
		self.computer = computer
		self.val = val #int 0 for add, 1 for remove
		self.bind('<Button-1>', lambda x: add_remove_computer(self.computer, self.val))


class ToggleCanv(Canvas):
	'''version of tkinter canvas that acts as computerList toggle button'''

	def __init__(self, master, computer, **kw):
		apply(Canvas.__init__, (self, master), kw)
		self.bind('<Button-1>', lambda x: add_remove_computer(computer))


class KillCanv(Canvas):
	'''version of tkinter canvas that acts as a per-computer process kill button'''

	def __init__(self, master, computer, **kw):
		apply(Canvas.__init__, (self, master), kw)
		self.bind('<Button-1>', lambda x: Job(jobNumber.get()).kill_thread(computer)) #need a kill process function





#------Global Functions------


def browse(): #opens file browser window and returns a path
	filepath = tkFileDialog.askopenfilename(title='Open File')
	return filepath

def startJob():
	Job(jobNumber.get()).render()

def killJob():
	Job(jobNumber.get()).kill()

def resumeJob():
	Job(jobNumber.get()).resume()

def removeJob():
	index = jobNumber.get()
	if Job(index).checkSlotFree():
		Dialog(11).warn()
		return

	if Status(index).get_status() == 'Rendering': 
		Dialog(15).warn()
		return

	if not Dialog(3).confirm():
		return

	Job(index).clear()



def add_remove_computer(computer):
	index = jobNumber.get()
	if Job(index).checkSlotFree(): #can't change computer list if there's no job in queue
		return

	computerList = renderJobs[index][4]
	if not computer in computerList:
		Job(index).add_computer(computer)
	else:
		if len(computerList) <= 1:
			if not Dialog(5).confirm():
				return
		Job(index).remove_computer(computer)

	if Status(index).get_status() == 'Rendering':
		RenderLog(index).complist_changed()




def set_job(index): #sets active job number when box is clicked
	jobNumber.set(index)

	oncolor = 'white' 
	offcolor = 'gray80' 
	ontext = 'black'
	offtext = 'gray50'

	
	for i in range(1, queueslots + 1):
		if i != index: #change inactive boxes to offcolor
			jobstatFrame.nametowidget('jobstat_'+str(i)).config(bg=offcolor, relief=GROOVE, bd=1)

			for widget in otherwidgets:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+widget+str(i)).config(bg=offcolor, highlightbackground=offcolor)
			
			for label in jobstat_label_list:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+label+str(i)).config(bg=offcolor, fg=offtext)

			for button in buttons:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.buttonframe_'+str(i)+'.'+button+str(i)).config(bg=offcolor, highlightbackground=offcolor)

		else: #change active boxes to oncolor
			jobstatFrame.nametowidget('jobstat_'+str(i)).config(bg=oncolor, relief=FLAT, bd=0)

			for widget in otherwidgets:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+widget+str(i)).config(bg=oncolor, highlightbackground=oncolor)
			
			for label in jobstat_label_list:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+label+str(i)).config(bg=oncolor, fg=ontext)

			for button in buttons:
				jobstatFrame.nametowidget('jobstat_'+str(i)+'.buttonframe_'+str(i)+'.'+button+str(i)).config(bg=oncolor, highlightbackground=oncolor)

	updateFields()




def updateFields(): #updates & redraws detailed status info when job is switched
	index = jobNumber.get()
	Status(index).clearAllBoxes()


def parseOutput(): #called by update(), reads renderJobs & updates UI status indicators
	index = jobNumber.get()
	termout = renderJobs[index][10]
	status = renderJobs[index][8]
	Status(index).drawJoblight()

	for i in renderJobs: #update global statuses for ALL slots
		Status(i).globalJobstat()

	if not Job(index).checkSlotFree(): #update detailed info only for CURRENT slot
		if len(termout) == 5:
			Status(index).drawBar()
		if status == 'Finished':
			Status(index).fillAllBars()


def update(): #refreshes GUI
	parseOutput()
	root.update_idletasks()
	canvas.config(height=(root.winfo_height()-105))
	root.after(80, update)


def toggle_verbosity(): #toggles python verbose variable based on tkinter verbosity checkbox
	global verbose
	verbose = verbosity.get()


def start_next_job(): #starts the next job in queue 
	global renderJobs
	global maxglobalrenders

	renders = 0
	for index in renderJobs:
		if renderJobs[index][8] == 'Rendering': #terminate if a render is in progress
			renders += 1

	if renders >= maxglobalrenders:
		return

	for index in renderJobs:
		if renderJobs[index][8] == 'Finished': #check for waiting jobs
			for i in renderJobs:
				if renderJobs[i][8] == 'Waiting':
					Job(i).render()
					time.sleep(0.25) #delay between starting simultaneous renders
					return


def check_job_queue(): #checks if any jobs are waiting and calls start_next_job() if yes
	global startnext

	if startnext == 1:
		start_next_job()

	root.after(5000, check_job_queue)



def set_startnext(): #updates global startnext variable
	global startnext
	startnext = stnext.get()
	if startnext == 1:
		print('Autostart on')
	else:
		print('Autostart off')



def quit(): #forces immediate exit without waiting for loops to terminate
	_exit(1) 



def check_missing_frames(index):
	if index in range(1, queueslots + 1): #checking a currently-queued job
		path = renderJobs[index][0]
		start = renderJobs[index][1]
		end = renderJobs[index][2]
		extras = renderJobs[index][3]
	else:
		path = check_path.get()
		start = int(check_start.get())
		end = int(check_end.get())

	frames_theoretical = []
	frames_actual = []
	frames_missing = []

	for frame in range(start, end + 1):
		frames_theoretical.append(frame)

	dir_contents = subprocess.check_output('ls '+path, shell=True).split()

	for line in dir_contents:
		if line[-3:] in allowed_filetypes:
			filename = line
			name, ext = line.split('.')
			print filename, ext
			no_allowed_files = False
			break
		else:
			no_allowed_files = True
	
	if no_allowed_files == True:
		print('Error: No suitable files found.')
		return 'Error: No suitable files found.', None, None

	#reverse filename and check backwards from end until a non-digit is found.  Assume this is start of name text
	#intended to prevent problems if there are numbers in filename before sequential numbers
	length = range(len(name))
	length.reverse()
	for i in length:
		if not name[i].isdigit():
			leftbreak = i+1
			rightbreak = len(filename) - len(ext) - 1 #assuming sequential #s go to end of filename
			sequentials = filename[leftbreak:rightbreak]
			break

	def nametext_confirm():
		ntconf = Toplevel()
		ntframe = LabelFrame(ntconf, text='Confirm Filename Parsing')
		ntframe.grid(row=0, column=0, padx=10, pady=10)

		def get_slider():
			leftbreak = int(slider_left.get())
			rightbreak = int(slider_right.get())
			sequentials = filename[leftbreak:rightbreak]
			a.config(text=filename[0:leftbreak])
			b.config(text=sequentials)
			c.config(text=filename[rightbreak:])

		a = Label(ntframe, text=filename[0:leftbreak], fg='gray50')
		a.grid(row=0, column=0, sticky=E)
		b = Label(ntframe, text=sequentials, fg='DarkRed')
		b.grid(row=0, column=1, sticky=N)
		c = Label(ntframe, text=filename[rightbreak:], fg='gray50')
		c.grid(row=0, column=2, sticky=W)

		
		slidelength = len(filename)
		slider_left = ttk.Scale(ntframe, from_=0, to=slidelength, orient=HORIZONTAL, length=slidelength*9, command=lambda x: get_slider())
		slider_left.grid(row=1, column=0, columnspan=3, sticky=W)
		slider_left.set(leftbreak)
		
		slider_right = ttk.Scale(ntframe, from_=0, to=slidelength, orient=HORIZONTAL, length=slidelength*9, command=lambda x: get_slider())
		slider_right.grid(row=2, column=0, columnspan=3, sticky=W)
		slider_right.set(rightbreak)

		a.config(text=filename[0:leftbreak])
		b.config(text=sequentials)
		c.config(text=filename[rightbreak:])

		Button(ntframe, text='Close', command=ntconf.destroy).grid(row=3)

	nametext_confirm()
	
	for line in dir_contents:
		if line[-3:] in allowed_filetypes:
			frameno = int(line[leftbreak:rightbreak])
			frames_actual.append(frameno)

	for frame in frames_theoretical:
		if not frame in frames_actual:
			frames_missing.append(frame)


	if not frames_missing:
		print('No missing frames found.')
	else:
		for frame in frames_missing:
			print('Missing frame '+str(frame))

	return dir_contents, frames_theoretical, frames_missing


	



#----------Global Variables----------

queueslots = 5 #total number of queue slots (for scalability purposes, used in various range() functions)


#create list of all computers available for rendering
computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'snowmass', 'humberto', 'tabeguache', 'conundrum', 'paradox'] 

fast = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 'eldiente'] #list of computers in the 'fast' group

farm = ['lindsey', 'wetterhorn', 'lincoln', 'snowmass', 'humberto', 'tabeguache'] #list of computers in the 'farm' group

extracomps = ['conundrum', 'paradox'] #list of computers that may not always be available for rendering.

renice_list = ['conundrum', 'paradox'] #list of computer to renice processes to lowest priority. Can be changed from prefs window.

macs = ['conundrum', 'paradox', 'sherman'] #computers running OSX. Needed because blender uses different path

blenderpath_mac = '/Applications/blender.app/Contents/MacOS/blender' #path to blender executable on OSX computers

blenderpath_linux = '/usr/local/bin/blender' #path to blender executable on Linux computers

allowed_filetypes = ['png', 'jpg', 'peg', 'gif', 'tif', 'iff', 'exr', 'PNG', 'JPG', 'PEG', 'GIF', 'TIF', 'IFF', 'EXR'] #allowed file extensions (last 3 chars only) for check_missing_files

timeout = 60 #timeout for failed machine in seconds

startnext = 1 #start next job when current one finishes. On by default

maxglobalrenders = 1 #maximum number of simultaneous renders for the start_next_job() function


#create global renderJobs dictionary
#holds render info for each job
#format: { job(int) : [path(str), startframe(int), endframe(int), extraframes(list), computerList(list), threads(dict), currentFrames(dict), totalFrames(list), status(str), index(int), termout(str), timestart(str) }
#Definitions:
	#extraframes: list of non-sequential frames to be rendered (must be outside of range(startframe, endframe + 1)
	#computerList: list of computers on which to render the current job
	#threads: PIDs for currently-running threads. Format is {'computer': PID}. Used for stop function
	#currentFrames: frames that are currently assigned to render threads. Format is {'computer': [frame, time]}. Used in timeout function and for killing processes.
	#totalFrames: list of all frames for a job.  Initially filled with zeros to mark length of anticipated render. Zeros replaced with frame numbers as each frame is returned. 
	#status: string representing current queue status. Can be 'Empty', 'Waiting', 'Rendering', 'Stopped', 'Finished'
	#index: integer representing the number of the job. This is the same as the queue slot's index in the job number (redundant, there was a reason for this originally)
	#termout: string containing per-computer render progress, parsed to update progress bars.
	#log_path: time of render start for logging purposes 
 

renderJobs= dict()
for job in range(1, queueslots + 1): #put empty placeholders so parsing/checking functions work
	renderJobs[job] = ['', 0, 0, [], [], {}, {}, [], 'Empty', job, '', '']


#create global dictionary of queues
#one queue for each render job
queue = dict()
for i in range(1, queueslots + 1):
	queue['q'+str(i)] = None 


#initiate total render time variables
#time format: index: [start, end]
ttime = ['none']
for job in range(1, queueslots + 1):
	ttime.append([0, 0])

#create compflags dictionary
#compflags block while render is active, limiting to one renderthread per computer per job
compflags = dict()
for job in range(1, queueslots + 1): 
	for computer in computers:
		compflags[str(job)+'_'+computer] = 0


#create killflags list
#if killflags[index] == 1, render is killed
killflags = []
for job in range(1, queueslots + 2): #+2 b/c first index is 0
	killflags.append(0)


#terminal output verbose. 0 = normal, 1 = write everything from render stdout to terminal
verbose = 0

#create re-entrant thread lock
threadlock = RLock()

#create dict for check_missing_frames
checkframes = dict()

#create dictionary of skiplists
skiplists = dict()
for i in range(1, queueslots + 1):
	skiplists[i] = []



#----------GUI MAIN----------

root = Tk()
root.title('IGP Render Controller Mk. IV')
root.config(bg='gray90')
root.minsize(1145, 400)
root.geometry('1145x525')
root.bind('<Command-q>', lambda x: quit()) #use internal quit function instead of OSX
root.bind('<Control-q>', lambda x: quit())
#ttk.Style().theme_use('clam') #use clam theme for widgets in Linux

bigboldfont = tkFont.Font(family='Default', size='16', weight='bold')
medboldfont = tkFont.Font(family='Default', size='14', weight='bold')
smallfont = tkFont.Font(family='Default', size='10')



#---GUI Variables---

pathInput = StringVar(None)
pathInput.set('/mnt/data/test_render/test_render.blend')

startInput = StringVar(None)
startInput.set('1')

endInput = StringVar(None)
endInput.set('3')

extrasInput = StringVar(None)

compList = StringVar(None)

jobNumber = IntVar()
jobNumber.set(1)

verbosity = IntVar() #tkinter equivalent of verbose variable
verbosity.set(0)

compAllvar = IntVar()
compFastvar = IntVar()
compFarmvar = IntVar()

stnext = IntVar() #tkinter var corresponding to startnext
stnext.set(startnext)


#list of computer variables, used to construct computerList in Job().enqueue()
compvars = []
for i in range(len(computers)):
	compvars.append(IntVar())


#create computer progress var variables
progvars = dict()
for computer in computers:
	progvars[computer] = IntVar()	

#create render total progress bar variables
totalprog = dict()
for i in range(1, queueslots + 1):
	totalprog[i] = IntVar()

#create variables for check_missing_frames()
check_path = StringVar()
check_start = StringVar()
check_end = StringVar()





#---------INPUT WINDOW----------

def input_window(): #opens a new window for render queue input

	class Compbutton(object):
	
		def __init__(self, comp):
			self.comp = comp
	
		def uncheck(self):
			inputBox.nametowidget('compBox.'+self.comp+'_button').deselect()
	
		def check(self):
			inputBox.nametowidget('compBox.'+self.comp+'_button').select()
	
	def clearInputs():
		pathInput.set('')
		startInput.set('')
		endInput.set('')
		extrasInput.set('')
		uncheckAll()


	def uncheckAll():
		compAll.deselect()
		compFast.deselect()
		compFarm.deselect()
		for comp in computers:
			Compbutton(comp).uncheck()
	
	def uncheckFast():
		for comp in fast:
			Compbutton(comp).uncheck()
	
	def uncheckFarm():
		for comp in farm:
			Compbutton(comp).uncheck()
	
	def checkAll():
		compFast.deselect()
		compFarm.deselect()
		for comp in computers:
			Compbutton(comp).check()
	
	def checkFast():
		uncheckAll()
		compFast.select()
		for comp in fast:
			Compbutton(comp).check()
	
	def checkFarm():
		uncheckAll()
		compFarm.select()
		for comp in farm:
			Compbutton(comp).check()
	
	
	def uncheckTop():
		compAll.deselect()
		compFast.deselect()
		compFarm.deselect()

	def queueJob():
		if Job(jobNumber.get()).enqueue():
			input_win.destroy()

	def get_input_path():
		filepath = browse()
		pathInput.set(filepath)
		
	

	input_win = Toplevel()
	input_win.title('Edit Job No. '+str(jobNumber.get()))

	inputBox = LabelFrame(input_win, text='Input')
	inputBox.grid(row=0, column=0, padx=5, pady=5)

	pathlabel = Label(inputBox, text='Path:')
	pathlabel.grid(row=0, column=0, padx=5, sticky=W)
	pathin = Entry(inputBox, textvariable=pathInput, width=68)
	pathin.grid(row=1, column=0, columnspan=3, padx=5, sticky=W)
	browsebutton = Button(inputBox, text='Browse', command=get_input_path)
	browsebutton.grid(row=1, column=2, padx=5, pady=5, sticky=E)

	startlabel = Label(inputBox, text="Start frame:")
	startlabel.grid(row=2, column=0, padx=5, sticky=W)
	startin = Entry(inputBox, textvariable=startInput, width=15)
	startin.grid(row=3, column=0, padx=5, sticky=W)

	endlabel = Label(inputBox, text="End frame:")
	endlabel.grid(row=2, column=1, padx=5, sticky=W)
	endin = Entry(inputBox, textvariable=endInput, width=15)
	endin.grid(row=3, column=1, padx=5, sticky=W)

	extralabel = Label(inputBox, text="Extra frames:")
	extralabel.grid(row=2, column=2, padx=5, sticky=W)
	extrasin = Entry(inputBox, textvariable=extrasInput, width=42)
	extrasin.grid(row=3, column=2, padx=5, sticky=W)

	#---Input Buttons---

	buttonFrame = Frame(inputBox)
	buttonFrame.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky=W)

	okbutton = Button(buttonFrame, text='OK', command=queueJob, borderwidth=4)
	okbutton.grid(row=0, column=0, sticky=W)
	input_win.bind('<Return>', lambda x: okbutton.invoke()) #activates OK button when user presses enter
	input_win.bind('<KP_Enter>', lambda x: okbutton.invoke()) #for the numpad enter key

	cancelbutton = Button(buttonFrame, text='Cancel', command=input_win.destroy)
	cancelbutton.grid(row=0, column=1, sticky=W)
	input_win.bind('<Escape>', lambda x: cancelbutton.invoke()) #activates cancel button when user presses Esc

	clearcomps = Button(buttonFrame, text='Reset Computers', command=uncheckAll)
	clearcomps.grid(row=0, column=2,  sticky=E)

	clearbutton = Button(buttonFrame, text='Reset All', command=clearInputs)
	clearbutton.grid(row=0, column=3, sticky=E)


	#---Computer Checkboxes---

	compBox = LabelFrame(inputBox, name='compBox', text='Computers:')
	compBox.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky=W)

	compAll = Checkbutton(compBox, text='All', variable=compAllvar, command=checkAll)
	compAll.grid(row=0, column=0, padx=5, pady=5, sticky=W)

	compFast = Checkbutton(compBox, text='Fast', variable=compFastvar, command=checkFast)
	compFast.grid(row=0, column=1, padx=5, pady=5, sticky=W)

	compFarm = Checkbutton(compBox, text='Farm', variable=compFarmvar, command=checkFarm)
	compFarm.grid(row=0, column=2, padx=5, pady=5, sticky=W)

	for i in range(len(computers)): #generates table of computer checkbuttons
		if i < 6: #generate fast buttons
			fastButton = Checkbutton(compBox, name=computers[i]+'_button', text=computers[i], variable=compvars[i], command=uncheckTop)
			fastButton.grid(row=1, column=i, padx=5, pady=5, sticky=W)
		elif i < 12: #generate farm buttons
			farmButton = Checkbutton(compBox, name=computers[i]+'_button', text=computers[i], variable=compvars[i], command=uncheckTop)
			farmButton.grid(row=2, column=i-6, padx=5, pady=5, sticky=W)
		else: #generate buttons for extra computers
			compButton = Checkbutton(compBox, name=computers[i]+'_button', text=computers[i], variable=compvars[i], command=uncheckTop)
			compButton.grid(row=3, column=i-12, padx=5, pady=5, sticky=W)






#------DUMP VARIABLES WINDOW------

def dump_vars_win(): 
	dv_win = Toplevel()
	dv_win.config(bg='gray90')
	dv_win.title('Show Variables')
	autoref = IntVar() #autorefresh (true/false)
	autoref.set(0) #off by default
	refint = StringVar() #user specified refresh interval in ms 
	dv_win.bind('<Command-q>', lambda x: quit()) #use internal quit function instead of OSX
	dv_win.bind('<Control-q>', lambda x: quit())
	
	def dump_renderJobs():
		global renderJobs
		rjtext.delete(0.0, END) #probably don't want to include this later
		for i in renderJobs:
			rjtext.insert(END, str(i)+':')
			rjtext.insert(END, renderJobs[i])
			rjtext.insert(END, '\n\n')

	def dump_compflags():
		global compflags
		global queueslots
		cftext1.delete(0.0, END)
		cftext2.delete(0.0, END)
		cftext3.delete(0.0, END)
		cftext4.delete(0.0, END)
		cftext5.delete(0.0, END)

		for flag in compflags:
			if flag[0] == '1':
				cftext1.insert(END, flag+':'+str(compflags[flag])+'\n')
			elif flag[0] == '2':
				cftext2.insert(END, flag+':'+str(compflags[flag])+'\n')
			elif flag[0] == '3':
				cftext3.insert(END, flag+':'+str(compflags[flag])+'\n')
			elif flag[0] == '4':
				cftext4.insert(END, flag+':'+str(compflags[flag])+'\n')
			elif flag[0] == '5':
				cftext5.insert(END, flag+':'+str(compflags[flag])+'\n')

	def dump_killflags():
		global killflags
		kftext.delete(0.0, END)
		kftext.insert(END, killflags)

	def dump_queue():
		global queue
		qtext.delete(0.0, END)
		qtext.insert(END, queue)

	def dump_ttime():
		global ttime
		tttext.delete(0.0, END)
		tttext.insert(END, ttime)

	def dump_all():
		dump_renderJobs()
		dump_compflags()
		dump_killflags()
		dump_queue()
		dump_ttime()

	def autorefresh():
		dump_all()
		try:
			interval = int(refint.get())
		except:
			interval = 300 #default interval of 0.3 sec
		if autoref.get() == 1:
			dv_win.after(interval, autorefresh)

	dv_topbar = Frame(dv_win, bg='gray90')
	dv_topbar.grid(row=0, column=0, padx=5, sticky=W)
	ttk.Button(dv_topbar, text='renderJobs', command=dump_renderJobs, style='Toolbutton').grid(row=0, column=0, padx=5, pady=5, sticky=W)
	ttk.Button(dv_topbar, text='compflags', command=dump_compflags, style='Toolbutton').grid(row=0, column=1, padx=5, pady=5, sticky=W)
	ttk.Button(dv_topbar, text='killflags', command=dump_killflags, style='Toolbutton').grid(row=0, column=2, padx=5, pady=5, sticky=W)
	ttk.Button(dv_topbar, text='queue', command=dump_queue, style='Toolbutton').grid(row=0, column=3, padx=5, pady=5, sticky=W)
	ttk.Button(dv_topbar, text='ttime', command=dump_ttime, style='Toolbutton').grid(row=0, column=4, padx=5, pady=5, sticky=W)

	arfframe = Frame(dv_topbar, bg='gray90', bd=2, relief=GROOVE)
	arfframe.grid(row=0, column=5, sticky=E)
	arfbtn = ttk.Checkbutton(arfframe, text='Auto Refresh', command=autorefresh, variable=autoref, style='Toolbutton')
	arfbtn.grid(row=0, column=0, padx=1, pady=1, sticky=W)
	Label(arfframe, text='Interval (ms):', bg='gray90').grid(row=0, column=1, padx=1, sticky=W)
	intentry = Entry(arfframe, textvariable=refint, width=4, highlightthickness=0)
	intentry.grid(row=0, column=2, padx=1, sticky=W)
	intentry.insert(END, '300') #display default interval in entry field
	
	
	#--renderJobs--
	
	rjlabel = LabelFrame(dv_win, text='Global renderJobs', bg='gray90')
	rjlabel.grid(row=1, column=0, padx=10)

	rjtextframe = Frame(rjlabel)
	rjtextframe.pack(padx=5, pady=5)
	
	rjscroll = Scrollbar(rjtextframe)
	rjscroll.pack(side=RIGHT, fill=Y)
	
	rjtext = Text(rjtextframe, width=100, height=12, bg='black', fg='white', highlightthickness=0)
	rjtext.pack()

	rjtext.config(yscrollcommand=rjscroll.set)
	rjscroll.config(command=rjtext.yview)
	
	#--compflags--

	cflabel = LabelFrame(dv_win, text='Global compflags', bg='gray90')
	cflabel.grid(row=2, column=0, padx=10)

	cftextframe = Frame(cflabel)
	cftextframe.pack(padx=5, pady=5)

	cfscroll = Scrollbar(cftextframe)
	cfscroll.pack(side=RIGHT, fill=Y)

	cftext1 = Text(cftextframe, width=20, height=14, bg='black', fg='white', highlightthickness=0)
	cftext1.pack(side=LEFT)

	cftext2 = Text(cftextframe, width=20, height=14, bg='black', fg='white', highlightthickness=0)
	cftext2.pack(side=LEFT)

	cftext3 = Text(cftextframe, width=20, height=14, bg='black', fg='white', highlightthickness=0)
	cftext3.pack(side=LEFT)

	cftext4 = Text(cftextframe, width=20, height=14, bg='black', fg='white', highlightthickness=0)
	cftext4.pack(side=LEFT)

	cftext5 = Text(cftextframe, width=20, height=14, bg='black', fg='white', highlightthickness=0)
	cftext5.pack(side=LEFT)

	cftext1.config(yscrollcommand=cfscroll.set)
	cfscroll.config(command=cftext1.yview)

	cftext2.config(yscrollcommand=cfscroll.set)
	cfscroll.config(command=cftext2.yview)

	cftext3.config(yscrollcommand=cfscroll.set)
	cfscroll.config(command=cftext3.yview)

	cftext4.config(yscrollcommand=cfscroll.set)
	cfscroll.config(command=cftext4.yview)

	cftext5.config(yscrollcommand=cfscroll.set)
	cfscroll.config(command=cftext5.yview)

	#--killflags--

	kflabel = LabelFrame(dv_win, text='Global killflags', bg='gray90')
	kflabel.grid(row=3, column=0, padx=10)

	kftextframe = Frame(kflabel)
	kftextframe.pack(padx=5, pady=5)

	kfscroll = Scrollbar(kftextframe)
	kfscroll.pack(side=RIGHT, fill=Y)

	kftext = Text(kftextframe, width=100, height=1, bg='black', fg='white', highlightthickness=0)
	kftext.pack()

	kftext.config(yscrollcommand=cfscroll.set)
	kfscroll.config(command=kftext.yview)

	#--queue--

	qlabel = LabelFrame(dv_win, text='Global queue', bg='gray90')
	qlabel.grid(row=4, column=0, padx=10)

	qtextframe = Frame(qlabel)
	qtextframe.pack(padx=5, pady=5)

	qscroll = Scrollbar(qtextframe)
	qscroll.pack(side=RIGHT, fill=Y)

	qtext = Text(qtextframe, width=100, height=3, bg='black', fg='white', highlightthickness=0)
	qtext.pack()

	qtext.config(yscrollcommand=qscroll.set)
	qscroll.config(command=qtext.yview)

	#--ttime--

	ttlabel = LabelFrame(dv_win, text='Global ttime', bg='gray90')
	ttlabel.grid(row=6, column=0, padx=10)

	tttextframe = Frame(ttlabel)
	tttextframe.pack(padx=5, pady=5)

	ttscroll = Scrollbar(tttextframe)
	ttscroll.pack(side=RIGHT, fill=Y)

	tttext = Text(tttextframe, width=100, height=3, bg='black', fg='white', highlightthickness=0)
	tttext.pack()

	tttext.config(yscrollcommand=ttscroll.set)
	ttscroll.config(command=tttext.yview)

	dump_all() #populate all fields to start




#----------PREFERENCES WINDOW----------

def prefs():
	prefs_win = Toplevel()
	prefs_win.title('Preferences')
	prefs_win.config(bg='gray90')
	prefs_win.bind('<Command-q>', lambda x: quit()) #use internal quit function instead of OSX
	prefs_win.bind('<Control-q>', lambda x: quit())
	prefs_win.bind('<Return>', lambda x: prefsok.invoke())
	prefs_win.bind('<KP_Enter>', lambda x: prefsok.invoke())

	#--variables--
	tout = StringVar() #tkinter variable corresponding to global timeout
	rnice = StringVar() #tkinter variable corresponding to renice_list
	rnice_str = '' #string version of renice_list for readability
	maclist = StringVar() #tkinter variable corresponding to macs list
	maclist_str = '' #more readable verson of macs list
	bpathmac = StringVar() #corresponds to blenderpath_mac
	bpathlin = StringVar() #corresponds to blenderpath_linux
	mgrenders = StringVar() #tkinter var corresponding to maxglobalrenders
	ftlist = StringVar() #corresponds to allowed_filetypes
	allowed_filetypes_str = ''#more readable version of allowed_filetypes

	for comp in renice_list: #makes readable list to put in input field
		rnice_str = rnice_str + comp + ' '

	for comp in macs:
		maclist_str = maclist_str + comp + ' '

	for i in allowed_filetypes:
		allowed_filetypes_str = allowed_filetypes_str + i + ' '

	def set_timeout(): #updates global timeout variable from toinput
		global timeout
		newtime = tout.get()
		try:
			timeout = float(newtime)
			print('timeout is now '+str(timeout)+' s')
		except:
			tkMessageBox.showwarning('Error', 'Must be a number')

	def set_renice(): #updates global renice_list from rninput
		global renice_list
		renice_list = rnice.get().split()
		print('renice_list: ', renice_list)


	def set_maxglobalrenders(): #updates maxglobalrenders
		global maxglobalrenders
		try:
			maxglobalrenders = int(mgrenders.get())
			print('Now allowing 2 simultaneous renders from autostart')
		except:
			tkMessageBox.showwarning('Error', 'Must be an integer')


	def set_maclist(): #updates global macs list from maclist
		global macs
		macs = maclist.get().split()
		print('macs list changed: ', macs)

	def set_bpathmac(): #sets blenderpath_mac
		global blenderpath_mac
		blenderpath_mac = bpathmac.get()
		print('OSX path to blender executable is now', blenderpath_mac)

	def set_bpathlin(): #sets blenderpath_linux
		global blenderpath_linux
		blenderpath_linux = bpathlin.get()
		print('Linux path to blender executable is now', blenderpath_linux)

	def set_ftlist(): #sets allowed_filetypes
		global allowed_filetypes
		allowed_filetypes = ftlist.get().split()

	toframe = LabelFrame(prefs_win, text='Global Timeout', bg='gray90')
	toframe.grid(row=0, column=0, padx=10, pady=10, sticky=W)
	Label(toframe, text='Maximum time renderer will wait between updates before marking a computer as offline and retrying.', wraplength=225, bg='gray90').pack()
	toinput = Entry(toframe, textvariable=tout, width=5, highlightthickness=0)
	toinput.pack(side=LEFT, padx=3, pady=3)
	Label(toframe, text='sec.', bg='gray90', highlightthickness=0).pack(side=LEFT)
	ttk.Button(toframe, text='Set', command=set_timeout).pack(side=RIGHT, padx=3, pady=3)
	toinput.insert(END, timeout)

	mgframe = LabelFrame(prefs_win, text='Max. Simul. Renders', bg='gray90')
	mgframe.grid(row=0, column=1, padx=10, pady=10, sticky=E)
	Label(mgframe, text='Max number of simultaneous renders that can be initiated by the autostart function.', wraplength=225, bg='gray90').pack()
	mginput = Entry(mgframe, textvariable=mgrenders, width=5, highlightthickness=0)
	mginput.pack(side=LEFT, padx=3, pady=3)
	ttk.Button(mgframe, text='Set', command=set_maxglobalrenders).pack(side=RIGHT, padx=3, pady=3)
	mginput.insert(END, maxglobalrenders)

	rnframe = LabelFrame(prefs_win, text='Renice List', bg='gray90')
	rnframe.grid(row=1, column=0, columnspan=2, padx=10, pady=10)
	Label(rnframe, text='Space-separated list of computers to run at lowest priority.', bg='gray90').grid(row=0, column=0, columnspan=2, padx=3, pady=3, sticky=W)
	rninput = Entry(rnframe, textvariable=rnice, width=50, highlightthickness=0)
	rninput.grid(row=1, column=0, padx=3, pady=3)
	ttk.Button(rnframe, text='Set', command=set_renice).grid(row=1, column=1, padx=3, pady=3)
	rninput.insert(END, rnice_str)

	bpath_mac_frame = LabelFrame(prefs_win, text='Blender OSX Path', bg='gray90')
	bpath_mac_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10)
	Label(bpath_mac_frame, text='Path to Blender executable on Mac OSX.', bg='gray90').grid(row=0, column=0, columnspan=2, padx=3, pady=3, sticky=W)
	bpath_mac_input = Entry(bpath_mac_frame, textvariable=bpathmac, width=50, highlightthickness=0)
	bpath_mac_input.grid(row=1, column=0, padx=3, pady=3)
	ttk.Button(bpath_mac_frame, text='Set', command=set_bpathmac).grid(row=1, column=1, padx=3, pady=3)
	bpath_mac_input.insert(END, blenderpath_mac)

	bpath_linux_frame = LabelFrame(prefs_win, text='Blender Linux Path', bg='gray90')
	bpath_linux_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=10)
	Label(bpath_linux_frame, text='Path to Blender executable on Linux.', bg='gray90').grid(row=0, column=0, columnspan=2, padx=3, pady=3, sticky=W)
	bpath_linux_input = Entry(bpath_linux_frame, textvariable=bpathlin, width=50, highlightthickness=0)
	bpath_linux_input.grid(row=1, column=0, padx=3, pady=3)
	ttk.Button(bpath_linux_frame, text='Set', command=set_bpathlin).grid(row=1, column=1, padx=3, pady=3)
	bpath_linux_input.insert(END, blenderpath_linux)

	macsframe = LabelFrame(prefs_win, text='Mac Computer List', bg='gray90')
	macsframe.grid(row=4, column=0, columnspan=2, padx=10, pady=10)
	Label(macsframe, text='Space-separated list of OSX computers.', bg='gray90').grid(row=0, column=0, columnspan=2, padx=3, pady=3, sticky=W)
	macsinput = Entry(macsframe, textvariable=maclist, width=50, highlightthickness=0)
	macsinput.grid(row=1, column=0, padx=3, pady=3)
	ttk.Button(macsframe, text='Set', command=set_maclist).grid(row=1, column=1, padx=3, pady=3)
	macsinput.insert(END, maclist_str)

	ftframe = LabelFrame(prefs_win, text='Allowed File Types', bg='gray90')
	ftframe.grid(row=5, column=0, columnspan=2, padx=10, pady=10)
	Label(ftframe, text='Allowed file extensions (last 3 characters only) for missing frame check', bg='gray90').grid(row=0, column=0, columnspan=2, padx=3, pady=3, sticky=W)
	ftinput = Entry(ftframe, textvariable=ftlist, width=50, highlightthickness=0)
	ftinput.grid(row=1, column=0, padx=3, pady=3)
	ttk.Button(ftframe, text='Set', command=set_ftlist).grid(row=1, column=1, padx=3, pady=3)
	ftinput.insert(END, allowed_filetypes_str)

	prefsok = ttk.Button(prefs_win, text='Done', command=prefs_win.destroy, style='Toolbutton')
	prefsok.grid(row=6, column=1, padx=10, pady=10, sticky=E)
	
	



#----------EXTRAFRAMES BALLOON---------
#displays long list of extraframes in popup box
def extraballoon(event, index):
	extras = renderJobs[index][3]
	if len(extras) <= 2: #don't open window if there aren't enough frames to show 
		return

	if event.x_root < 0: #protect against crashes caused by negative window offsets on multiple monitors.
		x = '+0'
	else:
		x = '+'+str(event.x_root - 20)

	if event.y_root < 0:
		y = '+0'
	else:
		y = '+'+str(event.y_root)

	exwin = Toplevel()
	exwin.transient() #specifies that window is transient
	exwin.overrideredirect(True) #disables title bar & other decorations
	exwin.geometry(x+y)
	jobstatFrame.nametowidget('jobstat_'+str(index)+'.extrafram_'+str(index)).bind('<Leave>', lambda x: exwin.destroy()) #destroy window when cursor leaves area

	extras.sort()
	for frame in extras:
		if frame != 0:
			Label(exwin, text=frame).pack(padx=5)




#----------FILENAME BALLOON---------
#displays file path in popup box
def nameballoon(event, index):
	filepath = renderJobs[index][0]
	#if len(filepath) <= 18: #don't open if filepath isn't truncated
	#	return
	if event.x_root < 0: #protect against crashes caused by negative window offsets on multiple monitors.
		x = '+0'
	else:
		x = '+'+str(event.x_root - 40)

	if event.y_root < 0:
		y = '+0'
	else:
		y = '+'+str(event.y_root)

	namewin = Toplevel()
	namewin.transient()
	namewin.overrideredirect(True)
	namewin.geometry(x+y)
	jobstatFrame.nametowidget('jobstat_'+str(index)+'.filenam_'+str(index)).bind('<Leave>', lambda x: namewin.destroy())

	Label(namewin, text=filepath).pack(padx=5, pady=5)




#----------CHECK MISSING FRAMES WINDOW---------
def check_frames_window():

	def get_breaks():
		'''isolate sequential numbers and determine left & right break points'''
		global checkframes
		path = check_path.get()
		dir_contents = subprocess.check_output('ls '+path, shell=True).split()
	
		for line in dir_contents:
			if line[-3:] in allowed_filetypes:
				filename = line
				name, ext = line.split('.')
				filesok = True
				break
			else:
				filesok = False

		if filesok == False:
			tkMessageBox.showwarning('Error', 'No suitable files found in directory.  Check path and try again.')
			return
	
		#reverse filename and check backwards from end until a non-digit is found.  Assume this is start of name text
		#intended to prevent problems if there are numbers in filename before sequential numbers
		length = range(len(name))
		length.reverse()
		for i in length:
			if not name[i].isdigit():
				leftbreak = i+1
				rightbreak = len(filename) - len(ext) - 1 #assuming sequential #s go to end of filename
				sequentials = filename[leftbreak:rightbreak]
				break

		#configure slider initial state
		slidelength = len(filename)
		slider_left.config(to=slidelength)
		slider_right.config(to=slidelength)
		slider_left.set(leftbreak)
		slider_right.set(rightbreak)
		nameleft.config(text=filename[0:leftbreak])
		nameseq.config(text=sequentials)
		nameright.config(text=filename[rightbreak:])
		checkframes['rightbreak'] = rightbreak
		checkframes['leftbreak'] = leftbreak
		checkframes['sequentials'] = sequentials
		checkframes['dir_contents'] = dir_contents
		checkframes['filename'] = filename
		getlist()
	
	
	def put_text(): #puts info for existing jobs into text fields
		checkin.delete(0, END)
		startent.delete(0, END)
		endent.delete(0, END)
	
		index = checkjob.get()
		if not index == 0: 
			chkpath = renderJobs[index][0]
			if tkMessageBox.askokcancel('Confirm', 'Browse to render directory now?'):
				chkpath = tkFileDialog.askdirectory(initialdir=chkpath)
			check_path.set(chkpath)
			check_start.set(renderJobs[index][1])
			check_end.set(renderJobs[index][2])

	
	def get_slider():
		global checkframes
		if not checkframes:
			return

		filename = checkframes['filename']
		leftbreak = int(slider_left.get())
		rightbreak = int(slider_right.get())
		sequentials = filename[leftbreak:rightbreak]
		nameleft.config(text=filename[0:leftbreak])
		nameseq.config(text=sequentials)
		nameright.config(text=filename[rightbreak:])
		checkframes['leftbreak'] = leftbreak
		checkframes['rightbreak'] = rightbreak
		checkframes['sequentials'] = sequentials
	
	
	def get_framecheck_path(): #handles the browse button
		filepath = tkFileDialog.askdirectory() 
		check_path.set(filepath)
	
	def getlist():
		dir_contents = checkframes['dir_contents']
		leftbreak = checkframes['leftbreak']
		rightbreak = checkframes['rightbreak']
		sequentials = checkframes['sequentials']

		for i in sequentials:
			if not i.isdigit():
				tkMessageBox.showwarning('Error', 'Sequential file numbers must contain only integers.')
				return


		dirconts.delete(0.0, END)
		foundfrms.delete(0.0, END)
		expfrms.delete(0.0, END)
		missfrms.delete(0.0, END)

		frames_expected = []
		frames_found = []
		frames_missing = []

		chkpath = check_path.get()
		if chkpath[-1] != '/': #make sure trailing slash is present
			chkpath = chkpath + '/'

		start = int(check_start.get())
		end = int(check_end.get())

		for frame in range(start, end + 1):
			frames_expected.append(frame)

		for line in dir_contents:
			dirconts.insert(END, str(line)+'\n')
			if line [-3:] in allowed_filetypes: #verify that line is an image
				frameno = int(line[leftbreak:rightbreak])
				frames_found.append(frameno)
				foundfrms.insert(END, str(frameno)+'\n')

		for frame in frames_expected:
			expfrms.insert(END, str(frame)+'\n')
			if not frame in frames_found:
				frames_missing.append(frame)
				missfrms.insert(END, str(frame)+'\n')

		if not frames_missing:	
			missfrms.insert(END, 'None')


	def chkclose():
		global checkframes
		checkframes = None
		checkframes = dict()
		cfwin.destroy()
	
	
	cfwin = Toplevel()
	cfwin.title('Check for Missing Frames')
	cfwin.config(bg='gray90')
	checkjob = IntVar()
	checkjob.set(0)
	Label(cfwin, text='Compare the contents of a directory against a generated file list to search for missing frames.', bg='gray90').grid(row=0, column=0, padx=10, pady=10, sticky=W)

	cfframe = LabelFrame(cfwin)
	cfframe.grid(row=1, column=0, padx=10, pady=10)
	Label(cfframe, text='Check existing job:').grid(row=0, column=0, padx=5, pady=5, sticky=E)
	bbox = Frame(cfframe)
	bbox.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky=W)
	ttk.Radiobutton(bbox, text='None', variable=checkjob, value=0, command=put_text, style='Toolbutton').grid(row=0, column=1, sticky=W)
	
	for i in range(1, queueslots + 1):
		if Job(i).checkSlotFree():
			btnstate = 'disabled' #disable job buttons for empty queue slots
		else:
			btnstate = 'normal'
		ttk.Radiobutton(bbox, text=str(i), variable=checkjob, value=i, command=put_text, state=btnstate, style='Toolbutton').grid(row=0, column=i+1, sticky=W)
	
	Label(cfframe, text='Directory to check:').grid(row=1, column=0, padx=5, pady=5, sticky=E)
	checkin = Entry(cfframe, textvariable=check_path, width=50)
	checkin.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=W)
	Button(cfframe, text='Browse', command=get_framecheck_path).grid(row=1, column=4, padx=5, pady=5, sticky=W)
	
	Label(cfframe, text='Start frame:').grid(row=2, column=0, padx=5, pady=5, sticky=E)
	startent = Entry(cfframe, textvariable=check_start, width=20)
	startent.grid(row=2, column=1, padx=5, pady=5, sticky=W)

	Label(cfframe, text='End frame:').grid(row=3, column=0, padx=5, pady=5, sticky=E)
	endent = Entry(cfframe, textvariable=check_end, width=20)
	endent.grid(row=3, column=1, padx=5, pady=5, sticky=W)

	startbtn = Button(cfframe, text='Generate lists', command=get_breaks)
	startbtn.grid(row=4, column=0, padx=5, pady=5, sticky=E)
	Button(cfframe, text='Update lists', command=getlist).grid(row=4, column=1, sticky=W)
	cfwin.bind('<Return>', lambda x: startbtn.invoke())
	cfwin.bind('<KP_Enter>', lambda x: startbtn.invoke())
	cfwin.bind('<Command-w>', lambda x: chkclose())
	cfwin.bind('<Control-w>', lambda x: chkclose())
	

	confirmframe = LabelFrame(cfframe, text='Adjust Filename Parsing')
	confirmframe.grid(row=2, rowspan=3 , column=2, columnspan=3, padx=10, pady=5, ipady=5, sticky=W)
	Label(confirmframe, text='Move sliders to isolate sequential file numbers.').grid(row=0, column=0, columnspan=3)

	nameleft = Label(confirmframe, fg='gray50')
	nameleft.grid(row=1, column=0)

	nameseq = Label(confirmframe, fg='DarkRed')
	nameseq.grid(row=1, column=1)

	nameright = Label(confirmframe, fg='gray50')
	nameright.grid(row=1, column=2)
	
	slider_left = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, length=300, command=lambda x: get_slider())
	slider_left.grid(row=2, column=0, columnspan=3)
	
	slider_right = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, length=300, command=lambda x: get_slider())
	slider_right.grid(row=3, column=0, columnspan=3)

	
	resultframe = LabelFrame(cfframe, text='Result')
	resultframe.grid(row=5, column=0, columnspan=5, padx=10, pady=5, ipady=5)

	Label(resultframe, text='Directory contents:').grid(row=0, column=0, padx=5, sticky=W)
	dirconts = st.ScrolledText(resultframe, width=38, height=10, highlightthickness=0, bd=4) #directory contents
	dirconts.frame.config(border=2, relief=GROOVE)
	dirconts.grid(row=1, column=0, padx=5, sticky=W)

	Label(resultframe, text='Found:').grid(row=0, column=1, padx=5, sticky=W)
	foundfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #found frame numbers after parsing
	foundfrms.frame.config(border=2, relief=GROOVE)
	foundfrms.grid(row=1, column=1, padx=5, sticky=W)

	Label(resultframe, text='Expected:').grid(row=0, column=2, padx=5, sticky=W)
	expfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #expected frames
	expfrms.frame.config(border=2, relief=GROOVE)
	expfrms.grid(row=1, column=2, padx=5, sticky=W)

	Label(resultframe, text='Missing:').grid(row=0, column=3, padx=5, sticky=W)
	missfrms = st.ScrolledText(resultframe, width=10, height=10, highlightthickness=0, bd=4) #missing frames
	missfrms.frame.config(border=2, relief=GROOVE)
	missfrms.grid(row=1, column=3, padx=5, sticky=W)
	
	
	ttk.Button(cfframe, text='Close', command=chkclose, style='Toolbutton').grid(column=4, padx=10, pady=5, sticky=E)







#------GUI LAYOUT------

topbar = Frame(root, bd=0, bg='gray90')
topbar.grid(row=0, column=0, padx=10, sticky=W)

verbosebtn = ttk.Checkbutton(topbar, text='Verbose', variable=verbosity, command=toggle_verbosity, style='Toolbutton')
verbosebtn.grid(row=0, column=0, pady=5, sticky=W)

autobtn = ttk.Checkbutton(topbar, text='Autostart', variable=stnext, command=set_startnext, style='Toolbutton')
autobtn.grid(row=0, column=1, padx=5, sticky=W)

prefsbutton = ttk.Button(topbar, text='Prefs', command=prefs, style='Toolbutton')
prefsbutton.grid(row=0, column=2, padx=5, sticky=W)

dumpbtn = ttk.Button(topbar, text='Show Variables', command=dump_vars_win, style='Toolbutton')
dumpbtn.grid(row=0, column=3, padx=5, pady=5, sticky=W)

chkfrmbtn = ttk.Button(topbar, text='Check Missing Frames', command=check_frames_window, style='Toolbutton')
chkfrmbtn.grid(row=0, column=4, padx=5, pady=5, sticky=W)

quitbutton = ttk.Button(topbar, text='Quit', command=quit, style='Toolbutton')
quitbutton.grid(row=0, column=5, padx=5, pady=5, sticky=E)



container = LabelFrame(root, bg='white')
container.grid(row=1, column=0, padx=10)

jobstatFrame = LabelFrame(container, width=685, bd=0)
jobstatFrame.grid(row=0, padx=5, pady=5, sticky=N+W)
container.bind('<Control-n>', lambda x: input_window()) #lambda b/c input_window does not take an event arg
container.bind('<Command-n>', lambda x: input_window()) #alt keybinding for OSX


#lists of widget names to simplify color change functions
jobstat_label_list = ['filenam_', 'startfram_', 'endfram_', 'extrafram_', 'vrule3_', 'vrule4_', 'vrule5_']
otherwidgets = ['statlight_', 'buttonframe_', 'timecanv_', 'perdone_']
buttons = ['editbutton_', 'startbutton_', 'stopbutton_', 'resumebutton_', 'removebutton_', 'spacer_']
timefields = ['totaltime_', 'avgframetime_', 'estremain_']

for i in renderJobs:
	jobstat = ClickFrame(jobstatFrame, name='jobstat_'+str(i), index=i)
	jobstat.grid(row=i, column=0, padx=0, pady=0)

	ClickCanvas(jobstat, name='statlight_'+str(i), width=121, height=21, index=i, highlightthickness=0).grid(row=0, column=0, padx=0, sticky=W)

	NameHoverLabel(jobstat, name='filenam_'+str(i), text='', wraplength=130, anchor=W, index=i).grid(row=0, column=1, padx=0, sticky=W)
	ClickLabel(jobstat, name='vrule3_'+str(i), text='|', width=1, anchor=W, index=i).grid(row=0, column=2, padx=0)

	ClickLabel(jobstat, name='startfram_'+str(i), text='', anchor=W, index=i).grid(row=0, column=3, padx=0, sticky=W)
	ClickLabel(jobstat, name='vrule4_'+str(i), text='|', width=1, anchor=W, index=i).grid(row=0, column=4, padx=0)

	ClickLabel(jobstat, name='endfram_'+str(i), text='', anchor=W, index=i).grid(row=0, column=5, padx=0, sticky=W)
	ClickLabel(jobstat, name='vrule5_'+str(i), text='|', width=1, anchor=W, index=i).grid(row=0, column=6, padx=0)

	FramesHoverLabel(jobstat, name='extrafram_'+str(i), text='', wraplength=150, anchor=W, index=i).grid(row=0, column=7, columnspan=2, padx=0, sticky=W)

	timecanv = ClickCanvas(jobstat, name='timecanv_'+str(i), width=615, height=20, highlightthickness=0, index=i)
	timecanv.grid(row=1, column=0, columnspan=8, sticky=W)
	timecanv.create_text(35, 10, text='Total time:')
	timecanv.create_text(240, 10, text='Avg/frame:')
	timecanv.create_text(448, 10, text='Remaining:')

	ClickProg(jobstat, length=500, variable=totalprog[i], index=i).grid(row=2, column=0, columnspan=8, sticky=W)
	perdone = ClickCanvas(jobstat, width=110, height=20, name='perdone_'+str(i), index=i, highlightthickness=0)
	perdone.grid(row=2, column=7, sticky=E, padx=3) 
	perdone.create_text(55, 9, text='0% Complete')
	

	buttonframe = ClickFrame(jobstat, index=i, name='buttonframe_'+str(i), bd=0)
	buttonframe.grid(row=3, column=0, columnspan=8, sticky=W)
	DoubleButton(buttonframe, name='editbutton_'+str(i), text='New / Edit', index=i, command=input_window).grid(row=0, column=0, sticky=W)
	DoubleButton(buttonframe, name='startbutton_'+str(i), text='Start', index=i, command=startJob).grid(row=0, column=1, sticky=W)
	DoubleButton(buttonframe, name='stopbutton_'+str(i), text='Stop', index=i, command=killJob).grid(row=0, column=2, sticky=W)
	DoubleButton(buttonframe, name='resumebutton_'+str(i), text='Resume', index=i, command=resumeJob).grid(row=0, column=3, sticky=W)
	ClickLabel(buttonframe, name='spacer_'+str(i), text='                                                     ', index=i).grid(row=0, column=4) #spacer to push remove button to right
	DoubleButton(buttonframe, name='removebutton_'+str(i), text='Remove Job', index=i, command=removeJob).grid(row=0, column=5, sticky=E)

	


#---Statbox Frame---

compstat = LabelFrame(container, bd=0, bg='white')
compstat.grid(row=0, column=1, padx=5, pady=0, sticky=N+W)

top_info = Frame(compstat) 
top_info.grid(row=0, column=0, sticky=W, padx=5, pady=5)

joblabel = Canvas(top_info, width=80, height=31, highlightthickness=0) 
joblabel.grid(row=0, column=0, sticky=W)

joblight = Canvas(top_info, width=120, height=31, highlightthickness=0)
joblight.grid(row=0, column=1, sticky=W)

filelabel = Canvas(top_info, width=261, height=31, highlightthickness=0)
filelabel.grid(row=0, column=2, sticky=W)

scrollcontainer = Frame(compstat) #container to control location of scrollbar
scrollcontainer.grid(row=1, column=0)

canvas = Canvas(scrollcontainer, width=461, height=555, scrollregion=(0, 0, 461, 900), bg='white') #height is reset in update() based on root window height.
vbar = Scrollbar(scrollcontainer, orient=VERTICAL)
vbar.pack(side=RIGHT, fill=Y)
vbar.config(command=canvas.yview)

canvas.config(yscrollcommand=vbar.set)

statframe = Frame(canvas, bg='white') #Holds status boxes 

for i in range(len(computers)): 

	statbox = LabelFrame(statframe, name=computers[i]+'_statbox')
	statbox.grid(row=i, column=0)

	compdata = Canvas(statbox, name=computers[i]+'_compdata', height=20, width=355, highlightthickness=0) 
	compdata.grid(row=0, column=0, columnspan=3) #change row to 0 when done

	compdata.create_text(5, 10, anchor=W, text=computers[i])
	compdata.create_text(130, 10, anchor=W, text='Frame:')
	compdata.create_text(180, 10, anchor=W, text='0000') #framenumber placeholder
	compdata.create_text(279, 10, anchor=E, text='100') #percentage placeholder
	compdata.create_text(280, 10, anchor=W, text='% Complete')

	pbar = ttk.Progressbar(statbox, variable=progvars[computers[i]], length=350)
	pbar.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=W)

	togglebtn = ToggleCanv(statbox, name=computers[i]+'_togglebtn', height=40, width=40, highlightthickness=0, bg='gray80', computer=computers[i])
	togglebtn.grid(row=0, rowspan=2, column=3, padx=5, pady=5)

	killbtn = KillCanv(statbox, name=computers[i]+'_killbtn', height=40, width=40, highlightthickness=0, bg='gray80', computer=computers[i])
	killbtn.grid(row=0, rowspan=2, column=4, padx=5, pady=5)
	killbtn.create_rectangle(2, 2, 37, 37, outline='gray50', fill='gray90')
	killbtn.create_text(20, 20, text='Kill' )

statframe.pack()
canvas.create_window(0, 0, window=statframe, anchor=NW)
canvas.pack(side=LEFT, expand=True, fill=BOTH)

Frame(root).grid(row=2, column=0, pady=5) #spacer to pad bottom of window




set_job(1) #always starts with the first queue slot active
update()
check_job_queue()
root.mainloop()
