"""
Amazon.co.jp カテゴリ別販売手数料スクレイピング。
公開ページから手数料を取得してSQLiteにキャッシュする。
"""
import re
from utils.playwright_manager import get_page, human_wait
from utils.cache_manager import get_amazon_fees_from_cache, save_amazon_fees_to_cache
from config.settings import AppConfig

AMAZON_FEE_URL = "https://sell.amazon.co.jp/pricing/referral-fees"

# スクレイピング失敗時のフォールバック手数料（Amazon公式2024年版）
FALLBACK_FEES = [
    {"key": "electronics", "name": "家電", "fee_rate": 0.08, "min_fee": 30},
    {"key": "pc", "name": "パソコン・周辺機器", "fee_rate": 0.08, "min_fee": 30},
    {"key": "camera", "name": "カメラ", "fee_rate": 0.08, "min_fee": 30},
    {"key": "mobile", "name": "スマートフォン・携帯電話", "fee_rate": 0.08, "min_fee": 30},
    {"key": "books", "name": "本", "fee_rate": 0.15, "min_fee": None},
    {"key": "music", "name": "音楽", "fee_rate": 0.15, "min_fee": None},
    {"key": "video", "name": "DVD・ビデオ", "fee_rate": 0.15, "min_fee": None},
    {"key": "software", "name": "ソフトウェア", "fee_rate": 0.15, "min_fee": None},
    {"key": "video_games", "name": "TVゲーム", "fee_rate": 0.15, "min_fee": None},
    {"key": "clothing", "name": "服&ファッション小物", "fee_rate": 0.15, "min_fee": None},
    {"key": "shoes", "name": "シューズ&バッグ", "fee_rate": 0.15, "min_fee": None},
    {"key": "watches", "name": "時計", "fee_rate": 0.15, "min_fee": None},
    {"key": "jewelry", "name": "ジュエリー", "fee_rate": 0.20, "min_fee": None},
    {"key": "sports", "name": "スポーツ&アウトドア", "fee_rate": 0.10, "min_fee": None},
    {"key": "baby", "name": "ベビー&マタニティ", "fee_rate": 0.10, "min_fee": None},
    {"key": "toys", "name": "おもちゃ", "fee_rate": 0.10, "min_fee": None},
    {"key": "health", "name": "ヘルス&ビューティー", "fee_rate": 0.10, "min_fee": None},
    {"key": "beauty", "name": "コスメ・ヘルス・介護用品", "fee_rate": 0.10, "min_fee": None},
    {"key": "supplement", "name": "サプリメント・栄養補助食品", "fee_rate": 0.10, "min_fee": None},
    {"key": "food", "name": "食品&飲料", "fee_rate": 0.10, "min_fee": None},
    {"key": "pet", "name": "ペット用品", "fee_rate": 0.10, "min_fee": None},
    {"key": "home", "name": "ホーム&キッチン", "fee_rate": 0.10, "min_fee": None},
    {"key": "tools", "name": "DIY・工具・ガーデン", "fee_rate": 0.12, "min_fee": None},
    {"key": "auto", "name": "車&バイク", "fee_rate": 0.10, "min_fee": None},
    {"key": "office", "name": "文房具・オフィス用品", "fee_rate": 0.15, "min_fee": None},
    {"key": "stationery", "name": "楽器", "fee_rate": 0.15, "min_fee": None},
    {"key": "other", "name": "その他", "fee_rate": 0.15, "min_fee": 30},
]


def get_amazon_fees(force_refresh: bool = False) -> list[dict]:  # noqa: ARG001
    """
    Amazon手数料一覧を返す。キャッシュ優先、期限切れ時はスクレイピング。

    Returns:
        [{"key": str, "name": str, "fee_rate": float, "min_fee": float|None}, ...]
    """
    # テストモード または キャッシュ有効時はフォールバック値を直接返す
    if AppConfig.TEST_MODE:
        return FALLBACK_FEES

    if not force_refresh:
        cached = get_amazon_fees_from_cache()
        if cached:
            return cached

    try:
        fees = _scrape_amazon_fees()
        if fees:
            save_amazon_fees_to_cache(fees)
            return fees
    except Exception as e:
        print(f"Amazon手数料スクレイピング失敗: {e}")

    # スクレイピング失敗時はフォールバック値を使用・保存
    save_amazon_fees_to_cache(FALLBACK_FEES)
    return FALLBACK_FEES


def _scrape_amazon_fees() -> list[dict]:
    """Amazon公開ページから手数料をスクレイピングする。"""
    fees = []
    with get_page(headless=True, timeout_ms=30000) as page:
        page.goto(AMAZON_FEE_URL, wait_until="networkidle")
        human_wait(1.5, 3.0)

        # テーブル行を探す
        rows = page.query_selector_all("table tr, .fee-table tr, [class*='table'] tr")
        for row in rows:
            cells = row.query_selector_all("td, th")
            if len(cells) < 2:
                continue
            texts = [c.inner_text().strip() for c in cells]
            category_name = texts[0]
            fee_text = texts[1] if len(texts) > 1 else ""

            rate = _parse_rate(fee_text)
            if rate is None or not category_name or len(category_name) > 100:
                continue

            min_fee = _parse_min_fee(fee_text)
            key = _name_to_key(category_name)
            fees.append({
                "key": key,
                "name": category_name,
                "fee_rate": rate,
                "min_fee": min_fee,
            })

    return fees


def _parse_rate(text: str) -> float | None:
    """テキストから手数料率（小数）を抽出する。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if m:
        return float(m.group(1)) / 100
    return None


def _parse_min_fee(text: str) -> float | None:
    """テキストから最低手数料（円）を抽出する。"""
    m = re.search(r"最低[：:\s]*[¥￥]?\s*(\d+)", text)
    if m:
        return float(m.group(1))
    return None


def _name_to_key(name: str) -> str:
    """カテゴリ名からキーを生成する。"""
    import hashlib
    return hashlib.md5(name.encode()).hexdigest()[:8]
