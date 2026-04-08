"""
FBA送料・国際送料の計算サービス。
商品の縦横高さ・重量から各種送料を算出する。
"""


# ──────────────────────────────────────────
# FBA手数料（Amazon Japan 2024年版）
# ──────────────────────────────────────────

def classify_fba_size(length_cm: float, width_cm: float, height_cm: float, weight_g: float) -> str:
    """
    Amazon Japanのサイズ区分を返す。
    （3辺を大きい順に並べてから判定）
    """
    sides = sorted([length_cm, width_cm, height_cm], reverse=True)
    l, w, h = sides

    # 小型サイズ条件
    if (l <= 35 and w <= 25 and h <= 12 and weight_g <= 9000):
        return "small"
    # 大型サイズ（それ以外）
    if (l > 45 or (l + 2 * (w + h)) > 130 or weight_g > 9000):
        return "large"
    return "standard"


def calculate_fba_fee_from_dimensions(
    length_cm: float, width_cm: float, height_cm: float, weight_g: float
) -> dict:
    """
    商品寸法・重量からFBA手数料を算出する。

    Returns:
        {"size_class": str, "size_label": str, "fee_jpy": float}
    """
    size_class = classify_fba_size(length_cm, width_cm, height_cm, weight_g)

    if size_class == "small":
        label = "小型"
        if weight_g <= 100:   fee = 257
        elif weight_g <= 200: fee = 257
        elif weight_g <= 300: fee = 257
        elif weight_g <= 400: fee = 281
        elif weight_g <= 500: fee = 290
        elif weight_g <= 600: fee = 300
        elif weight_g <= 700: fee = 309
        elif weight_g <= 800: fee = 318
        elif weight_g <= 900: fee = 328
        elif weight_g <= 1000: fee = 337
        else: fee = 337 + ((weight_g - 1000) // 500 + 1) * 37

    elif size_class == "standard":
        label = "通常"
        if weight_g <= 250:   fee = 385
        elif weight_g <= 500: fee = 425
        elif weight_g <= 750: fee = 465
        elif weight_g <= 1000: fee = 505
        elif weight_g <= 1250: fee = 530
        elif weight_g <= 1500: fee = 555
        elif weight_g <= 1750: fee = 580
        elif weight_g <= 2000: fee = 605
        elif weight_g <= 2500: fee = 655
        elif weight_g <= 3000: fee = 705
        else: fee = 705 + ((weight_g - 3000) // 500 + 1) * 50

    else:  # large
        label = "大型"
        if weight_g <= 1000:  fee = 934
        elif weight_g <= 2000: fee = 1020
        elif weight_g <= 3000: fee = 1107
        elif weight_g <= 4000: fee = 1193
        elif weight_g <= 5000: fee = 1280
        elif weight_g <= 6000: fee = 1366
        elif weight_g <= 7000: fee = 1453
        elif weight_g <= 8000: fee = 1539
        elif weight_g <= 9000: fee = 1626
        else: fee = 1626 + ((weight_g - 9000) // 1000 + 1) * 100

    return {"size_class": size_class, "size_label": label, "fee_jpy": fee}


# ──────────────────────────────────────────
# 国際送料（中国→日本 快速船便）
# ──────────────────────────────────────────

# 梱包係数（商品+ダンボール+緩衝材の概算）
PACKING_FACTOR = 1.2   # 商品寸法の20%増し

# 重量換算係数（容積重量）
# 快速船便（航空+海上混載）: 1kg = 6000cm³
VOLUMETRIC_DIVISOR_FAST_SEA = 6000

# 料金（円/kg）※ 猫の手/セラーバンク系の一般的な相場（2024年）
FAST_SEA_RATE_PER_KG = 250   # 快速船便
AIR_RATE_PER_KG = 800        # 航空便
MINIMUM_CHARGE = 500         # 最低料金（円）


def calculate_international_shipping(
    length_cm: float, width_cm: float, height_cm: float,
    weight_g: float, quantity: int = 1,
    method: str = "fast_sea"
) -> dict:
    """
    商品寸法・重量から国際送料（中国→日本）を計算する。

    Args:
        length_cm, width_cm, height_cm: 商品寸法（cm）
        weight_g: 商品重量（g）
        quantity: 梱包数（ダンボール1箱に何個入るか）
        method: "fast_sea"（快速船便）or "air"（航空便）

    Returns:
        {
            "actual_weight_kg": float,
            "volumetric_weight_kg": float,
            "chargeable_weight_kg": float,
            "total_shipping_jpy": float,
            "per_unit_jpy": float,
            "method": str,
        }
    """
    # 梱包後の寸法（係数適用）
    packed_l = length_cm * PACKING_FACTOR
    packed_w = width_cm * PACKING_FACTOR
    packed_h = height_cm * PACKING_FACTOR

    # 容積重量（kg）
    volume_cm3 = packed_l * packed_w * packed_h
    if method == "air":
        volumetric_kg = volume_cm3 / 5000
        rate = AIR_RATE_PER_KG
    else:
        volumetric_kg = volume_cm3 / VOLUMETRIC_DIVISOR_FAST_SEA
        rate = FAST_SEA_RATE_PER_KG

    # 実重量（kg）
    actual_kg = weight_g / 1000 * PACKING_FACTOR

    # 課金重量 = max(実重量, 容積重量)
    chargeable_kg = max(actual_kg, volumetric_kg)

    # 合計送料
    total = max(chargeable_kg * rate * quantity, MINIMUM_CHARGE)
    per_unit = total / quantity if quantity > 0 else total

    method_label = "快速船便" if method == "fast_sea" else "航空便"
    return {
        "actual_weight_kg": round(actual_kg, 3),
        "volumetric_weight_kg": round(volumetric_kg, 3),
        "chargeable_weight_kg": round(chargeable_kg, 3),
        "total_shipping_jpy": round(total, 0),
        "per_unit_jpy": round(per_unit, 0),
        "method": method_label,
        "rate_per_kg": rate,
    }


# ──────────────────────────────────────────
# 国際送料（コンテナ便 LCL）
# ──────────────────────────────────────────

# CBMあたり料金（LCL / 弊社概算）
# (最大CBM, 円/m³)
CONTAINER_LCL_RATES = [
    (2,           20_000),   # 0〜2㎥
    (20,          14_000),   # 2〜20㎥
    (float("inf"), 12_500),  # 20㎥超
]


def calculate_container_shipping(
    length_cm: float, width_cm: float, height_cm: float,
    weight_g: float, quantity: int = 1
) -> dict:
    """
    コンテナ便（LCL）の国際送料（中国→日本）を計算する。
    梱包係数を適用した容積（m³）× CBM単価で算出。

    Returns:
        {
            "cbm_per_unit": float,
            "total_cbm": float,
            "rate_per_cbm": int,
            "total_shipping_jpy": float,
            "per_unit_jpy": float,
            "method": str,
            "chargeable_weight_kg": None,
            "rate_per_kg": None,
        }
    """
    packed_l = length_cm * PACKING_FACTOR
    packed_w = width_cm * PACKING_FACTOR
    packed_h = height_cm * PACKING_FACTOR
    cbm_per_unit = packed_l * packed_w * packed_h / 1_000_000  # cm³ → m³

    total_cbm = cbm_per_unit * quantity

    rate = CONTAINER_LCL_RATES[-1][1]
    for max_cbm, r in CONTAINER_LCL_RATES:
        if total_cbm <= max_cbm:
            rate = r
            break

    total = cbm_per_unit * rate * quantity
    per_unit = total / quantity if quantity > 0 else total

    return {
        "cbm_per_unit": round(cbm_per_unit, 5),
        "total_cbm": round(total_cbm, 3),
        "rate_per_cbm": rate,
        "total_shipping_jpy": round(total, 0),
        "per_unit_jpy": round(per_unit, 0),
        "method": "コンテナ便（LCL）",
        "chargeable_weight_kg": None,
        "rate_per_kg": None,
    }


# ──────────────────────────────────────────
# 国内送料（佐川急便 BtoC / 弊社概算）
# ──────────────────────────────────────────

# (3辺合計上限cm, 円/個)
SAGAWA_BTOC_RATES = [
    (60,  570),
    (80,  630),
    (100, 690),
    (140, 950),
    (160, 1_180),
    (170, 1_880),
    (180, 2_190),
    (200, 2_690),
    (220, 3_190),
    (240, 4_190),
    (260, 5_190),
]


def calculate_sagawa_btoc(
    length_cm: float, width_cm: float, height_cm: float
) -> dict:
    """
    佐川急便BtoC料金（国内→FBA倉庫）を計算する。
    梱包後の3辺合計でサイズ区分を決定。

    Returns:
        {
            "three_sides_sum_cm": float,
            "size_label": str,
            "fee_jpy": int,
        }
    """
    packed_l = length_cm * PACKING_FACTOR
    packed_w = width_cm * PACKING_FACTOR
    packed_h = height_cm * PACKING_FACTOR
    three_sum = packed_l + packed_w + packed_h

    for max_size, fee in SAGAWA_BTOC_RATES:
        if three_sum <= max_size:
            return {
                "three_sides_sum_cm": round(three_sum, 1),
                "size_label": f"{max_size}サイズ",
                "fee_jpy": fee,
            }

    # 260cm超（最大サイズで対応）
    return {
        "three_sides_sum_cm": round(three_sum, 1),
        "size_label": "260超（要確認）",
        "fee_jpy": 5_190,
    }
