/* ===== アプリ状態 ===== */
const state = {
  amazonCategories: [],
  customsCategories: [],
  selectedProduct: null,
  browseResults: [],       // 最後に取得した商品一覧（重み変更時に再ソートに使う）
  exchangeRate: 21.5,       // 為替レート（仕入れ上限計算用）
  watchlist: [],            // ウォッチリスト（localStorage永続化）
  lastAnalysisResult: null, // 保存ボタン用に最後の計算結果を保持
  modalResult: null,        // 出品済み詳細モーダル用
};

/* ===== 初期化 ===== */
document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupResearch();
  setupLookup();
  setupAnalyze();
  loadWatchlistFromStorage();
  await loadMasterData();
});

async function loadMasterData() {
  try {
    const data = await apiGet("/api/amazon/categories");
    state.amazonCategories = data.categories;
    populateSelect("amazon-category", data.categories, c => `${c.name}（${(c.fee_rate*100).toFixed(0)}%）`, c => c.key);
  } catch(e) { console.warn("Amazon手数料読み込み失敗", e); }

  try {
    const data = await apiGet("/api/customs/categories");
    state.customsCategories = data.categories;
    populateSelect("customs-category", data.categories,
      c => `${c.description}（関税${(c.customs_rate*100).toFixed(1)}%）`, c => c.key);
  } catch(e) { console.warn("関税カテゴリ読み込み失敗", e); }

  // 為替レートは初期値22円を使用（「更新」ボタンで最新レートに変更可能）
  state.exchangeRate = parseFloat(document.getElementById("exchange-rate")?.value) || 22;

}

function populateSelect(id, items, labelFn, valueFn) {
  const sel = document.getElementById(id);
  if (!sel) return;
  sel.innerHTML = '<option value="">選択してください...</option>';
  items.forEach(item => {
    const opt = document.createElement("option");
    opt.value = valueFn(item);
    opt.textContent = labelFn(item);
    Object.assign(opt.dataset, item);
    sel.appendChild(opt);
  });
}

/* ===== タブ切り替え ===== */
function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.style.display = "none");
      btn.classList.add("active");
      const tab = document.getElementById(`tab-${btn.dataset.tab}`);
      if (tab) tab.style.display = "block";
    });
  });
}

/* =============================================
   商品リサーチ（ベストセラーブラウズ）
   ============================================= */

function setupResearch() {
  document.getElementById("btn-browse").addEventListener("click", runBrowse);
  document.getElementById("btn-refresh-cache").addEventListener("click", triggerCacheRefresh);

  // 重みスライダー：値表示 + リアルタイム再ソート
  ["sales", "review"].forEach(key => {
    const slider = document.getElementById(`w-${key}`);
    const valEl  = document.getElementById(`w-${key}-val`);
    slider.addEventListener("input", () => {
      valEl.textContent = slider.value;
      if (state.browseResults.length > 0) rerenderWithWeights();
    });
  });

  loadCacheStatus();
}

async function loadCacheStatus() {
  try {
    const data = await apiGet("/api/research/cache-status");
    updateCacheStatusBar(data);
    populateCategorySelect(data.categories || []);
  } catch(e) {
    document.getElementById("cache-status-text").textContent = "状態取得に失敗しました";
  }
}

function updateCacheStatusBar(data) {
  const el = document.getElementById("cache-status-text");
  if (data.running) {
    const done = data.categories_done || 0;
    const total = data.categories_total || 0;
    const cur = data.current_category ? `（${data.current_category}）` : "";
    el.innerHTML = `<span class="spinner" style="display:inline-block;width:12px;height:12px;border-width:2px;margin-right:6px;vertical-align:middle"></span>更新中${cur} ${done}/${total}カテゴリ`;
    setTimeout(loadCacheStatus, 3000);
  } else if (data.last_updated && data.total_products > 0) {
    const dt = new Date(data.last_updated).toLocaleString("ja-JP");
    el.textContent = `最終更新: ${dt}　商品数: ${data.total_products.toLocaleString()}件`;
    el.style.color = "#065f46";
  } else if (data.error) {
    el.textContent = `エラー: ${data.error}`;
    el.style.color = "#dc2626";
  } else {
    el.textContent = "データなし。「データ更新」ボタンを押してAmazonから取得してください。";
    el.style.color = "#92400e";
  }
}

/* ===== カテゴリツリーナビゲーション ===== */
let _catTree = {};

function _buildCatTree(categories) {
  const tree = {};
  for (const cat of categories) {
    const parts = cat.split(" > ");
    let node = tree;
    for (const part of parts) {
      if (!node[part]) node[part] = {};
      node = node[part];
    }
  }
  return tree;
}

function populateCategorySelect(categories) {
  _catTree = _buildCatTree(categories);
  renderCatLevel(_catTree, []);

  // パネル外クリックで閉じる
  document.addEventListener("click", (e) => {
    const root = document.getElementById("cat-nav-root");
    if (root && !root.contains(e.target)) {
      const panel = document.getElementById("cat-panel");
      if (panel) panel.style.display = "none";
    }
  });
}

function toggleCatPanel() {
  const panel = document.getElementById("cat-panel");
  if (panel.style.display === "none") {
    renderCatLevel(_catTree, []);
    panel.style.display = "flex";
  } else {
    panel.style.display = "none";
  }
}

function renderCatLevel(node, path) {
  const breadcrumb = document.getElementById("cat-breadcrumb");
  const list = document.getElementById("cat-list");

  // パンくず
  if (path.length === 0) {
    breadcrumb.innerHTML = '<span style="color:var(--gray-400)">カテゴリを選択</span>';
  } else {
    breadcrumb.innerHTML =
      `<span class="cat-back" onclick="catNavBack(${JSON.stringify(path)})">← 戻る</span>` +
      `<span class="cat-bc-path">${path.join(" › ")}</span>`;
  }

  list.innerHTML = "";

  // 「全て」選択肢
  const allItem = document.createElement("div");
  allItem.className = "cat-item cat-item-all";
  const allLabel = path.length === 0 ? "全カテゴリ（絞り込まない）" : path[path.length - 1] + "（全て）";
  const allValue = path.length === 0 ? "" : path.join(" > ");
  allItem.textContent = allLabel;
  allItem.addEventListener("click", (e) => { e.stopPropagation(); selectCatValue(allValue, allLabel); });
  list.appendChild(allItem);

  // サブカテゴリ一覧
  const keys = Object.keys(node).sort();
  for (const key of keys) {
    const hasChildren = Object.keys(node[key]).length > 0;
    const item = document.createElement("div");
    item.className = "cat-item" + (hasChildren ? " cat-item-parent" : "");
    const childPath = [...path, key];

    if (hasChildren) {
      // 親アイテム：どこをクリックしても次の階層へ（選択は各階層の「全て」で行う）
      const nameSpan = document.createElement("span");
      nameSpan.className = "cat-item-name";
      nameSpan.textContent = key;
      const arrow = document.createElement("span");
      arrow.className = "cat-item-arrow";
      arrow.textContent = "›";
      item.appendChild(nameSpan);
      item.appendChild(arrow);
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        renderCatLevel(node[key], childPath);
      });
    } else {
      item.textContent = key;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        selectCatValue(childPath.join(" > "), childPath.join(" › "));
      });
    }
    list.appendChild(item);
  }
}

function catNavBack(path) {
  path.pop();
  let node = _catTree;
  for (const p of path) node = node[p];
  renderCatLevel(node, path);
}

function selectCatValue(value, label) {
  document.getElementById("filter-category").value = value;
  document.getElementById("cat-display-text").textContent =
    value ? label : "全カテゴリ（絞り込まない）";
  document.getElementById("cat-panel").style.display = "none";
}

async function triggerCacheRefresh() {
  const btn = document.getElementById("btn-refresh-cache");

  // 更新対象カテゴリの選択（全カテゴリ or 選択中のトップカテゴリのみ）
  const catVal = document.getElementById("filter-category").value;
  const topCat = catVal ? catVal.split(" > ")[0] : null;

  const msg = topCat
    ? `「${topCat}」のベストセラーデータを更新します。`
    : "全カテゴリのベストセラーデータを更新します。完了まで数分かかります。";

  if (!confirm(msg + "\nよろしいですか？")) return;

  setLoading(btn, true);
  try {
    const payload = topCat ? { categories: [topCat] } : {};
    const data = await apiPost("/api/research/refresh", payload);
    showToast(data.message, data.ok ? "success" : "error");
    if (data.ok) {
      document.getElementById("cache-status-text").textContent = "更新中...";
      setTimeout(loadCacheStatus, 2000);
    }
  } catch(e) {
    showToast(`更新開始に失敗: ${e.message}`, "error");
  } finally {
    setLoading(btn, false);
  }
}

async function runBrowse() {
  const maxReview = parseInt(document.getElementById("filter-max-review").value) || 100;
  const minSales = parseInt(document.getElementById("filter-min-sales").value) || 300;
  const category = document.getElementById("filter-category").value || "";
  const btn = document.getElementById("btn-browse");
  setLoading(btn, true);

  const container = document.getElementById("research-results");
  container.innerHTML = `<div class="card" style="text-align:center;padding:40px;color:#6b7280">
    <div class="spinner" style="border-color:rgba(37,99,235,.3);border-top-color:var(--primary);margin:0 auto 12px"></div>
    データを取得中...
  </div>`;

  try {
    const data = await apiPost("/api/research/browse", {
      max_review: maxReview,
      min_monthly_sales: minSales,
      category: category || null,
    });
    state.browseResults = data.results || [];
    renderResearchResults(data);
  } catch(e) {
    showToast(`取得失敗: ${e.message}`, "error");
    container.innerHTML = `<div class="card" style="text-align:center;padding:40px;color:#dc2626">取得に失敗しました: ${e.message}</div>`;
  } finally {
    setLoading(btn, false);
  }
}

function getWeights() {
  return {
    ws: parseInt(document.getElementById("w-sales")?.value) || 5,
    wr: parseInt(document.getElementById("w-review")?.value) || 5,
  };
}

