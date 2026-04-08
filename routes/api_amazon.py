from flask import Blueprint, request, jsonify
from services.scraper_amazon_fee import get_amazon_fees
from services.fba_calculator import calculate_fba_fee, get_all_tiers
from services.scraper_amazon_search import predict_category_from_amazon

bp = Blueprint("api_amazon", __name__, url_prefix="/api/amazon")


@bp.route("/categories", methods=["GET"])
def categories():
    """Amazonカテゴリ別手数料一覧を返す。"""
    try:
        fees = get_amazon_fees()
        return jsonify({"categories": fees})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/fee", methods=["POST"])
def fee():
    """カテゴリと商品重量からAmazon手数料を計算する。"""
    data = request.get_json(force=True) or {}
    category_key = data.get("category_key", "")
    selling_price = float(data.get("selling_price", 0))
    weight_g = float(data.get("weight_g", 0))

    # カテゴリ手数料率取得
    fees = get_amazon_fees()
    category = next((f for f in fees if f["key"] == category_key), None)
    if category is None:
        # キーが見つからなければ名前で検索
        category = next((f for f in fees if category_key in f["name"]), fees[-1])

    referral_rate = category["fee_rate"]
    min_fee = category.get("min_fee") or 0
    referral_fee = max(selling_price * referral_rate, min_fee)

    # FBA手数料
    fba = calculate_fba_fee(weight_g)
    fba_fee = fba["fee_jpy"]

    return jsonify({
        "category_name": category["name"],
        "referral_rate": referral_rate,
        "referral_fee": round(referral_fee, 2),
        "fba_size": fba["size_name"],
        "fba_fee": fba_fee,
        "total_amazon_fee": round(referral_fee + fba_fee, 2),
    })


@bp.route("/fba-tiers", methods=["GET"])
def fba_tiers():
    """FBA手数料の全区分を返す（UI用）。"""
    return jsonify({"tiers": get_all_tiers()})


@bp.route("/predict-category", methods=["POST"])
def predict_category():
    """商品名からAmazonカテゴリを予測する。"""
    data = request.get_json(force=True) or {}
    product_name = data.get("product_name", "").strip()
    if not product_name:
        return jsonify({"error": "商品名を入力してください"}), 400

    try:
        result = predict_category_from_amazon(product_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/refresh-fees", methods=["POST"])
def refresh_fees():
    """Amazon手数料キャッシュを強制更新する。"""
    try:
        fees = get_amazon_fees(force_refresh=True)
        return jsonify({"message": "手数料データを更新しました", "count": len(fees)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
