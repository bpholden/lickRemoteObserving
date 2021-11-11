#!/usr/env/python

## Import General Tools
import os
import re
import stat
import sys

import argparse
import atexit
import datetime
import getpass
import logging
import math
import pathlib
import socket
import subprocess
import telnetlib
import threading
import time
import traceback
import warnings

import yaml

import soundplay

__version__ = '1.2'

##-------------------------------------------------------------------------
## Start from command line
##-------------------------------------------------------------------------
def main():
    #catch all exceptions so we can exit gracefully
    try:
        lvl = LickVncLauncher() # create the main object
        create_logger() #
        lvl.log = logging.getLogger('KRO')
        lvl.start()
    except Exception as error:
        lvl.handle_fatal_error(error)

##-------------------------------------------------------------------------
## Create logger
##-------------------------------------------------------------------------
def create_logger():
    '''
    create_logger()
    Makes a logging instance.

    Currently this is a global variable, which is then attached to
    the lick_vnc_launcher object.

    '''
    try:
        ## Create logger object
        log = logging.getLogger('KRO')
        log.setLevel(logging.DEBUG)

        #create log file and log dir if not exist
        ymd = datetime.datetime.utcnow().date().strftime('%Y%m%d')
        pathlib.Path('logs/').mkdir(parents=True, exist_ok=True)

        #file handler (full debug logging)
        logFile = f'logs/lick-remote-log-utc-{ymd}.txt'
        logFileHandler = logging.FileHandler(logFile)
        logFileHandler.setLevel(logging.DEBUG)
        logFormat = logging.Formatter('%(asctime)s UT - %(levelname)s: %(message)s')
        logFormat.converter = time.gmtime
        logFileHandler.setFormatter(logFormat)
        log.addHandler(logFileHandler)

        #stream/console handler (info+ only)
        logConsoleHandler = logging.StreamHandler()
        logConsoleHandler.setLevel(logging.INFO)
        logFormat = logging.Formatter(' %(levelname)8s: %(message)s')
        logFormat.converter = time.gmtime
        logConsoleHandler.setFormatter(logFormat)

        log.addHandler(logConsoleHandler)

    except Exception as error:
        print(str(error))
        print(f"ERROR: Unable to create logger at {logFile}")
        print("Make sure you have write access to this directory.\n")
        log.info("EXITING APP\n")
        sys.exit(1)


##-------------------------------------------------------------------------
## Class definitions
##-------------------------------------------------------------------------

class VNCSession(object):
    '''An object to contain information about a VNC session.
    '''
    def __init__(self, name=None, display=None, desktop=None, user=None, pid=None):
        if name is None and display is not None:
            name = ''.join(desktop.split()[1:])
        self.name = name
        self.display = display
        self.desktop = desktop
        self.user = user
        self.pid = pid

    def __repr__(self):
        return f"  {self.name:12s} {self.display:5s} {self.desktop:s}"

class LickVncLauncher(object):
    '''Fundamental object for starting, managing and closing VNC sessions to Lick.
    The object has a number of methods but the basic construction should look like
    this:
            lvl = LickVncLauncher() # instantize object
            create_logger()  # create a location for logging
            lvl.log = logging.getLogger('KRO') # link log object to VNC object
            lvl.start() # now start the whole process

    '''
    def __init__(self):
        #init vars we need to shutdown app properly
        self.config  = None
        self.sound   = None
        self.tel        = None

        self.ports_in_use   = {}
        self.vnc_threads    = []
        self.vnc_processes  = []
        self.sessions_found = []

        self.vncserver  = None
        self.vncviewer    = None
        self.vncargs      = None
        self.vncprefix    = None
        self.vncviewonly  = False
        self.tigervnc     = False

        self.ssh_forward      = True
        self.connection_valid = False

        #ssh key constants
        self.ssh_pkey           = 'lick_id_rsa'
        self.ssh_key_valid      = False
        self.ssh_account        = 'user'
        self.ssh_server         = 'shimmy.ucolick.org'
        self.ssh_additional_kex = '+diffie-hellman-group1-sha1'

        self.exit = False

        self.check_cmd      = None
        self.check_cmd_args = None

        self.soundplayer   = None
        self.soundplaytags = ":1,:2,:3,:4,:5,:6"
        self.aplay         = None
        self.pv            = None


        self.servers_to_try = {'shane' : 'shimmy.ucolick.org',
                                   'nickel' : 'noir.ucolick.org',
                                   'apf' : 'frankfurt.apf.ucolick.org'}
        self.soundservers = {'shane' : 'shimmy.ucolick.org',
                                   'nickel' : 'noir.ucolick.org',
                                   'apf' : 'frankfurt.apf.ucolick.org'}

        self.geometry = list()
        self.vncviewer_has_geometry = False
        self.screens = [[0,0]]

        #default start sessions
        self.DEFAULT_SESSIONS = [
            'Kast blue',
            'Kast red',
            'Kast Guider Camera',
            'Kast Spare 1',
            'Kast Spare 2',
            'Kast Spare 3'
        ]

        #NOTE: 'status' session on different server and always on port 1,
        # so assign localport to constant to avoid conflict
        self.STATUS_PORT       = ':1'
        self.LOCAL_PORT_START  = 5901




    ##-------------------------------------------------------------------------
    ## Start point (main)
    ##-------------------------------------------------------------------------
    def start(self):
        '''
        start(self) - the whole event sequence, includes parsing of arguments
        from command line, reading and checking the configuration,
        making connections, managing them, and providing a menu of options
        for the user.
        '''
        ##---------------------------------------------------------------------
        ## Parse command line args and get config
        ##---------------------------------------------------------------------
        self.log.debug("\n***** PROGRAM STARTED *****\nCommand: "+' '.join(sys.argv))

        self.args = create_parser()
        if self.args.account not in ['shane','nickel','apf']:
            self.exit_app('A valid account (shane or nickel) must be specified.')
        self.get_config()
        self.check_config()

        ##---------------------------------------------------------------------
        ## Log basic system info
        ##---------------------------------------------------------------------
        self.log_system_info()
        self.check_version()

        self.get_vncviewer_properties()
        self.get_display_info()
        self.how_check_local_port()

        if self.args.test:
            self.test_functions()
            self.exit_app("Started in test mode, exiting after tests run.")



        ##---------------------------------------------------------------------
        ## Determine telescope
        ##---------------------------------------------------------------------
        self.determine_tel(self.args.account)
        if not self.tel:
            self.exit_app(f'Invalid telescope account: "{self.args.account}"')


        ##---------------------------------------------------------------------
        ## Validate connection and ssh key
        ##---------------------------------------------------------------------

        self.validate_connection()
        if not self.connection_valid:
            self.log.error("\n\n\tCould not validate connection, is your VPN working?\n\t"\
                          "Contact sa@ucolick.org "\
                          "if the VPN is on but this test fails.\n")
            self.exit_app()

        ##---------------------------------------------------------------------
        ## Determine VNC Sessions
        ##---------------------------------------------------------------------
        if self.args.authonly:
            self.exit_app("Connection can be made.")

        self.sessions_found = self.get_vnc_sessions(self.ssh_account)

        if not self.sessions_found or len(self.sessions_found) == 0:
            self.exit_app('No VNC sessions found')


        ##---------------------------------------------------------------------
        ## Open requested sessions
        ##---------------------------------------------------------------------
        self.calc_window_geometry()