function calcWeightedScore(p) {
  const { ws, wr } = getWeights();
  const s = p.scores || { sales: 50, review: 50 };
  const total = ws + wr;
  return Math.round((s.sales * ws + s.review * wr) / total);
}

function weightedLabel(score) {
  if (score >= 80) return "◎ 優良";
  if (score >= 60) return "○ 良好";
  if (score >= 40) return "△ 普通";
  return "× 不向き";
}

function weightedScoreClass(score) {
  if (score >= 80) return "score-excellent";
  if (score >= 60) return "score-good";
  if (score >= 40) return "score-normal";
  return "score-bad";
}

function rerenderWithWeights() {
  const sortMode = document.getElementById("sort-mode")?.value || "score";
  const products = state.browseResults;

  let sorted;
  if (sortMode === "sales") {
    sorted = [...products].sort((a, b) => b.estimated_monthly_sales - a.estimated_monthly_sales);
  } else if (sortMode === "price") {
    sorted = [...products].sort((a, b) => b.price - a.price);
  } else if (sortMode === "review_asc") {
    sorted = [...products].sort((a, b) => a.review_count - b.review_count);
  } else {
    sorted = [...products].sort((a, b) => calcWeightedScore(b) - calcWeightedScore(a));
  }

  renderProductGrid(sorted);
}

function renderResearchResults(data) {
  const container = document.getElementById("research-results");
  if (!data.results || data.results.length === 0) {
    container.innerHTML = `<div class="card" style="text-align:center;padding:40px;color:#9ca3af">
      条件に合う商品が見つかりませんでした。条件を緩めてみてください。
    </div>`;
    return;
  }

  const catLabel = data.category && data.category !== "全カテゴリ" ? `【${data.category}】` : "【全カテゴリ】";
  container.innerHTML = `
    <div id="results-header" style="padding:8px 0 12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
      <span style="font-size:13px;color:#6b7280">${catLabel} ${data.count}件が条件に合致</span>
      <div style="display:flex;align-items:center;gap:6px;font-size:12px">
        <label style="color:#374151;font-weight:600">並び替え：</label>
        <select id="sort-mode" onchange="rerenderWithWeights()"
          style="font-size:12px;padding:3px 8px;border:1px solid #d1d5db;border-radius:4px">
          <option value="score">機会スコア順</option>
          <option value="sales">📦 月間販売数順</option>
          <option value="price">💴 販売価格順</option>
          <option value="review_asc">⭐ レビューの少なさ順</option>
        </select>
      </div>
    </div>
    <div id="results-grid" class="result-grid"></div>`;

  rerenderWithWeights();
}

function buildProductCardEl(p) {
  const wScore = calcWeightedScore(p);
  const label  = weightedLabel(wScore);
  const scoreClass = weightedScoreClass(wScore);
  const s = p.scores || { sales: 0, review: 0, seller: 0 };

  const reviewClass = p.review_count <= 30 ? "good" : p.review_count <= 70 ? "warn" : "danger";
  const salesClass  = p.estimated_monthly_sales >= 500 ? "good" : p.estimated_monthly_sales >= 300 ? "warn" : "danger";

  const rankBadge = p.rank_in_category
    ? `<span style="background:#fef3c7;color:#92400e;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:700">ランク ${p.rank_in_category}位</span>`
    : "";

  const keepa = p.keepa_analysis || {};
  const keepaLabel = keepa.label || "";
  const keepaBadge = (() => {
    if (!keepaLabel || keepaLabel === "未取得") return "";
    const peakStr = keepa.peak_months_str ? `（${keepa.peak_months_str}にピーク）` : "";
    if (keepa.badge_type === "stable") {
      return `<span title="${keepa.detail || ""}" style="background:#dcfce7;color:#166534;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:700">📈 ${keepaLabel}</span>`;
    } else if (keepa.badge_type === "seasonal") {
      return `<span title="${keepa.detail || ""}" style="background:#dbeafe;color:#1e40af;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:700">🗓 ${keepaLabel}${peakStr}</span>`;
    } else if (keepa.badge_type === "growing") {
      return `<span title="${keepa.detail || ""}" style="background:#ffedd5;color:#9a3412;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:700">🚀 ${keepaLabel}</span>`;
    } else {
      return `<span title="${keepa.detail || ""}" style="background:#fee2e2;color:#991b1b;padding:1px 7px;border-radius:4px;font-size:11px;font-weight:700">⚠ ${keepaLabel}</span>`;
    }
  })();

  const scoreBar = (val, color) =>
    `<div style="height:5px;background:#e5e7eb;border-radius:3px;overflow:hidden">
      <div style="height:100%;width:${val}%;background:${color};border-radius:3px"></div>
     </div>`;

  // ウォッチリストボタン
  const inWatch = isInWatchlist(p.asin);
  const watchBtnId = `watch-btn-${p.asin}`;

  const card = document.createElement("div");
  card.className = "product-card";
  card.innerHTML = `
    <div style="display:flex;gap:6px;align-items:flex-start;flex-wrap:wrap;margin-bottom:6px">
      <span class="score-badge ${scoreClass}">${label}　${wScore}点</span>
      ${rankBadge}
      ${keepaBadge}
    </div>
    <div class="product-title">${p.title}</div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:8px">${p.category_path || p.category || ""}</div>
    <div class="product-stats">
      <div class="stat-item">
        <div class="stat-value" style="color:#2563eb">¥${p.price.toLocaleString()}</div>
        <div class="stat-label">販売価格</div>
      </div>
      <div class="stat-item">
        <div class="stat-value ${salesClass}">${p.estimated_monthly_sales.toLocaleString()}${p.sales_from_badge ? "以上" : ""}</div>
        <div class="stat-label">${p.variation_count > 1 ? `月販(${p.variation_count}種合算)` : "月間販売数"}</div>
      </div>
      <div class="stat-item">
        <div class="stat-value ${reviewClass}">${p.review_count}</div>
        <div class="stat-label">レビュー数</div>
      </div>
    </div>
    <div style="font-size:11px;color:#6b7280;margin-bottom:6px;display:grid;gap:4px">
      <div style="display:flex;align-items:center;gap:6px">
        <span style="width:60px;flex-shrink:0">📦 販売数</span>
        <span style="width:52px;flex-shrink:0;color:#2563eb;font-weight:600">${p.estimated_monthly_sales.toLocaleString()}${p.sales_from_badge ? "以上" : ""}件</span>
        ${scoreBar(s.sales, "#2563eb")}
        <span style="width:28px;flex-shrink:0;text-align:right;font-weight:700;color:#2563eb">${s.sales}</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px">
        <span style="width:60px;flex-shrink:0">⭐ レビュー</span>
        <span style="width:52px;flex-shrink:0;color:#16a34a;font-weight:600">${p.review_count}件</span>
        ${scoreBar(s.review, "#16a34a")}
        <span style="width:28px;flex-shrink:0;text-align:right;font-weight:700;color:#16a34a">${s.review}</span>
      </div>
    </div>
    <div style="font-size:11px;color:#9ca3af;margin-bottom:8px">
      ★ ${p.rating}
    </div>
    <div style="display:flex;gap:6px;margin-top:8px">
      <button class="analyze-btn" style="flex:1" onclick="openRivalModal(${JSON.stringify(p).replace(/"/g, '&quot;')})">
        同カテゴリ TOP100を確認 →
      </button>
      <button id="${watchBtnId}" style="padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;background:${inWatch ? '#fef9c3' : '#fff'};cursor:pointer;font-size:13px;white-space:nowrap"
        onclick="toggleWatchlist(${JSON.stringify(p).replace(/"/g, '&quot;')}, '${watchBtnId}')">
        ${inWatch ? "⭐" : "☆"} ウォッチ
      </button>
    </div>
  `;
  return card;
}

function renderProductGrid(products) {
  const grid = document.getElementById("results-grid");
  if (!grid) return;
  grid.innerHTML = "";
  products.forEach(p => grid.appendChild(buildProductCardEl(p)));
}

/* =============================================
   単品調査
   ============================================= */

function setupLookup() {
  document.getElementById("btn-lookup").addEventListener("click", runLookup);
  document.getElementById("lookup-input").addEventListener("keydown", e => {
    if (e.key === "Enter") runLookup();
  });
}

async function runLookup() {
  const input = document.getElementById("lookup-input").value.trim();
  if (!input) {
    showToast("ASINまたはURLを入力してください", "error");
    return;
  }

  const btn = document.getElementById("btn-lookup");
  const resultEl = document.getElementById("lookup-result");

  setLoading(btn, true);
  resultEl.innerHTML = `<div class="card" style="text-align:center;padding:40px;color:#6b7280">
    <div class="spinner" style="border-color:rgba(37,99,235,.3);border-top-color:var(--primary);margin:0 auto 12px"></div>
    商品情報を取得中...
  </div>`;

  try {
    const data = await apiPost("/api/research/product-detail", { asin_or_url: input });
    if (data.error) {
      showToast(data.error, "error");
      resultEl.innerHTML = `<div class="card" style="text-align:center;padding:32px;color:#dc2626">${data.error}</div>`;
      return;
    }
    resultEl.innerHTML = "";
    resultEl.appendChild(buildProductCardEl(data));
  } catch(e) {
    showToast(`取得失敗: ${e.message}`, "error");
    resultEl.innerHTML = `<div class="card" style="text-align:center;padding:32px;color:#dc2626">取得に失敗しました: ${e.message}</div>`;
  } finally {
    setLoading(btn, false);
  }
}

// ──────────────────────────────────────────
// 同カテゴリTOP100モーダル
// ──────────────────────────────────────────

