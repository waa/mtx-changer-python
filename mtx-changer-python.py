#!/usr/bin/python3
#
# ---------------------------------------------------------------------------
# - 20230519 - mtx-changer-python.py v1.0 - Initial release
# ---------------------------------------------------------------------------
#
# - 20230519
# - Bill Arlofski - The purpose of this script will be to add more functionality
#                   than the original bash version of this script had. This script
#                   is a rewrite of the mtx-changer bash/perl script in Python.
#                   A key additional feature this script will initially provide is
#                   the ability to automatically detect when a tape drive in a library
#                   is reporting that it needs to be cleaned, and then to load a
#                   cleaning tape from a slot to clean the drive, and return it
#                   back to its slot when the cleaning is complete.
#
# If you use this script every day and think it is worth anything, I am
# always grateful to receive donations of any size with Venmo: @waa2k,
# or PayPal: @billarlofski
#
# The latest version of this script may be found at: https://github.com/waa
#
# -----------------------------------------------------------------------------------
# BSD 2-Clause License
#
# Copyright (c) 2023, William A. Arlofski waa@revpol.com
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1.  Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2.  Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ----------------------------------------------------------------------------
#
# USER VARIABLES - All user variables should be configured in the config file.
# See the options -C and -S in the instructions. Because the defaults in this
# script may change and more variables may be added over time, it is highly
# recommended to make use of the config file for customizing the variable
# settings.
# ---------------------------------------------------------------------------
#
# Modified notes from the original bash/perl mtx-changer script
# -------------------------------------------------------------
# mtx-changer "changer-device" "command" "slot" "archive-device" "drive-index" "job-name"
#              $1               $2        $3     $4               $5            $6
#
#  By default, the Bacula SD will always call with all of the above arguments, even though
#  in come cases, not all are used.
#
#  Valid commands are:
#  - list      List available volumes in slot:volume format
#  - listall   List all slots in one of the following formats:
#              - For Drives:         D:drive index:F:slot:volume - D:0:F:5:G03005TA or for an empty drive:               D:3:E
#              - For Slots:          S:slot:F:volume             - S:2:F:G03002TA   or for an empty slot:                S:1:E
#              - For Import/Export:  I:slot:F:volume             - I:41:F:G03029TA  or for am empty import/Export slot:  I:42:E
#  - loaded    Show which slot is loaded in a drive, else 0 if the drive is empty
#  - unload    Unload a drive to a slot
#  - load      Load a a slot to a drive
#  - slots     Show the number of slots in the autochanger
#  - transfer  Transfer a volume from one slot to another
#
#  Slots are numbered from 1
#  Drives are numbered from 0
# ----------------------------------------------------------------------------
#
# ============================================================
# Nothing below this line should need to be modified
# Set variables in /opt/bacula/scripts/mtx-changer-python.conf
# ============================================================
#
# Import the required modules
# ---------------------------
import os
import re
import sys
import subprocess
from time import sleep
from docopt import docopt
from datetime import datetime
from configparser import ConfigParser, BasicInterpolation

# Set some variables
# ------------------
progname = 'MTX Changer - Python'
version = '1'
reldate = 'May 19, 2023'
progauthor = 'Bill Arlofski'
authoremail = 'waa@revpol.com'
scriptname = 'mtx-changer-python.py'
prog_info_txt = progname + ' - v' + version + ' - ' + scriptname \
                + '\nBy: ' + progauthor + ' ' + authoremail + ' (c) ' + reldate + '\n\n'

# This list is so that we can reliably convert the True/False strings
# from the config file into real booleans to be used in later tests.
# -------------------------------------------------------------------
cfg_file_true_false_lst = ['debug', 'inventory', 'offline', 'vxa_packetloader']

# Define the docopt string
# ------------------------
doc_opt_str = """
Usage:
    mtx-changer-python.py [-C <config>] [-S <section>] <chgr_device> <mtx_cmd> <slot> <drive_device> <drive_index> [<jobname>]
    mtx-changer-python.py -h | --help
    mtx-changer-python.py -v | --version

Options:
-C, --config <config>        Configuration file - [default: /mnt/mtx-changer-python/mtx-changer-python.conf]
-S, --section <section>      Section in configuration file [default: DEFAULT]

-h, --help                   Print this help message
-v, --version                Print the script name and version

"""