#         self.ssh_threads  = []
        self.ports_in_use = {}
        self.vnc_threads  = []
        self.vnc_processes = []
        for s in self.sessions_found:
            self.start_vnc_session(s.display)


        ##---------------------------------------------------------------------
        ## Open Soundplay
        ##---------------------------------------------------------------------
        sound = None
        if self.args.nosound is False and self.config.get('nosound', False) != True:
            self.start_soundplay()


        ##---------------------------------------------------------------------
        ## Wait for quit signal, then all done
        ##---------------------------------------------------------------------
        atexit.register(self.exit_app, msg="App exit")
        self.prompt_menu()
        self.exit_app()



    ##-------------------------------------------------------------------------
    ## Start VNC session
    ##-------------------------------------------------------------------------
    def start_vnc_session(self, session_display):
        '''
        start_vnc_session(self, session_display)

        Makes a VNC session connection to a session named session_display.
        The name must be in the list of allowed sessions stored in self.
        Makes a ssh connection using the stored credentials to the host
        stored in the self as self.vncserver.
        '''


#         try:
        #get session data by name
        session = None
        for s in self.sessions_found:
                if s.display == session_display:
                        session = s
                        break

        if not session:
            self.log.error(f"No server VNC session found for '{session_display}'.")
            self.print_sessions_found()
            return
        self.log.info(f"Opening VNCviewer for '{session.desktop}'")
        #determine vncserver (only different for "status")
        vncserver = self.vncserver

        #get remote port
        display   = int(session.display)
        port      = int(f"59{display:02d}")

        ## If authenticating, open SSH tunnel for appropriate ports
        if self.ssh_forward:

            #determine account and password
            account  = self.ssh_account if self.ssh_key_valid else self.args.account
            password = None

            # determine if there is already a tunnel for this session
            local_port = None
            for p in self.ports_in_use.keys():
                if session_display == self.ports_in_use[p][1]:
                    local_port = p
                    self.log.info(f"Found existing SSH tunnel on port {port}")
                    vncserver = 'localhost'
                    break

            #open ssh tunnel
            if local_port is None:
                try:
                    local_port = self.open_ssh_tunnel(vncserver, account, password,
                                                    self.ssh_pkey, port, None,
                                                    session_name=session_display)
                except:
                    self.log.error(f"Failed to open SSH tunnel for "
                              f"{account}@{vncserver}:{port}")
                    trace = traceback.format_exc()
                    self.log.debug(trace)
                    return
                vncserver = 'localhost'
        else:
            local_port = port




        #If vncviewer is not defined, then prompt them to open manually and
        # return now
        if self.vncviewer in [None, 'None', 'none']:
            self.log.info(f"\nNo VNC viewer application specified")
            self.log.info(f"Open your VNC viewer manually\n")
            return

        #determine geometry
        geometry = None
        if self.vncviewer_has_geometry is None:
            self.get_vncviewer_properties()
        if self.vncviewer_has_geometry is True and len(self.geometry) > 0:
            i = len(self.vnc_threads) % len(self.geometry)
            geometry = self.geometry[i]

        ## Open vncviewer as separate thread
        self.vnc_threads.append(threading.Thread(target=self.launch_vncviewer,
                                       args=(vncserver, local_port, geometry)))
        self.vnc_threads[-1].start()
        time.sleep(0.05)



    ##-------------------------------------------------------------------------
    ## Get Configuration
    ##-------------------------------------------------------------------------
    def get_config(self):
        '''
        get_config(self)

        If the config option is passed an as argument,
        this checks that file first.
        If the config option is not passed, the config
        file must be stored in one of two locations:

        local_config.yaml
        lick_vnc_config.yaml

        Reads and parses the first file, if it exists, then the second.

        The configuration is then attached to self.config
        '''
        #define files to try loading in order of pref
        filenames=['local_config.yaml', 'lick_vnc_config.yaml']

        #if config file specified, put that at beginning of list
        filename = self.args.config
        if filename is not None:
            if not pathlib.Path(filename).is_file():
                self.log.error(f'Specified config file "{filename}" does not exist.')
                self.exit_app()
            else:
                filenames.insert(0, filename)

        #find first file that exists
        file = None
        for f in filenames:
            if pathlib.Path(f).is_file():
                file = f
                break
        if not file:
            self.log.error(f'No config files found in list: {filenames}')
            self.exit_app()

        #load config file and make sure it has the info we need
        self.log.info(f'Using config file:\n {file}')

        # open file a first time just to log the raw contents
        with open(file) as FO:
            contents = FO.read()
