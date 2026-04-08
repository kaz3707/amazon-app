"""
Amazon.co.jp ベストセラーランキングをカテゴリ別に収集するサービス。

大カテゴリ → 中カテゴリ → 小カテゴリと再帰的にたどり、
各サブカテゴリのTop100を取得してキャッシュに保存する。
食品・サプリ・医薬品カテゴリは除外する。
"""

import re
import json
import os
import threading
from datetime import datetime
from config.settings import AppConfig

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "bestseller_cache.json")

# ──────────────────────────────────────────
# スクレイピング対象カテゴリのルート（中国輸入品向け）
# ──────────────────────────────────────────

CATEGORY_ROOTS = [
    {"name": "ホーム＆キッチン",       "url": "https://www.amazon.co.jp/gp/bestsellers/kitchen/"},
    {"name": "スポーツ＆アウトドア",   "url": "https://www.amazon.co.jp/gp/bestsellers/sports/"},
    {"name": "ペット用品",             "url": "https://www.amazon.co.jp/gp/bestsellers/pet-supplies/"},
    {"name": "カー＆バイク用品",       "url": "https://www.amazon.co.jp/gp/bestsellers/automotive/"},
    {"name": "家電＆カメラ",           "url": "https://www.amazon.co.jp/gp/bestsellers/electronics/"},
    {"name": "おもちゃ",               "url": "https://www.amazon.co.jp/gp/bestsellers/toys/"},
    {"name": "文房具・オフィス用品",   "url": "https://www.amazon.co.jp/gp/bestsellers/office-products/"},
    {"name": "ベビー＆マタニティ",     "url": "https://www.amazon.co.jp/gp/bestsellers/baby/"},
    {"name": "ファッション",           "url": "https://www.amazon.co.jp/gp/bestsellers/fashion/"},
    {"name": "DIY・工具・ガーデン",   "url": "https://www.amazon.co.jp/gp/bestsellers/diy/"},
    {"name": "ビューティー",           "url": "https://www.amazon.co.jp/gp/bestsellers/beauty/"},
    {"name": "バッグ・旅行用品",       "url": "https://www.amazon.co.jp/gp/bestsellers/fashion/2221077051/"},
    {"name": "ドラッグストア",         "url": "https://www.amazon.co.jp/gp/bestsellers/hpc/"},
    {"name": "産業・研究開発",         "url": "https://www.amazon.co.jp/gp/bestsellers/industrial/"},
]

# 除外カテゴリ（食品・サプリ・医薬品は中国輸入不可）
_EXCLUDED_KEYWORDS = [
    # 食品・サプリ・医薬品（中国輸入不可）
    "食品", "飲料", "お酒", "酒類", "栄養補助食品", "サプリメント", "サプリ",
    "医薬品", "医薬部外品", "健康食品",
    "プロテイン", "ビタミン", "ミネラル", "コラーゲン", "乳酸菌",
    # デジタルコンテンツ・無形商品（中国輸入対象外）
    "Kindle", "DVD", "ゲーム", "ミュージック", "デジタルミュージック",
    "Prime Video", "アプリ", "PCソフト", "ギフトカード", "整備済み品",
]

# ──────────────────────────────────────────
# バックグラウンド更新状態
# ──────────────────────────────────────────

_status = {
    "running": False,
    "categories_done": 0,
    "categories_total": 0,
    "current_category": "",
    "error": None,
}


def get_status() -> dict:
    if AppConfig.TEST_MODE:
        categories = sorted(set(p["category_path"] for p in _DUMMY_PRODUCTS))
        return {
            "running": False,
            "categories_done": 0,
            "categories_total": 0,
            "current_category": "",
            "error": None,
            "last_updated": "テストモード",
            "total_products": len(_DUMMY_PRODUCTS),
            "categories": categories,
            "category_roots": [r["name"] for r in CATEGORY_ROOTS],
        }
    cache = _load_cache()
    return {
        "running": _status["running"],
        "categories_done": _status["categories_done"],
        "categories_total": _status["categories_total"],
        "current_category": _status["current_category"],
        "error": _status["error"],
        "last_updated": cache.get("last_updated"),
        "total_products": cache.get("total_products", 0),
        "categories": cache.get("categories", []),
        "category_roots": [r["name"] for r in CATEGORY_ROOTS],
    }


