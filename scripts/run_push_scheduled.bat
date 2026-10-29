@echo off
REM ============================================================
REM run_push_scheduled.bat - Atualiza dashboard e publica no GitHub Pages
REM Chamado pelo Windows Task Scheduler (tarefa: Benchmark-Geral-Pages-Diario)
REM push_github.py internamente: run_consolidated.py --use-cache -> pytest gate ->
REM commit main (se houver mudanca) -> push origin main + gh-pages (index.html)
REM ============================================================
setlocal ENABLEEXTENSIONS

set PROJECT_DIR=%~dp0..
set LOG_DIR=%PROJECT_DIR%\cron\output
set LOG_FILE=%LOG_DIR%\push_scheduled.log

if not exist "%LOG_DIR%\" mkdir "%LOG_DIR%"

echo [%DATE% %TIME%] Iniciando atualizacao do benchmark-geral >> "%LOG_FILE%" 2>&1

cd /d "%PROJECT_DIR%"

REM push_github.py reconstrói o dashboard (cache local) e publica main + gh-pages
py scripts/push_github.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] ERRO na atualizacao do dashboard (ver %LOG_FILE%) >> "%LOG_FILE%" 2>&1
    exit /b 1
)

echo [%DATE% %TIME%] OK - Dashboard atualizado e publicado no GitHub Pages >> "%LOG_FILE%" 2>&1
exit /b 0
