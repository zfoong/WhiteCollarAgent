@echo off
echo Running Google Token Refresh Test...
echo.
cd /d "%~dp0"
python test_token_refresh.py
pause
