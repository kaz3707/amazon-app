/* ===== トースト通知 ===== */

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

/* ===== ボタンのローディング状態 ===== */

function setLoading(btn, loading, originalText) {
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> 取得中...`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || originalText || "";
    btn.disabled = false;
  }
}

/* ===== 数値フォーマット ===== */

function formatYen(value) {
  if (value === null || value === undefined) return "—";
  const n = Math.round(Number(value));
  return "¥" + n.toLocaleString("ja-JP");
}

function formatRate(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(1) + "%";
}
