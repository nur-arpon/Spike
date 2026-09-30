@echo off
rem Start Spike's brain so the phone app can reach it over Wi-Fi and Tailscale
rem (not just the USB cable). Same as run_spike.bat --lan.
call "%~dp0run_spike.bat" --lan %*
