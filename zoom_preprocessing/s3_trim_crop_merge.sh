#!/bin/bash
# Episode 1
# x y w h
# screen: 6 176 2230 1250 
# camera: 2240 710 320 164
# crop out the screen
ffmpeg -i trimmed/1_1_episode1.mp4 -filter:v "crop=2230:1250:6:176" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/1_1_episode1_screen.mp4

# crop out the camera
ffmpeg -i trimmed/1_1_episode1.mp4 -filter:v "crop=320:164:2240:710" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/1_1_episode1_camera.mp4

# merge screen and camera
ffmpeg -i cropped/1_1_episode1_screen.mp4 -i cropped/1_1_episode1_camera.mp4 -filter_complex "[0:v][1:v] overlay=W-w:0" -c:v libx264 -crf 18 -preset fast -c:a copy final/episode1.mp4

# Episode2_1
# x y w h
# 4 182 1912 1074
# we don't have camera for this episode :(
ffmpeg -i trimmed/2_1_episode2.mp4 -filter:v "crop=1912:1074:4:182" -c:v libx264 -crf 18 -preset fast -c:a copy final/2_1_episode2_screen.mp4

# Episode2_2
# x y w h
# screen: 4 182 1912 1074 
# camera: 1920 90 320 164
# crop out the screen
ffmpeg -i trimmed/2_2_episode2.mp4 -filter:v "crop=1912:1074:4:182" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/2_2_episode2_screen.mp4

# crop out the camera
ffmpeg -i trimmed/2_2_episode2.mp4 -filter:v "crop=320:164:1920:90" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/2_2_episode2_camera.mp4

# merge screen and camera
ffmpeg -i cropped/2_2_episode2_screen.mp4 -i cropped/2_2_episode2_camera.mp4 -filter_complex "[0:v][1:v] overlay=W-w:0" -c:v libx264 -crf 18 -preset fast -c:a copy final/episode2.mp4


# Episode2_3
# x y w h
# screen: 4 182 1912 1074 
# camera 1920 90 320 164

# crop out the screen
ffmpeg -i trimmed/2_3_episode2.mp4 -filter:v "crop=1912:1074:4:182" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/2_3_episode2_screen.mp4

# crop out the camera
ffmpeg -i trimmed/2_3_episode2.mp4 -filter:v "crop=320:164:1920:90" -c:v libx264 -crf 18 -preset fast -c:a copy cropped/2_3_episode2_camera.mp4

# merge screen and camera
ffmpeg -i cropped/2_3_episode2_screen.mp4 -i cropped/2_3_episode2_camera.mp4 -filter_complex "[0:v][1:v] overlay=W-w:0" -c:v libx264 -crf 18 -preset fast -c:a copy final/episode2.mp4

