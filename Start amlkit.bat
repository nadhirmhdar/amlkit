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

REM ---------------------------------------------------------------------
REM  SINGLE-OPERATOR MODE
REM
REM  Leave this commented out if two or more people can review alerts.
REM  Dismissing a sanctions or proliferation match then requires a second
REM  operator to confirm - that separation is the control.
REM
REM  If this firm has only ONE compliance officer, remove the REM below.
REM  Dismissals are then recorded with "no independent review" stamped on
REM  the alert and on the printed evidence pack. The gap becomes visible to
REM  a supervisor rather than silently absent - which is the honest
REM  treatment, and it stops a solo officer being unable to clear a queue.
REM ---------------------------------------------------------------------
REM set AMLKIT_SINGLE_OPERATOR_MODE=1

echo Starting amlkit...

REM Server gets its own titled window so it is obvious what is running and
REM how to stop it. Closing that window shuts the server down.
start "amlkit server - CLOSE THIS WINDOW TO STOP" .venv\Scripts\python.exe scripts\serve.py

REM Give uvicorn a moment to bind before the browser asks for the page,
REM otherwise the first load fails with a connection error.
timeout /t 4 /nobreak >nul

start "" http://127.0.0.1:8000

exit /b 0
