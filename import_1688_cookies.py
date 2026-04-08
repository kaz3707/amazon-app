"""
Playwrightのブラウザで1688にログインして、セッションを保存するスクリプト。
ChromeのCDPやCookie暗号化に依存しない方式。
"""
import sys
import subprocess
import time
from pathlib import Path

PROFILE_DIR = str(Path(__file__).parent / "data" / "1688_session")
Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def main():
    print("=" * 50)
    print("  1688 ログイン & セッション保存")
    print("=" * 50)
    print()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwrightをインストール中...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright

    print("ブラウザを起動中...")
    print()

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-setuid-sandbox",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 800},
        )

        # webdriver フラグを隠すステルス設定
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            if (!window.chrome) { window.chrome = { runtime: {} }; }
        """)

        page = context.new_page()

        # タオバオのログインページに直接アクセス（1688ポップアップより安定）
        print("ログインページを開いています...")
        page.goto("https://login.taobao.com/member/login.jhtml", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        print()
        print("=" * 50)
        print("  ブラウザでログインしてください")
        print("=" * 50)
        print()
        print("  ・タオバオ/1688のログイン画面が開いています")
        print("  ・ログインを完了してください")
        print("  ・ログイン後に右上にアカウント名が表示されたらOK")
        print()
        input(">> ログイン完了後、Enterを押して続行 >> ")
        time.sleep(2)

        print()
        print("✓ セッションを保存中...")
        context.close()

    print(f"✓ 保存完了: {PROFILE_DIR}")
    print()
    print("✓ 完了！次回からアプリで1688の検索が使えます。")
    print("  （次回以降はこのスクリプトを実行しなくてもログイン状態が維持されます）")
    input("\nEnterで終了...")


if __name__ == "__main__":
    main()
