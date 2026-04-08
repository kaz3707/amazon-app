"""
関税・消費税率取得サービス。
日本関税協会・税関公式サイトから関税率を取得する。
消費税は10%固定（輸入時の内税）。
"""
import re
import time
from utils.playwright_manager import get_page
from utils.cache_manager import get_customs_rate_from_cache, save_customs_rate_to_cache
from config.settings import AppConfig

CUSTOMS_SEARCH_URL = "https://www.customs.go.jp/tariff/"

# 主要商品カテゴリの関税率マスタ（フォールバック用）
CUSTOMS_MASTER = {
    # キー: (関税率, 説明)
    "supplement": (0.0, "栄養補助食品・サプリメント（HSコード2106等）"),
    "health_food": (0.0, "健康食品（HSコード2106等）"),
    "food_general": (0.09, "食品一般"),
    "confectionery": (0.21, "菓子類（チョコレート等）"),
    "beverage": (0.0, "飲料"),
    "clothing": (0.107, "衣類・繊維製品（HSコード61-62章）"),
    "shoes": (0.30, "靴（HSコード64章）"),
    "bag": (0.10, "バッグ・かばん（HSコード42章）"),
    "electronics": (0.0, "電子機器・家電（HSコード85章）"),
    "toys": (0.0, "玩具（HSコード95章）"),
    "sports": (0.0, "スポーツ用品（HSコード95章）"),
    "cosmetics": (0.0, "化粧品（HSコード33章）"),
    "furniture": (0.0, "家具（HSコード94章）"),
    "jewelry": (0.056, "宝石・貴金属（HSコード71章）"),
    "books": (0.0, "書籍・印刷物（HSコード49章）"),
    "auto_parts": (0.0, "自動車部品（HSコード87章）"),
    "other": (0.044, "その他一般品（平均関税率）"),
}

# カテゴリ名キーワードマッピング
KEYWORD_MAP = {
    "サプリ": "supplement",
    "supplement": "supplement",
    "栄養": "supplement",
    "健康食品": "health_food",
    "食品": "food_general",
    "食料": "food_general",
    "飲料": "beverage",
    "ドリンク": "beverage",
    "菓子": "confectionery",
    "チョコ": "confectionery",
    "衣類": "clothing",
    "服": "clothing",
    "アパレル": "clothing",
    "靴": "shoes",
    "シューズ": "shoes",
    "バッグ": "bag",
    "かばん": "bag",
    "電子": "electronics",
    "家電": "electronics",
    "スマホ": "electronics",
    "パソコン": "electronics",
    "おもちゃ": "toys",
    "玩具": "toys",
    "スポーツ": "sports",
    "化粧品": "cosmetics",
    "コスメ": "cosmetics",
    "家具": "furniture",
    "ジュエリー": "jewelry",
    "宝石": "jewelry",
    "本": "books",
    "書籍": "books",
}

CONSUMPTION_TAX_RATE = 0.10  # 消費税10%


def get_customs_rate(search_key: str) -> dict:
    """
    商品カテゴリまたはHSコードから関税率を取得する。

    Args:
        search_key: カテゴリ名（日本語）またはHSコード

    Returns:
        {
            "search_key": str,
            "description": str,
            "customs_rate": float,
            "consumption_tax_rate": float,
            "total_rate": float,
        }
    """
    # テストモードはマスタ直接参照
    if AppConfig.TEST_MODE:
        return _lookup_from_master(search_key)

    # キャッシュ確認
    cached = get_customs_rate_from_cache(search_key)
    if cached:
        return cached

    # HSコードの場合はWebスクレイピング
    if re.match(r"^\d{4,10}$", search_key.strip()):
        try:
            result = _scrape_by_hs_code(search_key.strip())
            if result:
                save_customs_rate_to_cache(result)
                return result
        except Exception as e:
            print(f"HSコード検索失敗: {e}")

    # キーワードマスタから検索
    result = _lookup_from_master(search_key)
    save_customs_rate_to_cache(result)
    return result


def _scrape_by_hs_code(hs_code: str) -> dict | None:
    """税関サイトでHSコードを検索して税率を取得する。"""
    with get_page(headless=True, timeout_ms=30000) as page:
        page.goto(CUSTOMS_SEARCH_URL, wait_until="domcontentloaded")
        time.sleep(2)

        # HSコード検索フォームを探す
        try:
            input_el = page.query_selector("input[name*='hs'], input[name*='code'], input[type='text']")
            if input_el:
                input_el.fill(hs_code)
                page.keyboard.press("Enter")
                time.sleep(2)

                body = page.inner_text("body")
                rate = _extract_rate_from_text(body)
                if rate is not None:
                    total = rate + CONSUMPTION_TAX_RATE
                    return {
                        "search_key": hs_code,
                        "description": f"HSコード {hs_code}",
                        "customs_rate": rate,
                        "consumption_tax_rate": CONSUMPTION_TAX_RATE,
                        "total_rate": round(total, 4),
                    }
        except Exception:
            pass
    return None


def _extract_rate_from_text(text: str) -> float | None:
    """テキストから関税率（小数）を抽出する。"""
    patterns = [
        r"基本税率[：:\s]*(\d+(?:\.\d+)?)\s*%",
        r"WTO税率[：:\s]*(\d+(?:\.\d+)?)\s*%",
        r"一般税率[：:\s]*(\d+(?:\.\d+)?)\s*%",
        r"関税率[：:\s]*(\d+(?:\.\d+)?)\s*%",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return float(m.group(1)) / 100
    return None


def _lookup_from_master(search_key: str) -> dict:
    """キーワードマッピングからマスタを参照する。"""
    master_key = "other"

    for keyword, key in KEYWORD_MAP.items():
        if keyword.lower() in search_key.lower():
            master_key = key
            break

    customs_rate, description = CUSTOMS_MASTER[master_key]
    total_rate = customs_rate + CONSUMPTION_TAX_RATE

    return {
        "search_key": search_key,
        "description": description,
        "customs_rate": customs_rate,
        "consumption_tax_rate": CONSUMPTION_TAX_RATE,
        "total_rate": round(total_rate, 4),
    }


def get_all_categories() -> list[dict]:
    """利用可能な商品カテゴリ一覧を返す（UI用）。"""
    categories = []
    for key, (rate, desc) in CUSTOMS_MASTER.items():
        categories.append({
            "key": key,
            "description": desc,
            "customs_rate": rate,
            "consumption_tax_rate": CONSUMPTION_TAX_RATE,
            "total_rate": round(rate + CONSUMPTION_TAX_RATE, 4),
        })
    return categories
