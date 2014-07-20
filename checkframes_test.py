'''
1. Determine if 'Check existing job' was used.  If so, grab data from existing renderJobs entry

2. If not, look for an empty job slot then enqueue.

3. If no empty slots, ask if user would like to overwrite existing item, verify status != Rendering, clear, then enqueue

??Disable autostart or give option to start immediately??
'''

#if a job was selected, intvar checkjob == index, otherwise checkjob == 0. Resets each time window is opened.

def enqueue_missing_frames(frames_missing):
	if frames_missing == 'None': #close if no missing frames
		return

	startframe = frames_missing[0]
	endframe = frames_missing[0] #start=end to circumvent error check. Remainder go in extraframes box.


	index = checkjob.get()
	if not index == 0:
		#job exists, use existing information from renderJobs
		pass

	else: #no job selected, need to create new queue object
		#need to get an empty queue slot
		for i in renderJobs:
			if Job(i).checkSlotFree():
				open_index = i
				break

		if not open_index: #no empty slots found
			#ask for one to overwrite
			pass

		#try just opening input window and setting variables directly
		jobNumber.set(open_index)
		input_window()
		
		extrastring = '' #string to put in input box
		if len(frames_missing) > 1: #make sure there are additional frames
			for i in frames_missing:
				if i == 0:
					pass
				else:
					extrastring = extrastring + i + ' '
		startInput.set(startframe)
		endInput.set(endframe)
		extrasInput.set(extrastring)
		











def get_empty_slot():
	for i in renderJobs:
		if Job(i).checkSlotFree():
			#enqueue here
			return i
	#no empty job slots
	#warning message, choose job to overwrite
	#NOTE: need index
	#enque here
	return index

#this will be a Job() method...
def enqueue_extra_frames(self):

