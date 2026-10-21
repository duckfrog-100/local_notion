@echo off
setlocal
cd /d "%~dp0"
if not defined LOCAL_NOTION_DATA_DIR set "LOCAL_NOTION_DATA_DIR=%~dp0runtime_data"
python app.py
pause
