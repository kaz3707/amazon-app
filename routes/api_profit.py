import json
from flask import Blueprint, request, jsonify
from models.db import db, CalculationHistory
from services.profit_calculator import CostInput, calculate_profit, breakdown_to_dict

bp = Blueprint("api_profit", __name__, url_prefix="/api/profit")


@bp.route("/calculate", methods=["POST"])
def calculate():
    """全コスト情報から利益を計算する。"""
    data = request.get_json(force=True) or {}

    try:
        inp = CostInput(
            purchase_price_jpy=float(data.get("purchase_price_jpy", 0)),
            international_shipping_per_unit=float(data.get("international_shipping_per_unit", 0)),
            customs_rate=float(data.get("customs_rate", 0)),
            inspection_fee_per_unit=float(data.get("inspection_fee_per_unit", 0)),
            other_cost_per_unit=float(data.get("other_cost_per_unit", 0)),
            platform=data.get("platform", "amazon"),
            selling_price=float(data.get("selling_price", 0)),
            amazon_referral_rate=float(data.get("amazon_referral_rate", 0.10)),
            amazon_referral_min_fee=float(data.get("amazon_referral_min_fee", 0)),
            fba_fee=float(data.get("fba_fee", 0)),
            sm_ad_rate=float(data.get("sm_ad_rate", 0.20)),
            sm_shipping_fee=float(data.get("sm_shipping_fee", 0)),
            sm_storage_fee=float(data.get("sm_storage_fee", 0)),
        )
    except (TypeError, ValueError) as e:
        return jsonify({"error": f"入力値エラー: {str(e)}"}), 400

    if inp.selling_price <= 0:
        return jsonify({"error": "販売価格を入力してください"}), 400

    result = calculate_profit(inp)
    result_dict = breakdown_to_dict(result)
    return jsonify(result_dict)


@bp.route("/save", methods=["POST"])
def save():
    """計算結果を手動保存する。"""
    data = request.get_json(force=True) or {}
    try:
        history = CalculationHistory(
            product_name=data.get("product_name", ""),
            product_url_1688=data.get("product_url_1688", ""),
            platform=data.get("platform", "amazon"),
            selling_price=float(data.get("selling_price", 0)),
            total_cost=float(data.get("total_cost", 0)),
            profit=float(data.get("profit", 0)),
            profit_rate=float(data.get("profit_rate", 0)),
            detail_json=json.dumps(data.get("detail", {}), ensure_ascii=False),
        )
        db.session.add(history)
        db.session.commit()
        return jsonify({"ok": True, "id": history.id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/history", methods=["GET"])
def history():
    """計算履歴一覧を返す（最新50件）。"""
    rows = CalculationHistory.query.order_by(
        CalculationHistory.created_at.desc()
    ).limit(50).all()

    def _extra(r):
        try:
            d = json.loads(r.detail_json) if r.detail_json else {}
            return {
                "roi": d.get("roi"),
                "monthly_net_profit": d.get("monthly", {}).get("net_profit"),
                "asin": d.get("asin"),
                "amazon_price": d.get("amazon_price"),
            }
        except Exception:
            return {}

    return jsonify({
        "history": [
            {
                "id": r.id,
                "product_name": r.product_name,
                "platform": r.platform,
                "selling_price": r.selling_price,
                "profit": r.profit,
                "profit_rate": r.profit_rate,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
                **_extra(r),
            }
            for r in rows
        ]
    })


@bp.route("/history/<int:history_id>", methods=["GET"])
def history_detail(history_id: int):
    """計算履歴の詳細を返す。"""
    row = CalculationHistory.query.get_or_404(history_id)
    detail = json.loads(row.detail_json) if row.detail_json else {}
    return jsonify({
        "id": row.id,
        "product_name": row.product_name,
        "product_url_1688": row.product_url_1688,
        "platform": row.platform,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M"),
        **detail,
    })


@bp.route("/history/<int:history_id>", methods=["DELETE"])
def delete_history(history_id: int):
    """計算履歴を削除する。"""
    row = CalculationHistory.query.get_or_404(history_id)
    db.session.delete(row)
    db.session.commit()
    return jsonify({"message": "削除しました"})
