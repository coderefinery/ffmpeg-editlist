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
args = parser.parse_args()

data = yaml.safe_load(open(args.editlist))
PWD = Path(os.getcwd())
LOGLEVEL = 31


input0 = args.input
for segment in data:
    print(segment)
    tmp_outputs = [ ]
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

            # Find input file
            if not os.path.exists(input1):
                input1 = args.input / input1

            # Normalize times
            start = str(start).strip()
            stop = str(stop).strip()

            tmp_out = str(Path(tmpdir)/('tmpout-%02d.mp4'%i))
            tmp_outputs.append(tmp_out)
            cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                   '-i', input1, '-ss', start, '-to', stop,
                   '-vcodec', 'copy', '-acodec', 'copy',
                   tmp_out
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
               args.output / segment['output'],
               ]
        print(cmd)
        subprocess.check_call(cmd)
        if args.wait:
            input('press return to continue> ')
