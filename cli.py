# Command line interface for IGP Render Controller
# Must run in python 3

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



#import argparse
import os
import framechecker
import socketwrapper as sw

illegal_characters = [';', '&'] #not allowed in path

class Config(object):
    '''Object to hold config variables imported from server.'''
    def __init__(self, socket):
        self.sock = socket
        pass

    def get_server_cfg(self):
        '''Gets config info from the server.'''
        try:
            servercfg = self.sock.send_cmd('get_config_vars')
        except Exception as e:
            return e
        (
        self.computers, self.renice_list, 
        self.macs, self.blenderpath_mac, self.blenderpath_linux, 
        self.terragenpath_mac, self.terragenpath_linux, 
        self.allowed_filetypes, self.timeout, self.serverport,
        self.autostart, self.verbose, self.log_basepath 
        ) = servercfg
        return False



class Cli(object):
    '''Master object for command line interface.'''
    def __init__(self, host='localhost', port=2020):
        #var to contain all current server job attributes
        self.socket = sw.ClientSocket(host, port)
        self.cfg = Config(self.socket)
        self.cfg.get_server_cfg()
        self.serverjobs = self.socket.send_cmd('get_attrs')
        '''Need a list of integer IDs corresponding to jobs on the server to
        make manipulating them easier from the command line.  Because dict keys
        are not kept in any order, need to sort the list each time to make sure
        that job IDs don't change between listing and running a command.'''
        self.job_ids = sorted(self.serverjobs.keys())
        #remove the metadata
        self.autostart = self.serverjobs['__STATEVARS__']['autostart']
        self.job_ids.remove('__STATEVARS__')
        self.job_ids.remove('__MESSAGE__')
        self.fprint = FPrinter(self.cfg) #formatted printer object


    def list_jobs(self):
        '''Prints a list of jobs in queue with their job ID numbers.'''
        print('Listing all jobs on %s:%s\n' %self.socket.getaddr())
        self.fprint.jlist_header()
        for i in range(len(self.job_ids)):
            fname = self.job_ids[i]
            status = self.serverjobs[fname]['status']
            prog = self.serverjobs[fname]['progress']
            self.fprint.jlist(i, fname, status, prog)

    def print_single_job(self, job_id):
        '''Prints header for a single job, then prints its status info.'''
        self._print_job_info(job_id)

    def list_all(self):
        print('Printing full status info for all jobs on %s:%s' 
              %self.socket.getaddr())
        for i in range(len(self.job_ids)):
            self.fprint.job_separator(i)
            self._print_job_info(i)

    def _print_job_info(self, job_id):
        '''Prints complete status info for a given job.'''
        index = self.job_ids[job_id]
        job = self.serverjobs[index]
        elapsed, avg, remaining = job['times']
        self.fprint.jobsummary(
            job['path'], job['status'], job['progress'], elapsed, avg, remaining
            )
        colwidth = self.fprint.get_maxlen(self.cfg.computers) + 3
        self.fprint.complist_header(colwidth)
        for comp in self.cfg.computers:
            cs = self.serverjobs[index]['compstatus'][comp]
            if cs['active']:
                status = 'Active'
            else:
                if cs['frame']:
                    status = 'FAILED'
                else:
                    status = 'Inactive'
            self.fprint.complist(comp, status, cs['frame'], cs['progress'], 
                                 cs['error'], colwidth)
            

    def start_render(self, job_id):
        '''Start job with the given ID'''
        result = self.socket.send_cmd('start_render', self.job_ids[job_id])
        print(result)

    def kill_render(self, job_id):
        '''Kill render and all associated processes for given ID'''
        index = self.job_ids[job_id]
        if not input('This will stop rendering %s and attempt to kill all '
                     'related processes.  Continue? (Y/n): ' %index) == 'Y':
            print('Cancelled')
            return
        result = self.socket.send_cmd('kill_render', index, True)
        print(result)

    def resume_render(self, job_id):
        '''Resume a stopped render.'''
        result = self.socket.send_cmd('resume_render', self.job_ids[job_id], 
                                      True)
        print(result)

    def killall(self, program):
        '''Attempts to kill all instances of program.'''
        if not (program == 'terragen' or program =='blender'):
            print('Invalid argument. Must be "terragen" or "blender".')
            return
        if not input('This will attempt to kill all instances of %s '
                     'on all computers. Proceed? (Y/n): ' %program) == 'Y':
            print('Cancelled')
            return
        if program == 'terragen':
            result = self.socket.send_cmd('killall_tgn')
        elif program == 'blender':
            result = self.socket.send_cmd('killall_blender')
        print(result)

    def toggle_comp(self, job_id, computer):
        '''Toggle status of a computer for a given job.'''
        result = self.socket.send_cmd('toggle_comp', 
                                      self.job_ids[int(job_id)], computer)
        print(result)

    def checkframes(self):
        '''Checks a given directory for missing frames in a given range.'''
        path = input('Path to directory: ')
        start = int(input('Start frame: '))
        end = int(input('End frame: '))
        self.checker = framechecker.Framechecker(path, start, end)
        self.checker.calculate_indices()
        lists = self.checker.generate_lists()
        totalfiles = len(lists[1])
        missing = lists[-1]
        print('Directory contains %s items' %totalfiles)
        if not missing:
            print('No missing frames found')
        else:
            print('Missing frames:')
            for i in missing:
                print(i)

    def enqueue(self):
        '''Interactively puts a job in queue.'''
        path = input('Path to file: ')
        #make sure path is legal and index is available
        for char in illegal_characters:
            if char in path:
                print('Path contains illegal character(s)')
                return
        index = os.path.basename(path)
        if self.socket.send_cmd('job_exists', index):
            if input('Job with same index already exists. '
                     'Overwrite? (Y/n): ') != 'Y':
                return
        if path.endswith('blend'):
            render_engine = 'blend'
        elif path.endswith('tgd'):
            render_engine = 'tgd'
        else:
            print('File extension not recognized.  Project file must end '
                  'with ".blend" for Blender files or ".tgd" for '
                  'Terragen files.')
            return
        start = int(input('Start frame: '))
        end = int(input('End frame: '))
        extras = input('Extra frames: ')
        if extras:
            extraframes = [int(i) for i in extras.split()]
        else:
            extraframes = []
        comps = input('Computers (type "list" for a list of available '
                      'computers): ')
        if comps == 'list':
            print('This feature doesnt work yet')
            complist = input('Computers: ').split()
        else:
            complist = comps.split()
        for char in complist:
            if char in illegal_characters:
                print('Computer list contains illegal character(s)')
                return
        #All info collected. Ready to confirm then enqueue.
        print('Ready to place %s into queue.' %index)
        print('Path: %s\n'
              'Start frame: %s\t End frame: %s\t Extras: %s\n'
              'On %s' %(path, start, end, extras, ', '.join(complist)))
        if not input('Proceed? (Y/n): ') == 'Y':
            return
        kwargs = {
            'index':index,'path':path,'startframe':start, 'endframe':end,
            'extraframes':extraframes, 'render_engine':render_engine,
            'complist':complist, 'cachedata':False
            }
        reply = self.socket.send_cmd('enqueue', kwargs)
        print(reply)

    def toggle_autostart(self, mode):
        '''Attempts to set the server's autostart variable.  Mode can be
        "off", "on" or "get".  If mode is "get", the server's autostart
        status will be printed.'''
        print('called with', mode)
        print('self.autostart:', self.autostart)
        if mode == 'get':
            if not self.autostart:
                print('Autostart is currently disabled.')
            else:
                print('Autostart is currently enabled.')
        elif mode == 'on':
            if self.autostart:
                print('Autostart is currently enabled.')
            else:
                reply = self.socket.send_cmd('toggle_autostart')
                print(reply)
        elif mode == 'off':
            if self.autostart:
                reply = self.socket.send_cmd('toggle_autostart')
                print(reply)
            else:
                print('Autostart is currently disabled')
        else:
            print('Incorrect input. Optional switch values are "on" and "off".')




