#!/usr/bin/python3
#
# ----------------------------------------------------------------------------
# - mtx-changer-python.py
# ----------------------------------------------------------------------------
#
# - Bill Arlofski - This script is intended to be a drop-in replacement for
#                   Bacula's original mtx-changer bash/perl script but with
#                   more features.
#
#                 - Initially this script adds the following features:
#
#                   - Control what information gets logged by setting the
#                     'debug_level' variable.
#                   - Automatic tape drive cleaning. Can be configured to
#                     check a drive's sg_logs status after an unload and
#                     automatically load a cleaning tape, wait, then unload
#                     it.
#
# The latest version of this script may be found at: https://github.com/waa
#
# USER VARIABLES - All user variables should be configured in the config file.
# See the options -c and -s in the instructions. Because the defaults in this
# script may change and more variables may be added over time, it is highly
# recommended to make use of the config file for customizing the variable
# settings.
# ----------------------------------------------------------------------------
#
# BSD 2-Clause License
#
# Copyright (c) 2023-2024, William A. Arlofski waa@revpol.com
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
# -----------------------------------------------------------------------
#
# Modified notes from the original bash/perl mtx-changer script
# -------------------------------------------------------------
# This script is called by the Bacula SD, configured in the
# Autochanger's ChangerCommand setting like in this default example:
#
# ChangerCommand = "/opt/bacula/scripts/mtx-changer-python.py %c %o %S %a %d"
#
# Additionally, new, optional parameters such as a configuration file, configuration section,
# a jobid, and jobname may also be specified:
#
# mtx-changer-python.py [-c <config>] [-s <section>] [-i <jobid>] [-j <jobname>] <chgr_device> <mtx_cmd> <slot> <drive_device> <drive_index>
#
# All <required> parameters must be passed to the script and they must be in the correct order as listed above.
# Bacula's SD will always pass all options specified on the ChangerCommand line even though in some cases not
# all of them are needed.
#
# In the example command line above, we can see that the parameters '-c config', '-s section', '-i jobid',
# and '-j jobname' are optional.
#
# For example, if you wanted to use a specific section in the default config file, and also wanted to have
# the jobid and job name written to every line in the log file, the following ChangerCommand command line would work:
#
# ChangerCommand = "/opt/bacula/scripts/mtx-changer-python.py -s My_Section -i %i -j %j %c %o %S %a %d"
#
# NOTE: The %i is not supported by the SD ChangerCommand in Bacula Community before 15.0.2
#       and Bacula Enterprise before 18.0.0. This option should be available on or about November 14, 2023.
#
#
#  Valid '<mtx_cmd>' commands are:
#  - list      List available volumes in slot:volume format.
#  - listall   List all slots in one of the following formats:
#              - For Drives:         D:drive index:F:slot:volume - D:0:F:5:G03005TA or for an empty drive:               D:3:E
#              - For Slots:          S:slot:F:volume             - S:2:F:G03002TA   or for an empty slot:                S:1:E
#              - For Import/Export:  I:slot:F:volume             - I:41:F:G03029TA  or for am empty import/export slot:  I:42:E
#  - slots     Show the number of slots in the autochanger.
#  - load      Load a a slot to a drive.
#  - unload    Unload a drive to a slot.
#  - loaded    Show which slot is loaded in a drive, else 0 if the drive is empty.
#  - transfer  Transfer a volume from one slot to another. In this case, the <drive_device> is the destination slot.
#
#  Slots are numbered from 1.
#  Drives are numbered from 0.
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
import random
import shutil
import argparse
import subprocess
from time import sleep
from datetime import datetime
from configparser import ConfigParser, BasicInterpolation

# Set some variables
# ------------------
progname = 'MTX-Changer-Python'
version = '1.32'
reldate = 'October 29, 2024'
progauthor = 'Bill Arlofski'
authoremail = 'waa@revpol.com'
scriptname = 'mtx-changer-python.py'
prog_info_txt = '\n' + progname + ' - v' + version + ' - ' + scriptname \
                + '\nBy: ' + progauthor + ' ' + authoremail + ' (c) ' + reldate + '\n\n'

# List of valid mtx_cmd choices:
# ------------------------------
valid_mtx_cmd_lst = ['list', 'listall', 'load', 'loaded', 'slots', 'transfer', 'unload']

# This list is so that we can reliably convert the True/False strings
# from the config file into real booleans to be used in later tests.
# -------------------------------------------------------------------
cfg_file_true_false_lst = ['auto_clean', 'chk_drive', 'chgr_name_hdr_only',
                           'include_import_export', 'inventory', 'jobid_hdr_only',
                           'jobname_hdr_only', 'log_cfg_vars', 'offline',
                           'strip_jobname', 'vxa_packetloader']

# Initialize these to satisfy the defaults
# in the load() and unload() functions.
# ----------------------------------------
slot = drive_device = drv_idx = drive_index = ''

# Lists of platform specific binaries
# -----------------------------------
linux_bin_lst = ['lsscsi_bin']
fbsd_bin_lst = ['camcontrol_bin']

# Define the argparse arguments, descriptions, defaults, etc
# waa - Something to look into: https://www.reddit.com/r/Python/comments/11hqsbv/i_am_sick_of_writing_argparse_boilerplate_code_so/
# ---------------------------------------------------------------------------------------------------------------------------------
parser = argparse.ArgumentParser(prog=scriptname, description='Drop-in replacement for mtx-changer bash/perl script with more features.')
parser.add_argument('-v', '--version', help='Print the script version.', version=scriptname + " v" + version, action='version')
parser.add_argument('-c', '--config', help='Configuration file.', default='/opt/bacula/scripts/mtx-changer-python.conf', type=argparse.FileType('r'))
parser.add_argument('-s', '--section', help='Section in configuration file.', default='DEFAULT')
parser.add_argument('-i', '--jobid', help='The jobid.', default=None)
parser.add_argument('-j', '--jobname', help='The job name.', default=None)
parser.add_argument('chgr_device', help='The library\'s /dev/sg#, or /dev/tape/by-id/*, or /dev/tape/by-path/* node.')
parser.add_argument('mtx_cmd', help='The mtx command to issue.', choices=valid_mtx_cmd_lst)
parser.add_argument('slot', help='The one-based library slot to load/unload, or the source slot for the transfer command.')
parser.add_argument('drive_device', help='The drive\'s /dev/nst#, /dev/tape/by-id/*-nst, /dev/tape/by-path/* node. Or, the destination slot for the transfer command.')
parser.add_argument('drive_index', help='The zero-based drive index.')
args = parser.parse_args()

