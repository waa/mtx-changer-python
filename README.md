# mtx-changer-python.py
- A drop-in replacement for Bacula's original `mtx-changer` bash/perl script to control tape libraries.

This script is meant to be automatically called by the Bacula Storage daemon (SD) to load/unload drives in a tape library, or to issue queries to the library to get information.

It is configured in the SD's Autochanger `Changer Command` setting like:
```
Autochanger {
  Name = AutochangerName
  Description = "Dell autochanger with four drives"
  ChangerDevice = "/dev/tape/by-id/scsi-xxxxxxxxxxxxx"
  ChangerCommand = "/opt/bacula/scripts/mtx-changer-python.py %c %o %S %a %d %i %j"    <---- Here
  Device = Drive_0, Drive_1, Drive_2, Drive_3
}

```

Where the variables passed are:
```
%c - Library's changer device node. eg: /dev/tape/by-id/scsi-350223344ab001000-nst.
%o - The command. Valid options: slots, list, listall, loaded, load, unload, transfer.
%S - The one-based library slot to load/unload, or the source slot for the transfer command.
%a - The drive's "ArchiveDevice". eg: /dev/nst#, or /dev/tape/by-id/*-nst, or /dev/tape/by-path/* node.
     Or, the destination slot for the transfer command.
%d - The zero-based drive index.
%i - Optional jobid. If present, it will be written after the timestamp to the log file.*
%j - Optional job name. If present, it will be written after the jobid to the log file.
```
* NOTE: The `%i` variable is not available as of 20230526. I have an official request with the developers to add this variable. Until this feature request is implemented, just pass a literal empty string in this place instead of %i: ''

Instructions on which parameters are optional, which are required, and the order they must appear in:
```
Usage:
mtx-changer-python.py [-c <config>] [-s <section>] <chgr_device> <mtx_cmd> <slot> <drive_device> <drive_index> [<jobid>] [<jobname>]
mtx-changer-python.py -h | --help
mtx-changer-python.py -v | --version

Options:
-c, --config <config>     Configuration file. [default: /opt/bacula/scripts/mtx-changer-python.conf]
-s, --section <section>   Section in configuration file. [default: DEFAULT]

chgr_device               The library's /dev/sg#, or /dev/tape/by-id/*, or /dev/tape/by-path/* node.
mtx_cmd                   Valid commands are: slots, list, listall, loaded, load, unload, transfer.
slot                      The one-based library slot to load/unload, or the source slot for the transfer command.
drive_device              The drive's /dev/nst#, or /dev/tape/by-id/*-nst, or /dev/tape/by-path/* node.
Or, the destination slot for the transfer command.
drive_index               The zero-based drive index.
jobid                     Optional jobid. If present, it will be written after the timestamp to the log file.
jobname                   Optional job name. If present, it will be written after the timestamp to the log file.

-h, --help                Print this help message
-v, --version             Print the script name and version
```
