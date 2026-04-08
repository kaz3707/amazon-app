from flask import Blueprint, request, jsonify
from services.scraper_sale_monster import get_sale_monster_costs

bp = Blueprint("api_sale_monster", __name__, url_prefix="/api/sale-monster")


@bp.route("/costs", methods=["POST"])
def costs():
    """セールモンスターにログインして費用情報を取得する。"""
    data = request.get_json(force=True) or {}
    selling_price = float(data.get("selling_price", 0))

    result = get_sale_monster_costs()

    # 広告費（20%）を販売価格から計算
    ad_fee = selling_price * result.get("ad_rate", 0.20)
    result["ad_fee"] = round(ad_fee, 2)
    result["selling_price"] = selling_price
    result["total_sm_fee"] = round(
        ad_fee + result.get("shipping_fee", 0) + result.get("storage_fee_monthly", 0), 2
    )

    return jsonify(result)
