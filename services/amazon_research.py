"""
Amazon.co.jp 商品リサーチサービス。
キーワード検索 → 売れているのにライバルが弱い商品を抽出する。

判定基準:
- 月間販売数 ≥ 300個
- レビュー数 ≤ 100
- 複数セラーが類似商品を販売している
"""
import re
import time
import math
from config.settings import AppConfig
from utils.playwright_manager import get_page
from services.ad_estimator import estimate_monthly_sales_from_bsr

AMAZON_SEARCH = "https://www.amazon.co.jp/s?k={query}&ref=nb_sb_noss"

# ──────────────────────────────────────────
# 中国輸入除外カテゴリ・キーワード
# 食品・飲料・サプリ・医薬品は中国から輸入してAmazonで販売できないため除外
# ──────────────────────────────────────────

# カテゴリ文字列に含まれていたら除外
_EXCLUDED_CATEGORY_KEYWORDS = [
    "食品", "飲料", "お酒", "酒", "栄養補助", "サプリメント",
    "医薬品", "医薬部外品", "健康食品", "ドラッグ",
    "Food", "Beverage", "Supplement", "Vitamin", "Grocery",
]

# タイトルに含まれていたら除外（食品・サプリと判断できる単語）
_EXCLUDED_TITLE_KEYWORDS = [
    "サプリ", "サプリメント", "プロテイン", "ビタミン", "ミネラル",
    "コラーゲン", "乳酸菌", "腸活", "グルコサミン", "コンドロイチン",
    "鉄分", "カルシウム", "亜鉛", "マグネシウム", "葉酸", "DHA", "EPA",
    "オメガ3", "アミノ酸", "BCAA", "クレアチン", "ホエイ",
    "食品", "飲料", "お茶", "コーヒー", "ジュース", "お酒", "ビール",
    "栄養", "無添加", "オーガニック", "栄養補助", "健康食品",
    "サプリ", "粒", "カプセル", "錠", "mg配合",
]


def _is_excluded_product(title: str, category: str) -> bool:
    """食品・サプリ・医薬品カテゴリに該当する商品かどうかを判定する。"""
    for kw in _EXCLUDED_CATEGORY_KEYWORDS:
        if kw in category:
            return True
    for kw in _EXCLUDED_TITLE_KEYWORDS:
        if kw in title:
            return True
    return False


# ──────────────────────────────────────────
# テストモード用ダミーデータ（中国輸入向け商品）
# ──────────────────────────────────────────

