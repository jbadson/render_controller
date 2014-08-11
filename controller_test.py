#Fourth major revision of IGP render controller by Jim Adson
#Core render module based on original renderscript by Eric Lobato

import Queue
import subprocess
import threading
from Tkinter import *
import time
import tkMessageBox
import tkFileDialog
import tkFont
import ttk
from os import path, _exit
import ScrolledText as st
import json
import cfgfile



class Job(object):
    '''represents a render job in a single queue slot'''

    def __init__(self, index):
        '''populate all variables for a given index from the global renderJobs 
        dict'''
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
        self.render_engine = renderJobs[self.index][12]

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
            self.render_data = [self.path, self.startframe, self.endframe,
            self.extraframes, self.computerList, self.threads, 
            self.currentFrames, self.totalFrames, self.status, self.index, 
            self.termout, self.timestart, self.render_engine]
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
        self.render_engine = 'blender'
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
                Dialog('Cannot modify a queue item while it is rendering.').warn()
                return False
            if self.status == 'Stopped':
                Dialog('Cannot change start, end, or extra frames once render has '
                        + 'been started.').warn()
                return False
            if not Dialog('Overwrite existing queue contents?').confirm():
                return False
            if self.status == 'Finished':
                self.clear()

        if not pathInput.get():
            Dialog('Path, start frame, end frame, and computers must be '
                    + 'specified.').warn()
            return False


        self.render_engine = render_eng.get()
        
        self.path = pathInput.get()
        if not path.exists(self.path): 
            Dialog('File path invalid or inaccessible.').warn()
            return False

        #verify that file suffix matches selected render engine
        if self.render_engine == 'blender':
            if not self.path.find('.blend') > 0:
                Dialog('File suffix does not match selected render engine.').warn()
                return False
        elif self.render_engine == 'terragen':
            if not self.path.find('.tgd') > 0:
                Dialog('File suffix does not match selected render engine.').warn()
                return False
        else:
            print('Unknown error in render engine selector.')
            return False

        try:
            self.startframe = int(startInput.get())
            self.endframe = int(endInput.get())
        except:
            Dialog('Frame numbers must be integers.').warn()
            return False


        if not self.endframe >= self.startframe:
            Dialog('End frame must be greater than or equal to start '
                    + 'frame.').warn()
            return False

        self.extraframes = []
        for frame in extrasInput.get().split():
            try:
                if frame != 0:
                    self.extraframes.append(int(frame))
            except:
                Dialog('Extra frames must be integers separated by spaces '
                        + 'only.').warn()
                return False

        if self.extraframes != []:
            for i in self.extraframes:
                if i-1 in range(self.endframe - self.startframe + 1):
                    Dialog('Extra frames are in the start-end frame range.').warn()
                    return False

        #complicated because comp names have to be strings but vars can't
        self.computerList = [] 
        for i in range(len(compvars)):
            if compvars[i].get():
                self.computerList.append(computers[i])

        if self.computerList == []:
            Dialog('Path, start frame, end frame, and computers must be '
                    + 'specified.').warn()
            return False

        '''fill totalFrames list with zeros so that len(totalFrames) returns 
            total number to be rendered. Used for calculating percent complete'''
        for i in range(self.startframe, self.endframe + 1 + 
            len(self.extraframes)):
            self.totalFrames.append(0) 

        with threadlock:
            killflags[self.index] = 0 #reset killflag just in case

        RenderTimer(self.index).clear() #set timer to zero for a fresh render

        self.status = 'Waiting'
        self.update()
        return True


    def render(self):
        '''creates a queue of frames and assigns them to RenderThreads()'''

        if self.status != 'Waiting':
            Dialog('Render cannot be started unless job status is '
                    + '"Waiting"').warn()
            return

        self.status = 'Rendering'
        RenderTimer(self.index).start()
        RenderLog(self.index).render_started()

        with threadlock:
            queue['q'+str(self.index)] = Queue.LifoQueue(0) 
    
        framelist = range(self.startframe, self.endframe + 1)
        #Reverse order for LifoQueue
        framelist.reverse() 

        for frame in framelist:
            with threadlock:
                queue['q'+str(self.index)].put(frame)

        if len(self.extraframes) > 0:
            #render lower frame numbers first
            self.extraframes.reverse() 
            for frame in self.extraframes:
                with threadlock:
                    queue['q'+str(self.index)].put(frame)

        self.update()
        global skiplists
        with threadlock:
            skiplists[self.index] = []

        #master thread to control RenderThreads 
        def masterthread(): 
            global compflags

            #---RENDER LOOP---
            while not queue['q'+str(self.index)].empty():
                if killflags == 1:
                    break
            
                self.computerList = renderJobs[self.index][4]
                for computer in self.computerList:
                    #no active thread
                    if compflags[str(self.index)+'_'+computer] == 0:  
                        #skip flag raised
                        if computer in skiplists[self.index]: 
                            continue
                        #break loop if queue becomes empty after a new 
                        #computer is added
                        elif queue['q'+str(self.index)].empty(): 
                            break
                        else:
                            frame = queue['q'+str(self.index)].get()
                
                        with threadlock:
                            #set compflag as active
                            compflags[str(self.index)+'_'+computer] = 1 
                            #moving add currentFrames here b/c of multple 
                            #renderthread sending issue.
                            #add to currentFrames & start timeout timer
                            self.currentFrames[computer] = [frame, time.time()] 
                            renderJobs[self.index][6] = self.currentFrames 
                
                        RenderThread(self.index, self.path, computer, frame).create()
                        #if skiplists[self.index]:
                        #    with threadlock:
                                 #remove oldest entry from skip list
                        #        skiplists[self.index].pop(0) 
            
                    #if thread is active on computer or computer was skipped
                    else: 
                        #computer has not been sent a frame 
                        if not computer in self.currentFrames: 
                            with threadlock:
                                #reset compflag, send back to loop
                                compflags[str(self.index)+'_'+computer] = 0 
                            time.sleep(0.01)
                            continue
            
                        else: 
                            #computer has been sent a frame
                            if (time.time() - self.currentFrames[computer][-1] 
                                > timeout): #timeout exceeded

                                frame = self.currentFrames[computer][0]
                                print('ERROR:Job:'+str(self.index)+'|Fra:'
                                    +str(frame)+'|'+computer+
                                    '|Timed out in render loop. Retrying')
                                RenderLog(self.index).error(computer, frame, 
                                3, '') #error code 3, no output line
                                with threadlock:
                                    #add computer to skiplist
                                    skiplists[self.index].append(computer) 
                                try:
                                    subprocess.call('ssh igp@'+computer+' "kill '
                                        +str(self.threads[computer])+'"', 
                                        shell=True)
                                #skip kill command if threads entry is blank 
                                #(ssh timeout)
                                except: 
                                    pass
                                with threadlock:
                                    #return frame to queue
                                    queue['q'+str(self.index)].put(frame) 
                                    #reset compflag to try again on next round
                                    compflags[str(self.index)+'_'+computer] = 0 
                                    #remove currentFrames entry
                                    del self.currentFrames[computer] 
                    time.sleep(0.01)
            
            #---FINISH LOOP---
            #Waits for remaining renders to finish, catches any errors
            while queue['q'+str(self.index)].empty():
                if killflags[self.index] == 1:
                    break
            
                #force update of currentFrames
                self.currentFrames = renderJobs[self.index][6] 
                #break loop if all frames have been returned 
                #RenderThread deletes currentFrames entry when frame is saved
                if not self.currentFrames: 
                    break
            
                #timeout function for remaining renders
                for computer in self.currentFrames: 
                    #terminate loop if frame is finished 
                    #(fixes re-entrant loop fuckery) 
                    if self.currentFrames[computer][0] in self.totalFrames: 
                        del self.currentFrames[computer]
                        break

                    if time.time() - self.currentFrames[computer][-1] > timeout:
                        frame = self.currentFrames[computer][0]
                        print('ERROR:Job:'+str(self.index)+'|Fra:'+str(frame)+
                            '|'+computer+'|Timed out in finish loop. Retrying')
                        #error code 3, no output line
                        RenderLog(self.index).error(computer, frame, 3, '') 
                        with threadlock:
                            skiplists[self.index].append(computer)
                        try:
                            subprocess.call('ssh igp@'+computer+' "kill '
                                +str(self.threads[computer])+'"', shell=True)

                        #skip kill command if threads entry is blank 
                        #(ssh timeout)
                        except: 
                            pass
            
                        with threadlock:
                            queue['q'+str(self.index)].put(self.currentFrames\
                            [computer][0])
                            compflags[str(self.index)+'_'+computer] = 0
                            del self.currentFrames[computer]
                        time.sleep(0.01)
                        #force restart of for loop b/c len(self.currentFrames) 
                        #changed during iteration
                        break 

                time.sleep(0.01)

            #catch any frames that were returned to queue in finish loop
            if not queue['q'+str(self.index)].empty(): 
                stragglers = threading.Thread(target=masterthread, args=())
                stragglers.start()

            #Render is done, clean up
            else: 
                print('Job:'+str(self.index)+'|Finished rendering.')
                RenderLog(self.index).render_finished()
                RenderTimer(self.index).stop()
                print('stopped render timer after finish loop') #debugging
                self.status = 'Finished'
                with threadlock:
                    renderJobs[self.index][8] = self.status

                #reset all compflags
                for computer in computers: 
                    with threadlock:
                        compflags[str(self.index)+'_'+computer] = 0 
                return


        master = threading.Thread(target=masterthread, args=())
        master.start()


    def add_computer(self, comp):
        '''add computer to the render pool'''
        self.comp = comp
        if self.comp in self.computerList: 
            Dialog('Computer is already in render pool.').warn()
            return

        with threadlock:
            renderJobs[self.index][4].append(self.comp)

        print('Job:'+str(self.index)+'|Added '+self.comp+' to the render pool.')



    def remove_computer(self, comp):
        '''remove computer from the render pool'''
        self.comp = comp
        if not self.comp in self.computerList:
            Dialog('Computer is not in current render pool.').warn()
            return

        with threadlock:
            renderJobs[self.index][4].remove(self.comp)

        print('Job:'+str(self.index)+'|Removed '+self.comp+
            ' from the render pool.')



    def kill(self):
        '''kills an in-progress render job'''

        if self.status != 'Rendering':
            Dialog('Job is not currently rendering.').warn()
            return

        if not Dialog('Stop the current render?').confirm():
            return

        with threadlock:
            killflags[self.index] = 1

        print('Job:'+str(self.index)+'|Render stopped by user.')

        for computer in computers: #prevent any new frames being sent
            with threadlock:
                compflags[str(self.index)+'_'+computer] = 1 

        if Dialog('Kill active processes? Clicking "Cancel" will stop the job but '
                    + 'allow currently rendering frames to finish.').confirm():
	        for computer in self.threads:
	            #sending twice b/c stuff is getting missed
	            subprocess.call('ssh igp@'+computer+' "kill '
	                +str(self.threads[computer])+'"', shell=True)
	            subprocess.call('ssh igp@'+computer+' "kill '
	                +str(self.threads[computer])+'"', shell=True) 
        else:
            #add currently rendering frames to totalFrames (assume they finish 
            #successfully)
            for computer in self.threads:
                print('Attempting to let current frames finish. Removing them '
                        + 'from resume list.')#debugging
                try:
                    frame = self.currentFrames[computer][0]
                    if not frame in self.totalFrames:
                        self.totalFrames.remove(0)
                        self.totalFrames.append(frame)
                except:
                    pass

        #flush the queue   
        while not queue['q'+str(self.index)].empty(): 
            with threadlock:
                queue['q'+str(self.index)].get()
            with threadlock:
                queue['q'+str(self.index)].task_done()
            time.sleep(0.001)

        #reset compflags
        for computer in computers: 
            with threadlock:
                compflags[str(self.index)+'_'+computer] = 0

        RenderLog(self.index).render_killed()
        RenderTimer(self.index).stop()
        print('stopped render timer in kill()') #debugging

        threadlock.acquire()
        self.status = 'Stopped'
        self.update()
        threadlock.release()



    def kill_thread(self, computer):
        '''kills an individual render thread'''

        if self.status != 'Rendering':
            return

        if not Dialog('Kill the render on this computer?').confirm():
            return

        if not computer in self.threads:
            Dialog('No render thread currently assigned to this computer.').warn()
            return

        try:
            frame = self.currentFrames[computer][0]
            with threadlock:
                #return frame to queue
                queue['q'+str(self.index)].put(frame) 
        except:
            print('No thread found to kill.')
            return

        subprocess.call('ssh igp@'+computer+' "kill '
            +str(self.threads[computer])+'"', shell=True)
        subprocess.call('ssh igp@'+computer+' "kill '
            +str(self.threads[computer])+'"', shell=True)

        print('Job:'+str(self.index)+'|Killed process on '+computer+
            '|Returning frame '+str(frame)+' to queue.')
        RenderLog(self.index).thread_killed(computer, frame)

        with threadlock:
            compflags[str(self.index)+'_'+computer] = 0
            


    def resume(self):
        '''resumes a stopped render job'''

        if self.status != 'Stopped':
            Dialog('Render must be stopped before it can be resumed.').warn()
            return

        #self.status = 'Rendering' #only do this in render() to simplify things 
        with threadlock:
            #reset killflag
            killflags[self.index] = 0 

        resumeFrames = []
        #using currentFrames because self.computerlist can change between 
        #stop and resume 
        for computer in self.currentFrames: 
            #if frame was assigned before render stopped
            if self.currentFrames[computer][0]: 
                #[0] is frame, [1] is timer
                resumeFrames.append(self.currentFrames[computer][0]) 

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
            #destroy queue object
            queue['q'+str(self.index)] = None 

        #RenderTimer(self.index).clear()

        print('Job:'+str(self.index)+'|Render resumed by user.')
        RenderLog(self.index).render_resumed()
        
        if Dialog('Start render immediately? Click "Cancel" to queue for '
                    + 'later.').confirm():
            self.status = 'Waiting'
            self.update()
            self.render()
            return
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

        global renderJobs
        self.render_engine = renderJobs[self.index][12]


    def create(self): 
        '''creates a thread for a single frame on a specified computer'''

        if self.render_engine == 'blender':
            t = threading.Thread(target=self.send_command, args=())
            t.start()
        elif self.render_engine == 'terragen':
            t = threading.Thread(target=self.send_command_terragen, args=())
            t.start()


    def send_command(self): 
        '''sends the render command for blender via ssh'''

        global skiplists

        with threadlock: 
            #start timeout timer
            renderJobs[self.index][6][self.computer] = [self.frame, time.time()] 

        print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+
                '|Sent') #need to add timestamp
        RenderLog(self.index).frame_sent(self.computer, self.frame)

        if self.computer in macs:
            renderpath = blenderpath_mac 
        else:
            renderpath = blenderpath_linux 

        command = subprocess.Popen('ssh igp@'+self.computer+' "'+renderpath+
            ' -b '+self.path+' -f '+str(self.frame)+' & pgrep -n blender"', 
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        self.output = ''
        for line in iter(command.stdout.readline, ''):
            if line:
                with threadlock:
                    #reset timer every time an update is received
                    renderJobs[self.index][6][self.computer] = [self.frame, 
                        time.time()] 

            if line.find('Fra:') >= 0:
                self.parseline(line, self.frame, self.computer, self.index)

            #detect PID at first line
            elif line.strip().isdigit(): 
                pid = int(line)
                with threadlock:
                    renderJobs[self.index][5][self.computer] = pid
                #renice process to lowest priority on specified comps 
                if self.computer in renice_list: 
                    subprocess.call('ssh igp@'+self.computer+' "renice 20 -p '
                        +str(pid)+'"', shell=True)
                    #for debugging
                    print('reniced PID '+str(pid)+' to pri 20 on '+self.computer) 
                if skiplists[self.index]:
                    with threadlock:
                        #remove oldest entry from skip list
                        skiplists[self.index].pop(0) 
                        #debugging
                        print('frame sent. Removing oldest item from skiplist') 

    
            elif line.find('Saved:') >= 0 and line.find('Time') >= 0:
                #grabs final render time string from blender's output
                #checks for 'Time' b/c if there are multiple files saved per
                #frame, there may not be a timestamp.
                rendertime = line[line.find('Time'):].split(' ')[1] 
                print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                    +self.computer+'|Received after '+rendertime) 
                RenderLog(self.index).frame_received(self.computer, self.frame, 
                    rendertime)
                with threadlock:
                    compflags[str(self.index)+'_'+self.computer] = 0
                with threadlock:
                    #check if there are placeholders left in total frames
                    if 0 in renderJobs[self.index][7]: 
                        #remove a placeholder
                        renderJobs[self.index][7].remove(0) 
                    renderJobs[self.index][7].append(self.frame)
                    try:
                        #delete currentFrames entry
                        del renderJobs[self.index][6][self.computer] 
                    except:
                        print('failed to delete currentFrames entry for ', 
                            self.computer) #debugging
                        pass

                with threadlock:
                    queue['q'+str(self.index)].task_done() 
            else:
                self.output = self.output + line

            if verbose: #verbose terminal output
                if line:
                    print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                        +self.computer+'|STDOUT: '+line)

        for line in iter(command.stderr.readline, ''):
            #assume any text in STDERR means connection/render failure
            if line: 
                with threadlock:
                    queue['q'+str(self.index)].put(self.frame)
                with threadlock:
                    #reset compflag to try again on next round
                    compflags[str(self.index)+'_'+self.computer] = 0 
                with threadlock:
                    skiplists[self.index].append(self.computer)
                    #debugging
                    print('Text in stderr. Adding '+self.computer+' to skiplist')

                print('ERROR:Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                    +self.computer+'|STDERR: '+line) 
                RenderLog(self.index).error(self.computer, self.frame, 3, line) 

        if self.check_warn(self.output):
            with threadlock:
                #reset compflag to try again on next round
                compflags[str(self.index)+'_'+self.computer] = 0 
            #try adding this to skiplist to avoid issue of multiple 
            #blender processes
            with threadlock:
                #debugging
                print('problem with check_warn(), adding computer to skiplist') 
                skiplists[self.index].append(self.computer)
            with threadlock:
                queue['q'+str(self.index)].put(self.frame)

            print('ERROR|Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                +self.computer+'|Blender returned a warning. Offending line: '
                +self.output)
            RenderLog(self.index).error(self.computer, self.frame, 2, line) 



    def send_command_terragen(self): 
        '''sends the render command for terragen via ssh'''

        global skiplists

        with threadlock: 
            #start timeout timer
            renderJobs[self.index][6][self.computer] = [self.frame, time.time()] 

        print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'+self.computer+
            '|Sent') 
        RenderLog(self.index).frame_sent(self.computer, self.frame)

        if self.computer in macs:
            renderpath = terragenpath_mac
        else:
            renderpath = terragenpath_linux
        #NOTE: From terragen mac command line documentation: If Terragen is not 
        #in the current working directory, it will probably make lots of 
        #complaints when it starts. It's not enough just to pass the full path 
        #of the Terragen 3 command when you run it. Terragen needs to know where 
        #it can find other related files.
        #can edit the TERRAGEN_PATH env var or cd to terragen directory before 
        #running

        command = subprocess.Popen('ssh igp@'+self.computer+' "'+renderpath+' -p '
            +self.path+' -hide -exit -r -f '+str(self.frame)+
            ' & pgrep -n Terragen&wait"', stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, shell=True)
        print('sending command with renderpath '+renderpath) #debugging

        self.output = ''
        for line in iter(command.stdout.readline, ''):
            if line:
            #NOTE: timeout will be a problem.  Need to find workaround for 
            #terragen. Maybe make timeout an instance var instead of global
                with threadlock:
                    #reset timer every time an update is received
                    renderJobs[self.index][6][self.computer] = [self.frame, 
                        time.time()] 

            #Terragen provides much less continuous status info, so parseline 
            #replaced with a few specific conditionals

            #starting overall render or one of the render passes
            if line.find('Starting') >= 0:
                ellipsis = line.find('...')
                passname = line[9:ellipsis]
                print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                    +self.computer+'|Starting '+passname)

            elif line.find('Rendered') >= 0:
                #finished one of the render passes
                mark = line.find('of ')
                passname = line[mark+3:]
                print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                    +self.computer+'|Finished '+passname)

            elif line.find('Rendering') >= 0:
                #pattern 'Rendering pre pass... 0:00:30s, 2% of pre pass'
                #NOTE: terragen ALWAYS has at least 2 passes, so prog bars to 
                #to 100% twice.  Need to note this somewhere or workaround.
                #could scale percentages so that prepass accounts for no more 
                #than 50% of progress bar

                #get name of pass:
                ellipsis = line.find('...')
                passname = line[10:ellipsis]

                #get percent complete for pass
                for i in line.split():
                    if '%' in i:
                        pct_str = i
                        percent = float(pct_str[:-1])
                        break

                print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                +self.computer+'|Rendering '+passname+', '+pct_str+' complete.')
                #pass info to progress bars (equiv of parseline())
                self.termout = [self.computer, self.frame, percent] 
                with threadlock:
                    renderJobs[self.index][10] = self.termout

            #detect PID at first line
            elif line.strip().isdigit(): 
                pid = int(line)
                print('possible PID detected: '+str(pid)) #debugging
                if pid != self.frame: 
                    #necessary b/c terragen echoes frame # at start. 
                    #Hopefully PID will never be same as frame #
                    print('PID set to: '+str(pid)) #debugging
                    with threadlock:
                        renderJobs[self.index][5][self.computer] = pid
                        #renice process to lowest priority on specified comps 
                    if self.computer in renice_list: 
                        subprocess.call('ssh igp@'+self.computer+
                            ' "renice 20 -p '+str(pid)+'"', shell=True)
                        print('reniced PID '+str(pid)+' to pri 20 on '
                            +self.computer) #for debugging
                    if skiplists[self.index]:
                        with threadlock:
                            #remove oldest entry from skip list
                            skiplists[self.index].pop(0) 
                            print('frame sent. Removing oldest item from '
                                'skiplist') #debugging

            elif line.find('Finished') >= 0:
                print('Finished line: '+line) #debugging
                rendertime = line.split()[2][:-1]

                print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                    +self.computer+'|Finished frame after '+rendertime) 
                RenderLog(self.index).frame_received(self.computer, self.frame, 
                    rendertime)
                with threadlock:
                    compflags[str(self.index)+'_'+self.computer] = 0
                with threadlock:
                    #check if there are placeholders left in total frames
                    if 0 in renderJobs[self.index][7]: 
                        #remove a placeholder
                        renderJobs[self.index][7].remove(0) 
                    renderJobs[self.index][7].append(self.frame)
                    try:
                        #delete currentFrames entry
                        del renderJobs[self.index][6][self.computer] 
                    except:
                        print('failed to delete currentFrames entry for ', 
                            self.computer) #debugging
                        pass
                with threadlock:
                    queue['q'+str(self.index)].task_done() 
            else:
                self.output = self.output + line

            #if verbose, pass all STDOUT from thread to STDOUT for script
            if verbose: 
                if line:
                    print('Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                        +self.computer+'|STDOUT: '+line)


        for line in iter(command.stderr.readline, ''):
            #terragen throwing window server error but still saving file?
            if line.find('WindowServer') >= 0: 
                print('Got terragen window server error in STDERR on '
                    +self.computer+', frame '+str(self.frame)+', ignoring')
                pass

            #terragen has weird `' does not exist in file system error
            elif line.find('ERROR 4') >= 0: 
                print('Got terragen ERROR 4 in STDERR on '+self.computer+
                    ', frame '+str(self.frame)+', ignoring.')
                pass

            #assume any text in STDERR (other than above) means 
            #connection/render failure
            elif line: 
                print('Text in stderr, ignoring because this error checking '
                    'function is temporarily disabled', line) #debugging
                pass

                #ignore following blocks
                #with threadlock:
                #    queue['q'+str(self.index)].put(self.frame)
                #with threadlock:
                #    #reset compflag to try again on next round
                #    compflags[str(self.index)+'_'+self.computer] = 0 
                #with threadlock:
                #    skiplists[self.index].append(self.computer)
                #debugging
                #print('Text in stderr.'+self.computer+' STDERR:'+line ) 

                #print('ERROR:Job:'+str(self.index)+'|Fra:'+str(self.frame)+'|'
                #   +self.computer+'|STDERR: '+line) 
                #RenderLog(self.index).error(self.computer, self.frame, 3, line)






    def parseline(self, line, frame, computer, index): 
        '''parses render proress and renders it in compact form'''

        self.line = line
        if self.line.find('Tile') >= 0:
            tiles, total = self.line.split('|')[-1].split(' ')[-1].split('/')
            tiles = int(tiles)
            total = int(total)
            percent = float(tiles) / total * 100
            #doing it this way to try to fix frame -1 issue
            self.termout = [self.computer, self.frame, percent] 
            with threadlock:
                renderJobs[self.index][10] = self.termout


    def check_warn(self, output):
        '''returns true if blender throws a warning'''

        if self.output.find('Warning:') >= 0:
            print('WARNING was found') #debugging
            print self.output #debugging
            return True 
            
        #hack to fix issue with blender completing renders but returning error 
        #for "not freed memory blocks"
        elif self.output.find('Error: Not freed'):
            print('had not freed memory error, returning false in check_warn()')#debugging
            return False

        elif self.output.find('Error:') >= 0:
            print('ERROR was found') #debugging
            print self.output #debugging
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

        #starting a totally new render
        if ttime[self.index][0] == 0: 
            with threadlock:
                ttime[self.index][0] = time.time()

        #resuming a stopped render, leave timer unaffected.
        else: 
            #time rendering before stopped
            prev_elapsed_time = ttime[self.index][1] - ttime[self.index][0] 
            with threadlock:
                ttime[self.index][0] = time.time() - prev_elapsed_time
            print('resuming with prev_elapsed:', prev_elapsed_time) #debugging


    def stop(self):
        '''stops a render timer **but does not reset it to zero**'''

        with threadlock:
            ttime[self.index][1] = time.time()


    def get(self): 
        '''returns total elapsed time for a render'''

        if self.status != 'Rendering':
            rendertime = ttime[self.index][1] - ttime[self.index][0]
        else:
            #with threadlock:
            #    ttime[self.index][1] = time.time()
            #rendertime = ttime[self.index][1] - ttime[self.index][0]
            rendertime = time.time() - ttime[self.index][0]

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
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m '
                +str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h '
                +str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr




class RenderLog(Job):
    '''class to handle logging functions for a rendering job'''

    hrule = '='*80 #for printing a thick horizontal line in the log
    delim = ', ' #delimiter to join computer lists into more readable format


    def __init__(self, index):
        Job.__init__(self, index)
        self.timestart = renderJobs[self.index][11]
        #set the start time only when the class is called for the first time
        if not self.timestart: 
            self.timestart = subprocess.check_output('date +%Y-%m-%d_%H%M', 
                shell=True).strip()
            with threadlock:
                renderJobs[self.index][11] = self.timestart
        self.filename = self.path.split('/')[-1]
        self.log_path = ('/mnt/data/renderlogs/'+self.filename.split('.')[0]+
            '.'+str(self.timestart)+'.txt')


    def render_started(self):

        if len(self.extraframes) > 0: 
            subprocess.call('date "+'+RenderLog.hrule+'\nRender started at '
                '%H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '
                +str(self.startframe)+' - '+str(self.endframe)+' plus '
                +str(self.extraframes)+'\nOn: '
                +RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule
                +'\n" > '+self.log_path, shell=True)
        else:
            subprocess.call('date "+'+RenderLog.hrule+'\nRender started at '
                '%H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '
                +str(self.startframe)+' - '+str(self.endframe)+'\nOn: '
                +RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule
                +'\n" > '+self.log_path, shell=True)


    def frame_sent(self, computer, frame):
        self.computer = computer
        self.frame = frame
        subprocess.call('date "+Sent frame '+str(self.frame)+' of '
            +str(len(self.totalFrames))+' to '+self.computer+' at %H:%M:%S on '
            '%m-%d-%Y" >> '+self.log_path, shell=True)

    def frame_received(self, computer, frame, rendertime):
        self.computer = computer
        self.frame = frame
        self.rendertime = rendertime
        subprocess.call('date "+Received frame '+str(self.frame)+' of '
            +str(len(self.totalFrames))+' from '+self.computer+' at %H:%M:%S '
            'on %m-%d-%Y after '+self.rendertime+'" >> '+self.log_path, 
            shell=True)

    def error(self, computer, frame, code, line):
        self.computer = computer
        self.frame = frame
        self.code = code
        self.line = line

        if self.code == 1: #text in stderr
            self.err = 'Text in STDERR: '+str(self.line) 

        if self.code == 2: #failed check_warn()
            self.err = ('Blender returned a warning. Offending line: '
                +str(self.line))

        if self.code == 3: #computer timed out
            self.err = 'Computer timed out.'

        subprocess.call('date "+ERROR: frame'+str(self.frame)+' failed to '
            'render on '+self.computer+' at %H:%M:%S on %m-%d-%Y. Reason: '
            +self.err+'" >> '+self.log_path, shell=True)


    def complist_changed(self):
        #force an update
        self.computerList = renderJobs[self.index][4] 
        subprocess.call('date "+Computer list changed at %H:%M:%S on %m-%d-%Y. '
            'Now rendering on: '+RenderLog.delim.join(self.computerList)+
            '." >> '+self.log_path, shell=True)


    def render_finished(self):
        tt = RenderTimer(self.index).get()
        totaltime = RenderTimer(self.index).convert(tt)
        subprocess.call('date "+'+RenderLog.hrule+'\nRender finished at '
            '%H:%M:%S on %m-%d-%Y\nTotal render time was '+totaltime+'.\n'
            +RenderLog.hrule+'" >> '+self.log_path, shell=True)


    def render_killed(self):
        subprocess.call('date "+'+RenderLog.hrule+'\nRender stopped by user at '
            '%H:%M:%S on %m-%d-%Y. Current frames: '+str(self.currentFrames)+
            '. Most recent PIDs: '+str(self.threads)+'." >> '+self.log_path, 
            shell=True)

    def render_resumed(self):
        if len(self.extraframes) > 0: 
            subprocess.call('date "+'+RenderLog.hrule+'\nRender resumed by user '
                'at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '
                +str(self.startframe)+' - '+str(self.endframe)+' plus '
                +str(self.extraframes)+'\nOn: '
                +RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule
                +'\n" >> '+self.log_path, shell=True)
        else:
            subprocess.call('date "+'+RenderLog.hrule+'\nRender resumed by user '
                'at %H:%M:%S on %m-%d-%Y\nFile: '+self.path+'\nFrames: '
                +str(self.startframe)+' - '+str(self.endframe)+'\nOn: '
                +RenderLog.delim.join(self.computerList)+'\n'+RenderLog.hrule
                +'\n" >> '+self.log_path, shell=True)

    def thread_killed(self, computer, frame):
        self.computer = computer
        self.frame = frame
        subprocess.call('date "+User killed render thread on '+self.computer+
            ' at %H:%M:%S on %m-%d-%Y. Returning frame '+str(self.frame)+
            ' to queue." >> '+self.log_path, shell=True)




class Status(Job):
    '''class representing the status of a queued or rendering job'''

    def __init__(self, index):
        Job.__init__(self, index)
        self.filename = self.path.split('/')[-1]



    def get_status(self):
        return self.status


    def globalJobstat(self):
        '''populates global job status box'''

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'
            +str(self.index)).delete('all')

        if self.status == 'Empty':
            color = 'gray70'
            jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'
                +str(self.index)).create_rectangle(0, 0, 120, 20, fill=color)
            jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'
                +str(self.index)).create_text(60, 10, text='Job '
                +str(self.index)+' '+self.status)
            return


        finished_frames = 0 #number of frames finished
        for i in self.totalFrames:
            if i != 0:
                finished_frames += 1

        if len(self.totalFrames) != 0:
            percent_complete = int(finished_frames / 
                float(len(self.totalFrames)) * 100)
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
        #truncate long list of extraframes
        else: 
            self.extraframes.sort()
            if len(self.extraframes) <= 2:
                extraset = []
                for frame in self.extraframes:
                    extraset.append(str(frame))
                extras = RenderLog.delim.join(extraset)

            else:
                extras = (str(self.extraframes[0])+', '+str(self.extraframes[1])
                    +'...')

        if len(self.filename) > 17: #truncate long filenames
            self.filename = self.filename[0:16]+'...'

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'
            +str(self.index)).create_rectangle(0, 0, 120, 20, fill=color)
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.statlight_'
            +str(self.index)).create_text(60, 10, text='Job '+str(self.index)
            +' '+self.status)

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.filenam_'
            +str(self.index)).config(text=self.filename)
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.startfram_'
            +str(self.index)).config(text='Start: '+str(self.startframe))
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.endfram_'
            +str(self.index)).config(text='End: '+str(self.endframe))
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.extrafram_'
            +str(self.index)).config(text='Extras: '+str(extras))

        tt = RenderTimer(self.index).get()
        at = RenderTimer(self.index).avgFrameTime()
        tl = RenderTimer(self.index).estTimeRemaining()

        totaltime = RenderTimer(self.index).convert(tt)
        avgtime = RenderTimer(self.index).convert(at)
        timeleft = RenderTimer(self.index).convert(tl)

        #Change font size if too many characters for fields
        if len(totaltime) > 14 or len(avgtime) > 14 or len(timeleft) > 14: 
            timefont = smallfont
            charwidth = 7 #approx character width for smallfont 
        else:
            timefont = 'TkDefaultFont' 
            charwidth = 9 #approx character width for defaultfont

        ttx = 35 + 29 + int(charwidth * len(totaltime) / 2)
        atx = 240 + 42 + int(charwidth * len(avgtime) / 2)
        tlx = 448 + 48 + int(charwidth * len(timeleft) / 2)

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).delete('all')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(35, 10, text='Total time:')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(ttx, 10, text=str(totaltime), 
            font=timefont)
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(250, 10, text='Avg/frame:')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(atx, 10, text=str(avgtime), 
            font=timefont)
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(466, 10, text='Remaining:')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(tlx, 10, text=str(timeleft), 
            font=timefont)

        Status(self.index).drawTotalBar()
        


    def purgeGlobalJobstat(self):
        '''resets all text fields in global queue status for a given index'''
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.filenam_'
            +str(self.index)).config(text='')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.startfram_'
            +str(self.index)).config(text='')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.endfram_'
            +str(self.index)).config(text='')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.extrafram_'
            +str(self.index)).config(text='')

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).delete('all')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(35, 10, text='Total time:')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(250, 10, text='Avg/frame:')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.timecanv_'
            +str(self.index)).create_text(466, 10, text='Remaining:')

        Status(self.index).clearTotalBar()



    def drawBar(self):
        '''updates individual computer progress bars, current frames, 
            and % completed'''

        if not self.termout:
            return

        self.computer = self.termout[0]
        self.frame = self.termout[1]
        self.percent = int(self.termout[-1])

        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').delete('all')
        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').create_text(5, 10, anchor=W, text=self.computer)
        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').create_text(130, 10, anchor=W, text='Frame:')
        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').create_text(180, 10, anchor=W, text=self.frame) 
        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').create_text(279, 10, anchor=E, text=self.percent)
        statframe.nametowidget(self.computer+'_statbox.'+self.computer
            +'_compdata').create_text(280, 10, anchor=W, text='% Complete')

        progvars[self.computer].set(self.percent)



    def fillAllBars(self):
        '''sets computer progress bar to 100%'''
        for computer in computers:
            #if computer recently rendered a frame
            if computer in self.threads: 
                self.termout = [computer, '', 100]
                #self.termout[0] = computer
                #self.termout[-1] = 100
                self.drawBar()
            else:
                statframe.nametowidget(computer+'_statbox.'+computer+
                    '_compdata').delete('all')
                statframe.nametowidget(computer+'_statbox.'+computer+
                    '_compdata').create_text(5, 10, anchor=W, text=computer)
                statframe.nametowidget(computer+'_statbox.'+computer+
                    '_compdata').create_text(130, 10, anchor=W, text='Frame:')
                statframe.nametowidget(computer+'_statbox.'+computer+
                    '_compdata').create_text(280, 10, anchor=W, 
                    text='% Complete')
                progvars[computer].set(0)



    def clearAllBoxes(self):
        '''clears computer progress bars and statboxes'''
        for computer in computers:
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_compdata').delete('all')
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_compdata').create_text(5, 10, anchor=W, text=computer)
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_compdata').create_text(130, 10, anchor=W, text='Frame:')
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_compdata').create_text(280, 10, anchor=W, text='% Complete')
            progvars[computer].set(0)



    def drawTotalBar(self):
        '''draws & updates total render progress bar'''

        finished_frames = 0
        for i in self.totalFrames:
            if i != 0:
                finished_frames += 1

        if len(self.totalFrames) != 0:
            percent_complete = (finished_frames / 
                float(len(self.totalFrames)) * 100)
        else:
            percent_complete = 0

        totalprog[self.index].set(int(percent_complete))

        pct = PaddedNumber(int(percent_complete)).percent()
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'
            +str(self.index)).delete('all')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'
            +str(self.index)).create_text(55, 9, text=pct+'% Complete')



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

        #truncate long filenames
        if len(self.filename) > 30: 
            self.filename = self.filename[0:30]+'...'

        joblabel.delete('all')
        joblight.delete('all')
        filelabel.delete('all')

        joblabel.create_rectangle(0, 0, 80, 30, fill=color, outline='gray70')
        joblabel.create_text(40, 15, text='Job '+str(self.index), 
            font='TkCaptionFont')

        joblight.create_rectangle(-1, 0, 120, 30, fill=color, outline='gray70')
        joblight.create_text(60, 15, text=self.status, font='TkCaptionFont')

        filelabel.create_rectangle(0, 0, 260, 30, fill='gray90', 
            outline='gray70')
        filelabel.create_text(130, 15, text=self.filename, font='TkCaptionFont')

        self.drawToggleButtons() 



    def drawToggleButtons(self):
        '''creates and updates computer toggle buttons in statboxes'''

        incolor = 'SpringGreen' #color for computers that are in render pool
        outcolor = 'Khaki' #color for computers that are not in render pool

        for computer in computers:
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').delete('all')
            statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').create_text(20, 10, text='Pool', font=smallfont)
            if computer in self.computerList:
                statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').create_rectangle(2, 20, 37, 37, fill=incolor, 
                outline='gray50')
                statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').create_text(20, 29, text='In', font=smallfont)
            else:
                statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').create_rectangle(2, 20, 37, 37, fill=outcolor, 
                outline='gray50')
                statframe.nametowidget(computer+'_statbox.'+computer+
                '_togglebtn').create_text(20, 29, text='Out', font=smallfont)




    def clearTotalBar(self): 
        '''clears contents of total progress bar'''

        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'
            +str(self.index)).delete('all')
        jobstatFrame.nametowidget('jobstat_'+str(self.index)+'.perdone_'
            +str(self.index)).create_text(55, 9, text='0% Complete')
        with threadlock:
            totalprog[self.index].set(0)





