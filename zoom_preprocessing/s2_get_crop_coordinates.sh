#!/bin/bash

# This step is needed to identify the coordinates of the screen-share and of the "webcam" of the speaker. It basically saves pngs for one frame for each video and then manually one has to identify the coordinates for step3

for n in $(find trimmed -name "*.mp4");do
	bn=$(basename $n)
	echo 'ffmpeg -i '$n' -vf "select=eq(n\,5000)" -vframes 1 frames/'$bn'.png'
	ffmpeg -i $n -vf "select=eq(n\,5000)" -vframes 1 frames/$bn.png
done

