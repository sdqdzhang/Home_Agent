@echo off
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe test\test_llm_config_service.py
) else if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe test\test_llm_config_service.py
) else (
    python test\test_llm_config_service.py
)
