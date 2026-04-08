"""
OEM改善案 & Amazon Q&A取得 APIエンドポイント。
"""
from flask import Blueprint, request, jsonify

bp = Blueprint("oem", __name__)


@bp.route("/api/oem/suggest", methods=["POST"])
def oem_suggest():
    """
    OEM物理改善案を生成する。
    Body: { product_title, category, competitor_titles[] }
    """
    data = request.get_json(force=True) or {}
    product_title = (data.get("product_title") or "").strip()
    category = (data.get("category") or "不明").strip()
    competitor_titles = data.get("competitor_titles") or []

    if not product_title:
        return jsonify({"error": "product_title は必須です"}), 400

    try:
        from services.claude_service import generate_oem_suggestions
        result = generate_oem_suggestions(product_title, category, competitor_titles)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/oem/deepdive", methods=["POST"])
def oem_deepdive():
    """
    OEM改善案の深掘り分析を生成する。
    Body: { product_title, category, suggestion_title, suggestion_description }
    """
    data = request.get_json(force=True) or {}
    product_title        = (data.get("product_title") or "").strip()
    category             = (data.get("category") or "不明").strip()
    suggestion_title     = (data.get("suggestion_title") or "").strip()
    suggestion_description = (data.get("suggestion_description") or "").strip()

    if not product_title or not suggestion_title:
        return jsonify({"error": "product_title と suggestion_title は必須です"}), 400

    try:
        from services.claude_service import deepdive_oem_suggestion
        result = deepdive_oem_suggestion(product_title, category, suggestion_title, suggestion_description)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/oem/qa", methods=["POST"])
def amazon_qa():
    """
    Amazon商品のQ&Aを取得する。
    Body: { asin }
    """
    data = request.get_json(force=True) or {}
    asin = (data.get("asin") or "").strip()

    if not asin:
        return jsonify({"error": "asin は必須です"}), 400

    try:
        from services.amazon_qa import fetch_amazon_qa
        items = fetch_amazon_qa(asin)
        return jsonify({"qa": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
