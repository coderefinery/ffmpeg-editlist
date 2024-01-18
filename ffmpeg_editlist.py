#!/usr/bin/env python3

"""Cut and splice video files using a YAML definition file and ffmpeg
"""

__version__ = '0.5.4'

import argparse
import bisect
import contextlib
import copy
from datetime import timedelta
import itertools
import logging
from math import floor
import os
from pathlib import Path
import re
import shlex
import shutil
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

FFMPEG_VIDEO_COPY = ['-vcodec', 'copy',]
FFMPEG_VIDEO_ENCODE = ['-c:v', 'libx264', ] #'-preset', 'slow', '-crf', '22'
FFMPEG_AUDIO_COPY = ['-acodec', 'copy',]
FFMPEG_AUDIO_ENCODE = ['-acodec', 'aac', '-b:a', '160k', ]
# x is horizontal, y is vertical, from top left
FFMPEG_COVER = \
    "drawbox=enable='between(t,{begin},{end}):w={w}:h={h}:x={x}:y={y}:t=fill:c=black'"
# Only used for images
FFMPEG_FRAMERATE = 30

def generate_cover(begin, end, w=10000, h=10000, x=0, y=0):
    begin = seconds(begin)
    end = seconds(end)
    return FFMPEG_COVER.format(**locals())

def generate_crop(w, h, x, y):
    return ['-filter:v', f"crop={w}:{h}:{x}:{y}"]


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

def map_time(seg_n, lookup_table, time):
    """Map a time from source time to output time
    """
    time_lookup_vals = [(x[0], x[1]) for x in lookup_table]
    i = bisect.bisect_right(time_lookup_vals, (seg_n, time))
    #print(f"lookup of {seg_n},{time} found at i={i}")
    if lookup_table[i-1][1] is None:
        #LOG.error("%s", lookup_table)
        #LOG.error("%s", time)
        LOG.error("Bad time lookup (type 1) for %s(=%ss)", humantime(time), time)
        sys.exit(1)
    if lookup_table[i-1][2] is None:
        #LOG.error("%s", lookup_table)
        #LOG.error("%s", time)
        LOG.error("Bad time lookup (type 2) for %s(=%ss)", humantime(time), time)
        sys.exit(1)
    return time - lookup_table[i-1][1] + lookup_table[i-1][2]

def ensure_filedir_exists(filename):
    """Ensure a a directory exists, that can hold the file given as argument"""
    dirname = os.path.dirname(filename)
    if dirname == '':
        return
    if not os.path.isdir(dirname):
        os.makedirs(dirname)

@contextlib.contextmanager
def atomic_write(fname, mode='w+b'):
    """Atomically write into the given fname.

    Returns a NamedTemporaryFile that will be moved (atomically,
    os.replace).  Use [returnvalue].name to access the file's name.
    """
    if os.access(fname, os.F_OK) and not os.access(fname, os.W_OK, follow_symlinks=False):
        raise PermissionError(fname)
    root, ext = os.path.splitext(fname)
    import string
    import random
    randstr = ''.join(random.choice(string.ascii_lowercase) for i in range(20))
    tmp = '.'.join((str(fname), randstr, 'tmp'))
    try:
        yield tmp
    except:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    else:
        try:
            os.replace(tmp, fname)
        except FileNotFoundError:
            pass

def shell_join(x):
    return ' '.join(shlex.quote(str(_)) for _ in x)



