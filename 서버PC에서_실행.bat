@echo off
setlocal
cd /d "%~dp0"
if not defined LOCAL_NOTION_PASSWORD (
  echo [주의] 다중 사용자 서버를 실행하려면 LOCAL_NOTION_PASSWORD 환경 변수를 설정하세요.
  echo 회사 IT 담당자의 보안 승인과 HTTPS 구성이 필요합니다.
  pause
  exit /b 1
)
set "LOCAL_NOTION_HOST=0.0.0.0"
python shared_server.py
pause
