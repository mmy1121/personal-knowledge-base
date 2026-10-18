@echo off
rem Start backend. Default is Mock mode, no key needed.
rem For real LLM, set env vars in this window first, e.g.:
rem   set LLM_PROVIDER=deepseek
rem   set LLM_API_KEY=your_key
rem Never commit keys. Use env vars or a local .env only.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo [ERROR] venv not found. Follow README to create the virtual env first.
  pause
  exit /b 1
)
if not exist "data" mkdir data
echo Backend starting: http://127.0.0.1:8000/  (Ctrl+C to stop)
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
