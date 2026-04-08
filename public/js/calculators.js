/**
 * 計算ロジック（Python services からの移植）
 * 依存: constants.js が先に読み込まれていること
 */

// ──────────────────────────────────────────
// FBA手数料計算（shipping_calculator.py より）
// ──────────────────────────────────────────

function classifyFbaSize(lengthCm, widthCm, heightCm, weightG) {
  const sides = [lengthCm, widthCm, heightCm].sort((a, b) => b - a);
  const [l, w, h] = sides;
  if (l <= 35 && w <= 25 && h <= 12 && weightG <= 9000) return "small";
  if (l > 45 || (l + 2 * (w + h)) > 130 || weightG > 9000) return "large";
  return "standard";
}

function calculateFbaFee(lengthCm, widthCm, heightCm, weightG) {
  const sizeClass = classifyFbaSize(lengthCm, widthCm, heightCm, weightG);
  let label, fee;

  if (sizeClass === "small") {
    label = "小型";
    if (weightG <= 300) fee = 257;
    else if (weightG <= 400) fee = 281;
    else if (weightG <= 500) fee = 290;
    else if (weightG <= 600) fee = 300;
    else if (weightG <= 700) fee = 309;
    else if (weightG <= 800) fee = 318;
    else if (weightG <= 900) fee = 328;
    else if (weightG <= 1000) fee = 337;
    else fee = 337 + (Math.floor((weightG - 1000) / 500) + 1) * 37;
  } else if (sizeClass === "standard") {
    label = "通常";
    if (weightG <= 250) fee = 385;
    else if (weightG <= 500) fee = 425;
    else if (weightG <= 750) fee = 465;
    else if (weightG <= 1000) fee = 505;
    else if (weightG <= 1250) fee = 530;
    else if (weightG <= 1500) fee = 555;
    else if (weightG <= 1750) fee = 580;
    else if (weightG <= 2000) fee = 605;
    else if (weightG <= 2500) fee = 655;
    else if (weightG <= 3000) fee = 705;
    else fee = 705 + (Math.floor((weightG - 3000) / 500) + 1) * 50;
  } else {
    label = "大型";
    if (weightG <= 1000) fee = 934;
    else if (weightG <= 2000) fee = 1020;
    else if (weightG <= 3000) fee = 1107;
    else if (weightG <= 4000) fee = 1193;
    else if (weightG <= 5000) fee = 1280;
    else if (weightG <= 6000) fee = 1366;
    else if (weightG <= 7000) fee = 1453;
    else if (weightG <= 8000) fee = 1539;
    else if (weightG <= 9000) fee = 1626;
    else fee = 1626 + (Math.floor((weightG - 9000) / 1000) + 1) * 100;
  }

  return { size_class: sizeClass, size_label: label, fee_jpy: fee };
}

// ──────────────────────────────────────────
// 国際送料計算（快速船便）
// ──────────────────────────────────────────

function calculateInternationalShipping(lengthCm, widthCm, heightCm, weightG, quantity = 1, method = "fast_sea") {
  const packedL = lengthCm * PACKING_FACTOR;
  const packedW = widthCm * PACKING_FACTOR;
  const packedH = heightCm * PACKING_FACTOR;
  const volumeCm3 = packedL * packedW * packedH;

  let volumetricKg, rate;
  if (method === "air") {
    volumetricKg = volumeCm3 / 5000;
    rate = AIR_RATE_PER_KG;
  } else {
    volumetricKg = volumeCm3 / VOLUMETRIC_DIVISOR_FAST_SEA;
    rate = FAST_SEA_RATE_PER_KG;
  }

  const actualKg = (weightG / 1000) * PACKING_FACTOR;
  const chargeableKg = Math.max(actualKg, volumetricKg);
  const total = Math.max(chargeableKg * rate * quantity, MINIMUM_SHIPPING_CHARGE);
  const perUnit = quantity > 0 ? total / quantity : total;

  return {
    actual_weight_kg: Math.round(actualKg * 1000) / 1000,
    volumetric_weight_kg: Math.round(volumetricKg * 1000) / 1000,
    chargeable_weight_kg: Math.round(chargeableKg * 1000) / 1000,
    total_shipping_jpy: Math.round(total),
    per_unit_jpy: Math.round(perUnit),
    method: method === "air" ? "航空便" : "快速船便",
    rate_per_kg: rate,
  };
}

// ──────────────────────────────────────────
// 国際送料計算（コンテナ便 LCL）
// ──────────────────────────────────────────

