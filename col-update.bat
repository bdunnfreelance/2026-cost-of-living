@echo off
rem Import new bank files, reload the reference workbook, export for Power BI, then show status.
rem Stops at the first step that fails.
setlocal
set "RC=0"
call "%~dp0col.bat" import
if errorlevel 1 goto failed
call "%~dp0col.bat" load-mappings
if errorlevel 1 goto failed
call "%~dp0col.bat" export-actuals
if errorlevel 1 goto failed
call "%~dp0col.bat" status
goto done
:failed
set "RC=1"
echo.
echo STOPPED: a step failed (see the message above). The later steps were not run.
:done
rem Keep the window open when started by double-clicking.
echo %cmdcmdline% | find /i "%~0" >nul
if not errorlevel 1 pause
exit /b %RC%