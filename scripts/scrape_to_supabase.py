"""
Amazon ベストセラーをスクレイピングし、Supabase に書き込むスタンドアロンスクリプト。
ローカルPCで実行する。

使い方:
  cd 利益計算アプリ
  python scripts/scrape_to_supabase.py

オプション:
  --max-depth N    カテゴリ再帰の最大深度（デフォルト: 3）
  --categories X Y 対象大カテゴリ名で絞り込み（省略=全カテゴリ）
"""

import sys
import os
import time
import argparse
from datetime import datetime

# プロジェクトルートをパスに追加（既存のモジュールを再利用するため）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from services.amazon_bestseller import (
    CATEGORY_ROOTS,
    _EXCLUDED_KEYWORDS,
    _parse_bestseller_page,
    _get_subcategories,
    _calc_individual_scores,
    _calc_opportunity_score,
    _score_to_label,
)
from utils.playwright_manager import get_page, human_wait


# ──────────────────────────────────────────
# ネットワークリトライ用ヘルパー
# ──────────────────────────────────────────

NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    OSError,
)


def with_retry(fn, *, max_attempts: int = 10, base_delay: float = 5.0, label: str = ""):
    """ネットワークエラー時に指数バックオフでリトライする。
    Wi-Fi切断などからの復帰を想定し、最大10回・最大待機5分まで粘る。
    """
    attempt = 0
    while True:
        try:
            return fn()
        except NETWORK_ERRORS as e:
            attempt += 1
            if attempt >= max_attempts:
                print(f"  リトライ上限到達 ({label}): {e}")
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 300)
            print(f"  ネットワークエラー ({label}) 試行{attempt}/{max_attempts}: {e} → {delay:.0f}秒後に再試行")
            time.sleep(delay)

# ──────────────────────────────────────────
# Supabase 設定（service_role キーで RLS を迂回）
# ──────────────────────────────────────────

SUPABASE_URL = "https://iadzbyuefqeeeiemrkym.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_SERVICE_KEY:
    print("エラー: 環境変数 SUPABASE_SERVICE_KEY を設定してください。")
    print("  set SUPABASE_SERVICE_KEY=eyJ...")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}


def supabase_upsert(table: str, rows: list[dict]):
    """Supabase REST API で upsert する。ネットワーク断時はリトライする。"""
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    # 500件ずつバッチ処理
    batch_size = 500
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]

        def _post():
            return httpx.post(url, json=batch, headers=HEADERS, timeout=60)

        try:
            resp = with_retry(_post, label=f"upsert {table}")
        except Exception as e:
            print(f"  Supabase upsert 失敗（リトライ尽き） ({table}): {e}")
            continue
        if resp.status_code not in (200, 201):
            print(f"  Supabase upsert エラー ({table}): {resp.status_code} {resp.text[:200]}")


def supabase_update_metadata(key: str, value: dict):
    """scrape_metadata テーブルを更新する（存在すればUPDATE、なければINSERT）。
    メタデータ更新はベストエフォート（失敗してもスクレイピング本体は止めない）。
    """
    url = f"{SUPABASE_URL}/rest/v1/scrape_metadata?key=eq.{key}"
    headers_patch = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    def _patch():
        return httpx.patch(
            url,
            json={"value": value, "updated_at": datetime.now().isoformat()},
            headers=headers_patch,
            timeout=30,
        )

    try:
        with_retry(_patch, max_attempts=5, label="metadata patch")
    except Exception as e:
        print(f"  metadata PATCH 失敗（無視して継続）: {e}")

    # 行がない場合に備えてINSERTも試行（重複なら無視）
    url_insert = f"{SUPABASE_URL}/rest/v1/scrape_metadata"
    headers_insert = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates",
    }

    def _insert():
        return httpx.post(
            url_insert,
            json={"key": key, "value": value, "updated_at": datetime.now().isoformat()},
            headers=headers_insert,
            timeout=30,
        )

    try:
        with_retry(_insert, max_attempts=5, label="metadata insert")
    except Exception as e:
        print(f"  metadata INSERT 失敗（無視して継続）: {e}")


def product_to_row(p: dict) -> dict:
    """スクレイピング結果をSupabaseテーブルのカラムに変換する。
    テーブルカラム: asin, title, price, rating, review_count, estimated_monthly_sales,
    bsr, category_path, rank_in_category, image_url, url, seller_count, scores,
    opportunity_score, opportunity_label, keepa_analysis, dimensions, scraped_at
    """
    return {
        "asin": p["asin"],
        "title": p.get("title", "")[:200],
        "price": p.get("price", 0),
        "rating": p.get("rating", 0),
        "review_count": p.get("review_count", 0),
        "estimated_monthly_sales": p.get("estimated_monthly_sales", 0),
        "bsr": p.get("bsr", 0),
        "category_path": p.get("category_path", ""),
        "rank_in_category": p.get("rank_in_category", 0),
        "image_url": p.get("image_url", ""),
        "url": p.get("url", ""),
        "opportunity_score": p.get("opportunity_score", 0),
        "opportunity_label": p.get("opportunity_label", ""),
        "scores": p.get("scores", {}),
        "keepa_analysis": p.get("keepa_analysis", {}),
        "dimensions": p.get("dimensions", {}),
        "seller_count": p.get("seller_count", 1),
        "scraped_at": datetime.now().isoformat(),
    }


