@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw accessviewer.py
) else (
    python accessviewer.py
    if errorlevel 1 (
        echo.
        echo Python is not installed. Get it from https://www.python.org/downloads/
        echo During install, tick "Add python.exe to PATH".
        pause
    )
)
