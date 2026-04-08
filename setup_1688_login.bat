@echo off
echo ========================================
echo   1688 Login Setup
echo ========================================
echo.

echo [1/2] Installing Playwright...
venv\Scripts\python.exe -m pip install playwright --quiet
venv\Scripts\python.exe -m playwright install chromium
echo.

echo [2/2] Starting login setup...
echo.
venv\Scripts\python.exe setup_1688_login.py
