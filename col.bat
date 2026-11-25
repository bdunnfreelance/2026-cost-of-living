@echo off
rem Run any Cost of Living command without typing the Python path.
rem   col status
rem   col show --limit 20
rem   col            (no arguments: lists the available commands)
setlocal
set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo ERROR: the Python environment was not found at %PYEXE%
    echo Create it once, from this folder:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -e .
    exit /b 1
)
"%PYEXE%" -m cost_of_living.admin_cli %*
exit /b %errorlevel%
