# lickRemoteObserving

These scripts are to be used by remote sites to connect to Keck for remote observing.

Before embarking on setting up a Remote Observing station, we recommend reading the offical remote observing policy and documentation at: [https://](https://)

## Notify Lick of your intent to connect remotely
Before you can connect to Keck remotely, we need to provide you with the firewall info and passwords.  As well, we need info about your remote observing station.

- Email `sa@ucolick.org` with the following info about your remote site:
    - Institution
    - City, State
    - Room Name/#
    - Room phone #
    - Emergency Services phone #

Once we receive your request, we will respond with instructions on obtaining the firewall info, firewall password, and VNC session password.

# Hardware Setup

## Displays

The primary hardware requirement for running Lick VNCs is screen space. 

We recommend you use the largest monitors you available. If you have
access to a large HDMI TV and the appropriate cables, that is also a
solution though it maybe less readable. 

## Computer Recommendations

The following hardware configuration has been tested:

- Computer: MacBook Pro 
    - CPU: Intel Core i7 CPU
    - RAM: 16GB

# Software Installation

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
        - **On macOS**: Real VNC's [VNC Viewer](https://www.realvnc.com/en/connect/download/viewer/) is recommended (note, this is the free software, you do not need VNC Viewer Plus).
        - **On macOS**: It is also possible to use the built in VNC viewer on macOS, but we have seen a few instances where the screen freezes and the client needs to be closed and reopened to get an up to date screen.


## Download and Install Lick VNC software

(NOTE: Examples below assuming a user named 'observer' and installing to home directory)

- Download or clone this project from github: 
    ```
    cd
    git clone https://github.com/bpholden/lickRemoteObserving
    cd ~/lickRemoteObserving
    ```

- Create configuration file: copy `lick_vnc_config.yaml` to `local_config.yaml`.
    ```
    cp lick_vnc_config.yaml local_config.yaml
    ```

- Create a KRO [conda environment](https://docs.conda.io/projects/conda/en/latest/user-guide/concepts/environments.html) using the provided environment.yaml file:
    ```
    cd ~/lickRemoteObserving
    conda env create -f environment.yaml
    ```

- Obtain SSH Keys:
    - 

- (optional) Add VNC start script to path:
    ```
    export PATH=/home/observer/lickRemoteObserving:$PATH
    ```

## Configure Lick VNC software

Edit the configuration file as appropriate.  Read the comments in the
configuration file itself as they can guide you.  You may need to
uncomment (remove the leading `#`) from lines you want to customize.

- **Configure Firewall:** If you are connecting outside of the Lick
  network,

```
To be filled in.
```

- **Configure Path to Private SSH Key:** Enter the path to the
  **private** key corresponding you obtained from Lick.  For example:

    ```
    ssh_pkey: '/Users/YOUR_ACCOUNT_NAME_HERE/.ssh/id_rsa',
    ```

- **Configure Local VNC Viewer Software:** This is where one sets
  `vncviewer` with the path and executable for the local VNC viewer
  client (we recommend TigerVNC as the most compatible with our
  system).  Some VNC viewers (such as the built in macOS one) may need
  a prefix such as `vnc://` which can be set via the `vncprefix`
  value.  Options which should be passed to the vncviewer application
  are set in the `vncargs` value (defaults should be good for Tiger
  VNC).
  
    - **Important:** Make sure you have configured your client **not** to resize the sessions (see the note about TigerVNC above).
    - **On Linux:** (optional) Save VNC session password (not available on macOS):
        - NOTE: This is for the final password prompt for each VNC window.
        - Run the `vncpasswd` command line utility and note where it saves the VNC password file.
        - Edit `local_config.yaml` to include the password file as a VNC start option:
            ```
            vncargs: '-passwd=/home/observer/.vnc/passwd',
            ```

- **Configure Default Sessions:** Lick instruments typically use 4 VNC
  sessions for instrument control named "control0", "control1",
  "control2", and "telstatus".  On a normal invocation of the software
  (via the `start_lick_viewers` command) it will open the six
  sessions specified here. 

- **Soundplay Configuration:** For compatible systems, uncomment the
  `soundplayer` line to specify which compiled executable for
  soundplay to use.  Other operating systems sometimes need other
  soundplay versions, contact `@ucolick.org` for help configuring
  this value.  Also, if you local machine's path to the `aplay`
  executable is non-standard, specify that in the `aplay` value.
  
	  
    - If your system is not compatible, or if you do not want it to
      have sounds, add a line to your `local_config.yaml` file:
      `nosound: True,` to avoid starting sounds.  This is important
      for sites which are using multiple computers for each set of VNC
      sessions.  Choose one to handle sounds, and set the `nosound:
      True,` option for the other.
	  

# Test your connection to Lick

Only after your SSH key is successfully installed at Lick, you can
test your system.

From the directory where the Lick VNC software is installed
(e.g. `~/lickRemoteObserving/`), run pytest:

```
conda activate KRO
pytest
```

This may query you for passwords, depending on your local
configuration. It should print out a report which indicates that all
tests passed. Make sure there are no test failures.

If there are test failures, email your logfile to `@ucolick.org`.
Verbose debug information is logged to the `lickRemoteObserving/logs/`
folder.  Log files are created based on the UTC date.


# Run the VNC launch script

From the command line, cd into your install directory and run
`start_lick_viewers` followed by the name of the instrument account
assigned for your observing night (ie `kast`, `nickel`).  Running the
script without options will start 6 VNC sessions for the Kast and the
soundplayer. Additionally, you should see a command line menu with
more options once you have started the script.:

``` cd ~/lickRemoteObserving ./start_lick_viewers [instrument account]
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

If you need assistance, please email `@ucolick.org` and attach the
most recent log file from the logs folder.