# Now for some functions
# ----------------------
def usage():
    'Show the instructions and script information.'
    print(doc_opt_str)
    print(prog_info_txt)
    sys.exit(1)

def now():
    'Return the current date/time in human readable format.'
    return datetime.today().strftime('%Y-%m-%d %H:%M:%S')

def log(text):
    'Given some text, write it to the mtx_log_file.'
    with open(mtx_log_file, 'a+') as file:
        file.write(now() + ' - ' + ('Job: ' + jobname + ' - ' if jobname not in (None, '*System*') \
        else (jobname + ' - ' if jobname is not None else '')) \
        + (chgr_id + ' - ' if len(chgr_id) != 0 else '') + text + '\n')

def print_opt_errors(opt):
    'Print the incorrect variable and the reason it is incorrect.'
    if opt == 'config':
        return '\nThe config file \'' + config_file + '\' does not exist or is not readable.'
    if opt == 'section':
        return '\nThe section [' + config_section + '] does not exist in the config file \'' + config_file + '\''
    if opt == 'conf_version':
        return '\nThe config file conf_version variable (' + conf_version + ') does not match the script version (' + version + ')'
    if opt == 'uname':
        return '\nCould not determine the OS using the \'uname\' utility.'
    if opt == 'command':
        return '\nThe command provided (' + mtx_cmd + ') is not a valid command.'

def chk_cfg_version ():
    'Check to make sure that the conf_version variable matches script version'
    if conf_version == version:
        return True
    else:
        print(print_opt_errors('conf_version'))
        usage()

def get_shell_result(cmd):
    'Given a command to run, return the subprocess.run result'
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    return result

def get_ready_str():
    'Determine the OS so we can set the correct mt "ready" string.'
    cmd = 'uname'
    result = get_shell_result(cmd)
    uname = result.stdout
    if uname == 'Linux\n':
        if os.path.isfile('/etc/debian_version'):
            cmd = 'mt --version|grep "mt-st"'
            result = get_shell_result(cmd)
            if result.returncode == 1:
                return 'drive status'
        else:
            cmd = 'mt --version|grep "GNU cpio"'
            result = get_shell_result(cmd)
            if result.returncode == 0:
                return 'drive status'
        return 'ONLINE'
    elif uname == 'SunOS\n':
        return 'No Additional Sense'
    elif uname == 'FreeBSD\n':
        return 'Current Driver State: at rest.'
    else:
        print(print_opt_errors('uname'))
        usage()

def do_loaded():
    'Tells if the drive is loaded'
    if debug:
        log('In function do_loaded')
        log('Checking if drive index ' + drive_index + ' is loaded.')
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    if debug:
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if result.returncode != 0:
        log('ERROR calling: ' + cmd)
        log(result.stdout + result.stderr)
        sys.exit(result.returncode)

    # We re.search for drive_index:Full lines and then we return 0
    # if the drive is empty, or the number of the slot that is loaded
    # For the debug log, we also print the volume name and the slot.
    # ---------------------------------------------------------------
    drive_loaded_line = re.search('Data Transfer Element ' + drive_index + ':Full.*', result.stdout)
    # If the re.search finds soemthing, it returns True with a re.search object
    # -------------------------------------------------------------------------
    if drive_loaded_line:
        drive_loaded = re.sub('^Data Transfer Element.*Element (.*) Loaded.*', '\\1', drive_loaded_line.group(0))
        vol_loaded = re.sub('.*:VolumeTag = (.+?) .*', '\\1', drive_loaded_line.group(0))
        if debug:
            log('Drive index ' + drive_index + ' loaded with volume ' + vol_loaded + ' from slot ' + drive_loaded + '.')
            log('do_loaded output: ' + drive_loaded)
        print(drive_loaded)
        sys.exit(0)
    else:
        if debug:
            log('do_loaded output: 0')
        print('0')
        sys.exit(0)

