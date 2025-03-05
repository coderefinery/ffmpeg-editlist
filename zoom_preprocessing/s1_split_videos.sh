#!/bin/bash
# This script runs on triton where the module "ffmpeg" is available. Alternatively, just make sure ffmpeg is visible from your PATH
module load ffmpeg

# For each video to process, find manually the starting time (parameter for -ss) and the length (paramter for -to)
# Here below an example that was splitting two long zoom recordings into 4 shorter videos.

ffmpeg  -ss 00:03:06 -i source_videos/1.mp4 -to 00:04:00 -c copy trimmed/1_1_episode1.mp4
ffmpeg  -ss 00:00:24 -i source_videos/2.mp4 -to 00:18:06 -c copy trimmed/2_1_episode2.mp4
ffmpeg  -ss 00:26:32 -i source_videos/2.mp4 -to 00:23:46 -c copy trimmed/2_2_episode2.mp4
ffmpeg  -ss 01:09:10 -i source_videos/2.mp4 -to 00:16:51 -c copy trimmed/2_3_episode2.mp4