function calculateContainerShipping(lengthCm, widthCm, heightCm, weightG, quantity = 1) {
  const packedL = lengthCm * PACKING_FACTOR;
  const packedW = widthCm * PACKING_FACTOR;
  const packedH = heightCm * PACKING_FACTOR;
  const cbmPerUnit = (packedL * packedW * packedH) / 1_000_000;
  const totalCbm = cbmPerUnit * quantity;

  let rate = CONTAINER_LCL_RATES[CONTAINER_LCL_RATES.length - 1][1];
  for (const [maxCbm, r] of CONTAINER_LCL_RATES) {
    if (totalCbm <= maxCbm) { rate = r; break; }
  }

  const total = cbmPerUnit * rate * quantity;
  const perUnit = quantity > 0 ? total / quantity : total;

  return {
    cbm_per_unit: Math.round(cbmPerUnit * 100000) / 100000,
    total_cbm: Math.round(totalCbm * 1000) / 1000,
    rate_per_cbm: rate,
    total_shipping_jpy: Math.round(total),
    per_unit_jpy: Math.round(perUnit),
    method: "コンテナ便（LCL）",
    chargeable_weight_kg: null,
    rate_per_kg: null,
  };
}

// ──────────────────────────────────────────
// 佐川急便BtoC（国内→FBA倉庫）
// ──────────────────────────────────────────

function calculateSagawaBtoC(lengthCm, widthCm, heightCm) {
  const packedL = lengthCm * PACKING_FACTOR;
  const packedW = widthCm * PACKING_FACTOR;
  const packedH = heightCm * PACKING_FACTOR;
  const threeSum = packedL + packedW + packedH;

  for (const [maxSize, fee] of SAGAWA_BTOC_RATES) {
    if (threeSum <= maxSize) {
      return { three_sides_sum_cm: Math.round(threeSum * 10) / 10, size_label: `${maxSize}サイズ`, fee_jpy: fee };
    }
  }
  return { three_sides_sum_cm: Math.round(threeSum * 10) / 10, size_label: "260超（要確認）", fee_jpy: 5190 };
}

// ──────────────────────────────────────────
// 関税率取得
// ──────────────────────────────────────────

function getCustomsRate(searchKey) {
  const master = CUSTOMS_MASTER[searchKey];
  if (master) {
    return {
      search_key: searchKey,
      description: master.desc,
      customs_rate: master.rate,
      consumption_tax_rate: CONSUMPTION_TAX_RATE,
      total_rate: Math.round((master.rate + CONSUMPTION_TAX_RATE) * 10000) / 10000,
    };
  }
  const fallback = CUSTOMS_MASTER.other;
  return {
    search_key: searchKey,
    description: fallback.desc,
    customs_rate: fallback.rate,
    consumption_tax_rate: CONSUMPTION_TAX_RATE,
    total_rate: Math.round((fallback.rate + CONSUMPTION_TAX_RATE) * 10000) / 10000,
  };
}

// ──────────────────────────────────────────
// 総合利益計算（routes/api_research.py の /analyze ロジック移植）
// ──────────────────────────────────────────

