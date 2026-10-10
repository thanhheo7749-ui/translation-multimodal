@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="stop" goto stop
if "%~1"=="logs" goto logs
if "%~1"=="test" goto test
if "%~1"=="diagnose" goto diagnose
if "%~1"=="gemini" goto gemini
if not "%~1"=="" goto usage
docker compose up -d --build --wait
if errorlevel 1 goto failed
if not defined STUDIO_HTTP_PORT set "STUDIO_HTTP_PORT=8004"
echo Studio: http://localhost:%STUDIO_HTTP_PORT%/live
start "" "http://localhost:%STUDIO_HTTP_PORT%/live"
exit /b 0
:stop
docker compose down
exit /b %ERRORLEVEL%
:logs
docker compose logs -f --tail 80 studio
exit /b %ERRORLEVEL%
:diagnose
docker compose run --rm --no-deps studio python diagnose_network.py
exit /b %ERRORLEVEL%
:test
docker compose build
if errorlevel 1 goto failed
docker compose stop studio
if errorlevel 1 goto failed
docker compose run --rm --no-deps studio python experiments/compare_local_translation.py --download --providers both --gemini-direct --prompt-key
set "test_exit=%ERRORLEVEL%"
docker compose up -d --wait
if errorlevel 1 goto failed
exit /b %test_exit%
:gemini
powershell.exe -NoProfile -Command "$ErrorActionPreference='Stop'; $env:TRANSLATION_PROVIDER='gemini'; if(-not $env:GEMINI_API_KEY){$s=Read-Host 'Gemini API key (hidden)' -AsSecureString; $p=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); try{$env:GEMINI_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($p)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p)}}; if(-not $env:GEMINI_API_KEY){exit 1}; docker compose up -d --build --wait; exit $LASTEXITCODE"
if errorlevel 1 goto failed
if not defined STUDIO_HTTP_PORT set "STUDIO_HTTP_PORT=8004"
start "" "http://localhost:%STUDIO_HTTP_PORT%/live"
exit /b 0
:usage
echo Usage: studio.cmd [stop^|logs^|test^|diagnose^|gemini]
exit /b 1
:failed
echo Docker could not start the studio. Check Docker Desktop and run studio.cmd logs.
pause
exit /b 1
