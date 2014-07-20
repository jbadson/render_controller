#rudimentary script for retreiving cpu and ram utilization 
import subprocess

top = subprocess.check_output('top -l1', shell=True)

top_split = top.split('\n')
for line in top_split:
	if 'CPU usage' in line:
		cpu_line = line

	if 'PhysMem' in line:
		mem_line = line

print(cpu_line)
print(mem_line)

cpu_free = float(cpu_line.split()[-2][:-1])
cpu_used = 100 - cpu_free #%CPU utilization 
print(cpu_used)

mem_used = int(mem_line.split()[1][:-1]) #memory used in MB
print(mem_used)
