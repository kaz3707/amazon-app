/**
 * Supabase クライアント & データアクセス層
 */

const SUPABASE_URL = "https://iadzbyuefqeeeiemrkym.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZHpieXVlZnFlZWVpZW1ya3ltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU2NDcwNTMsImV4cCI6MjA5MTIyMzA1M30.LXoK999MTI8vjqRc7WnNliNCepi-zCLLJ-wnZJ_dSh0";

// Supabase JS CDN から読み込まれた supabase オブジェクトを使用
let _supabase = null;

function getSupabase() {
  if (!_supabase) {
    _supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return _supabase;
}

// ──────────────────────────────────────────
// ベストセラー商品の取得
// ──────────────────────────────────────────

async function fetchBestsellerProducts(maxReview = 100, minSales = 300, categoryPrefix = null, minReview = 1) {
  const sb = getSupabase();
  let query = sb
    .from("bestseller_products")
    .select("*")
    .gte("review_count", minReview)
    .lte("review_count", maxReview)
    .gte("estimated_monthly_sales", minSales)
    .order("opportunity_score", { ascending: false })
    .limit(500);

  if (categoryPrefix) {
    query = query.like("category_path", `${categoryPrefix}%`);
  }

  const { data, error } = await query;
  if (error) throw new Error(error.message);
  return data || [];
}

// ──────────────────────────────────────────
// カテゴリ一覧の取得
// ──────────────────────────────────────────

async function fetchCategories() {
  const sb = getSupabase();
  // PostgREST はテーブル/ビューに対し max-rows 1000 が効くため、RPC 経由で全件取得する
  // RPC は jsonb で文字列配列を返すので data はそのまま string[]
  const { data, error } = await sb.rpc("get_bestseller_categories");
  if (error) throw new Error(error.message);
  return Array.isArray(data) ? data : [];
}

// ──────────────────────────────────────────
// キャッシュ状態（スクレイピングメタデータ）
// ──────────────────────────────────────────

async function fetchCacheStatus() {
  const sb = getSupabase();

  // メタデータからステータス取得
  const { data: meta } = await sb
    .from("scrape_metadata")
    .select("*")
    .eq("key", "bestseller_status")
    .single();

  // 商品総数を取得
  const { count } = await sb
    .from("bestseller_products")
    .select("*", { count: "exact", head: true });

  const categories = await fetchCategories();

  return {
    running: meta?.value?.running || false,
    current_category: meta?.value?.current_category || "",
    categories_done: meta?.value?.categories_done || 0,
    categories_total: meta?.value?.categories_total || 0,
    last_updated: meta?.value?.last_updated || null,
    error: meta?.value?.error || null,
    total_products: count || 0,
    categories,
  };
}

// ──────────────────────────────────────────
// カテゴリTOP100
// ──────────────────────────────────────────

async function fetchCategoryTop100(categoryPath) {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("bestseller_products")
    .select("*")
    .eq("category_path", categoryPath)
    .order("rank_in_category", { ascending: true })
    .limit(100);

  if (error) throw new Error(error.message);
  return data || [];
}

// ──────────────────────────────────────────
// 計算履歴の保存・取得・削除
// ──────────────────────────────────────────

async function saveCalculationHistory(record) {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("calculation_history")
    .insert({
      product_name: record.product_name || "",
      product_url_1688: record.product_url_1688 || "",
      platform: record.platform || "amazon",
      selling_price: record.selling_price || 0,
      total_cost: record.total_cost || 0,
      profit: record.profit || 0,
      profit_rate: record.profit_rate || 0,
      detail_json: record.detail || {},
    })
    .select()
    .single();

  if (error) throw new Error(error.message);
  return { ok: true, id: data.id };
}

async function fetchCalculationHistory() {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("calculation_history")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(50);

  if (error) throw new Error(error.message);

  return (data || []).map(r => {
    const d = r.detail_json || {};
    return {
      id: r.id,
      product_name: r.product_name,
      platform: r.platform,
      selling_price: r.selling_price,
      profit: r.profit,
      profit_rate: r.profit_rate,
      created_at: new Date(r.created_at).toLocaleString("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
      roi: d.roi,
      monthly_net_profit: d.monthly?.net_profit,
      asin: d.asin,
      amazon_price: d.amazon_price,
    };
  });
}

async function fetchCalculationDetail(id) {
  const sb = getSupabase();
  const { data, error } = await sb
    .from("calculation_history")
    .select("*")
    .eq("id", id)
    .single();

  if (error) throw new Error(error.message);

  const detail = data.detail_json || {};
  return {
    id: data.id,
    product_name: data.product_name,
    product_url_1688: data.product_url_1688,
    platform: data.platform,
    created_at: new Date(data.created_at).toLocaleString("ja-JP", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
    ...detail,
  };
}

async function deleteCalculationHistory(id) {
  const sb = getSupabase();
  const { error } = await sb
    .from("calculation_history")
    .delete()
    .eq("id", id);

  if (error) throw new Error(error.message);
}

// ──────────────────────────────────────────
// Netlify Functions 呼び出しヘルパー
// ──────────────────────────────────────────

async function callNetlifyFunction(name, body = {}) {
  const res = await fetch(`/.netlify/functions/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
  return json;
}

async function callNetlifyFunctionGet(name) {
  const res = await fetch(`/.netlify/functions/${name}`);
  const json = await res.json();
  if (!res.ok) throw new Error(json.error || `HTTP ${res.status}`);
  return json;
}