def start_refresh(selected_root_names=None, max_depth=3):
    """バックグラウンドでベストセラーデータを更新する。"""
    if _status["running"]:
        return False, "既に更新中です"

    roots = CATEGORY_ROOTS
    if selected_root_names:
        roots = [r for r in CATEGORY_ROOTS if r["name"] in selected_root_names]
    if not roots:
        return False, "対象カテゴリがありません"

    _status["categories_total"] = len(roots)
    _status["categories_done"] = 0
    _status["error"] = None

    thread = threading.Thread(target=_do_refresh, args=(roots, max_depth), daemon=True)
    thread.start()
    return True, f"{len(roots)}カテゴリの更新を開始しました"


def browse(max_review=100, min_sales=300, category_prefix=None) -> list[dict]:
    """キャッシュから条件に合う商品一覧を返す。"""
    if AppConfig.TEST_MODE:
        return _browse_dummy(max_review, min_sales, category_prefix)

    cache = _load_cache()
    products = cache.get("products", [])

    results = []
    for p in products:
        if p.get("review_count", 9999) > max_review:
            continue
        if p.get("estimated_monthly_sales", 0) < min_sales:
            continue
        if category_prefix and not p.get("category_path", "").startswith(category_prefix):
            continue
        results.append(p)

    return sorted(results, key=lambda x: -x.get("opportunity_score", 0))


def get_categories() -> list[str]:
    """カテゴリパス一覧を返す。"""
    if AppConfig.TEST_MODE:
        return sorted(set(p["category_path"] for p in _DUMMY_PRODUCTS))
    cache = _load_cache()
    return cache.get("categories", [])


def get_category_top100(category_path: str) -> list[dict]:
    """指定の小カテゴリのTOP100商品をキャッシュから返す（ランク順）。"""
    if AppConfig.TEST_MODE:
        matched = [p for p in _DUMMY_PRODUCTS if p.get("category_path") == category_path]
        return sorted(matched, key=lambda x: x.get("rank_in_category", 9999))[:100]
    cache = _load_cache()
    products = cache.get("products", [])
    matched = [p for p in products if p.get("category_path") == category_path]
    return sorted(matched, key=lambda x: x.get("rank_in_category", 9999))[:100]


# ──────────────────────────────────────────
# キャッシュ読み書き
# ──────────────────────────────────────────

def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(products: list, categories: list):
    data = {
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "total_products": len(products),
        "categories": sorted(set(categories)),
        "products": products,
    }
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────
# バックグラウンドスクレイピング
# ──────────────────────────────────────────

def _do_refresh(roots: list, max_depth: int):
    from utils.playwright_manager import get_page, human_wait
    global _status
    _status["running"] = True

    all_products = []
    all_categories = []
    seen_urls: set[str] = set()
    seen_asins: set[str] = set()

    try:
        with get_page(headless=True, timeout_ms=40000) as page:
            for root in roots:
                _status["current_category"] = root["name"]
                _scrape_recursive(
                    page, root["url"], root["name"], 1, max_depth,
                    all_products, all_categories, seen_urls, seen_asins,
                )
                _status["categories_done"] += 1
                # 大カテゴリ完了ごとにキャッシュ保存（途中でも使える）
                _save_cache(all_products, all_categories)
    except Exception as e:
        _status["error"] = str(e)
        print(f"ベストセラー更新エラー: {e}")
    finally:
        _status["running"] = False
        _status["current_category"] = ""


