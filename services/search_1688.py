"""
1688.com 検索サービス。
- キーワード検索
- 画像検索（以图搜图）: Amazon商品画像URLを使って同一商品を1688で探す
"""
import re
import time
import uuid
import requests
from pathlib import Path
from config.settings import AppConfig
from utils.playwright_manager import get_page, get_1688_page, human_wait
from services.exchange_rate import get_cny_to_jpy

TMP_DIR = Path(__file__).parent.parent / "static" / "img" / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)

# 1688 画像検索URL
IMAGE_SEARCH_URL = "https://s.1688.com/selloffer/offerlist.htm"

SEARCH_URL = "https://s.1688.com/selloffer/offerlist.htm?keywords={query}"

DUMMY_RESULTS = [
    {
        "title": "コラーゲンペプチド 粉末 500g OEM対応 健康食品",
        "price_cny": 15.80,
        "price_jpy": 0,
        "moq": 100,
        "shop_name": "広州健康食品有限公司",
        "url": "https://detail.1688.com/offer/dummy001.html",
        "image_url": "",
        "monthly_sales": 2400,
    },
    {
        "title": "胶原蛋白肽 日本向け 500g 食品グレード",
        "price_cny": 18.50,
        "price_jpy": 0,
        "moq": 50,
        "shop_name": "深圳営養品工厂",
        "url": "https://detail.1688.com/offer/dummy002.html",
        "image_url": "",
        "monthly_sales": 800,
    },
    {
        "title": "胶原蛋白 粉 日本輸出向け 分装可能",
        "price_cny": 12.00,
        "price_jpy": 0,
        "moq": 200,
        "shop_name": "杭州保健品工厂直营",
        "url": "https://detail.1688.com/offer/dummy003.html",
        "image_url": "",
        "monthly_sales": 5000,
    },
]


def search_by_keyword(keyword: str, max_results: int = 10) -> dict:
    """
    キーワードで1688を検索して商品リストを返す。

    Returns:
        {
            "keyword": str,
            "exchange_rate": float,
            "results": [
                {
                    "title": str,
                    "price_cny": float,
                    "price_jpy": float,
                    "moq": int,
                    "shop_name": str,
                    "url": str,
                    "image_url": str,
                }
            ]
        }
    """
    exchange_rate = get_cny_to_jpy()

    search_url = SEARCH_URL.format(query=keyword.replace(" ", "+"))

    if AppConfig.TEST_MODE:
        raw = DUMMY_RESULTS[:max_results]
        results = _score_and_convert(raw, exchange_rate)
        recommended = select_recommended_suppliers(results)
        return {"keyword": keyword, "exchange_rate": exchange_rate,
                "results": results, "recommended": recommended, "search_url": search_url}

    try:
        results = _scrape_search(keyword, exchange_rate, max_results)
        recommended = select_recommended_suppliers(results)
        return {"keyword": keyword, "exchange_rate": exchange_rate,
                "results": results, "recommended": recommended, "search_url": search_url}
    except Exception as e:
        print(f"1688検索失敗: {e}")
        return {"keyword": keyword, "exchange_rate": exchange_rate,
                "results": [], "recommended": {"cheapest": None, "average": None},
                "search_url": search_url, "error": str(e)}


def _scrape_search(keyword: str, exchange_rate: float, max_results: int) -> list[dict]:
    """1688検索ページをスクレイピングする。"""
    url = SEARCH_URL.format(query=keyword.replace(" ", "+"))
    results = []

    with get_page(headless=True, timeout_ms=40000) as page:
        page.goto(url, wait_until="domcontentloaded")
        human_wait(1.5, 3.0)

        # 人間らしいスクロールで遅延ロードを促す
        page.evaluate("window.scrollTo(0, 400)")
        human_wait(0.6, 1.2)
        page.evaluate("window.scrollTo(0, 900)")
        human_wait(0.5, 1.0)

        items = page.query_selector_all(
            ".offer-item, .sm-offer-item, [class*='offer-item'], [class*='item-info']"
        )

        for item in items[:max_results]:
            try:
                product = _parse_item(item, exchange_rate)
                if product and product["price_cny"] > 0:
                    results.append(product)
            except Exception:
                continue

    return results


