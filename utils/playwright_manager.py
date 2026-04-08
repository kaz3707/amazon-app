"""
Playwright同期APIの共通ラッパー。
テストモードではPlaywrightを使用しないため、インポートは実行時に遅延する。
"""
import random
import time
from contextlib import contextmanager
from pathlib import Path

# 1688ログインセッション保存先
_1688_PROFILE_DIR = str(Path(__file__).parent.parent / "data" / "1688_session")

# 一般的なデスクトップ解像度
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
]

# ボット検出を回避するための init スクリプト
# - navigator.webdriver を隠す
# - Chrome headless 固有のプロパティを補完
_STEALTH_SCRIPT = """
() => {
    // webdriver フラグを隠す
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // headless 判定に使われる plugins を補完
    if (navigator.plugins.length === 0) {
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin',     filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer',     filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client',         filename: 'internal-nacl-plugin' },
            ],
        });
    }

    // languages が空の場合に補完
    if (navigator.languages.length === 0) {
        Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja', 'en-US'] });
    }

    // Chrome オブジェクトが存在しない場合に補完（headless では undefined になることがある）
    if (!window.chrome) {
        window.chrome = { runtime: {} };
    }

    // permission API をブロック（headless では denied が返るため）
    const origQuery = window.navigator.permissions?.query;
    if (origQuery) {
        window.navigator.permissions.query = (params) =>
            params.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : origQuery.call(window.navigator.permissions, params);
    }
}
"""


def _get_sync_playwright():
    """Playwrightを遅延インポートする。テストモード時はインポートしない。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwrightがインストールされていません。\n"
            "setup.bat を実行するか、以下を実行してください:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )


def _random_viewport() -> dict:
    return random.choice(_VIEWPORTS)


def human_wait(min_sec: float = 1.0, max_sec: float = 3.0) -> None:
    """人間らしいランダム待機。スクレイピング処理の合間に呼ぶ。"""
    time.sleep(random.uniform(min_sec, max_sec))


def _apply_stealth(context) -> None:
    """コンテキストにステルス設定を適用する。"""
    context.add_init_script(_STEALTH_SCRIPT)


@contextmanager
def get_page(headless: bool = True, timeout_ms: int = 30000):
    """
    使い捨てのPlaywright Pageを返すコンテキストマネージャー。
    ボット検出回避のためのステルス設定を適用済み。
    """
    sync_playwright = _get_sync_playwright()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport=_random_viewport(),
        )
        _apply_stealth(context)
        context.set_default_timeout(timeout_ms)
        page = context.new_page()
        try:
            yield page
        finally:
            page.close()
            context.close()
            browser.close()


def _load_imported_cookies() -> list:
    """import_1688_cookies.py で保存したCookieを読み込む。"""
    cookie_file = Path(_1688_PROFILE_DIR) / "imported_cookies.json"
    if not cookie_file.exists():
        return []
    try:
        import json
        with open(cookie_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@contextmanager
def get_1688_page(headless: bool = True, timeout_ms: int = 60000):
    """
    1688ログインセッションを保持するPlaywright Pageを返すコンテキストマネージャー。
    セッションは data/1688_session/ に保存され、ブラウザ再起動後も維持される。
    初回はimport_1688_cookies.bat で手動ログインが必要。
    """
    sync_playwright = _get_sync_playwright()
    Path(_1688_PROFILE_DIR).mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=_1688_PROFILE_DIR,
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport=_random_viewport(),
        )
        # ChromeからインポートしたCookieがあれば注入
        imported = _load_imported_cookies()
        if imported:
            try:
                context.add_cookies(imported)
            except Exception:
                pass
        _apply_stealth(context)
        context.set_default_timeout(timeout_ms)
        page = context.new_page()
        try:
            yield page
        finally:
            page.close()
            context.close()


def has_1688_session() -> bool:
    """1688のセッションデータが保存済みかどうかを返す。"""
    base = Path(_1688_PROFILE_DIR) / "Default"
    # 新しいChromiumは Network/Cookies、古いバージョンは Cookies
    return (base / "Network" / "Cookies").exists() or (base / "Cookies").exists()


@contextmanager
def get_persistent_page(headless: bool = True, timeout_ms: int = 30000):
    """
    ログインセッションを維持するためのコンテキストマネージャー。
    """
    sync_playwright = _get_sync_playwright()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            viewport=_random_viewport(),
        )
        _apply_stealth(context)
        context.set_default_timeout(timeout_ms)
        page = context.new_page()
        try:
            yield page
        finally:
            page.close()
            context.close()
            browser.close()