DUMMY_RESULTS = [
    {
        "asin": "B0TEST001",
        "title": "【テスト】折りたたみ式スマホスタンド 角度調整 アルミ製 卓上",
        "price": 1980,
        "rating": 4.2,
        "review_count": 34,
        "estimated_monthly_sales": 520,
        "bsr": 1250,
        "category": "スマートフォン・タブレット > アクセサリ",
        "image_url": "https://images-na.ssl-images-amazon.com/images/I/71test001.jpg",
        "url": "https://www.amazon.co.jp/dp/B0TEST001",
        "seller_count": 3,
        "opportunity_score": 88,
        "opportunity_label": "◎ 優良",
        "dimensions": {"length": 12, "width": 8, "height": 3, "weight_g": 180},
        "similar_seller_count": 5,
    },
    {
        "asin": "B0TEST002",
        "title": "【テスト】ケーブル収納ボックス コードオーガナイザー 大容量",
        "price": 2480,
        "rating": 4.1,
        "review_count": 21,
        "estimated_monthly_sales": 410,
        "bsr": 1850,
        "category": "ホーム＆キッチン > 収納・整理",
        "image_url": "",
        "url": "https://www.amazon.co.jp/dp/B0TEST002",
        "seller_count": 2,
        "opportunity_score": 84,
        "opportunity_label": "◎ 優良",
        "dimensions": {"length": 20, "width": 12, "height": 10, "weight_g": 350},
        "similar_seller_count": 4,
    },
    {
        "asin": "B0TEST003",
        "title": "【テスト】ドッグハーネス 小型犬 メッシュ 反射テープ付き 3サイズ",
        "price": 1680,
        "rating": 4.3,
        "review_count": 58,
        "estimated_monthly_sales": 680,
        "bsr": 920,
        "category": "ペット用品 > 犬用品",
        "image_url": "",
        "url": "https://www.amazon.co.jp/dp/B0TEST003",
        "seller_count": 4,
        "opportunity_score": 76,
        "opportunity_label": "○ 良好",
        "dimensions": {"length": 22, "width": 15, "height": 3, "weight_g": 120},
        "similar_seller_count": 7,
    },
    {
        "asin": "B0TEST004",
        "title": "【テスト】防水LEDキャンプランタン USB充電 4モード 折りたたみ",
        "price": 2980,
        "rating": 4.4,
        "review_count": 77,
        "estimated_monthly_sales": 390,
        "bsr": 1540,
        "category": "スポーツ＆アウトドア > キャンプ・登山",
        "image_url": "",
        "url": "https://www.amazon.co.jp/dp/B0TEST004",
        "seller_count": 5,
        "opportunity_score": 71,
        "opportunity_label": "○ 良好",
        "dimensions": {"length": 10, "width": 10, "height": 15, "weight_g": 230},
        "similar_seller_count": 6,
    },
    {
        "asin": "B0TEST006",
        "title": "【テスト】爪切り ステンレス製 ゴムグリップ ケース付き 高級",
        "price": 1280,
        "rating": 4.3,
        "review_count": 18,
        "estimated_monthly_sales": 480,
        "bsr": 1100,
        "category": "ビューティー > ネイルケア",
        "image_url": "",
        "url": "https://www.amazon.co.jp/dp/B0TEST006",
        "seller_count": 3,
        "opportunity_score": 90,
        "opportunity_label": "◎ 優良",
        "dimensions": {"length": 9, "width": 3, "height": 1, "weight_g": 45},
        "similar_seller_count": 5,
    },
    {
        "asin": "B0TEST005",
        "title": "【テスト】マグネット車載ホルダー ダッシュボード 360度回転 ワイヤレス充電対応",
        "price": 1580,
        "rating": 4.5,
        "review_count": 12,
        "estimated_monthly_sales": 730,
        "bsr": 610,
        "category": "カー＆バイク用品 > カーアクセサリ",
        "image_url": "",
        "url": "https://www.amazon.co.jp/dp/B0TEST005",
        "seller_count": 2,
        "opportunity_score": 95,
        "opportunity_label": "◎ 優良",
        "dimensions": {"length": 9, "width": 6, "height": 4, "weight_g": 95},
        "similar_seller_count": 3,
    },
]


def search_opportunities(
    keyword: str,
    max_review: int = 100,
    min_monthly_sales: int = 300,
    max_results: int = 20,
) -> list[dict]:
    """
    Amazonでキーワード検索し、機会スコアが高い商品リストを返す。
    """
    if AppConfig.TEST_MODE:
        kw_lower = keyword.lower()
        filtered = [r for r in DUMMY_RESULTS
                    if r["review_count"] <= max_review
                    and r["estimated_monthly_sales"] >= min_monthly_sales
                    and not _is_excluded_product(r["title"], r["category"])
                    and (kw_lower in r["title"].lower() or kw_lower in r["category"].lower())]
        return sorted(filtered, key=lambda x: -x["opportunity_score"])

    try:
        return _scrape_search_results(keyword, max_review, min_monthly_sales, max_results)
    except Exception as e:
        print(f"Amazonリサーチ失敗: {e}")
        return []


def get_product_detail(asin_or_url: str) -> dict:
    """
    Amazon商品の詳細情報（寸法・重量・BSR・セラー数など）を取得する。
    """
    if AppConfig.TEST_MODE:
        return _dummy_product_detail(asin_or_url)

    url = asin_or_url if asin_or_url.startswith("http") else f"https://www.amazon.co.jp/dp/{asin_or_url}"
    try:
        return _scrape_product_detail(url)
    except Exception as e:
        print(f"商品詳細取得失敗: {e}")
        return {}


