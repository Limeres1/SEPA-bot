@echo off
setlocal

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
cd /d "%PROJECT_DIR%" || exit /b 1

set "DB_MODE=sqlite"
set "DB_PATH=%PROJECT_DIR%\data\sepa.db"
set "RUN_TIMEZONE=America/Argentina/Buenos_Aires"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo No se encontro el entorno virtual en "%PYTHON_EXE%".
    echo Crea .venv e instala las dependencias con los pasos del README.
    exit /b 1
)

"%PYTHON_EXE%" -m sepa_bot.main --once
exit /b %ERRORLEVEL%
