#!/usr/bin/python3

#command line interface for IGP Render Controller
#must run in python 3

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
import os.path
import framechecker
import socketwrapper as sw

illegal_characters = [';', '&'] #not allowed in path

class Cli(object):
    '''Master object for command line interface.'''
    def __init__(self, host='localhost', port=2020):
        #var to contain all current server job attributes
        self.socket = sw.ClientSocket(host, port)
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
        self.fprint = FPrinter() #formatted printer object


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
        print('Full status info for ID %s\n' %job_id)
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
        self.fprint.jobsummary(index, job['status'], job['progress'], elapsed, 
                               avg, remaining)
        print('\nComputer status info:\n')
        self.fprint.complist_header()
        for comp in self.serverjobs[index]['complist']:
            cs = self.serverjobs[index]['compstatus'][comp]
            self.fprint.complist(comp, cs['frame'], cs['progress'], cs['active'],
                                 cs['error'])

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

    def complist_header(self):
        formatstr = '{:<20} {:<10} {:<10} {:<10} {}'
        print(formatstr.format('Computer', 'Frame', 'Progress', 'Active', 'Error'))
        print('-'*70)

    def complist(self, computer, frame, progress, active, error):
        formatstr = '{!s:<20} {!s:<10} {!s:<10} {!s:<10} {}'
        print(formatstr.format(computer, frame, round(progress, 1), active, 
              error))

    def job_separator(self, job_id):
        print('\n%s ID: %s %s' %('#'*30, job_id, '#'*30))




if __name__ == '__main__':
    print('Module containing command line interface methods for the IGP Render Controller.')


