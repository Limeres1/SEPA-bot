@echo off
cd /d "%~dp0\.."

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m sepa_bot.main --server
    exit /b %ERRORLEVEL%
)

python -m sepa_bot.main --server
