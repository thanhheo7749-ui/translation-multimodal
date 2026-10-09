@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\publish_project.ps1" %*
set "publish_exit=%ERRORLEVEL%"
if not "%publish_exit%"=="0" echo Publishing failed. See the error above; the original project is preserved.
exit /b %publish_exit%
