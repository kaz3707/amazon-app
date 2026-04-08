"""
Keepa API を使った BSR（ベストセラーランキング）分析サービス。

テストモード: ASINごとに固定のモックデータを返す
本番モード: Keepa API から過去3年のBSRデータを取得し、需要パターンを分析する

判定パターン:
  通年安定  … 年間を通じてBSR変動が小さい
  季節型    … 季節性あり（夏型・冬型・年末型・年始型・春型・秋型）
  急成長    … 3年前・2年前は低調/データなし → 直近1年で急伸（新興商品）
  需要不安定 … データはあるが年をまたいでパターンが乱高下
"""
import math
import statistics
from datetime import datetime, timedelta, timezone
from config.settings import AppConfig, KeepaConfig

# Keepa時刻の基準: 2011-01-01 00:00 UTC
_KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=timezone.utc)

# ──────────────────────────────────────────
# テストモード用モックデータ（ASIN → 分析結果）
# ──────────────────────────────────────────

_TEST_DATA = {
    # 通年安定
    "B0D001": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D002": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D003": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D004": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D005": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D006": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    # 夏型（キャンプ・アウトドア）
    "B0D007": {"label": "夏型",       "peak_months": [5, 6, 7, 8], "detail": "5〜8月にBSRが大幅改善（販売増）。過去3年で同パターンを確認。"},
    "B0D008": {"label": "夏型",       "peak_months": [5, 6, 7, 8], "detail": "5〜8月にBSRが大幅改善（販売増）。過去3年で同パターンを確認。"},
    # 年始型（フィットネス：新年ブーム）
    "B0D009": {"label": "年始型",     "peak_months": [1, 2, 3],   "detail": "1〜3月（新年の運動ブーム）にBSRが改善。過去3年で同パターンを確認。"},
    # 需要不安定（腹筋ローラー：3年前好調→2年前急落→直近また上昇、乱高下）
    "B0D010": {"label": "需要不安定", "peak_months": [],           "detail": "3年前は好調だったが2年前に急落し直近また上昇。季節性ではなく需要が乱高下しています。要注意。"},
    # 通年安定
    "B0D011": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D012": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D013": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D014": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    # 急成長（マグネット車載ホルダー：MagSafe普及で直近1年急伸・3年前はデータなし）
    "B0D015": {"label": "急成長",     "peak_months": [],           "detail": "3年前・2年前はほぼデータなし。直近1年でBSRが急改善。新興カテゴリまたは新規参入商品の可能性あり。"},
    # 需要不安定（エアコン吹き出し口ホルダー：競合増加で乱高下）
    "B0D016": {"label": "需要不安定", "peak_months": [],           "detail": "過去3年でBSRの乱高下あり。年をまたいだパターンの一致なし。競合増加による価格競争の可能性あり。"},
    # 通年安定
    "B0D017": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D018": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    # 急成長（スマホリング：MagSafe対応モデルとして直近急伸）
    "B0D019": {"label": "急成長",     "peak_months": [],           "detail": "3年前・2年前は低調。直近1年でBSRが急改善。新規トレンドに乗った商品の可能性あり。"},
    # 年末型（おもちゃ：クリスマス需要）
    "B0D020": {"label": "年末型",     "peak_months": [11, 12],    "detail": "11〜12月（クリスマス商戦）にBSRが大幅改善。過去3年で同パターンを確認。"},
    "B0D021": {"label": "年末型",     "peak_months": [11, 12],    "detail": "11〜12月（クリスマス商戦）にBSRが大幅改善。過去3年で同パターンを確認。"},
    # 通年安定
    "B0D022": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D023": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D024": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D025": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D026": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    "B0D027": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
    # 夏型（旅行用品）
    "B0D028": {"label": "夏型",       "peak_months": [7, 8],      "detail": "7〜8月（旅行シーズン）にBSRが改善。過去3年で同パターンを確認。"},
    "B0D029": {"label": "夏型",       "peak_months": [7, 8],      "detail": "7〜8月（旅行シーズン）にBSRが改善。過去3年で同パターンを確認。"},
    # 通年安定
    "B0D030": {"label": "通年安定",   "peak_months": [],           "detail": "過去3年間、年間を通じてBSRが安定しています。"},
}


