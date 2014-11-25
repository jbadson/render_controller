'''When executed from a Blender .blend file: Converts all file
paths to relative, saves the file, exits.'''

import bpy

bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
bpy.ops.wm.quit_blender()
