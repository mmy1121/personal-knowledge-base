@echo off
rem Start floating box (start the backend first: start_backend.bat)
rem Default hotkey: Ctrl+Alt+K show/hide, Ctrl+Enter save, Esc hide
rem Backend address can be overridden by env var KB_API_BASE (default http://127.0.0.1:8000)
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo [ERROR] venv not found. Follow README to create the virtual env first.
  pause
  exit /b 1
)
venv\Scripts\python.exe -m floatbox.app
