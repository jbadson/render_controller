This is a network rendering utility written for the Interactive Geology Project
at the University of Colorado Boulder (http://igp.colorado.edu).

The purpose of this software is to distribute the workload of rendering 3D 
animations across multiple computers.  It works by distributing one frame to 
each computer, tracking the progress, and sending new frames as computers 
become available.  It also includes several other useful render-related 
utilities.

The main differences between this and some other network rendering software 
out there are: 1) It supports multiple render engines (currently Blender's 
Cycles and Terragen 3, Maya/Mental Ray coming soon), 2) It's free, and 3) It 
was a good excuse to learn how to code.

It's still in a very early stage and is being developed to fill the specific 
needs of the project, but it's my long term goal to generalize it and make it 
available for other users.  Of course you're free to download and use it now, 
but be warned that some features are not yet working or only partially working, 
it may require significant work to adapt it to your needs, and I might 
radically change it at any time.  Feel free to contact me at 
james.adson@colorado.edu for more info.

Basic features:
    -Support for Blender's Cycles render engine and Planetside Terragen 3. 
     Maya/Mental Ray coming soon.
    -Runs in Mac OSX or Linux (Python 3.4 required).
    -Add or remove computers from the render pool at any time.
    -Queue up as many jobs as you want, they will start automatically 
     one at a time.
    -Automatic re-rendering of failed frames.
    -Support for an unlimited number of computers. 
     (though now GUI is only set up for a small number, less than 20 or so)
    -Main functionality is a lightweight command line or daemon process.
    -Client with graphical user interface that allows multiple users to check 
     render progress, add or remove jobs from the queue, add or remove 
     computers from the render pool, and access other functions.
    -No special software needed on render nodes.
     (other than the render engine, of course). 
    -All communication between the render controller and the nodes is done by 
     SSH, so the nodes do not need to be on the same local network.
    -Access project files from a shared volume or automatically cache files 
     locally on render nodes.
    -Utility to check a directory for frames missing from a specified range of 
     frame numbers.

As a final warning, this is pretty much my first attempt at programming after 
Hello World.  I'm gradually making changes as I learn more about how things 
should be done, but don't be surprised if some things are done in a silly or 
needlessly complex way.  I'll fix things as I get to them, but the bottom line 
is this was written to fill an immediate need at work and that's still the 
primary focus of development.