def goto_with_retry(page, url, max_attempts: int = 5, base_delay: float = 10.0):
    """page.goto をネットワーク断に強くするラッパー。"""
    attempt = 0
    while True:
        try:
            page.goto(url, wait_until="domcontentloaded")
            return
        except Exception as e:
            attempt += 1
            msg = str(e).lower()
            # ネットワーク系の文字列を含むかでリトライ判定
            transient = any(k in msg for k in (
                "err_internet_disconnected",
                "err_name_not_resolved",
                "err_network",
                "err_proxy",
                "err_timed_out",
                "err_connection",
                "err_address_unreachable",
                "net::err",
                "navigation timeout",
                "timeout",
            ))
            if attempt >= max_attempts or not transient:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), 300)
            print(f"  page.goto エラー 試行{attempt}/{max_attempts}: {e} → {delay:.0f}秒後に再試行")
            time.sleep(delay)


def scrape_recursive(page, url, category_path, depth, max_depth,
                     all_products, seen_urls, seen_asins):
    """再帰的にベストセラーカテゴリをスクレイピング。"""
    if url in seen_urls:
        return
    seen_urls.add(url)

    if any(kw in category_path for kw in _EXCLUDED_KEYWORDS):
        return

    try:
        goto_with_retry(page, url)
        human_wait(1.5, 3.5)

        subcats = _get_subcategories(page, url) if depth < max_depth else []

        if not subcats:
            # リーフカテゴリ: TOP100を取得
            products = _parse_bestseller_page(page, category_path)
            new_products = []
            for p in products:
                if p.get("asin") and p["asin"] not in seen_asins:
                    seen_asins.add(p["asin"])
                    all_products.append(p)
                    new_products.append(p)

            if new_products:
                # リアルタイムでSupabaseに書き込み
                rows = [product_to_row(p) for p in new_products]
                supabase_upsert("bestseller_products", rows)

            print(f"  [{depth}] 小カテゴリ保存: {category_path} ({len(new_products)}件) / 累計{len(all_products)}件")
        else:
            print(f"  [{depth}] 中間スキップ: {category_path} → {len(subcats)}サブカテゴリ")
            for subcat_url, subcat_name in subcats:
                child_path = f"{category_path} > {subcat_name}"
                scrape_recursive(
                    page, subcat_url, child_path, depth + 1, max_depth,
                    all_products, seen_urls, seen_asins,
                )
                human_wait(1.0, 2.5)
    except Exception as e:
        print(f"  スクレイピング失敗 ({category_path}): {e}")


def main():
    parser = argparse.ArgumentParser(description="Amazon ベストセラー → Supabase")
    parser.add_argument("--max-depth", type=int, default=3, help="カテゴリ再帰の最大深度")
    parser.add_argument("--categories", nargs="*", help="対象大カテゴリ名（省略=全カテゴリ）")
    args = parser.parse_args()

    roots = CATEGORY_ROOTS
    if args.categories:
        roots = [r for r in CATEGORY_ROOTS if r["name"] in args.categories]
        if not roots:
            print(f"エラー: 指定されたカテゴリが見つかりません: {args.categories}")
            print(f"利用可能: {[r['name'] for r in CATEGORY_ROOTS]}")
            sys.exit(1)

    print(f"対象: {len(roots)}カテゴリ / 最大深度: {args.max_depth}")
    print(f"カテゴリ: {', '.join(r['name'] for r in roots)}")
    print()

    all_products = []
    seen_urls = set()
    seen_asins = set()

    # 既存ASINをロード（重複保存を避けて再開を高速化）
    try:
        print("既存ASINをロード中…")
        offset = 0
        page_size = 1000
        while True:
            url_select = (
                f"{SUPABASE_URL}/rest/v1/bestseller_products?select=asin"
                f"&offset={offset}&limit={page_size}"
            )
            r = httpx.get(url_select, headers=HEADERS, timeout=60)
            if r.status_code != 200:
                print(f"  既存ASIN取得エラー: {r.status_code}")
                break
            chunk = r.json()
            if not chunk:
                break
            for row in chunk:
                a = row.get("asin")
                if a:
                    seen_asins.add(a)
            if len(chunk) < page_size:
                break
            offset += page_size
        print(f"  既存ASIN: {len(seen_asins)}件 をスキップ対象に登録")
    except Exception as e:
        print(f"  既存ASINロード失敗（無視して継続）: {e}")

    # ステータスをSupabaseに記録
    supabase_update_metadata("bestseller_status", {
        "running": True,
        "categories_done": 0,
        "categories_total": len(roots),
        "current_category": "",
        "error": None,
        "last_updated": datetime.now().isoformat(),
    })

    try:
        with get_page(headless=True, timeout_ms=40000) as page:
            for i, root in enumerate(roots):
                print(f"\n{'='*60}")
                print(f"[{i+1}/{len(roots)}] {root['name']}")
                print(f"{'='*60}")

                supabase_update_metadata("bestseller_status", {
                    "running": True,
                    "categories_done": i,
                    "categories_total": len(roots),
                    "current_category": root["name"],
                    "error": None,
                    "last_updated": datetime.now().isoformat(),
                })

                scrape_recursive(
                    page, root["url"], root["name"], 1, args.max_depth,
                    all_products, seen_urls, seen_asins,
                )

        # 完了ステータス
        supabase_update_metadata("bestseller_status", {
            "running": False,
            "categories_done": len(roots),
            "categories_total": len(roots),
            "current_category": "",
            "error": None,
            "last_updated": datetime.now().isoformat(),
        })

        print(f"\n完了！ 合計 {len(all_products)} 商品を Supabase に書き込みました。")

    except Exception as e:
        supabase_update_metadata("bestseller_status", {
            "running": False,
            "categories_done": 0,
            "categories_total": len(roots),
            "current_category": "",
            "error": str(e),
            "last_updated": datetime.now().isoformat(),
        })
        print(f"\nエラーで中断: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
