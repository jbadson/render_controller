#workspace for exporting render status info to JSON document for web display

#export & basic parsing are working.  Need to find way to load JSON data into HTML/javascript repeatedly.

#might be too messy to dump all of renderJobs. Only necessary info is:
#job number
	#status
	#filename (maybe path)
	#startframe
	#endframe
	#extraframes
	#computer list
	#current global progress
	#current per-computer progress

#NOTE: index of dictionary must be clearly a string, i.e. it CANT CONTAIN ONLY NUMBERS
#NOTE: will probably be much easier to work with if each item is a dictionary entry with a clear key name

import json

jobs = dict()
for i in range(1, 6):
	jobs['job'+str(i)+'status'] = 'Rendering'
	jobs['job'+str(i)+'filename'] = 'test.blend'
	jobs['job'+str(i)+'startframe'] = 1
	jobs['job'+str(i)+'endframe'] = 20
	jobs['job'+str(i)+'extraframes'] = [22, 33, 44]
	jobs['job'+str(i)+'complist'] = ['comp1', 'comp2', 'comp3']
	jobs['job'+str(i)+'job_progress'] = 62 #percent
	jobs['job'+str(i)+'comp_progress'] = {'comp1':[1, 10], 'comp2':[2, 20], 'comp3':[3, 30]} #format is 'compname':[frame, progress %]

#try a separate dict for each job
job_1_output = dict()
job_1_output['job_number'] = 1
job_1_output['status'] = 'Rendering'
job_1_output['filename'] = 'test.blend'
job_1_output['startframe'] = 1
job_1_output['endframe'] = 20
job_1_output['extraframes'] = [22, 33, 44]
job_1_output['complist'] = ['comp1', 'comp2', 'comp3']
job_1_output['job_progress'] = 62 #percent
#there seems to be an issue with including nested dictionaries (can't figure out how to access indices).  Might need to reformat this as a list or something.
job_1_output['comp_progress'] = {'comp1':[1, 10], 'comp2':[2, 20], 'comp3':[3, 30]} #format is 'compname':[frame, progress %]

#NOTE: remember that dict can scramble index order, just need to call fields by name in javascript parser


print jobs 

fout = open('dump_test.json', 'w')
fout.write(json.dumps(jobs))
fout.close()
print('done')
