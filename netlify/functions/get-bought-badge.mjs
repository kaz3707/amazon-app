/**
 * ASIN を受け取り、Amazon商品詳細ページから「過去1か月で○○点購入されました」
 * バッジを抽出して返す。結果はSupabaseにキャッシュする。
 *
 * POST { asin: "B0CPSRZ2B4", force?: true }
 * → { count: 1000, text: "過去1か月で1000点以上購入されました", cached: false, updated_at: "..." }
 */

const SUPABASE_URL = "https://iadzbyuefqeeeiemrkym.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZHpieXVlZnFlZWVpZW1ya3ltIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU2NDcwNTMsImV4cCI6MjA5MTIyMzA1M30.LXoK999MTI8vjqRc7WnNliNCepi-zCLLJ-wnZJ_dSh0";

// 同じASINで連続取得するのを防ぐ最低間隔（7日）
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

function extractBadge(html) {
  // Amazonはバッジを複数の <span> に分割してレンダリングするため
  // 該当ブロックを抜き出してからタグ除去してマッチする
  const block = html.match(
    /social-proofing-faceout-title-text[\s\S]{0,80}?>([\s\S]{0,500}?)<\/span>\s*<\/div>/
  );
  const candidates = [];
  if (block) candidates.push(block[1]);
  // フォールバック: id=social-proofing-faceout-title-tk_bought 周辺
  const byId = html.match(
    /id="social-proofing-faceout-title-tk_bought"[\s\S]{0,600}?<\/span>\s*<\/div>/
  );
  if (byId) candidates.push(byId[0]);

  const patterns = [
    /過去1(?:か|ヶ|ヵ)月で\s*([\d,]+)\s*点以上\s*購入されました/,
    /過去1(?:か|ヶ|ヵ)月で\s*([\d,]+)\s*点\s*購入されました/,
    /(\d[\d,]*)\+?\s*bought in past month/i,
  ];
  for (const raw of candidates) {
    const stripped = raw.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
    for (const re of patterns) {
      const m = stripped.match(re);
      if (m) {
        const count = parseInt(m[1].replace(/,/g, ""), 10);
        if (!isNaN(count)) return { count, text: m[0] };
      }
    }
  }
  return null;
}

async function sbGet(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
  });
  if (!res.ok) throw new Error(`Supabase GET ${res.status}`);
  return res.json();
}

async function sbRpc(fn, payload) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`RPC ${fn} ${res.status}: ${t.slice(0, 200)}`);
  }
  return res.json().catch(() => null);
}

export async function handler(event) {
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
  };

  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers };
  }

  let body = {};
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "invalid json" }) };
  }

  const asin = (body.asin || "").trim();
  const force = body.force === true;
  if (!/^[A-Z0-9]{10}$/i.test(asin)) {
    return { statusCode: 400, headers, body: JSON.stringify({ error: "invalid asin" }) };
  }

  try {
    // 1. キャッシュ確認
    if (!force) {
      const rows = await sbGet(
        `bestseller_products?asin=eq.${asin}&select=bought_in_past_month,bought_in_past_month_text,bought_updated_at`
      );
      const row = rows?.[0];
      if (row && row.bought_updated_at) {
        const age = Date.now() - new Date(row.bought_updated_at).getTime();
        if (age < CACHE_TTL_MS && row.bought_in_past_month != null) {
          return {
            statusCode: 200,
            headers,
            body: JSON.stringify({
              asin,
              count: row.bought_in_past_month,
              text: row.bought_in_past_month_text,
              cached: true,
              updated_at: row.bought_updated_at,
            }),
          };
        }
      }
    }

    // 2. Amazon商品ページを取得
    const url = `https://www.amazon.co.jp/dp/${asin}`;
    const resp = await fetch(url, {
      headers: {
        "User-Agent": UA,
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "Accept":
          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!resp.ok) {
      return {
        statusCode: 502,
        headers,
        body: JSON.stringify({ error: `Amazon ${resp.status}`, asin }),
      };
    }

    const html = await resp.text();
    const badge = extractBadge(html);

    if (!badge) {
      // バッジが無い商品 = 購入数表示に満たない商品。0 として記録する
      await sbRpc("upsert_bought_badge", {
        p_asin: asin,
        p_count: 0,
        p_text: "",
      });
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({
          asin,
          count: 0,
          text: "",
          cached: false,
          note: "バッジ表示なし",
        }),
      };
    }

    // 3. DBに保存
    await sbRpc("upsert_bought_badge", {
      p_asin: asin,
      p_count: badge.count,
      p_text: badge.text,
    });

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        asin,
        count: badge.count,
        text: badge.text,
        cached: false,
      }),
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: err.message, asin }),
    };
  }
}