async function openRivalModal(product) {
  document.getElementById("rival-modal-overlay")?.remove();

  const categoryPath = product.category_path || product.category || "";

  const overlay = document.createElement("div");
  overlay.id = "rival-modal-overlay";
  overlay.className = "rival-modal-overlay";
  overlay.innerHTML = `
    <div class="rival-modal">
      <div class="rival-modal-header">
        <div>
          <h3>📊 同カテゴリ TOP100</h3>
          <div class="product-ref">${categoryPath || product.title.slice(0, 60)}</div>
        </div>
        <button class="rival-modal-close" onclick="document.getElementById('rival-modal-overlay').remove()">✕</button>
      </div>
      <div class="rival-modal-body" id="rival-modal-body">
        <div style="text-align:center;padding:40px;color:#9ca3af">
          <div style="font-size:24px;margin-bottom:8px">📊</div>
          <div>同カテゴリのTOP100商品をキャッシュから取得中...</div>
        </div>
      </div>
      <div class="rival-modal-footer">
        <span class="hint">確認後、利益計算へ進めます</span>
        <button class="btn btn-primary" onclick="closeRivalModalAndAnalyze()">
          この商品の利益計算へ進む →
        </button>
      </div>
    </div>
  `;

  overlay.addEventListener("click", e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  window._rivalModalProduct = product;

  try {
    const res = await apiPost("/api/research/category-top100", {
      category_path: categoryPath,
    });
    renderCategoryTop100(res.products || [], res.category_path || categoryPath, product);
  } catch (err) {
    document.getElementById("rival-modal-body").innerHTML = `
      <div style="text-align:center;padding:40px;color:#dc2626">
        <div style="font-size:24px;margin-bottom:8px">⚠️</div>
        <div>取得に失敗しました</div>
        <div style="font-size:12px;color:#9ca3af;margin-top:4px">${err.message || ""}</div>
      </div>`;
  }
}

function renderCategoryTop100(products, categoryPath, targetProduct) {
  const body = document.getElementById("rival-modal-body");
  if (!body) return;

  const reviewColor = (n) => n <= 30 ? "#16a34a" : n <= 100 ? "#d97706" : "#dc2626";
  const salesColor  = (n) => n >= 500 ? "#16a34a" : n >= 300 ? "#d97706" : "#6b7280";

  const selfHtml = `
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:12px">
      <span style="font-weight:700;color:#1e40af">📦 調査中の商品：</span>
      <span style="color:#374151">${targetProduct.title.slice(0, 70)}${targetProduct.title.length > 70 ? "…" : ""}</span>
      <span style="margin-left:8px;color:#2563eb;font-weight:700">¥${targetProduct.price.toLocaleString()}</span>
      <span style="margin-left:8px;color:#16a34a">⭐${targetProduct.review_count}件 / 月販${targetProduct.estimated_monthly_sales}個</span>
    </div>`;

  if (!products.length) {
    body.innerHTML = selfHtml + `
      <div style="text-align:center;padding:40px;color:#9ca3af">
        <div style="font-size:20px;margin-bottom:8px">📭</div>
        <div>キャッシュにこのカテゴリの商品がありません</div>
        <div style="font-size:12px;margin-top:6px">「商品リサーチ」タブでキャッシュを更新してください</div>
      </div>`;
    return;
  }

  const rowsHtml = products.map((c, i) => {
    const rank = c.rank_in_category || (i + 1);
    const title = c.title.length > 55 ? c.title.slice(0, 55) + "…" : c.title;
    return `
      <div class="top100-row${c.asin === targetProduct.asin ? " top100-row--self" : ""}">
        <span class="top100-rank">${rank}位</span>
        <span class="top100-title">${title}</span>
        <span class="top100-price">¥${(c.price || 0).toLocaleString()}</span>
        <span class="top100-reviews" style="color:${reviewColor(c.review_count || 0)}">⭐${(c.review_count || 0).toLocaleString()}</span>
        <span class="top100-sales" style="color:${salesColor(c.estimated_monthly_sales || 0)}">月販${(c.estimated_monthly_sales || 0).toLocaleString()}</span>
        <a class="top100-link" href="${c.url}" target="_blank" rel="noopener">↗</a>
      </div>`;
  }).join("");

  body.innerHTML = selfHtml + `
    <div style="font-size:12px;color:#6b7280;margin-bottom:8px">
      ${categoryPath} — ${products.length}件（類似品がどれくらいあるか目視で確認してください）
    </div>
    <div class="top100-list">${rowsHtml}</div>`;
}

function closeRivalModalAndAnalyze() {
  const product = window._rivalModalProduct;
  document.getElementById("rival-modal-overlay")?.remove();
  if (!product) return;
  selectProductForAnalysis(product);
}

function selectProductForAnalysis(product) {
  state.selectedProduct = product;

  // 分析タブに切り替え
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.style.display = "none");
  document.querySelector('[data-tab="analyze"]').classList.add("active");
  document.getElementById("tab-analyze").style.display = "block";

  // フォームに自動入力
  setVal("product-title", product.title);
  setVal("amazon-price", product.price);
  setVal("monthly-sales", product.estimated_monthly_sales);
  setVal("competitor-reviews", product.review_count);
  setVal("seller-count", product.seller_count);

  if (product.dimensions && product.dimensions.length != null && product.dimensions.length > 0) {
    setVal("dim-length", product.dimensions.length);
    setVal("dim-width", product.dimensions.width);
    setVal("dim-height", product.dimensions.height);
    setVal("dim-weight", product.dimensions.weight_g);
    updateShippingDisplay();
  }

  // カテゴリ自動選択（商品カテゴリパスからキーワードマッチ）
  autoSelectCategoryFromPath(product.category || "");

  // Amazon商品画像をセット
  if (product.image_url) setAmazonImage(product.image_url);

  // 保存ファイル名用にASINを保持
  state._cropFilename = product.asin || null;

  showToast("商品情報を自動入力しました。", "success");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function autoSelectCategoryFromPath(categoryPath) {
  if (!categoryPath) return;

  // キーはすべて FALLBACK_FEES に存在するものに統一
  const keywords = {
    // 車・バイク（長いものを先に）
    "カー＆バイク": "auto", "カーアクセサリ": "auto", "バイク用品": "auto",
    "カー&バイク": "auto", "車": "auto", "バイク": "auto",
    // DIY・工具
    "DIY・工具": "tools", "電動工具": "tools", "工具": "tools", "ガーデン": "tools",
    // スマートフォン・PC・カメラ・家電
    "スマートフォン": "mobile", "携帯電話": "mobile",
    "パソコン": "pc", "周辺機器": "pc",
    "カメラ": "camera",
    "家電": "electronics", "電子": "electronics",
    // ファッション
    "シューズ": "shoes", "バッグ": "shoes", "旅行用品": "shoes",
    "靴": "shoes", "衣類": "clothing", "服": "clothing",
    "時計": "watches", "ジュエリー": "jewelry",
    // スポーツ・アウトドア
    "スポーツ": "sports", "アウトドア": "sports",
    // ホーム・キッチン
    "ホーム＆キッチン": "home", "ホーム&キッチン": "home",
    "キッチン": "home", "ホーム": "home",
    // ペット・ベビー・おもちゃ
    "ペット": "pet", "ベビー": "baby", "マタニティ": "baby", "おもちゃ": "toys",
    // ビューティー・ヘルス
    "ビューティー": "beauty", "コスメ": "beauty", "スキンケア": "beauty",
    "ヘルス": "health", "栄養補助食品": "supplement", "サプリ": "supplement",
    "ビタミン": "supplement", "プロテイン": "supplement",
    // 食品
    "食品": "food", "飲料": "food",
    // 文房具・本
    "文房具": "office", "オフィス": "office",
    "本": "books", "書籍": "books",
  };

  // 長いキーワードを優先（誤マッチ防止）
  const sorted = Object.entries(keywords).sort((a, b) => b[0].length - a[0].length);
  for (const [kw, key] of sorted) {
    if (categoryPath.includes(kw)) {
      const sel = document.getElementById("amazon-category");
      if (sel) {
        sel.value = key;
        // 選択できているか確認（optionに存在しないキーは無視）
        if (!sel.value) sel.value = "other";
        // 関税カテゴリも連動
        const customsSel = document.getElementById("customs-category");
        if (customsSel) {
          // AmazonカテゴリキーからCUSTOMS_MASTERキーへのマッピング
          const amazonToCustoms = {
            "auto": "auto_parts", "tools": "other", "mobile": "electronics",
            "pc": "electronics", "camera": "electronics", "electronics": "electronics",
            "shoes": "shoes", "clothing": "clothing", "watches": "jewelry",
            "jewelry": "jewelry", "sports": "sports", "home": "other",
            "pet": "other", "baby": "toys", "toys": "toys",
            "beauty": "cosmetics", "health": "other", "supplement": "supplement",
            "food": "food_general", "office": "other", "books": "books",
            "music": "other", "video": "other", "software": "other",
            "video_games": "toys", "stationery": "other", "other": "other",
          };
          customsSel.value = amazonToCustoms[key] || "other";
        }
        updateCustomsDisplay();
      }
      return;
    }
  }

  // どれにも一致しない場合は "other" を選択
  const sel = document.getElementById("amazon-category");
  if (sel) sel.value = "other";
}

/* =============================================
   利益・ROI計算
   ============================================= */

function setupAnalyze() {
  // 寸法変更で送料自動表示
  ["dim-length", "dim-width", "dim-height", "dim-weight"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", () => {
      // 寸法が変わったら手動編集フラグをリセット（自動計算値で上書き）
      const inp = document.getElementById("intl-shipping-input");
      if (inp) delete inp.dataset.manuallyEdited;
      updateShippingDisplay();
    });
  });

  // 国際送料inputを手動変更したらフラグを立てる
  document.getElementById("intl-shipping-input")?.addEventListener("input", function() {
    this.dataset.manuallyEdited = "1";
  });

  // 発注数量変更時も送料を再計算（コンテナ便はCBM合計が変わる）
  document.getElementById("order-quantity")?.addEventListener("input", updateShippingDisplay);

  // 仕入れ単価（元）変更で円換算・国内送料再計算
  document.getElementById("purchase-price-cny")?.addEventListener("input", recalcJpy);
  document.getElementById("exchange-rate")?.addEventListener("input", recalcJpy);
  document.getElementById("purchase-price-jpy")?.addEventListener("input", () => { recalcAgentFee(); recalcDomesticShipping(); });
  document.getElementById("agent-fee-rate")?.addEventListener("input", recalcAgentFee);
  document.getElementById("domestic-shipping-rate")?.addEventListener("input", recalcDomesticShipping);

  // 為替レート更新
  document.getElementById("btn-refresh-rate")?.addEventListener("click", async () => {
    const btn = document.getElementById("btn-refresh-rate");
    setLoading(btn, true);
    try {
      const data = await apiGet("/api/1688/exchange-rate");
      setVal("exchange-rate", data.rate.toFixed(2));
      recalcJpy();
      showToast(`為替更新: ${data.rate.toFixed(2)}円/元`, "success");
    } catch(e) { showToast("取得失敗", "error"); }
    finally { setLoading(btn, false); }
  });

  // 関税カテゴリ変更
  document.getElementById("customs-category")?.addEventListener("change", updateCustomsDisplay);



  // 計算ボタン
  document.getElementById("btn-analyze")?.addEventListener("click", runAnalysis);
}

