#!/usr/bin/env python3

import argparse
import bisect
import itertools
import logging
from math import floor
from pathlib import Path
import os
import re
import shlex
import tempfile
import yaml
import subprocess

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

FFMPEG_COPY = ['-vcodec', 'copy', '-acodec', 'copy',]
FFMPEG_ENCODE = ['-c:v', 'libx264',
                 #'-preset', 'slow', '-crf', '22',
                 '-c:a', 'copy',
                 ]
# x is horizontal, y is vertical, from top left
FFMPEG_COVER = \
    "drawbox=enable='between(t,{begin},{end}):w={w}:h={h}:x={x}:y={y}:t=fill:c=black"

def generate_cover(begin, end, w=0, h=0, x=0, y=0):
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

def map_time(lookup_table, time):
    """Map a time from source time to output time
    """
    time_lookup_vals = [x[0] for x in lookup_table]
    i = bisect.bisect_right(time_lookup_vals, time)
    if lookup_table[i-1][1] is None:
        LOG.error("%s", lookup_table)
        LOG.error("Bad time lookup at %d, %s", i, lookup_table[i-1])
    return time - lookup_table[i-1][0] + lookup_table[i-1][1]

def shell_join(x):
    return ' '.join(shlex.quote(str(_)) for _ in x)


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
    parser.add_argument('--threads', type=int,
                        help='Number of encoding threads')
    parser.add_argument('--check', '-c', action='store_true',
                        help="Don't encode, just check consistency")
    parser.add_argument('--force', '-f', action='store_true',
                        help='Overwrite existing files')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose (put ffmpeg in normal mode)')
    parser.add_argument('--preset', default='slow',
                        help='')
    parser.add_argument('--crf', default=22, type=int,
                        help='')
    args = parser.parse_args()

    if args.threads:
        FFMPEG_ENCODE.extend(['-threads', str(args.threads)])
    FFMPEG_ENCODE.extend(['-preset', args.preset])
    FFMPEG_ENCODE.extend(['-crf', str(args.crf)])


    # Open the input file.  Parse out of markdown if it is markdown:
    data = open(args.editlist).read()
    if '```' in data:
        matches = re.findall(r'`{3,}[^\n]*\n(.*?)\n`{3,}', data, re.MULTILINE|re.DOTALL)
        print(matches)
        data = '\n'.join([m for m in matches])
        print(data)
    data = yaml.safe_load(data)


    PWD = Path(os.getcwd())
    LOGLEVEL = 31
    if args.verbose:
        LOGLEVEL = 40

    input0 = args.input
    for segment in data:
        #print(segment)

        tmp_outputs = [ ]
        TOC = [ ]
        segment_list = [ ]
        cumulative_time = 0
        filters = [ ]
        covers = [ ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Find input
            if 'input' in segment:
                input0 = segment['input']
            if 'output' not in segment:
                continue
            # Exclude non-matching files if '--limit' specified.
            if args.limit and args.limit not in segment['output']:
                continue
            for i, command in enumerate(segment['time']):
                input1 = input0

                # Is this a TOC entry?
                # If it's a dict, it is a table of contents entry that will be
                # mapped to the correct time in the procesed video.
                if isinstance(command, dict) and 'cover' in command:
                    cover = command['cover']
                    covers.append(seconds(cover['begin']))
                    filters.append(generate_cover(**cover))
                    continue
                # This is a TOC entry
                if isinstance(command, dict):
                    ( (start, title), ) = list(command.items())
                    #print(start, title)
                    #print('TOC', start, title, segment)
                    TOC.append((seconds(start), title))
                    continue

                # This is a regular time segment command
                # time can be string with comma or list
                time = command
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

                segment_list.append([seconds(start), cumulative_time])
                segment_list.append([seconds(stop), None])
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
                LOG.info(shell_join(cmd))
                if not args.check:
                    subprocess.check_call(cmd)
                filters = [ ]

            # Create the playlist of inputs
            playlist = Path(tmpdir) / 'playlist.txt'
            with open(playlist, 'w') as playlist_f:
                for file_ in tmp_outputs:
                    playlist_f.write('file '+str(file_)+'\n')
            LOG.debug("Playlist:")
            LOG.debug(open(playlist).read())
            # Re-encode
            output = args.output / segment['output']
            cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                   #*itertools.chain.from_iterable(('-i', x) for x in tmp_outputs),
                   #'-i', 'concat:'+'|'.join(tmp_outputs),
                   '-safe', '0', '-f', 'concat', '-i', playlist,
                   '-fflags', '+igndts',
                   '-c', 'copy',
                   *(['-y'] if args.force else []),
                   output,
                   ]
            LOG.info(shell_join(cmd))
            if not args.check:
                subprocess.check_call(cmd)

            # Print table of contents
            import pprint
            LOG.debug(pprint.pformat(segment_list))
            LOG.debug(pprint.pformat(TOC))


            if not args.check:
                toc_file = open(str(output)+'.toc.txt', 'w')
            for time, name in TOC:
                LOG.debug(f"TOC entry: {time} {name}")
                new_time = map_time(segment_list, time)
                print(humantime(new_time), name)
                if not args.check:
                    print(humantime(new_time), name,
                        file=toc_file)

            # Print out covered segments
            for time in covers:
                new_time = map_time(segment_list, time)
                LOG.info("Check cover at %s", humantime(new_time))

            if args.wait:
                input('press return to continue> ')