class PaddedNumber(object): 
    '''padded number strings for display in the GUI'''

    def __init__(self, number):
        self.number = number #must be an integer

    def percent(self): 
        '''Pad integer percent with blank space to fill three char widths.
           Use monospace fonts for proper effect'''

        percent_padded = str(self.number)
        if len(percent_padded) == 1:
            percent_padded = '  '+percent_padded
        elif len(percent_padded) == 2:
            percent_padded = ' '+percent_padded
        return percent_padded




class Dialog(object):
    '''dialog boxes that display message passed as param'''

    def __init__(self, msg):
        self.msg = msg #message to be displayed

    def warn(self):
        '''creates warning popup with only OK button'''

        tkMessageBox.showwarning('Achtung!', self.msg)

    def confirm(self):
        '''creates popup with OK and Cancel buttons, returns true if user 
           clicks OK'''
        
        if tkMessageBox.askokcancel('Achtung!', self.msg, icon='warning'):
            return True
        else:
            return False



class SystemStatus(object):
    '''Methods for checking various system status indicators'''

    def __init__(self, computer):
        self.computer = computer
        if self.computer in macs:
            arg = '-l'
        else:
            arg = '-bn'
        try:
            self.top = subprocess.check_output(['ssh', 'igp@'+self.computer, 
                'top', arg, '1'])
        except:
            self.top = 'error'


    def get_cpu(self):
        '''returns % CPU utilization'''
        if self.top == 'error':
            return 0

        if self.computer in macs:
            for line in self.top.split('\n'):
                if 'CPU usage' in line:
                    cpu_line = line
            cpu_free = float(cpu_line.split()[-2][:-1])
            cpu_used = 100 - cpu_free
        else:
            for line in self.top.split('\n'):
                if 'Cpu(s)' in line:
                    cpu_line = line
            cpu_free = float(cpu_line.split()[4][:-4])
            cpu_used = 100 - float(cpu_free)

        return cpu_used


    def get_memory(self):
        '''returns ram utilization in GB'''
        if self.top == 'error':
            return 0

        if self.computer in macs:
            for line in self.top.split('\n'):
                if 'PhysMem' in line:
                    mem_line = line

            #must use free mem b/c of issue w/ top reporting incorrect ram use
            #in mavericks
            mem_free = float(mem_line.split()[-2][:-1]) 

            #make adjustments if units are not GB
            suffix = mem_line.split()[-2][-1]
            if suffix == 'K':
                mem_free = mem_free / 1e6
            elif suffix == 'M':
                mem_free = mem_free / 1e3

            for computer in maxram:
                if self.computer == computer:
                    mem_used = maxram[computer] - mem_free

        else:
            for line in self.top.split('\n'):
                if 'Mem:' in line:
                    mem_line = line

            #mem_used = float(mem_line[-4][:-1]) / 1e6 #check that these units
            #are right
            mem_str = mem_line.split()[3]
            print mem_str #debugging
            mem_used = ''
            for char in mem_str:
                if char.isdigit():
                    mem_used += char
            mem_used = float(mem_used) / 1e6

        return mem_used

            




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
    '''version of tkinter Button that takes an index argument and passes it to a 
       function different from the button's command function'''

    def __init__(self, master, index, **kw):
        apply(Button.__init__, (self, master), kw)
        self.index = index
        self.bind('<Button-1>', lambda x: set_job(self.index))


