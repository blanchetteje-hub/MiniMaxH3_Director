@echo off
cd /d H:\images\output\video

ffmpeg -y -f concat -safe 0 -i list.txt -c copy final.mp4

echo.
echo Stitching complete.