function calculateFullProfit(params) {
  const {
    amazon_price,
    amazon_category_key = "other",
    estimated_monthly_sales = 0,
    dimensions = {},
    purchase_price_cny,
    exchange_rate,
    order_quantity = 100,
    shipping_method = "fast_sea",
    inspection_fee_per_unit = 30,
    fba_domestic_shipping_per_unit = 0,
    intl_shipping_override = null,
    customs_category = "other",
    agent_fee_jpy = 0,
    domestic_shipping_jpy = 0,
    total_acos = 0.20,
  } = params;

  // 為替換算
  const purchasePriceJpy = purchase_price_cny * exchange_rate;

  // 寸法
  const l = parseFloat(dimensions.length) || 10;
  const w = parseFloat(dimensions.width) || 10;
  const h = parseFloat(dimensions.height) || 10;
  const weightG = parseFloat(dimensions.weight_g) || 200;

  // FBA手数料
  const fba = calculateFbaFee(l, w, h, weightG);
  const fbaFee = fba.fee_jpy;

  // 国際送料
  let intlShippingPerUnit, shippingDetail;
  let fbaDomesticShipping = fba_domestic_shipping_per_unit;

  if (shipping_method === "container_fba_direct") {
    const shipping = calculateContainerShipping(l, w, h, weightG, order_quantity);
    intlShippingPerUnit = intl_shipping_override != null ? intl_shipping_override : shipping.per_unit_jpy;

    const sagawa = calculateSagawaBtoC(l, w, h);
    if (fbaDomesticShipping <= 0) fbaDomesticShipping = sagawa.fee_jpy;

    shippingDetail = {
      method: shipping.method,
      cbm_per_unit: shipping.cbm_per_unit,
      total_cbm: shipping.total_cbm,
      rate_per_cbm: shipping.rate_per_cbm,
      total_shipping_jpy: shipping.total_shipping_jpy,
      chargeable_weight_kg: null,
      rate_per_kg: null,
      fba_domestic_method: `佐川急便BtoC ${sagawa.size_label}`,
    };
  } else {
    const shipping = calculateInternationalShipping(l, w, h, weightG, order_quantity, "fast_sea");
    intlShippingPerUnit = intl_shipping_override != null ? intl_shipping_override : shipping.per_unit_jpy;

    shippingDetail = {
      method: shipping.method,
      chargeable_weight_kg: shipping.chargeable_weight_kg,
      rate_per_kg: shipping.rate_per_kg,
      total_shipping_jpy: shipping.total_shipping_jpy,
      cbm_per_unit: null,
      total_cbm: null,
      fba_domestic_method: "ヤマトパートナーキャリア 140サイズ",
    };
  }

  // Amazon紹介手数料
  const feeData = AMAZON_FEES.find(f => f.key === amazon_category_key) || AMAZON_FEES[AMAZON_FEES.length - 1];
  const referralRate = feeData.fee_rate;
  const referralFee = Math.max(amazon_price * referralRate, feeData.min_fee || 0);

  // 関税・消費税
  const customsData = getCustomsRate(customs_category);
  const customsTotalRate = customsData.total_rate;
  const customsAmount = purchasePriceJpy * customsTotalRate;

  // 総コスト（広告費前）
  const totalCostBeforeAd = purchasePriceJpy + agent_fee_jpy + domestic_shipping_jpy
    + intlShippingPerUnit + customsAmount + inspection_fee_per_unit
    + fbaDomesticShipping + referralFee + fbaFee;

  // 広告費前利益
  const profitBeforeAd = amazon_price - totalCostBeforeAd;
  const profitRateBeforeAd = amazon_price > 0 ? (profitBeforeAd / amazon_price * 100) : 0;

  // 広告費
  const adCostPerUnit = amazon_price * total_acos;

  // 純利益
  const netProfit = profitBeforeAd - adCostPerUnit;
  const netProfitRate = amazon_price > 0 ? (netProfit / amazon_price * 100) : 0;

  // ROI
  const roi = purchasePriceJpy > 0 ? (netProfit / purchasePriceJpy * 100) : 0;

  // 月間純利益
  const monthlyNetProfit = netProfit * estimated_monthly_sales;

  return {
    amazon_price,
    purchase_price_cny,
    purchase_price_jpy: Math.round(purchasePriceJpy),
    exchange_rate: Math.round(exchange_rate * 100) / 100,
    order_quantity,

    costs: {
      purchase_price_jpy: Math.round(purchasePriceJpy),
      agent_fee_jpy: Math.round(agent_fee_jpy),
      domestic_shipping_jpy: Math.round(domestic_shipping_jpy),
      intl_shipping_per_unit: Math.round(intlShippingPerUnit),
      customs_amount: Math.round(customsAmount),
      customs_rate_pct: Math.round(customsTotalRate * 1000) / 10,
      inspection_fee: Math.round(inspection_fee_per_unit),
      fba_domestic_shipping: Math.round(fbaDomesticShipping),
      referral_fee: Math.round(referralFee),
      referral_rate_pct: Math.round(referralRate * 1000) / 10,
      fba_fee: Math.round(fbaFee),
      fba_size: fba.size_label,
      total_before_ad: Math.round(totalCostBeforeAd),
    },

    profit_before_ad: Math.round(profitBeforeAd),
    profit_rate_before_ad: Math.round(profitRateBeforeAd * 10) / 10,

    ad_info: {
      total_acos_pct: Math.round(total_acos * 1000) / 10,
      ad_cost_per_unit: Math.round(adCostPerUnit),
    },

    net_profit: Math.round(netProfit),
    net_profit_rate: Math.round(netProfitRate * 10) / 10,
    roi: Math.round(roi * 10) / 10,

    monthly: {
      estimated_sales: estimated_monthly_sales,
      net_profit: Math.round(monthlyNetProfit),
    },

    shipping_detail: shippingDetail,
  };
}
