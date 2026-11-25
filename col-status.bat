@echo off
rem Runs: admin_cli status   (extra arguments are passed through)
call "%~dp0col.bat" status %*
set "RC=%errorlevel%"
rem Keep the window open when started by double-clicking.
echo %cmdcmdline% | find /i "%~0" >nul
if not errorlevel 1 pause
exit /b %RC%
