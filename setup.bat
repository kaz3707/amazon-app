@echo off
chcp 65001 >nul
echo ============================================
echo   利益計算アプリ セットアップ
echo ============================================
echo.

:: Python確認
python --version >nul 2>&1
if errorlevel 1 (
    echo [エラー] Pythonがインストールされていません。
    echo https://www.python.org/ からPythonをインストールしてください。
    pause
    exit /b 1
)

:: venv作成
if not exist "venv" (
    echo [1/4] 仮想環境を作成中...
    python -m venv venv
)

:: 依存パッケージインストール
echo [2/4] パッケージをインストール中...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet

:: Playwright ブラウザインストール
echo [3/4] Playwrightブラウザをインストール中...
python -m playwright install chromium

:: config.ini作成
if not exist "config.ini" (
    echo [4/4] 設定ファイルを作成中...
    copy config.ini.example config.ini
    echo.
    echo [重要] config.ini を開いてセールモンスターの
    echo        ID・パスワードを設定してください。
) else (
    echo [4/4] config.ini は既に存在します。
)

echo.
echo ============================================
echo   セットアップ完了！
echo   start.bat を実行してアプリを起動してください
echo ============================================
pause
