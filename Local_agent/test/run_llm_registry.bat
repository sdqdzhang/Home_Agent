@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe test\test_llm_registry.py
) else if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe test\test_llm_registry.py
) else (
    python test\test_llm_registry.py
)
pause
