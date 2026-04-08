"""
1688ログインセットアップスクリプト。

初回および セッション期限切れ時に実行する。
ブラウザが画面付きで開くので、手動でSMS認証→ログインを完了してからEnterを押す。
セッションは data/1688_session/ に保存され、次回から自動でログイン状態になる。
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

PROFILE_DIR = str(Path(__file__).parent / "data" / "1688_session")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwrightがインストールされていません。setup.bat を先に実行してください。")
        input("\nEnterで終了...")
        return

    Path(PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  1688 ログインセットアップ")
    print("=" * 60)
    print()
    print("ブラウザが開きます。以下の手順でログインしてください：")
    print()
    print("  1. 画面右上「登录」をクリック")
    print("  2. 手机号（携帯番号）を入力")
    print("  3. SMSで届いた認証コードを入力")
    print("  4. ログイン完了を確認")
    print("  5. このウィンドウに戻って Enterを押す")
    print()
    print("※ ログインセッションは通常2〜4週間持続します。")
    print("   期限切れ時はこのスクリプトを再実行してください。")
    print()

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--start-maximized",
            ],
            user_agent=USER_AGENT,
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            no_viewport=True,
        )
        page = context.new_page()
        page.goto("https://www.1688.com/", wait_until="domcontentloaded")

        input("1688へのログイン完了後、Enterを押してください... ")

        # ログイン状態を確認
        current_url = page.url
        if "login" in current_url or "passport" in current_url:
            print()
            print("⚠ まだログインページです。")
            print("  ログインを完了してから、もう一度 Enterを押してください。")
            input()

        print()
        print("✓ セッションを保存しました。")
        print("  次回から画像検索が自動で動作します。")

        context.close()

    print()
    input("Enterで終了...")


if __name__ == "__main__":
    main()
