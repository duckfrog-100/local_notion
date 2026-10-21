@echo off
setlocal
cd /d "%~dp0"
if not exist server_url.txt (
  echo [Local Notion] server_url.txt 파일이 없습니다.
  echo 관리자가 서버 주소를 설정해야 합니다. 예: http://192.168.0.10:8765
  pause
  exit /b 1
)
set /p TARGET=<server_url.txt
if "%TARGET%"=="" (
 echo 서버 주소가 비어 있습니다.
 pause
 exit /b 1
)
start "" "%TARGET%"
