#Fifth major revison of IGP render controller
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

import queue
import threading
import time
import subprocess
import os
import socket
import shlex
import datetime
import re
import cfgfile
import projcache
import socketwrapper as sw

illegal_characters = [';', '&'] #not allowed in paths
class Job(object):
    '''Represents a render job.'''

    def __init__(self):
        #initialize all attrs for client updates
        self.status = 'Empty'
        self.queuetime = time.time()
        self.priority = 'Normal'
        self.starttime = None #time render() called
        self.stoptime = None #time masterthread stopped
        self.complist = []
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in Config.computers:
            self._reset_compstatus(computer)
        self.skiplist = []
        self.path = None
        self.startframe = None
        self.endframe = None
        self.extraframes = []
        self.render_engine = None
        self.totalframes = []
        self.progress = None
        self.cachedata = None #holds info related to local file caching
        self._id = None #unique job identifier for logging, 

    def _reset_compstatus(self, computer):
        '''Creates compstatus dict or resets an existing one to 
        default values'''
        with threadlock:
            self.compstatus[computer] = {
                'active':False, 'frame':None, 'pid':None, 'timer':None, 
                'progress':0.0, 'error':None
                }

    def get_job_progress(self):
        '''Returns the percent complete for the job.'''
        calcstatuses = ['Rendering', 'Stopped', 'Paused']
        if self.status in calcstatuses:
            n = 0
            for i in self.totalframes:
                if i != 0:
                    n += 1
            self.progress = float(n) / len(self.totalframes) * 100
        elif self.status == 'Finished':
            self.progress = 100.0
        else:
            self.progress = 0.0
        return self.progress

    def get_comp_status(self, computer):
        '''Returns the contents of self.compstatus for a given computer.'''
        return self.compstatus[computer]

    def enqueue(self, path, startframe, endframe, render_engine, complist, 
                extraframes=[], cachedata=None):
        '''Create a new job and place it in queue.'''
        #make sure path is properly shell-escaped
        self.path = shlex.quote(path)
        for char in illegal_characters:
            if char in path:
                return False
        #deal with relative paths (shlex.quote will escape the ~)
        #XXX Do this correctly using os.path.abspath when client is written
        if path[0] == '~':
            self.path = '~' + shlex.quote(path[1:])
        self._id_ = id(self)
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes

        self.render_engine = render_engine
        self.complist = complist
        #Fill list of total frames with zeros
        #used for tracking percent complete
        self.totalframes = []
        for i in range(self.startframe, self.endframe + 
                       len(self.extraframes) + 1):
            self.totalframes.append(0)
        #create LifoQueue and put frames
        #using Lifo (last-in-first-out) so that frames returned to queue b/c
        #of problems during render are reassigned first
        self.queue = queue.LifoQueue(0)
        framelist = list(range(self.startframe, self.endframe + 1))
        framelist.reverse()
        for frame in framelist:
            self.queue.put(frame)
        #render extraframes first, lowest number first
        #check again to make sure there are still extraframes
        if self.extraframes:
            self.extraframes.sort()
            self.extraframes.reverse()
            for frame in self.extraframes:
                self.queue.put(frame)
        #if project files will be cached locally on render nodes, set up cacher
        if cachedata:
            print('Request for projcache detected in enqueue()', cachedata)
            #XXX not sure if there's really any need to maintain both the
            #cachedata dict and the filecacher object.
            self.cachedata = cachedata
            self.filecacher = projcache.FileCacher(
                cachedata['rootpath'], cachedata['filepath'], 
                cachedata['renderdirpath'], cachedata['computers']
                )
            self.renderlog = RenderLog(
                self.path, self.startframe, self.endframe, self.extraframes, 
                self.complist, self._id_, caching=True
                )
        else:
            self.renderlog = RenderLog(
                self.path, self.startframe, self.endframe, self.extraframes, 
                self.complist, self._id_
                )
        self.status = 'Waiting'
        return True

    def render(self, time_offset=None):
        '''Starts a render for a given job.
        time_offset: correction factor in seconds used when restoring a 
        running job after server restart.'''
        self.prints(event='entered render()') #debug
        if self.status != 'Waiting':
            return False
        self.status = 'Rendering'
        self._start_timer(offset=time_offset)
        self.renderlog.start()

        self.killflag = False

        master = threading.Thread(target=self._masterthread, args=())
        master.start()
        return True

    def _masterthread(self):
        '''Main thread to control render process and create renderthreads.'''
        '''{'active':False, 'frame':None,
            'pid':None, 'timer':None, 'progress':0.0, 'error':None}'''
    
        self.prints('started _masterthread()')#debug
        self.threads_active = False
        #set target thread type based on render engine
        if self.render_engine == 'blend':
            tgt_thread = self._renderthread
        elif self.render_engine == 'tgd':
            tgt_thread = self._renderthread_tgn
        while True:
            if self.killflag:
                self.prints('Kill flag detected, breaking render loop.') #debug
                #deal with log & render timer
                break
    
            if self.queue.empty() and not self._threadsactive():
                self.prints('Render done at detector.') #debug
                self.status = 'Finished'
                self._stop_timer()
                self.renderlog.finished(self.get_times())
                if self.cachedata:
                    self.retrieve_cached_files()
                break

            #prevent lockup if all computers end up in skiplist
            if len(self.skiplist) == len(self.complist):
                #ignore if both lists are empty
                if not len(self.complist) == 0:
                    self.prints('All computers in skiplist, popping oldest '
                                'one')
                    skipcomp = self.skiplist.pop(0)
                    self._reset_compstatus(skipcomp)
    
            for computer in Config.computers:
                time.sleep(0.01)
                if not computer in self.complist:
                    continue

                elif (not self.compstatus[computer]['active'] and 
                        computer not in self.skiplist):
                    #break loop if queue becomes empty after computer added
                    if self.queue.empty():
                        break
                    else:
                        frame = self.queue.get()
                        with threadlock:
                            self.compstatus[computer]['active'] = True
                            self.compstatus[computer]['frame'] = frame
                            self.compstatus[computer]['timer'] = time.time()
                            self.threads_active = True
                            self.renderlog.frame_sent(frame, computer) 
                        self.prints('Creating renderthread')#debug
                        rthread = threading.Thread(
                            target=tgt_thread, args=(frame,  computer, 
                            self.queue)
                            )
                        rthread.start()
                #ignore computers in skiplist
                elif computer in self.skiplist:
                    continue
                #if computer is active, check its timeout status
                elif (time.time() - self.compstatus[computer]['timer'] > 
                        Config.timeout):
                    self._thread_failed(self.compstatus[computer]['frame'], 
                                       computer, 'Timeout')

        self.prints('_masterthread() terminating') #debug



    def _threadsactive(self):
        '''Returns true if instances of _renderthread() are active.'''
        for computer in self.compstatus:
            if self.compstatus[computer]['active']:
                return True
        self.prints('_threadsactive() returning false') #debug
        return False

    def _renderthread(self, frame, computer, framequeue):
        '''Thread to send command, montor status, and parse return data for a
        single frame in Blender's Cycles render engine.  NOTE: This will not
        parse output from Blender's internal engine correctly.'''

        self.prints('started _renderthread()', frame, computer)
        thread_start_time = datetime.datetime.now()
        if computer in Config.macs:
            renderpath = shlex.quote(Config.blenderpath_mac)
        else:
            renderpath = shlex.quote(Config.blenderpath_linux)
        command = subprocess.Popen(
            'ssh igp@' + computer + ' "' + renderpath +
             ' -b -noaudio ' + self.path + ' -f ' + str(frame) + 
             ' & pgrep -n blender"', stdout=subprocess.PIPE, shell=True )
        for line in iter(command.stdout.readline, ''):
            #convert byte object to unicode string
            #necessary for Python 3.x compatibility
            # Starting with Blender 2.76, having problems with unicode decoding errors
            # Not sure what's going on, but need to get things working
            try:
                line = line.decode('UTF-8')
                if not line:
                    #pipe broken, 
                    self._thread_failed(frame, computer, 'Broken pipe')
                    return
            except UnicodeDecodeError as e:
                print('Got the Unicode error: %s in line: %s' %(e, line))
                continue

            #reset timeout timer every time an update is received
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            if Config.verbose:
                with threadlock:
                    self.prints(line)
            #calculate progress based on tiles
            if line.find('Fra:') >= 0 and line.find('Tile') >0:
                match = re.search('Path Tracing Tile +?([0-9]+)\/([0-9]+)', line)
                if not match:
                    # Don't break if regex doesn't match
                    continue
                else:
                    tiles, total = match.group(1), match.group(2)
                    progress = int(tiles) / int(total) * 100
                    with threadlock:
                        self.compstatus[computer]['progress'] = progress
            #detect PID at first line
            elif line.strip().isdigit():
                pid = line.strip()
                self.prints('PID detected: %s' %pid, frame=frame, 
                            computer=computer)
                with threadlock:
                    self.compstatus[computer]['pid'] = pid
                if computer in Config.renice_list:
                    subprocess.call('ssh igp@' + computer + ' "renice 20 -p ' + 
                                     str(pid) + '"', shell=True)
                #remove oldest item from skiplist if render starts successfully
                with threadlock:
                    if len(self.skiplist) > 0:
                        skipcomp = self.skiplist.pop(0)
                        self._reset_compstatus(skipcomp)
            #detect if frame has finished rendering
            elif line.find('Saved:') >= 0:
                thread_end_time = datetime.datetime.now()
                # Subtracting two datetime objects returns a datetime.timedelta object
                # which can be converted to a string.  May do better formatting later.
                rendertime = str(thread_end_time - thread_start_time)
                self.totalframes.append(frame)
                if 0 in self.totalframes:
                    self.totalframes.remove(0)
                framequeue.task_done()
                self._reset_compstatus(computer)
                self.prints('Finished after %s' %rendertime, frame=frame, 
                          computer=computer)
                with threadlock:
                    self.renderlog.frame_recvd(frame, computer, rendertime)
                break
    
        #NOTE omitting stderr checking for now
        self.prints('_renderthread() terminated', frame=frame, 
                    computer=computer)

    def _renderthread_tgn(self, frame, computer, framequeue):
        '''Thread to send command, monitor status, and parse return data for a
        single frame in Terragen 3.'''

        print('started _renderthread_tgn()', frame, computer)
        #pgrep string is different btw OSX and Linux so using whole cmd strings
        if computer in Config.macs:
            cmd_string = (
                'ssh igp@%s "%s -p %s -hide -exit -r -f %s & pgrep -n '
                'Terragen&wait"' 
                %(computer, shlex.quote(Config.terragenpath_mac), self.path, 
                  frame)
                )
        else:
            cmd_string = (
                'ssh igp@%s "%s -p %s -hide -exit -r -f %s & pgrep -n '
                'terragen&wait"' 
                %(computer, shlex.quote(Config.terragenpath_linux), self.path, 
                  frame)
                )

        command = subprocess.Popen(cmd_string, stdout=subprocess.PIPE, 
                                   shell=True)

        for line in iter(command.stdout.readline, ''):
            line = line.decode('UTF-8')
            if not line:
                #pipe broken, 
                self._thread_failed(frame, computer, 'Broken pipe')
                return

            #reset timer
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            if Config.verbose:
                with threadlock:
                    self.prints(line)

            #starting overall render or one of the render passes
            if line.strip().isdigit():
                pid = int(line.strip())
                self.prints('Possible PID detected: %s' %pid, frame, computer)
                if pid != frame: 
                    #necessary b/c terragen echoes frame # at start. 
                    #Hopefully PID will never be same as frame #
                    self.prints('PID set to %s' %pid, frame, computer)
                    with threadlock:
                        self.compstatus[computer]['pid'] = pid
                    #renice process to lowest priority on specified comps 
                    if computer in Config.renice_list: 
                        subprocess.call('ssh igp@'+computer+' "renice 20 -p '
                                        +str(pid)+'"', shell=True)
                        self.prints('Reniced PID %s to pri 20' %pid, frame, 
                                  computer)
                    #remove oldest item from skiplist if render starts 
                    with threadlock:
                        if len(self.skiplist) > 0:
                            skipcomp = self.skiplist.pop(0)
                            self._reset_compstatus(skipcomp)
            #starting a new render pass
            elif line.find('Starting') >= 0:
                ellipsis = line.find('...')
                passname = line[9:ellipsis]
                self.prints('Starting %s' %passname, frame, computer)

            #finished one of the render passes
            elif line.find('Rendered') >= 0:
                mark = line.find('of ')
                passname = line[mark+3:]
                self.prints('Finished %s' %passname, frame, computer)

            elif line.find('Rendering') >= 0:
                #pattern 'Rendering pre pass... 0:00:30s, 2% of pre pass'
                #NOTE: terragen ALWAYS has at least 2 passes, so prog bars go
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
                self.prints('%s%% complete' %percent, frame, computer)
                with threadlock:
                    self.compstatus[computer]['progress'] = percent
            #frame is done rendering
            elif line.find('Finished') >= 0:
                self.totalframes.append(frame)
                if 0 in self.totalframes:
                    self.totalframes.remove(0)
                framequeue.task_done()
                self._reset_compstatus(computer)
                rendertime = str(line.split()[2][:-1])
                self.prints('Finished after %s' %rendertime, frame, computer)
                with threadlock:
                    self.renderlog.frame_recvd(frame, computer, rendertime)
                break
            #NOTE: omitting stderr testing for now
        self.prints('_renderthread_tgn() terminated', frame, computer)

    def _thread_failed(self, frame, computer, errortype):
        '''Handles operations associated with a failed render thread.'''
        #If pipe is broken because render was killed by user, don't
        #treat it as an error:
        #if self.compstatus[computer]['error'] == 'Killed':
        if not self.compstatus[computer]['active']:
            return
        self.prints('Failed to render, error type: %s' %errortype, 
                  frame, computer, error=True)
        self.skiplist.append(computer)
        with threadlock:
            self.queue.put(frame)
            self.compstatus[computer]['active'] = False
            self.compstatus[computer]['error'] = errortype
            self.renderlog.frame_failed(frame, computer, errortype)
        pid = self.compstatus[computer]['pid']
        #XXX Not sure if there should be an exemption for broken pipe here
        #b/c slow comptuers are having ssh issues and breaking pipes while
        #blender is still running (I think)
        #if pid and errortype != 'Broken pipe':
        if pid:
            self._kill_thread(computer, pid)

    def _kill_thread(self, computer, pid):
        '''Handles INTERNAL kill thread requests. Encapsulates kill command
        in separate thread to prevent blocking of main if ssh connection is
        slow.'''
        kthread = threading.Thread(target=self._threadkiller, 
                                   args=(computer, pid))
        kthread.start()
        with threadlock:
            self.renderlog.process_killed(pid, computer)

    def _threadkiller(self, computer, pid):
        '''Target thread to manage kill commands, created by _kill_thread'''
        self.prints('entered _threadklller(), pid: %s' %pid, computer=computer)
        subprocess.call('ssh igp@%s "kill %s"' %(computer, pid), shell=True)
        self.prints('finished _threadkiller()', computer=computer)

    def kill_thread(self, computer):
        '''Handles EXTERNAL kill thread requests.  Returns PID if 
        successful.'''
        try:
            pid = self.compstatus[computer]['pid']
            frame = self.compstatus[computer]['frame']
        except Exception as e:
            self.prints('Exception caught in Job.kill_thread() while getting '
                      'pid: %s' %e, computer=computer, error=True)
            return False
        if (pid == None or frame == None):
            self.prints('Job.kill_thread() failed, no frame or PID assigned', 
                      computer=computer)
            return False
        with threadlock:
            self.queue.put(frame)
        self._kill_thread(computer, pid)
        self._reset_compstatus(computer)
        self.prints('Finished Job.kill_thread()', computer=computer)
        return pid

    def _start_timer(self, offset=None):
        '''Starts the render timer for the job.
        offset: correction factor in seconds, used when restoring a running
        job after server restart.'''
        if offset:
            self.starttime = time.time() - offset
            print('Offsetting job start time by %s seconds') #debug
        if (self.status == 'Stopped' or self.status == 'Paused'):
            #account for time elapsed since render was stopped
            self.starttime = time.time() - (self.stoptime - self.starttime)
        else:
            self.starttime = time.time()

    def _stop_timer(self):
        '''Stops the render timer for the job.'''
        self.stoptime = time.time()

    def get_times(self):
        '''Returns elapsed time, avg time per frame, and estimated time 
        remaining. Units are float seconds.'''
        if not self.starttime:
            return (0, 0, 0)
        if self.status == 'Rendering':
            elapsed_time = time.time() - self.starttime
            frames_completed = 0
            for i in self.totalframes:
                if i != 0:
                    frames_completed += 1
            if frames_completed == 0:
                avg_time = 0
            else:
                avg_time = elapsed_time / frames_completed
            rem_time = avg_time * (len(self.totalframes) - frames_completed)
        else:
            elapsed_time = self.stoptime - self.starttime
            avg_time = elapsed_time / len(self.totalframes)
            rem_time = 0
        return (elapsed_time, avg_time, rem_time)

    def get_attrs(self):
        '''Returns dict containing all status-related attributes and times.'''
        attrdict = {
            'status':self.status,
            'queuetime':self.queuetime,
            'priority':self.priority,
            'starttime':self.starttime,
            'stoptime':self.stoptime,
            'complist':self.complist,
            'compstatus':self.compstatus,
            'path':self.path,
            'startframe':self.startframe,
            'endframe':self.endframe,
            'extraframes':self.extraframes,
            'render_engine':self.render_engine,
            'totalframes':self.totalframes,
            'progress':self.get_job_progress(),
            'times':self.get_times(),
            'cachedata':self.cachedata,
            '_id_':self._id_
            }
        return attrdict

    def add_computer(self, computer):
        #if self.compstatus[computer]['pool']:
        if computer in self.complist:
            return False
        else:
            #if project files are being cached locally, add computer to
            #cache list & transfer files if necessary
            if self.cachedata:
                if not computer in self.filecacher.computers:
                    self.prints('Added to filecacher computer list', 
                              computer=computer)
                    result = self.filecacher.cache_single(computer)
                    if result:
                        self.prints('Unable to transfer files: %s' %result, 
                                  computer=computer, error=True)
                        return False
                    #NOTE: FileCacher should add comp to its list automatically
                    self.cachedata['computers'].append(computer)
            self.complist.append(computer)
            if self.status == 'Rendering':
                with threadlock:
                    self.renderlog.computer_added(computer)
            return True

    def remove_computer(self, computer):
        if not computer in self.complist:
            return False
        else:
            self.complist.remove(computer)
            if computer in self.skiplist:
                self.skiplist.remove(computer)
            if self.status == 'Rendering':
                with threadlock:
                    self.renderlog.computer_removed(computer)
            return True

    def kill_now(self):
        '''Kills job and all currently rendering frames'''
        if not self.status == 'Rendering':
            return False
        self.killflag = True
        self._stop_timer()
        with threadlock:
            self.renderlog.stop(self.get_times())
        self.status = 'Stopped'
        for computer in Config.computers:
            try:
                if self.compstatus[computer]['active']:
                    self.kill_thread(computer)
            except Exception:
                pass
        return True

    def kill_later(self, finalstatus='Stopped'):
        '''Kills job but allows any currently rendering frames to finish.
        NOTE: Does not monitor progress of currently rendering frames, so 
        if they do not finish there will be missing frames, or if job is 
        immediately resumed there may be multiple render processes running 
        on each computer until the old frames finish.

        The finalstatus attribute can be used to pass a special status
        (i.e. 'Paused') to be assigned when the function is complete.'''
        if not self.status == 'Rendering':
            return False
        self.killflag = True
        self._stop_timer()
        with threadlock:
            self.renderlog.stop(self.get_times())
        self.status = finalstatus
        return True

    def resume(self, startnow=True):
        '''Resumes a render that was previously stopped. If startnow == False,
        render will be placed in queue with status 'Waiting' but not 
        started.'''
        if not (self.status == 'Stopped' or self.status == 'Paused'):
            return False
        self.killflag = False
        for computer in Config.computers:
            self._reset_compstatus(computer)
        self.status = 'Waiting'
        if startnow:
            self.render()
            return True
        else:
            return True

    def autostart(self):
        '''Handles starting the current job from the check_autostart 
        function.'''
        if self.status == 'Waiting':
            self.render()
        else:
            self.status = 'Stopped'
            self.resume(startnow=True)

    def set_priority(self, priority):
        if priority == self.priority:
            return False
        self.priority = priority
        return True

    def set_attrs(self, attrdict):
        '''Sets all attributes for an instance of Job. Used for restoring
        a session following a server restart or crash.'''
        self.status = attrdict['status']
        self.queuetime = attrdict['queuetime']
        self.priority = attrdict['priority']
        self.starttime = attrdict['starttime']
        self.stoptime = attrdict['stoptime']
        self.complist = attrdict['complist']
        self.compstatus = attrdict['compstatus']
        self.path = attrdict['path']
        self.startframe = attrdict['startframe']
        self.endframe = attrdict['endframe']
        self.render_engine = attrdict['render_engine']
        self.totalframes = attrdict['totalframes']
        times = attrdict['times']
        self.cachedata = attrdict['cachedata']
        self._id_ = attrdict['_id_']
        #create new entries if list of available computers has changed
        #new computers added
        added = [comp for comp in Config.computers if not 
                 comp in self.compstatus]
        if added:
            for comp in added:
                self._reset_compstatus(comp)
                self.prints('New computer available, creating compstatus '
                            'entry', computer=comp)
        #any computers no longer available
        removed = [comp for comp in self.compstatus if not
                   comp in Config.computers]
        if removed:
            for comp in removed:
                if comp in self.complist:
                    self.complist.remove(comp)
                self.prints('Computer in compstatus no longer available. '
                            'removing compstatus entry.', computer=comp)
        if self.cachedata:
            self.filecacher = projcache.FileCacher(
                self.cachedata['rootpath'], self.cachedata['filepath'], 
                self.cachedata['renderdirpath'], 
                self.cachedata['computers']
                )
        if not self.status == 'Finished':
            self.queue = queue.LifoQueue(0)
            framelist = list(range(self.startframe, self.endframe + 1))
            framelist.reverse()
            if self.extraframes:
                framelist.extend(extraframes)
            for frame in framelist:
                if frame in self.totalframes:
                    framelist.remove(frame)
                else:
                    self.queue.put(frame)
            self.prints('Restoring job with frames: %s' %framelist)
            self.renderlog = RenderLog(
                self.path, self.startframe, self.endframe, 
                self.extraframes, self.complist, self._id_
                )

        if self.status == 'Rendering':
            self.prints('Attempting to start')
            #determine time offset to give correct remaining time estimate
            elapsed = times[0]
            for computer in Config.computers:
                self._reset_compstatus(computer)
            self.status = 'Waiting'
            self.render(time_offset=elapsed)
        return True

    def retrieve_cached_files(self):
        '''Attempts to copy rendered frames from the rendercache directory
        on each render node back to the shared directory on the server.'''
        self.prints('Attempting to retrieve rendered frames from local '
                  'rendercahes')
        if not self.cachedata:
            return 'Caching not enabled'
        result = self.filecacher.retrieve_all()
        if result:
            #errors were received in a list of tuples, print it neatly
            print('Errors reported:')
            for i in result:
                print('%s returned non-zero exit status %s' %i)
            #XXX Need way to report this to GUI
            #XXX removed renderlog stuff b/c it was causing issues.
            return result
        else:
            #print('Cached frames successfully retrieved.')
            self.prints('Cached frames successfully retrieved')
            return 0

    def gettime(self):
        '''Returns current time as string formatted for timestamps.'''
        timestamp = time.strftime('%H:%M:%S on %Y/%m/%d', time.localtime())
        return timestamp

    def prints(self, event, frame=None, computer=None, error=False):
        '''Writes info about a status change event to stdout.'''
        if error:
            errstr = 'ERROR:'
        else:
            errstr = ''
        if frame and computer:
            print('%s%s| %s | Fra:%s | %s | %s' 
                  %(errstr, self._id_, computer, frame, event, self.gettime()))
        elif computer:
            print('%s%s| %s | %s | %s' %(errstr, self._id_, computer, 
                  event, self.gettime()))
        else:
            print('%s%s| %s | %s' %(errstr, self._id_, event, self.gettime()))

    def getstatus(self):
        return self.status