def _scrape_recursive(page, url, category_path, depth, max_depth,
                       all_products, all_categories, seen_urls, seen_asins):
    """1カテゴリのベストセラーとサブカテゴリを再帰的にスクレイピング。
    小カテゴリ（リーフ）のTOP100のみ保存し、大・中カテゴリはスキップして再帰する。
    """
    from utils.playwright_manager import human_wait

    if url in seen_urls:
        return
    seen_urls.add(url)

    # 食品・サプリは除外
    if any(kw in category_path for kw in _EXCLUDED_KEYWORDS):
        return

    try:
        page.goto(url, wait_until="domcontentloaded")
        human_wait(1.5, 3.5)

        # サブカテゴリを確認（最大深度に達した場合はリーフとみなす）
        subcats = _get_subcategories(page, url) if depth < max_depth else []

        if not subcats:
            # リーフカテゴリ（小カテゴリ）: TOP100を保存して即時キャッシュ書き込み
            products = _parse_bestseller_page(page, category_path)
            for p in products:
                if p.get("asin") and p["asin"] not in seen_asins:
                    seen_asins.add(p["asin"])
                    all_products.append(p)
            if products:
                all_categories.append(category_path)
                _save_cache(all_products, all_categories)  # 1小カテゴリ完了ごとに保存
            print(f"  [{depth}] 小カテゴリ保存: {category_path} ({len(products)}件) / 累計{len(all_products)}件")
        else:
            # 中間カテゴリ: 商品は保存せず子カテゴリへ再帰
            print(f"  [{depth}] 中間スキップ: {category_path} → {len(subcats)}サブカテゴリ")
            for subcat_url, subcat_name in subcats:
                child_path = f"{category_path} > {subcat_name}"
                _scrape_recursive(
                    page, subcat_url, child_path, depth + 1, max_depth,
                    all_products, all_categories, seen_urls, seen_asins,
                )
                human_wait(1.0, 2.5)
    except Exception as e:
        print(f"スクレイピング失敗 ({category_path}): {e}")


def _get_subcategories(page, current_url: str) -> list[tuple[str, str]]:
    """左サイドバーからサブカテゴリリンクを取得する。"""
    subcats = []
    try:
        selectors = [
            "#zg-left-col ul li a",
            ".zg-left-col ul li a",
            "[class*='zg-browse'] a",
            "[class*='zg_browse'] a",
        ]
        links = []
        for sel in selectors:
            links = page.query_selector_all(sel)
            if links:
                break

        # サイドバーに出る「すべてのカテゴリー」は全カテゴリルートへのリンクなので除外
        _SKIP_NAMES = {"すべてのカテゴリー", "すべてのカテゴリ"}

        for link in links:
            href = link.get_attribute("href") or ""
            name = link.inner_text().strip()
            if not href or not name or "bestsellers" not in href:
                continue
            if name in _SKIP_NAMES:
                continue
            full_url = f"https://www.amazon.co.jp{href}" if href.startswith("/") else href
            if full_url == current_url:
                continue
            if not any(kw in name for kw in _EXCLUDED_KEYWORDS):
                subcats.append((full_url, name[:60]))
    except Exception as e:
        print(f"サブカテゴリ取得失敗: {e}")

    return subcats[:25]


def _parse_bestseller_page(page, category_path: str) -> list[dict]:
    """ベストセラーページから商品一覧を取得する（最大2ページ=100位まで）。"""
    products = []

    for page_num in [1, 2]:
        try:
            if page_num == 2:
                next_btn = page.query_selector(
                    ".a-pagination .a-last a, [class*='zg-pagination'] a:last-child"
                )
                if not next_btn:
                    break
                next_btn.click()
                from utils.playwright_manager import human_wait
                human_wait(1.5, 3.0)

            item_selectors = [
                "[id*='gridItemRoot']",
                ".zg-item-immersion",
                "[class*='zg-item']",
                ".p13n-desktop-grid-edge",
            ]
            items = []
            for sel in item_selectors:
                items = page.query_selector_all(sel)
                if items:
                    break

            base_rank = 1 + (page_num - 1) * 50
            for i, item in enumerate(items[:50]):
                try:
                    p = _parse_item(item, category_path, rank=base_rank + i)
                    if p:
                        products.append(p)
                except Exception:
                    continue
        except Exception:
            break

    return products


