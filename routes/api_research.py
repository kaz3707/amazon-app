"""
商品リサーチ・総合利益計算APIエンドポイント。
"""
import re
import requests as _requests
from flask import Blueprint, request, jsonify, Response
from services.amazon_research import search_opportunities, get_product_detail, get_competitors, aggregate_competitor_dimensions, search_rival_products
from services.amazon_bestseller import browse, get_categories, get_status, start_refresh, get_category_top100
from services.search_1688 import search_by_keyword, to_chinese_keyword, search_by_image
from services.claude_service import extract_search_keyword
from services.shipping_calculator import (
    calculate_fba_fee_from_dimensions,
    calculate_international_shipping,
    calculate_container_shipping,
    calculate_sagawa_btoc,
)
from services.scraper_customs import get_customs_rate
from services.ad_estimator import estimate_monthly_sales_from_bsr
from services.scraper_amazon_fee import FALLBACK_FEES
from services.exchange_rate import get_cny_to_jpy

bp = Blueprint("api_research", __name__, url_prefix="/api/research")


@bp.route("/cache-status", methods=["GET"])
def cache_status():
    """ベストセラーキャッシュの状態を返す。"""
    return jsonify(get_status())


@bp.route("/browse", methods=["POST"])
def browse_products():
    """キャッシュ済みベストセラーデータをフィルタリングして返す。"""
    data = request.get_json(force=True) or {}
    max_review = int(data.get("max_review", 100))
    min_sales = int(data.get("min_monthly_sales", 300))
    category_prefix = data.get("category", "") or None

    try:
        results = browse(max_review, min_sales, category_prefix)
        return jsonify({"results": results, "count": len(results), "category": category_prefix or "全カテゴリ"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/refresh", methods=["POST"])
def refresh_cache():
    """ベストセラーデータのバックグラウンド更新を開始する。"""
    data = request.get_json(force=True) or {}
    selected = data.get("categories") or None
    max_depth = int(data.get("max_depth", 3))

    ok, msg = start_refresh(selected, max_depth)
    return jsonify({"ok": ok, "message": msg})


@bp.route("/categories", methods=["GET"])
def list_categories():
    """利用可能なカテゴリパス一覧を返す。"""
    return jsonify({"categories": get_categories()})


@bp.route("/search-amazon", methods=["POST"])
def search_amazon():
    """Amazonでキーワード検索して機会商品リストを返す。"""
    data = request.get_json(force=True) or {}
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "キーワードを入力してください"}), 400

    max_review = int(data.get("max_review", 100))
    min_monthly_sales = int(data.get("min_monthly_sales", 300))

    try:
        results = search_opportunities(keyword, max_review, min_monthly_sales)
        return jsonify({"keyword": keyword, "results": results, "count": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/product-detail", methods=["POST"])
def product_detail():
    """Amazon商品URLまたはASINから詳細情報を取得する。機会スコア・Keepa分析を付与して返す。"""
    from services.amazon_bestseller import _calc_individual_scores, _calc_opportunity_score, _score_to_label
    from services.keepa_service import analyze_bsr

    data = request.get_json(force=True) or {}
    asin_or_url = data.get("asin_or_url", "").strip()
    if not asin_or_url:
        return jsonify({"error": "ASINまたはURLを入力してください"}), 400

    try:
        detail = get_product_detail(asin_or_url)

        # ASIN抽出（URLの場合 /dp/XXXXXXXXXX から、ASINの場合そのまま）
        m = re.search(r"/dp/([A-Z0-9]{10})", asin_or_url)
        asin = m.group(1) if m else re.sub(r"[^A-Z0-9]", "", asin_or_url.upper())[:10] or asin_or_url

        # 不足フィールドを補完
        detail.setdefault("asin", asin)
        detail.setdefault("image_url", "")
        detail.setdefault("url", f"https://www.amazon.co.jp/dp/{asin}")
        detail.setdefault("similar_seller_count", 0)
        detail.setdefault("category_path", detail.get("category", ""))
        detail.setdefault("rank_in_category", detail.get("bsr", 0))
        detail.setdefault("seller_count", 1)

        # 機会スコア計算
        detail["scores"] = _calc_individual_scores(detail)
        detail["opportunity_score"] = _calc_opportunity_score(detail)
        detail["opportunity_label"] = _score_to_label(detail["opportunity_score"])

        # Keepa BSR分析
        detail["keepa_analysis"] = analyze_bsr(asin)

        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/competitors", methods=["POST"])
def competitors():
    """指定商品のライバルセラー商品リストを返す。"""
    data = request.get_json(force=True) or {}
    asin = data.get("asin", "").strip()
    title = data.get("title", "").strip()
    max_results = int(data.get("max_results", 6))

    if not title and not asin:
        return jsonify({"error": "asin または title を指定してください"}), 400

    try:
        results = get_competitors(asin, title, max_results)

        # 競合ページから梱包寸法を集約（外れ値除去・中央値）
        dim_list = [r["dimensions"] for r in results if r.get("dimensions")]
        aggregated_dims = aggregate_competitor_dimensions(dim_list) if dim_list else {}

        return jsonify({
            "competitors": results,
            "count": len(results),
            "aggregated_dimensions": aggregated_dims,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/search-1688", methods=["POST"])
def search_1688():
    """1688でキーワード検索して仕入れ候補を返す。"""
    data = request.get_json(force=True) or {}
    keyword = data.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "キーワードを入力してください"}), 400

    cn_keyword = to_chinese_keyword(keyword)
    try:
        result = search_by_keyword(cn_keyword, max_results=8)
        result["cn_keyword"] = cn_keyword
        result["search_method"] = "キーワード検索"
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/search-1688-by-image", methods=["POST"])
def search_1688_by_image():
    """Amazon商品画像URLを使って1688で画像検索する（以图搜图）。"""
    data = request.get_json(force=True) or {}
    image_url = data.get("image_url", "").strip()
    if not image_url:
        return jsonify({"error": "画像URLを指定してください"}), 400

    crop = data.get("crop")  # {x1,y1,x2,y2} or None
    try:
        result = search_by_image(image_url, max_results=10, crop=crop)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/analyze", methods=["POST"])
def analyze():
    """
    選択した商品の総合利益・ROI分析を実行する。

    入力:
        amazon_price: float            # Amazon販売価格
        amazon_category_key: str       # Amazonカテゴリキー
        review_count: int              # ライバルのレビュー数
        seller_count: int              # ライバルのセラー数
        estimated_monthly_sales: int   # 月間販売数推計
        dimensions: {length, width, height, weight_g}  # 商品寸法
        purchase_price_cny: float      # 1688仕入れ単価（元）
        order_quantity: int            # 発注数量
        inspection_fee_per_unit: float # 検品費用/個
        customs_category: str          # 関税カテゴリ

    出力:
        完全な利益計算結果 + 広告費推計 + ROI
    """
    data = request.get_json(force=True) or {}

    # ─── 入力値取得 ───
    amazon_price = float(data.get("amazon_price", 0))
    category_key = data.get("amazon_category_key", "other")
    review_count = int(data.get("review_count", 50))
    seller_count = int(data.get("seller_count", 2))
    est_monthly_sales = int(data.get("estimated_monthly_sales", 0))
    dims = data.get("dimensions", {})
    purchase_price_cny = float(data.get("purchase_price_cny", 0))
    order_quantity = int(data.get("order_quantity", 100))
    inspection_fee = float(data.get("inspection_fee_per_unit", 30))
    fba_domestic_shipping = float(data.get("fba_domestic_shipping_per_unit", 0))  # FBA納品送料（国内作業所→FBA）
    customs_category = data.get("customs_category", category_key)
    agent_fee_jpy = float(data.get("agent_fee_jpy", 0))                    # 代行業者手数料
    domestic_shipping_jpy = float(data.get("domestic_shipping_jpy", 0))  # 中国国内送料
    total_acos = float(data.get("total_acos", 0.20))                      # トータルACOS（デフォルト20%）

    if amazon_price <= 0:
        return jsonify({"error": "Amazon販売価格を入力してください"}), 400
    if purchase_price_cny <= 0:
        return jsonify({"error": "1688仕入れ単価を入力してください"}), 400

    # ─── 計算 ───

    # 為替換算
    exchange_rate = get_cny_to_jpy()
    purchase_price_jpy = purchase_price_cny * exchange_rate

    # FBA手数料
    l = float(dims.get("length", 10))
    w = float(dims.get("width", 10))
    h = float(dims.get("height", 10))
    weight_g = float(dims.get("weight_g", 200))
    fba = calculate_fba_fee_from_dimensions(l, w, h, weight_g)
    fba_fee = fba["fee_jpy"]

    # 国際送料 ― 輸送方法に応じて計算、手動上書き値があればそちらを優先
    shipping_method = data.get("shipping_method", "fast_sea")
    intl_override = data.get("intl_shipping_override")

    if shipping_method == "container_fba_direct":
        shipping = calculate_container_shipping(l, w, h, weight_g, order_quantity)
        intl_shipping_per_unit = float(intl_override) if intl_override is not None else shipping["per_unit_jpy"]
        # FBA納品送料（佐川BtoC）― フロント側の値を優先、未入力なら自動計算
        if fba_domestic_shipping <= 0:
            sagawa = calculate_sagawa_btoc(l, w, h)
            fba_domestic_shipping = sagawa["fee_jpy"]
        else:
            sagawa = calculate_sagawa_btoc(l, w, h)
        shipping_detail = {
            "method": shipping["method"],
            "cbm_per_unit": shipping["cbm_per_unit"],
            "total_cbm": shipping["total_cbm"],
            "rate_per_cbm": shipping["rate_per_cbm"],
            "total_shipping_jpy": round(shipping["total_shipping_jpy"], 0),
            "chargeable_weight_kg": None,
            "rate_per_kg": None,
            "fba_domestic_method": f"佐川急便BtoC {sagawa['size_label']}",
        }
    else:
        shipping = calculate_international_shipping(l, w, h, weight_g, order_quantity, method="fast_sea")
        intl_shipping_per_unit = float(intl_override) if intl_override is not None else shipping["per_unit_jpy"]
        shipping_detail = {
            "method": shipping["method"],
            "chargeable_weight_kg": shipping["chargeable_weight_kg"],
            "rate_per_kg": shipping["rate_per_kg"],
            "total_shipping_jpy": round(shipping["total_shipping_jpy"], 0),
            "cbm_per_unit": None,
            "total_cbm": None,
            "fba_domestic_method": "ヤマトパートナーキャリア 140サイズ",
        }

    # Amazon紹介手数料
    fee_data = next((f for f in FALLBACK_FEES if f["key"] == category_key), FALLBACK_FEES[-1])
    referral_rate = fee_data["fee_rate"]
    referral_fee = max(amazon_price * referral_rate, fee_data.get("min_fee") or 0)

    # 関税・消費税
    customs_data = get_customs_rate(customs_category)
    customs_total_rate = customs_data["total_rate"]
    customs_amount = purchase_price_jpy * customs_total_rate

    # 総コスト（広告費前）
    total_cost_before_ad = (
        purchase_price_jpy
        + agent_fee_jpy
        + domestic_shipping_jpy
        + intl_shipping_per_unit
        + customs_amount
        + inspection_fee
        + fba_domestic_shipping
        + referral_fee
        + fba_fee
    )

    # 広告費前利益
    profit_before_ad = amazon_price - total_cost_before_ad
    profit_rate_before_ad = profit_before_ad / amazon_price * 100

    # 広告費（トータルACOS × 販売価格）
    ad_cost_per_unit = amazon_price * total_acos

    # 純利益（広告費込み）
    net_profit = profit_before_ad - ad_cost_per_unit
    net_profit_rate = net_profit / amazon_price * 100

    # ROI = 純利益 / 仕入れ単価
    roi = net_profit / purchase_price_jpy * 100 if purchase_price_jpy > 0 else 0

    # 月間純利益
    monthly_net_profit = net_profit * est_monthly_sales

    return jsonify({
        # 入力サマリ
        "amazon_price": amazon_price,
        "purchase_price_cny": purchase_price_cny,
        "purchase_price_jpy": round(purchase_price_jpy, 0),
        "exchange_rate": round(exchange_rate, 2),
        "order_quantity": order_quantity,

        # コスト内訳
        "costs": {
            "purchase_price_jpy": round(purchase_price_jpy, 0),
            "agent_fee_jpy": round(agent_fee_jpy, 0),
            "domestic_shipping_jpy": round(domestic_shipping_jpy, 0),
            "intl_shipping_per_unit": round(intl_shipping_per_unit, 0),
            "customs_amount": round(customs_amount, 0),
            "customs_rate_pct": round(customs_total_rate * 100, 1),
            "inspection_fee": round(inspection_fee, 0),
            "fba_domestic_shipping": round(fba_domestic_shipping, 0),
            "referral_fee": round(referral_fee, 0),
            "referral_rate_pct": round(referral_rate * 100, 1),
            "fba_fee": round(fba_fee, 0),
            "fba_size": fba["size_label"],
            "total_before_ad": round(total_cost_before_ad, 0),
        },

        # 広告費前利益
        "profit_before_ad": round(profit_before_ad, 0),
        "profit_rate_before_ad": round(profit_rate_before_ad, 1),

        # 広告費
        "ad_info": {
            "total_acos_pct": round(total_acos * 100, 1),
            "ad_cost_per_unit": round(ad_cost_per_unit, 0),
        },

        # 純利益（広告込み）
        "net_profit": round(net_profit, 0),
        "net_profit_rate": round(net_profit_rate, 1),
        "roi": round(roi, 1),

        # 月間推計
        "monthly": {
            "estimated_sales": est_monthly_sales,
            "net_profit": round(monthly_net_profit, 0),
        },

        # 配送詳細
        "shipping_detail": shipping_detail,
    })


@bp.route("/debug-scrape", methods=["GET"])
def debug_scrape():
    """ベストセラーページのスクレイピング診断（1カテゴリだけ試す）。"""
    from utils.playwright_manager import get_page, human_wait
    url = "https://www.amazon.co.jp/gp/bestsellers/kitchen/"
    result = {"url": url}
    try:
        with get_page(headless=True, timeout_ms=30000) as page:
            page.goto(url, wait_until="domcontentloaded")
            human_wait(2, 3)

            result["page_title"] = page.title()

            # 商品アイテムのセレクタ確認
            item_selectors = {
                "[id*='gridItemRoot']": 0,
                ".zg-item-immersion": 0,
                "[class*='zg-item']": 0,
                ".p13n-desktop-grid-edge": 0,
            }
            for sel in item_selectors:
                item_selectors[sel] = len(page.query_selector_all(sel))
            result["item_selector_counts"] = item_selectors

            # サブカテゴリのセレクタ確認
            subcat_selectors = {
                "#zg-left-col ul li a": 0,
                ".zg-left-col ul li a": 0,
                "[class*='zg-browse'] a": 0,
                "[class*='zg_browse'] a": 0,
            }
            for sel in subcat_selectors:
                subcat_selectors[sel] = len(page.query_selector_all(sel))
            result["subcat_selector_counts"] = subcat_selectors

            # ページのbody冒頭500文字
            body = page.inner_text("body")
            result["body_preview"] = body[:500]

            # 最初のアイテムの内部HTML（タイトルセレクタ確認用）
            first_item = page.query_selector("[id*='gridItemRoot']")
            if first_item:
                result["first_item_html"] = first_item.inner_html()[:2000]
                result["first_item_text"] = first_item.inner_text()[:500]

    except Exception as e:
        result["error"] = str(e)
    return jsonify(result)


@bp.route("/rival-products", methods=["POST"])
def rival_products():
    """タイトル＋カテゴリからキーワードを抽出し、Amazon上位10商品を返す（市場確認用）。"""
    data = request.get_json(force=True) or {}
    title = data.get("title", "").strip()
    category = data.get("category", "").strip()
    if not title:
        return jsonify({"error": "title を指定してください"}), 400

    try:
        result = search_rival_products(title, category, max_results=10)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/category-top100", methods=["POST"])
def category_top100():
    """同カテゴリのTOP100商品をキャッシュから返す（目視確認用）。"""
    data = request.get_json(force=True) or {}
    category_path = data.get("category_path", "").strip()
    if not category_path:
        return jsonify({"error": "category_path を指定してください"}), 400

    products = get_category_top100(category_path)
    return jsonify({"products": products, "category_path": category_path, "count": len(products)})


@bp.route("/extract-keyword", methods=["POST"])
def extract_keyword():
    """商品タイトルから最も検索されやすいキーワードを返す。"""
    data = request.get_json(force=True) or {}
    title = data.get("title", "")
    if not title:
        return jsonify({"keyword": ""})
    try:
        keyword = extract_search_keyword(title)
        return jsonify({"keyword": keyword})
    except Exception as e:
        return jsonify({"keyword": "", "error": str(e)})


@bp.route("/image-proxy", methods=["GET"])
def image_proxy():
    """Amazon画像をサーバー経由で取得してCORSを回避する。"""
    url = request.args.get("url", "")
    if not url or not url.startswith("https://"):
        return Response("invalid url", status=400)
    try:
        resp = _requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        return Response(
            resp.content,
            content_type=resp.headers.get("Content-Type", "image/jpeg"),
        )
    except Exception as e:
        return Response(str(e), status=502)