// 佐川急便BtoC料金テーブル（3辺合計cm → 円）
const SAGAWA_BTOC_RATES = [
  [60,  570], [80,  630], [100, 690], [140, 950],
  [160, 1180], [170, 1880], [180, 2190], [200, 2690],
  [220, 3190], [240, 4190], [260, 5190],
];

function calcSagawaBtoC(l, w, h) {
  const PACK = 1.2;
  const threeSum = (l + w + h) * PACK;
  for (const [maxSize, fee] of SAGAWA_BTOC_RATES) {
    if (threeSum <= maxSize) return { threeSum: threeSum.toFixed(1), label: `${maxSize}サイズ`, fee };
  }
  return { threeSum: ((l + w + h) * PACK).toFixed(1), label: "260超（要確認）", fee: 5190 };
}

// コンテナLCL料金テーブル（CBM上限 → 円/m³）
const CONTAINER_LCL_RATES = [[2, 20000], [20, 14000], [Infinity, 12500]];

function calcContainerPerUnit(l, w, h, qty) {
  const PACK = 1.2;
  const cbmPerUnit = (l * PACK) * (w * PACK) * (h * PACK) / 1_000_000;
  const totalCbm = cbmPerUnit * qty;
  let rate = 12500;
  for (const [maxCbm, r] of CONTAINER_LCL_RATES) {
    if (totalCbm <= maxCbm) { rate = r; break; }
  }
  return { cbmPerUnit, totalCbm, rate, perUnit: Math.round(cbmPerUnit * rate) };
}

function onShippingMethodChange() {
  const intlInput = document.getElementById("intl-shipping-input");
  if (intlInput) delete intlInput.dataset.manuallyEdited;
  updateShippingDisplay();
}

function updateShippingDisplay() {
  const l = parseFloat(document.getElementById("dim-length")?.value) || 0;
  const w = parseFloat(document.getElementById("dim-width")?.value) || 0;
  const h = parseFloat(document.getElementById("dim-height")?.value) || 0;
  const g = parseFloat(document.getElementById("dim-weight")?.value) || 0;
  if (!l || !w || !h || !g) return;

  const method = document.getElementById("shipping-method")?.value || "fast_sea";
  const qty    = parseInt(document.getElementById("order-quantity")?.value) || 100;

  const fastSeaBox      = document.getElementById("intl-shipping-per-unit-box");
  const containerBox    = document.getElementById("container-shipping-per-unit-box");
  const sagawaBox       = document.getElementById("sagawa-btoc-box");
  const intlRow         = document.getElementById("intl-shipping-input-row");
  const intlInput       = document.getElementById("intl-shipping-input");
  const display         = document.getElementById("shipping-auto-display");

  if (method === "container_fba_direct") {
    // ── コンテナ便 → FBA直納 ──
    if (display) display.textContent = "";
    if (fastSeaBox) fastSeaBox.style.display = "none";

    const c = calcContainerPerUnit(l, w, h, qty);
    if (containerBox) {
      containerBox.style.display = "block";
      containerBox.innerHTML = `📦 <strong>コンテナ（LCL）国際送料/個</strong>：`
        + `${c.cbmPerUnit.toFixed(5)}m³/個 × ${qty}個 = ${c.totalCbm.toFixed(3)}m³ `
        + `（¥${c.rate.toLocaleString()}/m³）= <strong>¥${c.perUnit.toLocaleString()}</strong>`;
    }
    if (intlRow) intlRow.style.display = "block";
    if (intlInput && !intlInput.dataset.manuallyEdited) intlInput.value = c.perUnit;

    // 佐川BtoC FBA納品送料
    const s = calcSagawaBtoC(l, w, h);
    if (sagawaBox) {
      sagawaBox.style.display = "block";
      sagawaBox.innerHTML = `🚛 <strong>佐川急便BtoC FBA納品送料/個</strong>：`
        + `3辺合計 ${s.threeSum}cm → ${s.label} = <strong>¥${s.fee.toLocaleString()}</strong>`;
    }
    const fdInput  = document.getElementById("fba-domestic-shipping");
    const fdDetail = document.getElementById("fba-domestic-shipping-detail");
    if (fdInput) fdInput.value = s.fee;
    if (fdDetail) fdDetail.textContent = `3辺合計（梱包後）${s.threeSum}cm → ${s.label} = ¥${s.fee.toLocaleString()}/個`;

  } else {
    // ── 快速船便（デフォルト）──
    if (containerBox) containerBox.style.display = "none";
    if (sagawaBox)    sagawaBox.style.display    = "none";

    const vol = l * w * h;
    const volKg = vol / 6000;
    const actKg = g / 1000;
    const chargeKg = Math.max(volKg, actKg);
    const chargeKgStr = chargeKg.toFixed(2);

    if (display) {
      display.textContent = `容積重量 ${volKg.toFixed(2)}kg / 実重量 ${actKg.toFixed(2)}kg → 課金重量 ${chargeKgStr}kg`;
    }

    const FAST_SEA_RATE = 250;
    const intlPerUnit = Math.round(chargeKg * FAST_SEA_RATE);
    if (fastSeaBox) {
      fastSeaBox.style.display = "block";
      fastSeaBox.innerHTML = `🚢 <strong>快速船便 国際送料/個</strong>：課金重量 ${chargeKgStr}kg × ¥${FAST_SEA_RATE}/kg = <strong>¥${intlPerUnit.toLocaleString()}</strong>`;
    }
    if (intlRow)  intlRow.style.display = "block";
    if (intlInput && !intlInput.dataset.manuallyEdited) intlInput.value = intlPerUnit;

    // ── FBA納品送料（国内作業所→FBA：ヤマトパートナーキャリア 140サイズ） ──
    const BOX_L = 56, BOX_W = 42, BOX_H = 42;
    const BOX_RATE = 1500;
    const BOX_MAX_G = 25000;
    const dimArr = [l, w, h];
    const perms = [[0,1,2],[0,2,1],[1,0,2],[1,2,0],[2,0,1],[2,1,0]];
    let maxByDim = 0;
    for (const [a, b, c] of perms) {
      const cnt = Math.floor(BOX_L / dimArr[a]) * Math.floor(BOX_W / dimArr[b]) * Math.floor(BOX_H / dimArr[c]);
      if (cnt > maxByDim) maxByDim = cnt;
    }
    const byWeight = Math.floor(BOX_MAX_G / g);
    const itemsPerBox = Math.max(1, Math.min(maxByDim, byWeight));
    const fdShipping = Math.ceil(BOX_RATE / itemsPerBox);

    const fdInput  = document.getElementById("fba-domestic-shipping");
    const fdDetail = document.getElementById("fba-domestic-shipping-detail");
    if (fdInput)  fdInput.value = fdShipping;
    if (fdDetail) fdDetail.textContent = `¥${BOX_RATE.toLocaleString()} ÷ ${itemsPerBox}個/箱 = ¥${fdShipping.toLocaleString()}/個（140サイズ箱 ${BOX_L}×${BOX_W}×${BOX_H}cm）`;
  }

  recalcDomesticShipping();
}

function recalcJpy() {
  const cny = parseFloat(document.getElementById("purchase-price-cny")?.value) || 0;
  const rate = parseFloat(document.getElementById("exchange-rate")?.value) || 0;
  const jpy = Math.round(cny * rate);
  const el = document.getElementById("purchase-price-jpy");
  if (el) el.value = jpy > 0 ? jpy : "";
  recalcAgentFee();
  recalcDomesticShipping();
}

function recalcAgentFee() {
  const jpy  = parseFloat(document.getElementById("purchase-price-jpy")?.value) || 0;
  const rate = parseFloat(document.getElementById("agent-fee-rate")?.value) || 5;
  const fee  = Math.round(jpy * rate / 100);
  const el   = document.getElementById("agent-fee-jpy");
  if (el) el.value = fee > 0 ? fee : "";
}

function recalcDomesticShipping() {
  const jpy = parseFloat(document.getElementById("purchase-price-jpy")?.value) || 0;
  const rate = parseFloat(document.getElementById("domestic-shipping-rate")?.value) || 10;
  const domestic = Math.round(jpy * rate / 100);
  const el = document.getElementById("domestic-shipping-jpy");
  if (el) el.value = domestic > 0 ? domestic : "";
}

function updateCustomsDisplay() {
  const sel = document.getElementById("customs-category");
  const opt = sel?.options[sel.selectedIndex];
  const display = document.getElementById("customs-rate-display");
  if (!opt?.value || !display) return;
  const cat = state.customsCategories.find(c => c.key === opt.value);
  if (cat) {
    display.textContent = `関税 ${(cat.customs_rate * 100).toFixed(1)}% + 消費税 10% = 合計 ${(cat.total_rate * 100).toFixed(1)}%`;
  }
}

