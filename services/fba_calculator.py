"""
FBA手数料計算。重量とサイズ区分からFBA配送手数料を返す。
"""
from utils.cache_manager import get_fba_fees


def calculate_fba_fee(weight_g: float) -> dict:
    """
    重量(g)からFBA配送手数料を計算する。
    Returns:
        {"size_name": str, "fee_jpy": float}
    """
    fees = get_fba_fees()
    # weight_max_g昇順にソート済みであることを前提
    for tier in fees:
        if tier["weight_max_g"] is None or weight_g <= tier["weight_max_g"]:
            return {"size_name": tier["size_name"], "fee_jpy": tier["fee_jpy"]}
    # 見つからなければ最大区分
    last = fees[-1]
    return {"size_name": last["size_name"], "fee_jpy": last["fee_jpy"]}


def get_all_tiers() -> list[dict]:
    """FBA手数料の全区分を返す（UI用）。"""
    return get_fba_fees()
