@echo off
REM ============================================================
REM run_push_github.bat - Executa push_github.py para GitHub Pages
REM ============================================================
REM Chamado pelo Task Scheduler (Windows)
REM Usa o python do venv do Hermes (AppData/Local/hermes/hermes-agent/venv)
REM ============================================================

set PYTHON_EXE=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe
set PROJECT_DIR=%~dp0\..

if not exist "%PYTHON_EXE%" (
    echo ERRO: Python do Hermes nao encontrado em %PYTHON_EXE%
    exit /b 1
)

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" "scripts/push_github.py"

if errorlevel 1 (
    echo ERRO: Push falhou (exit code %errorlevel%)
    exit /b %errorlevel%
)

echo OK - Push concluido
exit /b 0