function onAcosChange() {
  const r = state.lastAnalysisResult;
  if (!r) return;

  const acosPct  = parseFloat(document.getElementById("total-acos")?.value) || 20;
  const acosRate = acosPct / 100;
  const adCost   = Math.round(r.amazon_price * acosRate);
  const netProfit = Math.round(r.profit_before_ad - adCost);
  const netProfitRate = r.amazon_price > 0 ? (netProfit / r.amazon_price * 100) : 0;
  const roi = r.purchase_price_jpy > 0 ? (netProfit / r.purchase_price_jpy * 100) : 0;
  const monthlyNetProfit = Math.round(netProfit * (r.monthly?.estimated_sales || 0));

  // 広告費ボックス
  document.getElementById("res-ad-cost").textContent =
    `${formatYen(adCost)}（トータルACOS ${acosPct}%）`;

  // ROIヒーロー
  const isPositive = netProfit >= 0;
  document.getElementById("res-net-profit").textContent = formatYen(netProfit);
  document.getElementById("res-net-profit").className = `roi-value ${isPositive ? "positive" : "negative"}`;
  document.getElementById("res-roi").textContent = `${roi.toFixed(1)}%`;
  document.getElementById("res-roi").className = `roi-value ${roi >= 30 ? "positive" : roi >= 0 ? "warn" : "negative"}`;
  document.getElementById("res-monthly").textContent = formatYen(monthlyNetProfit);
  document.getElementById("res-monthly").className = `roi-value ${monthlyNetProfit >= 0 ? "positive" : "negative"}`;

  // 利益サマリ
  const c = r.costs;
  document.getElementById("profit-summary-body").innerHTML = `
    <tr class="selling-row"><td>Amazon販売価格</td><td>${formatYen(r.amazon_price)}</td></tr>
    <tr><td>総コスト（広告費前）</td><td style="color:var(--danger)">${formatYen(c.total_before_ad)}</td></tr>
    <tr><td>広告費前利益</td><td style="font-weight:700">${formatYen(r.profit_before_ad)}（${r.profit_rate_before_ad}%）</td></tr>
    <tr><td>広告費 / 個（ACOS ${acosPct}%）</td><td style="color:var(--danger)">${formatYen(adCost)}</td></tr>
    <tr class="total-row profit-row"><td>純利益 / 個</td><td>${formatYen(netProfit)}（${netProfitRate.toFixed(1)}%）</td></tr>
    <tr><td>ROI（仕入れ対比）</td><td style="font-weight:700;color:${roi >= 30 ? 'var(--success)' : roi >= 0 ? 'var(--warning)' : 'var(--danger)'}">${roi.toFixed(1)}%</td></tr>
    <tr><td>月間純利益推計（${r.monthly.estimated_sales}個販売時）</td><td style="font-weight:700">${formatYen(monthlyNetProfit)}</td></tr>
  `;
}

// ── Amazon画像表示 & クロップ保存 ──────────────────────────
let _cropRect = null; // {x1,y1,x2,y2} 0〜1の比率

function setAmazonImage(imageUrl) {
  const img = document.getElementById("amazon-product-image");
  const preview = document.getElementById("amazon-product-preview");
  if (img && imageUrl) {
    // サーバープロキシ経由で取得（Canvas描画のCORS回避）
    const proxiedUrl = `/api/research/image-proxy?url=${encodeURIComponent(imageUrl)}`;
    img.crossOrigin = "anonymous";
    img.src = proxiedUrl;
    img.onerror = () => { if (preview) preview.style.display = "none"; };
    img.onload = () => initCropTool();
    if (preview) preview.style.display = "block";
    clearCrop();
  }
}

function initCropTool() {
  const container = document.getElementById("crop-container");
  if (!container) return;
  if (container._cropInited) return;
  container._cropInited = true;

  const overlay = document.getElementById("crop-selection");
  let dragging = false, sx = 0, sy = 0;

  container.addEventListener("mousedown", e => {
    e.preventDefault();
    dragging = true;
    const r = container.getBoundingClientRect();
    sx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    sy = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
    overlay.style.display = "none";
    _cropRect = null;
  });

  // documentで拾うことでカーソルが画像外に出ても追跡できる
  document.addEventListener("mousemove", e => {
    if (!dragging) return;
    const r = container.getBoundingClientRect();
    const cx = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    const cy = Math.max(0, Math.min(1, (e.clientY - r.top) / r.height));
    const x1 = Math.min(sx, cx), y1 = Math.min(sy, cy);
    const x2 = Math.max(sx, cx), y2 = Math.max(sy, cy);
    Object.assign(overlay.style, {
      display: "block",
      left: `${x1 * 100}%`, top: `${y1 * 100}%`,
      width: `${(x2 - x1) * 100}%`, height: `${(y2 - y1) * 100}%`,
    });
    _cropRect = { x1, y1, x2, y2 };
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    if (!_cropRect || (_cropRect.x2 - _cropRect.x1) < 0.03 || (_cropRect.y2 - _cropRect.y1) < 0.03) {
      clearCrop(); return;
    }
    document.getElementById("crop-hint").textContent = "✓ 範囲指定済み";
    document.getElementById("btn-save-crop").style.display = "inline-block";
    document.getElementById("btn-clear-crop").style.display = "inline-block";
  });
}

function clearCrop() {
  _cropRect = null;
  const overlay = document.getElementById("crop-selection");
  if (overlay) overlay.style.display = "none";
  const hint = document.getElementById("crop-hint");
  if (hint) hint.textContent = "ドラッグして切り抜き範囲を指定";
  const btnSave = document.getElementById("btn-save-crop");
  if (btnSave) btnSave.style.display = "none";
  const btnClear = document.getElementById("btn-clear-crop");
  if (btnClear) btnClear.style.display = "none";
}