def _parse_item(item, category_path: str, rank: int) -> dict | None:
    """ベストセラー1商品をパースする。"""
    try:
        # ASIN取得: data-asin属性を優先（最も確実）
        asin = ""
        asin_el = item.query_selector("[data-asin]")
        if asin_el:
            asin = asin_el.get_attribute("data-asin") or ""
        if not asin:
            link_el = item.query_selector("a[href*='/dp/']")
            href = link_el.get_attribute("href") if link_el else ""
            asin = _extract_asin(href)
        if not asin:
            return None

        # タイトル取得: セレクタで試みてダメなら全テキストから抽出
        title_el = item.query_selector(
            "[class*='p13n-sc-css-line-clamp'], "
            "[class*='p13n-sc-truncated'], "
            ".p13n-sc-truncated, "
            "[class*='sc-product-title'], "
            "[class*='product-title'], "
            "a span[class*='p13n-sc'], "
            "a[href*='/dp/'] span"
        )
        title = title_el.inner_text().strip() if title_el else ""

        # フォールバック: アイテム全テキストの最初の意味ある行
        if not title or len(title) < 3:
            all_text = item.inner_text() or ""
            lines = [l.strip() for l in all_text.split("\n")
                     if l.strip() and not l.strip().startswith("#") and len(l.strip()) >= 3]
            title = lines[0] if lines else ""

        if not title or len(title) < 3:
            return None

        price = _extract_price(item)
        rating, review_count = _extract_reviews(item)
        monthly_sales = _estimate_sales_from_rank(rank)
        image_url = _extract_image(item)

        p = {
            "asin": asin,
            "title": title[:120],
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "estimated_monthly_sales": monthly_sales,
            "bsr": rank,
            "category_path": category_path,
            "category": category_path,
            "rank_in_category": rank,
            "image_url": image_url,
            "url": f"https://www.amazon.co.jp/dp/{asin}",
            "seller_count": 1,
            "similar_seller_count": 0,
            "dimensions": {},
        }
        p["scores"] = _calc_individual_scores(p)
        p["opportunity_score"] = _calc_opportunity_score(p)
        p["opportunity_label"] = _score_to_label(p["opportunity_score"])
        # Keepa BSR分析（本番モードでは後でまとめて取得するためデフォルト値を入れる）
        p["keepa_analysis"] = {"label": "未取得", "peak_months": [], "peak_months_str": "", "detail": "", "badge_type": "stable"}
        return p
    except Exception:
        return None


# ──────────────────────────────────────────
# パースヘルパー
# ──────────────────────────────────────────

def _extract_asin(href: str) -> str:
    m = re.search(r"/dp/([A-Z0-9]{10})", href or "")
    return m.group(1) if m else ""


def _extract_price(item) -> float:
    # セレクタで試みる
    for sel in [".p13n-sc-price", "[class*='p13n-sc-price']",
                ".a-price-whole", ".a-price .a-offscreen",
                "span.a-color-price", "[class*='a-price']"]:
        el = item.query_selector(sel)
        if el:
            text = el.inner_text().replace("￥", "").replace("¥", "").replace(",", "").strip()
            m = re.match(r"^(\d+)", text)
            if m and int(m.group(1)) >= 100:
                return float(m.group(1))
    # テキストフォールバック: ¥X,XXX 形式の行を探す
    try:
        all_text = item.inner_text() or ""
        prices = []
        for line in all_text.split("\n"):
            line = line.strip()
            if line.startswith("¥") or line.startswith("￥"):
                text = line.replace("¥", "").replace("￥", "").replace(",", "").strip()
                m = re.match(r"^(\d{3,7})$", text)
                if m:
                    prices.append(int(m.group(1)))
        if prices:
            return float(min(prices))  # 最安値（セール価格）を採用
    except Exception:
        pass
    return 0.0


