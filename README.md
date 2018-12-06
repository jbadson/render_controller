# RenderController
At the time I wrote this (spring 2014), I was working for a scientific animation group and we needed some free network rendering software. I was also interested in learning to code, so I decided this would be a good first project after "hello world".  It got the job done on both counts, but my lack of experience at the time really shows and there are many things that could have been done much, much better.

What this really needs is a complete rewrite from the ground up, but I moved on from that job in early 2016 and as far as I know nobody else is using this software. I don't see any reason to rewrite or continue maintaining it, but I decided to release a simplified version that should be a little easier for others to modify or maintain in the off chance somebody does have a use for it. This isn't a full rewrite, I just stripped out some incomplete features I was working on before changing jobs, refactored a few things, and made a few other changes that should hopefully make it a little less terrible.

# Major changes:
* Changed config file format to YAML
* Added required ssh_user parameter to server.conf
* Removed preferences window in GUI (all options now set in config file)
* Removed remote file caching
* Moved renderlog dir to /var/log/rcontroller
* Refactored code for simplicity and stability (still a lot of room for improvement)
* Restructured to allow packaging with setuptools

# Requirements:
* Linux or MacOS
* Python 3.4+
* pip for Python 3
* Tkinter (only needed for the GUI client)

# Installation
1. Install Dependencies
    * `RHEL/CentOS 7: yum install python34 python34-pip python34-tkinter`
2. Download and build the latest version
    * `git clone https://github.com/jbadson/render_controller.git`
    * `pip3 setup.py sdist`
3. Install with pip
    * `pip3 install dist/rendercontroller-{version}.tar.gz`

If you run into a cryptic error message like "error: can't copy 'conf/server.conf': doesn't exist or not a regular file" when building the pip package, try upgrading to the latest version of setuptools: `pip3 install --upgrade setuptools`


# REST API reference
/job/summary -> summary of all jobs on server
/job/new -> Start a new job
/job/status/{id} -> Detailed status for a given job
/job/start/{id} -> Start a given job
/job/stop/{id} -> Stop a given job
/job/enqueue/{id} -> Place a stopped job back in render queue
/job/delete/{id} -> Remove a given job from the server
/node/list -> List render nodes
/node/enable/{name}/{id} -> Enable a render node for a given job
/node/disable/{name}/{id} -> Disable a render node for a given job
/storage/ls -> List the contents of a directory on shared storage
    Filesystem access is restricted by the filesystem_base_dir config file setting.
/config/autostart -> Returns autostart state
/config/autostart/enable -> Enables autostart
/config/autostart/disable -> Disables autostart


# Render Queue, Status, and Autostart
New jobs are automatically placed in the render queue. If autostart is enabled, jobs will be rendered one at a time in the order in which they were submitted. If multiple renders are started manually, none will be started automatically until all active renders have finished. If autostart is not enabled, the render queue just represents the list of jobs available for rendering, but they must be manually started.

## Job Statuses
* Waiting: Job is in queue and waiting to be rendered.
* Stopped: Job was stopped by user. Stopped jobs are excluded from the render queue and will not be rendered without user intervention.  A user may either resume rendering the job by clicking the Start button, or may place it back in queue with the Enqueue button.
* Rendering: Job is actively rendering.
* Finished: Job is finished rendering.

## Here's the old overview:
This is a network rendering utility written for the Interactive Geology Projectat the University of Colorado Boulder (http://igp.colorado.edu).

### Basic features:
* Support for Blender's Cycles render engine and Planetside Terragen 3. Maya/Mental Ray coming soon.
* Runs in Mac OSX or Linux (Python 3.4+ required).
* Add or remove nodes from the render pool at any time.
* Queue up as many jobs as you want, they will start automatically one at a time.
* Automatic re-rendering of failed frames.
* Support for an unlimited number of nodes. (though the GUI can only display 20 or so on a 1080p monitor)
* Client-server architecture allows multiple users to simultaneously add, remove, start, stop, and check status of jobs.
* GUI and command line interfaces.
* Communicates with nodes by SSH. No clients or special software needed.
* All communication between the render controller and the nodes is done by SSH, so the nodes do not need to be on the same local network.
* Utility to check a directory for frames missing from a specified range of frame numbers.Dependencies:

