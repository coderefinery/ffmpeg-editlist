# ffmpeg editlist utility

This utility takes a YAML definition of an edit list (segments to cut
out and re-assemble into a file), and does the re-assembling using the
ffmpeg command line utility.

This is currently an alpha-level utility: it works, but expect to need
code modifications to make it work for your case.  Documentation is
not good.


## Installation and dependencies.

This is a single-file script in Python, no installation is needed.

It depends on the `ffmpeg` command line utility and PyYAML (pip:
`pyyaml`).

## Usage

Create an edit list file (next section).  The general usage is:

```
ffmpeg-editlist.py editlist.yaml input-dir output-dir
```

Where `input-dir` is the search path for input files and `output-dir`
is the output path for files.

## Editlist definition

```yaml

# This input will be used for all segments until redefined
# Input relative to input-dir
- input: cr-2021may-day1-obs.mov

- output: day1-welcome.mp4
  time:
    - 12:20, 31:14

# Git-intro day 1
- output: day1-git-intro-1.mp4    # Output filename
  time:
    # These pairs are times to *include*
	- 31:14, 38:13
	- 41:28, 1:04:45
	- 1:18:22, 1:28:27

    # Thes are table of contents entries.  They are times in the
	# original video, and they are converted to the equivalent times in
	# the processed videos. They must be within the ranges above:
    #   segment_start <= toc_time < segment_end.
	# These can be interspersed with the segment definitions obev

    - 31:14: Overview of the day
    - 33:25: Motivation to version control
    #- 41:28, Real-life repository examples
    - 48:35: Basics of version control
    - 1:18:22: "Exercise: record changes"   # has a ':', so must be quoted


```

## Development

Bug reports or improvements welcome.  Test with ``pytest
ffmpeg-editlist.py``, but note that main functionality is not tested
right now.



## See also

* https://trac.ffmpeg.org/wiki/Concatenate
* https://stackoverflow.com/q/7333232
* Inspired by https://github.com/mvdoc/budapest-fmri-data/blob/master/scripts/preprocessing-stimulus/split_movie.sh


## Status

Under development, expected to need code browsing to use.