# ──────────────────────────────────────────
# 実際のスクレイピング（本番モード）
# ──────────────────────────────────────────

def _scrape_search_results(
    keyword: str,
    max_review: int,
    min_monthly_sales: int,
    max_results: int,
) -> list[dict]:
    """Amazon検索ページをスクレイピングして商品リストを返す。"""
    url = AMAZON_SEARCH.format(query=keyword.replace(" ", "+"))
    products = []

    with get_page(headless=True, timeout_ms=40000) as page:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(2)

        items = page.query_selector_all(
            "[data-component-type='s-search-result']"
        )

        for item in items[:max_results]:
            try:
                product = _parse_search_item(page, item)
                if product:
                    products.append(product)
            except Exception:
                continue

        # スポンサー広告の比率を計算（広告費推計用）
        sponsored = page.query_selector_all("[class*='sponsored'], [data-component-type='sp-sponsored-result']")
        ad_ratio = len(sponsored) / max(len(items), 1)

    # 機会スコアを付与してフィルタリング（食品・サプリは除外）
    results = []
    for p in products:
        if _is_excluded_product(p["title"], p["category"]):
            continue
        p["opportunity_score"] = _calc_opportunity_score(p)
        p["opportunity_label"] = _score_to_label(p["opportunity_score"])
        if p["review_count"] <= max_review and p["estimated_monthly_sales"] >= min_monthly_sales:
            results.append(p)

    return sorted(results, key=lambda x: -x["opportunity_score"])


def _parse_search_item(page, item) -> dict | None:
    """検索結果の1アイテムをパースする。"""
    try:
        title_el = item.query_selector("h2 a span, h2 span")
        title = title_el.inner_text().strip() if title_el else ""
        if not title:
            return None

        # URL・ASIN
        link_el = item.query_selector("h2 a")
        href = link_el.get_attribute("href") if link_el else ""
        asin = _extract_asin(href)
        full_url = f"https://www.amazon.co.jp{href}" if href.startswith("/") else href

        # 価格
        price = _extract_price(item)

        # レビュー
        rating, review_count = _extract_reviews(item)

        # 月間販売数（表示されている場合）
        monthly_sales_text = _extract_monthly_sales_text(item)
        monthly_sales = monthly_sales_text or 0

        # カテゴリ（検索結果からは難しいので空文字）
        category = ""

        return {
            "asin": asin,
            "title": title[:120],
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "estimated_monthly_sales": monthly_sales,
            "bsr": 0,
            "category": category,
            "image_url": _extract_image(item),
            "url": full_url,
            "seller_count": 1,
            "dimensions": {},
            "similar_seller_count": 0,
            "opportunity_score": 0,
            "opportunity_label": "",
        }
    except Exception:
        return None


def _extract_variation_asins(page) -> list[str]:
    """バリエーション選択UI（twister）から子ASINの一覧を取得する。"""
    try:
        result = page.evaluate("""
        () => {
            const asins = new Set();
            const selectors = [
                '#twister [data-asin]',
                '#twister_feature_div [data-asin]',
                '[id^="color_name_"][data-asin]',
                '[id^="size_name_"][data-asin]',
                '[id^="style_name_"][data-asin]',
                '[id^="flavor_name_"][data-asin]',
            ];
            selectors.forEach(sel => {
                try {
                    document.querySelectorAll(sel).forEach(el => {
                        const a = (el.getAttribute('data-asin') || '').trim();
                        if (/^[A-Z0-9]{10}$/.test(a)) asins.add(a);
                    });
                } catch(e) {}
            });
            // ドロップダウン形式のバリエーション
            document.querySelectorAll('select option[data-asin]').forEach(el => {
                const a = (el.getAttribute('data-asin') || '').trim();
                if (/^[A-Z0-9]{10}$/.test(a)) asins.add(a);
            });
            return [...asins];
        }
        """)
        return result or []
    except Exception:
        return []


