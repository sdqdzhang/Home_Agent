@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  py -3 -m venv .venv 2>nul
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo Failed to create .venv. Install Python 3 and retry.
  pause
  exit /b 1
)

echo Installing dependencies...
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "PIP_PROXY="
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check --proxy="" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if errorlevel 1 (
  echo pip install failed. Try: .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

echo Starting live2d_test...
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 (
  echo.
  echo If PySide6 / ffmpeg is missing, run: .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo Browser-only: .venv\Scripts\python.exe app.py --browser
  pause
)
