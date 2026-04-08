"""
Amazon.co.jp で類似商品を検索してカテゴリを予測するサービス。
1688の商品名（中国語または日本語）をもとにAmazonを検索し、
上位結果のカテゴリからAmazon手数料カテゴリを推定する。
"""
import re
import time
from utils.playwright_manager import get_page
from config.settings import AppConfig

AMAZON_SEARCH_URL = "https://www.amazon.co.jp/s?k={query}"

# Amazonのパンくずカテゴリ名 → 手数料カテゴリキーのマッピング
AMAZON_CATEGORY_MAP = {
    "食品": "food",
    "食料品": "food",
    "飲料": "beverage",
    "お酒": "beverage",
    "ビール": "beverage",
    "ワイン": "beverage",
    "栄養補助食品": "supplement",
    "サプリ": "supplement",
    "プロテイン": "supplement",
    "ビタミン": "supplement",
    "コラーゲン": "supplement",
    "健康食品": "health_food",
    "ヘルス": "health",
    "ビューティー": "beauty",
    "コスメ": "cosmetics",
    "化粧品": "cosmetics",
    "スキンケア": "cosmetics",
    "服": "clothing",
    "ファッション": "clothing",
    "衣類": "clothing",
    "アパレル": "clothing",
    "靴": "shoes",
    "シューズ": "shoes",
    "バッグ": "bag",
    "財布": "bag",
    "電化製品": "electronics",
    "家電": "electronics",
    "スマートフォン": "mobile",
    "パソコン": "pc",
    "おもちゃ": "toys",
    "ホビー": "toys",
    "ゲーム": "video_games",
    "テレビゲーム": "video_games",
    "スポーツ": "sports",
    "アウトドア": "sports",
    "ペット": "pet",
    "ホーム": "home",
    "キッチン": "home",
    "インテリア": "home",
    "家具": "furniture",
    "文房具": "office",
    "オフィス": "office",
    "本": "books",
    "書籍": "books",
    "時計": "watches",
    "ジュエリー": "jewelry",
    "DIY": "tools",
    "工具": "tools",
    "ベビー": "baby",
    "マタニティ": "baby",
    "車": "auto",
    "バイク": "auto",
    "カメラ": "camera",
    "音楽": "music",
}


def predict_category_from_amazon(product_name: str) -> dict:
    """
    Amazonで類似商品を検索してカテゴリを予測する。

    Args:
        product_name: 商品名（中国語または日本語）

    Returns:
        {
            "predicted_category_key": str,
            "predicted_category_name": str,
            "confidence": "high" | "medium" | "low",
            "amazon_product_title": str,   # 見つかったAmazon商品名
            "amazon_category_path": str,   # Amazonのカテゴリパス
            "search_query": str,
        }
    """
    if AppConfig.TEST_MODE:
        return _dummy_prediction(product_name)

    # 中国語テキストを含む場合はキーワードを絞る
    search_query = _clean_query(product_name)

    try:
        return _search_amazon(search_query, product_name)
    except Exception as e:
        print(f"Amazonカテゴリ予測失敗: {e}")
        return _fallback_prediction(product_name)


def _dummy_prediction(product_name: str) -> dict:
    """テストモード用ダミー予測。カテゴリパスから正しく推定する。"""
    category_path = "ヘルス＆ビューティー > 栄養補助食品 > コラーゲン"
    key, name = _map_category(category_path)

    # category_pathでマッチしなければ商品名から推定
    if key == "other":
        key, name = _map_category(product_name)

    return {
        "predicted_category_key": key,
        "predicted_category_name": name,
        "confidence": "high",
        "amazon_product_title": f"【テスト】{product_name[:30]}（類似商品）",
        "amazon_category_path": category_path,
        "search_query": _clean_query(product_name),
    }


def _search_amazon(query: str, original_name: str) -> dict:
    """Amazonで検索して上位商品のカテゴリを取得する。"""
    url = AMAZON_SEARCH_URL.format(query=query.replace(" ", "+"))

    with get_page(headless=True, timeout_ms=30000) as page:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(2)

        # 最初の商品リンクを取得
        first_result = page.query_selector(
            "[data-component-type='s-search-result'] h2 a, "
            ".s-result-item h2 a"
        )
        if not first_result:
            return _fallback_prediction(original_name)

        product_title = first_result.inner_text().strip()

        # 商品詳細ページへ移動
        first_result.click()
        time.sleep(2)

        # パンくずリスト（カテゴリパス）を取得
        category_path = _extract_category_path(page)
        product_title_detail = _extract_product_title(page) or product_title

        # カテゴリキーを推定
        category_key, category_name = _map_category(category_path or "")

        confidence = "high" if category_path else "low"

        return {
            "predicted_category_key": category_key,
            "predicted_category_name": category_name,
            "confidence": confidence,
            "amazon_product_title": product_title_detail[:100],
            "amazon_category_path": category_path or "",
            "search_query": query,
        }


def _extract_category_path(page) -> str:
    """パンくずリストからカテゴリパスを抽出する。"""
    selectors = [
        "#wayfinding-breadcrumbs_feature_div",
        ".a-breadcrumb",
        "#breadcrumb",
        "[id*='breadcrumb']",
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                # 改行・連続スペースを整理
                text = re.sub(r"\s+", " > ", text).strip(" > ")
                if text:
                    return text[:200]
        except Exception:
            continue
    return ""


def _extract_product_title(page) -> str:
    """商品詳細ページからタイトルを取得する。"""
    selectors = ["#productTitle", "h1.a-size-large", "h1"]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                return el.inner_text().strip()[:100]
        except Exception:
            continue
    return ""


def _map_category(category_path: str) -> tuple[str, str]:
    """カテゴリパス文字列から手数料カテゴリキーと名称を返す。
    長いキーワードを優先してマッチする（部分一致の誤判定を防ぐ）。
    """
    from services.scraper_amazon_fee import FALLBACK_FEES

    # キーワードを長い順に並べてマッチ精度を上げる
    sorted_items = sorted(AMAZON_CATEGORY_MAP.items(), key=lambda x: -len(x[0]))

    for keyword, key in sorted_items:
        if keyword in category_path:
            fee_info = next((f for f in FALLBACK_FEES if f["key"] == key), None)
            name = fee_info["name"] if fee_info else keyword
            return key, name

    # マッチしなければ「その他」
    return "other", "その他"


def _fallback_prediction(product_name: str) -> dict:
    """商品名キーワードからカテゴリを推定するフォールバック。"""
    from services.scraper_amazon_fee import FALLBACK_FEES

    key, name = _map_category(product_name)

    # フォールバック値から正確な名前を取得
    fee_info = next((f for f in FALLBACK_FEES if f["key"] == key), None)
    if fee_info:
        name = fee_info["name"]

    return {
        "predicted_category_key": key,
        "predicted_category_name": name,
        "confidence": "low",
        "amazon_product_title": "",
        "amazon_category_path": "",
        "search_query": _clean_query(product_name),
    }


def _clean_query(text: str) -> str:
    """商品名から検索クエリを生成する。中国語文字を除去し日本語キーワードを抽出。"""
    # 中国語（CJK統合漢字の範囲）と日本語を分離
    # 日本語（ひらがな・カタカナ）を優先
    jp_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+', text)

    if jp_chars:
        query = " ".join(jp_chars[:4])  # 最大4トークン
    else:
        # 英数字のみの場合
        query = re.sub(r'[^\w\s]', ' ', text)
        query = " ".join(query.split()[:5])

    return query[:100]
