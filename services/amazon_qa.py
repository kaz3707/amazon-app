"""
Amazon商品ページのQ&Aを取得するスクレイパー。
ログイン不要。Playwright使用。
"""
import re
from config.settings import AppConfig


_DUMMY_QA = [
    {"question": "防水対応はしていますか？", "answer": "防水加工は施されていません。水濡れにはご注意ください。"},
    {"question": "スマートフォン以外にも使えますか？", "answer": "タブレットにも対応しております。"},
    {"question": "子供でも使いやすいですか？", "answer": "はい、軽量設計のため子供でも扱いやすいです。"},
    {"question": "色違いはありますか？", "answer": "現在は黒のみの取り扱いとなっております。"},
    {"question": "長時間使用しても熱くなりませんか？", "answer": "放熱設計により長時間使用でも熱くなりにくい構造です。"},
]


def fetch_amazon_qa(asin: str, max_items: int = 10) -> list:
    """
    Amazon商品ページのQ&Aを取得する。

    Returns:
        [{"question": str, "answer": str}, ...]
    """
    if AppConfig.TEST_MODE:
        return _DUMMY_QA[:max_items]

    from utils.playwright_manager import get_page

    url = f"https://www.amazon.co.jp/ask/questions/asin/{asin}/"
    results = []

    try:
        with get_page(headless=True, timeout_ms=20000) as page:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)

            # Q&Aアイテムを探す
            qa_items = page.query_selector_all("[data-hook='ask-btf-container'], .askTeaserQuestions, [class*='askQuestion']")

            if not qa_items:
                # 別のセレクタを試す
                qa_items = page.query_selector_all("div[id^='question-']")

            for item in qa_items[:max_items]:
                try:
                    q_el = item.query_selector("[data-hook='question-text'], .a-declarative span, h3 span")
                    a_el = item.query_selector("[data-hook='answer-body'], .a-expander-content span")

                    q_text = q_el.inner_text().strip() if q_el else ""
                    a_text = a_el.inner_text().strip() if a_el else "（回答なし）"

                    # 短すぎるものは除外
                    if len(q_text) > 5:
                        results.append({"question": q_text[:200], "answer": a_text[:300]})
                except Exception:
                    continue

            # セレクタが機能しなかった場合、テキストから直接抽出を試みる
            if not results:
                content = page.content()
                # 質問らしいテキストパターンを探す
                questions = re.findall(r'class="[^"]*question[^"]*"[^>]*>([^<]{10,200})<', content)
                for q in questions[:max_items]:
                    q_clean = re.sub(r'\s+', ' ', q).strip()
                    if q_clean:
                        results.append({"question": q_clean, "answer": "（Amazonで確認してください）"})

    except Exception as e:
        raise RuntimeError(f"Q&A取得エラー: {e}")

    return results
