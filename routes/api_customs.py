from flask import Blueprint, request, jsonify
from services.scraper_customs import get_customs_rate, get_all_categories

bp = Blueprint("api_customs", __name__, url_prefix="/api/customs")


@bp.route("/search", methods=["POST"])
def search():
    """カテゴリ名またはHSコードから関税率を取得する。"""
    data = request.get_json(force=True) or {}
    search_key = data.get("search_key", "").strip()
    if not search_key:
        return jsonify({"error": "カテゴリ名またはHSコードを入力してください"}), 400

    try:
        result = get_customs_rate(search_key)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/categories", methods=["GET"])
def categories():
    """利用可能な商品カテゴリ一覧を返す（UI用）。"""
    return jsonify({"categories": get_all_categories()})
