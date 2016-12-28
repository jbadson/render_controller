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
import yaml
import json
import logging
import socketwrapper as sw


#XXX Does not quite work because we can't add file handler after the fact. Make global logger from start
logger = logging.getLogger('rcontroller.server')
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
file_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')
console_formatter = logging.Formatter('%(levelname)s %(name)s: %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S')
console.setFormatter(console_formatter)
logger.addHandler(console)

illegal_characters = [';', '&'] #not allowed in paths

class Job(object):
    '''Represents a render job.'''

    def __init__(self, _id=None):
        if _id:
            self._id = _id
        else:
            self._id = id(self)
        self.logger = logging.getLogger('rcontroller.server.Job.{}'.format(self._id))
        #initialize all attrs for client updates
        self.status = 'Empty'
        self.queuetime = time.time()
        self.priority = 'Normal'
        self.starttime = None #time render() called
        self.stoptime = None #time masterthread stopped
        self.complist = []
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in CONFIG.rendernodes:
            self._reset_compstatus(computer)
        self.skiplist = []
        self.path = None
        self.startframe = None
        self.endframe = None
        self.extraframes = []
        self.render_engine = None
        self.totalframes = []
        self.progress = None


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
                extraframes=[]):
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
        self.renderlog = RenderLog(
            self.path, self.startframe, self.endframe, self.extraframes, 
            self.complist, self._id
            )
        self.status = 'Waiting'
        return True

    def render(self, time_offset=None):
        '''Starts a render for a given job.
        time_offset: correction factor in seconds used when restoring a 
        running job after server restart.'''
        self.logger.debug('entered render()')
        if self.status != 'Waiting':
            return False
        self.status = 'Rendering'
        self._start_timer(offset=time_offset)
        # Having issues with script crashing if data server goes offline and
        # render log is inaccessible.
        #try:
        self.renderlog.start()
        #except:
        #    print("ERROR: Unable to write to render log.")

        self.killflag = False

        master = threading.Thread(target=self._masterthread, args=())
        master.start()
        return True

    def _masterthread(self):
        '''Main thread to control render process and create renderthreads.'''
        '''{'active':False, 'frame':None,
            'pid':None, 'timer':None, 'progress':0.0, 'error':None}'''
    
        self.logger.debug('started _masterthread()')
        self.threads_active = False
        #set target thread type based on render engine
        if self.render_engine == 'blend':
            tgt_thread = self._renderthread
        elif self.render_engine == 'tgd':
            tgt_thread = self._renderthread_tgn
        while True:
            if self.killflag:
                self.logger.debug('Kill flag detected, breaking render loop.')
                #deal with log & render timer
                break
    
            if self.queue.empty() and not self._threadsactive():
                self.logger.debug('Render done at detector')
                self.status = 'Finished'
                self._stop_timer()
                try:
                    self.renderlog.finished(self.get_times())
                except:
                    self.renderlog.exception('Unable to write to render log')
                break

            #prevent lockup if all computers end up in skiplist
            if len(self.skiplist) == len(self.complist):
                #ignore if both lists are empty
                if not len(self.complist) == 0:
                    self.logger.info('All nodes in skiplist, popping oldest one.')
                    skipcomp = self.skiplist.pop(0)
                    self._reset_compstatus(skipcomp)
    
            for computer in CONFIG.rendernodes:
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
                            try:
                                self.renderlog.frame_sent(frame, computer) 
                            except:
                                self.logger.exception('Unable to write to render log.')
                        self.logger.debug('Creating renderthread')
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
                        CONFIG.timeout):
                    self._thread_failed(self.compstatus[computer]['frame'], 
                                       computer, 'Timeout')

        self.logger.debug('_masterthread() terminating')



    def _threadsactive(self):
        '''Returns true if instances of _renderthread() are active.'''
        for computer in self.compstatus:
            if self.compstatus[computer]['active']:
                return True
        self.logger.debug('_threadsactive() returning false')
        return False

    def _renderthread(self, frame, computer, framequeue):
        '''Thread to send command, montor status, and parse return data for a
        single frame in Blender's Cycles render engine.  NOTE: This will not
        parse output from Blender's internal engine correctly.'''

        self.logger.debug('started _renderthread() for {} {}'.format(frame, computer))
        thread_start_time = datetime.datetime.now()
        if computer in CONFIG.macs:
            renderpath = shlex.quote(CONFIG.blenderpath_mac)
        else:
            renderpath = shlex.quote(CONFIG.blenderpath_linux)
        command = subprocess.Popen(
            'ssh {user}@{host} "{prog} -b -noaudio {path} -f {frame} & pgrep -n blender"'.format(
            user=CONFIG.ssh_user, host=computer, prog=renderpath, path=self.path, frame=frame), 
            stdout=subprocess.PIPE, shell=True )
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
                self.logger.exception('Error decoding subprocess output.')
                continue

            #reset timeout timer every time an update is received
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            if CONFIG.verbose:
                with threadlock:
                    self.logger.info(line)
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
                self.logger.info('PID {} detected for frame {} on {}'.format(pid, frame, computer))
                with threadlock:
                    self.compstatus[computer]['pid'] = pid
                if computer in CONFIG.renice_list:
                    subprocess.call('ssh {}@{} "renice 20 -p {}"'.format(
                        CONFIG.ssh_user, computer, pid), shell=True)
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
                self.logger.info('Finished frame {} on {} after {}'.format(frame, computer, rendertime))
                with threadlock:
                    try:
                        self.renderlog.frame_recvd(frame, computer, rendertime)
                    except:
                        self.logger.exception('Unable to write to render log')
                break
    
        #NOTE omitting stderr checking for now
        self.logger.debug('_renderthread() terminated for {} on {}'.format(frame, computer))

    def _renderthread_tgn(self, frame, computer, framequeue):
        '''Thread to send command, monitor status, and parse return data for a
        single frame in Terragen 3.'''

        self.logger.debug('started _renderthread_tgn() for {} on {}'.format(frame, computer))
        #pgrep string is different btw OSX and Linux so using whole cmd strings
        if computer in CONFIG.macs:
            cmd_string = (
                'ssh {user}@{host} "{prog} -p {path} -hide -exit -r '
                '-f {frame} & pgrep -n Terragen&wait"'.format(
                    user=CONFIG.ssh_user, host=computer, prog=CONFIG.terragenpath_mac, 
                    path=self.path, frame=frame
                )
            )
        else:
            cmd_string = (
                'ssh {user}@{host} "{prog} -p {path} -hide -exit -r '
                '-f {frame} & pgrep -n terragen&wait"'.format(
                    user=CONFIG.ssh_user, host=computer, prog=CONFIG.terragenpath_linux, 
                    path=self.path, frame=frame
                )
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
            if CONFIG.verbose:
                with threadlock:
                    self.logger.info(line)

            #starting overall render or one of the render passes
            if line.strip().isdigit():
                pid = int(line.strip())
                self.logger.debug('Possible PID detected: {} for {} on {}'.format(
                    pid, frame, computer))
                if pid != frame: 
                    #necessary b/c terragen echoes frame # at start. 
                    #Hopefully PID will never be same as frame #
                    self.logger.debug('PID set to {} for {} on {}'.format(pid, frame, computer))
                    with threadlock:
                        self.compstatus[computer]['pid'] = pid
                    #renice process to lowest priority on specified comps 
                    if computer in CONFIG.renice_list: 
                        subprocess.call('ssh {}@{} "renice 20 -p {}"'.format(
                            CONFIG.ssh_user, pid), shell=True)
                        self.logger.info('Reniced PID {} to pri 20 on {}'.format(pid, computer))
                    #remove oldest item from skiplist if render starts 
                    with threadlock:
                        if len(self.skiplist) > 0:
                            skipcomp = self.skiplist.pop(0)
                            self._reset_compstatus(skipcomp)
            #starting a new render pass
            elif line.find('Starting') >= 0:
                ellipsis = line.find('...')
                passname = line[9:ellipsis]
                self.logger.info('Starting pass {} for {} on {}'.format(passname, frame, computer))

            #finished one of the render passes
            elif line.find('Rendered') >= 0:
                mark = line.find('of ')
                passname = line[mark+3:]
                self.logger.info('Finished pass {} for {} on {}'.format(passname, frame, computer))

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
                self.logger.info('Frame {} {}% complete on {}'.format(frame, percent, computer))
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
                self.logger.info('Finished frame {} on {} after {}'.format(
                    frame, computer, rendertime))
                with threadlock:
                    try:
                        self.renderlog.frame_recvd(frame, computer, rendertime)
                    except:
                        self.logger.exception('Unable to write to render log')
                break
            #NOTE: omitting stderr testing for now
        self.logger.debug('_renderthread_tgn() terminated for {} on {}'.format(frame, computer))

    def _thread_failed(self, frame, computer, errortype):
        '''Handles operations associated with a failed render thread.'''
        #If pipe is broken because render was killed by user, don't
        #treat it as an error:
        #if self.compstatus[computer]['error'] == 'Killed':
        if not self.compstatus[computer]['active']:
            return
        self.logger.error('Failed to render frame {} on {} with error type {}'.format(
            frame, computer, errortype))
        self.skiplist.append(computer)
        with threadlock:
            self.queue.put(frame)
            self.compstatus[computer]['active'] = False
            self.compstatus[computer]['error'] = errortype
            try:
                self.renderlog.frame_failed(frame, computer, errortype)
            except:
                self.logger.exception('Unable to write to render log')
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
            try:
                self.renderlog.process_killed(pid, computer)
            except:
                self.logger.exception('Unable to write to render log')

    def _threadkiller(self, computer, pid):
        '''Target thread to manage kill commands, created by _kill_thread'''
        self.logger.debug('entered _threadkiller(), pid: {] on {}'.format(pid, computer))
        subprocess.call('ssh {}@{} "kill {}"'.format(CONFIG.ssh_user, computer, pid), shell=True)
        self.logger.debug('finished _threadkiller() on {}'.format(computer))

    def kill_thread(self, computer):
        '''Handles EXTERNAL kill thread requests.  Returns PID if 
        successful.'''
        try:
            pid = self.compstatus[computer]['pid']
            frame = self.compstatus[computer]['frame']
        except:
            self.logger.exception('Caught exception in Job.kill_thread while getting'
                + 'pid on {}'.format(computer))
            return False
        if (pid == None or frame == None):
            self.logger.error('Job.kill_thread() failed on {}. No PID or frame assigned.'.format(
                computer))
            return False
        with threadlock:
            self.queue.put(frame)
        self._kill_thread(computer, pid)
        self._reset_compstatus(computer)
        self.logger.debug('Finished Job.kill_thread on {}'.format(computer))
        return pid

    def _start_timer(self, offset=None):
        '''Starts the render timer for the job.
        offset: correction factor in seconds, used when restoring a running
        job after server restart.'''
        if offset:
            self.starttime = time.time() - offset
            self.logger.info('Offsetting job start time by {} seconds.'.format(offset))
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
            '_id':self._id
            }
        return attrdict

    def add_computer(self, computer):
        #if self.compstatus[computer]['pool']:
        if computer in self.complist:
            return False
        else:
            self.complist.append(computer)
            if self.status == 'Rendering':
                with threadlock:
                    try:
                        self.renderlog.computer_added(computer)
                    except:
                        self.logger.exception('Unable to write to render log')
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
                    try:
                        self.renderlog.computer_removed(computer)
                    except:
                        self.logger.exception('Unable to write to render log')
            return True

    def kill_now(self):
        '''Kills job and all currently rendering frames'''
        if not self.status == 'Rendering':
            return False
        self.killflag = True
        self._stop_timer()
        with threadlock:
            try:
                self.renderlog.stop(self.get_times())
            except:
                self.logger.exception('Unable to write to render log')
        self.status = 'Stopped'
        for computer in CONFIG.rendernodes:
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
            try:
                self.renderlog.stop(self.get_times())
            except:
                self.logger.exception('Unable to write to render log')
        self.status = finalstatus
        return True

    def resume(self, startnow=True):
        '''Resumes a render that was previously stopped. If startnow == False,
        render will be placed in queue with status 'Waiting' but not 
        started.'''
        if not (self.status == 'Stopped' or self.status == 'Paused'):
            return False
        self.killflag = False
        for computer in CONFIG.rendernodes:
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
        #create new entries if list of available computers has changed
        #new computers added
        added = [comp for comp in CONFIG.rendernodes if not 
                 comp in self.compstatus]
        if added:
            for comp in added:
                self._reset_compstatus(comp)
                self.logger.debug('New node {} available. Creating compstatus entry.'.format(
                    computer))
        #any computers no longer available
        removed = [comp for comp in self.compstatus if not
                   comp in CONFIG.rendernodes]
        if removed:
            for comp in removed:
                if comp in self.complist:
                    self.complist.remove(comp)
                self.logger.debug('Node {} in compstatus no longer available. Removing entry.'.format(
                    computer))
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
            self.logger.info('Restoring job with frames: {}'.format(framelist))
            self.renderlog = RenderLog(
                self.path, self.startframe, self.endframe, 
                self.extraframes, self.complist, self._id
                )

        if self.status == 'Rendering':
            self.logger.debug('Attempting to start')
            #determine time offset to give correct remaining time estimate
            elapsed = times[0]
            for computer in CONFIG.rendernodes:
                self._reset_compstatus(computer)
            self.status = 'Waiting'
            self.render(time_offset=elapsed)
        return True

    def gettime(self):
        '''Returns current time as string formatted for timestamps.'''
        timestamp = time.strftime('%H:%M:%S on %Y/%m/%d', time.localtime())
        return timestamp

    def getstatus(self):
        return self.status


