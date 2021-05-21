# ffmpeg editlist utility

This utility takes a YAML definition of an edit list (segments to cut
out and re-assemble into a file), and does the re-assembling using the
ffmpeg command line utility.

This is currently an alpha-level utility: it works, but expect to need
code modifications to make it work for your case.  Documentation is
not good.

Features include:

* YAML edit list
* Select segments to include.  Segments are either copied raw or
  re-encoded (`--reencode`)
* Give Table of Contents times in the source video, mapped to times in
  the output video automatically.
* Cover certain areas of video (for example, when an audience member
  appears)
* Everything scripted and non-interactive.



## Installation and dependencies.

This is a single-file script in Python, no installation is needed.

It depends on the `ffmpeg` command line utility and PyYAML (pip:
`pyyaml`).  Version requirements of `ffmpeg` are currently unknown.



## Usage

Create an edit list file (next section).  The general usage is:

```
ffmpeg-editlist.py editlist.yaml input-dir [-o output-dir]
```

Where `input-dir` is the search path for input files and `output-dir`
(default `.`) is the output path for files.



## Editlist definition

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