def _scrape_variation_sales(page, variation_asins: list[str], current_asin: str) -> tuple[int, list[dict]]:
    """
    各バリエーションのASINページを順に訪問して「X点以上購入」バッジを合算する。
    Returns: (total_sales_min, details_list)
    """
    details = []
    total = 0
    for asin in variation_asins:
        try:
            page.goto(f"https://www.amazon.co.jp/dp/{asin}", wait_until="domcontentloaded")
            time.sleep(1.2)
            sales = _extract_monthly_sales_text(page)
            details.append({"asin": asin, "sales": sales, "is_current": asin == current_asin})
            total += sales
            print(f"  バリエーション {asin}: {sales}点")
        except Exception as e:
            details.append({"asin": asin, "sales": 0, "is_current": asin == current_asin})
            print(f"  バリエーション {asin}: 取得失敗 ({e})")
    return total, details


def _scrape_product_detail(url: str) -> dict:
    """商品詳細ページをスクレイピングして寸法・BSR・セラー数などを取得する。"""
    # URLからASIN抽出
    m_asin = re.search(r"/dp/([A-Z0-9]{10})", url)
    current_asin = m_asin.group(1) if m_asin else ""

    with get_page(headless=True, timeout_ms=40000) as page:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(2)

        body = page.inner_text("body")

        # 寸法
        dims = _extract_dimensions(page, body)

        # BSR
        bsr, category = _extract_bsr(page, body)

        # レビュー
        rating, review_count = _extract_reviews_detail(page)

        # 価格
        price = _extract_price_detail(page)

        # セラー数
        seller_count = _extract_seller_count(page, body)

        # 現在の子ASINの月間販売数バッジ
        current_sales = _extract_monthly_sales_text(page)

        # タイトル・画像（ページ離脱前に取得）
        title_el = page.query_selector("#productTitle span.a-size-large, #productTitle span, #productTitle")
        title = title_el.inner_text().strip()[:120] if title_el else ""
        image_url, image_urls = _extract_product_images(page)

        # バリエーション子ASIN一覧を取得（ページ離脱前に）
        variation_asins = _extract_variation_asins(page)
        print(f"バリエーション検出: {variation_asins}")

        # バリエーションが複数ある場合は全子ASINの販売数を合算
        variation_details = []
        sales_from_badge = False
        if len(variation_asins) > 1:
            total, variation_details = _scrape_variation_sales(page, variation_asins, current_asin)
            if total > 0:
                monthly_sales = total
                sales_from_badge = True
            else:
                monthly_sales = current_sales or estimate_monthly_sales_from_bsr(bsr, "other")
                sales_from_badge = bool(current_sales)
        else:
            monthly_sales = current_sales or estimate_monthly_sales_from_bsr(bsr, "other")
            sales_from_badge = bool(current_sales)

        return {
            "title": title,
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "estimated_monthly_sales": monthly_sales,
            "sales_from_badge": sales_from_badge,
            "variation_count": len(variation_asins),
            "variation_sales_detail": variation_details,
            "bsr": bsr,
            "category": category,
            "seller_count": seller_count,
            "dimensions": dims,
            "image_url": image_url,
            "image_urls": image_urls,
        }


# ──────────────────────────────────────────
# パースヘルパー
# ──────────────────────────────────────────

def _extract_asin(href: str) -> str:
    m = re.search(r"/dp/([A-Z0-9]{10})", href)
    return m.group(1) if m else ""


def _extract_price(item) -> float:
    selectors = [".a-price .a-offscreen", ".a-price-whole", "[class*='price']"]
    for sel in selectors:
        el = item.query_selector(sel)
        if el:
            text = el.inner_text().replace("￥", "").replace(",", "").strip()
            m = re.search(r"(\d+)", text)
            if m:
                return float(m.group(1))
    return 0.0


