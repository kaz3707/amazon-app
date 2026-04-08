"""
セールモンスター費用取得サービス。
ログインして倉庫保管費・送料を取得する。
広告費は販売価格の20%（固定）。
"""
import re
import time
from utils.playwright_manager import get_persistent_page
from config.settings import SaleMonsterConfig, AppConfig


def get_sale_monster_costs(product_info: dict = None) -> dict:
    """
    セールモンスターにログインして費用情報を取得する。

    Args:
        product_info: 商品情報（任意。商品固有の費用を取得する場合）

    Returns:
        {
            "ad_rate": 0.20,
            "shipping_fee": float,      # 送料/個（円）
            "storage_fee_monthly": float, # 月額倉庫保管費（円）
            "other_fees": dict,
            "login_success": bool,
        }
    """
    if AppConfig.TEST_MODE:
        return {
            "ad_rate": 0.20,
            "shipping_fee": 650.0,
            "storage_fee_monthly": 120.0,
            "other_fees": {},
            "login_success": True,
            "note": "テストモード（ダミーデータ）",
        }

    cfg = SaleMonsterConfig

    if not cfg.login_id or not cfg.password:
        return {
            "ad_rate": 0.20,
            "shipping_fee": 0.0,
            "storage_fee_monthly": 0.0,
            "other_fees": {},
            "login_success": False,
            "error": "config.iniにセールモンスターのIDとパスワードが設定されていません",
        }

    try:
        return _login_and_fetch(cfg.login_id, cfg.password, cfg.login_url)
    except Exception as e:
        return {
            "ad_rate": 0.20,
            "shipping_fee": 0.0,
            "storage_fee_monthly": 0.0,
            "other_fees": {},
            "login_success": False,
            "error": str(e),
        }


def _login_and_fetch(login_id: str, password: str, login_url: str) -> dict:
    """セールモンスターにログインして費用情報を取得する。"""
    with get_persistent_page(headless=True, timeout_ms=45000) as page:
        # ログインページへアクセス
        page.goto(login_url, wait_until="domcontentloaded")
        time.sleep(2)

        # ログインフォームの入力
        # ID/メールアドレスフィールド
        id_selectors = [
            "input[name='email']",
            "input[name='username']",
            "input[name='login_id']",
            "input[type='email']",
            "input[type='text']",
        ]
        for sel in id_selectors:
            el = page.query_selector(sel)
            if el:
                el.fill(login_id)
                break

        # パスワードフィールド
        pass_selectors = [
            "input[name='password']",
            "input[type='password']",
        ]
        for sel in pass_selectors:
            el = page.query_selector(sel)
            if el:
                el.fill(password)
                break

        # ログインボタンをクリック
        btn_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('ログイン')",
            "button:has-text('Login')",
            ".login-btn",
        ]
        for sel in btn_selectors:
            el = page.query_selector(sel)
            if el:
                el.click()
                break

        time.sleep(3)

        # ログイン成功確認
        current_url = page.url
        if "login" in current_url.lower():
            raise Exception("ログインに失敗しました。IDとパスワードを確認してください。")

        # 費用情報ページへ移動
        costs = _extract_fee_info(page)
        costs["login_success"] = True
        costs["ad_rate"] = 0.20  # 広告費は固定20%

        return costs


def _extract_fee_info(page) -> dict:
    """ログイン後のページから費用情報を抽出する。"""
    # 料金・費用ページを探す
    fee_urls_to_try = [
        "/mypage/fee",
        "/fee",
        "/pricing",
        "/account/fee",
        "/seller/fee",
    ]
    base_url = "/".join(page.url.split("/")[:3])

    for path in fee_urls_to_try:
        try:
            page.goto(base_url + path, wait_until="domcontentloaded")
            time.sleep(1)
            body_text = page.inner_text("body")
            if "送料" in body_text or "保管" in body_text or "手数料" in body_text:
                return _parse_fee_page(body_text)
        except Exception:
            continue

    # 費用ページが見つからない場合はメインページから抽出
    body_text = page.inner_text("body")
    return _parse_fee_page(body_text)


def _parse_fee_page(text: str) -> dict:
    """費用ページのテキストから送料・保管費を抽出する。"""
    shipping_fee = _extract_amount(text, ["送料", "配送料", "配送費", "shipping"])
    storage_fee = _extract_amount(text, ["保管", "倉庫", "storage"])

    return {
        "shipping_fee": shipping_fee or 0.0,
        "storage_fee_monthly": storage_fee or 0.0,
        "other_fees": {},
    }


def _extract_amount(text: str, keywords: list) -> float | None:
    """テキストからキーワードに関連する金額を抽出する。"""
    for keyword in keywords:
        pattern = rf"{keyword}[^¥￥\d]*[¥￥]?\s*(\d+(?:,\d{{3}})*(?:\.\d+)?)"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    return None
