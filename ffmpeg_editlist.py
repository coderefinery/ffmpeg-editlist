#!/usr/bin/env python3

"""Cut and splice video files using a YAML definition file and ffmpeg
"""

__version__ = '0.5.0'

import argparse
import bisect
import itertools
import logging
from math import floor
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

import yaml

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

usage = """\

- workshop_description: >
    Description



- input: input.mkv

  - cover: {begin: "1:15:29", end: "1:51:34", w: 840, h: 300, x: 360}

"""

FFMPEG_COPY = ['-vcodec', 'copy', '-acodec', 'copy',]
FFMPEG_ENCODE = ['-c:v', 'libx264',
                 #'-preset', 'slow', '-crf', '22',
                 '-c:a', 'copy',
                 ]
# x is horizontal, y is vertical, from top left
FFMPEG_COVER = \
    "drawbox=enable='between(t,{begin},{end}):w={w}:h={h}:x={x}:y={y}:t=fill:c=black"

def generate_cover(begin, end, w=10000, h=10000, x=0, y=0):
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

def ensure_filedir_exists(filename):
    """Ensure a a directory exists, that can hold the file given as argument"""
    dirname = os.path.dirname(filename)
    if dirname == '':
        return
    if not os.path.isdir(dirname):
        os.makedirs(dirname)



def shell_join(x):
    return ' '.join(shlex.quote(str(_)) for _ in x)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('editlist')
    parser.add_argument('input', type=Path,
                        help="Input file or directory of files.")
    parser.add_argument('--output', '-o', default='.', type=Path,
                        help='Output directory')

    parser.add_argument('--limit', '-l', action='append',
                        help='Limit to only outputs matching this pattern.  There is no wildcarding.  This option can be given multiple times.')
    parser.add_argument('--check', '-c', action='store_true',
                        help="Don't encode or generate output files, just check consistency of the YAML file.  This *will* override the .info.txt output file.")
    parser.add_argument('--force', '-f', action='store_true',
                        help='Overwrite existing output files without prompting')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose (put ffmpeg in normal mode, otherwise ffmpeg is quiet.)')

    parser.add_argument('--reencode', action='store_true',
                        help='Re-encode all segments of the video.  See --preset and --crf to adjust parameters.'
                             'This is needed when you start a snipet in the middle of a video, since the video decoding '
                             'can only begin at a key frame.  '
                             'Default false.')
    parser.add_argument('--crf', default=20, type=int,
                        help='x264 crf (preceived quality) to use for re-encoding, lower is higher quality.  '
                             'Reasonable options are 20 (extremely good) to 30 (lower quality) (the absolute range 1 - 51); '
                             'higher numbers take less time to encode.'
                             'Default is 20, which should be good enough for any purpose.')
    parser.add_argument('--preset', default='veryslow',
                        help='x264 preset to use for re-encoding, basically the encoding speed.  '
                             'Changing this affects how much time it will take to compress to get the --crf quality target '
                             'you request; slower=better compression by using more expensive codec features.  '
                             'Example options you might use include veryslow, slow, medium, fast, and ultrafast.  '
                             'Default is veryslow, use ultrafast for fast testing.')
    parser.add_argument('--threads', type=int,
                        help='Number of encoding threads.  Default: unset, autodetect')
    parser.add_argument('--wait', action='store_true',
                        help='Wait after each encoding (don\'t clean up the temporary directory right away')
    args = parser.parse_args()

    if args.threads:
        FFMPEG_ENCODE.extend(['-threads', str(args.threads)])
    FFMPEG_ENCODE.extend(['-preset', args.preset])
    FFMPEG_ENCODE.extend(['-crf', str(args.crf)])

    all_inputs = set()

    # Open the input file.  Parse out of markdown if it is markdown:
    data = open(args.editlist).read()
    if '```' in data:
        matches = re.findall(r'`{3,}[^\n]*\n(.*?)\n`{3,}', data, re.MULTILINE|re.DOTALL)
        #print(matches)
        data = '\n'.join([m for m in matches])
        #print(data)
    data = yaml.safe_load(data)


    PWD = Path(os.getcwd())
    LOGLEVEL = 31
    if args.verbose:
        LOGLEVEL = 40
    workshop_title = None
    workshop_description = None

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
            if 'workshop_description' in segment:
                workshop_description = segment['workshop_description'].strip()
            if 'workshop_title' in segment:
                workshop_title = segment['workshop_title']
            if 'output' not in segment:
                continue
            allow_reencode = segment.get('reencode', True)
            # Exclude non-matching files if '--limit' specified.
            if args.limit and not any(limit_match in segment['output'] for limit_match in args.limit):
                continue
            input1 = input0
            editlist = segment.get('editlist', segment.get('time'))
            if editlist is None:
                continue
            for i, command in enumerate(editlist):

                # Is this a command to cover a part of the video?
                if isinstance(command, dict) and 'cover' in command:
                    cover = command['cover']
                    covers.append(seconds(cover['begin']))
                    filters.append(generate_cover(**cover))
                    continue
                # Input command: change input files
                elif isinstance(command, dict) and 'input' in command:
                    input1 = command['input']
                    continue
                # Start command: start a segment
                elif isinstance(command, dict) and 'start' in command:
                    start = command['start']
                    continue
                elif isinstance(command, dict) and 'begin' in command:
                    start = command['begin']
                    continue
                # End command: process this segment and all queued commands
                elif isinstance(command, dict) and 'stop' in command:
                    stop = command['stop']
                    # Continue below to process this segment
                elif isinstance(command, dict) and 'end' in command:
                    stop = command['end']
                    # Continue below to process this segment
                # Is this a TOC entry?
                # If it's a dict, it is a table of contents entry that will be
                # mapped to the correct time in the procesed video.
                # This is a TOC entry
                elif isinstance(command, dict):
                    ( (time, title), ) = list(command.items())
                    if time == '-':
                        time = start
                    #print(start, title)
                    #print('TOC', start, title, segment)
                    TOC.append((seconds(time), title))
                    continue


                # A time segment in the format 'start, stop'
                else:
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
                    input1 = os.path.expanduser(input1)
                all_inputs.add(input1)

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
                       *(FFMPEG_ENCODE if (args.reencode and allow_reencode) or filters else FFMPEG_COPY),
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
            ensure_filedir_exists(output)
            if output in all_inputs:
                raise RuntimeError("Output is the same as an input file, aborting.")
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


            video_description = [ ]
            if segment.get('title'):
                title = segment['title']
                if workshop_title is not None:
                    title = title + ' - ' + workshop_title

                video_description.extend([title, '\n'])
            if segment.get('description'):
                video_description.extend([segment['description'].strip().replace('\n', '\n\n')])
            # Print out the table of contents
            video_description.append('\n')
            for time, name in TOC:
                LOG.debug("TOC entry %s %s", time, name)
                new_time = map_time(segment_list, time)
                print(humantime(new_time), name)
                video_description.append(f"{humantime(new_time)} {name}")

            if workshop_description:
                video_description.extend(['\n-----\n', workshop_description, '\n'])

            if video_description:
                with open(str(output)+'.info.txt', 'w') as toc_file:
                    toc_file.write('\n'.join(video_description))

            # Print out covered segments
            for time in covers:
                new_time = map_time(segment_list, time)
                LOG.info("Check cover at %s", humantime(new_time))

            if args.wait:
                input('press return to continue> ')



if __name__ == '__main__':
    main()
