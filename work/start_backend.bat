@echo off
rem 一键启动后端（默认 Mock，无需 key、无需联网）。
rem 如需真实 LLM，请先在本窗口手动设置环境变量，例如：
rem   set LLM_PROVIDER=deepseek
rem   set LLM_API_KEY=你的key
rem 密钥只经环境变量传入，切勿写进本文件或 .env 后提交。
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo [错误] 未找到 venv，请先按 README 的“安装”一节创建虚拟环境并安装依赖。
  pause
  exit /b 1
)
if not exist "data" mkdir data
echo 后端启动中：http://127.0.0.1:8000/ （管理页）  Ctrl+C 停止
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