def _extract_reviews(item) -> tuple[float, int]:
    rating = 0.0
    count = 0
    rating_el = item.query_selector(".a-icon-alt, [class*='rating']")
    if rating_el:
        text = rating_el.inner_text()
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if m:
            rating = float(m.group(1))
    count_el = item.query_selector("[class*='review-count'], .a-size-base")
    if count_el:
        text = count_el.inner_text().replace(",", "")
        m = re.search(r"(\d+)", text)
        if m:
            count = int(m.group(1))
    return rating, count


def _extract_reviews_detail(page) -> tuple[float, int]:
    rating = 0.0
    count = 0
    try:
        el = page.query_selector("#acrPopover")
        if el:
            text = el.get_attribute("title") or ""
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            if m:
                rating = float(m.group(1))
        el2 = page.query_selector("#acrCustomerReviewText")
        if el2:
            text = el2.inner_text().replace(",", "")
            m = re.search(r"(\d+)", text)
            if m:
                count = int(m.group(1))
    except Exception:
        pass
    return rating, count


def _extract_monthly_sales_text(item_or_page) -> int:
    """「過去1ヶ月でX点以上購入」の表示から月間販売数を取得する。"""
    try:
        if hasattr(item_or_page, "query_selector"):
            # Amazon.co.jp の social proofing テキスト（例: 「過去1か月で200点以上購入されました」）
            selectors = [
                "[class*='social-proofing']",
                "#social-proofing-faceout-title-text",
                "[id*='social-proofing']",
                "[class*='bought-in-past']",
                "[class*='purchase']",
                "[class*='bought']",
            ]
            for sel in selectors:
                el = item_or_page.query_selector(sel)
                if el:
                    text = el.inner_text().replace(",", "")
                    m = re.search(r"(\d+)\+?\s*(?:点|個|件)", text)
                    if m:
                        return int(m.group(1))
            # セレクタに引っかからない場合は全文テキストから探す
            body_el = item_or_page.query_selector("#centerCol, #ppd, body")
            if body_el:
                body_text = body_el.inner_text().replace(",", "")
                m = re.search(r"過去[1１]か?ヶ?月で\s*(\d+)\s*(?:点|個|件)以上購入", body_text)
                if m:
                    return int(m.group(1))
    except Exception:
        pass
    return 0


def _extract_image(item) -> str:
    try:
        el = item.query_selector("img.s-image, img[class*='image']")
        if el:
            return el.get_attribute("src") or ""
    except Exception:
        pass
    return ""


def _extract_product_images(page) -> tuple[str, list[str]]:
    """商品詳細ページから全画像URLを取得する。高解像度版を優先。"""
    import json as _json
    urls = []

    # data-a-dynamic-image に複数サイズのURLが入っている
    main_el = page.query_selector("#landingImage, #imgBlkFront, #main-image")
    if main_el:
        dynamic = main_el.get_attribute("data-a-dynamic-image") or ""
        if dynamic:
            try:
                sizes = _json.loads(dynamic)
                # 最大解像度のURLを先頭に
                sorted_urls = sorted(sizes.keys(), key=lambda u: sizes[u][0], reverse=True)
                urls.extend(sorted_urls)
            except Exception:
                pass
        if not urls:
            src = main_el.get_attribute("src") or ""
            if src:
                urls.append(src)

    # サムネイル一覧から追加画像を取得
    thumb_els = page.query_selector_all(
        "#altImages .item img, #imageBlock_feature_div .imageThumbnail img, "
        "#imageBlockThumbs img, .regularAltImageThumb img"
    )
    for el in thumb_els:
        src = el.get_attribute("src") or ""
        # サムネイルURLを高解像度に変換 (_SS40_ → _SL500_ など)
        import re as _re
        hires = _re.sub(r"\._[A-Z0-9_,]+_\.", "._SL500_.", src)
        if hires and hires not in urls and "sprite" not in hires and "gif" not in hires:
            urls.append(hires)

    # 重複除去・空除去
    seen = set()
    result = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            result.append(u)

    return (result[0] if result else ""), result


