# ffmpeg editlist utility

Often, one wants to reprocess a video file using some basic
operations, such as removing certain segments.  Rather than opening a
video editor, it is nice to be able to define a text file (the
**editlist**) with processing instructions, and then run it.  This
allows collaboration in the processing, for example sharing the
editlist file via git.

This utility takes a YAML definition of an editlist (segments to cut
out and re-assemble into a file), and does the re-assembling using the
ffmpeg command line utility.

This is currently an alpha-level utility: it works, but expect it may
not exactly fit your use case without a bit of work.  Documentation is
minimal but still needs improvement.  However, it has been used for
several large events.

Features include:

* YAML edit list definition.
* Select segments to stitch together in the final video file.
  Segments are either copied raw or re-encoded (`--reencode`).
* Give Table of Contents times (for example, '16:45: Lesson 2 begins')
  relative to the source video, output mapped to times in
  the output video automatically.
* Cover certain areas of video (for example, when an audience member
  appears).
* Everything scripted and non-interactive.



## Installation and dependencies.

This is a single-file script in Python, no installation is needed.

It depends on the `ffmpeg` command line utility and PyYAML (pip:
`pyyaml`).  Version requirements of `ffmpeg` are currently unknown.



## Usage

Create an edit list file (described in next section, including minimal
examples).  The general usage is:

```
python ffmpeg-editlist.py editlist.yaml input-dir [-o output-dir]
```

Where `input-dir` is the search path for input files and `output-dir`
(default `.`) is the output path for files.

Because of the way keyframes work, there may be missing segments
around the transition points.  After you have tested that your timings
seem reasonable, re-run with ``--reencode`` and it will do a full
re-encoding and make a seamless videos.  The default encoding settings
are designed to be slow but good enough for all practical purposes:

```
python ffmpeg-editlist.py editlist.yaml --reencode input-dir [-o output-dir]
```




## Editlist definition


### Minimal example: single file

```yaml
# Input is taken from command line argument `input`.
- output: output.mp4
  time:
    - [00:00, 5:00]     # These are time segments to include
    - [6:13, 99:00]
```

Run with `python ffmpeg-editlist.py editlist.yaml input.mkv`.


### Minimal example with multiple files

```yaml

- input: raw-day1.mkv
  output: day1-part1.mkv
  time:
    - [1:12, 55:30]

# Previous input file is used if no new input is defined
- output: day1-part2.mkv
  time:
    - [1:00:12, 1:54:00]
```

Run with `python ffmpeg-editlist.py editlist.yaml $input_directory`.


### Multi-file with video descriptions

This is a full example that demonstrates all features.

```yaml

- workshop_description: >
    If this exists, it will be appended to the bottom of every video
    description.  For example, it can be general information about the
    overall workshop.

# This input will be used for all segments until redefined
# Input relative to the input-dir command line argument.
# If not given, use the raw input-dir argument as a filename.
- input: cr-2021may-day1-obs.mov

# A basic example
# Output is relative to the output-dir command line argument.
- output: day1-welcome.mp4
  time:
    - start: 12:20
    - end: 31:14
    # This older format for a segment still works but is not
    # recommended:
    #- 12:20, 31:14

# Git-intro day 1
- output: day1-git-intro-1.mp4    # Output filename
  title: YouTube Video Title
  description: >
    Description of the video.
  time:
    # These pairs are times to *include*
    - start: 31:14
    - end: 38:13
    - start: 41:28
    - end: 1:04:45

# A sample including table of contents entries.
# You need to map times from the raw file, to the output file, in
# order to make a clickable YouTube table of contents.
# They are times in the
# original video, and they are converted to the equivalent times in
# the processed videos. They must be within the ranges above (and
# you get a unhandled error if they aren't):
#   segment_start <= toc_time < segment_end.
# These can be interspersed with the segment definitions.
# Example:
- output: day2-git-intro-2.mp4
  time:
    - start: 31:14
    # TOC entry:
    - 31:14: Overview of the day
    - 33:25: Motivation to version control
    - end: 38:13
    - start: 41:28
    - 41:28, Basics of version control
    - 48:35: "Exercise: record changes"   # has a ':', so must be quoted
    - end: 1:04:45
    #- 1:18:22: This will fail

This syntax is used to cover a segment of the video:
- output: day3-has-audience-visible.mp4
  time:
  - start: 00:00
  # Cover an area.  begin/end are clear.  w and h are width and
  # height.  x and y are offset from the top-left corner
  - cover: {begin: "1:15:29", end: "1:51:34", w: 840, h: 300, x: 360}
  - end: 5:00


```

Alongside the `.mp4` output file, a `.mp4.info.txt` file is created
with these contents.  This is designed for easy copying and pasting
into hosting sites:

```
Title of Video

Video description.

01:53 Table of contents entry 1
15:45 Table of contents entry 2
...


Workshop description.
```


### Multiple inputs

Multiple inputs in one segment might be useful when you are attaching
an introduction to the main video.  Note that things might go wrong if
the video sizes and codecs do not align perfectly.  (TODO: does this
work as expected?)

```yaml
- output: output.mp4
  time:
    - input: intro.mkv
    - [00:00, 99:00]
	- input: main.mkv
    - [0:00, 99:00]
	- input: outro.mkv
	- [0:00, 99:00]

```




## See also

* https://trac.ffmpeg.org/wiki/Concatenate
* https://stackoverflow.com/q/7333232
* Inspired by https://github.com/mvdoc/budapest-fmri-data/blob/master/scripts/preprocessing-stimulus/split_movie.sh



## Status / Contributing

Alpha, under development, basically a toy project for a single use
(but could easily become more).  In order to use this you probably
have to read some code / work around some bugs since it isn't well
tested yet.

Bug reports or improvements welcome, but it is kind of a mess now.
Test with ``pytest ffmpeg-editlist.py``, but note that main
functionality is not tested right now.