def analyze_bsr(asin: str) -> dict:
    """
    ASINのBSR分析を返す。

    Returns:
        {
            "label": "通年安定" | "夏型" | "年末型" | ... | "急成長" | "需要不安定",
            "peak_months": [5, 6, 7, 8],
            "peak_months_str": "5〜8月",
            "detail": "...",
            "badge_type": "stable" | "seasonal" | "growing" | "unstable",
        }
    """
    if AppConfig.TEST_MODE:
        result = _TEST_DATA.get(asin, {
            "label": "通年安定",
            "peak_months": [],
            "detail": "過去3年間、年間を通じてBSRが安定しています。",
        })
    else:
        result = _fetch_and_analyze(asin)

    label = result["label"]
    if label == "通年安定":
        badge_type = "stable"
    elif label == "急成長":
        badge_type = "growing"
    elif label == "需要不安定":
        badge_type = "unstable"
    else:
        badge_type = "seasonal"

    peak_months = result.get("peak_months", [])
    return {
        "label": label,
        "peak_months": peak_months,
        "peak_months_str": _months_to_str(peak_months),
        "detail": result.get("detail", ""),
        "badge_type": badge_type,
    }


# ──────────────────────────────────────────
# 本番モード: Keepa API 呼び出し＆分析
# ──────────────────────────────────────────