def _extract_dimensions(page, body: str) -> dict:
    """
    商品詳細ページから梱包時の寸法を抽出する。
    FBA手数料は梱包サイズ基準のため、梱包サイズを優先して取得し、
    なければ商品サイズにフォールバックする。
    """
    dims = {}

    # ── 梱包サイズ優先パターン ──
    # Amazonの商品詳細テーブルでは "梱包サイズ" または "パッケージサイズ" と記載される
    packaging_patterns = [
        r"(?:梱包サイズ|パッケージサイズ|Package\s*Dimensions?|梱包時のサイズ)[^\d]*"
        r"(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM)",
        r"(?:梱包サイズ|パッケージサイズ)[^\d]*"
        r"(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)",
    ]
    # ── 商品サイズフォールバックパターン ──
    product_patterns = [
        r"(?:商品サイズ|サイズ|寸法)[^\d]*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*[×x×]\s*(\d+(?:\.\d+)?)\s*(?:cm|CM)",
        r"(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*[×x]\s*(\d+(?:\.\d+)?)\s*cm",
    ]

    for pat in packaging_patterns + product_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            vals = sorted([float(m.group(1)), float(m.group(2)), float(m.group(3))], reverse=True)
            dims = {"length": vals[0], "width": vals[1], "height": vals[2]}
            break

    # 重量（梱包時重量 → 商品重量 の順で優先）
    weight_patterns = [
        r"(?:梱包時の重量|梱包重量|Package\s*Weight)[^\d]*(\d+(?:\.\d+)?)\s*(g|kg|グラム|キログラム)",
        r"(?:商品の重量|重量|重さ)[^\d]*(\d+(?:\.\d+)?)\s*(g|kg|グラム|キログラム)",
    ]
    for pat in weight_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            unit = m.group(2)
            dims["weight_g"] = val * 1000 if "k" in unit.lower() else val
            break

    return dims


