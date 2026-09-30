@echo off
rem ---------------------------------------------------------------------------
rem  Shows the pairing QR for the Spike phone app (and opens it as a picture).
rem  In the app: Connect > Scan the pairing code.
rem  The brain must be listening on Wi-Fi: the autostart does that, or
rem  run_spike.bat --lan
rem ---------------------------------------------------------------------------
title Pair a phone with Spike
cd /d "%~dp0"
".venv\Scripts\python.exe" -m spike_brain --pair
pause