def _extract_reviews(item) -> tuple[float, int]:
    """評価(星)とレビュー数を取得する。

    実測: [aria-label*="星"] のinnerTextが "5つ星のうち4.4\n 8,640" の形式で
    評価とレビュー数を両方含む。これを優先的に使用する。
    """
    rating, count = 0.0, 0

    el = item.query_selector("[aria-label*='星']")
    if el:
        text = el.inner_text() or ""
        # 評価: 小数点付き数字（例: "4.4"）
        m = re.search(r"(\d+\.\d+)", text)
        if m:
            rating = float(m.group(1))
        # レビュー数: 改行後の数字（例: " 8,640" → 8640）
        lines = [l.strip().replace(",", "") for l in text.split("\n") if l.strip()]
        for line in lines:
            m = re.match(r"^(\d+)$", line)
            if m and int(m.group(1)) > 5:  # 評価スケール(1-5)より大きければレビュー数
                count = int(m.group(1))
                break

    # フォールバック: .a-icon-alt の aria-label から評価のみ
    if rating == 0.0:
        el = item.query_selector(".a-icon-alt")
        if el:
            text = el.get_attribute("aria-label") or el.inner_text()
            m = re.search(r"(\d+\.\d+)", text)
            if m:
                rating = float(m.group(1))

    return rating, count


def _extract_image(item) -> str:
    try:
        el = item.query_selector("img")
        if el:
            return el.get_attribute("src") or ""
    except Exception:
        pass
    return ""


def _estimate_sales_from_rank(rank: int) -> int:
    """サブカテゴリ内ランキングから月間販売数を推計する。"""
    if rank <= 5:   return 2000
    if rank <= 10:  return 1200
    if rank <= 20:  return 700
    if rank <= 30:  return 500
    if rank <= 50:  return 380
    if rank <= 70:  return 320
    return 280


def _calc_individual_scores(p: dict) -> dict:
    """各指標の個別スコア（0〜100点）を計算する。"""
    # 販売数スコア
    sales = p.get("estimated_monthly_sales", 0)
    if sales >= 1000: sales_score = 100
    elif sales >= 700: sales_score = 85
    elif sales >= 500: sales_score = 70
    elif sales >= 400: sales_score = 60
    elif sales >= 300: sales_score = 50
    elif sales >= 200: sales_score = 35
    elif sales >= 100: sales_score = 20
    else:              sales_score = 5

    # レビュースコア（少ないほど高得点）
    reviews = p.get("review_count", 9999)
    if reviews <= 5:    review_score = 100
    elif reviews <= 10: review_score = 90
    elif reviews <= 20: review_score = 80
    elif reviews <= 30: review_score = 70
    elif reviews <= 50: review_score = 55
    elif reviews <= 70: review_score = 40
    elif reviews <= 100: review_score = 25
    elif reviews <= 200: review_score = 10
    else:               review_score = 0

    return {
        "sales": sales_score,
        "review": review_score,
    }


def _calc_opportunity_score(p: dict) -> int:
    """2指標の平均を機会スコアとする。"""
    s = _calc_individual_scores(p)
    return round((s["sales"] + s["review"]) / 2)


def _score_to_label(score: int) -> str:
    if score >= 80: return "◎ 優良"
    if score >= 60: return "○ 良好"
    if score >= 40: return "△ 普通"
    return "× 不向き"


# ──────────────────────────────────────────
# テストモード用ダミーデータ（中国輸入向け・複数サブカテゴリ）
# ──────────────────────────────────────────

def _d(l, w, h, g):
    """梱包寸法ショートハンド: length/width/height(cm), weight_g"""
    return {"length": l, "width": w, "height": h, "weight_g": g}


def _make(asin, title, price, rating, reviews, sales, rank, cat, img="", dims=None):
    from services.keepa_service import analyze_bsr
    p = {
        "asin": asin, "title": f"【テスト】{title}", "price": price,
        "rating": rating, "review_count": reviews, "estimated_monthly_sales": sales,
        "bsr": rank, "category_path": cat, "category": cat,
        "rank_in_category": rank, "image_url": img,
        "url": f"https://www.amazon.co.jp/dp/{asin}",
        "seller_count": 2 if reviews < 30 else 3, "similar_seller_count": 4,
        "dimensions": dims or {},
    }
    p["scores"] = _calc_individual_scores(p)
    p["opportunity_score"] = _calc_opportunity_score(p)
    p["opportunity_label"] = _score_to_label(p["opportunity_score"])
    p["keepa_analysis"] = analyze_bsr(asin)
    return p

