"""
利益計算コアロジック。外部依存なしの純粋関数として実装。
"""
from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class CostInput:
    # 仕入れ
    purchase_price_jpy: float           # 仕入れ単価（円）

    # 輸送・税
    international_shipping_per_unit: float  # 国際送料/個（円）
    customs_rate: float                     # 関税・消費税合計率 例: 0.13

    # 国内費用
    inspection_fee_per_unit: float = 0.0   # 検品費用/個（円）
    other_cost_per_unit: float = 0.0       # その他費用/個（円）

    # 販売
    platform: Literal["amazon", "sale_monster"] = "amazon"
    selling_price: float = 0.0

    # Amazon専用
    amazon_referral_rate: float = 0.10     # 紹介手数料率
    amazon_referral_min_fee: float = 0.0   # 最低手数料（円）
    fba_fee: float = 0.0                   # FBA配送手数料（円）

    # セールモンスター専用
    sm_ad_rate: float = 0.20               # 広告費率（固定20%）
    sm_shipping_fee: float = 0.0           # セルモン送料/個（円）
    sm_storage_fee: float = 0.0            # セルモン倉庫費/個（円）


@dataclass
class CostBreakdown:
    purchase_price_jpy: float
    international_shipping: float
    customs_and_tax: float
    inspection_fee: float
    other_cost: float
    platform_fee: float
    platform_fee_detail: dict = field(default_factory=dict)
    total_cost: float = 0.0
    selling_price: float = 0.0
    profit: float = 0.0
    profit_rate: float = 0.0             # 利益率（%）
    break_even_price: float = 0.0        # 損益分岐販売価格（円）


def calculate_profit(inp: CostInput) -> CostBreakdown:
    """利益を計算して CostBreakdown を返す。"""

    # 関税・消費税（仕入れ単価ベース）
    customs_and_tax = inp.purchase_price_jpy * inp.customs_rate

    # プラットフォーム手数料
    if inp.platform == "amazon":
        referral = max(
            inp.selling_price * inp.amazon_referral_rate,
            inp.amazon_referral_min_fee,
        )
        platform_fee = referral + inp.fba_fee
        platform_detail = {
            "紹介手数料": round(referral, 2),
            "FBA手数料": round(inp.fba_fee, 2),
        }
    else:  # sale_monster
        ad_fee = inp.selling_price * inp.sm_ad_rate
        platform_fee = ad_fee + inp.sm_shipping_fee + inp.sm_storage_fee
        platform_detail = {
            "広告費(20%)": round(ad_fee, 2),
            "セルモン送料": round(inp.sm_shipping_fee, 2),
            "倉庫保管費": round(inp.sm_storage_fee, 2),
        }

    total_cost = (
        inp.purchase_price_jpy
        + inp.international_shipping_per_unit
        + customs_and_tax
        + inp.inspection_fee_per_unit
        + inp.other_cost_per_unit
        + platform_fee
    )

    profit = inp.selling_price - total_cost
    profit_rate = (profit / inp.selling_price * 100) if inp.selling_price > 0 else 0.0

    # 損益分岐価格（プラットフォーム手数料が販売価格依存のため逆算）
    # selling_price = fixed_cost + selling_price * variable_rate
    # → selling_price * (1 - variable_rate) = fixed_cost
    fixed_cost = (
        inp.purchase_price_jpy
        + inp.international_shipping_per_unit
        + customs_and_tax
        + inp.inspection_fee_per_unit
        + inp.other_cost_per_unit
    )
    if inp.platform == "amazon":
        variable_rate = inp.amazon_referral_rate
        fixed_platform = inp.fba_fee
    else:
        variable_rate = inp.sm_ad_rate
        fixed_platform = inp.sm_shipping_fee + inp.sm_storage_fee

    denominator = 1 - variable_rate
    if denominator > 0:
        break_even = (fixed_cost + fixed_platform) / denominator
    else:
        break_even = 0.0

    return CostBreakdown(
        purchase_price_jpy=round(inp.purchase_price_jpy, 2),
        international_shipping=round(inp.international_shipping_per_unit, 2),
        customs_and_tax=round(customs_and_tax, 2),
        inspection_fee=round(inp.inspection_fee_per_unit, 2),
        other_cost=round(inp.other_cost_per_unit, 2),
        platform_fee=round(platform_fee, 2),
        platform_fee_detail=platform_detail,
        total_cost=round(total_cost, 2),
        selling_price=round(inp.selling_price, 2),
        profit=round(profit, 2),
        profit_rate=round(profit_rate, 2),
        break_even_price=round(break_even, 2),
    )


def breakdown_to_dict(bd: CostBreakdown) -> dict:
    return asdict(bd)