def aggregate_competitor_dimensions(dim_list: list[dict]) -> dict:
    """
    複数の競合ページから取得した梱包寸法リストを集約して信頼値を返す。

    アルゴリズム:
    1. 各辺（長・幅・高）と重量の中央値を計算
    2. 中央値から50%以上乖離する値を外れ値として除外
    3. 残った値の平均を最終値とする（外れ値除外後も中央値を使う）

    例:
      [30,30,31,28,5] → 中央値30 → 5は外れ値 → 残り[28,30,30,31]の中央値=30

    Returns:
      {"length": float, "width": float, "height": float, "weight_g": float,
       "source_count": int, "outliers_removed": int}
    """
    if not dim_list:
        return {}

    def _median_filtered(values: list[float]) -> tuple[float, int]:
        """中央値フィルタリング後の中央値と除去数を返す。"""
        if not values:
            return 0.0, 0
        values = sorted(values)
        med = values[len(values) // 2]
        if med == 0:
            return 0.0, 0
        filtered = [v for v in values if abs(v - med) / med <= 0.5]
        removed = len(values) - len(filtered)
        if not filtered:
            filtered = values  # 全部外れ値の場合は元に戻す
        final_med = filtered[len(filtered) // 2]
        return round(final_med, 1), removed

    keys = ["length", "width", "height", "weight_g"]
    result = {}
    total_outliers = 0

    for key in keys:
        values = [d[key] for d in dim_list if key in d and d[key] > 0]
        if values:
            val, removed = _median_filtered(values)
            result[key] = val
            total_outliers += removed

    result["source_count"] = len(dim_list)
    result["outliers_removed"] = total_outliers
    return result


def _extract_bsr(page, body: str) -> tuple[int, str]:
    """BSRとカテゴリを抽出する。"""
    bsr = 0
    category = ""
    # Amazon Japan BSR形式: "#3,990 in ホーム&キッチン"
    m = re.search(r"#([\d,]+)\s+in\s+([\w＆&・\-ーホームキッチン\s]+?)(?:\n|（|\(|$)", body)
    if not m:
        # 別形式: "#3,990（ホーム&キッチン）"
        m = re.search(r"#([\d,]+)\s*[（(]([\w＆&・\-ー\s]+)[）)]", body)
    if m:
        bsr = int(m.group(1).replace(",", ""))
        category = m.group(2).strip()[:100] if m.lastindex >= 2 else ""
    return bsr, category


def _extract_price_detail(page) -> float:
    selectors = [
        "#priceblock_ourprice", "#priceblock_dealprice",
        ".a-price .a-offscreen", "#corePrice_feature_div .a-offscreen",
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if el:
            text = el.inner_text().replace("￥", "").replace(",", "")
            m = re.search(r"(\d+)", text)
            if m:
                return float(m.group(1))
    return 0.0


def _extract_seller_count(page, body: str) -> int:
    """セラー数を抽出する。"""
    m = re.search(r"(\d+)\s*(?:人|社|件)(?:の新品|の出品)", body)
    if m:
        return int(m.group(1))
    return 1


# ──────────────────────────────────────────
# ライバルセラー取得
# ──────────────────────────────────────────

# テストモード用ライバルダミーデータ（カテゴリ別）
_DUMMY_COMPETITOR_POOL = [
    {
        "asin": "B0C101", "title": "【競合A】マグネット車載スマホホルダー 強力磁石 360度回転",
        "price": 1299, "rating": 4.2, "review_count": 45,
        "estimated_monthly_sales": 380,
        "image_url": "https://placehold.co/200x200/dbeafe/1e40af?text=競合A",
        "url": "https://www.amazon.co.jp/dp/B0C101",
        "dimensions": {"length": 11.0, "width": 9.0, "height": 6.0, "weight_g": 130},
    },
    {
        "asin": "B0C102", "title": "【競合B】ダッシュボード スマホスタンド マグネット式 3in1充電対応",
        "price": 1680, "rating": 4.0, "review_count": 128,
        "estimated_monthly_sales": 520,
        "image_url": "https://placehold.co/200x200/dcfce7/166534?text=競合B",
        "url": "https://www.amazon.co.jp/dp/B0C102",
        "dimensions": {"length": 12.0, "width": 9.0, "height": 6.0, "weight_g": 140},
    },
    {
        "asin": "B0C103", "title": "【競合C】車用スマートフォンホルダー 磁力強化版 iPhone/Android対応",
        "price": 2180, "rating": 4.5, "review_count": 312,
        "estimated_monthly_sales": 780,
        "image_url": "https://placehold.co/200x200/fef9c3/713f12?text=競合C",
        "url": "https://www.amazon.co.jp/dp/B0C103",
        "dimensions": {"length": 10.0, "width": 8.0, "height": 5.0, "weight_g": 110},
    },
    {
        "asin": "B0C104", "title": "【競合D】カーマウント マグネット型 超強力 粘着台座付き 汎用",
        "price": 980, "rating": 3.8, "review_count": 67,
        "estimated_monthly_sales": 290,
        "image_url": "https://placehold.co/200x200/fee2e2/991b1b?text=競合D",
        "url": "https://www.amazon.co.jp/dp/B0C104",
        "dimensions": {"length": 9.0, "width": 7.0, "height": 4.0, "weight_g": 90},  # 外れ値（小さめ）
    },
    {
        "asin": "B0C105", "title": "【競合E】スマホホルダー 車載 吸盤式 伸縮アーム 360度調節",
        "price": 1480, "rating": 4.1, "review_count": 89,
        "estimated_monthly_sales": 410,
        "image_url": "https://placehold.co/200x200/f3e8ff/6b21a8?text=競合E",
        "url": "https://www.amazon.co.jp/dp/B0C105",
        "dimensions": {"length": 13.0, "width": 10.0, "height": 7.0, "weight_g": 160},
    },
    {
        "asin": "B0C106", "title": "【競合F】マグネットホルダー 車載 エアコン吹き出し口 クリップ式",
        "price": 799, "rating": 3.9, "review_count": 203,
        "estimated_monthly_sales": 650,
        "image_url": "https://placehold.co/200x200/fff7ed/9a3412?text=競合F",
        "url": "https://www.amazon.co.jp/dp/B0C106",
        "dimensions": {"length": 11.0, "width": 8.0, "height": 5.0, "weight_g": 120},
    },
]


def search_rival_products(title: str, category: str = "", max_results: int = 10) -> dict:
    """
    タイトル＋カテゴリからキーワードを抽出し、Amazon検索で上位商品を返す。
    レビュー数・販売数のフィルターなし（市場確認用）。
    """
    from services.claude_service import extract_search_keyword

    # カテゴリパスの末尾（例: "ホーム＆キッチン > 収納 > ネックピロー" → "ネックピロー"）をフォールバックとして用意
    category_leaf = category.split(" > ")[-1].strip() if category else ""

    keyword = extract_search_keyword(title, category)
    if not keyword:
        # Claude失敗 → カテゴリ末尾 → タイトル先頭4語の順でフォールバック
        keyword = category_leaf or " ".join(title.split()[:4])

    if AppConfig.TEST_MODE:
        return {"keyword": keyword, "products": DUMMY_RESULTS[:max_results]}

    try:
        results = _scrape_search_results(keyword, max_review=99999, min_monthly_sales=0, max_results=max_results)
        return {"keyword": keyword, "products": results}
    except Exception as e:
        print(f"ライバル商品検索失敗: {e}")
        return {"keyword": keyword, "products": [], "error": str(e)}


def get_competitors(asin: str, title: str, max_results: int = 6) -> list[dict]:
    """
    指定商品のライバルセラー商品リストを返す。
    テストモード: ダミーデータを返す。
    本番モード: タイトルキーワードでAmazon検索して類似商品を返す。
    """
    if AppConfig.TEST_MODE:
        return [c for c in _DUMMY_COMPETITOR_POOL if c["asin"] != asin][:max_results]

    keyword = " ".join(title.split()[:6])  # 先頭6単語でキーワード検索
    try:
        results = _scrape_search_results(keyword, max_review=99999, min_monthly_sales=0, max_results=max_results + 2)
        return [r for r in results if r.get("asin") != asin][:max_results]
    except Exception as e:
        print(f"ライバル取得失敗: {e}")
        return []


def _dummy_product_detail(asin_or_url: str) -> dict:
    """テストモード用ダミー商品詳細。"""
    asin = _extract_asin(asin_or_url) if "/" in asin_or_url else asin_or_url
    dummy = next((d for d in DUMMY_RESULTS if d["asin"] == asin), DUMMY_RESULTS[0])
    return {
        "title": dummy["title"],
        "price": dummy["price"],
        "rating": dummy["rating"],
        "review_count": dummy["review_count"],
        "estimated_monthly_sales": dummy["estimated_monthly_sales"],
        "bsr": dummy["bsr"],
        "category": dummy["category"],
        "seller_count": dummy["seller_count"],
        "dimensions": dummy["dimensions"],
    }


# ──────────────────────────────────────────
# 機会スコア計算
# ──────────────────────────────────────────

def _calc_opportunity_score(p: dict) -> int:
    """
    0〜100点の機会スコアを計算する。
    - 月間販売数が多い → 高得点
    - レビューが少ない → 高得点
    """
    score = 0

    # 月間販売数スコア（最大50点）
    sales = p.get("estimated_monthly_sales", 0)
    score += min(50, int(sales / 300 * 25))

    # レビューの少なさスコア（最大50点）
    reviews = p.get("review_count", 9999)
    if reviews <= 10:    score += 50
    elif reviews <= 30:  score += 43
    elif reviews <= 50:  score += 34
    elif reviews <= 70:  score += 24
    elif reviews <= 100: score += 14
    else:                score += 0

    return min(100, score)


def _score_to_label(score: int) -> str:
    if score >= 80: return "◎ 優良"
    if score >= 60: return "○ 良好"
    if score >= 40: return "△ 普通"
    return "× 不向き"