def _fetch_and_analyze(asin: str) -> dict:
    """Keepa API からBSRデータを取得して分析する。"""
    try:
        import urllib.request
        import json

        api_key = KeepaConfig.api_key
        if not api_key:
            return {"label": "データなし", "peak_months": [], "detail": "Keepa APIキーが設定されていません。"}

        url = (
            f"https://api.keepa.com/product"
            f"?key={api_key}&domain=5&asin={asin}&history=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        products = data.get("products", [])
        if not products:
            return {"label": "データなし", "peak_months": [], "detail": "Keepaに商品データがありません。"}

        csv = products[0].get("csv", [])
        bsr_series = csv[3] if len(csv) > 3 and csv[3] else []
        return _analyze_bsr_series(bsr_series)

    except Exception as e:
        return {"label": "データなし", "peak_months": [], "detail": f"Keepa取得エラー: {e}"}


def _keepa_time_to_datetime(keepa_minutes: int) -> datetime:
    return _KEEPA_EPOCH + timedelta(minutes=keepa_minutes)


def _analyze_bsr_series(bsr_series: list) -> dict:
    """
    BSR時系列データ（Keepa形式: [time, value, time, value, ...]）を分析する。

    判定フロー:
    1. 直近3年のデータを年別に分割
    2. 直近1年だけ急激に改善（3年前・2年前が低調/欠損） → 「急成長」
    3. 変動係数が低い → 「通年安定」
    4. 変動係数が高い場合、3年分の月別パターンの相関を確認
       - 相関が高い → 「季節型」
       - 相関が低い → 「需要不安定」
    """
    if not bsr_series or len(bsr_series) < 4:
        return {"label": "データなし", "peak_months": [], "detail": "BSRデータが不足しています。"}

    pairs = []
    for i in range(0, len(bsr_series) - 1, 2):
        t, v = bsr_series[i], bsr_series[i + 1]
        if t is not None and v is not None and v > 0:
            pairs.append((_keepa_time_to_datetime(t), v))

    if not pairs:
        return {"label": "データなし", "peak_months": [], "detail": "有効なBSRデータがありません。"}

    now = datetime.now(tz=timezone.utc)
    three_years_ago = now - timedelta(days=1095)

    recent3y = [(dt, bsr) for dt, bsr in pairs if dt >= three_years_ago]
    if len(recent3y) < 12:
        return {"label": "データ不足", "peak_months": [], "detail": "直近3年のBSRデータが少なすぎます。"}

    # 年別に分割（年1=3年前、年2=2年前、年3=直近1年）
    y1_end = now - timedelta(days=730)
    y2_end = now - timedelta(days=365)

    year1_bsr = [bsr for dt, bsr in recent3y if dt < y1_end]
    year2_bsr = [bsr for dt, bsr in recent3y if y1_end <= dt < y2_end]
    year3_bsr = [bsr for dt, bsr in recent3y if dt >= y2_end]

    # ── 急成長の判定 ──
    # 年3（直近）にデータがあり、年1・年2がデータなしまたは著しく高いBSR
    if year3_bsr:
        avg3 = statistics.mean(year3_bsr)
        has_old_data = len(year1_bsr) >= 6 or len(year2_bsr) >= 6

        if not has_old_data:
            # 3年前・2年前のデータがほぼない → 新規出品で急伸
            return {
                "label": "急成長",
                "peak_months": [],
                "detail": f"3年前・2年前はデータなし。直近1年でBSRが急改善（平均{int(avg3)}位）。新興商品の可能性あり。",
            }

        if year1_bsr and year2_bsr:
            avg1 = statistics.mean(year1_bsr)
            avg2 = statistics.mean(year2_bsr)
            # 直近が3年前・2年前より40%以上BSRが改善（数値が低い=よく売れる）
            if avg3 < avg1 * 0.6 and avg3 < avg2 * 0.6:
                return {
                    "label": "急成長",
                    "peak_months": [],
                    "detail": (
                        f"3年前平均BSR{int(avg1)}位 → 2年前{int(avg2)}位 → 直近{int(avg3)}位。"
                        "直近1年で大幅に伸びています。"
                    ),
                }

    # ── 全データの変動係数 ──
    all_bsr = [bsr for _, bsr in recent3y]
    mean_bsr = statistics.mean(all_bsr)
    stdev_bsr = statistics.stdev(all_bsr) if len(all_bsr) > 1 else 0
    cv = stdev_bsr / mean_bsr if mean_bsr > 0 else 0

    if cv < 0.25:
        return {"label": "通年安定", "peak_months": [], "detail": f"BSR変動係数{cv:.2f}。過去3年を通じて安定しています。"}

    # ── 月別パターン（季節性vs不安定）──
    monthly: dict[tuple, list] = {}
    for dt, bsr in recent3y:
        monthly.setdefault((dt.year, dt.month), []).append(bsr)
    monthly_avg = {k: statistics.mean(v) for k, v in monthly.items()}

    # 3年分の月別平均を3期間に分けて相関を計算
    y1_ref = now.year - 2
    y2_ref = now.year - 1
    y3_ref = now.year
    pattern1 = [monthly_avg.get((y1_ref, m)) for m in range(1, 13)]
    pattern2 = [monthly_avg.get((y2_ref, m)) for m in range(1, 13)]
    pattern3 = [monthly_avg.get((y3_ref, m)) for m in range(1, 13)]

    corr12 = _pearson_correlation_filtered(pattern1, pattern2)
    corr23 = _pearson_correlation_filtered(pattern2, pattern3)
    corr_avg = (corr12 + corr23) / 2

    if corr_avg < 0.5:
        return {
            "label": "需要不安定",
            "peak_months": [],
            "detail": f"BSR変動係数{cv:.2f}、年間パターン相関{corr_avg:.2f}。需要が年ごとに異なり不安定です。",
        }

    # ── 季節型: ピーク月特定 ──
    month_buckets: dict[int, list] = {m: [] for m in range(1, 13)}
    for (year, month), avg in monthly_avg.items():
        month_buckets[month].append(avg)

    month_avg_bsr = {m: statistics.mean(v) for m, v in month_buckets.items() if v}
    if len(month_avg_bsr) < 6:
        return {"label": "データ不足", "peak_months": [], "detail": "月別データが不足しています。"}

    overall_mean = statistics.mean(month_avg_bsr.values())
    peak_months = sorted([m for m, avg in month_avg_bsr.items() if avg < overall_mean * 0.80])

    season_label = _season_label(peak_months)
    peak_str = _months_to_str(peak_months)
    return {
        "label": season_label,
        "peak_months": peak_months,
        "detail": f"季節性あり（年間パターン相関{corr_avg:.2f}）。{peak_str}にBSRが改善（販売増）。",
    }


def _pearson_correlation_filtered(x: list, y: list) -> float:
    """Noneを除外してピアソン相関係数を計算する。"""
    paired = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(paired) < 4:
        return 0.0
    xa = [a for a, _ in paired]
    ya = [b for _, b in paired]
    return _pearson_correlation(xa, ya)


def _pearson_correlation(x: list, y: list) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    denom = math.sqrt(sum((xi - mx) ** 2 for xi in x) * sum((yi - my) ** 2 for yi in y))
    return num / denom if denom > 0 else 0.0


def _season_label(peak_months: list) -> str:
    if not peak_months:
        return "季節性あり"
    peak_set = set(peak_months)
    winter = {12, 1, 2}
    spring = {3, 4, 5}
    summer = {6, 7, 8}
    autumn = {9, 10, 11}
    if peak_set & summer and not (peak_set & winter):
        return "夏型"
    if peak_set & winter and not (peak_set & summer):
        return "冬型"
    if peak_set <= {1, 2, 3}:
        return "年始型"
    if peak_set <= {11, 12}:
        return "年末型"
    if peak_set <= {3, 4, 5}:
        return "春型"
    if peak_set <= {9, 10, 11}:
        return "秋型"
    return "季節性あり"


def _months_to_str(peak_months: list) -> str:
    if not peak_months:
        return ""
    months = sorted(peak_months)
    if len(months) == 1:
        return f"{months[0]}月"
    return f"{months[0]}〜{months[-1]}月"