class RenderLog(Job):
    '''Logs render progress for a given job.  Log instance is created when
    job is placed in queue, but actual log file is not created until render
    is started. Time in filename reflects time job was placed in queue.'''
    hrule = '=' * 70 + '\n' #for printing thick horizontal line
    def __init__(self, path, startframe, endframe, extraframes, complist, 
                 _id_, caching=False):
        self.path = path
        self._id_ = _id_ #object ID of the parent Job() instance
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes
        self.complist = complist
        self.caching = caching #indicates if files are cached on render nodes
        self.log_basepath = Config.log_basepath
        self.filename, ext = os.path.splitext(os.path.basename(self.path))
        self.enq_time = time.strftime('%Y-%m-%d_%H%M%S', time.localtime())
        self.logpath = (self.log_basepath + self.filename + '.' 
                        + self.enq_time + '.txt')
        self.total = str(len(range(startframe, endframe)) + 1 + 
                         len(extraframes))

    def start(self):
        '''Creates initial entry corresponding to render start.'''
        #check if file exists. If so, assume render is being resumed
        if os.path.exists(self.logpath):
            self._resume()
            return
        with open(self.logpath, 'w') as log:
            log.write(RenderLog.hrule)
            log.write('Render started at ' + self.gettime() + '\n')
            log.write('File: ' + self.path + '\n')
            log.write('Frames: ' + str(self.startframe) + ' - ' 
                      + str(self.endframe) + ', ' + str(self.extraframes) 
                      + '\n')
            log.write('On: ' + ', '.join(self.complist) + '\n')
            log.write('Job ID: %s\n' %self._id_)
            if self.caching:
                log.write('Local file caching enabled \n')
            log.write(RenderLog.hrule)

    def frame_sent(self, frame, computer):
        with open(self.logpath, 'a') as log:
            log.write('Sent frame ' + str(frame) + ' of ' + self.total + ' to '
                      + computer + ' at ' + self.gettime() + '\n')

    def frame_recvd(self, frame, computer, rendertime):
        with open(self.logpath, 'a') as log:
            log.write('Received frame ' + str(frame) + ' of ' + self.total 
                      + ' from ' + computer + ' at ' + self.gettime() + 
                      '. Render time was ' + rendertime + '\n')

    def frame_failed(self, frame, computer, errtxt):
        with open(self.logpath, 'a') as log:
            log.write('ERROR: Frame ' + str(frame) + ' failed to render on ' 
                      + computer + ' at ' + self.gettime() + ': ' + errtxt 
                      + '\n')

    def process_killed(self, pid, computer):
        with open(self.logpath, 'a') as log:
            log.write('Killed process ' + str(pid) + ' on ' + computer + ' at '
                      + self.gettime() + '\n')

    def computer_added(self, computer):
        with open(self.logpath, 'a') as log:
            log.write('Added ' + computer + ' to render pool at ' 
                      + self.gettime() + '\n')

    def computer_removed(self, computer):
        with open(self.logpath, 'a') as log:
            log.write('Removed ' + computer + ' from render pool at ' 
                      + self.gettime() + '\n')

    def finished(self, times):
        '''Marks render finished, closes log file.'''
        elapsed, avg, rem = times
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render finished at ' + self.gettime() + '\n')
            log.write('Total time: ' + self.format_time(elapsed) + '\n')
            log.write('Average time per frame: ' + self.format_time(avg) + 
                      '\n')
            log.write(RenderLog.hrule)

    #XXX Not currently used
    def XXXframes_retrieved(self, computers, error=None):
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Attempted to retrieve locally cached frames at %s\n'
                      %self.gettime())
            if not error:
                log.write('No errors reported.\n')
            else:
                log.write('Received the following error(s): %s\n' %error)
            log.write('Final computer list: %s\n' %computers)
            log.write(RenderLog.hrule)

    def stop(self, times):
        '''Marks render stopped, closes log file.'''
        elapsed, avg, rem = times
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render stopped by user at ' + self.gettime() + '\n')
            log.write('Total time: ' + self.format_time(elapsed) + '\n')
            log.write('Average time per frame: ' + self.format_time(avg) + 
                      '\n')
            log.write(RenderLog.hrule)

    def _resume(self):
        '''Appends a new header to the existing log file.  If the server was
        shut down in the interim, a new file will be created.'''
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render resumed at ' + self.gettime() + '\n')
            log.write('File: ' + self.path + '\n')
            log.write('Frames: ' + str(self.startframe) + ' - ' 
                      + str(self.endframe) + ', ' + str(self.extraframes) 
                      + '\n')
            log.write('On: ' + ', '.join(self.complist) + '\n')
            log.write(RenderLog.hrule)

    def server_shutdown(self):
        '''Writes message to log if the server is manually shut down while
        unfinished jobs are still in queue.'''
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Server shut down at ' + self.gettime() + '\n')
            log.write('If server is restarted and this render is resumed,\n'
                      'a new log file will be created.\n') 
            log.write(RenderLog.hrule)

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
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m '
                +str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h ' + 
                       str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr


