@echo off
set ROOT_DIR=%~dp0
set ROOT_DIR=%ROOT_DIR:~0,-1%

echo Installing backend dependencies...
call cmd /c "cd /d %ROOT_DIR%\backend && python -m pip install -r requirements.txt"
if errorlevel 1 exit /b %errorlevel%

echo Installing frontend dependencies...
call cmd /c "cd /d %ROOT_DIR%\frontend && npm install"
if errorlevel 1 exit /b %errorlevel%

start "ERP FastAPI" cmd /k "cd /d %ROOT_DIR%\backend && python main.py"
start "ERP Frontend" cmd /k "cd /d %ROOT_DIR%\frontend && npm run dev"

echo FastAPI backend and frontend dev servers are starting...
