#!/usr/bin/env python3

import argparse
import bisect
import itertools
from math import floor
from pathlib import Path
import os
import re
import tempfile
import yaml
import subprocess


FFMPEG_COPY = ['-vcodec', 'copy', '-acodec', 'copy',]
FFMPEG_ENCODE = ['-c:v', 'libx264',
                 '-preset', 'slow', '-crf', '22',
                 '-c:a', 'copy',
                 ]
# x is horizontal, y is vertical, from top left
FFMPEG_COVER = \
    "drawbox=enable='between(t,{begin},{end}):w={w}:h={h}:x={x}:y={y}:t=fill:c=black"

def cover(begin, end, w=0, h=0, x=0, y=0):
    begin = seconds(begin)
    end = seconds(end)
    return FFMPEG_COVER.format(**locals())


def is_time(x):
    m = re.match(r'((\d{1,2}:)?\d{1,2}:)?\d{1,2}(\.\d*)?$', x)
    return bool(m)
def test_is_time():
    assert is_time('10')
    assert is_time('10.')
    assert is_time('10:10.5')
    assert is_time('10:10:10.5')
    assert not is_time('1e5')
    assert not is_time('string')
    assert not is_time('.5')
    assert not is_time('Exercise: aoeu')
def seconds(x):
    """Convert HH:MM:SS.SS or S to seconds"""
    if isinstance(x, (int, float)):
        return x
    x = x.split(':')
    sec = float(x[-1])
    if len(x) >= 2:
        sec += float(x[-2]) * 60
    if len(x) >= 3:
        sec += float(x[-3]) * 3600
    return sec
def test_seconds():
    assert seconds(30) == 30
    assert seconds(30.5) == 30.5
    assert seconds('30') == 30
    assert seconds('1:30') == 90
    assert seconds('1:1:30') == 3690
    assert seconds('1:1:30.5') == 3690.5
def humantime(x):
    hou = x // 3600
    min = (x % 3600) // 60
    sec = x % 60
    if hou:
        return "%d:%02d:%02d"%(hou, min, floor(sec))
    return "%02d:%02d"%(min, floor(sec))
def test_humantime():
    assert humantime(30) == "00:30"
    assert humantime(90) == "01:30"
    assert humantime(150) == "02:30"
    assert humantime(3690) == "1:01:30"
    assert humantime(3690.5) == "1:01:30"
    assert humantime(7350) == "2:02:30"
    assert humantime(43950) == "12:12:30"

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('editlist')
    parser.add_argument('input', type=Path,
                        help="Input file or directory of files.")
    parser.add_argument('--wait', action='store_true',
                        help='Wait after each encoding')
    parser.add_argument('--output', '-o', default='.', type=Path,
                        help='Output directory')
    parser.add_argument('-limit', '-l',
                        help='Limit to only these outputs')
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

    input0 = args.input
    for segment in data:
        print(segment)

        tmp_outputs = [ ]
        TOC = [ ]
        time_lookups = [ ]
        cumulative_time = 0
        filters = [ ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Find input
            if 'input' in segment:
                input0 = segment['input']
            if 'output' not in segment:
                continue
            # Exclude non-matching files if '--limit' specified.
            if args.limit and args.limit not in segment['output']:
                continue
            for i, time in enumerate(segment['time']):
                input1 = input0

                # Is this a TOC entry?
                # If it's a dict, it is a table of contents entry that will be
                # mapped to the correct time in the procesed video.
                if isinstance(time, dict) and 'cover' in time:
                    filters.append(cover(**time['cover']))
                    continue
                if isinstance(time, dict):
                    ( (start, title), ) = list(time.items())
                    print(start, title)
                    print('TOC', start, title, segment)
                    TOC.append((seconds(start), title))
                    continue

                # time can be string with comma or list
                if isinstance(time, str):
                    time = time.split(',')
                if len(time) == 2:
                    start, stop = time
                elif len(time) == 3:
                    input1, start, stop = time
                start = str(start).strip()
                stop = str(stop).strip()


                # Find input file
                if not os.path.exists(input1):
                    input1 = args.input / input1

                time_lookups.append([seconds(start), cumulative_time])
                time_lookups.append([seconds(stop), None])
                cumulative_time += seconds(stop) - seconds(start)
                # filters
                if filters:
                    filters = ['-vf', ','.join(filters)]

                tmp_out = str(Path(tmpdir)/('tmpout-%02d.mp4'%i))
                tmp_outputs.append(tmp_out)
                cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                       '-i', input1, '-ss', start, '-to', stop,
                       *(FFMPEG_ENCODE if args.reencode or filters else FFMPEG_COPY),
                       *filters,
                       tmp_out,
                       ]
                print(cmd)
                subprocess.check_call(cmd)

            # Create the playlist of inputs
            playlist = Path(tmpdir) / 'playlist.txt'
            with open(playlist, 'w') as playlist_f:
                for file_ in tmp_outputs:
                    playlist_f.write('file '+str(file_)+'\n')
            print(open(playlist).read())
            # Re-encode
            output = args.output / segment['output']
            cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                   #*itertools.chain.from_iterable(('-i', x) for x in tmp_outputs),
                   #'-i', 'concat:'+'|'.join(tmp_outputs),
                   '-safe', '0', '-f', 'concat', '-i', playlist,
                   '-c', 'copy',
                   *(['-y'] if args.force else []),
                   output,
                   ]
            print(cmd)
            subprocess.check_call(cmd)

            # Print table of contents
            import pprint
            pprint.pprint(time_lookups)
            pprint.pprint(TOC)
            time_lookup_vals = [x[0] for x in time_lookups]
            toc_file = open(output+'.toc.txt', 'w')
            for time, name in TOC:
                i = bisect.bisect_right(time_lookup_vals, time)
                print(humantime(time - time_lookups[i-1][0] + time_lookups[i-1][1]), name)
                print(humantime(time - time_lookups[i-1][0] + time_lookups[i-1][1]), name,
                      file=toc_file)

            if args.wait:
                input('press return to continue> ')
