"""Tests for ffmpeg-editlist running.
"""
import io
import json
import pathlib
import subprocess
import tempfile

import pytest

import ffmpeg_editlist

@pytest.fixture
def tmpdir():
    """temporary directory fixture"""
    with tempfile.TemporaryDirectory(prefix='ffmpeg-editlist-tmp-') as name:
        yield pathlib.Path(name)

def video_info(fname):
    """Return JSON with video info."""
    cmd = ['ffprobe', '-v', 'quiet', '-show_streams', '-print_format', 'json', str(fname)]
    ret = subprocess.run(cmd, capture_output=True, check=True)
    out = ret.stdout
    data = json.loads(out)
    return data


TEST_OPTS = ['--crf=51', '--preset=veryfast']

class Runner():
    def __init__(self, tmpdir):
        self.tmpdir = tmpdir
    @property
    def input(self):
        return self._input
    @input.setter
    def input(self, value):
        open(self.tmpdir/'input.yaml', 'w').write(value)
        self._input = str(self.tmpdir/'input.yaml')
    @property
    def output(self):
        return str(self.tmpdir)
    def get_output(self, value):
        return str(self.tmpdir/value)
    def check_duration(self, name, duration):
        name2 = self.get_output(name)
        info = video_info(name2)
        assert round(ffmpeg_editlist.seconds(info['streams'][0]['tags']['DURATION'])) == duration


@pytest.fixture
def runner(tmpdir):
    runner_ = Runner(tmpdir)
    yield runner_


def test_5s(runner):
    yaml = """
- input: video-10s.mkv
  output: 5s.mkv
  editlist:
    - start: 00:00
    - stop: 00:05
"""
    runner.input = yaml
    ffmpeg_editlist.main([runner.input, 'sample/', '-o', runner.output, '--reencode', *TEST_OPTS])
    runner.check_duration('5s.mkv', 5)

def test_concatenate(runner):
    yaml = """
- input: video-10s.mkv
  output: 10s.mkv
  editlist:
    - start: 00:00
    - stop: 00:05
    - input: video-10s.mkv
    - start: 00:02
    - stop: 00:07
"""
    runner.input = yaml
    ffmpeg_editlist.main([runner.input, 'sample/', '-o', runner.output, '--reencode', *TEST_OPTS])
    runner.check_duration('10s.mkv', 10)

def test_cover(runner):
    yaml = """
- input: video-10s.mkv
  output: covered.mkv
  editlist:
    - start: 00:00
    - cover: {begin: "00:01", end: "00:03"}
    - cover: {begin: "00:03", end: "00:04"}
    - stop: 00:05
"""
    runner.input = yaml
    ffmpeg_editlist.main([runner.input, 'sample/', '-o', runner.output, '--reencode', *TEST_OPTS])
    # For manual testing:
    #print(runner.get_output('covered.mkv'))
    #input()
    runner.check_duration('covered.mkv', 5)


def test_png(runner):
    yaml="""
- output: png-to-video.mkv
  editlist:
    - input: sample/logo-840x1080.png
      duration: 5
    - -: test
    - input: sample/logo-840x1080.png
      duration: 5
    - -: test 2
    - input: sample/video-10s.mkv
    - start: 00:00
    - 00:04: test 3
    - end:   00:05
"""
    runner.input = yaml
    # reencode needed
    ffmpeg_editlist.main([runner.input, 'sample/', '-o', runner.output, '--reencode' , *TEST_OPTS])
    runner.check_duration('png-to-video.mkv', 15)

def test_srt(runner):
    yaml="""
- input: count10.mkv
- output: count10-out.mkv
  editlist:
    - start: 00:01
    - end:   00:05
    - start: 00:06
    - end:   00:08
"""
    runner.input = yaml
    # reencode needed
    ffmpeg_editlist.main([runner.input, 'sample/', '-o', runner.output, '--srt' , *TEST_OPTS])
    srt_file = runner.tmpdir/'count10-out.srt'
    srt_data = open(srt_file).read()
    assert 'one' not in srt_data
    assert '2,200\nthree' in srt_data
    assert '3,600' in srt_data
    assert '4,000\nfive' in srt_data
    assert '6,000\neight' in srt_data