def quit():
    '''Forces immediate exit without waiting for loops to terminate.'''
    os._exit(1)


#----------GLOBAL VARIABLES----------
threadlock = threading.RLock()

#----------DEFAULTS / CONFIG FILE----------
class Config(object):
    '''Object to hold global configuration variables as class attributes.'''
    def __init__(self):
        self.cfg = cfgfile.ConfigFile()
        if not self.cfg.exists():
            print('No config file found, creating one from default values.')
            cfgsettings = self.cfg.write(self.defaults())
        else:
            print('Config file found, reading...')
            try:
                cfgsettings = self.cfg.read()
                if not len(cfgsettings) == len(self.defaults()):
                    raise IndexError
            #any exception should result in creation of new config file
            except Exception:
                print('Config file corrupt or incorrect. Creating new')
                cfgsettings = self.cfg.write(self.defaults())
        self.set_class_vars(cfgsettings)

    def set_class_vars(self, settings):
        '''Defines the class variables from a tuple formatted to match
        the one returned by getall().  Paths are escaped at the time
        of use so no need to do it here.'''
        (
        Config.computers, Config.renice_list, Config.macs, 
        Config.blenderpath_mac, Config.blenderpath_linux, 
        Config.terragenpath_mac, Config.terragenpath_linux, 
        Config.allowed_filetypes, Config.timeout, Config.serverport,
        Config.autostart, Config.verbose, Config.log_basepath
        ) = settings

    def getall(self):
        '''Returns tuple of all class variables. Used by clients to retrieve
        server config info.'''
        return (Config.computers, Config.renice_list, Config.macs, 
                Config.blenderpath_mac, Config.blenderpath_linux, 
                Config.terragenpath_mac, Config.terragenpath_linux, 
                Config.allowed_filetypes, Config.timeout, Config.serverport,
                Config.autostart, Config.verbose, Config.log_basepath)

    def update_cfgfile(self, settings):
        '''Updates the config file and sets class variables based on a tuple
        formatted to match getall().  Used by clients to change server
        config settings.'''
        self.cfg.write(settings)
        self.set_class_vars(settings)
        print('Wrote changes to config file.')

    def defaults(self):
        '''Restores all config file variables to default values. Also used
        for creating the initial config file.'''
        #create list of all computers available for rendering
        computers = [ 
            'hex1', 'hex2', 'hex3', 'borg1', 'borg2', 'borg3', 'borg4', 'borg5',
            'grob1', 'grob2', 'grob3', 'grob4', 'grob5', 'grob6', 'eldiente', 
            'lindsey', 'paradox', 'conundrum', 'gorgatron'
            ] 
        #list of computer to renice processes to lowest priority. 
        renice_list = ['conundrum', 'paradox'] 
        #computers running OSX. Needed because blender uses different path
        macs = ['conundrum', 'paradox'] 
        blenderpath_mac = "/Applications/blender.app/Contents/MacOS/blender" 
        blenderpath_linux = "/usr/local/bin/blender" 
        terragenpath_mac = (
            "/mnt/data/software/terragen_rendernode/osx/Terragen 3.app"                         "/Contents/MacOS/Terragen 3"
            )
        terragenpath_linux = (
            "/mnt/data/software/terragen_rendernode/linux/terragen"
            )
        #allowed file extensions (last 3 chars only) for check_missing_files
        allowed_filetypes = [
            '.png', '.jpg', '.peg', '.gif', '.tif', '.iff', '.exr', '.PNG', 
            '.JPG', '.PEG', '.GIF', '.TIF', '.IFF', '.EXR'] 
        #timeout for failed machine in seconds
        timeout = 1000
        #default server port number
        serverport = 2020
        #start next job when current one finishes.
        autostart = 1 
        verbose = 0
        #default directory to hold render log files
        log_basepath = "/mnt/data/renderlogs/"
    
        return (
            computers, renice_list, macs, blenderpath_mac, blenderpath_linux, 
            terragenpath_mac, terragenpath_linux, allowed_filetypes, timeout, 
            serverport, autostart, verbose, log_basepath
            ) 