def _parse_item(item, exchange_rate: float) -> dict | None:
    # タイトル
    title_el = item.query_selector(".title, .sm-offer-title, h4, a[title]")
    title = (title_el.inner_text().strip() if title_el else "")[:80]
    if not title:
        return None

    # 価格
    price_el = item.query_selector(".price, .sm-offer-priceNum, [class*='price']")
    price_text = price_el.inner_text() if price_el else "0"
    price_cny = _parse_number(price_text)

    # URL
    link_el = item.query_selector("a[href*='1688.com'], a[href*='detail.1688']")
    href = link_el.get_attribute("href") if link_el else ""
    if href and not href.startswith("http"):
        href = "https:" + href

    # MOQ
    moq_el = item.query_selector("[class*='moq'], [class*='min']")
    moq_text = moq_el.inner_text() if moq_el else "1"
    moq = int(_parse_number(moq_text) or 1)

    # 店舗名
    shop_el = item.query_selector(".company-name, [class*='company'], [class*='shop']")
    shop_name = shop_el.inner_text().strip()[:40] if shop_el else ""

    # 画像
    img_el = item.query_selector("img")
    img_url = ""
    if img_el:
        img_url = img_el.get_attribute("src") or img_el.get_attribute("data-src") or ""

    return {
        "title": title,
        "price_cny": price_cny,
        "price_jpy": round(price_cny * exchange_rate, 0),
        "moq": moq,
        "shop_name": shop_name,
        "url": href,
        "image_url": img_url,
        "monthly_sales": 0,
    }


def _parse_number(text: str) -> float:
    text = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(text)
    except Exception:
        return 0.0


def to_chinese_keyword(japanese_keyword: str) -> str:
    """
    日本語キーワードから1688検索用の中国語キーワードへの簡易変換。
    完全な翻訳ではなく、よく使われる対応語を返す。
    """
    mapping = {
        "コラーゲン": "胶原蛋白", "サプリ": "保健品营养品",
        "ビタミン": "维生素", "亜鉛": "锌", "鉄分": "铁",
        "マグネシウム": "镁", "乳酸菌": "乳酸菌益生菌",
        "プロテイン": "蛋白粉", "ヒアルロン酸": "透明质酸",
        "食品": "食品", "飲料": "饮料", "サプリメント": "营养补充剂",
        "マスク": "口罩面膜", "化粧品": "化妆品",
        "スキンケア": "护肤品", "おもちゃ": "玩具",
        "スポーツ": "运动", "バッグ": "包包",
        "靴": "鞋子", "衣類": "服装",
    }
    for jp, cn in mapping.items():
        if jp in japanese_keyword:
            return cn
    # 変換できなければ元のキーワードをそのまま使う
    return japanese_keyword


# ──────────────────────────────────────────
# 画像検索（以图搜图）
# ──────────────────────────────────────────

def _build_browser_search_url(image_url: str) -> str:
    """
    ブラウザで直接開ける1688画像検索URL（imageAddress方式）を返す。
    ユーザーのブラウザ（ログイン済み）で開くためのURL。
    """
    import urllib.parse
    encoded = urllib.parse.quote(image_url, safe="")
    return f"https://s.1688.com/selloffer/offerlist.htm?imageAddress={encoded}"


def search_by_image(image_url: str, max_results: int = 10, crop: dict = None) -> dict:
    """
    Amazon商品画像URLを使って1688で画像検索する。
    クロップ指定がある場合はクロップ画像を一時ホストしてブラウザ検索URLも提供する。

    Returns:
        {
            "image_url": str,
            "browser_search_url": str,  # ブラウザで直接開ける1688画像検索URL
            "local_image_path": str,
            "exchange_rate": float,
            "results": [...],
        }
    """
    exchange_rate = get_cny_to_jpy()

    if AppConfig.TEST_MODE:
        return _dummy_image_search(image_url, exchange_rate)

    # ブラウザで開くURL（クロップなし＝元画像で検索）
    browser_search_url = _build_browser_search_url(image_url)

    # 画像をダウンロードして一時保存（クロップ用）
    local_path = _download_image(image_url)
    if local_path and crop:
        local_path = _crop_image(local_path, crop)
        # クロップ画像はローカルにしかないためブラウザ検索URL更新は不可
        # → クロップなしの元URLでブラウザ検索を提供しつつ、Playwrightでもトライ

    if not local_path:
        return {
            "image_url": image_url,
            "browser_search_url": browser_search_url,
            "local_image_path": "",
            "exchange_rate": exchange_rate,
            "results": [],
            "error": "商品画像のダウンロードに失敗しました",
        }

    # Playwrightによる自動スクレイピング（失敗してもブラウザURLは返す）
    try:
        results, search_url = _scrape_image_search(local_path, exchange_rate, max_results)
        exact_results = [r for r in results if r.get("match_note") == "画像一致度: 高"]
        if not exact_results:
            exact_results = results
        recommended = select_recommended_suppliers(exact_results)
        print(f"[1688] 画像検索結果: {len(results)}件 → フィルター後: {len(exact_results)}件")
        return {
            "image_url": image_url,
            "browser_search_url": browser_search_url,
            "local_image_path": f"/static/img/tmp/{local_path.name}",
            "exchange_rate": exchange_rate,
            "search_url": search_url,
            "results": exact_results,
            "recommended": recommended,
        }
    except Exception as e:
        print(f"[1688] Playwright検索失敗: {e}")
        return {
            "image_url": image_url,
            "browser_search_url": browser_search_url,
            "local_image_path": f"/static/img/tmp/{local_path.name}" if local_path else "",
            "exchange_rate": exchange_rate,
            "results": [],
            "recommended": {"cheapest": None, "average": None},
            "error": str(e),
        }