def do_slots():
    'Print the number of slots in the library.'
    if debug:
        log('In function do_slots')
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    if debug:
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if result.returncode != 0:
        log('ERROR calling: ' + cmd)
        log(result.stdout + result.stderr)
        sys.exit(result.returncode)

    # First we re.search for the Storage Changer line, then re.sub for the number of slots
    # Example mtx status output for the 'Storage Changer' line:
    # Storage Changer /dev/tape/by-id/scsi-SSTK_L80_XYZZY_B:4 Drives, 44 Slots ( 4 Import/Export )
    # ----------------------------------------------------------------------------------------------
    slots_line = re.search('Storage Changer.*', result.stdout)
    slots = re.sub('^Storage Changer.* Drives, (.*) Slots.*', '\\1', slots_line.group(0))
    if debug:
        log('do_slots output: ' + slots)
    return slots

def do_inventory():
    'Call mtx with the inventory command if the inventory variable is True.'
    if debug:
        log('In function do_ineventory')
    cmd = mtx_bin + ' -f ' + chgr_device + ' inventory'
    if debug:
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if result.returncode != 0:
        log('ERROR calling: ' + cmd)
        log(result.stdout + result.stderr)
        sys.exit(result.returncode)
    return

def do_list():
    'Return the list of slots and volumes in the slot:volume format required by the SD.'
    if debug:
        log('In function do_list')
    # Does this library require an inventory command before the list command?
    # -----------------------------------------------------------------------
    if inventory:
        do_inventory()
    # If inventory was successful, or was
    # not needed, now run the list command
    # ------------------------------------
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    if debug:
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if result.returncode != 0:
        log('ERROR calling: ' + cmd)
        log(result.stdout + result.stderr)
        sys.exit(result.returncode)
    # Parse the results of the list output and
    # format the way the SD expects to see it.
    # ----------------------------------------
    mtx_elements_txt = ''
    # First we create a list of only the drives and slots that are full
    # -----------------------------------------------------------------
    storage_elements_list = re.findall('Storage Element [0-9]+:Full :.*\w', result.stdout)
    data_transfer_elements_list = re.findall('Data Transfer Element [0-9]+:Full.*\w', result.stdout)
    mtx_elements_list = storage_elements_list + data_transfer_elements_list
    for element in mtx_elements_list:
        # re.sub information for full drives first, before any Storage Element re.subs
        # ----------------------------------------------------------------------------
        tmp_txt = re.sub('Data Transfer Element [0-9]+:Full \(Storage Element ([0-9]+) Loaded\)', '\\1', element)
        tmp_txt = re.sub('VolumeTag = ', '', tmp_txt)
        # waa - 20230518 - I can't really see why the packetloader is needed. On our HP Lib
        #                  in the lab, the output looks like what we are sed/grepping for
        #                  in the packetloader section. Need more testing...
        # ---------------------------------------------------------------------------------
        if vxa_packetloader:
            tmp_txt = re.sub('*Storage Element ', '', tmp_txt)
            tmp_txt = re.sub('Full :VolumeTag=', '', tmp_txt)
        else:
            tmp_txt = re.sub('Storage Element ', '', tmp_txt)
            tmp_txt = re.sub('Full :VolumeTag=', '', tmp_txt)
            mtx_elements_txt += tmp_txt + ('' if element == mtx_elements_list[-1] else '\n')
    if debug:
        log('do_list output:\n' + mtx_elements_txt)
    return mtx_elements_txt

def do_getvol():
    'Get the volume name. If mtx_cmd is transfer we need to return src_vol and dst_vol'
    if debug:
        log('In function do_getvol')
    if mtx_cmd == 'transfer':
        vol = re.search('[SI]:' + slot + ':.:(.*)', do_listall())
        if vol:
            src_vol = vol.group(1)
        else:
            src_vol = ''
        vol = re.search('[SI]:' + drive_device + ':.:(.*)', do_listall())
        if vol:
            dst_vol = vol.group(1)
        else:
            dst_vol = ''
        return src_vol, dst_vol
    elif mtx_cmd == 'load':
        vol = re.search('[SI]:' + slot + ':.:(.*)', do_listall())
        if vol:
            return vol.group(1)
        else:
            return ''
    elif mtx_cmd == 'unload':
        vol = re.search('D:' + drive_index + ':.:' + slot + ':(.*)', do_listall())
        if vol:
            return vol.group(1)
        else:
            return ''