class AdRemButton(Button):
    '''version of tkinter button that takes a computer argument and passes it to
       another function'''

    def __init__(self, master, computer, val, **kw):
        apply(Button.__init__, (self, master), kw)
        self.computer = computer
        self.val = val #int 0 for add, 1 for remove
        self.bind('<Button-1>', lambda x: add_remove_computer(self.computer, 
            self.val))


class ToggleCanv(Canvas):
    '''version of tkinter canvas that acts as computerList toggle button'''

    def __init__(self, master, computer, **kw):
        apply(Canvas.__init__, (self, master), kw)
        self.bind('<Button-1>', lambda x: add_remove_computer(computer))


class KillCanv(Canvas):
    '''version of tkinter canvas that acts as a per-computer process kill 
       button'''

    def __init__(self, master, computer, **kw):
        apply(Canvas.__init__, (self, master), kw)
        #need a kill process function
        self.bind('<Button-1>', lambda x: Job(jobNumber.get()).kill_thread(computer)) 





#------Global Functions------


def browse(): 
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
        Dialog('Queue slot is already empty.').warn()
        return

    if Status(index).get_status() == 'Rendering': 
        Dialog('Cannot remove a job while rendering. Stop render first.').warn()
        return

    if not Dialog('Delete this queue item?').confirm():
        return

    Job(index).clear()



