#!/usr/bin/env python3

import argparse
import itertools
from pathlib import Path
import os
import re
import tempfile
import yaml
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument('editlist')
parser.add_argument('input', type=Path,
                    help="Input file or directory of files.")
parser.add_argument('--wait', action='store_true',
                    help='Wait after each encoding')
parser.add_argument('--output', '-o', default='.', type=Path,
                    help='Output directory')
parser.add_argument('--reencode', action='store_true',
                    help='Re-encode the video')
parser.add_argument('--force', '-f', action='store_true',
                    help='Overwrite existing files')
parser.add_argument('--verbose', '-v', action='store_true',
                    help='Verbose (put ffmpeg in normal mode)')
args = parser.parse_args()

data = yaml.safe_load(open(args.editlist))
PWD = Path(os.getcwd())
LOGLEVEL = 31
if args.verbose:
    LOGLEVEL = 40

FFMPEG_COPY = ['-vcodec', 'copy', '-acodec', 'copy',]
FFMPEG_ENCODE = ['-c:v', 'libx264',
                 '-preset', 'slow', '-crf', '22',
                 '-c:a', 'copy',
                 ]



def is_time(x):
    m = re.match(r'((\d{1,2}:)?\d{1,2}:)?\d{1,2}(.(\d+)?))?', x)
    if m:
        return True
def seconds(x):
    """Convert HH:MM:SS.SS to seconds"""
    x = x.split(':')
    seconds = float(x[-1])
    if len(x) >= 2:
        seconds += float(x[-2])
    if len(x) >= 3:
        seconds += float(x[-3])
    return seconds
def humantime(x):
    hours = x // 3600
    minutes = (x % 3600) // 60
    seconds = x % 60
    if hours:
        return "%d:%02d:%02d"%(hours, minutes, seconds)
    return "%02d:%02d"%(minutes, seconds)


input0 = args.input
for segment in data:
    print(segment)

    tmp_outputs = [ ]
    TOC = [ ]
    time_lookups = [ ]
    cumulative_time = [ ]

    with tempfile.TemporaryDirectory() as tmpdir:
        # Find input
        if 'input' in segment:
            input0 = segment['input']
        if 'output' not in segment:
            continue
        for i, time in enumerate(segment['time']):
            input1 = input0

            # time can be string with comma or list
            if isinstance(time, str):
                time = time.split(',')
            if len(time) == 2:
                start, stop = time
            elif len(time) == 3:
                input1, start, stop = time

            # Is this a TOC entry?
            if not is_time(stop):
                title = stop
                TOC.append(start, title)
                continue

            # Find input file
            if not os.path.exists(input1):
                input1 = args.input / input1

            # Normalize times
            start = str(start).strip()
            stop = str(stop).strip()

            time_lookups.append([seconds(start), cumulative_time])
            time_lookups.append([seconds(stop), None])
            cumulative_time += seconds(stop) - seconds(start)

            tmp_out = str(Path(tmpdir)/('tmpout-%02d.mp4'%i))
            tmp_outputs.append(tmp_out)
            cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                   '-i', input1, '-ss', start, '-to', stop,
                   *(FFMPEG_ENCODE if args.reencode else FFMPEG_COPY),
                   tmp_out,
                   ]
            print(cmd)
            subprocess.check_call(cmd)

        # Create the playlist of inputs
        playlist = Path(tmpdir) / 'playlist.txt'
        with open(playlist, 'w') as playlist_f:
            for file_ in tmp_outputs:
                playlist_f.write('file '+str(file_)+'\n')
        # Re-encode
        cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
               #*itertools.chain.from_iterable(('-i', x) for x in tmp_outputs),
               #'-i', 'concat:'+'|'.join(tmp_outputs),
               '-safe', '0', '-f', 'concat', '-i', playlist,
               '-c', 'copy',
               *(['-y'] if args.force else []),
               args.output / segment['output'],
               ]
        print(cmd)
        subprocess.check_call(cmd)
        if args.wait:
            input('press return to continue> ')
