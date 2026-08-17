@echo off
rem Run from the folder containing this batch file so no drive-specific path
rem needs to be edited after copying it into ComfyUI's video output folder.
cd /d "%~dp0"

ffmpeg -y -f concat -safe 0 -i list.txt -c copy final.mp4

echo.
echo Stitching complete.