#             lines = contents.split('/n')
        self.log.debug(f"Contents of config file: {contents}")

        # open file a second time to properly read config
        with open(file) as FO:
            config = yaml.load(FO, Loader=yaml.FullLoader)

        for key in ['vncviewer', 'soundplayer', 'aplay']:
            if key in config.keys():
                config[key] = os.path.expanduser(config[key])
                config[key] = os.path.expandvars(config[key])


        cstr = "Parsed Configuration:\n"
        for key, c in config.items():
            cstr += f"\t{key} = " + str(c) + "\n"
        self.log.debug(cstr)

        self.config = config


    ##-------------------------------------------------------------------------
    ## Check Configuration
    ##-------------------------------------------------------------------------
    def check_config(self):
        '''
        check_config(self)

        This checks the vnc arguments in the config, namely the
        vncviewer
        vncargs
        vncprefix

        If the appropriate files do exist, this will throw an warning.
        '''
        #check for vncviewer
        #NOTE: Ok if not specified, we will tell them to open vncviewer manually
        #todo: check if valid cmd path?
        self.vncviewer = self.config.get('vncviewer', None)
        self.vncargs = self.config.get('vncargs', None)
        self.vncprefix = self.config.get('vncprefix', '')
        if not self.vncviewer:
            self.log.warning("Config parameter 'vncviewer' undefined.")
            self.log.warning("You may need to open your vnc viewer manually.\n")
            rv = self.guess_vncviewer()
            if rv is None:
                self.log.warning("No good guess!\n")


        #checks local port start config
        self.local_port = self.LOCAL_PORT_START
        lps = self.config.get('local_port_start', None)
        if lps: self.local_port = lps


        #check ssh_pkeys
        filepath = os.path.dirname(os.path.abspath(__file__))
        self.ssh_pkey = os.path.join(filepath,self.ssh_pkey)
        if not self.ssh_pkey:
            self.log.warning("No ssh private key file specified in config file.\n")
            sys.exit()
        else:
            if not pathlib.Path(self.ssh_pkey).exists():
                self.log.warning(f"SSH private key path does not exist: {self.ssh_pkey}")
                sys.exit()

        self.aplay        = self.config.get('aplay', None)
        self.soundplayer  = self.config.get('soundplayer', None)
        sysinfo = os.uname()
        if self.soundplayer is not None:
            if sysinfo.sysname == 'Darwin' and 'linux' in self.soundplayer :
                self.log.warning(f"Running {self.soundplayer} is incompatible with a {sysinfo.sysname} host")
                self.soundplayer = 'soundplay-107050-8.6.3-macosx10.5-ix86+x86_64'
                self.log.warning(f"Reseting to {self.soundplayer} ")
                self.pv = '0.01'
            elif sysinfo.sysname == 'Linux' and 'macos' in self.soundplayer:
                self.log.warning(f"Running {self.soundplayer} is incompatible with a {sysinfo.sysname} host")
                self.soundplayer = 'soundplay-107098-8.6.3-linux-x86_64'
                self.log.warning(f"Reseting to {self.soundplayer} ")

        soundplaytags = self.config.get('soundplaytags', None)
        if soundplaytags is None:
            self.soundplaytags = self.args.tags
        else:
            self.soundplaytags = soundplaytags


    ##-------------------------------------------------------------------------
    ## Log basic system info
    ##-------------------------------------------------------------------------
    def log_system_info(self):
        '''
        log_system_info(self)

        Logs basics about the host running the software.
        '''
        try:
            self.log.debug(f'System Info: {os.uname()}')
        except:
            self.log.debug("os.uname() did not work, hopefully we are on a Windows box")
            trace = traceback.format_exc()
            self.log.debug(trace)

        try:
            hostname = socket.gethostname()
            self.log.debug(f'System hostname: {hostname}')
            # ip = socket.gethostbyname(hostname)
            # self.log.debug(f'System IP Address: {ip}')
            python_version_str = sys.version.replace("\n", " ")
            self.log.info(f'Python {python_version_str}')
            self.log.info(f'Remote Observing Software Version = {__version__}')
        except :
            self.log.error("Unable to log system info.")
            trace = traceback.format_exc()
            self.log.debug(trace)

    #------------------------------------------------------------------------
    # get some basic properties of the vncviewer
    #------------------------------------------------------------------------
    def get_vncviewer_properties(self):
        '''Determine whether we are using TigerVNC
        '''
        vncviewercmd = self.config.get('vncviewer', 'vncviewer')
        viewonly = self.config.get('vncviewonly',0)
        if viewonly == 1:
            self.vncviewonly = True
        if self.args.viewonly:
            self.vncviewonly = True


        cmd = [vncviewercmd, '--help']
        self.log.debug(f'Checking VNC viewer: {" ".join(cmd)}')
        result = subprocess.run(cmd, capture_output=True)
        output = result.stdout.decode() + '\n' + result.stderr.decode()
        if re.search(r'TigerVNC', output):
            self.log.info(f'We ARE using TigerVNC')
            self.tigervnc = True
        else:
            self.log.debug(f'We ARE NOT using TigerVNC')
            self.tigervnc = False

        if re.search(r'[Gg]eometry', output):
            self.log.info(f'Found geometry argument')
            self.vncviewer_has_geometry = True
        else:
            self.log.debug(f'Could not find geometry argument')
            self.vncviewer_has_geometry = False


    ##-------------------------------------------------------------------------
    ## Print sessions found for telescope
    ##-------------------------------------------------------------------------
    def print_sessions_found(self):
        '''
        print_sessions_found(self)

        Prints to stdout the sessions.

        '''
        print(f"\nSessions found for account '{self.args.account}':")
        for s in self.sessions_found:
            display   = int(s.display)
            print(f"  59{display:02d} {s.name:s}")


    ##-------------------------------------------------------------------------
    ## List Open Tunnels
    ##-------------------------------------------------------------------------
    def list_tunnels(self):
        '''
        list_tunnels(self)

        Lists the tunnels, handy for understanding why a VNC window or
        a soundplay connection dissappeared.
        '''
        if len(self.ports_in_use) == 0:
            print(f"No SSH tunnels opened by this program")
        else:
            print(f"\nSSH tunnels:")
            print(f"  Local Port | Desktop   | Remote Connection")
            for p in self.ports_in_use.keys():
                desktop = self.ports_in_use[p][1]
                remote_connection = self.ports_in_use[p][0]
                print(f"  {p:10d} | {desktop:9s} | {remote_connection:s}")



    ##-------------------------------------------------------------------------
    ## Open ssh tunnel
    ##-------------------------------------------------------------------------
    def open_ssh_tunnel(self, server, username, password, ssh_pkey, remote_port,
                        local_port=None, session_name='unknown'):
        '''
        open_ssh_tunnel(self, server, username, password, ssh_pkey, remote_port,
                        local_port=None, session_name='unknown')

        One of the core functions, this sets up the SSH tunnel required to
        forward the VNC or soundplay connection from the remote observing host to
        the observers local machine.

        server - host to make connection to
        username - username for account to ssh to, always an observing account
        password - if the ssh key requires a password
        ssh_pkey - the public key for the username on server
        remote_port - the port number for the connection, usually a VNC port or
            the sound play port
        local_port  - if None, grabs the next available local port not in use,
            else uses the value passed in
        session_name - the name of the session at the remote observing host

        '''
        #get next local port if need be
        #NOTE: Try up to 100 ports beyond
        if not local_port:
            for i in range(0,100):
                if self.is_local_port_in_use(self.local_port):
                    self.local_port += 1
                    continue
                else:
                    local_port = self.local_port
                    self.local_port += 1
                    break

        #if we can't find an open port, error and return
        if not local_port:
            self.log.error(f"Could not find an open local port for SSH tunnel "
                           f"to {username}@{server}:{remote_port}")
            self.local_port = self.LOCAL_PORT_START
            return False

        #log
        address_and_port = f"{username}@{server}:{remote_port}"
        self.log.info(f"Opening SSH tunnel for {address_and_port} "
                 f"on local port {local_port}.")

        # build the command
        forwarding = f"{local_port}:localhost:{remote_port}"
        command = ['ssh', '-l', username, '-L', forwarding, '-N', '-T', server]
        command.append('-oStrictHostKeyChecking=no')
        command.append('-oCompression=yes')
        if self.ssh_additional_kex is not None:
            command.append('-oKexAlgorithms=' + self.ssh_additional_kex)

        if ssh_pkey is not None:
            command.append('-i')
            command.append(ssh_pkey)

        self.log.debug('ssh command: ' + ' '.join (command))
        null = subprocess.DEVNULL
        proc = subprocess.Popen(command,stdin=null,stdout=null,stderr=null)


        # Having started the process let's make sure it's actually running.
        # First try polling,  then confirm the requested local port is in use.
        # It's a fatal error if either check fails.

        if proc.poll() is not None:
            raise RuntimeError('subprocess failed to execute ssh')

        checks = 50
        while checks > 0:
            result = self.is_local_port_in_use(local_port)
            if result == True:
                break
            else:
                checks -= 1
                time.sleep(0.1)

        if checks == 0:
            raise RuntimeError('ssh tunnel failed to open after 5 seconds')

        in_use = [address_and_port, session_name, proc]
        self.ports_in_use[local_port] = in_use

        return local_port


    ##-------------------------------------------------------------------------
    ##-------------------------------------------------------------------------
    def how_check_local_port(self):
        '''
        how_check_local_port(self)

        This examines the output of various commands on the observers local
        host.
        The purpose is to find the correct command to find open ports.
        Prefers in order ss,lsof, netstat.exe (Windows System for Linux)
        and then ps.  ps does not always work the way one would like as
        a process may not have an actual open port even if it claims the
        port was open.
        '''

        self.check_cmd = self.config.get('check_cmd', None)

        if self.check_cmd is None:
            self.check_cmd = self.args.check

        if self.check_cmd in ("ps","ss","lsof","netstat.exe"):
            try:
                cmd = subprocess.check_output(['which', self.check_cmd])
                return
            except:
                self.log.debug(f"{self.args.check} is not found")

        for tst_cmd in ("ss","lsof","netstat.exe","ps"):
            try:
                cmd = subprocess.check_output(['which', tst_cmd])
                self.check_cmd = tst_cmd
                return
            except subprocess.CalledProcessError:
                self.log.debug(f"{tst_cmd} is not found")


        return

    ##-------------------------------------------------------------------------
    ##-------------------------------------------------------------------------
    def is_local_port_in_use(self, port):
        '''
        is_local_port_in_use(self, port)

        port - the port number of interest

        Checks if port is in use or open. Uses the method
        determined by how_check_local_port()

        '''
        if self.check_cmd == 'netstat.exe':
            cmd = f'netstat.exe -an | grep ":{port}"'
        elif self.check_cmd == 'ss':
            cmd = f'ss -l | grep ":{port}"'
        elif self.check_cmd == 'lsof':
            cmd = f'lsof -i -P -n | grep LISTEN | grep ":{port} (LISTEN)" | grep -v grep'
        elif self.check_cmd == 'ps':
            cmd = f'ps aux | grep "{port}:" | grep -v grep'

        self.log.debug(f'Checking for port {port} in use: {cmd}')
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        data = proc.communicate()[0]
        data = data.decode("utf-8").strip()
        lines = data.split('\n') if data else list()
        if lines:
            self.log.debug(f"Port {port} is in use.")
            return True
        else:
            return False

    ##-------------------------------------------------------------------------
    ## Guess which vncviewerCmd to use if not specified
    ##-------------------------------------------------------------------------

    def guess_vncviewer(self):
        '''
        guess_vncviewer(self)

        If the vncviewer is not defined by the config file, this
        function will attempt guess it.

        '''

        try:
            sysinfo = os.uname()
            if sysinfo.sysname == 'Darwin':
                self.vncviewer = 'open'
                self.vncprefix = 'vnc://'
                self.vncargs = None
                # this should work
                return True
            elif sysinfo.sysname == 'Linux':
                # we are out on a limb Here
                self.vncviewer = 'vncviewer'
                self.vncprefix = ''
                self.vncargs = None
                return False
        except:
            return False

    ##-------------------------------------------------------------------------
    ## Launch vncviewer
    ##-------------------------------------------------------------------------
    def launch_vncviewer(self, vncserver, port, geometry=None):
        '''
        launch_vncviewer(self, vncserver, port, geometry=None)

        vncserver - remote host to connect to and open the VNC session
        port - remote port to connect for VNC session


        '''
        vncviewercmd   = self.vncviewer
        vncprefix      = self.vncprefix
        vncargs        = self.vncargs

        if self.tigervnc and self.vncviewonly:
            vncargs += ' -ViewOnly=1'
        elif self.vncviewer == '/Applications/VNC Viewer.app/Contents/MacOS/vncviewer' and self.vncviewonly:
            vncargs += ' SendPointerEvents=0'

        cmd = [vncviewercmd]
        if vncargs:
            vncargs = vncargs.split()
            cmd = cmd + vncargs

        #todo: make this config on/off so it doesn't break things
        if geometry:
            cmd.append(f'-geometry={geometry}')
        if vncviewercmd == "open":
            cmd.append(f'{vncprefix}{vncserver}:{port:4d}')
        else:
            cmd.append(f'{vncprefix}{vncserver}::{port:4d}')

        self.log.debug(f"VNC viewer command: {cmd}")
        null = subprocess.DEVNULL
        proc = subprocess.Popen(cmd,stdin=null,stdout=null,stderr=null)

        #append to proc list so we can terminate on app exit
        self.vnc_processes.append(proc)


    ##-------------------------------------------------------------------------
    ## Start soundplay
    ##-------------------------------------------------------------------------
    def start_soundplay(self):
        '''
        start_soundplay(self)

        Begins the soundplay connection, this is a separate object
        referenced by self.sound
        Uses the values from the configuration to determine the
        correct executables to use.

        '''
        try:
            #check for existing first and shutdown
            if self.sound:
                self.sound.terminate()

            #config vars
            sound_port   = 9798
            sound_server = self.soundservers[self.tel]
            sound_server = sound_server

            if self.soundplayer is None:
                self.guess_soundplay()
            if self.soundplayer is not None and 'macos' in self.soundplayer :
                self.pv = '0.01'

            #Do we need ssh tunnel for this?
            if self.ssh_forward:

                account  = self.ssh_account if self.ssh_key_valid else self.args.account
                password = None
                sound_port = self.open_ssh_tunnel(sound_server, account,
                                                  password, self.ssh_pkey,
                                                  sound_port,
                                                  local_port=sound_port,
                                                    session_name='soundplay')
                if not sound_port:
                    return
                else:
                    sound_server = 'localhost'

            self.sound = soundplay.soundplay()
            self.sound.connect(self.soundplaytags, sound_server, sound_port,
                               aplay=self.aplay, player=self.soundplayer,
                               pv=self.pv)
        except Exception:
            self.log.error('Unable to start soundplay.  See log for details.')
            trace = traceback.format_exc()
            self.log.debug(trace)


    ##-------------------------------------------------------------------------
    ## Play a test sound to see if sound works
    ##-------------------------------------------------------------------------
    def play_test_sound(self):

        if self.config.get('nosound', False) is True:
            self.log.warning('Sounds are not enabled on this install.  See config file.')
            return

        # Build the soundplay test command.
        self.soundplayer = self.config.get('soundplayer', None)
        soundplayer = soundplay.full_path(self.soundplayer)

        command = [soundplayer, '-l']

        self.log.info('Calling: ' + ' '.join (command))
        test_sound_STDOUT = subprocess.check_output(command)
        for line in test_sound_STDOUT.decode().split('\n'):
            self.log.debug(f'  {line}')

    ##-------------------------------------------------------------------------
    ## Guess which soundplay to use if not specified
    ##-------------------------------------------------------------------------

    def guess_soundplay(self):
        '''
        guess_soundplay(self)

        Guesses the sound play executable to use if it is not specified.
        '''
        try:
            sysinfo = os.uname()
            if sysinfo.sysname == 'Darwin':
                self.soundplayer = 'soundplay-107050-8.6.3-macosx10.5-ix86+x86_64'
                self.pv = '0.01'
            elif sysinfo.sysname == 'Linux':
                self.soundplayer = 'soundplay-107098-8.6.3-linux-x86_64'

        except:
            return



    ##-------------------------------------------------------------------------
    ## Determine telescope
    ##-------------------------------------------------------------------------
    def determine_tel(self, account):
        '''

        determine_tel(self, account)

        account - the name of the telescope to be connected to.


        '''
        if account is None:
            return

        instruments = {'apf' : 'apf',
                           'shane' : 'kast',
                           'nickel' : 'nickel'}

        telescope = ('apf','shane','nickel')

        if account.lower() in telescope:
            self.tel = account.lower()

        return


    ##-------------------------------------------------------------------------
    ## Utility function for opening ssh client, executing command and closing
    ##-------------------------------------------------------------------------
    def do_ssh_cmd(self, cmd, server, account, timeout=10):
        '''
        do_ssh_cmd(self, cmd, server, account, timeout=10)

        cmd - command to execute on remote host
        server  - remote host to ssh to
        account - the account to use on the remote host
        timeout - amount of time in seconds to wait


        '''
        output = None
        self.log.debug(f'Trying SSH connect to {server} as {account}:')
        command = ['ssh', server, '-l', account, '-T']

        if self.ssh_pkey is not None:
            command.append('-i')
            command.append(self.ssh_pkey)

        command.append(cmd)
        self.log.debug('ssh command: ' + ' '.join (command))

        pipe = subprocess.PIPE
        null = subprocess.DEVNULL
        stdout = subprocess.STDOUT
        stdin = null

        proc = subprocess.Popen(command, stdin=stdin, stdout=pipe, stderr=stdout)
        if proc.poll() is not None:
            raise RuntimeError('subprocess failed to execute ssh')

        try:
            stdout,stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout,stderr = proc.communicate(timeout=timeout)
            self.log.error('  Timeout')
            
        if proc.returncode != 0:
            message = '  command failed with error ' + str(proc.returncode)
            self.log.error(message)

        stdout = stdout.decode()
        stdout = stdout.strip()
        self.log.debug(f"Output: '{stdout}'")

        # The first line might be a warning about accepting a ssh host key.
        # Check for that, and get rid of it from the output.

        lines = stdout.split('\n')

        output = []

        for ln in lines:
            if 'Warning: ' in ln:
                self.log.debug('Removed warning from command output:')
                self.log.debug(ln)
            else:
                output.append(ln)
        stdout = '\n'.join(output)

        return stdout
    ##-------------------------------------------------------------------------
    ## Validate connection
    ##-------------------------------------------------------------------------
    def validate_connection(self):

        '''
        validate_connection(self)

        Checks if the ssh key is valid by connecting to a remote host
        and running a simple command.

        The hosts that are use to attempt to make conections are those
        listed in the self.servers_to_try dictionary. The self.tel
        determine which host.

        '''

        self.log.info(f"Validating connection...")
        if self.tel is None:
            self.log.error(" Cannot conncet with undefined telescope")
            return

        if self.change_mod() is False:
            self.log.error(" Cannot ensure that the ssh key has the correct permissions")
            return

        cmds = ['/usr/sbin/netstat','/sbin/ip']
        correct_cmd = None
        for cmd in cmds:
            if correct_cmd is None:
                try:
                    data = subprocess.check_output(['which', cmd])
                    self.log.info(f'  Command {cmd} found')
                except Exception as e:
                    self.log.debug('  Failed to find command ' +str(cmd) + ' ' + str(e))
                    data = None
                if data:
                    correct_cmd = cmd

        flags = ''
        if correct_cmd == '/usr/sbin/netstat':
            flags = '-nr'
        if correct_cmd == '/sbin/ip':
            flags = 'route'
        if correct_cmd:
            cmd = f"{correct_cmd} {flags} | grep 128.114"
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
            data = proc.communicate()[0]
            data = data.decode("utf-8").strip()
            lines = data.split('\n') if data else list()
            if len(lines) > 0:
                self.connection_valid = True


        if self.connection_valid:
            self.log.info(" Connection  OK")
        else:
            self.log.error("  Connection failed - check VPN connection, is it running?")

    ##-------------------------------------------------------------------------
    ## Ensure that the ssh key file has the right mode
    ##-------------------------------------------------------------------------
    def change_mod(self):
        '''
        change_mod(self)

        Sets the mode of the ssh key to the correct values for ssh.

        '''
        # find file
        rv = False
        cpath = os.path.dirname(os.path.abspath(__file__))
        fullpath = os.path.join(cpath,self.ssh_pkey)
        if not os.path.exists:
            self.log.error(f"RSA key {fullpath} does not exist")
            return rv
        # check mode
        # set mode to 400
        try:
            os.chmod(fullpath,stat.S_IRUSR)
            rv = True
        except:
            self.log.error(f"Cannot set {fullpath} to the correct mode, ssh may fail")

        return rv

    ##-------------------------------------------------------------------------
    ## Determine VNC Sessions
    ##-------------------------------------------------------------------------
    def get_vnc_sessions(self, account):
        '''
        get_vnc_sessions(self, account)


        account - account on vncserver running the VNC sessions

        Connects to vncserver through account using do_ssh_cmd.
        Runs the remote task vncstatus and finds the VNC sessions associated
        with the telescope

        '''

        self.vncserver = self.servers_to_try[self.tel]
        vncserver = self.vncserver

        self.log.info(f"Connecting to {account}@{vncserver} to get VNC sessions list")

        sessions = []
        cmd = f"vncstatus"
        try:
            data = self.do_ssh_cmd(cmd, vncserver, account)
        except Exception as e:
            self.log.error('  Failed: ' + str(e))
            trace = traceback.format_exc()
            self.log.debug(trace)
            data = ''

        if data:
            self.ssh_key_valid = True
            lns = data.split("\n")
            for ln in lns:
                if ln[0] != "#":
                    fields = ln.split('-')
                    display = fields[0].strip()
                    if display == 'Usage':
                        # this should not happen
                        self.log.error(f'{self.tel} not supported on host {vncserver}')
                        break
                    desktop = fields[1].strip()
                    name = ln.strip()
                    s = VNCSession(name=name, display=display, desktop=desktop, user=account)
                    sessions.append(s)
        self.log.debug(f'  Got {len(sessions)} sessions')
        for s in sessions:
            self.log.debug(str(s))

        return sessions


    ##-------------------------------------------------------------------------
    ## Close ssh threads
    ##-------------------------------------------------------------------------
    def close_ssh_thread(self, p):
        '''
        close_ssh_thread(self, p)

        p - port to be closed

        Closes ssh session on port p.

        '''
        if p in self.ports_in_use.keys():
            try:
                remote_connection, desktop, process = self.ports_in_use.pop(p, None)
            except KeyError:
                return

            self.log.info(f" Closing SSH tunnel for port {p:d}, {desktop:s} "
                     f"on {remote_connection:s}")
            process.kill()


    def close_ssh_threads(self):
        '''
        close_ssh_threads(self)

        Loops over open ports and closes them as needed.
        Uses close_ssh_thread()

        '''

        for p in list(self.ports_in_use.keys()):
            self.close_ssh_thread(p)


    ##-------------------------------------------------------------------------
    ## Calculate vnc windows size and position
    ##-------------------------------------------------------------------------
    def get_display_info(self):
        '''
        get_display_info(self)

        Determine the screen number and size

        '''

        self.log.debug('Determining display info')
        self.geometry = list()
        try:
            xpdyinfo = subprocess.run('xdpyinfo', stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=5)

        except subprocess.TimeoutExpired as e:
            # If xpdyinfo fails just log and keep going
            self.log.debug('xpdyinfo failed')
            self.log.debug(e)
            return
        except TimeoutError as e:
            # If xpdyinfo fails just log and keep going
            self.log.debug('xpdyinfo failed')
            self.log.debug(e)
            return
        except FileNotFoundError as e:
            self.log.debug('xpdyinfo does not exist')
            self.log.debug(e)
            return


        stdout = xpdyinfo.stdout.decode()
        if xpdyinfo.returncode != 0:
             self.log.debug(f'xpdyinfo failed')
             for line in stdout.split('\n'):
                 self.log.debug(f"xdpyinfo: {line}")
             stderr = xpdyinfo.stderr.decode()
             for line in stderr.split('\n'):
                 self.log.debug(f"xdpyinfo: {line}")
             return None
        find_nscreens = re.search('number of screens:\s+(\d+)', stdout)
        nscreens = int(find_nscreens.group(1)) if find_nscreens is not None else 1
        self.log.debug(f'Number of screens = {nscreens}')

        find_dimensions = re.findall('dimensions:\s+(\d+)x(\d+)', stdout)
        if len(find_dimensions) == 0:
            self.log.debug(f'Could not find screen dimensions')
            return None
        # convert values from strings to int
        self.screens = [[int(val) for val in line] for line in find_dimensions]
        for screen in self.screens:
            self.log.debug(f"Screen size: {screen[0]}x{screen[1]}")


    def calc_window_geometry(self):
        '''If window positions are not set in config file, make a guess.
        '''
        window_positions = self.config.get('window_positions', None)
        if window_positions is not None:
            self.geometry = window_positions
        else:
            self.log.debug(f"Calculating VNC window geometry...")
            num_win = len(self.sessions_found)
            cols = 2
            rows = 2
            screen = self.screens[0]
            #get x/y coords (assume two rows)
            for row in range(0, rows):
                for col in range(0, cols):
                    x = round(col * screen[0]/cols)
                    y = round(row * screen[1]/rows)
                    if window_positions is not None:
                        index = len(self.geometry) % len(window_positions)
                        x = window_positions[index][0]
                        y = window_positions[index][1]
                    self.geometry.append([x, y])
        self.log.debug('geometry: ' + str(self.geometry))

    def position_vnc_windows(self):
        '''Reposition the VNC windows to the preferred positions
        '''
        self.log.info("Re-reading config file")
        self.get_config()
        self.log.info(f"Positioning VNC windows...")
        self.calc_window_geometry()

        #get all x-window processes
        #NOTE: using wmctrl (does not work for Mac)
        #alternate option: xdotool?
        cmd = ['wmctrl', '-l']
        wmctrl_l = subprocess.run(cmd, stdout=subprocess.PIPE, timeout=5)
        stdout = wmctrl_l.stdout.decode()
        for line in stdout.split('\n'):
            self.log.debug(f'wmctrl line: {line}')
        if wmctrl_l.returncode != 0:
            self.log.debug(f'wmctrl failed')
            for line in stdout.split('\n'):
                self.log.debug(f'wmctrl line: {line}')
            stderr = wmctrl_l.stderr.decode()
            for line in stderr.split('\n'):
                self.log.debug(f'wmctrl line: {line}')
            return None
        win_ids = dict([x for x in zip(self.sessions_found,
                                [None for entry in self.sessions_found])])
        for line in stdout.split('\n'):
            for thread in self.vnc_threads:
                session = thread.name
                if session in line:
                    self.log.debug(f"Found {session} in {line}")
                    win_id = line.split()[0]
                    win_ids[session] = line.split()[0]

        for i,thread in enumerate(self.vnc_threads):
            session = thread.name
            if win_ids.get(session, None) is not None:
                index = i % len(self.geometry)
                geom = self.geometry[index]
                self.log.debug(f'{session} has geometry: {geom}')

                cmd = ['wmctrl', '-i', '-r', win_ids[session], '-e',
                       f'0,{geom[0]},{geom[1]},-1,-1']
                self.log.debug(f"Positioning '{session}' with command: " + ' '.join(cmd))
                wmctrl = subprocess.run(cmd, stdout=subprocess.PIPE, timeout=5)
                if wmctrl.returncode != 0:
                    return None
                stdout = wmctrl.stdout.decode()