def add_remove_computer(computer):
    index = jobNumber.get()
    #can't change computer list if there's no job in queue
    if Job(index).checkSlotFree(): 
        return

    computerList = renderJobs[index][4]
    if not computer in computerList:
        Job(index).add_computer(computer)
    else:
        if len(computerList) <= 1:
            if not Dialog('Are you sure you want to remove the last computer '
                            + 'from the pool?').confirm():
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
        #change inactive boxes to offcolor
        if i != index: 
            jobstatFrame.nametowidget('jobstat_'+str(i)).config(bg=offcolor, 
                relief=GROOVE, bd=1)

            for widget in otherwidgets:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+widget+
                    str(i)).config(bg=offcolor, highlightbackground=offcolor)
            
            for label in jobstat_label_list:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.'+label+
                    str(i)).config(bg=offcolor, fg=offtext)

            for button in buttons:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.buttonframe_'+
                    str(i)+'.'+button+str(i)).config(bg=offcolor, 
                    highlightbackground=offcolor)

        #change active boxes to oncolor
        else: 
            jobstatFrame.nametowidget('jobstat_'+str(i)).config(bg=oncolor, 
                relief=FLAT, bd=0)

            for widget in otherwidgets:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.'
                    +widget+str(i)).config(bg=oncolor, 
                    highlightbackground=oncolor)
            
            for label in jobstat_label_list:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.'
                    +label+str(i)).config(bg=oncolor, fg=ontext)

            for button in buttons:
                jobstatFrame.nametowidget('jobstat_'+str(i)+'.buttonframe_'+
                    str(i)+'.'+button+str(i)).config(bg=oncolor, 
                    highlightbackground=oncolor)

    updateFields()




def updateFields(): 
    '''updates & redraws detailed status info when job is switched'''
    index = jobNumber.get()
    Status(index).clearAllBoxes()


def parseOutput(): 
    '''called by update(), reads renderJobs & updates UI status indicators'''
    index = jobNumber.get()
    termout = renderJobs[index][10]
    status = renderJobs[index][8]
    Status(index).drawJoblight()

    for i in renderJobs: 
        '''update global statuses for ALL slots'''
        Status(i).globalJobstat()

    if not Job(index).checkSlotFree(): 
        '''update detailed info only for CURRENT slot'''
        if type(termout) == list and len(termout) == 3: 
            Status(index).drawBar()
        if status == 'Finished':
            Status(index).fillAllBars()


def update(): 
    '''refreshes GUI'''
    parseOutput()
    root.update_idletasks()
    canvas.config(height=(root.winfo_height()-105))
    root.after(80, update)


def toggle_verbosity(): 
    '''#toggles python verbose variable based on tkinter verbosity checkbox'''
    global verbose
    verbose = verbosity.get()
    if verbose == 1:
        print('Verbose on')
    else:
        print('Verbose off')


def start_next_job(): 
    '''starts the next job in queue''' 
    global renderJobs
    global maxglobalrenders

    renders = 0
    for index in renderJobs:
        #terminate if a render is in progress
        if renderJobs[index][8] == 'Rendering': 
            renders += 1

    if renders >= maxglobalrenders:
        return

    for index in renderJobs:
        #check for waiting jobs
        if renderJobs[index][8] == 'Finished': 
            for i in renderJobs:
                if renderJobs[i][8] == 'Waiting':
                    Job(i).render()
                    #delay between starting simultaneous renders
                    time.sleep(0.25) 
                    return


def check_job_queue(): 
    '''checks if any jobs are waiting and calls start_next_job() if yes'''
    global startnext

    if startnext == 1:
        start_next_job()

    root.after(5000, check_job_queue)



def set_startnext():
    '''updates global startnext variable'''
    global startnext
    startnext = stnext.get()
    if startnext == 1:
        print('Autostart on')
    else:
        print('Autostart off')



def quit(): 
    '''forces immediate exit without waiting for loops to terminate'''
    _exit(1) 


#leaving export_json() alone b/c Ludvig is working on it
def export_json(): #exports a formatted JSON file with current status for website
    global renderJobs

    #need job no., status, filepath, start, end, extras, complist, progress, computer+frame+status
    export_data = dict()
    for index in renderJobs:
        export_data['job'+str(index)+'status'] = renderJobs[index][8]
        export_data['job'+str(index)+'filepath'] = renderJobs[index][0]
        export_data['job'+str(index)+'startframe'] = renderJobs[index][1]
        export_data['job'+str(index)+'endframe'] = renderJobs[index][2]
        export_data['job'+str(index)+'extraframes'] = renderJobs[index][3]
        export_data['job'+str(index)+'complist'] = renderJobs[index][4]

        #calculate percent complete
        totalFrames = renderJobs[index][7]
        finished_frames = 0
        for i in renderJobs:
            if i != 0:
                finished_frames += 1

        if len(totalFrames) != 0:
            percent_complete = int(finished_frames / float(len(totalFrames)) * 100)
        else:
            percent_complete = 0

        export_data['job'+str(index)+'job_progress'] = percent_complete

        #create list of computer statuses
        #not currently working
        termout = renderJobs[index][10]
        compstatus = []
        for comp in termout:
            #[computer, frame, percent]
            export_data['job'+str(index)+'computer_status'] = compstatus.append([comp, termout[1], 
                termout[-1]]) 

    data_out = open('render_status.json', 'w')
    data_out.write(json.dumps(export_data, indent=1))
    data_out.close()
    print('JSON file exported') #debugging
        



#----------CONFIG FILE----------
def set_defaults():
    '''Restores all config settings to default values.'''

    #create list of all computers available for rendering
    computers = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache', 
        'conundrum', 'paradox'] 
    
    #list of computers in the 'fast' group
    fast = ['bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente'] 
    #list of computers in the 'farm' group
    farm = ['lindsey', 'wetterhorn', 'lincoln', 'humberto', 'tabeguache'] 
    
    #list of computer to renice processes to lowest priority. 
    #Can be changed from prefs window.
    renice_list = ['conundrum', 'paradox', 'sherman'] 
    
    #computers running OSX. Needed because blender uses different path
    macs = ['conundrum', 'paradox', 'sherman'] 
    
    #path to blender executable on OSX computers
    blenderpath_mac = '/Applications/blender.app/Contents/MacOS/blender' 
    
    #path to blender executable on Linux computers
    blenderpath_linux = '/usr/local/bin/blender' 
    
    terragenpath_mac = '/mnt/data/software/terragen_rendernode/osx/terragen3.app/Contents/MacOS/Terragen_3'
    
    terragenpath_linux = '/mnt/data/software/terragen_rendernode/linux/terragen'
    
    #allowed file extensions (last 3 chars only) for check_missing_files
    allowed_filetypes = ['png', 'jpg', 'peg', 'gif', 'tif', 'iff', 'exr', 'PNG', 
        'JPG', 'PEG', 'GIF', 'TIF', 'IFF', 'EXR'] 
    
    #timeout for failed machine in seconds
    timeout = 1000 
    
    #start next job when current one finishes. 1=yes, 0=no, on by default
    startnext = 1 
    
    #maximum number of simultaneous renders for the start_next_job() function
    maxglobalrenders = 1 

    #terminal output verbose. 0 = normal, 1 = write everything from render 
    #stdout to terminal
    verbose = 0

    #default path, start, and end frame to put in New / Edit job window
    default_path = '/mnt/data/test_render/test_render.blend'
    default_start = 1
    default_end = 3

    #default render engine. Can be 'blender' or 'terragen'
    default_renderer = 'blender'

    defaults = [computers, fast, farm, renice_list, macs, blenderpath_mac, 
            blenderpath_linux, terragenpath_mac, terragenpath_linux, 
            allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, 
            default_path, default_start, default_end, default_renderer]

    return defaults

def define_global_config_vars(settings):
    '''Defines/updates global variables from config settings.'''
    global cfgsettings
    global computers
    global fast
    global farm
    global renice_list
    global macs
    global blenderpath_mac
    global blenderpath_linux
    global terragenpath_mac
    global terragenpath_linux
    global allowed_filetypes
    global timeout
    global startnext
    global maxglobalrenders
    global verbose
    global default_path
    global default_start
    global default_end
    global default_renderer

    print('Updating global config variables.')
    cfgsettings = settings
    computers = settings[0]
    fast = settings[1]
    farm = settings[2]
    renice_list = settings[3]
    macs = settings[4]
    blenderpath_mac = settings[5]
    blenderpath_linux = settings[6]
    terragenpath_mac = settings[7]
    terragenpath_linux = settings[8]
    allowed_filetypes = settings[9]
    timeout = settings[10]
    startnext = settings[11]
    maxglobalrenders = settings[12]
    verbose = settings[13]
    default_path = settings[14]
    default_start = settings[15]
    default_end = settings[16]
    default_renderer = settings[17]


#check for a config file
if not cfgfile.check():
    print('No config file found. Creating one from defaults.')
    cfgsettings = cfgfile.write(set_defaults())
