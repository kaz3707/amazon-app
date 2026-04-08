"""
SQLiteキャッシュの読み書きユーティリティ。
TTL（有効期限）チェック付き。
"""
from datetime import datetime, timedelta
from models.db import (
    db, AmazonFeeCache, CustomsRateCache, ExchangeRateCache, FbaFeeConfig
)
from config.settings import CacheConfig


# ── Amazon手数料キャッシュ ────────────────────────────────────────────

def get_amazon_fees_from_cache() -> list[dict] | None:
    """キャッシュが有効なAmazon手数料一覧を返す。期限切れまたは未存在の場合はNone。"""
    first = AmazonFeeCache.query.first()
    if first is None:
        return None
    threshold = datetime.utcnow() - timedelta(hours=CacheConfig.fee_ttl_hours)
    if first.updated_at < threshold:
        return None
    rows = AmazonFeeCache.query.order_by(AmazonFeeCache.category_name).all()
    return [
        {
            "key": r.category_key,
            "name": r.category_name,
            "fee_rate": r.fee_rate,
            "min_fee": r.min_fee,
        }
        for r in rows
    ]


def save_amazon_fees_to_cache(fees: list[dict]) -> None:
    """Amazon手数料をキャッシュに保存（全件入れ替え）。"""
    AmazonFeeCache.query.delete()
    now = datetime.utcnow()
    for f in fees:
        row = AmazonFeeCache(
            category_key=f["key"],
            category_name=f["name"],
            fee_rate=f["fee_rate"],
            min_fee=f.get("min_fee"),
            updated_at=now,
        )
        db.session.add(row)
    db.session.commit()


# ── 関税キャッシュ ────────────────────────────────────────────────────

def get_customs_rate_from_cache(search_key: str) -> dict | None:
    """キャッシュから税率を取得。期限切れの場合はNone。"""
    row = CustomsRateCache.query.filter_by(search_key=search_key).first()
    if row is None:
        return None
    threshold = datetime.utcnow() - timedelta(days=CacheConfig.customs_ttl_days)
    if row.updated_at < threshold:
        return None
    return {
        "search_key": row.search_key,
        "description": row.description,
        "customs_rate": row.customs_rate,
        "consumption_tax_rate": row.consumption_tax_rate,
        "total_rate": row.total_rate,
    }


def save_customs_rate_to_cache(data: dict) -> None:
    """関税率をキャッシュに保存（upsert）。"""
    row = CustomsRateCache.query.filter_by(search_key=data["search_key"]).first()
    if row is None:
        row = CustomsRateCache(search_key=data["search_key"])
        db.session.add(row)
    row.description = data.get("description", "")
    row.customs_rate = data["customs_rate"]
    row.consumption_tax_rate = data.get("consumption_tax_rate", 0.10)
    row.total_rate = data["total_rate"]
    row.updated_at = datetime.utcnow()
    db.session.commit()


# ── 為替レートキャッシュ ──────────────────────────────────────────────

def get_exchange_rate_from_cache(pair: str) -> float | None:
    """キャッシュから為替レートを取得。期限切れの場合はNone。"""
    row = ExchangeRateCache.query.filter_by(currency_pair=pair).first()
    if row is None:
        return None
    threshold = datetime.utcnow() - timedelta(
        minutes=CacheConfig.exchange_rate_ttl_minutes
    )
    if row.updated_at < threshold:
        return None
    return row.rate


def save_exchange_rate_to_cache(pair: str, rate: float) -> None:
    """為替レートをキャッシュに保存。"""
    row = ExchangeRateCache.query.filter_by(currency_pair=pair).first()
    if row is None:
        row = ExchangeRateCache(currency_pair=pair)
        db.session.add(row)
    row.rate = rate
    row.updated_at = datetime.utcnow()
    db.session.commit()


# ── FBA手数料設定 ─────────────────────────────────────────────────────

def get_fba_fees() -> list[dict]:
    """FBA手数料設定を返す。DBが空の場合はデフォルト値を返す。"""
    rows = FbaFeeConfig.query.order_by(FbaFeeConfig.weight_max_g).all()
    if rows:
        return [
            {
                "size_name": r.size_name,
                "weight_max_g": r.weight_max_g,
                "fee_jpy": r.fee_jpy,
            }
            for r in rows
        ]
    # デフォルト値（2024年Amazon公式参考）
    return [
        {"size_name": "小型（250g以下）", "weight_max_g": 250, "fee_jpy": 257},
        {"size_name": "標準（~500g）", "weight_max_g": 500, "fee_jpy": 385},
        {"size_name": "標準（~1kg）", "weight_max_g": 1000, "fee_jpy": 479},
        {"size_name": "標準（~1.5kg）", "weight_max_g": 1500, "fee_jpy": 561},
        {"size_name": "標準（~2kg）", "weight_max_g": 2000, "fee_jpy": 643},
        {"size_name": "標準（~3kg）", "weight_max_g": 3000, "fee_jpy": 725},
        {"size_name": "大型（~4kg）", "weight_max_g": 4000, "fee_jpy": 1287},
        {"size_name": "大型（~5kg）", "weight_max_g": 5000, "fee_jpy": 1419},
        {"size_name": "大型（~6kg）", "weight_max_g": 6000, "fee_jpy": 1551},
        {"size_name": "大型（~10kg）", "weight_max_g": 10000, "fee_jpy": 1948},
        {"size_name": "大型（10kg超）", "weight_max_g": None, "fee_jpy": 2244},
    ]
