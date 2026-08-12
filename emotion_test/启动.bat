@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo emotion_test 启动中…
echo 请先用「联调启动.bat」拉起 Server Center / Local Agent。
echo.
python app.py
if errorlevel 1 (
  echo.
  echo 若提示找不到 python，请改用 py -3 app.py
  pause
)