else:
    print('Config file found. Reading...')
    try:
        cfgsettings = cfgfile.read()
    except:
        print('Config file corrupt or damaged. Creating new...')
        cfgsettings = cfgfile.write(set_defaults())

    #verify that config file contains appropriate number of entries
    #avoids error if config file is out of date with script version
    defaults = set_defaults()
    if not len(defaults) == len(cfgsettings):
        print('Config file length mismatch. Overwriting with default values...')
        cfgsettings = cfgfile.write(defaults)

#now define variables in main based on cfgsettings
define_global_config_vars(cfgsettings)

def update_cfgfile():
    cfgsettings = [computers, fast, farm, renice_list, macs, blenderpath_mac, 
            blenderpath_linux, terragenpath_mac, terragenpath_linux, 
            allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, 
            default_path, default_start, default_end, default_renderer]
    print('Updating config file.')
    cfgfile.write(cfgsettings)



#----------GLOBAL VARIABLES----------

#total number of queue slots (for scalability purposes
#used in various range() functions)
queueslots = 5 

#create global renderJobs dictionary
#holds render info for each job
#format:
'''{ job(int) : [path(str), startframe(int), endframe(int), 
    extraframes(list), computerList(list), threads(dict), currentFrames(dict), 
    totalFrames(list), status(str), index(int), termout(str), timestart(str), 
    render_engine(str) }'''
#Definitions:
#extraframes: list of non-sequential frames to be rendered 
    #(must be outside of range(startframe, endframe + 1)
#computerList: list of computers on which to render the current job
#threads: PIDs for currently-running threads. Format is {'computer': PID}. 
    #Used for stop function
#currentFrames: frames that are currently assigned to render threads. 
    #Format is {'computer': [frame, time]}. Used in timeout function and for 
    #killing processes.
#totalFrames: list of all frames for a job.  Initially filled with zeros to mark 
    #length of anticipated render. Zeros replaced with frame numbers as each 
    #frame is returned. 
#status: string representing current queue status. Can be 'Empty', 'Waiting', 
    #'Rendering', 'Stopped', 'Finished'
#index: integer representing the number of the job. This is the same as the 
    #queue slot's index in the job number (redundant, there was a reason for 
    #this originally)
#termout: string containing per-computer render progress, parsed to update 
    #progress bars.
#log_path: time of render start for logging purposes 
#render_engine: which render engine to use. Currently 'blender' or 'terragen'
 

renderJobs= dict()
#put empty placeholders so parsing/checking functions work
for job in range(1, queueslots + 1): 
    renderJobs[job] = ['', 0, 0, [], [], {}, {}, [], 'Empty', job, '', '', 
        'blender']


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
#compflags block while render is active, limiting to one renderthread per 
#computer per job
compflags = dict()
for job in range(1, queueslots + 1): 
    for computer in computers:
        compflags[str(job)+'_'+computer] = 0


#create killflags list
#if killflags[index] == 1, render is killed
killflags = []
for job in range(1, queueslots + 2): #+2 b/c first index is 0
    killflags.append(0)

#create re-entrant thread lock
threadlock = threading.RLock()

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
#use internal quit function instead of OSX
root.bind('<Command-q>', lambda x: quit()) 
root.bind('<Control-q>', lambda x: quit())
#ttk.Style().theme_use('clam') #use clam theme for widgets in Linux

smallfont = tkFont.Font(family='System', size='10')

#test font width & adjust font size to make sure everything fits with 
#different system fonts
fontwidth = smallfont.measure('abc ijk 123.456')
newsize = 10
if fontwidth > 76:
    while fontwidth > 76:
        newsize -= 1
        smallfont = tkFont.Font(family='System', size=newsize)
        fontwidth = smallfont.measure('abc ijk 123.456')



#---GUI Variables---

pathInput = StringVar(None)
pathInput.set(default_path)

startInput = StringVar(None)
startInput.set(default_start)

endInput = StringVar(None)
endInput.set(default_end)

extrasInput = StringVar(None)

compList = StringVar(None)

jobNumber = IntVar()
jobNumber.set(1)

verbosity = IntVar() #tkinter equivalent of verbose variable
verbosity.set(verbose)

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

#create render engine variable
render_eng = StringVar()
render_eng.set(default_renderer)





#---------INPUT WINDOW----------

def input_window(): 
    '''opens a new window for render queue input'''

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



    #---Render Engine Radiobuttons---
    rebox = LabelFrame(inputBox, text='Render Engine')
    rebox.grid(row=4, column=0, columnspan=3, padx=5, pady=5, sticky=W)
    rebtn_blender = Radiobutton(rebox, text='Blender', variable=render_eng, 
        value='blender')
    rebtn_blender.grid(row=0, column=0, padx=5, pady=5, sticky=W)
    rebtn_tgn = Radiobutton(rebox, text='Terragen', variable=render_eng, 
        value='terragen')
    rebtn_tgn.grid(row=0, column=1, padx=5, pady=5, sticky=W)
    #rebtn_blender.invoke()


    #---Computer Checkboxes---

    compBox = LabelFrame(inputBox, name='compBox', text='Computers:')
    compBox.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky=W)

    compAll = Checkbutton(compBox, text='All', variable=compAllvar,
        command=checkAll)
    compAll.grid(row=0, column=0, padx=5, pady=5, sticky=W)

    compFast = Checkbutton(compBox, text='Fast', variable=compFastvar, 
        command=checkFast)
    compFast.grid(row=0, column=1, padx=5, pady=5, sticky=W)

    compFarm = Checkbutton(compBox, text='Farm', variable=compFarmvar, 
        command=checkFarm)
    compFarm.grid(row=0, column=2, padx=5, pady=5, sticky=W)

    #generates table of computer checkbuttons
    for i in range(len(computers)): 
        if i < 6: #generate fast buttons
            fastButton = Checkbutton(compBox, name=computers[i]+'_button', 
                text=computers[i], variable=compvars[i], command=uncheckTop)
            fastButton.grid(row=1, column=i, padx=5, pady=5, sticky=W)
        elif i < 12: #generate farm buttons
            farmButton = Checkbutton(compBox, name=computers[i]+'_button', 
                text=computers[i], variable=compvars[i], command=uncheckTop)
            farmButton.grid(row=2, column=i-6, padx=5, pady=5, sticky=W)
        else: #generate buttons for extra computers
            compButton = Checkbutton(compBox, name=computers[i]+'_button', 
                text=computers[i], variable=compvars[i], command=uncheckTop)
            compButton.grid(row=3, column=i-12, padx=5, pady=5, sticky=W)

    #---Buttons---

    buttonFrame = Frame(inputBox)
    buttonFrame.grid(row=6, column=0, columnspan=3, padx=5, pady=5, sticky=W)

    okbutton = Button(buttonFrame, text='OK', command=queueJob, borderwidth=4)
    okbutton.grid(row=0, column=0, sticky=W)
    #activates OK button when user presses enter
    input_win.bind('<Return>', lambda x: okbutton.invoke()) 
    #for the numpad enter key
    input_win.bind('<KP_Enter>', lambda x: okbutton.invoke()) 

    cancelbutton = Button(buttonFrame, text='Cancel', command=input_win.destroy)
    cancelbutton.grid(row=0, column=1, sticky=W)
    #activates cancel button when user presses Esc
    input_win.bind('<Escape>', lambda x: cancelbutton.invoke()) 

    clearcomps = Button(buttonFrame, text='Reset Computers', command=uncheckAll)
    clearcomps.grid(row=0, column=2,  sticky=E)

    clearbutton = Button(buttonFrame, text='Reset All', command=clearInputs)
    clearbutton.grid(row=0, column=3, sticky=E)






