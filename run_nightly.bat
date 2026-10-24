@echo off
rem Night shift: saved tech videos to notes, only while plugged in, stops at 07:00. Scheduled daily at 23:00.
cd /d C:\Users\DELL\night-shift
set PYTHONIOENCODING=utf-8
echo [%date% %time%] night shift start >> out\nightly.log
C:\Python314\python.exe videoshift.py --limit 30 --until 07:00 >> out\nightly.log 2>&1
echo [%date% %time%] night shift end, exit %ERRORLEVEL% >> out\nightly.log