#----------SERVER INTERFACE----------


allowed_commands= [
'get_attrs', 'job_exists', 'enqueue',
'start_render', 'toggle_comp', 'kill_single_thread', 'kill_render',
'get_status', 'resume_render', 'clear_job', 'get_config_vars', 'create_job',
'toggle_verbose', 'toggle_autostart', 'check_path_exists', 'set_job_priority',
'update_server_cfg', 'restore_cfg_defaults', 'killall',
'cache_files', 'retrieve_cached_files', 'clear_rendercache'
]


class RenderServer(object):
    '''This is the master class for this module. Instantiate this class to
    start a server. The Job class and its methods can be used directly 
    without a RenderServer instance, however an instance of Config MUST be 
    created first to define the global configuration variables on which 
    Job's methods depend.'''
    def __init__(self, port=None):
        #read config file & set up config variables
        self.conf = Config()
        if not port:
            port = Config.serverport
        if not self._check_logpath():
            return
        self.renderjobs = {}
        self.waitlist = [] #ordered list of jobs waiting to be rendered
        self.msgq = queue.Queue() #queue for misc. messages to clients
        self._check_restore_state()
        self.updatethread = threading.Thread(target=self.update_loop)
        self.updatethread.start()
        self.server = sw.Server(self, port, allowed_commands)
        self.server.start()
        self.shutdown_server()
    

    def _check_logpath(self):
        #look for the renderlog base path and verify it's accessible
        if not os.path.exists(Config.log_basepath):
            print('WARNING: Path to renderlog directory: "' + 
                    Config.log_basepath +'" could not be found.')
            if input('Do you want to specify a new path now? (Y/n): ') == 'Y':
                Config.log_basepath = input('Path:')
                if not os.path.exists(Config.log_basepath):
                    print('Path does not exist, shutting down server.')
                    quit()
                elif Config.log_basepath[-1] != '/':
                    Config.log_basepath = Config.log_basepath + '/'
                print('Render logs will be stored in ' + Config.log_basepath + 
                      '.\nTo permanently change the log path, use the '
                      'Preferences window in the client GUI or edit the '
                      'server config file.')
                return True
            else:
                print('Server start failed, no renderlog path.')
                return False
        else:
            print('Renderlog directory found')
            return True

    def update_loop(self):
        '''Handles miscellaneous tasks that need to be carried out on a 
        regular interval. Runs in separate thread to prevent blocking other 
        processes.'''
        self.stop_update_loop = False
        print('started update_loop')
        while not self.stop_update_loop:
            #run tasks every 20 seconds, but subdivide loop into smaller
            #units so it's immediately interruptable when server shuts down.
            #waits for 0.5 sec 40 times on each pass
            for i in range(40):
                time.sleep(0.5)
                if self.stop_update_loop:
                    break
            self.save_state()
            if Config.autostart:
                self.check_autostart()
        print('update_loop done')
        self.shutdown_server()

    def shutdown_server(self):
        '''Saves the server state then shuts it down cleanly.'''
        #shut down the update loop
        self.stop_update_loop = True
        #check for any unfinished jobs, note the shutdown in their logs
        log_statuses = ['Rendering', 'Stopped', 'Paused']
        for i in self.renderjobs:
            if self.renderjobs[i].status in log_statuses:
                self.renderjobs[i].renderlog.server_shutdown()
        print('Saving server state')
        self.save_state()
        print('Done')
        quit()

    def check_autostart(self):
        #handle high priority renders
        times = {}
        for i in self.renderjobs:
            job = self.renderjobs[i]
            if job.priority == 'High':
                if job.status == 'Rendering':
                    #nothing else needs to be done on this pass
                    return
                elif job.status == 'Waiting':
                    times[job.queuetime] = job
        if times:
            print('High priority render detected.')
            #kill all active renders
            for i in self.renderjobs:
                job = self.renderjobs[i]
                if job.status == 'Rendering':
                    print('Pausing', job.path)
                    job.kill_later(finalstatus='Paused')
                    self.waitlist.insert(0, job)
            newjob = times[min(times)]
            newjob.autostart()
            print('Started', newjob.path)
            return

        #if there are no waiting jobs, no reason to continue
        if not self.waitlist:
            return
        
        #if no high priority jobs, handle the normal ones
        activejobs = []
        for i in self.renderjobs:
            job = self.renderjobs[i]
            if job.status == 'Rendering':
                activejobs.append(job)
        if len(activejobs) > 1:
            print('Autostart: more than 1 active job found, returning')#debug
            return
        elif len(activejobs) == 0:
            newjob = self.waitlist.pop(0)
            newjob.autostart()
            print('Autostart started', newjob.path)
            return
        elif len(activejobs) == 1:
            job = activejobs[0]
            if job.queue.empty():
                #All frames distributed, just waiting for render to finish.
                #If one frame is taking inordinately long, don't want to wait
                #to start the next render.
                print('Autostart: exactly 1 job running & queue empty')#debug
                if job.totalframes.count(0) > 1:
                    print('Autostart: >1 frame rendering, returning')#debug
                    return
                else:
                    print('Autostart: exactly 1 frame rendering, starting next'
                         )#debug
                    newjob = self.waitlist.pop(0)
                    newjob.autostart()
                    print('Autostart started', newjob.path)
                pass
            else:
                return

    def save_state(self):
        '''Writes the current state of all Job instances on the server
        to a file. Used for restoring queue contents and server state in
        case the server crashes or needs to be restarted.  The update_loop
        method periodically calls this function whenever the server is 
        running.'''
        statevars = {'verbose':Config.verbose, 'autostart':Config.autostart}
        jobs = {}
        for index in self.renderjobs:
            jobs[index] = self.renderjobs[index].get_attrs()
        serverstate = [statevars, jobs]
        savefile = cfgfile.ConfigFile(filename='serverstate.json')
        savefile.write(serverstate)
    
    def _check_restore_state(self):
        '''Checks for an existing serverstate.json file in the same directory
        as this file. If found, prompts the user to restore the server state
        from the file. If yes, loads the file contents and attempts to
        create new Job instances with attributes from the file. Can only
        be called at startup to avoid overwriting exiting Job instances.'''
        savefile = cfgfile.ConfigFile(filename='serverstate.json')
        if savefile.exists():
            if not input('Saved state file found. Restore previous server '
                         'state? (Y/n): ') == 'Y':
                print('Discarding previous server state')
                return
            (statevars, jobs) = savefile.read()
            #restore state variables
            Config.verbose = statevars['verbose']
            Config.autostart = statevars['autostart']
            #restore job queue
            for index in jobs:
                self.renderjobs[index] = Job()
                reply = self.renderjobs[index].set_attrs(jobs[index])
                if reply:
                    print('Restored job ', index)
                    #add job to waitlist if necessary
                    status = jobs[index]['status']
                    if (status == 'Waiting' or status == 'Paused'):
                        self.waitlist.append(self.renderjobs[index])
                        print('added %s to waitlist' %index)
                else:
                    print('Unable to restore job ', index)
            print('Server state restored')

    def get_attrs(self, index=None):
        '''Returns dict of attributes for a given index. If no index is 
        specified, returns a dict containing key:dictionary pairs for every 
        job instance on the server where key is the job's index and the 
        dict contains all of its attributes.
    
        Also if no index is specified, an entry called __STATEVARS__ will be 
        appended that contains non-job-related information about the server 
        state that needs to be updated in client GUI regularly.'''

        '''If there are any outgoing messages waiting in self.msgq, they will
        be sent to the client, but will only be removed from the queue if
        the client id matches the intended recipient of the message.'''
        if index:
            if not index in self.renderjobs:
                return 'Index not found.'
            else:
                attrdict = self.renderjobs[index].get_attrs()
                return attrdict
        #if no index specified, send everything
        attrdict = {}
        for i in self.renderjobs:
            attrdict[i] = self.renderjobs[i].get_attrs()
        #append non-job-related update info
        attrdict['__STATEVARS__'] = {'autostart':Config.autostart, 
                               'verbose':Config.verbose}
        if not self.msgq.empty():
            attrdict['__MESSAGE__'] = self.msgq.get()
            self.msgq.task_done()
            #XXX need to get client ID and put messages back in queue if 
            #they don't match
        else:
            attrdict['__MESSAGE__'] = None
        return attrdict
    
    def job_exists(self, index):
        '''Returns True if index is in self.renderjobs.'''
        if index in self.renderjobs:
            return True
        else:
            return False
    
    def enqueue(self, kwargs):
        '''Enqueue a job from client.'''
        index = kwargs['index']
        path = kwargs['path']
        for char in illegal_characters:
            if char in path:
                return 'Enqueue failed, illegal characters in path'
        #NOTE: path is also escaped by shlex.quote() in Job.enqueue
        startframe = kwargs['startframe']
        endframe = kwargs['endframe']
        extras = kwargs['extraframes']
        render_engine = kwargs['render_engine']
        complist = kwargs['complist']
        cachedata = kwargs['cachedata']
        #create the job
        if index in self.renderjobs:
            if self.renderjobs[index].getstatus() == 'Rendering':
                return ('Enqueue failed, job with same index is currently '
                       'rendering.')
        #place it in queue
        self.renderjobs[index] = Job()
        #put it in ordered list of waiting jobs
        self.waitlist.append(self.renderjobs[index])
        success = self.renderjobs[index].enqueue(
            path, startframe, endframe, render_engine, complist, 
            extraframes=extras, cachedata=cachedata
            )
        if success:
            return (index + ' successfully placed in queue')
        else:
            del self.renderjobs[index]
            return 'Enqueue failed, job deleted'
    
    def start_render(self, index):
        '''Start a render at the request of client.'''
        reply = self.renderjobs[index].render()
        #remove job from waitlist
        self.waitlist.remove(self.renderjobs[index])
        if reply:
            return index + ' render started'
        else:
            return 'Failed to start render.'
    
    def toggle_comp(self, index, computer):
        if not computer in Config.computers:
            return 'Computer "%s" not recognized.' %computer
        #if self.renderjobs[index].get_comp_status(computer)['pool']:
        if computer in self.renderjobs[index].complist:
            reply = self.renderjobs[index].remove_computer(computer)
            if reply: return (computer+' removed from render pool for ' + 
                              str(index))
        else:
            reply = self.renderjobs[index].add_computer(computer)
            if reply: return computer+ ' added to render pool for '+str(index)
        return 'Failed to toggle computer status.'
    
    def kill_single_thread(self, index, computer):
        #first remove computer from the pool
        remove = self.renderjobs[index].remove_computer(computer)
        kill = self.renderjobs[index].kill_thread(computer)
        #remove computer
        if kill:
            pid = kill
            rstr = 'Sent kill signal for %s' %pid
            if remove:
                rstr += ', %s removed from render pool' %computer
            else:
                rstr += ', unable to remove %s from render pool.' %computer
            #return 'Sent kill signal for pid '+str(pid)+' on '+computer
        else:
            #return 'Failed to kill thread.'
            rstr = 'Failed to kill thread'
            if remove:
                rstr += ', removed %s from render pool.' %computer
            else:
                rstr += ', unable to remove %s from render pool.' %computer
        return rstr
    
    def kill_render(self, index, kill_now):
        if kill_now:
            reply = self.renderjobs[index].kill_now()
            if reply:
                return ('Killed render and all associated processes for %s'
                        %index)
        else:
            reply = self.renderjobs[index].kill_later()
            if reply:
                return ('Killed render of '+str(index)+' but all '
                        'currently-rendering frames will be allowed '
                        'to finish.')
        return 'Failed to kill render for job '+str(index)
    
    def resume_render(self, index, startnow):
        reply = self.renderjobs[index].resume(startnow)
        #if render is not to be started immediately, add it to the waitlist
        if reply and not startnow:
            self.waitlist.append(self.renderjobs[index])
        if reply:
            return 'Resumed render of ' + str(index)
        else:
            return 'Failed to resume render of ' + str(index)
    
    def get_status(self, index):
        '''Returns status string for a given job.'''
        return self.renderjobs[index].getstatus()
    
    def clear_job(self, index):
        '''Clears an existing job from a queue slot.'''
        job = self.renderjobs[index]
        if self.renderjobs[index] in self.waitlist:
            self.waitlist.remove(self.renderjobs[index])
        del self.renderjobs[index]
        return index + ' deleted.'
    
    def get_config_vars(self):
        '''Gets server-side configuration variables and returns them as 
        a list.'''
        cfgvars = self.conf.getall()
        return cfgvars
    
    def toggle_verbose(self):
        '''Toggles the state of the verbose variable.'''
        if Config.verbose == 0:
            Config.verbose = 1
            print('Verbose reporting enabled')
            return 'verbose reporting enabled'
        else:
            Config.verbose = 0
            print('Verbose reporting disabled')
            return 'verbose reporting disabled'
    
    def toggle_autostart(self):
        '''Toggles the state of the autostart variable.'''
        if Config.autostart == 0:
            Config.autostart = 1
            return 'autostart enabled'
            print('Autostart enabled')
        else:
            Config.autostart = 0
            print('Autostart disabled')
            return 'autostart disabled'
    
    def check_path_exists(self, path):
        '''Checks if a path is accessible from the server (exists) and that 
        it's an regular file. Returns True if yes.'''
        #if os.path.exists(path) and os.path.isfile(path):
        #XXX No longer checking that path is to a file b/c also need to check
        #for the root project directory if file caching is turned on.
        #This might create a security problem.
        if os.path.exists(path):
            return True
        else:
            return False
    
    def set_job_priority(self, index, priority):
        '''Sets the render priority for a given index.'''
        if not index in self.renderjobs:
            return 'Index not found'
        if self.renderjobs[index].set_priority(priority):
            return 'Priority of ' + index + ' set to ' + str(priority)
        else:
            return 'Priority not changed'

    def update_server_cfg(self, settings):
        '''Updates server config variables and config file based on tuple 
        from client.'''
        Config().update_cfgfile(settings)
        return 'Server settings updated'

    def restore_cfg_defaults(self):
        '''Resets server config variables to default values and overwrites
        the config file.'''
        cfgsettings = Config().defaults()
        Config().update_cfgfile(cfgsettings)
        return 'Server settings restored to defaults'

    def killall(self, complist, procname):
        '''Attempts to kill all instances of the given processess on the
        given machines.'''
        # First make sure that everything is OK
        for comp in complist:
            if not comp in Config.computers:
                return 'Killall failed. Computer %s not recognized.' %comp
        if not procname in ['blender', 'terragen']:
            return 'Process name %s not recognized.' %procname
        SSHKillThread(complist, self.msgq, procname)
        return 'Attempting to kill %s on %s' %(procname, complist)

    def cache_files(self, cachedata):
        '''Transfers project files to local rendercache directories on each
        render node.'''
        
        #NOTE: paths are escaped with shlex.quote in filecacher
        cacher = projcache.FileCacher(
            cachedata['rootpath'], cachedata['filepath'], 
            cachedata['renderdirpath'], cachedata['computers']
            )
        if not cachedata['computers']:
            return 'Cache data stored but no computer list specified.'
        else:
            result = cacher.cache_all()
        if result:
            return 'Cache returned the following errors: %s' %result
        else:
            return 'Files cached without errors.'

    def retrieve_cached_files(self, index):
        '''Attempts to retrieve rendered frames from local storage for an
        existing job.'''
        if not index in self.renderjobs:
            return '%s not found on server' %index
        job = self.renderjobs[index]
        result = job.retrieve_cached_files()
        if result:
            return result
        else:
            return 0

    def clear_rendercache(self):
        '''Attempts to delete the contents of the ~/rendercache directory on
        all computers.'''
        errors = []
        for computer in Config.computers:
            try:
                subprocess.check_output('ssh igp@%s "rm -rf ~/rendercache/*"' 
                                        %computer, shell=True)
            except Exception as e:
                errors.append(e)
        if errors:
            return ('Clear rendercache returned the following errors: %s' 
                    %errors)
        else:
            return 'Clear rendercache finished without errors.'