# Now for some functions
# ----------------------
def now():
    'Return the current date/time in human readable format.'
    return datetime.today().strftime('%Y-%m-%d %H:%M:%S')

def usage():
    'Show the instructions and script information.'
    parser.print_help()
    print(prog_info_txt)
    sys.exit(1)

def log(text, level, hdr=None):
    'Given some text and a debug level, write the text to the mtx_log_file.'
    if level <= int(debug_level) and text != '':
        with open(mtx_log_file, 'a+') as file:
            file.write(('\n' if '[ Starting ' in text else '') \
            + now() + ' ' \
            + (chgr_name + ' ' if (len(chgr_name) != 0 and not chgr_name_hdr_only) else '') \
            + ('JobId: ' + jobid + ' ' if (jobid not in ('', '0', None) and not jobid_hdr_only) else '') \
            + ('Job: ' + jobname + ' ' if (jobname not in ('', None, '*System*') and not jobname_hdr_only) \
              else (jobname + ' ' if jobname != None and not jobname_hdr_only else '')) \
            + ('- ' if hdr is None else '| ') + text.rstrip('\n') + '\n')

def print_opt_errors(opt, bin_var=None, tfk=None, tfv=None):
    'Print the incorrect variable and the reason it is incorrect.'
    if opt == 'config':
        error_txt = 'The config file \'' + config_file + '\' does not exist or is not readable.'
    elif opt == 'section':
        error_txt = 'The section [' + config_section + '] does not exist in the config file \'' + config_file + '\''
    elif opt == 'bin':
        error_txt = 'The binary variable \'' + bin_var[0] + '\', pointing to \'' + bin_var[1] + '\' does not exist or is not executable.'
    elif opt == 'truefalse':
        error_txt = 'The variable \'' + tfk + '\' (' + tfv + ') must be a boolean \'True\' or \'False\'.'
    return '\n' + error_txt + '\n'

def log_cmd_results(result):
    'Given a subprocess.run() result object, clean up the extra line feeds from stdout and stderr and log them.'
    log('In function log_cmd_results()', 50)
    stdout = result.stdout.rstrip('\n')
    stderr = result.stderr.rstrip('\n')
    if stdout == '':
        stdout = 'N/A'
    if stderr == '':
        stderr = 'N/A'
    log('returncode: ' + str(result.returncode), 40)
    log('stdout: ' + ('\n[begin stdout]\n' + stdout + '\n[end stdout]' if '\n' in stdout else stdout), 40)
    log('stderr: ' + ('\n[begin stderr]\n' + stderr + '\n[end stderr]' if '\n' in stderr else stderr), 40)

def chk_cmd_result(result, cmd):
    'Given a result object, check the returncode, then log and exit if non zero.'
    log('In function: chk_cmd_result()', 50)
    if 'sg_logs' in cmd and result.returncode == 6:
        return result.returncode
    elif result.returncode != 0:
        log('ERROR calling: ' + cmd, 20)
        # The SD will print this stdout after 'Result=' in the job log
        # ------------------------------------------------------------
        print(result.stderr.rstrip('\n'))
        sys.exit(result.returncode)

def get_shell_result(cmd):
    'Given a command to run, return the subprocess.run() result.'
    log('In function: get_shell_result()', 50)
    return subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

