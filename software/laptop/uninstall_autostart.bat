@echo off
rem ---------------------------------------------------------------------------
rem  Stop Spike's brain from starting by itself when you sign in.
rem  Removes the "Spike brain" shortcut that install_autostart.bat put in your
rem  Startup folder. Nothing else is changed.
rem
rem  A brain that is already running keeps running until you sign out or
rem  restart. To stop it now: Task Manager > Details > the "pythonw.exe" whose
rem  command line has "spike_brain" > End task.
rem ---------------------------------------------------------------------------
setlocal
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Spike brain.lnk"
if exist "%LNK%" (
  del "%LNK%"
  if exist "%LNK%" (
    echo Could not remove "%LNK%".
    pause
    exit /b 1
  )
  echo Done. Spike's brain will no longer start by itself.
) else (
  echo Spike's brain was not set to start by itself. Nothing to do.
)
pause