#                 for line in stdout.split('\n'):
#                     self.log.debug(f'wmctrl line: {line}')
            else:
                self.log.info(f"Could not find window process for VNC session '{session}'")



    ##-------------------------------------------------------------------------
    ## Position vncviewers
    ##-------------------------------------------------------------------------
    def position_vnc_windows(self):
        '''
        position_vnc_windows(self)

        Postions the VNC windows. This only works if wmctrl is installed.


        '''
        self.log.info(f"Positioning VNC windows...")

        try:
            #get all x-window processes
            #NOTE: using wmctrl (does not work for Mac)
            #alternate option: xdotool?
            xlines = []
            cmd = ['wmctrl', '-l']
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            while True:
                line = proc.stdout.readline()
                if not line: break
                line = line.rstrip().decode('utf-8')
                self.log.debug(f'wmctrl line: {line}')
                xlines.append(line)

            #reposition each vnc session window
            for i, session in enumerate(self.sessions_found):
                self.log.debug(f'Search xlines for "{session}"')
                win_id = None
                for line in xlines:
                    if session not in line: continue
                    parts = line.split()
                    win_id = parts[0]

                if win_id:
                    index = i % len(self.geometry)
                    geom = self.geometry[index]
                    ww = geom[0]
                    wh = geom[1]
                    wx = geom[2]
                    wy = geom[3]
                    # cmd = ['wmctrl', '-i', '-r', win_id, '-e', f'0,{wx},{wy},{ww},{wh}']
                    cmd = ['wmctrl', '-i', '-r', win_id, '-e',
                           f'0,{wx},{wy},-1,-1']
                    self.log.debug(f"Positioning '{session}' with command: " + ' '.join(cmd))
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                else:
                    self.log.info(f"Could not find window process for VNC session '{session}'")
        except Exception as error:
            self.log.error("Failed to reposition windows.  See log for details.")
            self.log.debug(str(error))


    ##-------------------------------------------------------------------------
    ## Prompt command line menu and wait for quit signal
    ##-------------------------------------------------------------------------
    def prompt_menu(self):
        '''
        prompt_menu(self)

        Generates a menu of options for the user.
        Watches command line input and, based on input, calls appropriate
        function.

        '''
        line_length = 52
        lines = [f"-"*(line_length-2),
                 f"          Lick Remote Observing (v{__version__})",
                 f"                        MENU",
                 f"-"*(line_length-2),
                 f"  l               List sessions available",
                 f"  [desktop number]  Open VNC session by number (1-6)",
                 f"  w               Position VNC windows",
                 f"  s               Soundplayer restart",
                 f"  u               Upload log to Lick",
#                  f"|  p               Play a local test sound",
                 f"  t               List local ports in use",
                 f"  c [port]        Close ssh tunnel on local port",
                 f"  v               Check if software is up to date",
                 f"  q               Quit (or Control-C)",
                 f"-"*(line_length-2),
                 ]
        menu = "\n"
        for newline in lines:
            menu += '|' + newline + ' '*(line_length-len(newline)-1) + '|\n'
        menu += "> "

        quit = None
        while quit is None:
            cmd = input(menu).lower()
            cmatch = re.match(r'c (\d+)', cmd)
            nmatch = re.match(r'(\d)', cmd)
            if cmd == '':
                pass
            elif cmd == 'q':
                self.log.debug(f'Recieved command "{cmd}"')
                quit = True
            elif cmd == 'w':
                self.log.debug(f'Recieved command "{cmd}"')
                try:
                    self.position_vnc_windows()
                except:
                    self.log.error("Failed to reposition windows, see log")
                    trace = traceback.format_exc()
                    self.log.debug(trace)
            elif cmd == 'p':
                self.log.debug(f'Recieved command "{cmd}"')
                self.play_test_sound()
            elif cmd == 's':
                self.log.debug(f'Recieved command "{cmd}"')
                self.start_soundplay()
            elif cmd == 'u':
                self.log.debug(f'Recieved command "{cmd}"')
                self.upload_log()
            elif cmd == 'l':
                self.log.debug(f'Recieved command "{cmd}"')
                self.print_sessions_found()
            elif cmd == 't':
                self.log.debug(f'Recieved command "{cmd}"')
                self.list_tunnels()
            elif cmd == 'v':
                self.log.debug(f'Recieved command "{cmd}"')
                self.check_version()
            elif cmatch is not None:
                self.log.debug(f'Recieved command "{cmd}"')
                self.close_ssh_thread(int(cmatch.group(1)))
            elif nmatch is not None:
                self.log.debug(f'Recieved command "{cmd}"')
                desktop = int(nmatch.group(1)) - 1
                if desktop >= 0 and desktop < 6:
                    self.start_vnc_session(self.sessions_found[desktop].display)
                else:
                    self.log.error(f'Unrecognized desktop: "{cmd}"')
            else:
                self.log.debug(f'Recieved command "{cmd}"')
                self.log.error(f'Unrecognized command: "{cmd}"')


    ##-------------------------------------------------------------------------
    ## Check for latest version number on GitHub
    ##-------------------------------------------------------------------------
    def check_version(self):
        '''
        check_version(self)

        Checks the version of the software being run against the
        version in GitHub. Warns if they do not agree.

        '''
        url = ('https://raw.githubusercontent.com/bpholden/'
               'lickRemoteObserving/master/lick_vnc_launcher.py')
        try:
            import requests
            from packaging import version
            r = requests.get(url)
            findversion = re.search(r"__version__ = '(\d.+)'", r.text)
            if findversion is not None:
                remote_version = version.parse(findversion.group(1))
                local_version = version.parse(__version__)
            else:
                self.log.warning(f'Unable to determine software version on GitHub')
                return
            if remote_version == local_version:
                self.log.info(f'Your software is up to date (v{__version__})')
            else:
                self.log.warning(f'Your local software (v{__version__}) is not  '
                                 f'the currently available version '
                                 f'(v{remote_version})')
        except:
            self.log.warning("Unable to verify remote version")

    ##-------------------------------------------------------------------------
    ## Upload log file to Lick
    ##-------------------------------------------------------------------------
    def upload_log(self):
        '''
        upload_log(self)

        If possible, copies local log file to user@vncserver

        '''

        account = self.ssh_account

        logfile_handlers = [lh for lh in self.log.handlers if
                            isinstance(lh, logging.FileHandler)]
        logfile = pathlib.Path(logfile_handlers.pop(0).baseFilename)

        source = str(logfile)
        destination = account + '@' + self.vncserver + ':' + logfile.name

        command = ['scp',]

        if self.ssh_pkey is not None:
            command.append('-i')
            command.append(self.ssh_pkey)

        command.append('-oStrictHostKeyChecking=no')
        command.append('-oCompression=yes')
        command.append(source)
        command.append(destination)

        self.log.debug('scp command: ' + ' '.join (command))

        pipe = subprocess.PIPE
        null = subprocess.DEVNULL

        stdin = null

        proc = subprocess.Popen(command, stdin=stdin, stdout=null, stderr=null)
        if proc.poll() is not None:
            raise RuntimeError('subprocess failed to execute scp')

        try:
            stdout,stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.log.error('  Timeout attempting to upload log file')
            return

        if proc.returncode != 0:
            message = '  command failed with error ' + str(proc.returncode)
            self.log.error(message)
        else:
            self.log.info(f'  Uploaded {logfile.name}')
            self.log.info(f'  to {destination}')


    ##-------------------------------------------------------------------------
    ## Terminate all vnc processes
    ##-------------------------------------------------------------------------
    def kill_vnc_processes(self):
        '''

        kill_vnc_processes(self)

        Uses list in self.vnc_processes and ends those sessions.
        Each a subprocess.

        These are the local VNC sessions, not the sessions running
        on vncserver. Those are only managed locally on that host.


        '''
        self.log.info('Terminating all VNC sessions.')
        try:
            #NOTE: poll() value of None means it still exists.
            while self.vnc_processes:
                proc = self.vnc_processes.pop()
                self.log.debug('terminating VNC process: ' + str(proc.args))
                if proc.poll() == None:
                    proc.terminate()

        except:
            self.log.error("Failed to terminate VNC sessions.  See log for details.")
            trace = traceback.format_exc()
            self.log.debug(trace)



    ##-------------------------------------------------------------------------
    ## Common app exit point
    ##-------------------------------------------------------------------------
    def exit_app(self, msg=None):
        '''
        exit_app(self, msg=None)

        Terminates sound, closes ssh connections, and ends VNC processes.

        '''
        #hack for preventing this function from being called twice
        #todo: need to figure out how to use atexit with threads properly
        if self.exit: return

        #todo: Fix app exit so certain clean ups don't cause errors (ie thread not started, etc
        if msg != None: self.log.info(msg)

        #terminate soundplayer
        if self.sound:
            self.sound.terminate()

        # Close down ssh tunnels
        if self.ssh_forward:
            self.close_ssh_threads()


        #close vnc sessions
        self.kill_vnc_processes()

        self.exit = True
        self.log.info("EXITING APP\n")
        sys.exit(1)


    ##-------------------------------------------------------------------------
    ## Handle fatal error
    ##-------------------------------------------------------------------------
    def handle_fatal_error(self, error):
        '''
        handle_fatal_error(self, error)

        Trap exceptions and send them to author.

        '''
        #helpful user error message
        supportEmail = 'holden@ucolick.org'
        print("\n****** PROGRAM ERROR ******\n")
        print("Error message: " + str(error) + "\n")
        print("If you need troubleshooting assistance:")
        print(f"* Email {supportEmail}\n")
        #todo: call number, website?

        #Log error if we have a log object (otherwise dump error to stdout)
        #and call exit_app function
        msg = traceback.format_exc()
        if self.log:
            logfile = self.log.handlers[0].baseFilename
            print(f"* Attach log file at: {logfile}\n")
            self.log.debug(f"\n\n!!!!! PROGRAM ERROR:\n{msg}\n")
        else:
            print(msg)

        self.exit_app()


    ##-------------------------------------------------------------------------
    ## full set of tests
    ##-------------------------------------------------------------------------
    def test_functions(self):
        '''
        test_functions(self)

        Wrapper for running various test functions.
        Currently does not test sound.

        '''
        self.test_vncviewer()
        self.test_port_lookup()
        self.test_connection()
        self.test_ssh_key()
        server = self.servers_to_try[self.args.account]
        self.test_connection_to_servers(server)


    ##-------------------------------------------------------------------------
    ## test if the vncviewer exists
    ##-------------------------------------------------------------------------
    def test_vncviewer(self):
        '''
        Make sure application specified by config for viewing VNC
        sessions exists.
        Does NOT try to run it.
        '''
        self.log.info('Testing config file: vncviewer')
        vncviewer = self.vncviewer

        if vncviewer in [None, '', 'vncviewer']:
            # the line below will throw an error if which fails
            self.guess_vncviewer()
            try:
                vncviewer = subprocess.check_output(['which', 'vncviewer']).strip()
            except:
                self.log.error('Cannot find vncviewer and it is not defined in the config file.')
                return
        if vncviewer != 'open':
            assert os.path.exists(vncviewer)
            self.log.info(f' Passed')


    ##-------------------------------------------------------------------------
    ## test port look up method
    ##-------------------------------------------------------------------------
    def test_port_lookup(self):
        '''
        test_port_lookup(self)

        Test that an application selected for finding open ports
        is available.
        Then tests that application by running it.
        Both tests must pass.

        '''


        self.log.info('Testing port lookup')

        one_works = self.check_cmd is not None
        assert one_works
        self.log.info(f' Passed')
        assert self.is_local_port_in_use(self.LOCAL_PORT_START) is False
        self.log.info(f' Passed')

    ##-------------------------------------------------------------------------
    ## test connection
    ##-------------------------------------------------------------------------
    def test_connection(self):
        '''
        test_connection(self)

        Runs local executable to see if the route to MH exists.

        '''
        self.log.info('Testing config file: VPN connnection')
        self.tel = 'shane'
        self.validate_connection()
        assert self.connection_valid is True
        self.log.info(f' Passed')
    ##-------------------------------------------------------------------------
    ## test ssh key and validate it
    ##-------------------------------------------------------------------------
    def test_ssh_key(self):
        '''
        test_ssh_key(self)

        Tests connection by trying to ssh connect to the Shane.
        Only runs a single remote application, no VNC required.

        '''
        self.log.info('Testing config file: ssh_pkey')
        self.tel = 'shane'
        self.validate_ssh_key()
        assert self.ssh_key_valid is True
        self.log.info(f' Passed')

    ##-------------------------------------------------------------------------
    ## test to see if you can connect to the servers
    ##-------------------------------------------------------------------------
    def test_connection_to_servers(self, server):
        '''

        test_connection_to_servers(self, server)

        Tests that the software can connect to the requested host.
        Host specified by telescope command line argument (shane, nickel, etc.)

        '''
        vnc_account = self.ssh_account
        vnc_password = None
        result = f'{server}'
        self.log.info(f'Testing SSH to {vnc_account}@{server}')
        output = self.do_ssh_cmd('hostname', result,
                                vnc_account)
        assert output is not None
        assert output != ''
        assert output.strip() in [server, result]
        self.log.info(f' Passed')



