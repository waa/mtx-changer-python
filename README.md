# mtx-changer-python.py
- A drop-in replacement for Bacula's original bash/perl `mtx-changer` script to control tape libraries - Initial enhancements include automatic tape drive cleaning:
  - Clear logging of all actions when debug = True.
  - Control what information gets logged by setting the 'debug_level' variable.
  - Automatic tape drive cleaning. Can be configured to check a drive's `tapeinfo` status after an unload and automatically load a cleaning tape, wait, then unload it.

Please edit the `mtx-changer-python.conf` configuration file to customize what (if anything) gets logged to the debug log file, and to set other custom variables for the library or libraries managed by the SD.

This mtx-changer-python.py script is meant to be called by the Bacula Storage daemon (SD) to load/unload drives in a tape library, or to issue queries to the library to get information.

To use the mtx-changer-python.py script with an autochanger, it must be configured in the SD's Autochanger `Changer Command` setting like:
```
Autochanger {
  Name = AutochangerName
  Description = "Autochanger with four drives"
  ChangerDevice = "/dev/tape/by-id/scsi-XXXXXXXXXX"
  ChangerCommand = "/opt/bacula/scripts/mtx-changer-python.py %c %o %S %a %d %i %j"    <---- Here
  Device = Drive_0, Drive_1, Drive_2, Drive_3
}
```

Where the variables passed are:
```
%c - Library's changer device node. eg: /dev/tape/by-id/scsi-XXXXXXXXXX, or /dev/sgX
%o - The command. Valid options: slots, list, listall, loaded, load, unload, transfer.
%S - The one-based library slot to load/unload, or the source slot for the transfer command.
%a - The drive's "ArchiveDevice". eg: /dev/nst#, or /dev/tape/by-id/*-nst, or /dev/tape/by-path/* node.
     Or, the destination slot for the transfer command.
%d - The zero-based drive index.
%i - Optional jobid. If present, it will be written after the timestamp to the log file.*
%j - Optional job name. If present, it will be written after the jobid to the log file.
```
NOTE: The `%i` variable is not available as of 20230526. I have an official request with the developers to add this variable. Until this feature request is implemented, just pass a literal empty string in this place instead of %i: ''

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

### Example command lines and outputs:

- `slots` Prints the number of slots to stdout:
```
# ./mtx-changer-python.py /dev/chgr0 slots X Y Z
44
```
The slots command does not use the slot, drive device, nor drive index (X, Y, Z), but they must be present.

- `list` will return a list of FULL slots in the format 'slot:volume' like this:
```
# ./mtx-changer-python.py /dev/chgr0 list X Y Z
30:G03030TA
1:G03001TA
2:G03002TA
3:G03003TA
4:G03004TA
5:G03005TA
6:G03006TA
7:G03007TA
8:G03008TA
9:G03009TA
10:G03010TA
11:G03011TA
12:G03012TA
13:G03013TA
14:G03014TA
15:G03015TA
16:G03016TA
17:G03017TA
18:G03018TA
19:G03019TA
20:G03020TA
21:G03021TA
22:G03022TA
23:G03023TA
24:G03024TA
25:G03025TA
26:G03026TA
27:G03027TA
28:G03028TA
29:G03029TA
33:G03033TA
34:G03034TA
35:G03035TA
36:G03036TA
37:G03037TA
38:G03038TA
39:G03039TA
40:CLN303TA
41:G03031TA
42:G03032TA
```
The list command does not use the slot, drive device, nor drive index (X, Y, Z), but they must be present.

- `listall` will return a list of all slots in the library in different formats depending on whether the location represents a Drive, a Slot, or an Input/Output location, and whether it is full or empty:
```
# ./mtx-changer-python.py /dev/chgr0 listall X Y Z
D:0:F:30:G03030TA
D:1:E
D:2:E
D:3:E
S:1:F:G03001TA
S:2:F:G03002TA
S:3:F:G03003TA
S:4:F:G03004TA
S:5:F:G03005TA
S:6:F:G03006TA
S:7:F:G03007TA
S:8:F:G03008TA
S:9:F:G03009TA
S:10:F:G03010TA
S:11:F:G03011TA
S:12:F:G03012TA
S:13:F:G03013TA
S:14:F:G03014TA
S:15:F:G03015TA
S:16:F:G03016TA
S:17:F:G03017TA
S:18:F:G03018TA
S:19:F:G03019TA
S:20:F:G03020TA
S:21:F:G03021TA
S:22:F:G03022TA
S:23:F:G03023TA
S:24:F:G03024TA
S:25:F:G03025TA
S:26:F:G03026TA
S:27:F:G03027TA
S:28:F:G03028TA
S:29:F:G03029TA
S:30:E
S:31:E
S:32:E
S:33:F:G03033TA
S:34:F:G03034TA
S:35:F:G03035TA
S:36:F:G03036TA
S:37:F:G03037TA
S:38:F:G03038TA
S:39:F:G03039TA
S:40:F:CLN303TA
I:41:F:G03031TA
I:42:F:G03032TA
I:43:E
I:44:E
```
The listall command does not use the slot, drive device, nor drive index (X, Y, Z), but they must be present.

- `load` and `unload` commands do not log anything except on error, which will be printed in the joblog by the SD. On successful load/unload of a tape from a slot to/from a drive, the script simply exits with return code 0, else the return code is 1.

In this example, we load a tape from slot 30 into drive 1 and then unload it:
```
# ./mtx-changer-python.py /root/chgr80 load 30 /dev/tape/by-id/scsi-350223344ab001000-nst 1
# echo $?
0

# ./mtx-changer-python.py /root/chgr80 unload 30 /dev/tape/by-id/scsi-350223344ab001000-nst 1
# echo $?
0
```

- `loaded` will return the slot of the tape that is loaded in the drive, or zero (0) if the drive is empty.

Here we see that drive 0 is empty, and drive 1 is loaded with a tape from slot 30:
```
./mtx-changer-python.py /root/chgr80 loaded X Y 0    # Drive index 0 is empty.
0

./mtx-changer-python.py /root/chgr80 loaded X Y 1    # Drive index 1 is loaded with a tape from slot 30
30
```
The loaded command does not use the slot and drive device parameters (X, Y) but they must be present.

- `transfer` will attempt to transfer a tape from one slot to another.

The transfer command does not log anything except on error, which will be printed in the joblog by the SD. On successful load/unload of a tape from a slot to a drive, the script simply exits with return code 0, or it will exit with return code 1 on a failure.

Here we attempt to transfer a full slot (31) to an empty slot (29) and the command is successful:
```
# ./mtx-changer-python.py -c ./mtx-changer-python.conf /root/chgr80 transfer 31 29 X
# echo $?
0
```

Here we attempt to transfer a now empty slot (31) to a now full slot (29) and the command fails. Notice we have the failure reason printed to stdout. This would be printed in the joblog by the SD:
```
# ./mtx-changer-python.py -c ./mtx-changer-python.conf /root/chgr80 transfer 29 31 X
Err: The source slot is empty, or the destination slot is full. Will not even attempt the transfer
# echo $?
1
```
The transfer command uses the drive device parameter as the destination slot, and does not use the drive index (X), but it must be present.
