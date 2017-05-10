#!/usr/bin/env python3

def server():
    """Launches the server"""
    import rendercontroller.server
    rendercontroller.server.main()


def gui():
    """Launches the GUI client"""
    import rendercontroller.gui
    master = rendercontroller.gui.main()


def cli(argv):
    """Command line interface
    
    Args:
    argv -- (list) List of args a la sys.argv
    """
    import argparse
    import rendercontroller.cli
    helpstr = ("A multi-platform, multi-engine network rendering service.\n"
        + "Launches GUI client if no options are supplied.\n")
    parser = argparse.ArgumentParser(helpstr)
    parser.add_argument('-s', '--server', action='store_true', default=False,
        help='Start rendercontroller server')
    parser.add_argument('-g', '--gui', action='store_true', default=False,
        help='Start GUI client (same as if no options are supplied)')
    parser.add_argument('-l', '--list', action='store_true', default=False, 
        dest='joblist', help='List all items in render queue.')
    parser.add_argument('-a', '--listall', action='store_true', 
        default=False, dest='listall', 
        help='Print full status info for all jobs in queue.')
    parser.add_argument('-i', '--info', action='store', default=-1,
        dest='info', help='Print full status info for job with given ID.',
        metavar='ID', type=int)
    parser.add_argument('--start', action='store', default=-1,
        dest='start', help='Start render for job witn given ID.', 
        metavar='ID', type=int)
    parser.add_argument('--stop', action='store', default=-1, dest='stop',
        help='Stop render for job with given ID.', metavar='ID', type=int)
    parser.add_argument('--resume', action='store', default=-1, 
        dest='resume', type=int, metavar='ID', 
        help='Resume a stopped job with a given ID.')
    parser.add_argument('--killall', dest='killall', default='',
        type=str, help='Kill all terragen or blender processes on all '
        'computers. Specify "blender" or "terragen".', metavar='PROG')
    parser.add_argument('-t', '--toggle', nargs=2, dest='toggle', 
        metavar=('ID', 'COMP'), help='Toggle computer render status.')
    parser.add_argument('--checkframes', action='store_true', default=False,
        dest='checkframes', help='Check a directory for missing frames.')
    parser.add_argument('-e', '--enqueue', action='store_true', default=False,
        dest='enqueue', help='Create a new job (interactive)')
    parser.add_argument('-p', '--port', action='store', dest='port', 
        default=2020, type=int, help='Port number.')
    parser.add_argument('-c', '--connect_to', action='store', dest='host',
        type=str, default='localhost', help='Hostname or IP for command-'
        'line interface to connect to. If none is specified, the '
        'default "localhost" will be used. This option is ignored if '
        '-s or -g options are used.')
    parser.add_argument('--autostart', action='store', dest='autostart',
        default=None, nargs='?', const='get',
        help='Without any additional options, prints the '
        'current autostart status. If "on" or "off" is specified, sets '
        'the autostart mode to the specified state.')

    args = parser.parse_args(argv)
    if args.server:
        server()
        return
    elif args.gui:
        gui()
        return
    interface = rendercontroller.cli.Cli(args.host, args.port)
    if args.joblist:
        interface.list_jobs()
    if args.info>= 0:
        interface.print_single_job(args.info)
    if args.listall:
        interface.list_all()
    if args.start >= 0:
        interface.start_render(args.start)
    if args.stop >= 0:
        interface.kill_render(args.stop)
    if args.resume >= 0:
        interface.resume_render(args.resume)
    if args.killall:
        interface.killall(args.killall)
    if args.toggle:
        job_id, comp = args.toggle
        interface.toggle_comp(job_id, comp)
    if args.checkframes:
        interface.checkframes()
    if args.enqueue:
        interface.enqueue()
    if args.autostart:
        interface.toggle_autostart(args.autostart)


def main():
    import sys
    if len(sys.argv) > 1:
        cli(sys.argv[1:])
    else:
        gui()

if __name__ == '__main__':
    main()