async function saveCroppedImage() {
  const img = document.getElementById("amazon-product-image");
  if (!img || !_cropRect) return;

  // 元画像の実ピクセルサイズで切り抜き
  const naturalW = img.naturalWidth;
  const naturalH = img.naturalHeight;
  const sx = Math.round(_cropRect.x1 * naturalW);
  const sy = Math.round(_cropRect.y1 * naturalH);
  const sw = Math.round((_cropRect.x2 - _cropRect.x1) * naturalW);
  const sh = Math.round((_cropRect.y2 - _cropRect.y1) * naturalH);

  // Canvasで切り抜き
  const canvas = document.createElement("canvas");
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);

  // Blobに変換
  const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));

  // 保存ダイアログ（showSaveFilePicker対応ブラウザ）
  const suggestedName = (state._cropFilename || "画像検索") + ".png";
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName,
        types: [{ description: "PNG画像", accept: { "image/png": [".png"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      showToast("画像を保存しました", "success");
    } catch (e) {
      if (e.name !== "AbortError") showToast("保存に失敗しました: " + e.message, "error");
    }
  } else {
    // フォールバック：ダウンロードリンク
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = suggestedName;
    a.click();
    URL.revokeObjectURL(url);
    showToast("画像をダウンロードしました", "success");
  }
}
// ────────────────────────────────────────────────────────


async function runAnalysis() {
  const amazonPrice = parseFloat(document.getElementById("amazon-price")?.value) || 0;
  const purchaseCny = parseFloat(document.getElementById("purchase-price-cny")?.value) || 0;

  if (amazonPrice <= 0) { showToast("Amazon販売価格を入力してください", "error"); return; }
  if (purchaseCny <= 0) { showToast("1688仕入れ単価を入力してください", "error"); return; }

  const btn = document.getElementById("btn-analyze");
  setLoading(btn, true);

  const payload = {
    amazon_price: amazonPrice,
    amazon_category_key: document.getElementById("amazon-category")?.value || "other",
    review_count: parseInt(document.getElementById("competitor-reviews")?.value) || 50,
    seller_count: parseInt(document.getElementById("seller-count")?.value) || 2,
    estimated_monthly_sales: parseInt(document.getElementById("monthly-sales")?.value) || 0,
    dimensions: {
      length: parseFloat(document.getElementById("dim-length")?.value) || 10,
      width: parseFloat(document.getElementById("dim-width")?.value) || 10,
      height: parseFloat(document.getElementById("dim-height")?.value) || 10,
      weight_g: parseFloat(document.getElementById("dim-weight")?.value) || 200,
    },
    purchase_price_cny: purchaseCny,
    order_quantity: parseInt(document.getElementById("order-quantity")?.value) || 100,
    shipping_method: document.getElementById("shipping-method")?.value || "fast_sea",
    inspection_fee_per_unit: parseFloat(document.getElementById("inspection-fee")?.value) || 30,
    fba_domestic_shipping_per_unit: parseFloat(document.getElementById("fba-domestic-shipping")?.value) || 0,
    intl_shipping_override: parseFloat(document.getElementById("intl-shipping-input")?.value) || null,
    customs_category: document.getElementById("customs-category")?.value || "other",
    agent_fee_jpy: parseFloat(document.getElementById("agent-fee-jpy")?.value) || 0,
    domestic_shipping_jpy: parseFloat(document.getElementById("domestic-shipping-jpy")?.value) || 0,
    total_acos: (parseFloat(document.getElementById("total-acos")?.value) || 20) / 100,
  };

  try {
    const result = await apiPost("/api/research/analyze", payload);
    renderAnalysisResult(result);
    document.getElementById("analyze-placeholder").style.display = "none";
    document.getElementById("analyze-result").style.display = "block";
    document.getElementById("analyze-result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch(e) {
    showToast(`計算失敗: ${e.message}`, "error");
  } finally {
    setLoading(btn, false);
  }
}

function renderAnalysisResult(r) {
  state.lastAnalysisResult = r;
  const saveBtn = document.getElementById("btn-save-result");
  if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = "💾 この結果を保存する"; }
  const isPositive = r.net_profit >= 0;

  // ROIヒーロー
  document.getElementById("res-net-profit").textContent = formatYen(r.net_profit);
  document.getElementById("res-net-profit").className = `roi-value ${isPositive ? "positive" : "negative"}`;
  document.getElementById("res-roi").textContent = `${r.roi}%`;
  document.getElementById("res-roi").className = `roi-value ${r.roi >= 30 ? "positive" : r.roi >= 0 ? "warn" : "negative"}`;
  document.getElementById("res-monthly").textContent = formatYen(r.monthly.net_profit);
  document.getElementById("res-monthly").className = `roi-value ${r.monthly.net_profit >= 0 ? "positive" : "negative"}`;

  // コスト内訳
  const c = r.costs;
  document.getElementById("cost-breakdown-body").innerHTML = `
    <tr><td>仕入れ単価</td><td>${formatYen(c.purchase_price_jpy)}（￥${r.purchase_price_cny}元 × ${r.exchange_rate}円）</td></tr>
    ${c.agent_fee_jpy > 0 ? `<tr><td>代行業者手数料</td><td>${formatYen(c.agent_fee_jpy)}</td></tr>` : ''}
    <tr><td>国際送料 / 個</td><td>${formatYen(c.intl_shipping_per_unit)}（${r.shipping_detail.method}${r.shipping_detail.chargeable_weight_kg != null ? ` / ${r.shipping_detail.chargeable_weight_kg}kg` : ` / ${r.shipping_detail.total_cbm}㎥`}）</td></tr>
    <tr><td>関税・消費税</td><td>${formatYen(c.customs_amount)}（${c.customs_rate_pct}%）</td></tr>
    <tr><td>国内検品費用</td><td>${formatYen(c.inspection_fee)}</td></tr>
    ${c.fba_domestic_shipping > 0 ? `<tr><td>FBA納品送料</td><td>${formatYen(c.fba_domestic_shipping)}（${r.shipping_detail.fba_domestic_method || 'ヤマトパートナーキャリア 140サイズ'}）</td></tr>` : ''}
    <tr><td>Amazon手数料</td><td>${formatYen(c.referral_fee)}（${c.referral_rate_pct}%）</td></tr>
    <tr><td>FBA送料</td><td>${formatYen(c.fba_fee)}（${c.fba_size}サイズ）</td></tr>
    <tr class="total-row cost-row"><td>総コスト（広告費前）</td><td>${formatYen(c.total_before_ad)}</td></tr>
  `;

  // ACOSをAPIの計算値でセットしてから再描画
  const acosInput = document.getElementById("total-acos");
  if (acosInput) acosInput.value = r.ad_info.total_acos_pct;
  onAcosChange();

  // OEMパネルを表示（結果が出たタイミングで）
  const oemPanel = document.getElementById("oem-panel");
  if (oemPanel) {
    oemPanel.style.display = "block";
    // Q&AのASINを表示
    const asin = state.selectedProduct?.asin;
    const qaPlaceholder = document.getElementById("qa-placeholder");
    if (qaPlaceholder) {
      qaPlaceholder.textContent = asin
        ? `ASIN: ${asin} のQ&Aを取得します。「取得する」を押してください`
        : "商品リサーチから選択した商品のみQ&Aを取得できます";
    }
    const qaBtn = document.getElementById("btn-qa-fetch");
    if (qaBtn) qaBtn.disabled = !asin;
  }
}


/* =============================================
   ウォッチリスト（提案D）
   ============================================= */

function loadWatchlistFromStorage() {
  try {
    const raw = localStorage.getItem("watchlist_v1");
    state.watchlist = raw ? JSON.parse(raw) : [];
  } catch(e) {
    state.watchlist = [];
  }
  renderWatchlistBadge();
}

function saveWatchlistToStorage() {
  localStorage.setItem("watchlist_v1", JSON.stringify(state.watchlist));
}

function isInWatchlist(asin) {
  return state.watchlist.some(p => p.asin === asin);
}

function toggleWatchlist(p, btnId) {
  if (isInWatchlist(p.asin)) {
    state.watchlist = state.watchlist.filter(item => item.asin !== p.asin);
    showToast("ウォッチリストから削除しました", "success");
    const btn = document.getElementById(btnId);
    if (btn) { btn.style.background = "#fff"; btn.innerHTML = "☆ ウォッチ"; }
  } else {
    state.watchlist.push({ ...p, saved_at: new Date().toISOString() });
    showToast("ウォッチリストに追加しました ⭐", "success");
    const btn = document.getElementById(btnId);
    if (btn) { btn.style.background = "#fef9c3"; btn.innerHTML = "⭐ ウォッチ"; }
  }
  saveWatchlistToStorage();
  renderWatchlistBadge();
  // ウォッチリストタブが表示中なら再描画
  if (document.getElementById("tab-watchlist")?.style.display !== "none") renderWatchlist();
}

function renderWatchlistBadge() {
  const badge = document.getElementById("watchlist-badge");
  if (!badge) return;
  const count = state.watchlist.length;
  badge.textContent = count;
  badge.style.display = count > 0 ? "inline" : "none";
}

function renderWatchlist() {
  const grid  = document.getElementById("watchlist-grid");
  const empty = document.getElementById("watchlist-empty");
  if (!grid || !empty) return;

  if (state.watchlist.length === 0) {
    grid.style.display = "none";
    empty.style.display = "block";
    return;
  }

  empty.style.display = "none";
  grid.style.display  = "";
  grid.innerHTML = "";
  // 新しい順に表示
  [...state.watchlist].reverse().forEach(p => {
    const card = buildProductCardEl(p);
    grid.appendChild(card);
  });
}

function clearWatchlist() {
  if (!confirm(`ウォッチリスト（${state.watchlist.length}件）を全て削除しますか？`)) return;
  state.watchlist = [];
  saveWatchlistToStorage();
  renderWatchlistBadge();
  renderWatchlist();
}

// ウォッチリストタブを開いたとき再描画
(function patchTabSetup() {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tab-btn").forEach(btn => {
      if (btn.dataset.tab === "watchlist") {
        btn.addEventListener("click", renderWatchlist);
      }
    });
  }, true);
})();

/* =============================================
   計算結果の手動保存（提案C）
   ============================================= */

async function saveCurrentResult() {
  const r = state.lastAnalysisResult;
  if (!r) { showToast("先に計算を実行してください", "error"); return; }

  const btn = document.getElementById("btn-save-result");
  if (btn) { btn.disabled = true; btn.textContent = "保存中..."; }

  const productName  = document.getElementById("product-title")?.value || "";
  const url1688      = state._last1688SearchUrl || "";

  try {
    const res = await apiPost("/api/profit/save", {
      product_name:  productName,
      product_url_1688: url1688,
      platform:      "amazon",
      selling_price: r.amazon_price,
      total_cost:    r.costs?.total_before_ad || 0,
      profit:        r.net_profit,
      profit_rate:   r.net_profit_rate,
      detail:        r,
    });
    if (res.ok) {
      showToast(`保存しました（ID: ${res.id}）`, "success");
      if (btn) btn.textContent = "✓ 保存済み";
      // 出品済みタブが表示中なら再読み込み、そうでなければバッジだけ更新
      const listedTab = document.getElementById("tab-listed");
      if (listedTab && listedTab.style.display !== "none") {
        loadListedHistory();
      } else {
        // バッジカウントをインクリメント
        const badge = document.getElementById("listed-badge");
        if (badge) {
          const cur = parseInt(badge.textContent || "0", 10);
          renderListedBadge(cur + 1);
        }
      }
    } else {
      showToast(`保存失敗: ${res.error}`, "error");
      if (btn) { btn.disabled = false; btn.textContent = "💾 この結果を保存する"; }
    }
  } catch(e) {
    showToast(`保存失敗: ${e.message}`, "error");
    if (btn) { btn.disabled = false; btn.textContent = "💾 この結果を保存する"; }
  }
}

/* =============================================
   出品済み管理タブ
   ============================================= */

async function loadListedHistory() {
  const loading = document.getElementById("listed-loading");
  const empty   = document.getElementById("listed-empty");
  const list    = document.getElementById("listed-list");
  if (!list) return;

  if (loading) loading.style.display = "block";
  if (empty)   empty.style.display   = "none";
  list.style.display = "none";
  list.innerHTML = "";

  try {
    const data = await apiGet("/api/profit/history");
    const items = data.history || [];
    renderListedBadge(items.length);

    if (loading) loading.style.display = "none";

    if (items.length === 0) {
      if (empty) empty.style.display = "block";
      return;
    }

    list.style.display = "flex";
    items.forEach(item => {
      list.appendChild(buildListedCardEl(item));
    });
  } catch(e) {
    if (loading) loading.style.display = "none";
    if (empty) {
      empty.style.display = "block";
      empty.innerHTML = `<div style="font-size:32px;margin-bottom:8px">⚠️</div><div>読み込みに失敗しました: ${e.message}</div>`;
    }
  }
}

function buildListedCardEl(item) {
  const card = document.createElement("div");
  card.style.cssText = "background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px 20px;position:relative";

  const profitColor = item.profit >= 0 ? "#16a34a" : "#dc2626";
  const rateColor   = item.profit_rate >= 20 ? "#16a34a" : item.profit_rate >= 10 ? "#d97706" : "#dc2626";
  const roiColor    = (item.roi ?? 0) >= 50 ? "#16a34a" : (item.roi ?? 0) >= 20 ? "#d97706" : "#6b7280";

  const asinHtml = item.asin
    ? `<a href="https://www.amazon.co.jp/dp/${item.asin}" target="_blank" rel="noopener"
         style="font-size:11px;color:#2563eb;text-decoration:none;margin-left:8px">${item.asin}</a>`
    : "";

  const monthlyHtml = item.monthly_net_profit != null
    ? `<div style="display:inline-flex;align-items:center;gap:4px;background:#eff6ff;border-radius:6px;padding:4px 10px;font-size:12px">
         <span style="color:#6b7280">月間推計</span>
         <span style="font-weight:700;color:#1d4ed8">¥${Math.round(item.monthly_net_profit).toLocaleString()}</span>
       </div>`
    : "";

  card.style.cursor = "pointer";
  card.addEventListener("click", (e) => {
    if (!e.target.closest("button") && !e.target.closest("a")) openListedDetail(item.id);
  });

  card.innerHTML = `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap">
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;font-weight:700;color:#111827;margin-bottom:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${item.product_name || "（商品名未設定）"}${asinHtml}
        </div>
        <div style="font-size:11px;color:#9ca3af;margin-bottom:10px">${item.created_at}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
          <div style="display:inline-flex;align-items:center;gap:4px;background:#f9fafb;border-radius:6px;padding:4px 10px;font-size:12px">
            <span style="color:#6b7280">販売価格</span>
            <span style="font-weight:700;color:#374151">¥${Math.round(item.selling_price ?? 0).toLocaleString()}</span>
          </div>
          <div style="display:inline-flex;align-items:center;gap:4px;background:#f9fafb;border-radius:6px;padding:4px 10px;font-size:12px">
            <span style="color:#6b7280">純利益/個</span>
            <span style="font-weight:700;color:${profitColor}">¥${Math.round(item.profit ?? 0).toLocaleString()}</span>
          </div>
          <div style="display:inline-flex;align-items:center;gap:4px;background:#f9fafb;border-radius:6px;padding:4px 10px;font-size:12px">
            <span style="color:#6b7280">利益率</span>
            <span style="font-weight:700;color:${rateColor}">${(item.profit_rate ?? 0).toFixed(1)}%</span>
          </div>
          ${item.roi != null ? `
          <div style="display:inline-flex;align-items:center;gap:4px;background:#f9fafb;border-radius:6px;padding:4px 10px;font-size:12px">
            <span style="color:#6b7280">ROI</span>
            <span style="font-weight:700;color:${roiColor}">${(item.roi).toFixed(1)}%</span>
          </div>` : ""}
          ${monthlyHtml}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0">
        <button onclick="openListedDetail(${item.id})"
          style="font-size:11px;padding:4px 10px;border:1px solid #bfdbfe;border-radius:6px;background:#eff6ff;color:#1d4ed8;cursor:pointer">
          📊 詳細
        </button>
        <button onclick="deleteListedItem(${item.id}, this)"
          style="font-size:11px;padding:4px 10px;border:1px solid #fca5a5;border-radius:6px;background:#fff;color:#dc2626;cursor:pointer">
          🗑 削除
        </button>
      </div>
    </div>
  `;
  return card;
}

