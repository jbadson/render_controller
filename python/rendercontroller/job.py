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
import shlex
import datetime
import re
import json
import logging


# Module-level config variable. Injected by RenderController
# This is a stupid hack until I get this module rewritten.
CONFIG = None


#NOTE: All classes in this module depend on a global instance of
# Config named CONFIG. Be sure to create one if importing.
# This is not the best way to do things, but it is how it is.


logger = logging.getLogger("job")

illegal_characters = [';', '&'] #not allowed in paths
threadlock = threading.RLock()


def format_time(time):
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


class Job(object):
    '''Represents a render job.'''

    def __init__(self, _id=None):
        if _id:
            self._id = _id
        else:
            self._id = id(self)
        #initialize all attrs for client updates
        self.status = 'Empty'
        self.queuetime = time.time()
        self.priority = 'Normal'
        self.starttime = None #time render() called
        self.stoptime = None #time masterthread stopped
        self.complist = []
        #generate dict of computer statuses
        self.compstatus = dict()
        for computer in CONFIG.render_nodes:
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
        if self.status == 'Finished':
            self.progress = 100.0
            return self.progress
        rendered = 0
        for f in self.totalframes:
            if f != 0:
                rendered += 1
        self.progress = float(rendered) / len(self.totalframes) * 100
        return self.progress


    def get_comp_status(self, computer):
        '''Returns the contents of self.compstatus for a given computer.'''
        return self.compstatus[computer]

    def enqueue(self, path, startframe, endframe, render_engine, complist, 
                extraframes=None):
        '''Create a new job and place it in queue.'''
        #make sure path is properly shell-escaped
        self.path = shlex.quote(path)
        for char in illegal_characters:
            if char in path:
                return False
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes or []

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
        self.renderlog = logger.getChild(os.path.basename(self.path))
        self.renderlog.info(
            'placed in queue with startframe: {} endframe: {} extra frames: '\
            '{} on nodes: {} with job ID {}'.format(
            self.startframe, self.endframe, ', '.join(self.extraframes), 
            ', '.join(self.complist), self._id))
        self.status = 'Waiting'
        return True

    def render(self, time_offset=None):
        '''Starts a render for a given job.
        time_offset: correction factor in seconds used when restoring a 
        running job after server restart.'''
        logger.debug('entered render()')
        if self.status != 'Waiting':
            return False
        self.status = 'Rendering'
        self._start_timer(offset=time_offset)
        self.renderlog.info('Started render')
        self.killflag = False
        master = threading.Thread(target=self._masterthread, args=())
        master.start()
        return True

    def _masterthread(self):
        '''Main thread to control render process and create renderthreads.'''
        '''{'active':False, 'frame':None,
            'pid':None, 'timer':None, 'progress':0.0, 'error':None}'''
    
        logger.debug('started _masterthread()')
        self.threads_active = False
        #set target thread type based on render engine
        if self.render_engine == 'blend':
            tgt_thread = self._renderthread
        elif self.render_engine == 'tgd':
            tgt_thread = self._renderthread_tgn
        while True:
            if self.killflag:
                logger.debug('Kill flag detected, breaking render loop.')
                #deal with log & render timer
                break
    
            if self.queue.empty() and not self._threadsactive():
                logger.debug('Render done at detector')
                self.status = 'Finished'
                self._stop_timer()
                elapsed, avg, rem = self.get_times()
                self.renderlog.info(
                    'Finished render. Total time: {}, Avg time per frame: {}'.format(
                    format_time(elapsed), format_time(avg)))
                break

            #prevent deadlock if all computers end up in skiplist
            if len(self.skiplist) == len(self.complist):
                #ignore if both lists are empty
                if not len(self.complist) == 0:
                    logger.info('All nodes in skiplist, popping oldest one.')
                    skipcomp = self.skiplist.pop(0)
                    self._reset_compstatus(skipcomp)
    
            for computer in CONFIG.render_nodes:
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
                            self.renderlog.info('Sent frame {} to {}'.format(frame, computer))
                        logger.debug('Creating renderthread')
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
        logger.debug('_masterthread() terminating')


    def _threadsactive(self):
        '''Returns true if instances of _renderthread() are active.'''
        for computer in self.compstatus:
            if self.compstatus[computer]['active']:
                return True
        logger.debug('_threadsactive() returning false')
        return False

    def _renderthread(self, frame, computer, framequeue):
        '''Thread to send command, montor status, and parse return data for a
        single frame in Blender's Cycles render engine.  NOTE: This will not
        parse output from Blender's internal engine correctly.'''

        logger.debug('started _renderthread() for {} {}'.format(frame, computer))
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
            try:
                line = line.decode('UTF-8')
                if not line:
                    #pipe broken, 
                    self._thread_failed(frame, computer, 'Broken pipe')
                    return
            except UnicodeDecodeError as e:
                logger.exception('Error decoding subprocess output.')
                continue

            #reset timeout timer every time an update is received
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            logger.debug(line)
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
                logger.info('PID {} detected for frame {} on {}'.format(pid, frame, computer))
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
                self.renderlog.info('Finished frame {} on {} after {}'.format(frame, computer, rendertime))
                break
    
        #NOTE omitting stderr checking for now
        logger.debug('_renderthread() terminated for {} on {}'.format(frame, computer))

    def _renderthread_tgn(self, frame, computer, framequeue):
        '''Thread to send command, monitor status, and parse return data for a
        single frame in Terragen 3.'''

        logger.debug('started _renderthread_tgn() for {} on {}'.format(frame, computer))
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
            logger.debug(line)

            #starting overall render or one of the render passes
            if line.strip().isdigit():
                pid = int(line.strip())
                logger.debug('Possible PID detected: {} for {} on {}'.format(
                    pid, frame, computer))
                if pid != frame: 
                    #necessary b/c terragen echoes frame # at start. 
                    #Hopefully PID will never be same as frame #
                    logger.debug('PID set to {} for {} on {}'.format(pid, frame, computer))
                    with threadlock:
                        self.compstatus[computer]['pid'] = pid
                    #renice process to lowest priority on specified comps 
                    if computer in CONFIG.renice_list: 
                        subprocess.call('ssh {}@{} "renice 20 -p {}"'.format(
                            CONFIG.ssh_user, pid), shell=True)
                        logger.info('Reniced PID {} to pri 20 on {}'.format(pid, computer))
                    #remove oldest item from skiplist if render starts 
                    with threadlock:
                        if len(self.skiplist) > 0:
                            skipcomp = self.skiplist.pop(0)
                            self._reset_compstatus(skipcomp)
            #starting a new render pass
            elif line.find('Starting') >= 0:
                ellipsis = line.find('...')
                passname = line[9:ellipsis]
                logger.info('Starting pass {} for {} on {}'.format(passname, frame, computer))

            #finished one of the render passes
            elif line.find('Rendered') >= 0:
                mark = line.find('of ')
                passname = line[mark+3:]
                logger.info('Finished pass {} for {} on {}'.format(passname, frame, computer))

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
                logger.info('Frame {} {}% complete on {}'.format(frame, percent, computer))
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
                self.renderlog.info('Finished frame {} on {} after {}'.format(
                    frame, computer, rendertime))
                break
            #NOTE: omitting stderr testing for now
        logger.debug('_renderthread_tgn() terminated for {} on {}'.format(frame, computer))

    def _thread_failed(self, frame, computer, errortype):
        '''Handles operations associated with a failed render thread.'''
        #If pipe is broken because render was killed by user, don't
        #treat it as an error:
        if not self.compstatus[computer]['active']:
            return
        logger.error('Failed to render frame {} on {} with error type {}'.format(
            frame, computer, errortype))
        self.skiplist.append(computer)
        with threadlock:
            self.queue.put(frame)
            self.compstatus[computer]['active'] = False
            self.compstatus[computer]['error'] = errortype
            self.renderlog.warning(
                'Frame {} failed to render on {} because of {}'.format(
                frame, computer, errortype))
        pid = self.compstatus[computer]['pid']
        if pid:
            self._kill_thread(computer, pid)

    def _kill_thread(self, computer, pid):
        '''Handles INTERNAL kill thread requests. Encapsulates kill command
        in separate thread to prevent blocking of main if ssh connection is
        slow.'''
        kthread = threading.Thread(target=self._threadkiller, 
                                   args=(computer, pid))
        kthread.start()
        self.renderlog.info('Killed PID {} on {}'.format(pid, computer))

    def _threadkiller(self, computer, pid):
        '''Target thread to manage kill commands, created by _kill_thread'''
        logger.debug('entered _threadkiller(), pid: {} on {}'.format(pid, computer))
        subprocess.call('ssh {}@{} "kill {}"'.format(CONFIG.ssh_user, computer, pid), shell=True)
        logger.debug('finished _threadkiller() on {}'.format(computer))

    def kill_thread(self, computer):
        '''Handles EXTERNAL kill thread requests.  Returns PID if 
        successful.'''
        try:
            pid = self.compstatus[computer]['pid']
            frame = self.compstatus[computer]['frame']
        except:
            logger.exception('Caught exception in Job.kill_thread while getting'
                + 'pid on {}'.format(computer))
            return False
        if (pid == None or frame == None):
            logger.warning('Job.kill_thread() failed on {}. No PID or frame assigned.'.format(
                computer))
            return False
        with threadlock:
            self.queue.put(frame)
        self._kill_thread(computer, pid)
        self._reset_compstatus(computer)
        logger.debug('Finished Job.kill_thread on {}'.format(computer))
        return pid

    def _start_timer(self, offset=None):
        '''Starts the render timer for the job.
        offset: correction factor in seconds, used when restoring a running
        job after server restart.'''
        if offset:
            self.starttime = time.time() - offset
            logger.info('Offsetting job start time by {} seconds.'.format(offset))
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
        if computer in self.complist:
            return False
        else:
            self.complist.append(computer)
            if self.status == 'Rendering':
                self.renderlog.info('Added node {}'.format(computer))
            return True

    def remove_computer(self, computer):
        if not computer in self.complist:
            return False
        else:
            self.complist.remove(computer)
            if computer in self.skiplist:
                self.skiplist.remove(computer)
            if self.status == 'Rendering':
                self.renderlog.info('Removed node {}'.format(computer))
            return True

    def kill_now(self):
        '''Kills job and all currently rendering frames'''
        if not self.status == 'Rendering':
            return False
        self.killflag = True
        self._stop_timer()
        elapsed, avg, rem = self.get_times()
        self.renderlog.info(
            'Render stopped by user. Total time: {}, Avg time per frame: {}'.format(
            format_time(elapsed), format_time(avg)))
        self.status = 'Stopped'
        for computer in CONFIG.render_nodes:
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
        elapsed, avg, rem = self.get_times()
        self.renderlog.info(
            'Render stopped by user. Total time: {}, Avg time per frame: {}'.format(
            format_time(elapsed), format_time(avg)))
        self.status = finalstatus
        return True

    def resume(self, startnow=True):
        '''Resumes a render that was previously stopped. If startnow == False,
        render will be placed in queue with status 'Waiting' but not 
        started.'''
        if not (self.status == 'Stopped' or self.status == 'Paused'):
            return False
        self.killflag = False
        for computer in CONFIG.render_nodes:
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
        added = [comp for comp in CONFIG.render_nodes if not
                 comp in self.compstatus]
        if added:
            for comp in added:
                self._reset_compstatus(comp)
                logger.debug('New node {} available. Creating compstatus entry.'.format(
                    comp))
        #any computers no longer available
        removed = [comp for comp in self.compstatus if not
                   comp in CONFIG.render_nodes]
        if removed:
            for comp in removed:
                if comp in self.complist:
                    self.complist.remove(comp)
                logger.debug('Node {} in compstatus no longer available. Removing entry.'.format(
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
            self.renderlog = logger.getChild(os.path.basename(self.path))
            self.renderlog.info(
                'Restored job with startframe: {} endframe: {} extra frames: {} on nodes: '\
                '{} with job ID {}'.format(self.startframe, self.endframe, 
                ', '.join(self.extraframes), ', '.join(self.complist), self._id))

        if self.status == 'Rendering':
            logger.debug('Attempting to start')
            #determine time offset to give correct remaining time estimate
            elapsed = times[0]
            for computer in CONFIG.render_nodes:
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


def quit():
    '''Forces immediate exit without waiting for loops to terminate.'''
    os._exit(1)


class RenderServer(object):
    '''This is the master class for this module. Instantiate this class to
    start a server.'''
    def __init__(self):
        self.statefile = os.path.join(CONFIG.work_dir, "serverstate.json")
        self.renderjobs = {}
        self.waitlist = [] #ordered list of jobs waiting to be rendered
        self.msgq = queue.Queue() #queue for misc. messages to clients
        self._check_restore_state()
        self.updatethread = threading.Thread(target=self.update_loop)
        self.updatethread.start()

    def update_loop(self):
        '''Handles miscellaneous tasks that need to be carried out on a 
        regular interval. Runs in separate thread to prevent blocking other 
        processes.'''
        self.stop_update_loop = False
        logger.debug('started update_loop')
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
        logger.debug('update_loop done')
        self.shutdown_server()

    def shutdown_server(self):
        '''Saves the server state then shuts it down cleanly.'''
        #shut down the update loop
        self.stop_update_loop = True
        #check for any unfinished jobs, note the shutdown in their logs
        log_statuses = ['Rendering', 'Stopped', 'Paused']
        logger.info('Pausing any active jobs and saving server state')
        self.save_state()
        logger.info('Shutting down server')
        quit()

    def check_autostart(self):
        '''Checks all active and queued jobs and starts them if needed.'''
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
            logger.debug('High priority render detected')
            #kill all active renders
            for i in self.renderjobs:
                job = self.renderjobs[i]
                if job.status == 'Rendering':
                    logger.info('Pausing {}'.format(job.path))
                    job.kill_later(finalstatus='Paused')
                    self.waitlist.insert(0, job)
            newjob = times[min(times)]
            newjob.autostart()
            logger.info('Started {}'.format(newjob.path))
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
            logger.debug('Autostart: more than 1 active job found, returning')
            return
        elif len(activejobs) == 0:
            newjob = self.waitlist.pop(0)
            newjob.autostart()
            logger.info('Autostart started {}'.format(newjob.path))
            return
        elif len(activejobs) == 1:
            job = activejobs[0]
            if job.queue.empty():
                #All frames distributed, just waiting for render to finish.
                #If one frame is taking inordinately long, don't want to wait
                #to start the next render.
                logger.debug('Autostart: exactly 1 job running & queue empty')
                if job.totalframes.count(0) > 1:
                    logger.debug('Autostart: >1 frame rendering, returning')
                    return
                else:
                    logger.debug('Autostart: exactly 1 frame rendering, starting next')
                    newjob = self.waitlist.pop(0)
                    newjob.autostart()
                    logger.info('Autostart started {}'.format(newjob.path))
                pass
            else:
                return

    def save_state(self):
        '''Writes the current state of all Job instances on the server
        to a file. Used for restoring queue contents and server state in
        case the server crashes or needs to be restarted.  The update_loop
        method periodically calls this function whenever the server is 
        running.'''
        statevars = {'autostart':CONFIG.autostart}
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
        if os.path.exists(self.statefile) and os.stat(self.statefile).st_size > 0:
            try:
                with open(self.statefile, 'r') as f:
                    (statevars, jobs) = json.loads(f.read())
            except:
                logger.exception('Failed to read saved state file')
                return
            #restore state variables
            CONFIG.autostart = statevars['autostart']
            #restore job queue
            for index in jobs:
                _id = jobs[index]['_id']
                self.renderjobs[index] = Job(_id)
                reply = self.renderjobs[index].set_attrs(jobs[index])
                if reply:
                    logger.info('Restored {} from saved state'.format(index))
                    #add job to waitlist if necessary
                    status = jobs[index]['status']
                    if (status == 'Waiting' or status == 'Paused'):
                        self.waitlist.append(self.renderjobs[index])
                        logger.debug('Added {} to waitlist'.format(index))
                else:
                    logger.error('Unable to restore {}'.format(index))
            logger.info('Server state restored')

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
        attrdict['__STATEVARS__'] = {'autostart':CONFIG.autostart, }
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
                raise ValueError("Illegal character in path")
        #NOTE: path is also escaped by shlex.quote() in Job.enqueue
        startframe = kwargs['startframe']
        endframe = kwargs['endframe']
        if startframe > endframe:
            raise ValueError("End frame must be greater than start frame")
        extras = kwargs['extraframes']
        render_engine = kwargs['render_engine']
        complist = kwargs['complist']
        #create the job
        if index in self.renderjobs:
            if self.renderjobs[index].getstatus() == 'Rendering':
                raise ValueError("Job id in use")
        #place it in queue
        self.renderjobs[index] = Job()
        #put it in ordered list of waiting jobs
        self.waitlist.append(self.renderjobs[index])
        success = self.renderjobs[index].enqueue(
            path, startframe, endframe, render_engine, complist, 
            extraframes=extras, 
            )
        if success:
            return index
        else:
            del self.renderjobs[index]
            raise RuntimeError("Failed to create job")
    
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
        if not computer in CONFIG.render_nodes:
            return 'Computer "%s" not recognized.' %computer
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
            else:
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
        '''DEPRECATED Gets server-side configuration variables and returns them as
        a dict.'''
        return CONFIG.dump()
    
    def toggle_autostart(self):
        '''Toggles the state of the autostart variable.'''
        if CONFIG.autostart == 0:
            CONFIG.autostart = 1
            return 'autostart enabled'
            logger.info('Autostart enabled')
        else:
            CONFIG.autostart = 0
            logger.info('Autostart disabled')
            return 'autostart disabled'
    
    def check_path_exists(self, path):
        '''DEPRECATED Checks if a path is accessible from the server.'''
        if os.path.exists(path):
            return True
        else:
            return False
    
    def set_job_priority(self, index, priority):
        '''DEPRECATED Sets the render priority for a given index.'''
        if not index in self.renderjobs:
            return 'Index not found'
        if self.renderjobs[index].set_priority(priority):
            return 'Priority of ' + index + ' set to ' + str(priority)
        else:
            return 'Priority not changed'

    def killall(self, complist, procname):
        '''DEPRECATED Attempts to kill all instances of the given processess on the
        given machines.'''
        # First make sure that everything is OK
        for comp in complist:
            if not comp in CONFIG.render_nodes:
                return 'Killall failed. Computer %s not recognized.' %comp
        if not procname in ['blender', 'terragen']:
            return 'Process name %s not recognized.' %procname
        SSHKillThread(complist, self.msgq, procname)
        return 'Attempting to kill %s on %s' %(procname, complist)



class SSHKillThread(object):
    '''
    DEPRECATED

    Sends kill commands by ssh to specified hostnames. Returns a
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
            logger.debug('replies: {}'.format(replies))
            msgqueue.put(replies)

    def worker(self, comp, procname):
        logger.debug('killall thread for {} started'.format(comp))
        if comp in CONFIG.macs and procname == 'terragen':
            procname = "'Terragen 3'"
        logger.debug('procname is {}'.format(procname))
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
