#rudimentary script for retrieving cpu and ram usage from linux machine

import subprocess

#top = subprocess.check_output('top -n 1', shell=True)
top = subprocess.check_output('cat /Users/jim/top_output', shell=True)

top_split = top.split('\n')
for line in top_split:
	if 'Cpu(s)' in line:
		cpu_line = line
	if 'Mem:' in line:
		mem_line = line

cpu_free = float(cpu_line.split()[4][:-1])
cpu_used = 100 - cpu_free #%CPU utilization

mem_used = int(mem_line[-4][:-1]) #memory used in MB
