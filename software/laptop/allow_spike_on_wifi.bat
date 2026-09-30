@echo off
rem ---------------------------------------------------------------------------
rem  Let the phone app (and the robot) reach Spike's brain over Wi-Fi.
rem
rem  Adds ONE Windows Firewall rule, named "Spike brain":
rem    inbound, TCP port 8765 (the brain's port), PRIVATE networks only
rem    (your home Wi-Fi). Public networks (cafes, airports) stay closed.
rem  Windows asks for administrator permission once (the rule is system-wide).
rem  Running it again replaces the rule instead of adding a second one.
rem
rem  Your home Wi-Fi must be set to Private in Windows:
rem    Settings > Network and internet > Wi-Fi > your network > Private network
rem  Undo: remove_spike_from_wifi.bat
rem ---------------------------------------------------------------------------
setlocal
set "PORT=8765"
set "RULE=Spike brain"

rem --- ask for administrator rights (the UAC prompt), then run this file again
net session >nul 2>&1
if errorlevel 1 (
  echo Asking Windows for permission to add the firewall rule...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="%RULE%" >nul 2>&1
netsh advfirewall firewall add rule name="%RULE%" dir=in action=allow protocol=TCP localport=%PORT% profile=private description="Spike's laptop brain: the phone app and the robot on your home Wi-Fi (software\laptop\allow_spike_on_wifi.bat)"
if errorlevel 1 (
  echo.
  echo The rule could not be added.
  pause
  exit /b 1
)
echo.
echo Done: "%RULE%" lets devices on your PRIVATE Wi-Fi reach port %PORT%.
echo.
echo Your networks right now (Spike needs yours to say Private):
powershell -NoProfile -Command "Get-NetConnectionProfile | ForEach-Object { '  ' + $_.Name + ' (' + $_.InterfaceAlias + '): ' + $_.NetworkCategory }"
echo.
pause