def get_uname():
    'Get the OS uname to be use in other tests.'
    log('In function: get_uname()', 50)
    cmd = uname_bin
    log('Getting OS\'s uname so we can use it for other tests.', 40)
    log('shell command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    return result.stdout.rstrip('\n')

def cmd_exists(cmd):
    'Check that a binary command exists and is executable.'
    log('In function: cmd_exists()', 50)
    log('Checking command: ' + cmd[1], 40)
    cmd_exists = shutil.which(cmd[1]) is not None
    if cmd_exists:
        log('Command ' + cmd[1] + ': OK', 40)
    else:
        log('Command ' + cmd[1] + ': FAIL', 40)
    return cmd_exists

def chk_bins():
    'Check that all defined binaries exist and are executable.'
    log('In function: chk_bins()', 50)
    for bin_var in config_dict.items():
        if '_bin' in bin_var[0]:
            # Here we make sure to only test binary
            # commands that exist on the platform
            # -------------------------------------
            if (bin_var[0] in linux_bin_lst and uname == 'Linux') \
                or (bin_var[0] in fbsd_bin_lst and uname == 'FreeBSD'):
                if cmd_exists(bin_var):
                    pass
                else:
                    print(print_opt_errors('bin', bin_var))
                    usage()
            elif bin_var[0] not in linux_bin_lst and bin_var[0] not in fbsd_bin_lst:
                if cmd_exists(bin_var):
                    pass
                else:
                    print(print_opt_errors('bin', bin_var))
                    usage()
            elif (bin_var[0] in linux_bin_lst and uname != 'Linux') \
                  or (bin_var[0] in fbsd_bin_lst and uname != 'FreeBSD'):
                pass
            else:
                print(print_opt_errors('bin', bin_var))
                usage()

def get_ready_str():
    'Determine the OS so we can set the correct mt "ready" string.'
    log('In function: get_ready_str()', 50)
    if uname == 'Linux':
        if os.path.isfile('/etc/debian_version'):
            cmd = mt_bin + ' --version | grep "mt-st"'
            log('mt command: ' + cmd, 30)
            result = get_shell_result(cmd)
            log_cmd_results(result)
            if result.returncode == 1:
                return 'drive status'
        else:
            cmd = mt_bin + ' --version | grep "GNU cpio"'
            log('mt command: ' + cmd, 30)
            result = get_shell_result(cmd)
            log_cmd_results(result)
            if result.returncode == 0:
                return 'drive status'
        return 'ONLINE'
    elif uname == 'SunOS':
        return 'No Additional Sense'
    elif uname == 'FreeBSD':
        return 'Current Driver State: at rest.'
    elif uname == 'OpenBSD':
        return 'ds=3<Mounted>'
    else:
        print(print_opt_errors('uname'))
        usage()

def slots():
    'Print the number of slots in the library.'
    log('In function: slots()', 50)
    log('Determining the number of slots in the library.', 20)
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    log('mtx command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    # Storage Changer /dev/tape/by-id/scsi-SSTK_L80_XYZZY_B:4 Drives, 44 Slots ( 4 Import/Export )
    # --------------------------------------------------------------------------------------------
    slots_line = re.search('Storage Changer.*', result.stdout)
    slots = re.sub(r'^Storage Changer.* Drives, (\d+) Slots.*', '\\1', slots_line.group(0))
    log('Library' + (' ' + chgr_name if len(chgr_name) != 0 else '') + ' (' + chgr_device + ')' + ' has ' + slots + ' slots', 20)
    log('slots output: ' + slots, 40)
    return slots

def call_inventory():
    'Call mtx with the inventory command if the inventory variable is True.'
    log('In function: call_inventory()', 50)
    cmd = mtx_bin + ' -f ' + chgr_device + ' inventory'
    log('mtx command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    return

def loaded():
    'If the drive is loaded, return the slot that is in it, otherwise return 0'
    log('In function: loaded()', 50)
    log('Checking if drive device ' + drive_device + ' (drive index: ' + drive_index + ') is loaded', 20)
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    log('mtx command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    # We re.search() for drive_index:Full lines and then we return 0
    # if the drive is empty, or the number of the slot that is loaded
    # For the debug log, we also print the volume name and the slot.
    # TODO: Maybe skip the re.search() and just get what I need with
    # the re.subs
    # ---------------------------------------------------------------
    drive_loaded_line = re.search('Data Transfer Element ' + drive_index + ':Full.*', result.stdout)
    if drive_loaded_line is not None:
        slot_and_vol_loaded = (re.sub(r'^Data Transfer Element.*Element (\d+) Loaded.*= (\w+)', '\\1 \\2', drive_loaded_line.group(0))).split()
        slot_loaded = slot_and_vol_loaded[0]
        vol_loaded = slot_and_vol_loaded[1]
        log('Drive device ' + drive_device + ' (drive index: ' \
            + drive_index + ') is loaded with volume (' + vol_loaded \
            + ') from slot ' + slot_loaded, 20)
        log('loaded output: ' + slot_loaded, 40)
        return slot_loaded
    else:
        log('Drive device ' + drive_device + ' (drive index: ' + drive_index + ') is empty', 20)
        log('loaded output: 0', 40)
        return '0'

def list():
    'Return the list of slots and volumes in the slot:volume format required by the SD.'
    log('In function: list()', 50)
    # Does this library require an inventory command before the list command?
    # -----------------------------------------------------------------------
    if inventory:
        call_inventory()
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    log('mtx command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    # Create lists of only full Data Transfer Elements, Storage Elements, and possibly
    # the Import/Export elements. Then concatenate them into one 'mtx_elements_list' list.
    # ------------------------------------------------------------------------------------
    mtx_elements_txt = ''
    data_transfer_elements_list = re.findall(r'Data Transfer Element \d+:Full.*\w', result.stdout)
    storage_elements_list = re.findall(r'Storage Element \d+:Full.*', result.stdout)
    if include_import_export:
        importexport_elements_list = re.findall(r'Storage Element \d+ IMPORT.EXPORT:Full.*\w', result.stdout)
    # waa - 20231008 - If the data transfer elements are listed first, a bconsole
    #                  `status slots` output always shows slot 1 as empty, so they
    #                  are added last to match what `mtx-changer` outputs.
    # mtx_elements_list = data_transfer_elements_list + storage_elements_list \
    #                   + (importexport_elements_list if 'importexport_elements_list' in locals() else [])
    # ----------------------------------------------------------------------------------------------------
    mtx_elements_list = storage_elements_list \
                      + (importexport_elements_list if 'importexport_elements_list' in locals() else []) \
                      + data_transfer_elements_list

    # Parse the results of the status output and
    # format it the way the SD expects to see it.
    # -------------------------------------------
    for element in mtx_elements_list:
        tmp_txt = re.sub(r'Data Transfer Element \d+:Full \(Storage Element (\d+) Loaded\):VolumeTag = (\w)', '\\1:\\2', element)
        # waa - 20230518 - I need to find out what the actual packetloader text is so I can verify/test this.
        # Original grep/sed used in mtx-changer bash/perl script for VXA libraries:
        # grep " *Storage Element [1-9]*:.*Full" | sed "s/ *Storage Element //" | sed "s/Full :VolumeTag=//"
        # ---------------------------------------------------------------------------------------------------
        if vxa_packetloader:
            tmp_txt = re.sub(' *Storage Element [0-9]*:.*Full', '', tmp_txt)
            tmp_txt = re.sub('Full :VolumeTag=', '', tmp_txt)
        else:
            if include_import_export:
                tmp_txt = re.sub(r'Storage Element (\d+) IMPORT.EXPORT:Full :VolumeTag=(.*)', '\\1:\\2', tmp_txt)
            tmp_txt = re.sub(r'Storage Element (\d+):Full :VolumeTag=(\w)', '\\1:\\2', tmp_txt)
            tmp_txt = re.sub(r'Storage Element (\d+):Full', 'S:\\1:F:NO_BARCODE', tmp_txt)
            mtx_elements_txt += tmp_txt + ('' if element == mtx_elements_list[-1] else '\n')
    log('list output:\n' + mtx_elements_txt, 40)
    return mtx_elements_txt

def listall():
    'Return the list of slots and volumes in the format required by the SD.'
    log('In function: listall()', 50)
    # Does this library require an inventory command before the status command?
    # -------------------------------------------------------------------------
    if inventory:
        call_inventory()
    cmd = mtx_bin + ' -f ' + chgr_device + ' status'
    log('mtx command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    chk_cmd_result(result, cmd)
    # Create lists of all Data Transfer Elements, Storage Elements, and possibly Import/Export
    # elements - empty, or full. Then concatenate them into one 'mtx_elements_list' list.
    # ----------------------------------------------------------------------------------------
    mtx_elements_txt = ''
    data_transfer_elements_list = re.findall(r'Data Transfer Element \d+:.*\w', result.stdout)
    storage_elements_list = re.findall(r'Storage Element \d+:.*\w', result.stdout)
    if include_import_export:
        importexport_elements_list = re.findall(r'Storage Element \d+ IMPORT.EXPORT.*\w', result.stdout)
    mtx_elements_list = data_transfer_elements_list + storage_elements_list \
                      + (importexport_elements_list if 'importexport_elements_list' in locals() else [])
    # Parse the results of the status output and
    # format it the way the SD expects to see it.
    # -------------------------------------------
    for element in mtx_elements_list:
        tmp_txt = re.sub(r'Data Transfer Element (\d+):Empty', 'D:\\1:E', element)
        tmp_txt = re.sub(r'Data Transfer Element (\d+):Full \(Storage Element (\d+) Loaded\):VolumeTag = (.*)', 'D:\\1:F:\\2:\\3', tmp_txt)
        tmp_txt = re.sub(r'Storage Element (\d+):Empty(:VolumeTag){0,1}', 'S:\\1:E', tmp_txt)
        tmp_txt = re.sub(r'Storage Element (\d+):Full :VolumeTag=(.*)', 'S:\\1:F:\\2', tmp_txt)
        tmp_txt = re.sub(r'Storage Element (\d+):Full.*', 'S:\\1:F:NO_BARCODE', tmp_txt)
        if include_import_export:
            tmp_txt = re.sub(r'Storage Element (\d+) IMPORT.EXPORT:Empty(:VolumeTag){0,1}', 'I:\\1:E', tmp_txt)
            tmp_txt = re.sub(r'Storage Element (\d+) IMPORT.EXPORT:Full :VolumeTag=(.*)', 'I:\\1:F:\\2', tmp_txt)
        mtx_elements_txt += tmp_txt + ('' if element == mtx_elements_list[-1] else '\n')
    log('listall output:\n' + mtx_elements_txt, 40)
    return mtx_elements_txt

def getvolname(cln_slot=None):
    'Given a slot (or slot and device in the case of a transfer) return the volume name(s).'
    # If mtx_cmd is transfer we need to return src_vol and dst_vol
    # ------------------------------------------------------------
    log('In function: getvolname()', 50)
    if mtx_cmd == 'transfer':
        vol = re.search('[SI]:' + slot + ':.:(.*)', all_slots)
        if vol:
            src_vol = vol.group(1)
        else:
            src_vol = ''
        # Remember, for the transfer command, the SD sends the destination
        # slot in the drive_device position in the command line options.
        # ----------------------------------------------------------------
        vol = re.search('[SI]:' + drive_device + ':.:(.*)', all_slots)
        if vol:
            dst_vol = vol.group(1)
        else:
            dst_vol = ''
        return src_vol, dst_vol
    elif mtx_cmd == 'load':
        vol = re.search('[SI]:' + slot + ':.:(.*)', all_slots)
        if vol:
            return vol.group(1), ''
        else:
            # Slot we are loading might be in a drive
            # TODO: In load(), let's fail due to this!
            # ----------------------------------------
            vol = re.search('D:' + drive_index + ':F:\\d+:(.*)', all_slots)
            if vol:
                return vol.group(1), ''
            else:
                return '', ''
    elif mtx_cmd == 'unload':
        vol = re.search('D:' + drive_index + ':F:\\d+:(.*)', all_slots)
        if vol:
            src_vol = vol.group(1)
        else:
            src_vol = ''
        vol = re.search('[SI]:' + slot + ':.:(.*)', all_slots)
        if vol:
            dst_vol = vol.group(1)
        else:
            dst_vol = ''
        return src_vol, dst_vol

def wait_for_drive(vol):
    'Wait a maximum of load_wait seconds for the drive to become ready.'
    log('In function: wait_for_drive()', 50)
    s = 0
    log('Waiting a maximum of ' + load_wait + ' \'load_wait\' seconds for drive to become ready', 20)
    while s <= int(load_wait):
        cmd = mt_bin + ' -f ' + drive_device + ' status'
        log('mt command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        chk_cmd_result(result, cmd)
        if re.search(ready, result.stdout):
            log('Device ' + drive_device + ' (drive index: ' + drive_index + ') ready', 20)
            break
        log('Device ' + drive_device + ' (drive index: ' + drive_index + ') not ready, sleeping for one second and retrying...', 30)
        sleep(1)
        s += 1
    if s == int(load_wait) + 1:
        log('The maximum \'load_wait\' time of ' + load_wait + ' seconds has been reached', 20)
        log('Timeout waiting for drive device ' + drive_device + ' (drive index: ' + drive_index + ')'
            + ' to signal that it is loaded', 20)
        log('Perhaps the Device\'s "DriveIndex" is incorrect', 20)
        log('Exiting with return code 1', 30)
        return 1
    else:
        log('Successfully loaded volume' + (' (' + vol[0] + ')' if volume != '' else '') + ' from slot ' + slot \
            + ' to drive device ' + drive_device + ' (drive index: ' + drive_index + ')', 20)
        log('Exiting with return code 0', 30)
        return 0

def chk_for_cln_tapes():
    'Return a list of cleaning tapes in the library based on the cln_str variable.'
    log('In function: chk_for_cln_tapes()', 50)
    # If a cleaning tape is in a drive, we can have no
    # idea where in the cleaning process it is, so we
    # need to ignore cleaning tapes in drives.
    # ------------------------------------------------
    cln_tapes = re.findall(r'S:(\d+):F:(' + cln_str + '.*)', all_slots)
    if include_import_export:
        cln_tapes += re.findall(r'I:(\d+):F:(' + cln_str + '.*)', all_slots)
    if len(cln_tapes) > 0:
        log('Found the following cleaning tapes: ' + str(cln_tapes), 20)
    else:
        log('No cleaning tapes found in library', 20)
    return cln_tapes

def clean(cln_tapes):
    'Given the cln_tapes list of available cleaning tapes, randomly pick one and load it.'
    log('In function: clean()', 50)
    log('Selecting a cleaning tape', 20)
    cln_tuple = random.choice(cln_tapes)
    cln_slot = cln_tuple[0]
    cln_vol = cln_tuple[1]
    log('Will load cleaning tape (' + cln_vol + ') from slot ' + cln_slot \
        + ' into drive device ' + drive_device + ' (drive index: ' + drive_index + ')', 20)
    load(cln_slot, drive_device, drive_index, (cln_vol, ''), cln=True)

def get_sg_node():
    'Given a drive_device, return the /dev/sg# node.'
    log('In function: get_sg_node()', 50)
    log('Determining the tape drive\'s scsi generic device node required by sg_logs', 20)
    if uname == 'Linux':
        # Use `lsscsi` on Linux to always identify the
        # correct scsi generic device node on-the-fly.
        # --------------------------------------------
        # On Linux, tape drive device nodes may be specified
        # as '/dev/nst#' or '/dev/tape/by-id/scsi-3XXXXXXXX-nst' (the
        # preferred method), or even with '/dev/tape/by-path/*', so we
        # will determine which one it is and then use the output from
        # `lsscsi` to match it to its corresponding /dev/sg# node.
        # ------------------------------------------------------------
        # drive_device = '/dev/nst0'
        # drive_device = '/dev/tape/by-id/scsi-350223344ab000900-nst'
        # drive_device = '/dev/tape/by-path/STK-T10000B-XYZZY_B1-nst'
        # -----------------------------------------------------------
        # TODO: waa - 20240302 - These lines before the if statement
        # are not necessary. Probably are here for logging mainly
        # -----------------------------------------------------------
        cmd = ls_bin + ' -l ' + drive_device
        log('ls command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        chk_cmd_result(result, cmd)
        if '/dev/st' in drive_device or '/dev/nst' in drive_device:
            # OK, we caught the simple /dev/st# or /dev/nst# case
            # ---------------------------------------------------
            st = drive_device
        elif '/by-id' in drive_device or '/by-path' in drive_device:
            # OK, we caught the /dev/tape/by-id or /dev/tape/by-path case
            # -----------------------------------------------------------
            # The ls command outputs a line feed that needs to be stripped
            # ------------------------------------------------------------
            st = '/dev/' + re.sub(r'.* -> .*/n*(st\d+).*$', '\\1', result.stdout.rstrip('\n'), re.S)
        cmd = lsscsi_bin + ' -g'
        log('lsscsi command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        chk_cmd_result(result, cmd)
        sg_search = re.search('.*' + st + ' .*(/dev/sg\\d+)', result.stdout)
        if sg_search:
            sg = sg_search.group(1)
            log('SG node for drive device: ' + drive_device + ' (drive index: ' + drive_index + ') --> ' + sg, 20)
            return sg
    elif uname == 'FreeBSD':
        sa = re.sub(r'/dev/(sa\d+)', '\\1', drive_device)
        # On FreeBSD, tape drive device nodes are '/dev/sa#'
        # and their corresponding scsi generic device nodes
        # are '/dev/pass#'. We can correlate them with the
        # 'camcontrol' command.
        # --------------------------------------------------
        # camcontrol devlist
        # <VBOX HARDDISK 1.0>   at scbus0 target 0 lun 0 (pass0,ada0)
        # <VBOX CD-ROM 1.0>     at scbus1 target 0 lun 0 (cd0,pass1)
        # <STK L80 0107>        at scbus2 target 0 lun 0 (ch0,pass2)
        # <STK T10000B 0107>    at scbus3 target 0 lun 0 (pass3,sa0)
        # <STK T10000B 0107>    at scbus4 target 0 lun 0 (pass5,sa2)
        # <STK T10000B 0107>    at scbus5 target 0 lun 0 (pass4,sa1)
        # <STK T10000B 0107>    at scbus6 target 0 lun 0 (pass6,sa3)
        # -----------------------------------------------------------
        cmd = camcontrol_bin + ' devlist'
        log('camcontrol command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        chk_cmd_result(result, cmd)
        sg_search = re.search('.*\\((pass\\d+),' + sa + '\\)', result.stdout)
        if sg_search:
            sg = '/dev/' + sg_search.group(1)
            log('SG node for drive device: ' + drive_device + ' (drive index: ' + drive_index + ') --> ' + sg, 20)
            return sg
    else:
        log('Failed to identify an sg node device for drive device ' + drive_device, 20)
        return 1

def tapealerts(sg):
    'Call the sglogs_bin and return any tape alerts.'
    log('In function: tapealerts()', 50)
    # waa - 20240510 - We can't/shouldn't use tapeinfo here any more. This is because
    #                  tapeinfo clears the TapeAlert registers upon reading them.
    #                  This can possibly break the functionality of tapeinfo when
    #                  it is called in an SD's Drive Device's `AlertCommmand` script.
    #                  This is important because the SD has the ability to disable a
    #                  Drive, or flag a tape volume's volstatus as `Error` when
    #                  critical problems are detected.
    # -------------------------------------------------------------------------------
    # Call sg_logs and parse for 'Cleaning action required'
    # -----------------------------------------------------
    cmd = sglogs_bin + ' --page=0xc ' + sg
    log('Checking' + ' drive (sg node: ' + sg + ') with sg_logs utility', 20)
    log('sg_logs command: ' + cmd, 30)
    result = get_shell_result(cmd)
    log_cmd_results(result)
    # waa - 20240516 - It seems, that on a physical drive (not on mhVTL), the first time
    #                  sg_logs is called, we get a "unit attention" (returncode 6), and
    #                  no information about a Cleaning action required (or not required)
    #                  so we check for this and then just make the sg_logs call again
    #                  and report those results.
    # ----------------------------------------------------------------------------------
    # EXAMPLE:
    # --------
    # mtx -f /dev/tape/by-id/scsi-3500110a000896f20 unload 14 1 && sg_logs --page=0xc /dev/sg5
    # Unloading drive 1 into Storage Element 14...done
    #     HP        Ultrium 5-SCSI    Z6KW
    # log sense:  Fixed format, current;  Sense key: Unit Attention
    #  Additional sense: Mode parameters changed
    # log_sense: unit attention
    # echo $?
    # 6
    # sg_logs --page=0xc /dev/sg5
    #     HP        Ultrium 5-SCSI    Z6KW
    # Sequential access device page (ssc-3)
    #   Data bytes received with WRITE commands: 0 GB
    #   Data bytes written to media by WRITE commands: 0 GB
    #   Data bytes read from media by READ commands: 0 GB
    #   Data bytes transferred by READ commands: 0 GB
    #   Native capacity from BOP to EOD: 4294967295 MB
    #   Native capacity from BOP to EW of current partition: 4294967295 MB
    #   Minimum native capacity from EW to EOP of current partition: 4294967295 MB
    #   Native capacity from BOP to current position: 4294967295 MB
    #   Maximum native capacity in device object buffer: 0 MB
    #   Cleaning action not required (or completed)
    if chk_cmd_result(result, cmd) == 6:
        log('Recieved a "unit attention" status, retrying...', 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
    # Some example `sg_logs` outputs showing Cleaning status messages
    # ---------------------------------------------------------------
    # sg_logs --page=0xc /dev/sg7 | grep "Cleaning action"
    # Cleaning action required
    # sg_logs --page=0xc /dev/sg5 | grep "Cleaning action"
    # Cleaning action not required (or completed)
    # ----------------------------------------------------
    return re.search(r'Cleaning action required', result.stdout)

def checkdrive():
    'Given a tape drive /dev/sg# node, check sg_logs output, call clean() if "Cleaning action required" messages exist.'
    log('In function: checkdrive()', 50)
    # First, we need to check and see if we have any cleaning tapes in the library
    # ----------------------------------------------------------------------------
    if auto_clean:
        cln_tapes = chk_for_cln_tapes()
        if len(cln_tapes) == 0:
            log('Skipping automatic cleaning', 20)
            # Return to the unload() function with 1 because we cannot clean a
            # drive device without a cleaning tape, but the unload() function
            # that called us has already successfully unloaded the tape before it
            # called us and it needs to exit cleanly so the SD sees a 0 return code
            # and can continue.
            # ---------------------------------------------------------------------
            return 1

    # Next, we need the drive device's /dev/sg# node required by sg_logs
    # ------------------------------------------------------------------
    sg = get_sg_node()
    if sg == 1:
        # Return to the unload() function with 1 because we cannot run
        # sg_logs without an sg node, but the unload() function that called
        # us has already successfully unloaded the tape before it called us
        # and it needs to exit cleanly so the SD sees a 0 return code and
        # can continue.
        # -----------------------------------------------------------------
        return 1

    # Call the tapealerts() function to
    # check if the drive requires cleaning
    # ------------------------------------
    log('INFO: Calling tapealerts() to check for any sg_logs \'Cleaning action required\' messages', 20)
    clean_action = tapealerts(sg)
    if clean_action:
        log('WARN: ' + clean_action.group() + ' for drive device ' + drive_device + ' (' + sg + '):', 20)
        if auto_clean:
            log('INFO: Drive requires cleaning and the \'auto_clean\' variable is True, calling clean() function', 20)
            clean(cln_tapes)
        else:
            log('WARN: Drive requires cleaning but the \'auto_clean\' variable is False, skipping cleaning', 20)
    else:
       log('No \'Cleaning action required\' messages detected', 20)
    # Now we we need to just return
    # to the unload() function
    # -----------------------------
    return 0

def load(slt=None, drv_dev=None, drv_idx=None, vol=None, cln=False):
    'Load a tape from a slot to a drive.'
    log('In function: load()', 50)
    if slt is None:
        slt = slot
    if drv_dev is None:
        drv_dev = drive_device
    if drv_idx is None:
        drv_idx = drive_index
    if vol is None:
        vol = volume
    # Don't bother trying to load a tape into a drive that is full
    # ------------------------------------------------------------
    if loaded() != '0':
        fail_txt = 'Can\'t load a drive that is full, exiting with return code 1'
        log(fail_txt, 20)
        # Printing to stdout here is necessary so
        # that it is logged by the SD after the 'Result='
        # -----------------------------------------------
        print('Err: ' + fail_txt)
        return 1
    # Don't bother trying to load a tape from a slot that is empty
    # ------------------------------------------------------------
    elif vol[0] == '':
        fail_txt = 'Slot ' + slt + ' is empty. Can\'t load a drive from an empty slot, exiting with return code 1'
        log(fail_txt, 20)
        # Printing to stdout here is necessary so
        # that it is logged by the SD after the 'Result='
        # -----------------------------------------------
        print('Err: ' + fail_txt)
        return 1
    else:
        cmd = mtx_bin + ' -f ' + chgr_device + ' load ' + slt + ' ' + drv_idx
        log('Loading ' + ('cleaning tape' if cln else 'volume') \
            + (' (' + vol[0] + ')' if vol[0] != '' else '') + ' from slot ' + slt \
            + ' to drive device ' + drv_dev + ' (drive index: ' + drv_idx + ')', 20)
        log('mtx command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        # Don't call chk_cmd_result() here,
        # we need to log something specific
        # ---------------------------------
        if result.returncode != 0:
            log('ERROR calling: ' + cmd, 20)
            fail_txt = 'Failed to load drive device ' + drv_dev + ' (drive index: ' + drv_idx + ') ' \
                     + ('with volume (' + vol[0] + ') ' if vol[0] != '' else '') + 'from slot ' + slt
            log(fail_txt, 20)
            log('Err: ' + result.stderr, 20)
            log('Exiting with return code ' + str(result.returncode), 30)
            # The SD will print this stdout after 'Result=' in the job log
            # ------------------------------------------------------------
            print(fail_txt + ' Err: ' + result.stderr)
            sys.exit(result.returncode)
        # If we are loading a cleaning tape, do the clean_wait
        # waiting here instead of the load_sleep time
        # ----------------------------------------------------
        if cln:
            log('A cleaning tape was just loaded. Will wait (' + clean_wait + ') \'clean_wait\' seconds, then unload it', 20)
            sleep(int(clean_wait))
            log('Done waiting (' + clean_wait + ') \'clean_wait\' seconds', 30)
            unload(slt, drv_dev, drv_idx, vol, cln=True)
        else:
            # Sleep load_sleep seconds after the drive signals it is ready
            # ------------------------------------------------------------
            if int(load_sleep) != 0:
                log('Sleeping for \'load_sleep\' time of ' + load_sleep + ' seconds to let the drive settle', 20)
                sleep(int(load_sleep))
            # TODO: 20240510 - Why did I comment this? lol
            # elif chk_drive:
            #     log('The chk_drive variable is True, calling checkdrive() function', 20)
            #     if checkdrive() == 1:
            return wait_for_drive(vol)

def unload(slt=None, drv_dev=None, drv_idx=None, vol=None, cln=False):
    'Unload a tape from a drive to a slot.'
    log('In function: unload()', 50)
    if slt is None:
        slt = slot
    if drv_dev is None:
        drv_dev = drive_device
    if drv_idx is None:
        drv_idx = drive_index
    if vol is None:
        vol = volume
    # Don't bother trying to unload an empty drive
    # --------------------------------------------
    if loaded() == '0':
        fail_txt = 'Can\'t unload a drive that is empty, exiting with return code 1'
        log(fail_txt, 20)
        # Printing to stdout here is necessary so
        # that it is logged by the SD after the 'Result='
        # -----------------------------------------------
        print('Err: ' + fail_txt)
        return 1
    # Don't bother trying to unload a tape into a full slot
    # -----------------------------------------------------
    elif vol[1] != '':
        fail_txt = 'Slot ' + slt + ' is full with volume (' + vol[1] + '), exiting with return code 1'
        log(fail_txt, 20)
        # Printing to stdout here is necessary so
        # that it is logged by the SD after the 'Result='
        # -----------------------------------------------
        print('Err: ' + fail_txt)
        return 1
    else:
        if offline:
            log('The \'offline\' variable is True. Sending drive device ' + drv_dev \
                + ' offline command before unloading it', 30)
            cmd = mt_bin + ' -f ' + drv_dev + ' offline'
            log('mt command: ' + cmd, 30)
            result = get_shell_result(cmd)
            log_cmd_results(result)
            chk_cmd_result(result, cmd)
            if int(offline_sleep) != 0:
                log('Sleeping for \'offline_sleep\' time of ' + offline_sleep 
                    + ' seconds to let the drive settle before unloading it', 20)
                sleep(int(offline_sleep))
        cmd = mtx_bin + ' -f ' + chgr_device + ' unload ' + slt + ' ' + drv_idx
        log('Unloading ' + ('cleaning tape' if cln else 'volume') \
            + (' (' + vol[0] + ') ' if vol[0] != '' else '') + 'from drive device ' \
            + drv_dev + ' (drive index: ' + drv_idx + ')' + ' to slot ' + slt, 20)
        log('mtx command: ' + cmd, 30)
        result = get_shell_result(cmd)
        log_cmd_results(result)
        # Don't call chk_cmd_result() here,
        # we need to log something specific
        # ---------------------------------
        if result.returncode != 0:
            log('ERROR calling: ' + cmd, 20)
            fail_txt = 'Failed to unload drive device ' + drv_dev + ' (drive index: ' + drv_idx + ') ' \
                     + ('with volume (' + vol[0] + ') ' if vol[0] != '' else '') + 'to slot ' + slt
            log(fail_txt, 20)
            log('Err: ' + result.stderr, 20)
            log('Exiting with return code ' + str(result.returncode), 30)
            # The SD will print this stdout after 'Result=' in the Bacula job log
            # -------------------------------------------------------------------
            print(fail_txt + ' Err: ' + result.stderr)
        else:
            log('Successfully unloaded ' + ('cleaning tape' if cln else 'volume') \
                + ' (' + (vol[0] + ') ' if vol[0] != '' else '') + 'from drive device ' \
                + drv_dev + ' (drive index: ' + drv_idx + ') to slot ' + slt, 20)
            # After successful unload, check to see if the tape drive should be cleaned.
            # We need to intercept the process here, before we exit from the unload,
            # otherwise the SD will move on and try to load the next tape.
            # Additionally when unloading a cleaning tape, we call unload()
            # with 'cln = True' so we do not end up in any loops - especially if the
            # drive still reports it needs cleaning after it has been cleaned.
            # --------------------------------------------------------------------------
            if cln:
                log('A cleaning tape (' + vol[0] + ') was just unloaded, skipping \'Cleaning action required\' checks', 20)
            elif chk_drive:
                log('The chk_drive variable is True, calling checkdrive() function', 20)
                if checkdrive() == 1:
                    # I think there is nothing to do here. We could not get an sg
                    # node, or there are no cleaning tapes in the library, so we
                    # cannot run sg_logs but the drive has been successfully
                    # unloaded, so we just need to log and exit cleanly here.
                    # -----------------------------------------------------------
                    log('Exiting unload() volume ' + ('(' + vol[0] + ')' if vol != '' else '') \
                        + ' with return code ' + str(result.returncode), 30)
                    return 0
            else:
                log('The chk_drive variable is False, skipping \'Cleaning action required\' checks', 20)
            log('Exiting unload() volume ' + ('(' + vol[0] + ') ' if vol != '' else '') \
                + 'with return code ' + str(result.returncode), 30)
    return result.returncode

def transfer():
    'Transfer a tape from one slot to another.'
    # The SD will send the destination slot in the
    # 'drive_device' position on the command line
    # --------------------------------------------
    log('In function: transfer()', 50)
    cmd = mtx_bin + ' -f ' + chgr_device + ' transfer ' + slot + ' ' + drive_device
    log('Transferring volume ' + ('(' + volume[0] + ') ' if volume[0] != '' else '(EMPTY) ') + 'from slot '
        + slot + ' to slot ' + drive_device + (' containing volume (' + volume[1] + ')' if volume[1] != '' else '' ), 20)
    if volume[0] == '' or volume[1] != '':
       fail_txt = 'The source slot is empty, or the destination slot is full, will not even attempt the transfer'
       log(fail_txt, 20)
       log('Exiting with return code 1', 30)
       print('Err: ' + fail_txt)
       sys.exit(1)
    else:
       log('mtx command: ' + cmd, 30)
       result = get_shell_result(cmd)
       log_cmd_results(result)
       # Don't call chk_cmd_result() here,
       # we need to log something specific
       # ---------------------------------
       if result.returncode != 0:
           log('ERROR calling: ' + cmd, 20)
           fail_txt = 'Failed to transfer volume ' + ('(' + volume[0] + ') ' if volume[0] != '' else '(EMPTY) ') + 'from slot ' \
                    + slot + ' to slot ' + drive_device + (' containing volume (' + volume[1] + ')' if volume[1] != '' else '' )
           log(fail_txt, 20)
           log('Err: ' + result.stderr, 20)
           log('Exiting with return code ' + str(result.returncode), 30)
           # The SD will print this stdout after 'Result=' in the job log
           # ------------------------------------------------------------
           print(fail_txt + ' Err: ' + result.stderr)
           return result.returncode
       else:
           log('Successfully transferred volume ' + ('(' + volume[0] + ') ' if volume[0] != '' else '(EMPTY) ') \
               + 'from slot ' + slot + ' to slot ' + drive_device, 20)
           log('Exiting with return code ' + str(result.returncode), 30)
           return 0

# ================
# BEGIN the script
# ================
# Check for and parse the configuration file first
# ------------------------------------------------
config_file = args.config.name
config_section = args.section
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
        print('  - An exception has occurred while reading configuration file: ' + str(err))
        print(print_opt_errors('section'))
        sys.exit(1)

# For each key in the config_dict dictionary, make its key name
# into a global variable and assign it the key's dictionary value.
# https://www.pythonforbeginners.com/basics/convert-string-to-variable-name-in-python
# -----------------------------------------------------------------------------------
myvars = vars()
for k, v in config_dict.items():
    if k in cfg_file_true_false_lst:
        # Convert all the True/False strings to booleans on the fly
        # ---------------------------------------------------------
        # If any lower(dictionary) true/false
        # variable is 'true' or 'false', set it to
        # the boolean True or False, else print an
        # error, the instructions, and exit.
        # ----------------------------------------
        if v.lower() == 'true':
            config_dict[k] = True
        elif v.lower() == 'false':
            config_dict[k] = False
        else:
            pass
    # Set the global variable
    # -----------------------
    myvars[k] = config_dict[k]

# Assign variables from argparse Namespace
# ----------------------------------------
mtx_cmd = args.mtx_cmd
chgr_device = args.chgr_device
drive_device = args.drive_device
drive_index = args.drive_index
slot = args.slot
jobid = args.jobid
jobname = args.jobname

# Should we strip the long datestamp off
# of the jobname passed to us by the SD?
# --------------------------------------
if jobname is not None and strip_jobname:
    jobname = re.sub(r'(^.*)\.\d{4}\-\d{2}-\d{2}_.*', '\\1', args.jobname)
else:
    pass

# Check the boolean variables
# ---------------------------
for var in cfg_file_true_false_lst:
    if config_dict[var] not in (True, False):
        print(print_opt_errors('truefalse', tfk=var, tfv=str(config_dict[var])))
        usage()

# If debug_level is at a minimum
# level of 10, log command line
# variables to log file
# ------------------------------
log('-'*10 + '[ Starting ' + progname + ' v' + version + ' ]' + '-'*10 , 10, hdr=True)
log('Config File: ' + config_file, 10, hdr=True)
log('Config Section: [' + config_section + ']', 10, hdr=True)
log(('JobId: ' + jobid if jobid not in ('0', None) else ''), 10, hdr=True)
log(('Job Name: ' + jobname if jobname != None else ''), 10, hdr=True)
log(('Changer Name: ' + chgr_name if len(chgr_name) != 0 else ''), 10, hdr=True)
log('Changer Device: ' + chgr_device, 10, hdr=True)
log('Drive Device: ' + drive_device, 10, hdr=True)
log('Command: ' + mtx_cmd, 10, hdr=True)
log('Drive Index: ' + drive_index, 10, hdr=True)
log('Slot: ' + slot, 10, hdr=True)

# Log all configuration file
# variables and their values?
# ---------------------------
if log_cfg_vars:
    log('-'*22, 10, hdr=True)
    log('Config file variables:', 10, hdr=True)
    for k, v in config_dict.items():
        log(k + ': ' + str(v), 10, hdr=True)
log('-'*22, 10, hdr=True)

# Get the OS's uname to be used in other tests
# --------------------------------------------
uname = get_uname()

# Check that the binaries exist and that they are executable.
# NOTE: A small chicken and egg issue exists here because we call
# uname above but we have not verified the binary exists and is
# executable by us (ie: bacula user). We can't check the binaries
# first because we filter out testing binaries based on some
# platform-specific binaries that don't exist on other platforms
# using the 'uname' variable assigned by the get_uname()
# function. Should be safe, as all systems have uname in the
# $PATH.
# ---------------------------------------------------------------
chk_bins()

# Check the OS to assign the 'ready' variable
# to know when a drive is loaded and ready.
# -------------------------------------------
ready = get_ready_str()

# Get a list of all volumes in all slots
# This will be used throughout the script
# ---------------------------------------
all_slots = listall()

# Check to see if the operation can/should log volume
# names. If yes, call the getvolname() function
# ---------------------------------------------------
if mtx_cmd in ('load', 'loaded', 'unload', 'transfer'):
    volume = getvolname()

# Call the appropriate function based on the mtx_cmd
# --------------------------------------------------
if mtx_cmd == 'list':
    print(list())
elif mtx_cmd == 'listall':
    print(all_slots)
elif mtx_cmd == 'slots':
    print(slots())
elif mtx_cmd == 'loaded':
    print(loaded())
elif mtx_cmd == 'load':
    result = load()
    sys.exit(result)
elif mtx_cmd == 'unload':
    result = unload()
    sys.exit(result)
elif mtx_cmd == 'transfer':
    transfer()
