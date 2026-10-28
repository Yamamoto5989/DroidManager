@echo off
rem DroidManager launcher for Windows. Requires Python (python.org) and scrcpy for Windows.
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw "%~dp0droidmanager.py"
) else (
  start "" pythonw "%~dp0droidmanager.py"
)
