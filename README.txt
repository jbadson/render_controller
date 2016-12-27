At the time I wrote this (spring 2014), I was working for a scientific
animation group and we needed some free network rendering software. I was
also interested in learning to code, so I decided this would be a good
first project after "hello world".  It got the job done on both counts,
but my lack of experience at the time really shows and there are many
things that could have been done much, much better.

What this really needs is a complete rewrite from the ground up, but I moved 
on from that job in early 2016 and as far as I know nobody else is using 
this software. I don't see any reason to rewrite or continue maintaining it, 
but in the off chance somebody does have a use for it, I decided to release 
a simplified version that should be a little easier for others to modify or 
maintain. This isn't a full rewrite, I just stripped out some incomplete 
features I was working on before changing jobs, refactored a few things, 
and made a few other changes that should hopefully make it a little less 
terrible.

Major changes:
    -Changed config file format to YAML
    -Added required ssh_user parameter to server.conf
    -Removed remote file caching
    -Removed preferences window in GUI (just edit conf files)
    -Moved renderlog dir to /var/log/rcontroller

Here's the old overview:

This is a network rendering utility written for the Interactive Geology Project
at the University of Colorado Boulder (http://igp.colorado.edu).

Basic features:
    -Support for Blender's Cycles render engine and Planetside Terragen 3. 
     Maya/Mental Ray coming soon.
    -Runs in Mac OSX or Linux (Python 3.4+ required).
    -Add or remove nodes from the render pool at any time.
    -Queue up as many jobs as you want, they will start automatically 
     one at a time.
    -Automatic re-rendering of failed frames.
    -Support for an unlimited number of nodes. 
     (though the GUI can only display 20 or so on a 1080p monitor)
    -Client-server architecture allows multiple users to simultaneously add,
     remove, start, stop, and check status of jobs.
    -GUI and command line interfaces.
    -Communicates with nodes by SSH. No clients or special software needed.
    -All communication between the render controller and the nodes is done by 
     SSH, so the nodes do not need to be on the same local network.
    -Utility to check a directory for frames missing from a specified range of 
     frame numbers.

Dependencies:
    - Mac OS or Linux
    - Python 3.4+
    - tkinter
    - pyyaml