#----------PREFERENCES WINDOW----------
def prefs():
    #define tk variables corresponding to global cfgsettings
    cb_macs = [] #checkboxes for macs
    cb_fast = [] #checkboxes for fast
    cb_farm = [] #checkboxes for farm
    cb_renice = [] #checkboxes for renice_list
    for i in range(len(computers)):
        cb_macs.append(IntVar())
        cb_fast.append(IntVar())
        cb_farm.append(IntVar())
        cb_renice.append(IntVar())
    
    tk_blenderpath_mac = StringVar()
    tk_blenderpath_linux = StringVar()
    tk_terragenpath_mac = StringVar()
    tk_terragenpath_linux = StringVar()
    tk_allowed_filetypes = StringVar()
    tk_timeout = StringVar()
    tk_startnext = IntVar()
    tk_maxglobalrenders = StringVar()
    tk_verbose = IntVar()
    tk_default_path = StringVar()
    tk_default_start = StringVar()
    tk_default_end = StringVar()
    tk_default_renderer = StringVar()
    
    
    def populate_prefs_fields(cfgsettings):
        '''Populates the preferences window fields.'''
        for i in range(len(cfgsettings[0])):
            if cfgsettings[0][i] in cfgsettings[4]:
                cb_macs[i].set(1)
            else:
                cb_macs[i].set(0)
    
            if cfgsettings[0][i] in cfgsettings[1]:
                cb_fast[i].set(1)
            else:
                cb_fast[i].set(0)
    
            if cfgsettings[0][i] in cfgsettings[2]:
                cb_farm[i].set(1)
            else:
                cb_farm[i].set(0)
    
            if cfgsettings[0][i] in cfgsettings[3]:
                cb_renice[i].set(1)
            else:
                cb_renice[i].set(0)
    
        #clear fields
        bpath_mac_input.delete(0, END)
        bpath_linux_input.delete(0, END)
        tgnpath_mac_input.delete(0, END)
        tgnpath_linux_input.delete(0, END)
        aftinput.delete(0, END)
        toinput.delete(0, END)
        mginput.delete(0, END)
        defpathinput.delete(0, END)
        defstart_entry.delete(0, END)
        defend_entry.delete(0, END)
        
        bpath_mac_input.insert(END, cfgsettings[5])
        bpath_linux_input.insert(END, cfgsettings[6])
        tgnpath_mac_input.insert(END, cfgsettings[7])
        tgnpath_linux_input.insert(END, cfgsettings[8])
        toinput.insert(END, cfgsettings[10])
        mginput.insert(END, cfgsettings[12])
        defpathinput.insert(END, cfgsettings[14])
        defstart_entry.insert(END, cfgsettings[15])
        defend_entry.insert(END, cfgsettings[16])
        
        #format list as string for display in input fields
        str_allowed_filetypes = ''
        for i in cfgsettings[9]:
            str_allowed_filetypes = str_allowed_filetypes + i + ' '
        
        aftinput.insert(END, str_allowed_filetypes)

        #set button states
        if cfgsettings[11] == 1:
            tk_startnext.set(1)
        else:
            tk_startnext.set(0)

        if cfgsettings[13] == 1:
            tk_verbose.set(1)
        else:
            tk_verbose.set(0)

        tk_default_renderer.set(cfgsettings[17]) 
    
    def save_prefs():
        '''Gets input from fields, sets global variable values, updates config 
            file, closes prefs window.'''
    
        #clear each variable then put new values
        fast, farm, renice_list, macs = [], [], [], []
        for i in range(len(computers)):
            if cb_fast[i].get() == 1:
                fast.append(computers[i])
        for i in range(len(computers)):
            if cb_farm[i].get() == 1:
                farm.append(computers[i])
        for i in range(len(computers)):
            if cb_renice[i].get() == 1:
                renice_list.append(computers[i])
        for i in range(len(computers)):
            if cb_macs[i].get() == 1:
                macs.append(computers[i])
    
        blenderpath_mac = tk_blenderpath_mac.get()
        blenderpath_linux = tk_blenderpath_linux.get()
        terragenpath_mac = tk_terragenpath_mac.get()
        terragenpath_linux = tk_terragenpath_linux.get()
        allowed_filetypes = tk_allowed_filetypes.get().split()
        timeout = float(tk_timeout.get())
        startnext = int(tk_startnext.get())
        maxglobalrenders = int(tk_maxglobalrenders.get())
        verbose = int(tk_verbose.get())
        default_path = tk_default_path.get()
        default_start = int(tk_default_start.get())
        default_end = int(tk_default_end.get())
        default_renderer = tk_default_renderer.get()
    
        cfgsettings = [computers, fast, farm, renice_list, macs, blenderpath_mac, 
                blenderpath_linux, terragenpath_mac, terragenpath_linux, 
                allowed_filetypes, timeout, startnext, maxglobalrenders, verbose, 
                default_path, default_start, default_end, default_renderer]
        define_global_config_vars(cfgsettings)
        cfgfile.write(cfgsettings)
        prefs_win.destroy()
    
    
    def reset_prefs():
        '''Resets preferences to default values.'''
        defaults = set_defaults()
        #force restart if computer list differs from default 
        #prevents crash on GUI refresh
        if len(defaults[0]) != len(computers):
            if Dialog('Program must quit immediately to restore default computer '
                        + 'list.').confirm():
                cfgfile.write(defaults)
                quit()
            else:
                #do not proceed if lists don't match (disaster would ensue)
                print('Cancelled reset')
                return

        #also make sure contents of lists are the same even if length matches
        for comp in computers:
            if not comp in defaults[0]:
                if Dialog('Program must quit immediately to restore default '
                            + 'computer list.').confirm():
                    cfgfile.write(defaults)
                    quit()
                else:
                    #do not proceed if lists don't match (disaster would ensue)
                    print('Cancelled reset')
                    return

        print('Default preferences restored.')
        populate_prefs_fields(defaults)
    
    
    def update_complist():
        '''Updates computerlist edited by edit_complist()'''
        pass
        
    def edit_complist():
        '''Opens a popup window to edit the main computer list.'''

        def update_complist():
            raw_complist = complist.get(0.0, END)
            cfgsettings[0] = raw_complist.split()
            print('Updating config file. Restart to show changes.')
            print cfgsettings[0] #debugging
            cfgfile.write(cfgsettings)
            compsedit.destroy()
            prefs_win.destroy()
            Dialog('Computer list updated. Changes will not be visible until the '
                    + 'program is relaunched.').warn()

        compsedit = Toplevel()
        compsedit.config(bg='gray90')
        Label(compsedit, text=('Enter one computer per line. No spaces or commas. '
                + 'Name must be exactly as it appears in the hosts file.'), 
                wraplength='190', justify=LEFT, bg='gray90').pack(padx=10, pady=10)
        clframe = LabelFrame(compsedit, bg='gray90')
        clframe.pack(padx=10, pady=0)
        complist = st.ScrolledText(clframe, width=23, height=15)
        complist.pack(padx=0, pady=0)
        
        #populate the text box
        for i in computers:
            complist.insert(END, i + '\n')
    
        btnframe = Frame(compsedit, bg='gray90')
        btnframe.pack(padx=10, pady=10, anchor=W)
        ttk.Button(btnframe, text='Save', command=update_complist, 
            style='Toolbutton').pack(side=LEFT)
        ttk.Button(btnframe, text='Cancel', command=compsedit.destroy, 
            style='Toolbutton').pack(padx=5, side=RIGHT)

    
    #create window
    prefs_win = Toplevel()
    prefs_win.title('Preferences')
    prefs_win.config(bg='gray90')
    #use internal quit function instead of OSX
    prefs_win.bind('<Command-q>', lambda x: quit()) 
    prefs_win.bind('<Control-q>', lambda x: quit())
    prefs_win.bind('<Return>', lambda x: save_prefs())
    prefs_win.bind('<KP_Enter>', lambda x: save_prefs())
    #override native window close to be sure prefsopen is reset
    prefs_win.bind('<Escape>', lambda x: prefs_win.destroy())

    #left block
    leftframe = Frame(prefs_win, bg='gray90')
    leftframe.grid(row=0, column=0, padx=10, pady=10, sticky=NW)

    compframe = LabelFrame(leftframe, text='Computer List', bg='gray90')
    compframe.pack()
    
    Label(compframe, text='Computer Name', bg='gray90').grid(row=0, column=0, 
        sticky=W, padx=5, pady=5)
    Label(compframe, text='OSX', bg='gray90').grid(row=0, column=1, sticky=W, 
        pady=5)
    Label(compframe, text='Fast', bg='gray90').grid(row=0, column=2, sticky=W, 
        pady=5)
    Label(compframe, text='Farm', bg='gray90').grid(row=0, column=3, sticky=W, 
        pady=5)
    Label(compframe, text='Renice', bg='gray90').grid(row=0, column=4, sticky=W,
        pady=5)
    
    for i in range(len(computers)):
        Label(compframe, text=computers[i], bg='gray90').grid(row=i+1, column=0, 
        sticky=W, padx=5)
        Checkbutton(compframe, bg='gray90', variable=cb_macs[i]).grid(row=i+1, 
        column=1, sticky=W)
        Checkbutton(compframe, bg='gray90', variable=cb_fast[i]).grid(row=i+1, 
        column=2, sticky=W)
        Checkbutton(compframe, bg='gray90', variable=cb_farm[i]).grid(row=i+1, 
        column=3, sticky=W)
        Checkbutton(compframe, bg='gray90', variable=cb_renice[i]).grid(row=i+1,
            column=4)
    
    ttk.Button(compframe, text='Edit List', command=edit_complist, 
        style='Toolbutton').grid(row=len(computers)+1, column=0, sticky=SW, 
            padx=5, pady=5)

    btnframe = Frame(leftframe, bg='gray90')
    btnframe.pack(anchor=W)
    ttk.Button(btnframe, text='Save', style='Toolbutton', 
        command=save_prefs).pack(side=LEFT, padx=0, pady=5)
    ttk.Button(btnframe, text='Cancel', style='Toolbutton', 
        command=prefs_win.destroy).pack(side=LEFT, padx=5, pady=5)
    ttk.Button(btnframe, text='Restore Defaults', style='Toolbutton', 
        command=reset_prefs).pack(side=RIGHT, padx=0, pady=5)
    
    #middle block
    midframe = Frame(prefs_win, bg='gray90')
    midframe.grid(row=0, column=1, padx=0, pady=10, sticky=NW)
    
    pathbox = LabelFrame(midframe, text='Render Engine Paths', bg='gray90')
    pathbox.pack()
    
    Label(pathbox, text='Blender OSX Path', bg='gray90').pack(anchor=W, padx=5)
    bpath_mac_input = Entry(pathbox, width=50, highlightthickness=0, 
        textvariable=tk_blenderpath_mac)
    bpath_mac_input.pack(padx=5, pady=5)
    
    Label(pathbox, text='Blender Linux Path', bg='gray90').pack(anchor=W, padx=5)
    bpath_linux_input = Entry(pathbox, width=50, highlightthickness=0, 
        textvariable=tk_blenderpath_linux)
    bpath_linux_input.pack(padx=5, pady=5)
    
    Label(pathbox, text='Terragen OSX Path', bg='gray90').pack(anchor=W, padx=5)
    tgnpath_mac_input = Entry(pathbox, width=50, highlightthickness=0, 
        textvariable=tk_terragenpath_mac)
    tgnpath_mac_input.pack(padx=5, pady=5)
    
    Label(pathbox, text='Terragen Linux Path', bg='gray90').pack(anchor=W, padx=5)
    tgnpath_linux_input = Entry(pathbox, width=50, highlightthickness=0, 
        textvariable=tk_terragenpath_linux)
    tgnpath_linux_input.pack(padx=5, pady=5)
    
    aftbox = LabelFrame(midframe, text='Allowed File Types', bg='gray90')
    aftbox.pack() 
    Label(aftbox, text=('Allowed file extensions for missing frame check. '
        + 'For longer than 3 characters, enter only the last three '
        + 'characters.'), bg='gray90', wraplength=400, justify=LEFT).pack(padx=5, 
        pady=5, anchor=W)
    aftinput = Entry(aftbox, width=50, highlightthickness=0, 
        textvariable=tk_allowed_filetypes)
    aftinput.pack(padx=5, pady=5)

    defpathbox = LabelFrame(midframe, text='Default File Path', bg='gray90')
    defpathbox.pack()
    Label(defpathbox, text='Default file path in the New / Edit job window.', 
        bg='gray90', justify=LEFT).pack(padx=5, pady=5, anchor=W)
    defpathinput = Entry(defpathbox, width=50, highlightthickness=0, 
        textvariable=tk_default_path)
    defpathinput.pack(padx=5, pady=5)
    
    
    #right block
    rightframe = Frame(prefs_win, bg='gray90')
    rightframe.grid(row=0, column=2, padx=10, pady=10, sticky=NW)
    
    toframe = LabelFrame(rightframe, text='Global Timeout', bg='gray90')
    toframe.pack(anchor=W, fill=X)
    toinput = Entry(toframe, width=7, highlightthickness=0, 
        textvariable=tk_timeout)
    toinput.pack(side=LEFT, padx=5)
    Label(toframe, text='Sec.', bg='gray90').pack(side=LEFT, padx=0)
    Label(toframe, text=('Maximum time controller will wait between updates '
        + 'before marking a computer offline and retrying.'), 
        wraplength=175, bg='gray90', justify=LEFT).pack(side=LEFT, padx=5, pady=5)
    
    mgframe = LabelFrame(rightframe, text='Max. Simul. Renders', bg='gray90')
    mgframe.pack(anchor=W, fill=X)
    mginput = Entry(mgframe, width=5, highlightthickness=0, 
        textvariable=tk_maxglobalrenders)
    mginput.pack(side=LEFT, padx=5)
    Label(mgframe, text=('Max number of simultaneous renders that can be '
        + 'initiated by the autostart function.'), wraplength=225, bg='gray90', 
        justify=LEFT).pack(side=LEFT, padx=5, pady=5)
    
    subframe = LabelFrame(rightframe, text='Default Button States', bg='gray90')
    subframe.pack(anchor=W, fill=X)
    Label(subframe, text='This sets the defult button state at startup. Changes '
        + 'do not affect the current settings in the main window.', bg='gray90', 
        wraplength='300', justify=LEFT).pack()
    Checkbutton(subframe, text='Autostart enabled', bg='gray90',
        variable=tk_startnext).pack(anchor=W, padx=5, pady=5)
    Checkbutton(subframe, text='Verbose enabled', bg='gray90', 
        variable=tk_verbose).pack(anchor=W, padx=5, pady=5)

    defframe_frame = LabelFrame(rightframe, text='Default Frame Numbers', 
        bg='gray90')
    defframe_frame.pack(anchor=W, fill=X)
    Label(defframe_frame, text='Default start and end frame numbers for New / '
        + 'Edit job window.', wraplength='300', justify=LEFT, 
        bg='gray90').grid(row=0, column=0, columnspan=4)
    Label(defframe_frame, text='Start:', bg='gray90').grid(row=1, column=0)
    defstart_entry = Entry(defframe_frame, width=6, textvariable=tk_default_start, 
        highlightthickness=0)
    defstart_entry.grid(row=1, column=1, pady=5)
    Label(defframe_frame, text='End:', bg='gray90').grid(row=1, column=2)
    defend_entry = Entry(defframe_frame, width=6, textvariable=tk_default_end, 
        highlightthickness=0)
    defend_entry.grid(row=1, column=3, pady=5)

    defreframe = LabelFrame(rightframe, text='Default Render Engine', bg='gray90')
    defreframe.pack(anchor=W, fill=X)
    Radiobutton(defreframe, text='Blender', variable=tk_default_renderer, 
        value='blender', bg='gray90').pack(side=LEFT, padx=5, pady=5)
    Radiobutton(defreframe, text='Terragen', variable=tk_default_renderer, 
        value='terragen', bg='gray90').pack(side=LEFT, padx=5, pady=5)

    populate_prefs_fields(cfgsettings)




#----------SYSTEM STATUS WINDOW----------
#dict containing max ram for each computer
maxram = {'bierstadt':64, 'massive':64, 'sneffels':64, 'sherman':64, 
    'the-holy-cross':64, 'eldiente':32, 'lindsey':16, 'wetterhorn':8, 
    'lincoln':8, 'snowmass':8, 'humberto':8, 'tabeguache':8, 'conundrum':16, 
    'paradox':16 } 

#dict containing number of processor threads for each computer
proc_threads = {'bierstadt':12, 'massive':12, 'sneffels':12, 'sherman':12, 
    'the-holy-cross':12, 'eldiente':8, 'lindsey':4, 'wetterhorn':2, 
    'lincoln':2, 'snowmass':2, 'humberto':2, 'tabeguache':2, 'conundrum':8, 
    'paradox':8} 

#dictionary of CPU and RAM status, format is 
#{computer: [cpu_peak, ram_peak, cpu_history, ram_history]}
statdict = dict()
for computer in computers: 
    statdict[computer] = [0, 0, [], []] 

#generate list of x coordinates for status graph
#location of graph baseline (pixels below top of canv)
ycoord_max = 69
#location of 100% line (pixels below top of canv). 
#4 pixels lower than top of graph window so 100% line doesn't overlap frame
ycoord_min = 9 
xcoords = []
n = 5 
while n <= 285:
    xcoords.append(n)
    n += 28

#create list of y-coordinates 
ycoords = []
n = ycoord_min
while n <= ycoord_max:
    ycoords.append(n)
    n += 16

#flag to prevent opening more than one systat window at a time
systat_test = 0 


systat_update_interval = 1 #update frequency in seconds
systat_update_tk = DoubleVar() #tkinter version of above
systat_update_tk.set(systat_update_interval)