def do_listall():
    'Return the list of slots and volumes in the format required by the SD.'
    if debug:
        log('In function do_listall')
    # Does this library require an inventory command before the list command?
    # -----------------------------------------------------------------------
    if inventory:
        do_inventory()
    # If inventory was successful, or was
    # not needed, call the status command
    # -----------------------------------
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    if debug:
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if result.returncode != 0:
        if debug:
            log('ERROR calling: ' + cmd)
            log(result.stdout + result.stderr)
        sys.exit(result.returncode)
    # Parse the results of the list output and
    # format the way the SD expects to see it.
    # ----------------------------------------
    mtx_elements_txt = ''
    storage_elements_list = re.findall('Storage Element [0-9]+:.*\w', result.stdout)
    importexport_elements_list = re.findall('Storage Element [0-9]+ IMPORT.*\w', result.stdout)
    data_transfer_elements_list = re.findall('Data Transfer Element [0-9]+:.*\w', result.stdout)
    mtx_elements_list = data_transfer_elements_list + storage_elements_list + importexport_elements_list
    for element in mtx_elements_list:
        # re.sub information for drives, Storage Element, and Import/Export re.subs
        # -------------------------------------------------------------------------
        tmp_txt = re.sub('Data Transfer Element (\d+):Empty', 'D:\\1:E', element)
        tmp_txt = re.sub('Data Transfer Element (\d+):Full \(Storage Element (\d+) Loaded\):VolumeTag = (.*)', 'D:\\1:F:\\2:\\3', tmp_txt)
        tmp_txt = re.sub('Storage Element (\d+):Empty', 'S:\\1:E', tmp_txt)
        tmp_txt = re.sub('Storage Element (\d+):Full :VolumeTag=(.*)', 'S:\\1:F:\\2', tmp_txt)
        tmp_txt = re.sub('Storage Element (\d+) IMPORT.EXPORT:Empty', 'I:\\1:E', tmp_txt)
        tmp_txt = re.sub('Storage Element (\d+) IMPORT.EXPORT:Full :VolumeTag=(.*)', 'I:\\1:F:\\2', tmp_txt)
        mtx_elements_txt += tmp_txt + ('' if element == mtx_elements_list[-1] else '\n')
    if debug:
        log('do_listall output:\n' + mtx_elements_txt)
    return mtx_elements_txt

def wait_for_drive():
    'Wait a maximum of load_wait seconds for the drive to become ready.'
    if debug:
        log('In function wait_for_drive')
    s = 0
    while s <= int(load_wait):
        cmd = 'mt -f ' + drive_device + ' status'
        if debug:
            log('mt command: ' + cmd)
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if debug:
            log('returncode: ' + str(result.returncode))
            log('stdout:\n' + result.stdout)
            log('stderr:\n' + result.stderr)
        if re.search(ready, result.stdout):
            log('Device ' + drive_device + ' (drive index: ' + drive_index + ') reports ready.')
            break
        if debug:
            log('Device ' + drive_device + ' (drive index: ' + drive_index + ') - not ready, sleeping for one second and retrying...')
        sleep(1)
        s += 1
    if s == int(load_wait) + 1:
        if debug:
            log('The maximum \'load_wait\' time of ' + str(load_wait) + ' seconds has been reached.')
            log('Timeout waiting for drive device ' + drive_device + ' (drive index: ' + drive_index + ')'
                + ' to signal that it is loaded. Perhaps the Device\'s "DriveIndex" is incorrect.')
            log('Exiting with return code 1')
        return 2
    else:
        if debug:
            log('Successfully loaded drive device ' + drive_device + ' (drive index: ' + drive_index + ') with volume '
                + ('(' + volume + ') ' if volume is not '' else '') + 'from slot ' + slot + '.')
            log('Exiting with return code 0')
        return 0

def do_load():
    'Load a tape from a slot to a drive.'
    if debug:
        log('In function do_load')
    cmd = mtx_bin + ' -f ' + chgr_device + ' load ' + slot + ' ' + drive_index
    if debug:
        log('Loading drive device ' + drive_device + ' (drive index: ' + drive_index + ') with volume '
            + ('(' + volume + ') ' if volume is not '' else '') + 'from slot ' + slot + '.')
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if debug:
        log('returncode: ' + str(result.returncode))
        log('stdout: ' + result.stdout)
        log('stderr: ' + result.stderr)
    if result.returncode != 0:
        if debug:
            log('ERROR calling: ' + cmd)
            log('returncode: ' + str(result.returncode))
            log('stdout: ' + result.stdout)
            log('stderr: ' + result.stderr)
        sys.exit(result.returncode)
    else:
        # Sleep load_sleep seconds after the drive signals it is ready
        # ------------------------------------------------------------
        if int(load_sleep) != 0:
            if debug:
                log('Sleeping for \'load_sleep\' time of ' + load_sleep + ' seconds to let the drive settle.')
            sleep(int(load_sleep))
    return wait_for_drive()