def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser()
    parser.add_argument('editlist')
    parser.add_argument('input', type=Path,
                        help="Input file or directory of files.")
    parser.add_argument('--output', '-o', default='.', type=Path,
                        help='Output directory')
    parser.add_argument('--srt', action='store_true',
                        help='Also convert subtitles')

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
    parser.add_argument('--list', action='store_true',
                        help="Don't do anything, just list all outputs that would be processed (and nothing else)")
    args = parser.parse_args(argv)

    if args.threads:
        FFMPEG_VIDEO_ENCODE.extend(['-threads', str(args.threads)])
    FFMPEG_VIDEO_ENCODE.extend(['-preset', args.preset])
    FFMPEG_VIDEO_ENCODE.extend(['-crf', str(args.crf)])

    if args.srt:
        import srt

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
    options_ffmpeg_global = [ ]

    #
    # For each output file
    #
    input0 = args.input
    for segment in data:
        #print(segment)

        tmp_outputs = [ ]
        TOC = [ ]
        segment_list = [ ]
        cumulative_time = 0
        filters = [ ]
        covers = [ ]
        options_ffmpeg_output = [ ]
        subtitles = [ ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # Find input
            if 'input' in segment:
                input0 = segment['input']
            if 'workshop_description' in segment:
                workshop_description = segment['workshop_description'].strip()
            if 'workshop_title' in segment:
                workshop_title = segment['workshop_title']
            if 'crop' in segment:
                # -filter:v "crop=w:h:x:y"    - x:y is top-left corner
                options_ffmpeg_output.extend(generate_crop(**segment['crop']))


            if 'output' not in segment:
                continue
            allow_reencode = segment.get('reencode', True)
            # Exclude non-matching files if '--limit' specified.
            if args.limit and not any(limit_match in segment['output'] for limit_match in args.limit):
                continue
            if args.list:
                print(segment['output'])
                continue
            input1 = input0
            editlist = segment.get('editlist', segment.get('time'))
            if editlist is None:
                continue

            #
            # For each segment in the output
            #
            options_ffmpeg_segment = [ ]
            segment_type = 'video'
            segment_number = 0
            for i, command in enumerate(editlist):

                # Is this a command to cover a part of the video?
                if isinstance(command, dict) and 'cover' in command:
                    cover = command['cover']
                    covers.append((segment_number, seconds(cover['begin'])))
                    filters.append(generate_cover(**cover))
                    continue
                # Input command: change input files
                elif isinstance(command, dict) and 'input' in command:
                    input1 = command['input']
                    # Handle png images
                    if 'duration' in command:
                        start = 0
                        stop = seconds(command['duration'])
                        segment_type = 'image'
                        segment_number += 1
                    else:
                        continue
                # Start command: start a segment
                elif isinstance(command, dict) and 'start' in command:
                    segment_number += 1
                    start = command['start']
                    continue
                elif isinstance(command, dict) and 'begin' in command:
                    segment_number += 1
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
                    if title in {'stop', 'start', 'begin', 'end', 'cover', 'input'}:
                        LOG.error("ERROR: Suspicious TOC entry name, aborting encoding: %s", title)
                        sys.exit(1)
                    #print(start, title)
                    #print('TOC', start, title, segment)
                    TOC.append((segment_number, seconds(time), title))
                    continue


                # The end of our time segment (from 'start' to 'stop').  Do the
                # actual processing of this segment now.
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

                # Print status
                LOG.info("\n\nBeginning %s (line %d)", segment.get('title') if 'title' in segment else '[no title]', i)

                # Find input file
                if not os.path.exists(input1):
                    input1 = args.input / input1
                    input1 = os.path.expanduser(input1)
                all_inputs.add(input1)

                segment_list.append([segment_number, seconds(start), cumulative_time])
                segment_list.append([segment_number, seconds(stop), None])
                start_cumulative = cumulative_time
                cumulative_time += seconds(stop) - seconds(start)
                # filters
                if filters:
                    filters = ['-vf', ','.join(filters)]
                # Encode for video, image, etc?
                if segment_type == 'video':
                    encoding_args = ['-i', input1,
                                     '-ss', start, '-to', stop,
                                     *(FFMPEG_VIDEO_ENCODE if (args.reencode and allow_reencode) or filters else FFMPEG_VIDEO_COPY),
                                     *FFMPEG_AUDIO_COPY,
                                     ]
                    if seconds(start) > seconds(stop):
                        raise RuntimeError(f"start is greater than stop time ({start} > {stop} time in {segment.get('title')}")
                elif segment_type == 'image':
                    # https://trac.ffmpeg.org/wiki/Slideshow
                    encoding_args = ['-loop', '1',
                                     '-i', input1,
                                     '-t', str(command['duration']),
                                     '-vf', f'fps={FFMPEG_FRAMERATE},format=yuv420p',
                                     '-c:v', 'libx264', ]#'-r', str(FFMPEG_FRAMERATE)]
                else:
                    raise RuntimeError(f"unknown segment_type: {segment_type}")

                # Do encoding
                tmp_out = str(Path(tmpdir)/('tmpout-%02d.mkv'%i))
                tmp_outputs.append(tmp_out)
                cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                       *encoding_args,
                       *options_ffmpeg_output,
                       *options_ffmpeg_segment,
                       *filters,
                       tmp_out,
                       ]
                LOG.info(shell_join(cmd))
                if not args.check:
                    subprocess.check_call(cmd)

                # Subtitles?
                if args.srt:
                    sub_file = os.path.splitext(input1)[0] + '.srt'
                    start_dt = timedelta(seconds=seconds(start))
                    end_dt   = timedelta(seconds=seconds(stop))
                    start_cumulative_dt = timedelta(seconds=start_cumulative)
                    duration_segment_dt = end_dt-start_dt
                    for sub in srt.parse(open(sub_file).read()):
                        if sub.end < start_dt: continue
                        if sub.start > end_dt: continue
                        sub = copy.copy(sub)
                        sub.start = sub.start - start_dt + start_cumulative_dt
                        sub.end   = sub.end   - start_dt + start_cumulative_dt
                        sub.start = max(sub.start, start_cumulative_dt)
                        sub.end   = min(sub.end,   start_cumulative_dt + duration_segment_dt)
                        subtitles.append(sub)

                # Reset for the next round
                filters = [ ]
                options_ffmpeg_segment = [ ]
                segment_type = 'video'

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
            tmpdir_out = str(Path(tmpdir)/('final-'+segment['output'].replace('/', '%2F')))
            cmd = ['ffmpeg', '-loglevel', str(LOGLEVEL),
                   #*itertools.chain.from_iterable(('-i', x) for x in tmp_outputs),
                   #'-i', 'concat:'+'|'.join(tmp_outputs),
                   '-safe', '0', '-f', 'concat', '-i', playlist,
                   '-fflags', '+igndts',
                   '-c', 'copy',
                   *(['-y'] if args.force else []),
                   tmpdir_out,
                   ]
            LOG.info(shell_join(cmd))
            if not args.check:
                subprocess.check_call(cmd)
            # We need another copy, since ffmpeg detects output based on filename.  Yet for atomicness, we need a temporary filename for the temp part
            if not args.check:
                with atomic_write(output) as tmp_output:
                    shutil.move(tmpdir_out, tmp_output)

            # Subtitles
            if args.srt:
                srt_output = os.path.splitext(output)[0] + '.srt'
                open(srt_output, 'w').write(srt.compose(subtitles))

            # Print table of contents
            import pprint
            LOG.debug(pprint.pformat(segment_list))
            LOG.debug(pprint.pformat(TOC))


            video_description = [ ]
            if segment.get('title'):
                title = segment['title']
                if workshop_title is not None:
                    title = title + ' - ' + workshop_title

                video_description.extend([title.strip()])
            if segment.get('description'):
                video_description.extend([segment['description'].strip().replace('\n', '\n\n')])
            # Print out the table of contents
            #video_description.append('\n')
            toc = [ ]
            for seg_n, time, name in TOC:
                LOG.debug("TOC entry %s %s", time, name)
                new_time = map_time(seg_n, segment_list, time)
                print(humantime(new_time), name)
                toc.append(f"{humantime(new_time)} {name}")
            if toc:
                video_description.append('\n'.join(toc))

            if workshop_description:
                video_description.append('-----')
                video_description.append(workshop_description.replace('\n', '\n\n').strip())

            if video_description:
                with atomic_write(os.path.splitext(str(output))[0]+'.info.txt', 'w') as toc_file:
                    open(toc_file, 'w').write('\n\n'.join(video_description))

            # Print out covered segments (for verification purposes)
            for seg_n, time in covers:
                new_time = map_time(seg_n, segment_list, time)
                LOG.info("Check cover at %s", humantime(new_time))

            if args.wait:
                input('press return to continue> ')



if __name__ == '__main__':
    main()