class RenderLog(Job):
    '''Logs render progress for a given job.  Log instance is created when
    job is placed in queue, but actual log file is not created until render
    is started. Time in filename reflects time job was placed in queue.'''
    hrule = '=' * 70 + '\n' #for printing thick horizontal line
    def __init__(self, path, startframe, endframe, extraframes, complist, 
                 _id):
        self.path = path
        self._id = _id #object ID of the parent Job() instance
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes
        self.complist = complist
        self.log_basepath = CONFIG.log_basepath
        self.filename, ext = os.path.splitext(os.path.basename(self.path))
        self.enq_time = time.strftime('%Y-%m-%d_%H%M%S', time.localtime())
        logfile = '{}.{}.txt'.format(self.filename, self.enq_time)
        self.logpath = os.path.join(self.log_basepath, logfile)
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
            log.write('Job ID: %s\n' %self._id)
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
default_cfg_file = """# YAML configuration file for rcontroller server

# Server listen port
serverport: 2020

# Enable autostart by default (1=True, 0=False)
autostart: 1

# Start server in vebose mode by default
verbose: 0

# Directory to hold render logs
# Must be writable by user running the server
log_basepath: /var/log/rcontroller

# Timeout for failed render process in seconds
timeout: 1000

# SSH username for connecting to nodes
ssh_user: igp

# List of all render nodes
rendernodes:
  - hex1
  - hex2
  - hex3
  - borg1
  - borg2
  - borg3
  - borg4
  - borg5
  - grob1
  - grob2
  - grob3
  - grob4
  - grob5
  - grob6
  - eldiente
  - lindsey
  - conundrum
  - paradox

# Render nodes running Mac OSX
macs:
  - conundrum
  - paradox

# Renice render processes to low priority on these nodes
# Useful if rendering on a workstation that's in use
renice_list:
  - conundrum
  - paradox

# Path to render software executables
blenderpath_mac: /Applications/blender.app/Contents/MacOS/blender
blenderpath_linux: /usr/local/bin/blender
terragenpath_mac: '/mnt/data/software/terragen_rendernode/osx/Terragen\ 3.app/Contents/MacOS/Terragen\ 3'
terragenpath_linux: /mnt/data/software/terragen_rendernode/linux/terragen

# File extensions of rendered frames recognized by Check Missing Frames function
allowed_filetypes:
  - .png
  - .jpg
  - .peg
  - .gif
  - .tif
  - .iff
  - .exr
  - .PNG
  - .JPG
  - .PEG
  - .GIF
  - .TIF
  - .IFF
  - .EXR"""

