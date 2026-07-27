@echo off
cd /d "%~dp0.."
call venv\Scripts\activate.bat 2>nul
call .venv\Scripts\activate.bat 2>nul
python test\test_processor_gui.py
pause
