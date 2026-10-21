@echo off
setlocal
cd /d "%~dp0"
if not defined LOCAL_NOTION_DATA_DIR set "LOCAL_NOTION_DATA_DIR=%~dp0shared_data"
where python >nul 2>&1
if errorlevel 1 (
 echo Python 3.10 이상이 필요합니다.
 pause
 exit /b 1
)
start "Local Notion Server" cmd /k "python local_app.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8765"
