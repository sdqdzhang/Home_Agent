@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)
echo [Storage GUI] 日志与记录清理工具
python test\test_storage_gui.py