async function deleteListedItem(id, btn) {
  if (!confirm("この履歴を削除しますか？")) return;
  if (btn) { btn.disabled = true; btn.textContent = "削除中..."; }
  try {
    await fetch(`/api/profit/history/${id}`, { method: "DELETE" });
    const card = btn?.closest("[style]");
    if (card) card.remove();
    // バッジ更新
    const remaining = document.getElementById("listed-list")?.children.length ?? 0;
    renderListedBadge(remaining);
    if (remaining === 0) {
      const empty = document.getElementById("listed-empty");
      const list  = document.getElementById("listed-list");
      if (empty) empty.style.display = "block";
      if (list)  list.style.display  = "none";
    }
    showToast("削除しました", "success");
  } catch(e) {
    showToast(`削除失敗: ${e.message}`, "error");
    if (btn) { btn.disabled = false; btn.textContent = "🗑 削除"; }
  }
}

async function openListedDetail(id) {
  const modal = document.getElementById("listed-detail-modal");
  if (!modal) return;
  modal.style.display = "block";
  document.getElementById("modal-product-name").textContent = "読み込み中...";
  document.getElementById("modal-product-date").textContent = "";

  try {
    const data = await apiGet(`/api/profit/history/${id}`);
    state.modalResult = data;
    document.getElementById("modal-product-name").textContent = data.product_name || "（商品名未設定）";
    document.getElementById("modal-product-date").textContent = data.created_at || "";
    renderModalResult(data);
  } catch(e) {
    document.getElementById("modal-product-name").textContent = `読み込み失敗: ${e.message}`;
  }
}

function closeListedModal() {
  const modal = document.getElementById("listed-detail-modal");
  if (modal) modal.style.display = "none";
  state.modalResult = null;
}

function renderModalResult(r) {
  // コスト内訳
  const c = r.costs || {};
  document.getElementById("modal-cost-breakdown-body").innerHTML = `
    <tr><td>仕入れ単価</td><td>${formatYen(c.purchase_price_jpy ?? 0)}（¥${r.purchase_price_cny ?? "—"}元 × ${r.exchange_rate ?? "—"}円）</td></tr>
    ${(c.agent_fee_jpy ?? 0) > 0 ? `<tr><td>代行業者手数料</td><td>${formatYen(c.agent_fee_jpy)}</td></tr>` : ''}
    ${(c.domestic_shipping_jpy ?? 0) > 0 ? `<tr><td>中国国内送料</td><td>${formatYen(c.domestic_shipping_jpy)}</td></tr>` : ''}
    <tr><td>国際送料 / 個</td><td>${formatYen(c.intl_shipping_per_unit ?? 0)}${r.shipping_detail ? `（${r.shipping_detail.method}${r.shipping_detail.chargeable_weight_kg != null ? ` / ${r.shipping_detail.chargeable_weight_kg}kg` : r.shipping_detail.total_cbm != null ? ` / ${r.shipping_detail.total_cbm}㎥` : ''}）` : ''}</td></tr>
    <tr><td>関税・消費税</td><td>${formatYen(c.customs_amount ?? 0)}（${c.customs_rate_pct ?? 0}%）</td></tr>
    <tr><td>国内検品費用</td><td>${formatYen(c.inspection_fee ?? 0)}</td></tr>
    ${(c.fba_domestic_shipping ?? 0) > 0 ? `<tr><td>FBA納品送料</td><td>${formatYen(c.fba_domestic_shipping)}${r.shipping_detail?.fba_domestic_method ? `（${r.shipping_detail.fba_domestic_method}）` : ''}</td></tr>` : ''}
    <tr><td>Amazon手数料</td><td>${formatYen(c.referral_fee ?? 0)}（${c.referral_rate_pct ?? 0}%）</td></tr>
    <tr><td>FBA送料</td><td>${formatYen(c.fba_fee ?? 0)}${c.fba_size ? `（${c.fba_size}サイズ）` : ''}</td></tr>
    <tr class="total-row cost-row"><td>総コスト（広告費前）</td><td>${formatYen(c.total_before_ad ?? 0)}</td></tr>
  `;

  // ACOSをセット
  const acosInput = document.getElementById("modal-total-acos");
  if (acosInput) acosInput.value = r.ad_info?.total_acos_pct ?? 20;
  onModalAcosChange();
}

function onModalAcosChange() {
  const r = state.modalResult;
  if (!r) return;

  const acosPct  = parseFloat(document.getElementById("modal-total-acos")?.value) || 20;
  const acosRate = acosPct / 100;
  const adCost   = Math.round(r.amazon_price * acosRate);
  const netProfit = Math.round((r.profit_before_ad ?? 0) - adCost);
  const netProfitRate = r.amazon_price > 0 ? (netProfit / r.amazon_price * 100) : 0;
  const roi = (r.purchase_price_jpy ?? 0) > 0 ? (netProfit / r.purchase_price_jpy * 100) : 0;
  const monthlyNetProfit = Math.round(netProfit * (r.monthly?.estimated_sales || 0));

  document.getElementById("modal-res-ad-cost").textContent =
    `${formatYen(adCost)}（トータルACOS ${acosPct}%）`;

  const isPositive = netProfit >= 0;
  document.getElementById("modal-res-net-profit").textContent = formatYen(netProfit);
  document.getElementById("modal-res-net-profit").className = `roi-value ${isPositive ? "positive" : "negative"}`;
  document.getElementById("modal-res-roi").textContent = `${roi.toFixed(1)}%`;
  document.getElementById("modal-res-roi").className = `roi-value ${roi >= 30 ? "positive" : roi >= 0 ? "warn" : "negative"}`;
  document.getElementById("modal-res-monthly").textContent = formatYen(monthlyNetProfit);
  document.getElementById("modal-res-monthly").className = `roi-value ${monthlyNetProfit >= 0 ? "positive" : "negative"}`;

  const c = r.costs || {};
  document.getElementById("modal-profit-summary-body").innerHTML = `
    <tr class="selling-row"><td>Amazon販売価格</td><td>${formatYen(r.amazon_price ?? 0)}</td></tr>
    <tr><td>総コスト（広告費前）</td><td style="color:var(--danger)">${formatYen(c.total_before_ad ?? 0)}</td></tr>
    <tr><td>広告費前利益</td><td style="font-weight:700">${formatYen(r.profit_before_ad ?? 0)}（${r.profit_rate_before_ad ?? 0}%）</td></tr>
    <tr><td>広告費 / 個（ACOS ${acosPct}%）</td><td style="color:var(--danger)">${formatYen(adCost)}</td></tr>
    <tr class="total-row profit-row"><td>純利益 / 個</td><td>${formatYen(netProfit)}（${netProfitRate.toFixed(1)}%）</td></tr>
    <tr><td>ROI（仕入れ対比）</td><td style="font-weight:700;color:${roi >= 30 ? 'var(--success)' : roi >= 0 ? 'var(--warning)' : 'var(--danger)'}">${roi.toFixed(1)}%</td></tr>
    <tr><td>月間純利益推計（${r.monthly?.estimated_sales ?? 0}個販売時）</td><td style="font-weight:700">${formatYen(monthlyNetProfit)}</td></tr>
  `;
}

function renderListedBadge(count) {
  const badge = document.getElementById("listed-badge");
  if (!badge) return;
  badge.textContent = count;
  badge.style.display = count > 0 ? "inline" : "none";
}

// ESCキーでモーダルを閉じる
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeListedModal();
});

// タブを開いたとき自動読み込み
(function patchListedTab() {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".tab-btn").forEach(btn => {
      if (btn.dataset.tab === "listed") {
        btn.addEventListener("click", loadListedHistory);
      }
    });
  }, true);
})();

/* =============================================
   OEM改善案 & Amazon Q&A
   ============================================= */

function _getOemContext() {
  const title    = document.getElementById("product-title")?.value || "";
  const catSel   = document.getElementById("amazon-category");
  const category = catSel?.options[catSel.selectedIndex]?.text || "不明";
  // 同カテゴリの競合タイトルを最大6件
  const catKey = catSel?.value || "";
  const rivals = state.browseResults
    .filter(p => (p.category_path || p.category || "").includes(catKey) || catKey === "")
    .slice(0, 6)
    .map(p => p.title);
  return { product_title: title, category, competitor_titles: rivals };
}

