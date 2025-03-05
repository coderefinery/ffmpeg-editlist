# Preprocess zoom recordings

In this folder there are three scripts (3 steps) to preprocess zoom recordings where a single speaker is sharing their screen and webcam so that the recorded video file shows the screenshare+webcam on the same frame.

- Step1 trims the video (e.g. to remove introduction and post-talk discussions)
- Step2 extracts pngs from the video to identify the coordinates for the screenshare and the webcam view of the speaker.
- Step3 splits the zoom video into two sub-videos: the screenshare view and the webcam view, and then overlaps the webcam view on top of the screenshare on the top right corner. 

Note: if the speaker is sharing something important in the top right corner, the webcam view will hide it.