class FPrinter(object):
    '''Prints formatted data to stdout.'''

    def __init__(self, config):
        self.cfg = config

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
            timestr = (str(newtime[0])+'h '+str(newtime[1])+'m ' +
                       str(newtime[2])+'s')
        else:
            timestr = (str(newtime[0])+'d '+str(newtime[1])+'h ' + 
                       str(newtime[2])+'m '+str(newtime[3])+'s')
        return timestr

    def jobsummary(self, filename, status, progress, time_elapsed, 
                   time_avg, time_remaining):    
        header = ('Filename', 'Status', 'Progress', 'Elapsed', 'Avg./Fr.',
                  'Remaining')
        formatstr = '{:<20} {:<10} {:<9} {:<10} {:<10} {:<10}'

        etime = self.format_time(time_elapsed)
        avtime = self.format_time(time_avg)
        remtime = self.format_time(time_remaining)
        print(formatstr.format(*header))
        print('-'*70)
        print(formatstr.format(filename, status, round(progress, 1), etime, 
              avtime, remtime))

    def jlist_header(self):
        formatstr = '{:<4} {:<30} {:<10} {:<10}'
        print(formatstr.format('ID', 'Filename', 'Status', 'Progress'))
        print('-'*70)

    def jlist(self, job_id, filename, status, progress):
        formatstr = '{:<4} {:<30} {:<10} {:<10}'
        print(formatstr.format(job_id, filename, status, round(progress, 1)))

    def job_separator(self, job_id):
        print('\n%s ID: %s %s' %('#'*30, job_id, '#'*30))

    def get_maxlen(self, input_list):
        '''Accepts a list of strings, ints, or floats. Converts all to strings
        and returns the length of the longest item.'''
        maxlen = max([len(str(x)) for x in input_list])
        return maxlen

    def complist_header(self, colwidth):
        '''Print the header for a computer status list.  colwidth is the width
        of the first column in chars, used to keep lables aligned with computer
        lines.  All other columns are fixed width.'''
        formatstr = '{:<%s} {:<11} {:8} {:11} {:15}' %colwidth
        print(formatstr.format('Computer', 'Status', 'Frame', 'Progress', 
             'Error'))
        # Determine width of separator line based on col widths
        sep = colwidth + 11 + 8 + 11 + 15
        print('-'*sep)


    def complist(self, computer, status, frame, progress, error, colwidth):
        '''Print one line of status info for one computer.  colwidth is the 
        width of the first column in chars.  All others are fixed width.'''
        formatstr = '{!s:<%s} {!s:<11} {!s:<8} {!s:<11} {!s:<15}' %colwidth
        print(formatstr.format(computer, status, frame, round(progress, 1), 
              error))


    def truncate_filepath(self, path):
        '''Returns filepath truncated to fit current terminal width -4 chars.'''
        # Get current console width
        tsize = os.get_terminal_size() # returns obj with attrs columns and lines
        if len(path) > tsize.columns:
            head, tail = os.path.split(path)
            hlen = len(head)
            tlen = len(tail)
            n = 0
            while len(os.path.join(head, tail)) > tsize.columns - 4:
                # Try to truncate the head first, keeping at least 5 chars
                if hlen >= 5:
                    head = '%s...' %head[0:hlen]
                    hlen -= 1
                else:
                    # Truncate tail from the middle
                    tail = '%s...%s' %(tail[:tlen // 2 -n ], tail[tlen // 2 +n:])
                    n += 1
            path = os.path.join(head, tail)
        return path

    def get_time_width(self, timestring):
        '''Returns column width for a given time string.'''
        # Header needs at least 10 cols
        if len(timestring) > 6:
            width = len(timestring) + 4
        else:
            width = 10
        return width


    def jobsummary(self, filepath, status, progress, time_elapsed, 
                   time_avg, time_remaining):    
        header = ('Status:', 'Progress:', 'Elapsed:', 'Avg./Fr.:',
                  'Remaining:')

        etime = self.format_time(time_elapsed)
        avtime = self.format_time(time_avg)
        remtime = self.format_time(time_remaining)

        # Get widths of times
        ew = self.get_time_width(etime)
        aw = self.get_time_width(avtime)
        rw = self.get_time_width(remtime)

        formatstr = '{:<10} {:<10} {:<%s} {:<%s} {:<%s}' %(ew, aw, rw)
        print('File:')
        print(self.truncate_filepath(filepath) + '\n')
        print(formatstr.format(*header))
        print(formatstr.format(status, round(progress, 1), etime, 
              avtime, remtime) + '\n')


if __name__ == '__main__':
    print('Module containing command line interface methods for the IGP Render Controller.')


