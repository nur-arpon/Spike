@echo off
rem ---------------------------------------------------------------------------
rem  Spike's laptop brain. Double-click to start him.
rem  It opens the face simulator, already connected. Close this window to stop.
rem  Extra options can follow, e.g.  run_spike.bat --no-camera   or   --persona spicy
rem  The face is opened at ws://127.0.0.1:<port> (never "localhost"). If port 8765
rem  is taken by another program, the brain picks the next free port by itself.
rem ---------------------------------------------------------------------------
title Spike's brain
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Spike's Python setup is missing: software\laptop\.venv
  echo Ask for it to be installed again.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m spike_brain --open %*
if errorlevel 1 (
  echo.
  echo Spike stopped because of the problem shown above.
  pause
)
