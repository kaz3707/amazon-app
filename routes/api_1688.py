from flask import Blueprint, request, jsonify
from services.scraper_1688 import fetch_product_info
from services.exchange_rate import get_cny_to_jpy
from utils.playwright_manager import has_1688_session

bp = Blueprint("api_1688", __name__, url_prefix="/api/1688")


@bp.route("/fetch", methods=["POST"])
def fetch():
    """1688商品URLから商品情報を取得する。"""
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "URLを入力してください"}), 400
    if "1688.com" not in url:
        return jsonify({"error": "1688.comのURLを入力してください"}), 400

    try:
        result = fetch_product_info(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"商品情報の取得に失敗しました: {str(e)}"}), 500


@bp.route("/session-status", methods=["GET"])
def session_status():
    """1688ログインセッションの保存状態を返す。"""
    ok = has_1688_session()
    return jsonify({
        "logged_in": ok,
        "message": "ログイン済み" if ok else "未ログイン（setup_1688_login.bat を実行してください）",
    })


@bp.route("/exchange-rate", methods=["GET"])
def exchange_rate():
    """現在の人民元→円レートを返す。"""
    try:
        rate = get_cny_to_jpy()
        return jsonify({"rate": rate, "pair": "CNY_JPY"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
