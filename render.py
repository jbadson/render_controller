#Fifth major revison of IGP render controller
#Written for Python 3.4
import queue
import threading
import time
import subprocess
import os
import socket
import ast
import json
import cfgfile

illegal_characters = [' ', ';', '&'] #not allowed in paths
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
        for computer in computers:
            self.compstatus[computer] = self._reset_compstatus(computer)
        self.path = None
        self.startframe = None
        self.endframe = None
        self.extraframes = []
        self.render_engine = None
        self.totalframes = []
        self.progress = None

    def _reset_compstatus(self, computer):
        '''Returns a compstatus dict containing default values'''
        if computer in self.complist:
            pool = True
        else:
            pool = False
        return {
            'active':False, 'frame':None, 'pid':None, 'timer':None, 
            'progress':0.0, 'error':None, 'pool':pool
            }

    def get_job_progress(self):
        '''Returns the percent complete for the job.'''
        if self.status == 'Rendering' or self.status == 'Stopped':
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
        self.path = path
        for char in illegal_characters:
            if char in path:
                return False
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes
        print('extraframes:', extraframes, type(extraframes))#debug

        self.render_engine = render_engine
        self.complist = complist
        for computer in self.complist:
            self.compstatus[computer]['pool'] = True

        print('enqueued')
        #Fill list of total frames with zeros
        #used for tracking percent complete
        self.totalframes = []
        for i in range(self.startframe, self.endframe + len(self.extraframes) + 1):
            self.totalframes.append(0)
        #create LifoQueue and put frames
        self.queue = queue.LifoQueue(0)
        framelist = list(range(self.startframe, self.endframe + 1))
        framelist.reverse()
        for frame in framelist:
            self.queue.put(frame)
        #render extraframes first, lowest number first
        #check again to make sure there are still extraframes
        if self.extraframes:
            print('self.extraframes', self.extraframes, type(self.extraframes))
            self.extraframes.sort()
            self.extraframes.reverse()
            for frame in self.extraframes:
                self.queue.put(frame)
        self.renderlog = RenderLog(self.path, self.startframe, self.endframe, 
                                   self.extraframes, self.complist)
        self.status = 'Waiting'
        return True

    def render(self):
        '''Starts a render for a given job.'''
        print('entered render()') #debug
        if self.status != 'Waiting':
            print('Job status is not "Waiting". Aborting render.')
            return False
        self.status = 'Rendering'
        self._start_timer()
        self.renderlog.start()

        self.skiplist = []
        self.killflag = False

        master = threading.Thread(target=self._masterthread, args=())
        master.start()
        return True

    def _masterthread(self):
        '''Main thread to control render process and create renderthreads.'''
        '''{'active':False, 'frame':None,
            'pid':None, 'timer':None, 'progress':0.0, 'error':None}'''
    
        print('started _masterthread()') #debug
        self.threads_active = False
        if self.render_engine == 'blend':
            tgt_thread = self._renderthread
        elif self.render_engine == 'tgd':
            tgt_thread = self._renderthread_tgn
        while True:
            if self.killflag:
                print('Kill flag detected, breaking render loop.')
                #deal with log & render timer
                break
    
            if self.queue.empty() and not self._threadsactive():
                print('Render done at detector.') #debug
                self.status = 'Finished'
                self._stop_timer()
                self.renderlog.finished(self.get_times())
                break
    
            for computer in computers:
                time.sleep(0.01)
                if not self.compstatus[computer]['pool']:
                    continue
                if (not self.compstatus[computer]['active'] and 
                        computer not in self.skiplist):
                    #break loop if queue becomes empty after new computer is added
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
                        print('creating renderthread') #debug
                        rthread = threading.Thread(target=tgt_thread, args=(frame, 
                                                   computer, self.queue))
                        rthread.start()
                #ignore computers in skiplist
                elif computer in self.skiplist:
                    continue
                #if computer is active, check its timeout status
                elif time.time() - self.compstatus[computer]['timer'] > timeout:
                    frame = self.compstatus[computer]['frame']
                    print('Frame ' + str(frame) + ' on ' + computer + 
                          ' timed out in render loop. Adding to skiplist')
                    self.skiplist.append(computer)
                    print('skiplist:', self.skiplist)#debug
                    self.kill_thread(computer)
                    with threadlock:
                        self.compstatus[computer]['active'] = False
                        self.compstatus[computer]['error'] = 'timeout'
                        self.renderlog.frame_failed(frame, computer, 'Timed out')

        print('_masterthread() terminating') #debug

    def _threadsactive(self):
        '''Returns true if instances of _renderthread() are active.'''
        for computer in self.compstatus:
            if self.compstatus[computer]['active']:
                return True
        print('_threadsactive() returning false') #debug
        return False

    def _renderthread(self, frame, computer, framequeue):
        '''Thread to send command, montor status, and parse return data for a
        single frame in Blender's Cycles render engine.  NOTE: This will not
        parse output from Blender's internal engine correctly.'''

        print('started _renderthread()', frame, computer ) #debug
        if computer in macs:
            renderpath = blenderpath_mac
        else:
            renderpath = blenderpath_linux
        command = subprocess.Popen(
            'ssh igp@' + computer + ' "' + renderpath +
             ' -b ' + self.path + ' -f ' + str(frame) + 
             ' & pgrep -n blender"', stdout=subprocess.PIPE, shell=True )
        for line in iter(command.stdout.readline, ''):
            #convert byte object to unicode string
            #necessary for Python 3.x compatibility
            line = line.decode('UTF-8')
            if not line:
                #pipe broken, 
                #assume render failed but wait for timeout in _masterthread
                print('no line in stdout from _renderthread(), breaking', computer)
                break
            #reset timeout timer every time an update is received
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            if verbose:
                with threadlock:
                    print(line)
            #calculate progress based on tiles
            if line.find('Fra:') >= 0 and line.find('Tile') >0:
                progress = self._parseline(line, frame, computer)
                with threadlock:
                    self.compstatus[computer]['progress'] = progress
            #detect PID at first line
            elif line.strip().isdigit():
                pid = line.strip()
                print('PID detected: ', pid)#debug
                with threadlock:
                    self.compstatus[computer]['pid'] = pid
                if computer in renice_list:
                    subprocess.call('ssh igp@' + computer + ' "renice 20 -p ' + 
                                     str(pid) + '"', shell=True)
                #remove oldest item from skiplist if render started successfully
                with threadlock:
                    if len(self.skiplist) > 0:
                        skipcomp = self.skiplist.pop(0)
                        self.compstatus[skipcomp] = (
                            self._reset_compstatus(skipcomp)
                            )
            #detect if frame has finished rendering
            elif line.find('Saved:') >= 0 and line.find('Time') >= 0:
                self.totalframes.append(frame)
                if 0 in self.totalframes:
                    self.totalframes.remove(0)
                framequeue.task_done()
                with threadlock:
                    self.compstatus[computer] = self._reset_compstatus(computer)

                #get final rendertime from blender's output
                rendertime = str(line[line.find('Time'):].split(' ')[1])
                print('Frame ' + str(frame) + ' finished after ' + rendertime)
                with threadlock:
                    self.renderlog.frame_recvd(frame, computer, rendertime)
                break
    
        #NOTE omitting stderr checking for now
        print('_renderthread() terminated', frame, computer) #debug

    def _renderthread_tgn(self, frame, computer, framequeue):
        '''Thread to send command, monitor status, and parse return data for a
        single frame in Terragen 3.'''

        print('started _renderthread_tgn()') #debug
        #pgrep string is different btw OSX and Linux so using whole cmd strings
        if computer in macs:
            cmd_string = ('ssh igp@'+computer+' "'+terragenpath_mac+' -p '
                          +self.path+' -hide -exit -r -f '+str(frame)
                          +' & pgrep -n Terragen&wait"')
        else:
            cmd_string = ('ssh igp@'+computer+' "'+terragenpath_linux+' -p '
                          +self.path+' -hide -exit -r -f '+str(frame)
                          +' & pgrep -n terragen&wait"')

        command = subprocess.Popen(cmd_string, stdout=subprocess.PIPE, shell=True)

        for line in iter(command.stdout.readline, ''):
            line = line.decode('UTF-8')
            if not line:
                #pipe broken, 
                #assume render failed but wait for timeout in _masterthread
                print('no line in stdout from _renderthread(), breaking', computer)
                break
            #reset timer
            with threadlock:
                self.compstatus[computer]['timer'] = time.time()
            if verbose:
                with threadlock:
                    print(line)

            #Terragen provides much less continuous status info, so parseline 
            #replaced with a few specific conditionals

            #starting overall render or one of the render passes
            if line.strip().isdigit():
                pid = int(line.strip())
                print('Possible PID detected: ', pid)
                if pid != frame: 
                    #necessary b/c terragen echoes frame # at start. 
                    #Hopefully PID will never be same as frame #
                    print('PID set to: '+str(pid)) #debugging
                    with threadlock:
                        self.compstatus[computer]['pid'] = pid
                    #renice process to lowest priority on specified comps 
                    if computer in renice_list: 
                        subprocess.call('ssh igp@'+computer+' "renice 20 -p '
                                        +str(pid)+'"', shell=True)
                        print('reniced PID '+str(pid)+' to pri 20 on '+computer)
                    #remove oldest item from skiplist if render starts successfully
                    with threadlock:
                        if len(self.skiplist) > 0:
                            skipcomp = self.skiplist.pop(0)
                            self.compstatus[skipcomp] = (
                                self._reset_compstatus(skipcomp)
                                )
            #starting a new render pass
            elif line.find('Starting') >= 0:
                ellipsis = line.find('...')
                passname = line[9:ellipsis]
                print('Fra:'+str(frame)+'|'+computer+'|Starting '+passname)

            #finished one of the render passes
            elif line.find('Rendered') >= 0:
                mark = line.find('of ')
                passname = line[mark+3:]
                print('|Fra:'+str(frame)+'|'+computer+'|Finished '+passname)

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
                print('Frame '+str(frame)+' on '+computer+' '+str(percent)+'%')
                with threadlock:
                    self.compstatus[computer]['progress'] = percent
            #frame is done rendering
            elif line.find('Finished') >= 0:
                self.totalframes.append(frame)
                if 0 in self.totalframes:
                    self.totalframes.remove(0)
                framequeue.task_done()
                with threadlock:
                    self.compstatus[computer] = self._reset_compstatus(computer)
                rendertime = str(line.split()[2][:-1])
                print('Frame ' + str(frame) + ' finished after ' + rendertime)
                with threadlock:
                    self.renderlog.frame_recvd(frame, computer, rendertime)
                break
            #NOTE: omitting stderr testing for now
        print('_renderthread_tgn() terminated', frame, computer) #debug

    def _parseline(self, line, frame, computer):
        '''Parses Blender cycles progress and returns it in a compact form.'''
        tiles, total = line.split('|')[-1].split(' ')[-1].split('/')
        tiles = float(tiles)
        total = float(total)
        percent = tiles / total * 100
        return percent

    def _start_timer(self):
        '''Starts the render timer for the job.'''
        if self.status == 'Stopped':
            #account for time elapsed since render was stopped
            self.starttime = time.time() - (self.stoptime - self.starttime)
        else:
            self.starttime = time.time()

    def _stop_timer(self):
        '''Stops the render timer for the job.'''
        self.stoptime = time.time()

    def get_times(self):
        '''Returns elapsed time, avg time per frame, and estimated time remaining.
        Units are float seconds.'''
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
            'times':self.get_times()
            }
        return attrdict

    def add_computer(self, computer):
        if self.compstatus[computer]['pool']:
            return False
        else:
            self.complist.append(computer)
            self.compstatus[computer]['pool'] = True
            if self.status == 'Rendering':
                with threadlock:
                    self.renderlog.computer_added(computer)
            return True

    def remove_computer(self, computer):
        if not self.compstatus[computer]['pool']:
            return False
        else:
            self.complist.remove(computer)
            self.compstatus[computer]['pool'] = False
            if self.status == 'Rendering':
                with threadlock:
                    self.renderlog.computer_removed(computer)
            return True

    def kill_thread(self, computer):
        '''Attempts to terminate active render thread on a specified computer.'''
        if not self.compstatus[computer]['active']:
            return False
        try:
            frame = self.compstatus[computer]['frame']
            pid = self.compstatus[computer]['pid']
            if not frame > 0 and pid > 0:
                raise RuntimeError
        except Exception:
            return False
        #remove computer from pool unless render is being stopped
        if self.compstatus[computer]['pool'] and self.status != 'Stopped':
            self.remove_computer(computer)
        with threadlock:
            self.queue.put(frame)
        subprocess.call('ssh igp@'+computer+' "kill '+str(pid)+'"', shell=True)
        with threadlock:
            self.compstatus[computer]['active'] = False
            self.compstatus[computer]['error'] = 'killed'
            self.renderlog.process_killed(pid, computer)
        return pid

    def kill_now(self):
        '''Kills job and all currently rendering frames'''
        if not self.status == 'Rendering':
            return False
        self.killflag = True
        self._stop_timer()
        with threadlock:
            self.renderlog.stop(self.get_times())
        self.status = 'Stopped'
        for computer in computers:
            try:
                if self.compstatus[computer]['active']:
                    self.kill_thread(computer)
            except Exception:
                pass
        return True

    def kill_later(self, finalstatus='Stopped'):
        '''Kills job but allows any currently rendering frames to finish.
        NOTE: Does not monitor progress of currently rendering frames, so if they
        do not finish there will be missing frames, or if job is immediately
        resumed there may be multiple render processes running on each computer
        until the old frames finish.

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

    def resume(self, startnow):
        '''Resumes a render that was previously stopped. If startnow == False,
        render will be placed in queue with status 'Waiting' but not started.'''
        if self.status != 'Stopped':
            return False
        self.killflag = False
        for computer in computers:
            self._reset_compstatus(computer)
        self.status = 'Waiting'
        if startnow:
            self.render()
            return True
        else:
            return True

    def autostart(self):
        '''Handles starting the current job from the check_autostart function.'''
        if self.status == 'Waiting':
            print('got to autostart() with status waiting')
            self.render()
        else:
            self.status = 'Stopped'
            print('got to autostart() with status not waiting')
            self.resume(startnow=True)

    def set_priority(self, priority):
        if priority == self.priority:
            return False
        self.priority = priority
        return True


class RenderLog(Job):
    '''Logs render progress for a given job.  Log instance is created when
    job is placed in queue, but actual log file is not created until render
    is started. Time in filename reflects time job was placed in queue.'''
    hrule = '=' * 70 + '\n' #for printing thick horizontal line
    def __init__(self, path, startframe, endframe, extraframes, complist):
        self.path = path
        self.startframe = startframe
        self.endframe = endframe
        self.extraframes = extraframes
        self.complist = complist
        self.log_basepath = log_basepath
        self.filename, ext = os.path.splitext(os.path.basename(self.path))
        self.enq_time = time.strftime('%Y-%m-%d_%H%M%S', time.localtime())
        self.logpath = (self.log_basepath + self.filename + '.' 
                        + self.enq_time + '.txt')
        self.total = str(len(range(startframe, endframe)) + 1 + len(extraframes))

    def _gettime(self):
        '''Returns current time as string formatted for timestamps.'''
        timestamp = time.strftime('%H:%M:%S %Y/%m/%d', time.localtime())
        return timestamp

    def start(self):
        '''Creates initial entry corresponding to render start.'''
        #check if file exists. If so, assume render is being resumed
        if os.path.exists(self.logpath):
            self._resume()
            return
        with open(self.logpath, 'w') as log:
            log.write(RenderLog.hrule)
            log.write('Render started at ' + self._gettime() + '\n')
            log.write('File: ' + self.path + '\n')
            log.write('Frames: ' + str(self.startframe) + ' - ' 
                      + str(self.endframe) + ', ' + str(self.extraframes) + '\n')
            log.write('On: ' + ', '.join(self.complist) + '\n')
            log.write(RenderLog.hrule)

    def frame_sent(self, frame, computer):
        with open(self.logpath, 'a') as log:
            log.write('Sent frame ' + str(frame) + ' of ' + self.total + ' to '
                      + computer + ' at ' + self._gettime() + '\n')

    def frame_recvd(self, frame, computer, rendertime):
        with open(self.logpath, 'a') as log:
            log.write('Received frame ' + str(frame) + ' of ' + self.total 
                      + ' from ' + computer + ' at ' + self._gettime() + 
                      '. Render time was ' + rendertime + '\n')

    def frame_failed(self, frame, computer, errtxt):
        with open(self.logpath, 'a') as log:
            log.write('ERROR: Frame ' + str(frame) + ' failed to render on ' 
                      + computer + ' at ' + self._gettime() + ': ' + errtxt + '\n')

    def process_killed(self, pid, computer):
        with open(self.logpath, 'a') as log:
            log.write('Killed process ' + str(pid) + ' on ' + computer + ' at '
                      + self._gettime() + '\n')

    def computer_added(self, computer):
        with open(self.logpath, 'a') as log:
            log.write('Added ' + computer + ' to render pool at ' 
                      + self._gettime() + '\n')

    def computer_removed(self, computer):
        with open(self.logpath, 'a') as log:
            log.write('Removed ' + computer + ' from render pool at ' 
                      + self._gettime() + '\n')

    def finished(self, times):
        '''Marks render finished, closes log file.'''
        elapsed, avg, rem = times
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render finished at ' + self._gettime() + '\n')
            log.write('Total time: ' + self.format_time(elapsed) + '\n')
            log.write('Average time per frame: ' + self.format_time(avg) + '\n')
            log.write(RenderLog.hrule)

    def stop(self, times):
        '''Marks render stopped, closes log file.'''
        elapsed, avg, rem = times
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render stopped by user at ' + self._gettime() + '\n')
            log.write('Total time: ' + self.format_time(elapsed) + '\n')
            log.write('Average time per frame: ' + self.format_time(avg) + '\n')
            log.write(RenderLog.hrule)

    def _resume(self):
        '''Appends a new header to the existing log file.'''
        with open(self.logpath, 'a') as log:
            log.write(RenderLog.hrule)
            log.write('Render resumed at ' + self._gettime() + '\n')
            log.write('File: ' + self.path + '\n')
            log.write('Frames: ' + str(self.startframe) + ' - ' 
                      + str(self.endframe) + ', ' + str(self.extraframes) + '\n')
            log.write('On: ' + ', '.join(self.complist) + '\n')
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


def check_autostart():
    '''Starts next job and returns true if global autostart is enabled 
    and new job is ready.'''
    proceed_statuses = ['Waiting', 'Paused']
    #first check for high priority jobs
    times = {}
    #get list of all high priority jobs
    for index in renderjobs:
        if renderjobs[index].priority == 'High':
            #if high pri job is rendering, assume it's the oldest and move on
            if renderjobs[index].status == 'Rendering':
                print('High priority render in progress:', index)
                return False
            elif renderjobs[index].status in proceed_statuses:
                queuetime = renderjobs[index].queuetime
                times[queuetime] = index
    #if ready high pri jobs were found but none were running, start the oldest
    if times:
        index = times[min(times)]
        #stop all other renders
        for job in renderjobs:
            if renderjobs[job].status == 'Rendering':
                print('killing ', job)
                renderjobs[job].kill_later(finalstatus='Paused')
        print('Autostart found high priority job. Stopping all renders, '
              'starting render of ' + str(index))
        renderjobs[index].autostart()
        return True
    #if no high priority renders, run the normal autostart algorithm
    renders = 0 #number of currently-running renders
    for index in renderjobs:
        if renderjobs[index].status == 'Rendering':
            renders += 1
    if renders >= maxglobalrenders:
        return False
    times = {}
    for index in renderjobs:
        if renderjobs[index].status in proceed_statuses:
            queuetime = renderjobs[index].queuetime
            times[queuetime] = index
    if times:
        index = times[min(times)]
        print('Autostart: starting', index)
        renderjobs[index].autostart() 
        return True
    return False


def update_loop():
    '''Handles miscellaneous tasks that need to be carried out on a regular
    interval. Runs in separate thread to prevent blocking other processes.'''
    while True:
        if autostart:
            check_autostart()
        time.sleep(30)


#----------GLOBAL VARIABLES----------
threadlock = threading.RLock()



#----------DEFAULTS / CONFIG FILE----------
def set_defaults():
    '''Restores all config settings to default values. Used for creating
            initial config file or restoring it if corrupted.'''

    #create list of all computers available for rendering
    computers = [ 
        'bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente', 'lindsey', 'wetterhorn', 'lincoln', 'humberto', 
        'tabeguache', 'smaug', 'conundrum', 'paradox'
        ] 
    
    #list of computers in the 'fast' group
    fast = [
        'bierstadt', 'massive', 'sneffels', 'sherman', 'the-holy-cross', 
        'eldiente'
        ] 
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
    
    terragenpath_mac = ('/mnt/data/software/terragen_rendernode/osx/terragen3.app'                         '/Contents/MacOS/Terragen_3')
    
    terragenpath_linux = '/mnt/data/software/terragen_rendernode/linux/terragen'
    
    #allowed file extensions (last 3 chars only) for check_missing_files
    allowed_filetypes = [
        '.png', '.jpg', '.peg', '.gif', '.tif', '.iff', '.exr', '.PNG', 
        '.JPG', '.PEG', '.GIF', '.TIF', '.IFF', '.EXR'] 
    
    #timeout for failed machine in seconds
    timeout = 600
    
    #start next job when current one finishes. 1=yes, 0=no, on by default
    autostart = 1 
    
    #maximum number of simultaneous renders for the start_next_job() function
    maxglobalrenders = 1 

    #terminal output verbose. 0 = normal, 1 = write everything from render 
    #stdout to terminal
    verbose = 0

    #default directory to hold render log files
    log_basepath = '/mnt/data/renderlogs/'

    defaults = [
        computers, fast, farm, renice_list, macs,
        blenderpath_mac, blenderpath_linux, terragenpath_mac, 
        terragenpath_linux, allowed_filetypes, timeout, autostart, 
        maxglobalrenders, verbose, log_basepath
        ]

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
    global autostart
    global maxglobalrenders
    global verbose
    global log_basepath

    print('Global config variables updated.')
    cfgsettings = settings
    '''
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
    autostart = settings[11]
    maxglobalrenders = settings[12]
    verbose = settings[13]
    log_basepath = settings[14]
    '''
    (
    computers, fast, farm, renice_list, macs, blenderpath_mac,
    blenderpath_linux, terragenpath_mac, terragenpath_linux,
    allowed_filetypes, timeout, autostart, maxglobalrenders,
    verbose, log_basepath
    ) = settings

#Create ConfigFile instance with default path & filename
#file will be stored in same directory as this file and called config.json
config_file = cfgfile.ConfigFile()
#if file already exists and is valid, load config vars. Otherwise make new file.
if not config_file.exists():
    print('No config file found, creating one from defaults.')
    cfgsettings = config_file.write(set_defaults())
else:
    print('Config file found, reading...')
    try:
        cfgsettings = config_file.read()
        if not len(cfgsettings) == len(set_defaults()):
            raise IndexError
    except Exception:
        print('Config file corrupt or incorrect. Creating new')
        cfgsettings = config_file.write(set_defaults())


#now define variables in main based on cfgsettings
define_global_config_vars(cfgsettings)

def update_cfgfile():
    cfgsettings = [
        computers, fast, farm, renice_list, macs,  
        blenderpath_mac, blenderpath_linux, terragenpath_mac, 
        terragenpath_linux, allowed_filetypes, timeout, autostart, 
        maxglobalrenders, verbose, log_basepath
        ]
    print('Updating config file.')
    config_file.write(cfgsettings)

def quit():
    '''Forces immediate exit without waiting for loops to terminate.'''
    os._exit(1)

#verify that renderlog path is accessible
if not os.path.exists(log_basepath):
    print('WARNING: Path to renderlog directory: "'+log_basepath
            +'" could not be found.')
    if input('Do you want to specify a new path now? (Y/n)') == 'Y':
        log_basepath = input('Path:')
        if not os.path.exists(log_basepath):
            print('Path does not exist, shutting down server.')
            quit()
        elif log_basepath[-1] != '/':
            log_basepath = log_basepath + '/'
        print('Render logs will be stored in ' + log_basepath + '.\n' + 
              'To permanently change the log path, use the Preferences window ' + 
              'in the client GUI or edit the server config file.')
    else:
        print('Server start failed, no renderlog path.')
        quit()


#----------SERVER INTERFACE----------

'''
Client-server command-response protocol:

