@echo off
rem Import new bank files, reload the reference workbook, export for Power BI, then show status.
rem Stops at the first step that fails.
setlocal

call "%~dp0col.bat" update
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo STOPPED: the update failed ^(see the message above^).
)

rem Keep the window open when started by double-clicking.
echo %cmdcmdline% | find /i "%~0" >nul
if not errorlevel 1 pause
exit /b %RC%
