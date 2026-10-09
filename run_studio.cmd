@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Khong tim thay Python trong .venv. Vui long giu file nay trong thu muc du an.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -u "launch_studio.py" %*
if errorlevel 1 (
    echo.
    echo Khong khoi dong duoc. Xem thong bao loi o tren.
    pause
)
endlocal
