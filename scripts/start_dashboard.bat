@echo off
rem 더블클릭으로 대시보드를 띄우고 브라우저를 연다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dashboard.ps1"
timeout /t 2 >nul
start "" "http://localhost:8501"