function _buildOemCardHtml(s, idx, productTitle, category) {
  const costColor = s.cost_impact?.startsWith("低") ? "#166534"
                  : s.cost_impact?.startsWith("中") ? "#d97706" : "#dc2626";
  const costBg    = s.cost_impact?.startsWith("低") ? "#dcfce7"
                  : s.cost_impact?.startsWith("中") ? "#fef9c3" : "#fee2e2";
  const uid = idx ?? Math.random().toString(36).slice(2,8);
  const deepdiveId = `oem-deepdive-${uid}`;
  const esc = (v) => (v || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  return `
    <div style="background:#f8f7ff;border:1px solid #c7d2fe;border-radius:8px;padding:12px 14px">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px">
        <div style="font-weight:700;color:#3730a3;font-size:13px">💡 ${s.title || ""}</div>
        <span style="background:${costBg};color:${costColor};font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap;flex-shrink:0">
          コスト ${s.cost_impact || "—"}
        </span>
      </div>
      <div style="font-size:12px;color:#374151;margin-bottom:4px">📝 ${s.description || ""}</div>
      <div style="font-size:12px;color:#6b7280;margin-bottom:8px">→ ${s.reason || ""}</div>
      <button onclick="deepdiveOemSuggestion('${deepdiveId}','${esc(productTitle)}','${esc(category)}','${esc(s.title)}','${esc(s.description)}')"
        id="btn-deepdive-${deepdiveId}"
        style="font-size:11px;background:#ede9fe;color:#5b21b6;border:1px solid #c4b5fd;border-radius:4px;padding:3px 10px;cursor:pointer">
        🔍 深掘り ▼
      </button>
      <div id="${deepdiveId}" style="display:none;margin-top:10px;padding:10px 12px;background:#fafafa;border:1px solid #e5e7eb;border-radius:6px;font-size:12px"></div>
    </div>`;
}

async function deepdiveOemSuggestion(deepdiveId, productTitle, category, suggestionTitle, suggestionDesc) {
  const panel = document.getElementById(deepdiveId);
  const btn   = document.getElementById(`btn-deepdive-${deepdiveId}`);
  if (!panel) return;

  // トグル：展開済みなら閉じる
  if (panel.style.display === "block") {
    panel.style.display = "none";
    if (btn) btn.textContent = "🔍 深掘り ▼";
    return;
  }

  // すでにコンテンツがあれば再取得しない
  if (panel.dataset.loaded === "1") {
    panel.style.display = "block";
    if (btn) btn.textContent = "🔍 深掘り ▲";
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = "取得中..."; }
  panel.innerHTML = `<div style="color:#9ca3af;text-align:center;padding:8px">生成中...</div>`;
  panel.style.display = "block";

  try {
    const data = await apiPost("/api/oem/deepdive", {
      product_title: productTitle,
      category: category,
      suggestion_title: suggestionTitle,
      suggestion_description: suggestionDesc,
    });
    panel.innerHTML = _buildDeepdiveHtml(data);
    panel.dataset.loaded = "1";
    if (btn) { btn.disabled = false; btn.textContent = "🔍 深掘り ▲"; }
  } catch(e) {
    panel.innerHTML = `<div style="color:#dc2626">エラー: ${e.message}</div>`;
    if (btn) { btn.disabled = false; btn.textContent = "🔍 深掘り ▼"; }
  }
}

function _buildDeepdiveHtml(d) {
  const ul = (items) => (items || []).map(t => `<li style="margin-bottom:3px">${t}</li>`).join("");
  const reviews = (d.review_improvements || []).map(r => {
    const icon = r.resolved ? "✅" : "⚠️";
    return `<li style="margin-bottom:4px">${icon} 「${r.review}」<br>
      <span style="color:#6b7280;font-size:11px;margin-left:12px">→ ${r.note || ""}</span></li>`;
  }).join("");

  return `
    <div style="margin-bottom:8px">
      <div style="font-weight:700;color:#b45309;margin-bottom:4px">⚠️ リスク・注意点</div>
      <ul style="margin:0;padding-left:16px;color:#374151;line-height:1.6">${ul(d.risks)}</ul>
    </div>
    <div style="margin-bottom:8px">
      <div style="font-weight:700;color:#0369a1;margin-bottom:4px">🎯 訴求できるポイント</div>
      <ul style="margin:0;padding-left:16px;color:#374151;line-height:1.6">${ul(d.appeals)}</ul>
    </div>
    <div style="margin-bottom:8px">
      <div style="font-weight:700;color:#059669;margin-bottom:4px">😊 解決するお悩み</div>
      <ul style="margin:0;padding-left:16px;color:#374151;line-height:1.6">${ul(d.problems_solved)}</ul>
    </div>
    <div>
      <div style="font-weight:700;color:#7c3aed;margin-bottom:4px">📝 改善できるバッドレビュー（想定）</div>
      <ul style="margin:0;padding-left:16px;color:#374151;line-height:1.6">${reviews}</ul>
    </div>`;
}

function _buildQaCardHtml(qa) {
  return `
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:10px 14px">
      <div style="font-weight:700;font-size:12px;color:#0369a1;margin-bottom:4px">Q: ${qa.question || ""}</div>
      <div style="font-size:12px;color:#374151">A: ${qa.answer || "（回答なし）"}</div>
    </div>`;
}

async function generateOemSuggestions() {
  const ctx = _getOemContext();
  if (!ctx.product_title.trim()) { showToast("先に利益計算を実行してください（商品名が必要です）", "error"); return; }

  const loading     = document.getElementById("oem-loading");
  const error       = document.getElementById("oem-error");
  const results     = document.getElementById("oem-results");
  const cards       = document.getElementById("oem-cards");
  const placeholder = document.getElementById("oem-placeholder");
  const btn         = document.getElementById("btn-oem-generate");

  loading.style.display     = "block";
  error.style.display       = "none";
  results.style.display     = "none";
  placeholder.style.display = "none";
  if (btn) { btn.disabled = true; btn.textContent = "生成中..."; }

  try {
    const data = await apiPost("/api/oem/suggest", ctx);
    const suggestions = data.suggestions || [];
    if (suggestions.length === 0) throw new Error("提案が生成されませんでした");
    cards.innerHTML = suggestions.map((s, i) => _buildOemCardHtml(s, i, ctx.product_title, ctx.category)).join("");
    results.style.display = "block";
  } catch(e) {
    error.textContent = `エラー: ${e.message}`;
    error.style.display = "block";
    placeholder.style.display = "block";
  } finally {
    loading.style.display = "none";
    if (btn) { btn.disabled = false; btn.textContent = "✨ 再生成"; }
  }
}

async function fetchAmazonQA() {
  const asin = state.selectedProduct?.asin;
  if (!asin) { showToast("商品リサーチから商品を選択してください", "error"); return; }

  const loading     = document.getElementById("qa-loading");
  const error       = document.getElementById("qa-error");
  const list        = document.getElementById("qa-list");
  const placeholder = document.getElementById("qa-placeholder");
  const btn         = document.getElementById("btn-qa-fetch");

  loading.style.display     = "block";
  error.style.display       = "none";
  placeholder.style.display = "none";
  list.innerHTML             = "";
  if (btn) { btn.disabled = true; btn.textContent = "取得中..."; }

  try {
    const data = await apiPost("/api/oem/qa", { asin });
    const items = data.qa || [];
    if (items.length === 0) {
      list.innerHTML = `<div style="color:#9ca3af;font-size:13px;text-align:center;padding:12px">Q&Aが見つかりませんでした</div>`;
    } else {
      list.innerHTML = items.map(_buildQaCardHtml).join("");
    }
    document.getElementById("qa-results").style.display = "block";
  } catch(e) {
    error.textContent = `エラー: ${e.message}`;
    error.style.display = "block";
    placeholder.style.display = "block";
  } finally {
    loading.style.display = "none";
    if (btn) { btn.disabled = false; btn.textContent = "取得する"; }
  }
}

// ---- 出品済みモーダル用 ----

async function generateOemSuggestionsModal() {
  const r = state.modalResult;
  if (!r) return;

  const title    = r.product_name || "";
  const category = r.amazon_category || "不明";

  const loading     = document.getElementById("modal-oem-loading");
  const error       = document.getElementById("modal-oem-error");
  const cards       = document.getElementById("modal-oem-cards");
  const placeholder = document.getElementById("modal-oem-placeholder");

  loading.style.display     = "block";
  error.style.display       = "none";
  cards.innerHTML            = "";
  placeholder.style.display = "none";

  try {
    const data = await apiPost("/api/oem/suggest", { product_title: title, category, competitor_titles: [] });
    const suggestions = data.suggestions || [];
    cards.innerHTML = suggestions.length
      ? suggestions.map((s, i) => _buildOemCardHtml(s, `modal${i}`, title, category)).join("")
      : `<div style="color:#9ca3af;font-size:13px">提案が生成されませんでした</div>`;
  } catch(e) {
    error.textContent = `エラー: ${e.message}`;
    error.style.display = "block";
    placeholder.style.display = "block";
  } finally {
    loading.style.display = "none";
  }
}

async function fetchAmazonQAModal() {
  const r = state.modalResult;
  if (!r) return;

  const asin = r.asin || "";
  if (!asin) {
    showToast("このデータにASINが含まれていません", "error");
    return;
  }

  const loading     = document.getElementById("modal-qa-loading");
  const error       = document.getElementById("modal-qa-error");
  const list        = document.getElementById("modal-qa-list");
  const placeholder = document.getElementById("modal-qa-placeholder");

  loading.style.display     = "block";
  error.style.display       = "none";
  list.innerHTML             = "";
  placeholder.style.display = "none";

  try {
    const data = await apiPost("/api/oem/qa", { asin });
    const items = data.qa || [];
    list.innerHTML = items.length
      ? items.map(_buildQaCardHtml).join("")
      : `<div style="color:#9ca3af;font-size:13px;text-align:center;padding:12px">Q&Aが見つかりませんでした</div>`;
  } catch(e) {
    error.textContent = `エラー: ${e.message}`;
    error.style.display = "block";
    placeholder.style.display = "block";
  } finally {
    loading.style.display = "none";
  }
}

/* ===== ユーティリティ ===== */
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
