@echo off
rem ---------------------------------------------------------------------------
rem  Start Spike's brain by itself every time you sign in to Windows.
rem
rem  What it does (only for your Windows user, no administrator needed):
rem    puts a shortcut called "Spike brain" in your Startup folder:
rem      %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
rem    The shortcut runs the brain hidden (no window) and listening on your
rem    Wi-Fi (--lan), so the phone app finds him by itself. The language model
rem    is NOT loaded at sign-in: Ollama starts when the app connects or you
rem    talk to him, and unloads after 15 quiet minutes (spike_settings.toml
rem    [llm] idle_unload).
rem    Log: software\laptop\data\logs\brain.log
rem
rem  Undo: uninstall_autostart.bat
rem  The laptop webcam is left off (--no-camera): Spike's own camera replaces it,
rem  and the webcam light would come on at every sign-in. Remove --no-camera
rem  below if you want the webcam.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "SPIKE_ARGS=-m spike_brain --lan --no-camera --log-file data\logs\brain.log"
set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
  echo Spike's Python setup is missing: "%PYW%"
  pause
  exit /b 1
)
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Spike brain.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);" ^
  "$s.TargetPath = $env:PYW; $s.Arguments = $env:SPIKE_ARGS;" ^
  "$s.WorkingDirectory = (Resolve-Path '.').Path; $s.WindowStyle = 7;" ^
  "$s.Description = 'Spike''s laptop brain (hidden, listening on Wi-Fi)'; $s.Save()"
if errorlevel 1 (
  echo Could not create the Startup shortcut.
  pause
  exit /b 1
)
echo.
echo Done. Spike's brain will start by itself the next time you sign in.
echo Shortcut: "%LNK%"
echo.
echo To start him right now without signing out, double-click the shortcut above,
echo or run:  "%PYW%" %SPIKE_ARGS%
echo Pair the phone once with pair_phone.bat (scan the QR in the app).
echo.
pause
