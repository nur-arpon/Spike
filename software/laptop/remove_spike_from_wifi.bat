@echo off
rem ---------------------------------------------------------------------------
rem  Undo allow_spike_on_wifi.bat: removes the Windows Firewall rule named
rem  "Spike brain". Nothing else is touched. Asks for administrator
rem  permission once.
rem ---------------------------------------------------------------------------
setlocal
set "RULE=Spike brain"
net session >nul 2>&1
if errorlevel 1 (
  echo Asking Windows for permission to remove the firewall rule...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
netsh advfirewall firewall delete rule name="%RULE%"
if errorlevel 1 (
  echo There was no rule called "%RULE%". Nothing to remove.
) else (
  echo Done: the "%RULE%" firewall rule is removed.
)
pause
