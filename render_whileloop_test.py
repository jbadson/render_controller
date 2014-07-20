while 1:
	if killflags == 1:
		break

	self.computerList = renderJobs[self.index][4]

	for computer in self.computerList:
		if compflags[str(self.index)+'_'+computer] == 0: #no active thread:

			if queue['q'+str(self.index)].empty(): #break loop if queue['q'+str(self.index)] becomes empty after a new computer is added
				break
			else:
				frame = queue['q'+str(self.index)].get()
	
			with threadlock:
				compflags[str(self.index)+'_'+computer] = 1 #set compflag as active
				#renderJobs[self.index][6][computer] = [frame, time.time()] #start timeout timer
			print 'creating RenderThread with ', self.index, self.path, computer, frame  #debugging
			RenderThread(self.index, self.path, computer, frame).create()

		else: #if thread is active on computer

			if not computer in self.currentFrames: #computer not been sent a frame 
				with threadlock:
					compflags[str(self.index)+'_'+computer] = 0 #reset compflag, send back to loop
					#should not need to set timer here because computer should either be sent a frame next time through or queue['q'+str(self.index)] should be empty.
				time.sleep(0.01)
				continue

			else: #computer has been sent a frame
				if time.time() - self.currentFrames[computer][-1] > timeout: #timeout exceeded
					print('ERROR:Job:'+str(self.index)+'|Fra:'+str(frame)+'|'+computer+'|Timed out in render loop. Retrying')
					RenderLog(self.index).error(computer, frame, 3, '') #error code 3, no output line
					try:
						subprocess.call('ssh igp@'+computer+' "kill '+str(self.threads[computer])+'"', shell=True)
					except: #skip kill command if threads entry is blank (ssh timeout)
						pass
					with threadlock:
						queue['q'+str(self.index)]['q'+str(self.index)].put(self.currentFrames[computer][0]) #return frame to queue['q'+str(self.index)]
						compflags[str(self.index)+'_'+computer] = 0 #reset compflag to try again on next round
						currentFrames[computer] #remove currentFrames entry
