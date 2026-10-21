@echo off
setlocal
cd /d "%~dp0"
REM 각 직원 PC에서만 실행되는 로컬 웹앱. 모든 데이터는 공통 폴더에 저장.
if not defined LOCAL_NOTION_DATA_DIR set "LOCAL_NOTION_DATA_DIR=%~dp0shared_data"
where python >nul 2>&1
if errorlevel 1 (
 echo Python 3.10 이상이 필요합니다. 설치 정책을 확인하세요.
 pause
 exit /b 1
)
start "" "http://127.0.0.1:8765"
python local_app.py
pause
