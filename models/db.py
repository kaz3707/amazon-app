from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class AmazonFeeCache(db.Model):
    __tablename__ = "amazon_fee_cache"
    id = db.Column(db.Integer, primary_key=True)
    category_key = db.Column(db.String(200), unique=True, nullable=False)
    category_name = db.Column(db.String(200), nullable=False)
    fee_rate = db.Column(db.Float, nullable=False)       # 例: 0.10 = 10%
    min_fee = db.Column(db.Float, nullable=True)         # 最低手数料（円）
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FbaFeeConfig(db.Model):
    __tablename__ = "fba_fee_config"
    id = db.Column(db.Integer, primary_key=True)
    size_name = db.Column(db.String(100), nullable=False)   # 例: 小型, 標準1, 標準2
    weight_max_g = db.Column(db.Float, nullable=True)       # NULL=無制限
    fee_jpy = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomsRateCache(db.Model):
    __tablename__ = "customs_rate_cache"
    id = db.Column(db.Integer, primary_key=True)
    search_key = db.Column(db.String(200), unique=True, nullable=False)   # HSコード or カテゴリ名
    description = db.Column(db.String(500), nullable=True)
    customs_rate = db.Column(db.Float, nullable=False)      # 関税率 例: 0.05 = 5%
    consumption_tax_rate = db.Column(db.Float, default=0.10)  # 消費税率（固定10%）
    total_rate = db.Column(db.Float, nullable=False)        # 合計税率
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ExchangeRateCache(db.Model):
    __tablename__ = "exchange_rate_cache"
    id = db.Column(db.Integer, primary_key=True)
    currency_pair = db.Column(db.String(10), unique=True, nullable=False)  # 例: CNY_JPY
    rate = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalculationHistory(db.Model):
    __tablename__ = "calculation_history"
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(300), nullable=True)
    product_url_1688 = db.Column(db.String(500), nullable=True)
    platform = db.Column(db.String(50), nullable=False)     # amazon / sale_monster
    selling_price = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float, nullable=False)
    profit_rate = db.Column(db.Float, nullable=False)
    detail_json = db.Column(db.Text, nullable=True)         # 全明細をJSONで保存
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
