@echo off
title CivicAI - Reset Demo Data
cd /d "%~dp0"
echo ============================================================
echo   CivicAI - RESET DEMO DATA
echo ============================================================
echo.
echo  Ye purana database (civicai.db) delete karega aur
echo  fresh demo accounts + sample complaints bana dega.
echo  Aapki nayi banayi hui complaints / accounts bhi hat jayenge.
echo.
echo  Rokna hai to abhi is window ko band kar do.
echo  Aage badhne ke liye koi bhi key dabao...
pause >nul

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed.
  echo  Install Python 3.10+ from https://www.python.org/downloads/
  echo  IMPORTANT: tick "Add Python to PATH" during installation.
  pause
  exit /b
)

if exist civicai.db (
  del /f /q civicai.db
  if exist civicai.db (
    echo.
    echo  [ERROR] civicai.db delete nahi ho paayi.
    echo  Pehle chalta hua CivicAI server band karo ^(CTRL + C^), phir dobara try karo.
    pause
    exit /b
  )
  echo  [OK] Purana database delete ho gaya.
) else (
  echo  [OK] Koi purana database nahi mila, fresh banega.
)

echo.
echo  Installing required libraries ^(first time only, needs internet^)...
python -m pip install -q -r requirements.txt

echo.
echo ============================================================
echo   CivicAI - Starting on http://127.0.0.1:5050
echo ============================================================
echo.
set PORT=5050
python app.py
pause