def systat():

    global systat_test
    if systat_test == 1:
        return

    systat_test = 1

    def set_systat_interval():
        global systat_update_interval
        systat_update_interval = systat_update_tk.get()
        print('System status will now update once every '
            +str(systat_update_interval)+' seconds.')

    def get_sysinfo():
        for computer in computers: 

            cpu = SystemStatus(computer).get_cpu() 
            mem = SystemStatus(computer).get_memory()
            
            #normalize ram usage out of 100
            rambar = mem / (maxram[computer]) * 100 

            #update max CPU value
            if cpu > statdict[computer][0]: 
                statdict[computer][0] = cpu
            #update max ram value
            if mem > statdict[computer][1]:
                statdict[computer][1] = mem 

            #fill empty slots in CPU & RAM histories with zeros to prevent 
            #index errors
            while len(statdict[computer][2]) < 11: 
                statdict[computer][2].append(0)

            while len(statdict[computer][3]) < 11:
                statdict[computer][3].append(0)

            #append most recent values to CPU & RAM histories
            statdict[computer][2].append(cpu)
            #remove oldest history entry
            statdict[computer][2].pop(0) 

            statdict[computer][3].append(rambar)
            statdict[computer][3].pop(0)

            #print current numbers
            #using try statements to prevent errors if window is closed in 
            #middle of an operation
            try:
                systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                    +computer).delete('statnumbers')
    
                systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                    +computer).create_text(30, ycoord_max + 5, 
                    text=str(round(cpu, 1))+'%', anchor=NW, font=smallfont, 
                    tag='statnumbers')
                systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                    +computer).create_text(120, ycoord_max + 5, 
                    text=str(round(statdict[computer][0], 1))+'%', anchor=NW, 
                    font=smallfont, tag='statnumbers')
                systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                    +computer).create_text(187, ycoord_max + 5, 
                    text=str(round(mem, 1))+'GB', anchor=NW, font=smallfont, 
                    tag='statnumbers')
                systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                    +computer).create_text(282, ycoord_max + 5, 
                    text=str(round(statdict[computer][1], 1))+'GB', anchor=NW, 
                    font=smallfont, tag='statnumbers')
            except:
                print('exception in get_sysinfo() attempting to put text in '
                    'canv. Exiting function') #debugging
                #no point in attempting to draw graph if function fails here
                return 

            draw_graph(computer)



    def draw_graph(computer):
        cpu_history = statdict[computer][2]
        ram_history = statdict[computer][3]

        #invert CPU history so that graph displays correctly 
        #with top of canvas = 0 
        cpu_history_inverted = []
        for i in cpu_history:
            #correct for y scale. Using 60 so that 100% line 
            #falls slightly below top border of graph canvas.
            x = 60 * i/100.0 
            #use ycoord_max so top isn't clipped
            cpu_history_inverted.append(ycoord_max - x) 
            
        #invert RAM history
        ram_history_inverted = []
        for i in ram_history:
            #correct for y scale
            x = 60 * i/100.0 
            ram_history_inverted.append(ycoord_max - x)

        try:
            systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                +computer).delete('graph')
            systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                +computer).delete('frame')
        except:
            pass

        try:
            #create CPU history graph
            systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                +computer).create_polygon(xcoords[0]-0.01, ycoord_max, 
                xcoords[0],  cpu_history_inverted[0], xcoords[1],  
                cpu_history_inverted[1], xcoords[2],  cpu_history_inverted[2], 
                xcoords[3],  cpu_history_inverted[3], xcoords[4],  
                cpu_history_inverted[4], xcoords[5],  cpu_history_inverted[5], 
                xcoords[6],  cpu_history_inverted[6], xcoords[7],  
                cpu_history_inverted[7], xcoords[8],  cpu_history_inverted[8], 
                xcoords[9], cpu_history_inverted[9], xcoords[10], 
                cpu_history_inverted[10], xcoords[10]+0.01, ycoord_max, 
                fill='', outline='blue', tag='graph', width=2)

            #create RAM history graph
            systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                +computer).create_polygon(xcoords[0]-0.01, ycoord_max, 
                xcoords[0],  ram_history_inverted[0], xcoords[1],  
                ram_history_inverted[1], xcoords[2],  ram_history_inverted[2], 
                xcoords[3],  ram_history_inverted[3], xcoords[4],  
                ram_history_inverted[4], xcoords[5],  ram_history_inverted[5], 
                xcoords[6],  ram_history_inverted[6], xcoords[7],  
                ram_history_inverted[7], xcoords[8],  ram_history_inverted[8], 
                xcoords[9], ram_history_inverted[9], xcoords[10], 
                ram_history_inverted[10], xcoords[10]+0.01, ycoord_max, 
                fill='', outline='red', tag='graph', width=2)

            #redraw frame to make sure it's always on top
            systatframe.nametowidget('sysinfoframe_'+computer+'.graphcanv_'
                +computer).create_rectangle(xcoords[0], 5, xcoords[-1], 
                ycoord_max, fill='', outline='black', tag='frame', width=2)

        except:
            pass



    def sysinfohandler(): 
        while 1:
            #get state to check if window is still open
            try: 
                systatwin.state() 
            #assume exception means window is closed, break loop.
            except: 
                print ('window closed, terminating sysinfohandler loop') 
                    #debugging
                global systat_test
                systat_test = 0 #reset flag
                break

            get_sysinfo()
            global systat_update_interval
            #graph update frequency in seconds
            time.sleep(systat_update_interval) 


    systatwin = Toplevel()
    systatwin.config(bg='gray90')
    #use internal quit function instead of OSX
    systatwin.bind('<Command-q>', lambda x: quit()) 
    systatwin.bind('<Control-q>', lambda x: quit())
    
    tbarframe = Frame(systatwin, bg='gray90', highlightthickness=0)
    tbarframe.grid(row=0, column=0, padx=10, pady=5, sticky=W)
    uffframe = LabelFrame(tbarframe, bg='gray90', highlightthickness=0)
    uffframe.grid(row=0, column=0)
    Label(uffframe, text='Update interval:', highlightthickness=0, 
        bg='gray90').grid(row=0, column=0, sticky=W)
    Entry(uffframe, textvariable=systat_update_tk, width=4, 
        highlightthickness=0).grid(row=0, column=1, sticky=W)
    Label(uffframe, text='sec.', highlightthickness=0, bg='gray90').grid(row=0, 
        column=2, sticky=W)
    ttk.Button(uffframe, text='Set', style='Toolbutton', 
        command=set_systat_interval).grid(row=0, column=3, sticky=W)
    ttk.Button(tbarframe, text='Close', style='Toolbutton', 
        command=systatwin.destroy).grid(row=0, column=1, padx=10, sticky=W)
    systatframe = LabelFrame(systatwin)
    systatframe.grid(row=1, column=0, padx=10, ipadx=5, ipady=5)

    #generate system info boxes for each computer
    for i in range(len(computers)): 

        #create three-column layout
        if i < 5: 
            col = 0
            rww = i
        elif i < 10:
            col = 1
            rww = i - 5
        else:
            col = 2
            rww = i - 10

        sysinfoframe = LabelFrame(systatframe, text=computers[i], 
            name='sysinfoframe_'+computers[i])
        sysinfoframe.grid(row=rww, column=col, padx=10)
        graphcanv = Canvas(sysinfoframe, width=320, height=85, 
            name='graphcanv_'+computers[i])
        graphcanv.grid(row=0, column=0)

        #create time labels and vertical lines
        t = 10 #number of x-axis data points on graph
        for xcoord in xcoords:
            #only draw lines for even numbers
            if t % 2 == 0: 
                graphcanv.create_line(xcoord, 5, xcoord, ycoord_max, 
                    fill='PaleGreen', dash=(4, 4))
            t -= 1
        
        #create y-axis labels and horizontal lines
        for ycoord in ycoords:
            graphcanv.create_line(xcoords[0], ycoord, xcoords[-1], ycoord, 
            fill='LightSkyBlue', dash=(4,4))
        graphcanv.create_text(xcoords[-1]+5, ycoord_min, text='100%', anchor=W, 
            font=smallfont)
        graphcanv.create_text(xcoords[-1]+5, ycoord_max / 2 + ycoord_min, 
            text='50%', anchor=W, font=smallfont) 
        graphcanv.create_text(xcoords[-1]+5, ycoord_max, text='0%', anchor=W, 
            font=smallfont)

        #create CPU & RAM number labels
        graphcanv.create_text(5, ycoord_max + 5, text='CPU:', anchor=NW, 
            font=smallfont, fill='blue')
        graphcanv.create_text(70, ycoord_max + 5, text='CPU Peak:', anchor=NW, 
            font=smallfont)
        graphcanv.create_text(160, ycoord_max + 5, text='RAM:', anchor=NW, 
            font=smallfont, fill='red')
        graphcanv.create_text(230, ycoord_max + 5, text='RAM Peak:', anchor=NW, 
            font=smallfont)

        #create placeholders for CPU & RAM values
        graphcanv.create_text(30, ycoord_max + 5, text='...', anchor=NW, 
            font=smallfont, tag='statnumbers')
        graphcanv.create_text(120, ycoord_max + 5, text='...', anchor=NW, 
            font=smallfont, tag='statnumbers')
        graphcanv.create_text(187, ycoord_max + 5, text='...', anchor=NW, 
            font=smallfont, tag='statnumbers')
        graphcanv.create_text(282, ycoord_max + 5, text='...', anchor=NW, 
            font=smallfont, tag='statnumbers')

        #create frame around graph
        graphcanv.create_rectangle(xcoords[0], 5, xcoords[-1], ycoord_max, 
            fill='', outline='black', tag='frame', width=2)

        #padding for bottom of window
        Frame(systatwin).grid(row=2, pady=5) 

    #encapsulate get_sysinfo in new thread to prevent blocking GUI processes
    sysinfothread = threading.Thread(target=sysinfohandler, args=())
    sysinfothread.start()    

    




#----------EXTRAFRAMES BALLOON---------
#displays long list of extraframes in popup box
def extraballoon(event, index):
    extras = renderJobs[index][3]
    #don't open window if there aren't enough frames to show 
    if len(extras) <= 2: 
        return

    #protect against crashes caused by negative window offsets on 
    #multiple monitors.
    if event.x_root < 0: 
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
    #destroy window when cursor leaves area
    jobstatFrame.nametowidget('jobstat_'+str(index)+'.extrafram_'
        +str(index)).bind('<Leave>', lambda x: exwin.destroy()) 

    extras.sort()
    for frame in extras:
        if frame != 0:
            Label(exwin, text=frame).pack(padx=5)