_DUMMY_PRODUCTS = [
    # ホーム＆キッチン > 収納・整理 > ケーブル収納
    _make("B0D001","ケーブル収納ボックス コードオーガナイザー 大容量",2480,4.1,21,410,2,"ホーム＆キッチン > 収納・整理 > ケーブル収納",dims=_d(22,16,11,420)),
    _make("B0D002","ケーブルクリップ 10個セット 壁固定 シリコン製",980,4.3,8,550,5,"ホーム＆キッチン > 収納・整理 > ケーブル収納",dims=_d(12,8,3,80)),
    # ホーム＆キッチン > 収納・整理 > 引き出し用収納
    _make("B0D003","引き出し仕切り 伸縮式 6枚セット 調整可能",1580,4.2,35,320,8,"ホーム＆キッチン > 収納・整理 > 引き出し用収納",dims=_d(30,15,5,350)),
    _make("B0D004","小物入れ スタッキング収納ケース 透明 6個組",1280,4.0,52,350,12,"ホーム＆キッチン > 収納・整理 > 引き出し用収納",dims=_d(22,16,13,460)),
    # ホーム＆キッチン > 調理器具 > 計量器
    _make("B0D005","デジタルキッチンスケール 1g単位 5kg対応 風袋引き",1680,4.4,62,480,6,"ホーム＆キッチン > 調理器具 > 計量器",dims=_d(20,15,6,520)),
    _make("B0D006","計量スプーン 5本セット ステンレス 目盛り付き",880,4.2,19,390,10,"ホーム＆キッチン > 調理器具 > 計量スプーン",dims=_d(22,9,3,130)),
    # スポーツ＆アウトドア > キャンプ・登山 > ランタン
    _make("B0D007","防水LEDキャンプランタン USB充電 4モード 折りたたみ",2980,4.4,77,390,4,"スポーツ＆アウトドア > キャンプ・登山 > ランタン",dims=_d(13,13,19,370)),
    _make("B0D008","ソーラーランタン 充電式 防水 アウトドア コンパクト",1980,4.1,28,430,9,"スポーツ＆アウトドア > キャンプ・登山 > ランタン",dims=_d(11,11,16,290)),
    # スポーツ＆アウトドア > フィットネス > トレーニング器具
    _make("B0D009","プッシュアップバー 滑り止め付き 折りたたみ式",1480,4.3,41,520,3,"スポーツ＆アウトドア > フィットネス > トレーニング器具",dims=_d(32,22,11,620)),
    _make("B0D010","腹筋ローラー 膝マット付き ダブルホイール",1280,4.0,88,680,7,"スポーツ＆アウトドア > フィットネス > トレーニング器具",dims=_d(36,22,16,820)),
    # ペット用品 > 犬用品 > ハーネス・リード
    _make("B0D011","ドッグハーネス 小型犬 メッシュ 反射テープ付き 3サイズ",1680,4.3,58,680,2,"ペット用品 > 犬用品 > ハーネス・リード",dims=_d(24,17,4,160)),
    _make("B0D012","犬用リード 伸縮式 5m ロック機能付き 小中型犬",1380,4.1,33,410,6,"ペット用品 > 犬用品 > ハーネス・リード",dims=_d(14,9,9,210)),
    # ペット用品 > 猫用品 > おもちゃ
    _make("B0D013","猫じゃらし 電動 USB充電 自動回転 羽付き",1580,4.5,14,580,1,"ペット用品 > 猫用品 > おもちゃ",dims=_d(16,11,6,210)),
    _make("B0D014","猫用トンネル 折りたたみ 3穴タイプ ボール付き",1280,4.2,22,360,8,"ペット用品 > 猫用品 > おもちゃ",dims=_d(38,38,6,420)),
    # カー＆バイク用品 > カーアクセサリ > スマホホルダー
    _make("B0D015","マグネット車載ホルダー ダッシュボード 360度回転",1580,4.5,12,730,1,"カー＆バイク用品 > カーアクセサリ > スマホホルダー",dims=_d(11,9,6,120)),
    _make("B0D016","エアコン吹き出し口 スマホホルダー 片手操作",1280,4.3,25,490,4,"カー＆バイク用品 > カーアクセサリ > スマホホルダー",dims=_d(10,8,5,100)),
    # カー＆バイク用品 > カーアクセサリ > シートカバー
    _make("B0D017","シートカバー 前席2枚セット 防水 通気性メッシュ",3480,4.0,67,340,5,"カー＆バイク用品 > カーアクセサリ > シートカバー",dims=_d(42,36,9,1250)),
    # 家電＆カメラ > スマートフォン
    _make("B0D018","折りたたみ式スマホスタンド 角度調整 アルミ製 卓上",1980,4.2,34,520,3,"家電＆カメラ > スマートフォン > スタンド・ホルダー",dims=_d(15,11,4,230)),
    _make("B0D019","スマホリング 薄型 落下防止 360度回転 マグネット対応",880,4.3,17,640,5,"家電＆カメラ > スマートフォン > アクセサリ",dims=_d(10,8,3,55)),
    # おもちゃ > 知育玩具
    _make("B0D020","木製パズル 動物 10ピース 2歳以上 知育",1480,4.5,9,390,4,"おもちゃ > 知育玩具 > 木製パズル",dims=_d(26,19,5,420)),
    _make("B0D021","磁石ブロック 48ピース 立体 カラフル 収納袋付き",2480,4.3,31,420,7,"おもちゃ > 知育玩具 > 磁石ブロック",dims=_d(26,21,9,720)),
    # 文房具・オフィス用品
    _make("B0D022","多機能ボールペン 4色+シャープペン スリム 10本セット",1280,4.1,45,380,6,"文房具・オフィス用品 > 筆記用具 > ボールペン",dims=_d(21,9,4,210)),
    _make("B0D023","付箋 蛍光色 10色 600枚セット 防水タイプ",980,4.2,28,450,9,"文房具・オフィス用品 > 貼り付け用品 > 付箋",dims=_d(19,13,6,260)),
    # ビューティー > ネイルケア
    _make("B0D024","爪切り ステンレス製 ゴムグリップ ケース付き",1280,4.3,18,480,3,"ビューティー > ネイルケア > 爪切り",dims=_d(13,9,4,130)),
    _make("B0D025","ネイルファイル セット 両面グリット 10本入り",880,4.1,12,360,7,"ビューティー > ネイルケア > ネイルファイル",dims=_d(17,9,3,85)),
    # DIY・工具・ガーデン
    _make("B0D026","精密ドライバーセット 32本 磁気 収納ケース付き",1980,4.4,55,520,2,"DIY・工具・ガーデン > 工具 > ドライバーセット",dims=_d(19,13,5,360)),
    _make("B0D027","電動ドライバー USB充電式 トルク調整 LEDライト付き",3980,4.2,42,350,8,"DIY・工具・ガーデン > 電動工具 > 電動ドライバー",dims=_d(26,13,9,620)),
    # バッグ・旅行用品
    _make("B0D028","旅行用圧縮袋 6枚セット 手巻き式 大中小",1480,4.2,24,420,5,"バッグ・旅行用品 > 旅行用品 > 収納・整理",dims=_d(24,17,6,260)),
    _make("B0D029","トラベルポーチ 防水 4点セット 透明ジッパー",1280,4.0,38,380,9,"バッグ・旅行用品 > 旅行用品 > 収納・整理",dims=_d(22,16,9,310)),
    # ベビー＆マタニティ
    _make("B0D030","ベビーモニター ワイヤレス 暗視機能 温度表示",4980,4.3,16,310,6,"ベビー＆マタニティ > ベビーモニター",dims=_d(19,16,13,620)),
]


def _browse_dummy(max_review: int, min_sales: int, category_prefix: str | None) -> list[dict]:
    results = []
    for p in _DUMMY_PRODUCTS:
        if p["review_count"] > max_review:
            continue
        if p["estimated_monthly_sales"] < min_sales:
            continue
        if category_prefix and not p["category_path"].startswith(category_prefix):
            continue
        results.append(p)
    return sorted(results, key=lambda x: -x["opportunity_score"])
