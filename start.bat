@echo off
chcp 65001 >nul
echo ============================================
echo   利益計算アプリ 起動中...
echo ============================================
echo.

if not exist "venv" (
    echo [エラー] 先に setup.bat を実行してください。
    pause
    exit /b 1
)

echo ブラウザで http://localhost:5000 を開いてください
echo 終了するには Ctrl+C を押してください
echo.
venv\Scripts\python.exe app.py
pause
