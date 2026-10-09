@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Khong tim thay Python trong .venv.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -u "diagnose_network.py"
echo.
echo Gui ket qua chan doan hoac chup cua so nay. Khong can gui API key.
pause
endlocal
