@echo off
title CivicAI - AI Complaint Management System
cd /d "%~dp0"
echo ============================================================
echo   CivicAI - AI-Driven Complaint Management System
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed.
  echo  Install Python 3.10+ from https://www.python.org/downloads/
  echo  IMPORTANT: tick "Add Python to PATH" during installation.
  pause
  exit /b
)
echo.
echo  [1/2] Installing required libraries (first time only, needs internet)...
python -m pip install -q -r requirements.txt
echo  [2/2] Starting the app... your browser will open automatically.
echo.
python app.py
pause
