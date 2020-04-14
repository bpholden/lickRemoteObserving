# lickRemoteObserving

These scripts are to be used by remote sites to connect to Lick for remote observing.

When everything is properly configured, all you need to do is run
```./start_lick_viewers shane```
or
```./start_lick_viewers nickel```
to enable the connection.

## Notify Lick of your intent to connect remotely
Before you can connect to Lick remotely, we need to provide you with the firewall info and passwords.  As well, we need info about your remote observing station.

- Email `sa@ucolick.org` with the following info about your remote site:
    - Phone #

Once we receive your request, we will respond with instructions on
obtaining the VPN verification.


# Familiarize Yourself with Remote Operations

We have extensive instructions for
[Nickel Remote Operations](http://mthamilton.ucolick.org/techdocs/remoteObs/nickel/intro/)
and 
[Shane Remote Operations](http://mthamilton.ucolick.org/techdocs/remoteObs/shane/intro/)

# Hardware Setup

## Displays

The primary hardware requirement for running Lick VNCs is screen space. 

We recommend you use the largest monitors you available. If you have
access to a large HDMI TV and the appropriate cables, that is also a
solution though it maybe less readable. 

## Computer Recommendations

The following hardware configuration has been tested:

- Computer: MacBook 13" Pro 
    - CPU: Intel Core i7 CPU
    - RAM: 16GB
	- an old Samsung 24" 1920x1200 that was lying around

# Software Installation

## VPN Software

- For macOS, we recommend [Tunnelblick](https://tunnelblick.net/)
- For Linux, we recommend
[OpenVPN](https://openvpn.net/community-downloads/)

The actual certificates which will be valid for only your observing
run are available [here](https://www.ucolick.org)

## Install Software Dependencies

NOTE: Examples below assuming sudo/root installation for all users and were originally written for linux (CentOS).  Modify as appropriate for your local OS.

The software has been tested for macOS.

- Install Anaconda python3
    - Download and run the latest installer: https://www.anaconda.com/distribution/
    - Add python3 to user path (example below for ~/.bashrc with typical python install path):
    ```
    export PATH=/usr/local/anaconda3-7/bin:$PATH
    ```
- Install VNC viewer client
    - **For Linux**
        - **On Linux:** TigerVNC is recommended as the VNC client.  RealVNC has been tested as well.
        ```
        sudo yum install tigervnc-x86_64
        ```
        - **Important!** If you are using TigerVNC, in the $HOME/.vnc directory, create a file `default.tigervnc` with these two lines: 
        ```
        TigerVNC Configuration file Version 1.0
        RemoteResize=0 
        ```
        - **On Linux:** (optional) Install wmctrl (Used for auto-positioning VNC windows)
            ```
            sudo yum install epel-release 
            sudo yum install wmctrl
            ```
    - **For macOS**
        - **On macOS**: Real VNC's
          [VNC Viewer](https://www.realvnc.com/en/connect/download/viewer/)
          is recommended (note, this is the free software, you do not
          need VNC Viewer Plus).
		  
        - **On macOS**: It is also possible to use the built in VNC
          viewer on macOS, but we have seen a few instances where the
          screen freezes and the client needs to be closed and
          reopened to get an up to date screen. 

- Install VPN client
  - **For macOS**, install [Tunnelblick](https://tunnelblick.net/) by
    downloading latest stable release
  - **For Linux**, ```fill in preferred client here```

## Download and Install Lick VNC software

(NOTE: Examples below assuming a user named 'observer' and installing to home directory)


To retreive the software, you can download it or clone it using git.

- [Click here to download the software as a zipfile](https://github.com/bpholden/lickRemoteObserving/archive/master.zip)


- To clone this project from github:
    ```
    cd
    git clone https://github.com/bpholden/lickRemoteObserving
    cd ~/lickRemoteObserving
    ```

Once you have downloaded the software:

- Create configuration file: copy `lick_vnc_config.yaml` to `local_config.yaml`.
    ```
    cp lick_vnc_config.yaml local_config.yaml
    ```

- Create a KRO [conda environment](https://docs.conda.io/projects/conda/en/latest/user-guide/concepts/environments.html) using the provided environment.yaml file:
    ```
    cd ~/lickRemoteObserving
    conda env create -f environment.yaml
    ```

- (optional) Add VNC start script to path:
    ```
    export PATH=/home/observer/lickRemoteObserving:$PATH
    ```

## Configure Lick VNC software

Edit the configuration file  ```local_config.yaml```.  Read the comments in the
configuration file itself as they can guide you.  You may need to
uncomment (remove the leading `#`) from lines you want to customize.

- **Configure OpenVPN:**
  - **For macOS**: Obtain the tblk file from [here](http://) for your
    schedule observing run. Open the Tunnelblick and click on the
    ```VPN Details``` menu item. When the window for Tunnelblick
    opens, click on the Configurations tab at the top, it is in the
    upper left. 	Using the Finder, drag the tblk file into your
    configurations list on the left. It will ask if you want this
    installed for everyone or only you, select "Me". The hit the
    connect button to start the VPN.


- **Configure Local VNC Viewer Software:** This is where one sets
  `vncviewer` with the path and executable for the local VNC viewer
  client (for Linux we recommend TigerVNC as the most compatible with our
  system).  Some VNC viewers (such as the built in macOS one) may need
  a prefix such as `vnc://` which can be set via the `vncprefix`
  value.  Options which should be passed to the vncviewer application
  are set in the `vncargs` value (defaults should be good for Tiger
  VNC). This goes in the file ``` local_config.yaml```
  
    - **Important:** IF and ONLY IF you are using TigerVNC, make sure you have configured your client **not** to resize the sessions (see the note above).
    - **On Linux:** (optional) Save VNC session password (not available on macOS):
        - NOTE: This is for the final password prompt for each VNC window.
        - Run the `vncpasswd` command line utility and note where it saves the VNC password file.
        - Edit `local_config.yaml` to include the password file as a VNC start option:
            ```
            vncargs: '-passwd=/home/observer/.vnc/passwd',
            ```
		- **On MacOS** (optional) If you use the MacOS builtin VNC
          viewer, you can optionally save the password by clicking the
          box that says "Remember Password"


- **Soundplay Configuration:** For compatible systems, uncomment the
  `soundplayer` line to specify which compiled executable for
  soundplay to use.  Other operating systems sometimes need other
  soundplay versions, contact `holden@ucolick.org` for help configuring
  this value.  Also, if you local machine's path to the `aplay`
  executable is non-standard, specify that in the `aplay` value.
  
	  
    - If your system is not compatible, or if you do not want it to
      have sounds, add a line to your `local_config.yaml` file:
      `nosound: True,` to avoid starting sounds.  This is important
      for sites which are using multiple computers for each set of VNC
      sessions.  Choose one to handle sounds, and set the `nosound:
      True,` option for the other.
	  

# Test your connection to Lick


From the directory where the Lick VNC software is installed
(e.g. `~/lickRemoteObserving/`), run ```test_connection```

```
cd ~/lickRemoteObserving
./test_connection
```

It should print out a report which indicates that all four
tests passed. Make sure there are no test failures.

If there are test failures, email your logfile to `holden@ucolick.org`.
Verbose debug information is logged to the `lickRemoteObserving/logs/`
folder.  Log files are created based on the UTC date.


# Run the VNC launch script

From the command line, cd into your install directory and run
`start_lick_viewers` followed by the name of the instrument account
assigned for your observing night (ie `shane`, `nickel`).  Running the
script without options will start 6 VNC sessions for the Kast and the
soundplayer. Additionally, you should see a command line menu with
more options once you have started the script.:

```
cd ~/lickRemoteObserving
./start_lick_viewers [shane or nickel]
```

To get help on available command line options:
```
./start_lick_viewers --help
```

**NOTE:** Be sure to exit the script by using the 'q' quit option or
  control-c to ensure all VNC processes, SSH tunnels, and
  authentication are terminated properly.


# Troubleshooting and common problems

Verbose debug information is logged to the `lickRemoteObserving/logs/`
folder.  Log files are created based on the UTC date.

If you need assistance, please email `holden@ucolick.org` and attach the
most recent log file from the logs folder.

