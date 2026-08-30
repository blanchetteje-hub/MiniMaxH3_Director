@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Run from the folder containing this batch file so no drive-specific path
rem needs to be edited after copying it into ComfyUI's video output folder.
cd /d "%~dp0"

set "SOURCE_LIST=list.txt"
set "WORK_DIR=%CD%\.stitch_work_%RANDOM%_%RANDOM%"
set "TRIMMED_LIST=%WORK_DIR%\list.txt"
set "EXIT_CODE=0"

if not exist "%SOURCE_LIST%" (
    echo ERROR: %SOURCE_LIST% was not found.
    exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo ERROR: ffmpeg was not found on PATH.
    exit /b 1
)

mkdir "%WORK_DIR%"
if errorlevel 1 (
    echo ERROR: Could not create the temporary stitching folder.
    exit /b 1
)

type nul > "%TRIMMED_LIST%"
set /a SEGMENT_NUMBER=0

for /f "usebackq tokens=1,*" %%A in ("%SOURCE_LIST%") do (
    if /i "%%A"=="file" (
        set /a SEGMENT_NUMBER+=1
        set "SOURCE_VIDEO=%%B"

        rem FFmpeg concat lists normally wrap each path in single quotes.
        if "!SOURCE_VIDEO:~0,1!"=="'" set "SOURCE_VIDEO=!SOURCE_VIDEO:~1,-1!"
        for %%F in ("!SOURCE_VIDEO!") do set "SOURCE_VIDEO=%%~fF"

        if !SEGMENT_NUMBER! equ 1 (
            set "STITCH_VIDEO=!SOURCE_VIDEO!"
        ) else (
            set "STITCH_VIDEO=%WORK_DIR%\trimmed_segment_!SEGMENT_NUMBER!.mp4"
            echo Trimming the first 2 frames from Segment !SEGMENT_NUMBER!...
            ffmpeg -y -i "!SOURCE_VIDEO!" -ss 0.083333 -c:v libx264 -preset medium -crf 18 -c:a aac -b:a 192k "!STITCH_VIDEO!"
            if errorlevel 1 (
                echo ERROR: Could not trim Segment !SEGMENT_NUMBER!.
                set "EXIT_CODE=1"
                goto :cleanup
            )
        )

        set "FFMPEG_PATH=!STITCH_VIDEO:\=/!"
        >> "%TRIMMED_LIST%" echo file '!FFMPEG_PATH!'
    )
)

if !SEGMENT_NUMBER! equ 0 (
    echo ERROR: %SOURCE_LIST% contains no video entries.
    set "EXIT_CODE=1"
    goto :cleanup
)

echo Joining !SEGMENT_NUMBER! segments...
ffmpeg -y -f concat -safe 0 -i "%TRIMMED_LIST%" -c copy final.mp4
if errorlevel 1 (
    echo ERROR: FFmpeg could not create final.mp4.
    set "EXIT_CODE=1"
    goto :cleanup
)

:cleanup
rem This removes the temporary list and every trimmed video created above.
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Stitching complete: final.mp4
) else (
    echo Stitching failed. Temporary trimmed videos were deleted.
)

endlocal & exit /b %EXIT_CODE%
