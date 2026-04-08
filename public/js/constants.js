/**
 * 静的マスタデータ（Python services からの移植）
 */

// ──────────────────────────────────────────
// Amazonカテゴリ別販売手数料（FALLBACK_FEES）
// ──────────────────────────────────────────
const AMAZON_FEES = [
  { key: "electronics", name: "家電", fee_rate: 0.08, min_fee: 30 },
  { key: "pc", name: "パソコン・周辺機器", fee_rate: 0.08, min_fee: 30 },
  { key: "camera", name: "カメラ", fee_rate: 0.08, min_fee: 30 },
  { key: "mobile", name: "スマートフォン・携帯電話", fee_rate: 0.08, min_fee: 30 },
  { key: "books", name: "本", fee_rate: 0.15, min_fee: null },
  { key: "music", name: "音楽", fee_rate: 0.15, min_fee: null },
  { key: "video", name: "DVD・ビデオ", fee_rate: 0.15, min_fee: null },
  { key: "software", name: "ソフトウェア", fee_rate: 0.15, min_fee: null },
  { key: "video_games", name: "TVゲーム", fee_rate: 0.15, min_fee: null },
  { key: "clothing", name: "服&ファッション小物", fee_rate: 0.15, min_fee: null },
  { key: "shoes", name: "シューズ&バッグ", fee_rate: 0.15, min_fee: null },
  { key: "watches", name: "時計", fee_rate: 0.15, min_fee: null },
  { key: "jewelry", name: "ジュエリー", fee_rate: 0.20, min_fee: null },
  { key: "sports", name: "スポーツ&アウトドア", fee_rate: 0.10, min_fee: null },
  { key: "baby", name: "ベビー&マタニティ", fee_rate: 0.10, min_fee: null },
  { key: "toys", name: "おもちゃ", fee_rate: 0.10, min_fee: null },
  { key: "health", name: "ヘルス&ビューティー", fee_rate: 0.10, min_fee: null },
  { key: "beauty", name: "コスメ・ヘルス・介護用品", fee_rate: 0.10, min_fee: null },
  { key: "supplement", name: "サプリメント・栄養補助食品", fee_rate: 0.10, min_fee: null },
  { key: "food", name: "食品&飲料", fee_rate: 0.10, min_fee: null },
  { key: "pet", name: "ペット用品", fee_rate: 0.10, min_fee: null },
  { key: "home", name: "ホーム&キッチン", fee_rate: 0.10, min_fee: null },
  { key: "tools", name: "DIY・工具・ガーデン", fee_rate: 0.12, min_fee: null },
  { key: "auto", name: "車&バイク", fee_rate: 0.10, min_fee: null },
  { key: "office", name: "文房具・オフィス用品", fee_rate: 0.15, min_fee: null },
  { key: "stationery", name: "楽器", fee_rate: 0.15, min_fee: null },
  { key: "other", name: "その他", fee_rate: 0.15, min_fee: 30 },
];

// ──────────────────────────────────────────
// 関税マスタ（CUSTOMS_MASTER）
// ──────────────────────────────────────────
const CONSUMPTION_TAX_RATE = 0.10;

const CUSTOMS_MASTER = {
  supplement:   { rate: 0.0,   desc: "栄養補助食品・サプリメント（HSコード2106等）" },
  health_food:  { rate: 0.0,   desc: "健康食品（HSコード2106等）" },
  food_general: { rate: 0.09,  desc: "食品一般" },
  confectionery:{ rate: 0.21,  desc: "菓子類（チョコレート等）" },
  beverage:     { rate: 0.0,   desc: "飲料" },
  clothing:     { rate: 0.107, desc: "衣類・繊維製品（HSコード61-62章）" },
  shoes:        { rate: 0.30,  desc: "靴（HSコード64章）" },
  bag:          { rate: 0.10,  desc: "バッグ・かばん（HSコード42章）" },
  electronics:  { rate: 0.0,   desc: "電子機器・家電（HSコード85章）" },
  toys:         { rate: 0.0,   desc: "玩具（HSコード95章）" },
  sports:       { rate: 0.0,   desc: "スポーツ用品（HSコード95章）" },
  cosmetics:    { rate: 0.0,   desc: "化粧品（HSコード33章）" },
  furniture:    { rate: 0.0,   desc: "家具（HSコード94章）" },
  jewelry:      { rate: 0.056, desc: "宝石・貴金属（HSコード71章）" },
  books:        { rate: 0.0,   desc: "書籍・印刷物（HSコード49章）" },
  auto_parts:   { rate: 0.0,   desc: "自動車部品（HSコード87章）" },
  other:        { rate: 0.044, desc: "その他一般品（平均関税率）" },
};

// 関税カテゴリ一覧（UI用）
const CUSTOMS_CATEGORIES = Object.entries(CUSTOMS_MASTER).map(([key, v]) => ({
  key,
  description: v.desc,
  customs_rate: v.rate,
  consumption_tax_rate: CONSUMPTION_TAX_RATE,
  total_rate: Math.round((v.rate + CONSUMPTION_TAX_RATE) * 10000) / 10000,
}));

// ──────────────────────────────────────────
// 国際送料定数
// ──────────────────────────────────────────
const PACKING_FACTOR = 1.2;
const VOLUMETRIC_DIVISOR_FAST_SEA = 6000;
const FAST_SEA_RATE_PER_KG = 250;
const AIR_RATE_PER_KG = 800;
const MINIMUM_SHIPPING_CHARGE = 500;

// コンテナ便LCL料金 [最大CBM, 円/m³]
const CONTAINER_LCL_RATES = [
  [2, 20000],
  [20, 14000],
  [Infinity, 12500],
];

// 佐川急便BtoC料金 [3辺合計上限cm, 円/個]
const SAGAWA_BTOC_RATES = [
  [60, 570], [80, 630], [100, 690], [140, 950],
  [160, 1180], [170, 1880], [180, 2190], [200, 2690],
  [220, 3190], [240, 4190], [260, 5190],
];