def _crop_image(image_path: Path, crop: dict) -> Path:
    """指定した割合で画像をクロップして新しいファイルに保存する。"""
    try:
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        x1 = int(crop["x1"] * w)
        y1 = int(crop["y1"] * h)
        x2 = int(crop["x2"] * w)
        y2 = int(crop["y2"] * h)
        cropped = img.crop((x1, y1, x2, y2))
        crop_path = image_path.with_name(f"crop_{image_path.name}")
        cropped.save(crop_path)
        return crop_path
    except ImportError:
        print("Pillowがインストールされていません。クロップなしで検索します。")
        return image_path
    except Exception as e:
        print(f"クロップ失敗: {e}")
        return image_path


def _download_image(image_url: str) -> Path | None:
    """画像URLをダウンロードして一時ファイルに保存する。"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.amazon.co.jp/",
        }
        resp = requests.get(image_url, headers=headers, timeout=15, stream=True)
        resp.raise_for_status()

        # 拡張子を判定
        content_type = resp.headers.get("content-type", "")
        ext = ".jpg" if "jpeg" in content_type or "jpg" in content_type else \
              ".png" if "png" in content_type else \
              ".webp" if "webp" in content_type else ".jpg"

        filename = f"amazon_img_{uuid.uuid4().hex[:8]}{ext}"
        save_path = TMP_DIR / filename
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return save_path
    except Exception as e:
        print(f"画像ダウンロード失敗: {e}")
        return None


def _wait_for_captcha(page, timeout_sec: int = 120) -> None:
    """
    CAPTCHAページが検出された場合、ユーザーが解くまで待機する。
    解けたら処理を継続。タイムアウトなら例外を送出。
    """
    def _is_captcha():
        try:
            content = page.content()[:3000]
            return "请拖动" in content or "滑块" in content
        except Exception:
            return False

    if not _is_captcha():
        return  # CAPTCHAなし、そのまま続行

    print("[1688] CAPTCHAを検出。ブラウザで右にスライダーを引いてください...")
    for _ in range(timeout_sec):
        time.sleep(1)
        try:
            if not _is_captcha():
                print("[1688] CAPTCHA解除確認。処理を継続します。")
                time.sleep(2)
                return
        except Exception:
            pass

    raise Exception(
        "CAPTCHAの解除待ちがタイムアウトしました。"
        "ブラウザのスライダーを右に引いてから再度お試しください。"
    )


def _set_file_input(page, image_path: Path, wait_sec: int = 5) -> bool:
    """
    1688ページ上の file input に画像をセットする。
    wait_sec 秒間、ファイル入力が出現するまで待機してからセットする。
    """
    # DOMにファイル入力が現れるまで最大 wait_sec 秒待つ
    for sel in ["#img-search-upload", "input[accept*='image']", "input[type='file']"]:
        try:
            page.wait_for_selector(sel, timeout=wait_sec * 1000)
            locator = page.locator(sel).first
            locator.set_input_files(str(image_path))
            print(f"[1688] ファイルアップロード成功: {sel}")
            time.sleep(3)
            return True
        except Exception as e:
            print(f"[1688] {sel} 待機/セット失敗: {e}")
            continue
    return False


def _dismiss_popup(page) -> None:
    """言語・通貨設定などのポップアップを閉じる。"""
    try:
        # 「取消」または「×」ボタンをJS経由でクリック
        page.evaluate("""
            (function() {
                // テキストが取消/Cancel/×のボタンを探す
                var btns = document.querySelectorAll('button, [class*="cancel"], [class*="close"]');
                for (var b of btns) {
                    var txt = b.textContent.trim();
                    if (txt === '取消' || txt === 'Cancel' || txt === '×' || txt === 'X') {
                        b.click();
                        return;
                    }
                }
                // Escキー送出でも閉じる場合がある
            })()
        """)
        time.sleep(0.5)
    except Exception:
        pass


def _click_image_search_button(page) -> bool:
    """
    「以图搜款」ボタンをクリックしてファイルアップロード入力を表示させる。
    テキストマッチを優先し、クラスセレクターをフォールバックにする。
    """
    clicked = page.evaluate("""
        (function() {
            // テキストで「以图搜款」を探す
            var all = document.querySelectorAll('*');
            for (var el of all) {
                if (el.children.length === 0 || el.tagName === 'SPAN' || el.tagName === 'BUTTON') {
                    if (el.textContent.trim().includes('以图搜款') || el.textContent.trim().includes('以图搜')) {
                        el.click();
                        return true;
                    }
                }
            }
            // クラス名フォールバック
            var candidates = [
                '.vc-search-bar-camera', '.search-bar-camera',
                '[class*="SearchCamera"]', '[class*="searchCamera"]',
                '[class*="imageSearch"]', '[class*="img-search"]',
                '[title*="图"]', '[aria-label*="图"]'
            ];
            for (var sel of candidates) {
                var el = document.querySelector(sel);
                if (el) { el.click(); return true; }
            }
            return false;
        })()
    """)
    if clicked:
        time.sleep(1.5)
    return bool(clicked)


def _scrape_image_search(image_path: Path, exchange_rate: float, max_results: int) -> list[dict]:
    """
    1688の画像検索ページをPlaywrightで操作して結果を取得する。
    1688の「以图搜款」機能を使用。ログインセッション（data/1688_session/）を利用。
    """
    results = []

    with get_1688_page(headless=False, timeout_ms=60000) as page:
        # 1688トップページへ
        page.goto("https://www.1688.com/", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        print(f"[1688] 現在のURL: {page.url}")

        # CAPTCHAが出ていたらユーザーが解くまで最大120秒待機
        _wait_for_captcha(page, timeout_sec=120)

        # ログイン状態チェック
        current_url = page.url
        on_login_page = (
            ("login" in current_url or "passport" in current_url)
            and page.query_selector("input[type='password'], #fm-login-password, #TPL_password_1") is not None
        )
        if on_login_page:
            raise Exception(
                "1688のログインセッションが切れています。"
                "import_1688_cookies.bat を実行して再ログインしてください。"
            )

        # ── Step1: カメラボタンを押さずに隠れたfile inputに直接セット ──
        # 1688のfile inputはDOMに最初から存在する（id="img-search-upload"）
        uploaded = _set_file_input(page, image_path, wait_sec=3)

        if not uploaded:
            # ── Step2: ポップアップを閉じてからリトライ ──
            _dismiss_popup(page)
            time.sleep(1)
            uploaded = _set_file_input(page, image_path, wait_sec=5)

        if not uploaded:
            # デバッグ用スクリーンショット
            ss_path = TMP_DIR / f"1688_upload_fail_{uuid.uuid4().hex[:6]}.png"
            page.screenshot(path=str(ss_path))
            raise Exception(f"画像アップロードボタンが見つかりませんでした（スクリーンショット: {ss_path.name}）")

        # 画像がセットされた後、ドロップダウン内の「帮你找同款」または画像サムネイルをクリック
        time.sleep(2)
        search_triggered = page.evaluate("""
            (function() {
                // 1. 「帮你找同款」ボタン（画像検索ドロップダウン内）
                var all = document.querySelectorAll('*');
                for (var el of all) {
                    var txt = (el.textContent || '').trim();
                    if ((txt === '帮你找同款' || txt === '找同款' || txt.includes('找同款'))
                        && el.children.length <= 3) {
                        el.click();
                        return 'clicked:帮你找同款';
                    }
                }
                // 2. 画像アップロードパネル内のサムネイル画像をクリック
                var panelImgs = document.querySelectorAll(
                    '[class*="imgSearch"] img, [class*="imageSearch"] img, ' +
                    '[class*="upload"] img, [class*="Upload"] img'
                );
                for (var img of panelImgs) {
                    if (img.src && !img.src.includes('icon') && !img.src.includes('logo')) {
                        img.click();
                        return 'clicked:thumbnail';
                    }
                }
                // 3. 「搜索」テキストのボタン（フォールバック）
                var btns = document.querySelectorAll('button, [role="button"]');
                for (var b of btns) {
                    if ((b.textContent || '').trim() === '搜索') {
                        b.click();
                        return 'clicked:搜索';
                    }
                }
                return 'not_found';
            })()
        """)
        print(f"[1688] 検索トリガー: {search_triggered}")

        # 検索結果ページが読み込まれるまで待機（最大20秒）
        try:
            page.wait_for_url("**/offerlist**", timeout=20000)
        except Exception:
            pass
        time.sleep(3)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        print(f"[1688] 検索後URL: {page.url}")
        # 結果ページのスクリーンショット（デバッグ用）
        ss_result = TMP_DIR / f"1688_result_{uuid.uuid4().hex[:6]}.png"
        page.screenshot(path=str(ss_result))
        print(f"[1688] 結果SS: {ss_result.name}")

        # 結果をパース（キーワード検索と同じセレクター）
        items = page.query_selector_all(
            ".offer-item, .sm-offer-item, [class*='offer-item'], [class*='item-info'], "
            ".img-search-result-item, [class*='imgSearch']"
        )

        for item in items[:max_results]:
            try:
                product = _parse_item(item, exchange_rate)
                if product and product["price_cny"] > 0:
                    results.append(product)
            except Exception:
                continue

        # 位置ベースで一致度を付与（1688は類似度順に返すため上位ほど同一商品に近い）
        for i, p in enumerate(results):
            if i < 3:
                p["match_note"] = "画像一致度: 高"
            elif i < 6:
                p["match_note"] = "画像一致度: 中"
            else:
                p["match_note"] = "画像一致度: 低"

        # 検索結果ページのURLを取得（ブラウザで開くためのリンクに使用）
        final_url = page.url

        # 結果が0件の場合、ページ全体のスクリーンショットを撮って確認用に保存
        if not results:
            ss_path = TMP_DIR / f"1688_imgsearch_{uuid.uuid4().hex[:6]}.png"
            page.screenshot(path=str(ss_path))

    return results, final_url


def _dummy_image_search(image_url: str, exchange_rate: float) -> dict:
    """テストモード用ダミー画像検索結果（車載ホルダー系）。"""
    raw = [
        {
            "title": "磁吸车载手机支架 仪表台 360°旋转 日本向け OEM対応",
            "price_cny": 8.50, "moq": 100,
            "shop_name": "深圳優品電子厂直営",
            "url": "https://detail.1688.com/offer/car001.html",
            "image_url": "https://placehold.co/120x120/dbeafe/1e40af?text=工場A",
            "monthly_sales": 3200, "repeat_rate": 72,
            "is_quality_factory": True, "is_effort_award": False,
            "match_note": "画像一致度: 高",
        },
        {
            "title": "车载手机支架 磁吸式 重力感应 通用型 低価格",
            "price_cny": 5.20, "moq": 200,
            "shop_name": "広州汽車用品貿易公司",
            "url": "https://detail.1688.com/offer/car002.html",
            "image_url": "https://placehold.co/120x120/fef9c3/713f12?text=工場B",
            "monthly_sales": 850, "repeat_rate": 35,
            "is_quality_factory": False, "is_effort_award": True,
            "match_note": "画像一致度: 高",
        },
        {
            "title": "手机车载支架 磁力强力 仪表盘固定 日本規格",
            "price_cny": 6.80, "moq": 100,
            "shop_name": "東莞電子配件製造厂",
            "url": "https://detail.1688.com/offer/car003.html",
            "image_url": "https://placehold.co/120x120/dcfce7/166534?text=工場C",
            "monthly_sales": 1800, "repeat_rate": 58,
            "is_quality_factory": True, "is_effort_award": False,
            "match_note": "画像一致度: 中",
        },
        {
            "title": "磁力手机架 车用 圆形底座 金属片附属 超安値",
            "price_cny": 3.90, "moq": 500,
            "shop_name": "深圳雑貨電子貿易",
            "url": "https://detail.1688.com/offer/car004.html",
            "image_url": "https://placehold.co/120x120/fee2e2/991b1b?text=工場D",
            "monthly_sales": 420, "repeat_rate": 18,
            "is_quality_factory": False, "is_effort_award": False,
            "match_note": "画像一致度: 中",
        },
        {
            "title": "车载手机支架 磁吸 仪表盘 导航支架 努力賞認定",
            "price_cny": 7.20, "moq": 100,
            "shop_name": "浙江精密機械有限公司",
            "url": "https://detail.1688.com/offer/car005.html",
            "image_url": "https://placehold.co/120x120/f3e8ff/6b21a8?text=工場E",
            "monthly_sales": 2100, "repeat_rate": 65,
            "is_quality_factory": False, "is_effort_award": True,
            "match_note": "画像一致度: 中",
        },
        {
            "title": "磁吸式車載スマホホルダー 360度 強磁力 優良サプライヤー認定",
            "price_cny": 9.60, "moq": 50,
            "shop_name": "上海品質管理工厂（優良認定）",
            "url": "https://detail.1688.com/offer/car006.html",
            "image_url": "https://placehold.co/120x120/fff7ed/9a3412?text=工場F",
            "monthly_sales": 4500, "repeat_rate": 83,
            "is_quality_factory": True, "is_effort_award": True,
            "match_note": "画像一致度: 低",
        },
    ]
    results = _score_and_convert(raw, exchange_rate)
    # 「高」一致度のみ（同一商品）に絞る
    exact_results = [r for r in results if r.get("match_note") == "画像一致度: 高"]
    recommended = select_recommended_suppliers(exact_results)
    return {
        "image_url": image_url,
        "local_image_path": "",
        "exchange_rate": exchange_rate,
        "results": exact_results,
        "recommended": recommended,
        "search_method": "画像検索（以图搜图）",
    }


# ──────────────────────────────────────────
# 工場品質スコアリング・推奨選定
# ──────────────────────────────────────────

def _score_supplier(s: dict, rank: int) -> int:
    """
    工場の品質スコアを0〜100点で算出する。

    指標:
      月間販売数 (0-30): リピート需要の代理指標
      リピート率 (0-30): repeat_rate(%) — 実績顧客が再注文する割合
      1688優良工場マーク (0-20): is_quality_factory
      努力賞バッジ (0-15): is_effort_award
      おすすめ順位ボーナス (0-5): 検索上位ほど高評価
    """
    score = 0
    sales = s.get("monthly_sales", 0)
    if   sales >= 5000: score += 30
    elif sales >= 2000: score += 25
    elif sales >= 1000: score += 20
    elif sales >= 500:  score += 15
    elif sales >= 100:  score += 10
    else:               score += 5

    rr = s.get("repeat_rate", 0)
    if   rr >= 80: score += 30
    elif rr >= 60: score += 25
    elif rr >= 40: score += 15
    elif rr >= 20: score += 8
    else:          score += 3

    if s.get("is_quality_factory"): score += 20
    if s.get("is_effort_award"):    score += 15

    rank_bonus = max(0, 6 - rank)  # 1位→5, 2位→4, ..., 5位→1, 6位以降→0
    score += rank_bonus

    return min(100, score)


def _score_and_convert(raw: list[dict], exchange_rate: float) -> list[dict]:
    """スコアを付与し円換算した結果リストを返す。"""
    results = []
    for i, s in enumerate(raw):
        s = dict(s)
        s["price_jpy"] = round(s["price_cny"] * exchange_rate, 0)
        s["quality_score"] = _score_supplier(s, i + 1)
        results.append(s)
    return results


def select_recommended_suppliers(results: list[dict]) -> dict:
    """
    品質スコアで絞り込んだ工場の中から、
    最安値工場と平均価格工場の2社を選定して返す。

    Returns:
        {"cheapest": dict|None, "average": dict|None}
    """
    QUALITY_THRESHOLD = 35
    qualified = [s for s in results if s.get("quality_score", 0) >= QUALITY_THRESHOLD]
    if not qualified:
        qualified = sorted(results, key=lambda s: -s.get("quality_score", 0))[:3]

    if not qualified:
        return {"cheapest": None, "average": None}

    cheapest = min(qualified, key=lambda s: s["price_cny"])
    avg_price = sum(s["price_cny"] for s in qualified) / len(qualified)
    avg_supplier = min(qualified, key=lambda s: abs(s["price_cny"] - avg_price))

    return {
        "cheapest": cheapest,
        "average": avg_supplier if avg_supplier != cheapest else (
            # cheapest と同じ工場になる場合は2番目に近い工場を返す
            min([s for s in qualified if s != cheapest],
                key=lambda s: abs(s["price_cny"] - avg_price), default=None)
        ),
    }
