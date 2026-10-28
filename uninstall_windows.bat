@echo off
rem DroidManager uninstaller for Windows (double-click)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_windows.ps1"
echo.
pause