### Client ###      ### Server ###
send command   -->  receive command
                        |
                    validate command
                        |
receive report <--  report validation
    |
    |
send cmd args  -->  execute command w/args
                        |
                        |
receive result <--  report return string/result

Each connection from a client receives its own instance of ClientThread. This
thread checks the command against a list of valid commands, reports success or
failure of validation to the client, then executes the command with arguments 
supplied in a dict (kwargs) transmitted as a JSON string. It then reports the 
data returned from the function to the client. This can be a simple success/fail 
indicator, or it can be whatever data the client has requested also formatted as 
a JSON string..

For this reason, there are some rules for functions that directly carry out 
requests from client threads:

    1. The name of the function must be in the allowed_commands list.

    2. The function must accept the kwargs argument, even if it isn't used.

    3. The function must return something on completion. It can be any type of 
       object as long as it's compatible with python's json.dumps and json.loads.

'''


class ClientThread(threading.Thread):
    '''Subclass of threading.Thread to encapsulate client connections'''

    def __init__(self, clientsocket):
        self.clientsocket = clientsocket
        threading.Thread.__init__(self, target=self._clientthread)

    def _sendmsg(self, message):
        '''Wrapper for socket.sendall() that formats message for client.    
        Message must be compatible with json.dumps/json.loads.'''
        #now converting everything to a json string for web interface convenience
        message = json.dumps(message)
        msg = bytes(message, 'UTF-8')
        msglen = str(len(msg))
        #first 8 bytes contains message length 
        while len(msglen) < 8:
            msglen = '0' + msglen
        msglen = bytes(msglen, 'UTF-8')
        self.clientsocket.sendall(msglen)
        self.clientsocket.sendall(msg)

    def _recvall(self):
        '''Receives a message of a specified length, returns original type.'''
        #first 8 bytes contain msg length
        msglen = int(self.clientsocket.recv(8).decode('UTF-8'))
        bytes_recvd = 0
        chunks = []
        while bytes_recvd < msglen:
            chunk = self.clientsocket.recv(2048)
            if not chunk:
                break
            chunks.append(chunk.decode('UTF-8'))
            bytes_recvd += len(chunk)
        data = json.loads(''.join(chunks))
        return data

    def _clientthread(self):
        command = self._recvall()
        #don't print anything if request is for status update
        if not command == 'get_attrs': print('received command', command)
        #validate command first
        if not command in allowed_commands:
            self._sendmsg('False')
            if not command == 'get_attrs': print('command invalid')
            return
        else:
            self._sendmsg('True')
            if not command == 'get_attrs': print('command valid')
        #now get the args
        kwargs = self._recvall()
        if not command == 'get_attrs': print('received kwargs', kwargs)
        return_str = eval(command)(kwargs)
        if not command == 'get_attrs': print('sending return_str', return_str)
        #send the return string (T/F for success or fail, or other requested data)
        self._sendmsg(return_str)
        self.clientsocket.close()






#---Functions to carry out command requests from clients---

#list of permitted commands
#must match function names exactly
allowed_commands= [
    'cmdtest', 'get_attrs', 'job_exists', 'enqueue',
    'start_render', 'toggle_comp', 'kill_single_thread', 'kill_render',
    'get_status', 'resume_render', 'clear_job', 'get_config_vars', 'create_job',
    'toggle_verbose', 'toggle_autostart', 'check_path_exists', 'set_job_priority'
    ]

def cmdtest(kwargs):
    '''a basic test of client-server command-response protocol'''
    print('cmdtest() called')
    for arg in kwargs:
        print('arg:', arg, kwargs[arg])
    return 'cmdtest() success'

def get_attrs(kwargs=None):
    '''Returns dict of attributes for a given index. If no index is specified,
    returns a dict containing key:dictionary pairs for every job instance
    on the server where key is the job's index and the dict contains all of
    its attributes.

    Also if no index is specified, an entry called _EXTRA_ will be appended
    that contains non-job-related information about the server state that
    needs to be updated in client GUIs immediately.'''
    if kwargs:
        index = kwargs['index']
        if not index in renderjobs:
            return 'Index not found.'
        else:
            attrdict = renderjobs[index].get_attrs()
            return attrdict
    #if no index specified, send everything
    attrdict = {}
    for i in renderjobs:
        attrdict[i] = renderjobs[i].get_attrs()
    #append non-job-related update info
    attrdict['_EXTRA_'] = {'autostart':autostart, 'verbose':verbose}
    return attrdict

def job_exists(kwargs):
    '''Returns True if index is in renderjobs.'''
    index = kwargs['index']
    if index in renderjobs:
        return True
    else:
        return False

def enqueue(kwargs):
    '''Enqueue a job from client.'''
    index = kwargs['index']
    path = kwargs['path']
    for char in illegal_characters:
        if char in path:
            return 'Enqueue failed, illegal characters in path'
    startframe = kwargs['startframe']
    endframe = kwargs['endframe']
    extras = kwargs['extraframes']
    render_engine = kwargs['render_engine']
    complist = kwargs['complist']
    print('extraframes:', extras, type(extras))#debug
    #create the job
    if index in renderjobs:
        if renderjobs[index].status == 'Rendering':
            return 'Failed to create job'
    renderjobs[index] = Job()
    #place it in queue
    reply = renderjobs[index].enqueue(
        path, startframe, endframe, render_engine, complist, 
        extraframes=extras
        )
    if reply:
        return (index + ' successfully placed in queue')
    else:
        del renderjobs[index]
        return 'Enqueue failed, job deleted'

def start_render(kwargs):
    '''Start a render at the request of client.'''
    index = kwargs['index']
    reply = renderjobs[index].render()
    if reply:
        return index + ' render started'
    else:
        return 'Failed to start render.'

def toggle_comp(kwargs):
    index = kwargs['index']
    computer = kwargs['computer']
    if renderjobs[index].get_comp_status(computer)['pool']:
        reply = renderjobs[index].remove_computer(computer)
        if reply: return computer+' removed from render pool for '+str(index)
    else:
        reply = renderjobs[index].add_computer(computer)
        if reply: return computer+ ' added to render pool for '+str(index)
    return 'Failed to toggle computer status.'

def kill_single_thread(kwargs):
    index = kwargs['index']
    computer = kwargs['computer']
    reply = renderjobs[index].kill_thread(computer)
    if reply:
        pid = reply
        return 'Sent kill signal for pid '+str(pid)+' on '+computer
    else:
        return 'Failed to kill thread.'

def kill_render(kwargs):
    index = kwargs['index']
    kill_now = kwargs['kill_now']
    if kill_now:
        reply = renderjobs[index].kill_now()
        if reply:
            return 'Killed render and all associated processes for '+str(index)
    else:
        reply = renderjobs[index].kill_later()
        if reply:
            return ('Killed render of '+str(index)+' but all '
                    'currently-rendering processes will be allowed to finish.')
    return 'Failed to kill render for job '+str(index)

def resume_render(kwargs):
    index = kwargs['index']
    startnow = kwargs['startnow']
    reply = renderjobs[index].resume(startnow)
    if reply:
        return 'Resumed render of ' + str(index)
    else:
        return 'Failed to resume render of ' + str(index)

def get_status(kwargs):
    '''Returns status string for a given job.'''
    index = kwargs['index']
    status = renderjobs[index].status
    return status

def clear_job(kwargs):
    '''Clears an existing job from a queue slot.'''
    index = kwargs['index']
    del renderjobs[index]
    return index + ' deleted.'

def get_config_vars(kwargs=None):
    '''Gets server-side configuration variables and returns them as a list.'''
    cfgsettings = [
        computers, fast, farm, renice_list, macs,  
        blenderpath_mac, blenderpath_linux, terragenpath_mac, 
        terragenpath_linux, allowed_filetypes, timeout, autostart, 
        maxglobalrenders, verbose, log_basepath
        ]
    return cfgsettings

def toggle_verbose(kwargs=None):
    '''Toggles the state of the verbose variable.'''
    global verbose
    if verbose == 0:
        verbose = 1
        return 'verbose reporting enabled'
    else:
        verbose = 0
        return 'verbose reporting disabled'

def toggle_autostart(kwargs=None):
    '''Toggles the state of the autostart variable.'''
    global autostart
    if autostart == 0:
        autostart = 1
        return 'autostart enabled'
    else:
        autostart = 0
        return 'autostart disabled'

def check_path_exists(kwargs=None):
    '''Checks if a path is accessible from the server (exists) and that it's an 
    regular file. Returns True if yes.'''
    path = kwargs['path']
    if os.path.exists(path) and os.path.isfile(path):
        return True
    else:
        return False

def set_job_priority(kwargs):
    '''Sets the render priority for a given index.'''
    index = kwargs['index']
    priority = kwargs['priority']
    if not index in renderjobs:
        return 'Index not found'
    if renderjobs[index].set_priority(priority):
        return 'Priority of ' + index + ' set to ' + str(priority)
    else:
        return 'Priority not changed'





if __name__ == '__main__':
    renderjobs = {}
    updatethread = threading.Thread(target=update_loop)
    updatethread.start()

    #socket server to handle interface interactions
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    host = '' #all interfaces
    hostname = socket.gethostname()
    port = 2020
    s.bind((host, port))
    s.listen(5)
    print('Server now running on ' + hostname + ' port ' + str(port))
    print('Press Crtl + C to stop...')
    while True:
        try:
            clientsocket, address = s.accept()
            #print('Client connected from ', address)
            client_thread = ClientThread(clientsocket)
            client_thread.start()
        except KeyboardInterrupt:
            print('Shutting down server')
            #close the server socket cleanly if user interrupts the loop
            s.close()
            quit()
    s.close()


