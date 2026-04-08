"""
1688.com商品ページスクレイピング。
商品URLから仕入れ価格とSKU情報を取得し、スクリーンショットを保存する。
"""
import re
import uuid
from pathlib import Path
from utils.playwright_manager import get_page, human_wait
from services.exchange_rate import get_cny_to_jpy
from config.settings import AppConfig

SCREENSHOT_DIR = Path(__file__).parent.parent / "static" / "img" / "tmp"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _dummy_product_info(url: str) -> dict:
    """テストモード用ダミーデータ。"""
    return {
        "product_name": "【テスト】コラーゲンペプチド サプリメント 60粒",
        "price_cny": 18.50,
        "price_cny_max": 22.00,
        "price_jpy": 399,
        "price_jpy_max": 473,
        "exchange_rate": 21.56,
        "skus": [
            {"label": "60粒（1ヶ月分）", "selected": True},
            {"label": "120粒（2ヶ月分）", "selected": False},
        ],
        "screenshot_url": "",
        "moq": 100,
        "url": url,
    }


def fetch_product_info(url: str) -> dict:
    """
    1688商品URLから商品情報を取得する。

    Returns:
        {
            "product_name": str,
            "price_cny": float,          # 最低価格
            "price_cny_max": float,      # 最高価格（SKUによる）
            "price_jpy": float,          # 円換算（最低）
            "exchange_rate": float,
            "skus": [...],               # SKU情報リスト
            "screenshot_url": str,       # スクリーンショットの相対パス
            "moq": int,                  # 最小注文数
            "url": str,
        }
    """
    if AppConfig.TEST_MODE:
        return _dummy_product_info(url)

    session_id = uuid.uuid4().hex[:8]
    screenshot_filename = f"1688_{session_id}.png"
    screenshot_path = SCREENSHOT_DIR / screenshot_filename

    with get_page(headless=True, timeout_ms=45000) as page:
        page.goto(url, wait_until="domcontentloaded")
        human_wait(1.5, 3.0)

        # 人間らしいスクロール操作
        page.evaluate("window.scrollTo(0, 300)")
        human_wait(0.5, 1.2)
        page.evaluate("window.scrollTo(0, 700)")
        human_wait(0.5, 1.0)
        page.evaluate("window.scrollTo(0, 0)")
        human_wait(0.3, 0.8)

        # スクリーンショット保存
        page.screenshot(path=str(screenshot_path), full_page=False)

        product_name = _extract_product_name(page)
        prices = _extract_prices(page)
        skus = _extract_skus(page)
        moq = _extract_moq(page)

    exchange_rate = get_cny_to_jpy()
    price_cny = prices["min"] if prices["min"] else 0.0
    price_cny_max = prices["max"] if prices["max"] else price_cny

    return {
        "product_name": product_name,
        "price_cny": price_cny,
        "price_cny_max": price_cny_max,
        "price_jpy": round(price_cny * exchange_rate, 0),
        "price_jpy_max": round(price_cny_max * exchange_rate, 0),
        "exchange_rate": exchange_rate,
        "skus": skus,
        "screenshot_url": f"/static/img/tmp/{screenshot_filename}",
        "moq": moq,
        "url": url,
    }


def _extract_product_name(page) -> str:
    selectors = [
        ".d-title",
        "h1.title",
        "h1",
        "[class*='title']",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    return text[:200]
        except Exception:
            continue
    return "商品名取得失敗"


def _extract_prices(page) -> dict:
    """価格帯（最小・最大）を取得する。"""
    price_texts = []

    selectors = [
        ".price-original",
        ".price-content",
        "[class*='price']",
        ".offer-price",
        "span.price",
    ]
    for sel in selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements[:5]:
                text = el.inner_text().strip()
                if text:
                    price_texts.append(text)
        except Exception:
            continue

    # ページのテキストから価格を正規表現で抽出
    try:
        body = page.inner_text("body")
        # 中国語の元記号「¥」またはCNYの後の数値を探す
        found = re.findall(r"[¥￥]?\s*(\d+(?:\.\d+)?)", " ".join(price_texts) + " " + body[:2000])
        values = [float(v) for v in found if 1 <= float(v) <= 100000]
        if values:
            return {"min": min(values), "max": max(values)}
    except Exception:
        pass

    return {"min": 0.0, "max": 0.0}


def _extract_skus(page) -> list:
    """SKU（カラー・サイズ等）情報を取得する。"""
    skus = []
    try:
        # SKUボタンを探す
        sku_elements = page.query_selector_all("[class*='sku'] [class*='item'], [class*='spec'] li")
        for el in sku_elements[:20]:
            text = el.inner_text().strip()
            if text:
                skus.append({"label": text, "selected": False})
    except Exception:
        pass

    if not skus:
        skus = [{"label": "標準", "selected": True}]

    return skus


def _extract_moq(page) -> int:
    """最小注文数量を取得する。"""
    try:
        body = page.inner_text("body")
        m = re.search(r"起批[量数]?\D{0,5}(\d+)", body)
        if m:
            return int(m.group(1))
        m = re.search(r"minimum.*?(\d+)", body, re.IGNORECASE)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 1
