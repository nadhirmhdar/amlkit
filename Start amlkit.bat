@echo off
REM ---------------------------------------------------------------------
REM  amlkit launcher
REM
REM  Starts the local server and opens it in your default browser.
REM  The server runs in its own console window: CLOSE THAT WINDOW TO STOP.
REM
REM  Right-click this file > Send to > Desktop (create shortcut) to get a
REM  desktop icon. Nothing is installed and nothing runs at startup.
REM ---------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Python environment not found in this folder.
  echo   Expected: %CD%\.venv\Scripts\python.exe
  echo.
  echo   Set it up once with:
  echo       python -m venv .venv
  echo       .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo Starting amlkit...

REM Server gets its own titled window so it is obvious what is running and
REM how to stop it. Closing that window shuts the server down.
start "amlkit server - CLOSE THIS WINDOW TO STOP" .venv\Scripts\python.exe scripts\serve.py

REM Give uvicorn a moment to bind before the browser asks for the page,
REM otherwise the first load fails with a connection error.
timeout /t 4 /nobreak >nul

start "" http://127.0.0.1:8000

exit /b 0