def do_unload():
    'Unload a tape from a drive to a slot.'
    if debug:
        log('In function do_unload')
    # TODO
    # waa - 202305189 - The 'mt' offline command when issued to a
    #                   drive that is empty hangs indefinitely - At
    #                   least on an mhVTL drive.
    #                   This needs to be tested on a real tape drive.
    #                   Maybe a 'loaded' command should be used to
    #                   test first, and skip the offline/unload
    #                   commands if the drive is already empty.
    # ---------------------- ----------------------------------------
    if offline:
        cmd = mt_bin + ' -f ' + drive_device + ' offline'
        if debug:
            log('The \'offline\' variable is True. Sending drive device ' + drive_device + ' offline command before unloading it.')
            log('mtx command: ' + cmd)
        result = get_shell_result(cmd)
        if debug:
            log('returncode: ' + str(result.returncode))
            log('stdout: ' + result.stdout)
            log('stderr: ' + result.stderr)
        if int(offline_sleep) != 0:
            if debug:
                log('Sleeping for \'offline_sleep\' time of ' + offline_sleep + ' seconds to let the drive settle before unloading it.')
            sleep(int(offline_sleep))
    cmd = mtx_bin + ' -f ' + chgr_device + ' unload ' + slot + ' ' + drive_index
    if debug:
        print(volume)
        log('Unloading drive device ' + drive_device + ' (drive index: ' + drive_index + ') with volume '
            + ('(' + volume + ') ' if volume is not '' else '') + 'to slot ' + slot + '.')
        log('mtx command: ' + cmd)
    result = get_shell_result(cmd)
    if debug:
        log('returncode: ' + str(result.returncode))
        log('stdout: ' + result.stdout)
        log('stderr: ' + result.stderr)
    if result.returncode != 0:
        if debug:
            log('ERROR calling: ' + cmd)
            log('returncode: ' + str(result.returncode))
            log('stdout: ' + result.stdout)
            log('stderr: ' + result.stderr)
            log('Unsuccessfully unloaded drive device ' + drive_device + ' (drive index: ' + drive_index + ') with volume '
                + ('(' + volume + ') ' if volume is not '' else '') + 'to slot ' + slot + '.')
            log('Exiting with return code ' + str(result.returncode))
        sys.exit(result.returncode)
    else:
        if debug:
            log('Successfully unloaded drive device ' + drive_device + ' (drive index: ' + drive_index + ') with volume '
                + ('(' + volume + ') ' if volume is not '' else '') + 'to slot ' + slot + '.')
            log('Exiting with return code ' + str(result.returncode))
        return result.returncode

def do_transfer():
    cmd = mtx_bin + ' -f ' + chgr_device + ' transfer ' + slot + ' ' + drive_device
    if debug:
        log('Transferring volume ' + ('(' + volume[0] + ') ' if volume[0] is not '' else '(EMPTY) ') + 'from slot '
            + slot + ' to slot ' + drive_device + (' containing volume (' + volume[1] + ')' if volume[1] is not '' else '' ) + '.')
    if volume[0] is '' or volume[1] is not '':
       log('This operation will fail!')
       log('Not even going to attempt it!')
       log('Exiting wuth return code 1')
       sys.exit(1)
    else:
       if debug:
           log('mtx command: ' + cmd)
       result = get_shell_result(cmd)
       if debug:
           log('returncode: ' + str(result.returncode))
           log('stdout: ' + result.stdout)
           log('stderr: ' + result.stderr)
       if result.returncode != 0:
           if debug:
               log('ERROR calling: ' + cmd)
               log('returncode: ' + str(result.returncode))
               log('stdout: ' + result.stdout)
               log('stderr: ' + result.stderr)
               log('Unsuccessfully transferred volume ' + ('(' + volume[0] + ') ' if volume[0] is not '' else '(EMPTY) ') + 'from slot '
                   + slot + ' to slot ' + drive_device + (' containing volume (' + volume[1] + ')' if volume[1] is not '' else '' ) + '.')
               log('Exiting with return code ' + str(result.returncode))
           sys.exit(result.returncode)
       else:
           if debug:
               log('Successfully transferred volume (' + volume[0] + ') from slot ' + slot + ' to slot ' + drive_device + '.')
               log('Exiting with return code ' + str(result.returncode))
           sys.exit(0)

