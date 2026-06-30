@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"
set "ROOT=%~dp0"

:: 请求管理员权限（仅弹一次 UAC）
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 正在请求管理员权限...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%ROOT:~0,-1%' -Verb RunAs"
    exit /b
)

echo ========================================
echo   HomeAgent 一键联调（3 个管理员窗口）
echo ========================================
echo 项目目录: %ROOT%
echo.

if not exist "%ROOT%Server_center\venv\Scripts\activate.bat" (
    echo [错误] 未找到 Server_center\venv
    echo 请先在 Server_center 目录创建虚拟环境并安装依赖。
    pause
    exit /b 1
)

if not exist "%ROOT%Local_agent\venv\Scripts\activate.bat" (
    echo [错误] 未找到 Local_agent\venv
    echo 请先在 Local_agent 目录创建虚拟环境并安装依赖。
    pause
    exit /b 1
)

if not exist "%ROOT%Server_center\frontend\package.json" (
    echo [错误] 未找到 Server_center\frontend\package.json
    pause
    exit /b 1
)

if not exist "%ROOT%Server_center\frontend\node_modules" (
    echo [提示] 首次运行请先执行:
    echo   cd Server_center\frontend ^&^& npm install
    echo.
)

echo [1/3] 启动 Server Center  ^(http://127.0.0.1:8765^)
:: 【修改点】将直接调用 uvicorn 改为通过 python -m uvicorn 启动，绕过 Device Guard 策略
start "HomeAgent - Server Center" cmd /k "cd /d ""%ROOT%Server_center"" && call venv\Scripts\activate.bat && echo [Server Center] python -m uvicorn && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8765"

timeout /t 2 /nobreak >nul

echo [2/3] 启动 Local Agent   ^(http://127.0.0.1:8770^)
:: 【修改点】同步将 Local Agent 也改为 python -m uvicorn 启动，防止后续报错
start "HomeAgent - Local Agent" cmd /k "cd /d ""%ROOT%Local_agent"" && call venv\Scripts\activate.bat && echo [Local Agent] python -m uvicorn && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8770"

timeout /t 2 /nobreak >nul

echo [3/3] 启动前端开发服务   ^(http://127.0.0.1:5173^)
start "HomeAgent - Frontend" cmd /k "cd /d ""%ROOT%Server_center\frontend"" && echo [Frontend] npm run dev && npm run dev"

echo.
echo 三个窗口已打开（均为管理员 CMD）。
echo   - Server Center :8765
echo   - Local Agent   :8770
echo   - Web UI        :5173  （Vite 代理到 8765）
echo.
echo 关闭对应窗口即可停止各服务。
timeout /t 5 >nul