class Config(object):
    '''Represents contents of config file as attributes.'''

    DEFAULT_DIR = os.path.dirname(os.path.realpath(__file__))
    DEFAULT_FILENAME = 'server.conf'

    def __init__(self, cfg_path=None):
        '''Args:
        cfg_path -- Path to server config file (default=server.conf in same dir as this file)
        '''
        if cfg_path:
            self.cfg_path = cfg_path
        else:
            self.cfg_path = os.path.join(self.DEFAULT_DIR, self.DEFAULT_FILENAME)
        if not os.path.exists(self.cfg_path):
            logger.warning('Config file not found. Generating new from defaults')
            self.write_default_file()
        self.load()

    def load(self):
        '''Loads the config file then populates attributes'''
        default = yaml.load(default_cfg_file)
        try:
            with open(self.cfg_path, 'r') as f:
                cfg = yaml.load(f.read())
        except:
            logger.exception('Failed to load config file. Generating new from defaults')
            self.write_default_file()
            cfg = default
        # Make sure the file has all the required fields
        for key in default.keys():
            if key not in cfg:
                logger.error('Config file missing required field. Writing new from defaults.')
                self.write_default_file
                cfg = default
                break
        self.from_dict(cfg)

    def from_dict(self, dictionary):
        '''Sets attributes from a dictionary

        Args:
        dictionary -- Dict to be converted to attrs
        '''
        self.dictionary = dictionary
        for key in dictionary:
            self.__setattr__(key, dictionary[key])

    def write_default_file(self):
        '''Writes the default file to disk'''
        with open(self.cfg_path, 'w') as f:
            f.write(default_cfg_file)