#----------FILENAME BALLOON---------
#displays file path in popup box
def nameballoon(event, index):
    filepath = renderJobs[index][0]
    #if len(filepath) <= 18: #don't open if filepath isn't truncated
    #    return

    #protect against crashes caused by negative window offsets on 
    #multiple monitors.
    if event.x_root < 0: 
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
    jobstatFrame.nametowidget('jobstat_'+str(index)+'.filenam_'
        +str(index)).bind('<Leave>', lambda x: namewin.destroy())

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
            Dialog('No suitable files found in directory. Check path and try '
                    + 'again.').warn()
            return
    
        #reverse filename and check backwards from end until a non-digit is 
        #found.  Assume this is start of name text
        #intended to prevent problems if there are numbers in filename 
        #before sequential numbers
        length = range(len(name))
        length.reverse()
        for i in length:
            if not name[i].isdigit():
                leftbreak = i+1
                #assuming sequential #s go to end of filename
                rightbreak = len(filename) - len(ext) - 1 
                sequentials = filename[leftbreak:rightbreak]
                break

        #configure slider initial state
        slidelength = len(filename)
        slider_left.config(to=slidelength)
        slider_right.config(to=slidelength)
        slider_left.set(leftbreak)
        slider_right.set(rightbreak)
        nameleft.config(text=filename[0:leftbreak], bg='white')
        nameseq.config(text=sequentials, bg='DodgerBlue')
        nameright.config(text=filename[rightbreak:], bg='white')
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
            if Dialog('Browse to render directory now?').confirm():
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
        nameleft.config(text=filename[0:leftbreak], bg='white')
        nameseq.config(text=sequentials, bg='DodgerBlue')
        nameright.config(text=filename[rightbreak:], bg='white')
        checkframes['leftbreak'] = leftbreak
        checkframes['rightbreak'] = rightbreak
        checkframes['sequentials'] = sequentials
    
    
    def get_framecheck_path(): 
        '''handles the browse button'''
        filepath = tkFileDialog.askdirectory() 
        check_path.set(filepath)
    
    def getlist():
        dir_contents = checkframes['dir_contents']
        leftbreak = checkframes['leftbreak']
        rightbreak = checkframes['rightbreak']
        sequentials = checkframes['sequentials']

        for i in sequentials:
            if not i.isdigit():
                Dialog('Sequential file numbers must contain only integers.').warn()
                return


        dirconts.delete(0.0, END)
        foundfrms.delete(0.0, END)
        expfrms.delete(0.0, END)
        missfrms.delete(0.0, END)

        frames_expected = []
        frames_found = []
        frames_missing = []

        chkpath = check_path.get()
        #make sure trailing slash is present
        if chkpath[-1] != '/': 
            chkpath = chkpath + '/'

        start = int(check_start.get())
        end = int(check_end.get())

        for frame in range(start, end + 1):
            frames_expected.append(frame)

        for line in dir_contents:
            dirconts.insert(END, str(line)+'\n')
            #verify that line is an image
            if line [-3:] in allowed_filetypes: 
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
    Label(cfwin, text='Compare the contents of a directory against a generated '
        'file list to search for missing frames.', bg='gray90').grid(row=0, 
        column=0, padx=10, pady=10, sticky=W)

    cfframe = LabelFrame(cfwin, bg='gray90')
    cfframe.grid(row=1, column=0, padx=10, pady=10)
    Label(cfframe, text='Check existing job:', bg='gray90').grid(row=0, 
        column=0, padx=5, pady=5, sticky=E)
    bbox = Frame(cfframe)
    bbox.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky=W)
    ttk.Radiobutton(bbox, text='None', variable=checkjob, value=0, 
        command=put_text, style='Toolbutton').grid(row=0, column=1, sticky=W)
    
    for i in range(1, queueslots + 1):
        if Job(i).checkSlotFree():
            #disable job buttons for empty queue slots
            btnstate = 'disabled' 
        else:
            btnstate = 'normal'
        ttk.Radiobutton(bbox, text=str(i), variable=checkjob, value=i, 
            command=put_text, state=btnstate, style='Toolbutton').grid(row=0, 
            column=i+1, sticky=W)
    
    Label(cfframe, text='Directory to check:', bg='gray90').grid(row=1, 
        column=0, padx=5, pady=5, sticky=E)
    checkin = Entry(cfframe, textvariable=check_path, width=50, 
        highlightthickness=0)
    checkin.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=W)
    ttk.Button(cfframe, text='Browse', command=get_framecheck_path).grid(row=1, 
        column=4, padx=5, pady=5, sticky=W)
    
    Label(cfframe, text='Start frame:', bg='gray90').grid(row=2, column=0, 
        padx=5, pady=5, sticky=E)
    startent = Entry(cfframe, textvariable=check_start, width=20, 
        highlightthickness=0)
    startent.grid(row=2, column=1, padx=5, pady=5, sticky=W)

    Label(cfframe, text='End frame:', bg='gray90').grid(row=3, column=0, 
        padx=5, pady=5, sticky=E)
    endent = Entry(cfframe, textvariable=check_end, width=20, 
        highlightthickness=0)
    endent.grid(row=3, column=1, padx=5, pady=5, sticky=W)

    startbtn = ttk.Button(cfframe, text='Start', width=10, command=get_breaks)
    startbtn.grid(row=4, column=1, padx=5, pady=5, sticky=W)
    cfwin.bind('<Return>', lambda x: startbtn.invoke())
    cfwin.bind('<KP_Enter>', lambda x: startbtn.invoke())
    cfwin.bind('<Command-w>', lambda x: chkclose())
    cfwin.bind('<Control-w>', lambda x: chkclose())
    

    confirmframe = LabelFrame(cfframe, text='Adjust Filename Parsing', 
        bg='gray90')
    confirmframe.grid(row=2, rowspan=3 , column=2, columnspan=3, padx=10, 
        pady=5, ipady=5, sticky=W)
    Label(confirmframe, text='Move sliders to isolate sequential file numbers.',
        bg='gray90').grid(row=0, column=0, columnspan=3)

    nameframe = Frame(confirmframe, bg='gray90', highlightthickness=0)
    nameframe.grid(row=1, column=0, columnspan=3)
    nameleft = Label(nameframe, fg='gray50', highlightthickness=0, bg='gray90')
    nameleft.grid(row=1, column=0, sticky=E)

    nameseq = Label(nameframe, fg='white', highlightthickness=0, bg='gray90')
    nameseq.grid(row=1, column=1)

    nameright = Label(nameframe, fg='gray50', highlightthickness=0, bg='gray90')
    nameright.grid(row=1, column=2, sticky=W)
    
    slider_left = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, 
        length=300, command=lambda x: get_slider())
    slider_left.grid(row=2, column=0, columnspan=3)
    
    slider_right = ttk.Scale(confirmframe, from_=0, to=100, orient=HORIZONTAL, 
        length=300, command=lambda x: get_slider())
    slider_right.grid(row=3, column=0, columnspan=3)

    ttk.Button(confirmframe, text='Update', command=getlist).grid(row=4, 
        column=0, columnspan=3)


    resultframe = LabelFrame(cfframe, text='Result', bg='gray90')
    resultframe.grid(row=5, column=0, columnspan=5, padx=10, pady=5, ipady=5)

    Label(resultframe, text='Directory contents:', bg='gray90').grid(row=0, 
        column=0, padx=5, sticky=W)
    #directory contents
    dirconts = st.ScrolledText(resultframe, width=38, height=10, 
        highlightthickness=0, bd=4) 
    dirconts.frame.config(border=2, relief=GROOVE)
    dirconts.grid(row=1, column=0, padx=5, sticky=W)

    Label(resultframe, text='Found:', bg='gray90').grid(row=0, column=1, padx=5, 
        sticky=W)
    #found frame numbers after parsing
    foundfrms = st.ScrolledText(resultframe, width=10, height=10, 
        highlightthickness=0, bd=4) 
    foundfrms.frame.config(border=2, relief=GROOVE)
    foundfrms.grid(row=1, column=1, padx=5, sticky=W)

    Label(resultframe, text='Expected:', bg='gray90').grid(row=0, column=2, 
        padx=5, sticky=W)
    #expected frames
    expfrms = st.ScrolledText(resultframe, width=10, height=10, 
        highlightthickness=0, bd=4) 
    expfrms.frame.config(border=2, relief=GROOVE)
    expfrms.grid(row=1, column=2, padx=5, sticky=W)

    Label(resultframe, text='Missing:', bg='gray90').grid(row=0, column=3, 
        padx=5, sticky=W)
    #missing frames
    missfrms = st.ScrolledText(resultframe, width=10, height=10, 
        highlightthickness=0, bd=4) 
    missfrms.frame.config(border=2, relief=GROOVE)
    missfrms.grid(row=1, column=3, padx=5, sticky=W)
    
    
    ttk.Button(cfframe, text='Close', command=chkclose, 
        style='Toolbutton').grid(column=0, padx=5, pady=5, sticky=W)







#------GUI LAYOUT------

topbar = Frame(root, bd=0, bg='gray90')
topbar.grid(row=0, column=0, padx=10, sticky=W)

verbosebtn = ttk.Checkbutton(topbar, text='Verbose', variable=verbosity, 
    command=toggle_verbosity, style='Toolbutton')
verbosebtn.grid(row=0, column=0, pady=5, sticky=W)

autobtn = ttk.Checkbutton(topbar, text='Autostart New Renders', variable=stnext,
    command=set_startnext, style='Toolbutton')
autobtn.grid(row=0, column=1, padx=5, sticky=W)

prefsbutton = ttk.Button(topbar, text='Preferences', command=prefs, 
    style='Toolbutton')
prefsbutton.grid(row=0, column=2, padx=5, sticky=W)

chkfrmbtn = ttk.Button(topbar, text='Check Missing Frames', 
    command=check_frames_window, style='Toolbutton')
chkfrmbtn.grid(row=0, column=3, padx=5, pady=5, sticky=W)

systatbtn = ttk.Button(topbar, text='System Stats', command=systat, 
    style='Toolbutton')
systatbtn.grid(row=0, column=4, padx=5, pady=5, sticky=W)

quitbutton = ttk.Button(topbar, text='Quit', command=quit, 
    style='Toolbutton')
quitbutton.grid(row=0, column=5, padx=5, pady=5, sticky=E)

jsonbutton = ttk.Button(topbar, text='Export JSON', command=export_json, 
    style='Toolbutton')
jsonbutton.grid(row=0, column=6, padx=6, pady=6, sticky=E)



container = LabelFrame(root, bg='white')
container.grid(row=1, column=0, padx=10)

jobstatFrame = LabelFrame(container, width=685, bd=0)
jobstatFrame.grid(row=0, padx=5, pady=5, sticky=N+W)
#lambda b/c input_window does not take an event arg
container.bind('<Control-n>', lambda x: input_window()) 
#alt keybinding for OSX
container.bind('<Command-n>', lambda x: input_window()) 


#lists of widget names to simplify color change functions
jobstat_label_list = ['filenam_', 'startfram_', 'endfram_', 'extrafram_', 
    'vrule3_', 'vrule4_', 'vrule5_']
otherwidgets = ['statlight_', 'buttonframe_', 'timecanv_', 'perdone_']
buttons = ['editbutton_', 'startbutton_', 'stopbutton_', 'resumebutton_', 
    'removebutton_', 'spacer_']
timefields = ['totaltime_', 'avgframetime_', 'estremain_']

for i in renderJobs:
    jobstat = ClickFrame(jobstatFrame, name='jobstat_'+str(i), index=i)
    jobstat.grid(row=i, column=0, padx=0, pady=0)

    ClickCanvas(jobstat, name='statlight_'+str(i), width=121, height=21, 
        index=i, highlightthickness=0).grid(row=0, column=0, padx=0, sticky=W)

    NameHoverLabel(jobstat, name='filenam_'+str(i), text='', wraplength=130, 
        anchor=W, index=i).grid(row=0, column=1, padx=0, sticky=W)
    ClickLabel(jobstat, name='vrule3_'+str(i), text='|', width=1, anchor=W, 
        index=i).grid(row=0, column=2, padx=0)

    ClickLabel(jobstat, name='startfram_'+str(i), text='', anchor=W, 
        index=i).grid(row=0, column=3, padx=0, sticky=W)
    ClickLabel(jobstat, name='vrule4_'+str(i), text='|', width=1, anchor=W, 
        index=i).grid(row=0, column=4, padx=0)

    ClickLabel(jobstat, name='endfram_'+str(i), text='', anchor=W, 
        index=i).grid(row=0, column=5, padx=0, sticky=W)
    ClickLabel(jobstat, name='vrule5_'+str(i), text='|', width=1, anchor=W, 
        index=i).grid(row=0, column=6, padx=0)

    FramesHoverLabel(jobstat, name='extrafram_'+str(i), text='', 
        wraplength=150, anchor=W, index=i).grid(row=0, column=7, columnspan=2, 
        padx=0, sticky=W)

    timecanv = ClickCanvas(jobstat, name='timecanv_'+str(i), width=615, 
        height=20, highlightthickness=0, index=i)
    timecanv.grid(row=1, column=0, columnspan=8, sticky=W)
    timecanv.create_text(35, 10, text='Total time:')
    timecanv.create_text(240, 10, text='Avg/frame:')
    timecanv.create_text(448, 10, text='Remaining:')

    ClickProg(jobstat, length=500, variable=totalprog[i], index=i).grid(row=2, 
        column=0, columnspan=8, sticky=W)
    perdone = ClickCanvas(jobstat, width=110, height=20, name='perdone_'+str(i),
        index=i, highlightthickness=0)
    perdone.grid(row=2, column=7, sticky=E, padx=3) 
    perdone.create_text(55, 9, text='0% Complete')
    

    buttonframe = ClickFrame(jobstat, index=i, name='buttonframe_'+str(i), bd=0)
    buttonframe.grid(row=3, column=0, columnspan=8, sticky=W)
    DoubleButton(buttonframe, name='editbutton_'+str(i), text='New / Edit', 
        index=i, command=input_window).grid(row=0, column=0, sticky=W)
    DoubleButton(buttonframe, name='startbutton_'+str(i), text='Start', 
        index=i, command=startJob).grid(row=0, column=1, sticky=W)
    DoubleButton(buttonframe, name='stopbutton_'+str(i), text='Stop', index=i, 
        command=killJob).grid(row=0, column=2, sticky=W)
    DoubleButton(buttonframe, name='resumebutton_'+str(i), text='Resume', 
        index=i, command=resumeJob).grid(row=0, column=3, sticky=W)
    #spacer to push remove button to right
    ClickLabel(buttonframe, name='spacer_'+str(i), text='                                                     ', index=i).grid(row=0, column=4) 
    DoubleButton(buttonframe, name='removebutton_'+str(i), text='Remove Job', 
        index=i, command=removeJob).grid(row=0, column=5, sticky=E)

    


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

#container to control location of scrollbar
scrollcontainer = Frame(compstat) 
scrollcontainer.grid(row=1, column=0)

#height is reset in update() based on root window height.
canvas = Canvas(scrollcontainer, width=461, height=555, scrollregion=(0, 0, 
    461, 900), bg='white') 
vbar = Scrollbar(scrollcontainer, orient=VERTICAL)
vbar.pack(side=RIGHT, fill=Y)
vbar.config(command=canvas.yview)

canvas.config(yscrollcommand=vbar.set)

statframe = Frame(canvas, bg='white') #Holds status boxes 

for i in range(len(computers)): 

    statbox = LabelFrame(statframe, name=computers[i]+'_statbox')
    statbox.grid(row=i, column=0)

    compdata = Canvas(statbox, name=computers[i]+'_compdata', height=20, 
        width=355, highlightthickness=0) 
    compdata.grid(row=0, column=0, columnspan=3) #change row to 0 when done

    compdata.create_text(5, 10, anchor=W, text=computers[i])
    compdata.create_text(130, 10, anchor=W, text='Frame:')
    #framenumber placeholder
    compdata.create_text(180, 10, anchor=W, text='0000') 
    #percentage placeholder
    compdata.create_text(279, 10, anchor=E, text='100') 
    compdata.create_text(280, 10, anchor=W, text='% Complete')

    pbar = ttk.Progressbar(statbox, variable=progvars[computers[i]], length=350)
    pbar.grid(row=1, column=0, columnspan=3, padx=5, pady=5, sticky=W)

    togglebtn = ToggleCanv(statbox, name=computers[i]+'_togglebtn', height=40, 
        width=40, highlightthickness=0, bg='gray80', computer=computers[i])
    togglebtn.grid(row=0, rowspan=2, column=3, padx=5, pady=5)

    killbtn = KillCanv(statbox, name=computers[i]+'_killbtn', height=40, 
        width=40, highlightthickness=0, bg='gray80', computer=computers[i])
    killbtn.grid(row=0, rowspan=2, column=4, padx=5, pady=5)
    killbtn.create_rectangle(2, 2, 37, 37, outline='gray50', fill='gray90')
    killbtn.create_text(20, 20, text='Kill' )

statframe.pack()
canvas.create_window(0, 0, window=statframe, anchor=NW)
canvas.pack(side=LEFT, expand=True, fill=BOTH)

Frame(root).grid(row=2, column=0, pady=5) #spacer to pad bottom of window




set_job(1) #opens with the first queue slot active
update()
check_job_queue() 
root.mainloop()
