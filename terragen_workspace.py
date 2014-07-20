import subprocess

tgn_cmd = 'ssh igp@conundrum "cd /Applications/Terragen\ 3/Terragen\ 3.app/Contents/MacOS/&&./Terragen\ 3 -p /Users/jim/test_render/terragen_test.tgd -hide -exit -r -f 1 & pgrep -n Terragen&wait"'


class RenderThread(object):

	def send_command_terragen(self):

		command = subprocess.Popen(tgn_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

		self.output = ''
		for line in iter(command.stdout.readline, ''):
			if line:
				pass
			#NOTE: timeout will be a problem.  Need to find workaround for terragen. Maybe make timeout an instance var instead of global
			#	with threadlock:
			#		renderJobs[self.index][6][self.computer] = [self.frame, time.time()] #reset timer every time an update is received

			#No continuous status info, so parseline replaced with a few specific conditionals
			#actually it appears there are periodic updates, just not if render time is quick
			if line.find('Starting') >= 0:
				#starting overall render or one of the render passes
				ellipsis = line.find('...')
				passname = line[10:ellipsis]
				print('Starting '+passname)

			elif line.find('Rendered') >= 0:
				#finished one of the render passes
				mark = line.find('of ')
				passname = line[mark+3:]
				print('Finished '+passname)

			elif line.find('Rendering') >= 0:
				#pattern 'Rendering pre pass... 0:00:30s, 2% of pre pass'
				#NOTE: terragen ALWAYS has at least 2 passes, so prog bars to to 100% twice.  Need to note this somewhere or workaround.
				#could scale percentages so that prepass accounts for no more than 50% of progress bar

				#get name of pass:
				ellipsis = line.find('...')
				passname = line[10:ellipsis]

				#get percent complete for pass
				for i in line.split():
					if '%' in i:
						pct_str = i
						percent = float(pct_str[:-1])

				print('Rendering '+passname+', '+str(pct_int)+'% complete.')
				#pass info to progress bars (equiv of parseline())
				#self.termout = [self.computer, self.frame, percent] 
				#with threadlock:
				#	renderJobs[self.index][10] = self.termout


			elif line.strip().isdigit(): #detect PID at first line
				pid = int(line)
				print('PID detected: '+str(pid))
				#with threadlock:
				#	renderJobs[self.index][5][self.computer] = pid
				#if self.computer in renice_list: #renice process to lowest priority on specified comps 
				#	subprocess.call('ssh igp@'+self.computer+' "renice 20 -p '+str(pid)+'"', shell=True)
				#	print('reniced PID '+str(pid)+' to pri 20 on '+self.computer) #for debugging
				#if skiplists[self.index]:
				#	with threadlock:
				#		skiplists[self.index].pop(0) #remove oldest entry from skip list
				#		print('frame sent. Removing oldest item from skiplist') #debugging

			elif line.find('Finished') >= 0:
				print('Finished:'+line)
				print(type(line))
				rendertime = line.split()[2][-1]

			#	print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|Received after '+rendertime) 
				print('Render complete, rendertime: '+str(rendertime))
				#RenderLog(self.index).frame_received(self.computer, self.frame, rendertime)
				#with threadlock:
				#	compflags[str(self.index)+'_'+self.computer] = 0
				#with threadlock:
				#	if 0 in renderJobs[self.index][7]: #total frames
				#		renderJobs[self.index][7].remove(0) #remove a placeholder
				#	renderJobs[self.index][7].append(self.frame)
				#	try:
				#		del renderJobs[self.index][6][self.computer] #delete currentFrames entry
				#	except:
				#		print 'failed to delete currentFrames entry for ', self.computer #debugging
				#		pass
				#with threadlock:
				#	queue['q'+str(self.index)].task_done() 
                        else:
                                self.output = self.output + line

			#if verbose: #verbose terminal output
			#	if line:
			#		print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|STDOUT: '+line)

		for line in iter(command.stderr.readline, ''):
			if line: #assume any text in STDERR means connection/render failure
				#with threadlock:
				#	queue['q'+str(self.index)].put(self.frame)
				#with threadlock:
				#	compflags[str(self.index)+'_'+self.computer] = 0 #reset compflag to try again on next round
				#with threadlock:
				#	skiplists[self.index].append(self.computer)
				print('Text in stderr.' ) #debugging
				print('STDERR:'+line)

				#print('ERROR:Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|STDERR: '+line) 
				#RenderLog(self.index).error(self.computer, self.frame, 3, line) #error code 1

		#it appears that terragen reports all errors to STDERR so no need for check_warn()
		###if self.check_warn(self.output):
			#with threadlock:
			#	queue['q'+str(self.index)].put(self.frame)
			#with threadlock:
			#	compflags[str(self.index)+'_'+self.computer] = 0 #reset compflag to try again on next round

		###	print('ERROR|Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+'|Blender returned a warning. Offending line: '+self.output)
			#RenderLog(self.index).error(self.computer, self.frame, 2, line) #error code 2

	def check_warn(self, output):
		'''returns true if blender throws a warning'''
	        if self.output.find('Warning:') >= 0:
	                return True 
		elif self.output.find('Error:') >= 0:
			return True 
	        else:
	                return False 

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



RenderThread().send_command_terragen()