# ================
# BEGIN the script
# ================
# Assign docopt doc string variable
# ---------------------------------
args = docopt(doc_opt_str, version='\n' + progname + ' - v' + version + '\n' + reldate + '\n')

# Check for and parse the configuration file first
# ------------------------------------------------
if args['--config'] != None:
    config_file = args['--config']
    config_section = args['--section']
    if not os.path.exists(config_file) or not os.access(config_file, os.R_OK):
        print(print_opt_errors('config'))
        usage()
    else:
        try:
            config = ConfigParser(inline_comment_prefixes=('# ', ';'), interpolation=BasicInterpolation())
            config.read(config_file)
            # Create 'config_dict' dictionary from config file
            # ------------------------------------------------
            config_dict = dict(config.items(config_section))
        except Exception as err:
            print('  - An exception with the config file has occurred reading configuration file: ' + str(err))
            print(print_opt_errors('section'))
            sys.exit(1)

    # For each key in the config_dict dictionary, make
    # its key name into a global variable and assign it the key's dictionary value.
    # https://www.pythonforbeginners.com/basics/convert-string-to-variable-name-in-python
    # -----------------------------------------------------------------------------------
    myvars = vars()
    for k, v in config_dict.items():
        if k in cfg_file_true_false_lst:
            # Convert all the True/False strings to booleans on the fly
            # ---------------------------------------------------------
            # If any lower(dictionary) true/false variable
            # is not 'true', then it is set to False.
            # ----------------------------------------------
            if v.lower() == 'true':
                config_dict[k] = True
            else:
                config_dict[k] = False
        # Set the global variable
        # -----------------------
        myvars[k] = config_dict[k]

# Check the version in the config file
# and compare to sctipt's version variable
# ----------------------------------------
chk_cfg_version()

# Check the OS to assign the 'ready' variable
# to know when a drive is loaded and ready
# -------------------------------------------
ready = get_ready_str()

# Assign some variables from args set
# -----------------------------------
mtx_cmd = args['<mtx_cmd>']
chgr_device = args['<chgr_device>']
drive_device = args['<drive_device>']
drive_index = args['<drive_index>']
slot = args['<slot>']
jobname = args['<jobname>']

# If debug mode is enabled, log all variables to log file
# -------------------------------------------------------
if debug:
    log('----------[ Starting ' + sys.argv[0] + ' ]----------')
    log('Config File: ' + args['--config'])
    log('Config Section: ' + args['--section'])
    log('Changer ID: ' + (chgr_id if chgr_id else 'No chgr_id specified'))
    log('Job Name: ' + (jobname if jobname is not None else 'No Job Name specified'))
    log('Changer Device: ' + chgr_device)
    log('Drive Device: ' + drive_device)
    log('Command: ' + mtx_cmd)
    log('Drive Index: ' + drive_index)
    log('Slot: ' + slot)
    log('----------')

# Check to see if the operation should print volume
# names. If yes, then call the do_getvol function
# -------------------------------------------------
if mtx_cmd in ('load', 'loaded', 'unload', 'transfer'):
    volume = do_getvol()

# Call the appropriate function based on the mtx_cmd
# --------------------------------------------------
if mtx_cmd == 'list':
    print(do_list())
elif mtx_cmd == 'listall':
   print(do_listall())
elif mtx_cmd == 'slots':
    print(do_slots())
elif mtx_cmd == 'loaded':
    do_loaded()
elif mtx_cmd == 'load':
    result = do_load()
    sys.exit(result)
elif mtx_cmd == 'unload':
    result = do_unload()
    sys.exit(result)
elif mtx_cmd == 'transfer':
   do_transfer()
else:
    print(print_opt_errors('command'))
    usage()
