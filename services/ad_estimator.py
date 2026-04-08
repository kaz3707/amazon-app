"""
Amazon広告費（スポンサープロダクト）の推計サービス。
ライバルの広告出稿状況・カテゴリ特性からCPC・ACOSを推計し、
商品1個あたりの広告費を算出する。
"""


# カテゴリ別の標準CPC・ACOS・CVR（コンバージョン率）参考値
# ※ Amazon Japan 2024年 業界参考値
CATEGORY_AD_BENCHMARKS = {
    "supplement":    {"cpc": 80,  "acos": 0.25, "cvr": 0.12},
    "health_food":   {"cpc": 70,  "acos": 0.25, "cvr": 0.11},
    "health":        {"cpc": 75,  "acos": 0.25, "cvr": 0.11},
    "beauty":        {"cpc": 90,  "acos": 0.28, "cvr": 0.10},
    "cosmetics":     {"cpc": 90,  "acos": 0.28, "cvr": 0.10},
    "food":          {"cpc": 50,  "acos": 0.20, "cvr": 0.13},
    "beverage":      {"cpc": 50,  "acos": 0.20, "cvr": 0.13},
    "clothing":      {"cpc": 60,  "acos": 0.30, "cvr": 0.08},
    "shoes":         {"cpc": 70,  "acos": 0.30, "cvr": 0.08},
    "bag":           {"cpc": 70,  "acos": 0.28, "cvr": 0.09},
    "electronics":   {"cpc": 100, "acos": 0.15, "cvr": 0.12},
    "mobile":        {"cpc": 120, "acos": 0.15, "cvr": 0.11},
    "pc":            {"cpc": 120, "acos": 0.14, "cvr": 0.10},
    "toys":          {"cpc": 60,  "acos": 0.22, "cvr": 0.11},
    "sports":        {"cpc": 65,  "acos": 0.22, "cvr": 0.11},
    "home":          {"cpc": 55,  "acos": 0.20, "cvr": 0.12},
    "furniture":     {"cpc": 80,  "acos": 0.20, "cvr": 0.10},
    "books":         {"cpc": 30,  "acos": 0.15, "cvr": 0.15},
    "baby":          {"cpc": 70,  "acos": 0.25, "cvr": 0.11},
    "pet":           {"cpc": 65,  "acos": 0.23, "cvr": 0.12},
    "office":        {"cpc": 60,  "acos": 0.20, "cvr": 0.12},
    "tools":         {"cpc": 70,  "acos": 0.20, "cvr": 0.11},
    "auto":          {"cpc": 80,  "acos": 0.18, "cvr": 0.10},
    "other":         {"cpc": 70,  "acos": 0.25, "cvr": 0.10},
}

# 競合強度による補正係数
COMPETITION_MULTIPLIER = {
    "very_weak": 0.6,   # レビュー10未満
    "weak":      0.8,   # レビュー10〜50
    "medium":    1.0,   # レビュー50〜200
    "strong":    1.3,   # レビュー200〜1000
    "very_strong": 1.6, # レビュー1000以上
}


def estimate_ad_cost(
    selling_price: float,
    category_key: str,
    avg_competitor_reviews: float,
    sponsored_ad_ratio: float = 0.5,  # 広告掲載率（0〜1）
) -> dict:
    """
    広告費用を推計して1個あたりのコストを返す。

    Args:
        selling_price: 販売価格（円）
        category_key: カテゴリキー（例: "supplement"）
        avg_competitor_reviews: ライバルの平均レビュー数
        sponsored_ad_ratio: 検索結果での広告占有率（0〜1）

    Returns:
        {
            "estimated_cpc": float,       # 推計CPC（円/クリック）
            "estimated_cvr": float,       # 推計CVR（コンバージョン率）
            "estimated_acos": float,      # 推計ACOS
            "ad_cost_per_unit": float,    # 1個あたり広告費（円）
            "competition_level": str,     # 競合強度
            "ad_cost_rate": float,        # 広告費率（対販売価格）
            "note": str,
        }
    """
    benchmark = CATEGORY_AD_BENCHMARKS.get(category_key, CATEGORY_AD_BENCHMARKS["other"])

    # 競合強度の判定
    competition_level, comp_key = _classify_competition(avg_competitor_reviews)
    comp_mult = COMPETITION_MULTIPLIER[comp_key]

    # 広告掲載率による補正（広告が多いほどCPC上昇）
    ad_ratio_mult = 0.8 + sponsored_ad_ratio * 0.6  # 0.8〜1.4倍

    # CPC推計
    estimated_cpc = benchmark["cpc"] * comp_mult * ad_ratio_mult

    # CVR（コンバージョン率）推計
    # 新規セラー・レビューが少ない商品はCVR低め
    cvr_mult = 0.7 if avg_competitor_reviews < 20 else 1.0
    estimated_cvr = benchmark["cvr"] * cvr_mult

    # 1個販売するのに必要なクリック数
    clicks_per_sale = 1 / estimated_cvr if estimated_cvr > 0 else 10

    # 1個あたり広告費
    ad_cost_per_unit = estimated_cpc * clicks_per_sale

    # ACOS
    acos = ad_cost_per_unit / selling_price if selling_price > 0 else 0

    return {
        "estimated_cpc": round(estimated_cpc, 0),
        "estimated_cvr": round(estimated_cvr * 100, 1),   # %表示
        "estimated_acos": round(acos * 100, 1),           # %表示
        "ad_cost_per_unit": round(ad_cost_per_unit, 0),
        "competition_level": competition_level,
        "ad_cost_rate": round(acos * 100, 1),
        "note": f"カテゴリ標準CPC ¥{benchmark['cpc']} × 競合係数 {comp_mult}",
    }


def _classify_competition(avg_reviews: float) -> tuple[str, str]:
    """ライバルの平均レビュー数から競合強度を分類する。"""
    if avg_reviews < 10:
        return "非常に弱い", "very_weak"
    elif avg_reviews < 50:
        return "弱い", "weak"
    elif avg_reviews < 200:
        return "普通", "medium"
    elif avg_reviews < 1000:
        return "強い", "strong"
    else:
        return "非常に強い", "very_strong"


def estimate_monthly_sales_from_bsr(bsr: int, category_key: str) -> int:
    """
    BSR（ベストセラーランキング）から月間販売数を推計する。
    Amazon Japanの実績データに基づく経験則。
    """
    # カテゴリ別の基準係数
    base = {
        "electronics": 15000, "mobile": 12000, "pc": 8000,
        "books": 25000, "music": 5000, "video": 5000, "video_games": 8000,
        "toys": 6000, "sports": 5000, "home": 6000, "tools": 4000,
        "clothing": 8000, "shoes": 6000, "bag": 5000,
        "health": 7000, "beauty": 8000, "cosmetics": 8000,
        "supplement": 7000, "health_food": 6000, "food": 10000,
        "baby": 5000, "pet": 5000, "other": 5000,
    }.get(category_key, 5000)

    if bsr <= 0:
        return 0

    import math
    estimated = int(base * (bsr ** -0.75))
    return max(1, estimated)
