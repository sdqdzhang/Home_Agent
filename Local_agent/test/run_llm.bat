@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe test\test_llm_gui.py
) else if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe test\test_llm_gui.py
) else (
    python test\test_llm_gui.py
)