##-------------------------------------------------------------------------
## Create argument parser
##-------------------------------------------------------------------------
def create_parser():
    '''
    create_parser()

    Parses command line arguments.
    '''

    ## create a parser object for understanding command-line arguments
    description = (f"Lick VNC Launcher (v{__version__}). This program is used "
                   f"by approved Lick Remote Observing sites to launch VNC "
                   f"sessions for the specified telescope account. For "
                   f"help or information on how to configure the code, please "
                   f"see the included README.md file or email "
                   f"holden@ucolick.org")
    parser = argparse.ArgumentParser(description=description)


    ## add flags
    parser.add_argument("--authonly", dest="authonly",
        default=False, action="store_true",
        help="Authenticate only")
    parser.add_argument("--nosound", dest="nosound",
        default=False, action="store_true",
        help="Skip start of soundplay application.")
    parser.add_argument("--test", dest="test",
        default=False, action="store_true",
        help="Run only tests")
    parser.add_argument("--tags", dest="tags",
        default=":1,:2,:3,:4,:5,:6",
        help='Soundplay tags, defaults to ":1,:2,:3,:4,:5,:6"')

    parser.add_argument("--check", dest="check",default=None,
        help="How to check for open ports.")

    parser.add_argument("--viewonly", dest="viewonly",default=False,
        action='store_true',
        help='Runs the VNC viewer in view only mode'
    )

    parser.add_argument("account", type=str, nargs='?', default='',
                        help="The user account.")


    parser.add_argument("-c", "--config", dest="config", type=str,
        help="Path to local configuration file.")

    #parse
    return parser.parse_args()


if __name__ == '__main__':
    # do actual work
    main()
