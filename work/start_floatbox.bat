@echo off
rem 启动桌面悬浮框（需先启动后端：start_backend.bat）
rem 默认热键 Ctrl+Alt+K 呼出/隐藏，Ctrl+Enter 存入，Esc 隐藏
rem 后端地址可用环境变量 KB_API_BASE 覆盖（默认 http://127.0.0.1:8000）
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo [错误] 未找到 venv，请先按 README 的“安装”一节创建虚拟环境并安装依赖。
  pause
  exit /b 1
)
venv\Scripts\python.exe -m floatbox.app