class SSHKillThread(object):
    '''Sends kill commands by ssh to specified hostnames. Returns a 
    success or failure message via the msgqueue parameter. Any errors
    or other information generated by worker threads will be appended
    to that message, i.e. this will add one and only one item to the
    msgqueue.'''

    def __init__(self, complist, msgqueue, procname):
        '''complist: list of hostnames or ip addresses
        msgqueue: queue.Queue object to return result to parent object
        procname: process name to be killed (case insensitive)'''
        self.compq = queue.Queue() #job queue for child processes
        self.replyq = queue.Queue() #queue for replies from child processes
        for comp in complist:
            self.compq.put(comp)
        threads = range(len(complist))
        mt = threading.Thread(target=self.master, 
            args=(threads, msgqueue, procname))
        mt.daemon = True
        mt.start()
        print('killall master started, __init__ done')

    def master(self, workers, msgqueue, procname):
        '''Creates worker threads and waits for them to finish.
        workers: number of worker threads to create'''
        for i in workers:
            comp = self.compq.get()
            t = threading.Thread(target=self.worker, args=(comp, procname))
            t.daemon = True
            t.start()
        self.compq.join()
        print('join released')
        if self.replyq.empty():
            msgqueue.put('success')
            return
        else:
            replies = []
            while not self.replyq.empty():
                replies.append(self.replyq.get())
            print('replies: %s' %replies)
            msgqueue.put(replies)
        print('killall master done')

    def worker(self, comp, procname):
        print('killall thread for %s started' %comp)
        if comp in Config.macs and procname == 'terragen':
            procname = "'Terragen 3'"
        print('procname is ', procname)
        cmd = 'ssh igp@%s "pgrep %s | xargs kill"' %(comp, procname)
        #NOTE: By piping pgrep directly to xargs, no exception will be raised
        # if there are no procname processes running on the computer.
        try:
            result = subprocess.check_output(cmd, shell=True)
        except Exception as e:
            self.replyq.put('Exception %s on %s' %(e, comp))
            self.compq.task_done()
            return
        if result:
            self.replyq.put('%s returned %s' %(comp, result))
        self.compq.task_done()




    


if __name__ == '__main__':
    server = RenderServer()