#----------SERVER INTERFACE----------


allowed_commands= [
'get_attrs', 'job_exists', 'enqueue',
'start_render', 'toggle_comp', 'kill_single_thread', 'kill_render',
'get_status', 'resume_render', 'clear_job', 'get_config_vars', 'create_job',
'toggle_verbose', 'toggle_autostart', 'check_path_exists', 'set_job_priority',
'killall',
]


class RenderServer(object):
    '''This is the master class for this module. Instantiate this class to
    start a server. The Job class and its methods can be used directly 
    without a RenderServer instance, however an instance of Config MUST be 
    created first to define the global configuration variables on which 
    Job's methods depend.'''
    def __init__(self, port=None):
        self.logger = logging.getLogger('rcontroller.server.RenderServer')
        self.logger.setLevel(logging.DEBUG)
        #read config file & set up config variables
        global CONFIG
        CONFIG = Config()
        if not port:
            port = CONFIG.serverport
        if not self._check_logpath():
            return
        mainlog = logging.FileHandler(os.path.join(CONFIG.log_basepath, 'server.log'))
        mainlog.setLevel(logging.INFO)
        mainlog.setFormatter(file_formatter)
        self.logger.addHandler(mainlog)
        logger.addHandler(mainlog) # also add for the global logger
        self.statefile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'serverstate.json')
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
        if not os.path.exists(CONFIG.log_basepath):
            try:
                os.mkdir(CONFIG.log_basepath)
                self.logger.info('Created log directory at {}'.format(CONFIG.log_basepath))
            except PermissionError as e:
                self.logger.exception('Unable to create log directory')
                return False
        return True

    def update_loop(self):
        '''Handles miscellaneous tasks that need to be carried out on a 
        regular interval. Runs in separate thread to prevent blocking other 
        processes.'''
        self.stop_update_loop = False
        self.logger.debug('started update_loop')
        while not self.stop_update_loop:
            #run tasks every 20 seconds, but subdivide loop into smaller
            #units so it's immediately interruptable when server shuts down.
            #waits for 0.5 sec 40 times on each pass
            for i in range(40):
                time.sleep(0.5)
                if self.stop_update_loop:
                    break
            self.save_state()
            if CONFIG.autostart:
                self.check_autostart()
        self.logger.debug('update_loop done')
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
        self.logger.debug('Saving server state')
        self.save_state()
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
            self.logger.debug('High priority render detected')
            #kill all active renders
            for i in self.renderjobs:
                job = self.renderjobs[i]
                if job.status == 'Rendering':
                    self.logger.info('Pausing {}'.format(job.path))
                    job.kill_later(finalstatus='Paused')
                    self.waitlist.insert(0, job)
            newjob = times[min(times)]
            newjob.autostart()
            self.logger.info('Started {}'.format(newjob.path))
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
            self.logger.debug('Autostart: more than 1 active job found, returning')
            return
        elif len(activejobs) == 0:
            newjob = self.waitlist.pop(0)
            newjob.autostart()
            self.logger.info('Autostart started {}'.format(newjob.path))
            return
        elif len(activejobs) == 1:
            job = activejobs[0]
            if job.queue.empty():
                #All frames distributed, just waiting for render to finish.
                #If one frame is taking inordinately long, don't want to wait
                #to start the next render.
                self.logger.debug('Autostart: exactly 1 job running & queue empty')
                if job.totalframes.count(0) > 1:
                    self.logger.debug('Autostart: >1 frame rendering, returning')
                    return
                else:
                    self.logger.debug('Autostart: exactly 1 frame rendering, starting next')
                    newjob = self.waitlist.pop(0)
                    newjob.autostart()
                    self.logger.info('Autostart started {}'.format(newjob.path))
                pass
            else:
                return

    def save_state(self):
        '''Writes the current state of all Job instances on the server
        to a file. Used for restoring queue contents and server state in
        case the server crashes or needs to be restarted.  The update_loop
        method periodically calls this function whenever the server is 
        running.'''
        statevars = {'verbose':CONFIG.verbose, 'autostart':CONFIG.autostart}
        jobs = {}
        for index in self.renderjobs:
            jobs[index] = self.renderjobs[index].get_attrs()
        serverstate = [statevars, jobs]
        with open(self.statefile, 'w') as f:
            f.write(json.dumps(serverstate))

    
    def _check_restore_state(self):
        '''Checks for an existing serverstate.json file in the same directory
        as this file. If found, prompts the user to restore the server state
        from the file. If yes, loads the file contents and attempts to
        create new Job instances with attributes from the file. Can only
        be called at startup to avoid overwriting exiting Job instances.'''
        if os.path.exists(self.statefile):
            if input('Saved state file found. Restore previous server '
                         'state? (Y/n): ') in ['N', 'n']:
                self.logger.info('Discarding previous server state')
                return
            with open(self.statefile, 'r') as f:
                (statevars, jobs) = json.loads(f.read())
            #restore state variables
            CONFIG.verbose = statevars['verbose']
            CONFIG.autostart = statevars['autostart']
            #restore job queue
            for index in jobs:
                _id = jobs[index]['_id']
                self.renderjobs[index] = Job(_id)
                reply = self.renderjobs[index].set_attrs(jobs[index])
                if reply:
                    self.logger.info('Restored {} from saved state'.format(index))
                    #add job to waitlist if necessary
                    status = jobs[index]['status']
                    if (status == 'Waiting' or status == 'Paused'):
                        self.waitlist.append(self.renderjobs[index])
                        self.logger.debug('Added {} to waitlist'.format(index))
                else:
                    self.logger.error('Unable to restore {}'.format(index))
            self.logger.info('Server state restored')

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
        attrdict['__STATEVARS__'] = {'autostart':CONFIG.autostart, 
                               'verbose':CONFIG.verbose}
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
            extraframes=extras, 
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
        if not computer in CONFIG.rendernodes:
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
        try:
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
        except:
            return 'Operation failed, exception handled.'
    
    def kill_render(self, index, kill_now):
        try:
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
        except:
            return 'Unable to kill %s, exception handled' %index
    
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
        a dict.'''
        return CONFIG.dictionary
    
    def toggle_verbose(self):
        '''Toggles the state of the verbose variable.'''
        if CONFIG.verbose == 0:
            CONFIG.verbose = 1
            self.logger.info('Verbose reporting enabled')
            return 'verbose reporting enabled'
        else:
            CONFIG.verbose = 0
            self.logger.info('Verbose reporting disabled')
            return 'verbose reporting disabled'
    
    def toggle_autostart(self):
        '''Toggles the state of the autostart variable.'''
        if CONFIG.autostart == 0:
            CONFIG.autostart = 1
            return 'autostart enabled'
            self.logger.info('Autostart enabled')
        else:
            CONFIG.autostart = 0
            self.logger.info('Autostart disabled')
            return 'autostart disabled'
    
    def check_path_exists(self, path):
        '''Checks if a path is accessible from the server.'''
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

    def killall(self, complist, procname):
        '''Attempts to kill all instances of the given processess on the
        given machines.'''
        # First make sure that everything is OK
        for comp in complist:
            if not comp in CONFIG.rendernodes:
                return 'Killall failed. Computer %s not recognized.' %comp
        if not procname in ['blender', 'terragen']:
            return 'Process name %s not recognized.' %procname
        SSHKillThread(complist, self.msgq, procname)
        return 'Attempting to kill %s on %s' %(procname, complist)



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
        self.logger = getLogger('rcontroller.server.SSHKillThread')
        self.compq = queue.Queue() #job queue for child processes
        self.replyq = queue.Queue() #queue for replies from child processes
        for comp in complist:
            self.compq.put(comp)
        threads = range(len(complist))
        mt = threading.Thread(target=self.master, 
            args=(threads, msgqueue, procname))
        mt.daemon = True
        mt.start()

    def master(self, workers, msgqueue, procname):
        '''Creates worker threads and waits for them to finish.
        workers: number of worker threads to create'''
        for i in workers:
            comp = self.compq.get()
            t = threading.Thread(target=self.worker, args=(comp, procname))
            t.daemon = True
            t.start()
        self.compq.join()
        if self.replyq.empty():
            msgqueue.put('success')
            return
        else:
            replies = []
            while not self.replyq.empty():
                replies.append(self.replyq.get())
            self.logger.debug('replies: {}'.format(replies))
            msgqueue.put(replies)

    def worker(self, comp, procname):
        self.logger.debug('killall thread for {} started'.format(comp))
        if comp in CONFIG.macs and procname == 'terragen':
            procname = "'Terragen 3'"
        self.logger.debug('procname is {}'.format(procname))
        #cmd = 'ssh igp@%s "pgrep %s | xargs kill"' %(comp, procname)
        cmd = 'ssh {}@{} "pgrep %s | xargs kill"'.format(CONFIG.ssh_user, comp, procname)
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
