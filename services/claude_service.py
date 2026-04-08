"""
Claude API を使ったOEM改善案生成サービス。
"""
import json
from config.settings import ClaudeConfig


def generate_oem_suggestions(product_title: str, category: str, competitor_titles: list) -> dict:
    """
    商品のOEM物理改善案をClaudeに生成させる。

    Returns:
        {"suggestions": [{"title", "description", "reason", "cost_impact"}, ...]}
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic パッケージがインストールされていません。setup.bat を再実行してください。")

    if not ClaudeConfig.api_key:
        raise ValueError("config.ini の [claude] api_key が設定されていません。")

    competitors_text = "\n".join(f"- {t}" for t in competitor_titles[:6]) if competitor_titles else "（なし）"

    prompt = f"""あなたはAmazonセラー向けのOEM商品開発アドバイザーです。
以下の商品について、1688の工場で発注できる「物理的な商品改善・差別化案」を提案してください。

商品名: {product_title}
Amazonカテゴリ: {category}
競合商品タイトル（参考）:
{competitors_text}

【条件】
- 商品自体の構造・素材・機能・形状・色・サイズなど、物理的な変更のみ
- 説明書・保証書・パッケージ・ラベルなど付属品・梱包の話は除く
- 1688の工場に少ロット（MOQ100〜500個）で発注できる現実的なマイナーチェンジ
- 各案は具体的かつ独創的に（「高品質にする」「改善する」などの曖昧な表現は不可）
- cost_impact は「低（+10〜50円）」「中（+50〜200円）」「高（+200円〜）」のいずれか

以下のJSONのみで返答してください（前後に説明文不要）:
{{"suggestions": [{{"title": "改善案タイトル（15字以内）", "description": "具体的な改善内容（60字以内）", "reason": "なぜ売れやすくなるか（50字以内）", "cost_impact": "低（+10〜50円）"}}]}}

提案は5〜7件お願いします。"""

    client = anthropic.Anthropic(api_key=ClaudeConfig.api_key)
    message = client.messages.create(
        model=ClaudeConfig.model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # JSON部分だけ抽出
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Claude からのレスポンスにJSONが含まれていません: {text[:200]}")

    return json.loads(text[start:end])


def deepdive_oem_suggestion(product_title: str, category: str, suggestion_title: str, suggestion_description: str) -> dict:
    """
    OEM改善案を深掘りする（リスク・訴求・お悩み・バッドレビュー改善を生成）。

    Returns:
        {
          "risks": ["..."],
          "appeals": ["..."],
          "problems_solved": ["..."],
          "review_improvements": [{"review": "...", "resolved": true/false, "note": "..."}]
        }
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic パッケージがインストールされていません。setup.bat を再実行してください。")

    if not ClaudeConfig.api_key:
        raise ValueError("config.ini の [claude] api_key が設定されていません。")

    prompt = f"""あなたはAmazonセラー向けのOEM商品開発アドバイザーです。
以下のOEM改善案について、4項目を詳しく分析してください。

商品名: {product_title}
Amazonカテゴリ: {category}
改善案タイトル: {suggestion_title}
改善案の内容: {suggestion_description}

以下のJSONのみで返答してください（前後に説明文不要）:
{{
  "risks": ["発注・製造上のリスクや注意点を箇条書きで3〜4件（金型費用・品質トラブル・仕様指示の難しさ等）"],
  "appeals": ["Amazonタイトルや商品説明の箇条書きに使える訴求フレーズを3〜4件（具体的なキーワード入り）"],
  "problems_solved": ["この改善が解消する顧客の不満・悩みを3〜4件（「〜という悩み」形式で）"],
  "review_improvements": [
    {{"review": "このカテゴリ商品に多いバッドレビュー内容（1件）", "resolved": true, "note": "この改善でどう解決するか（またはなぜ未解決か）"}}
  ]
}}

review_improvementsは3〜4件。resolved=trueなら✅完全解決、false なら⚠️要注意。"""

    client = anthropic.Anthropic(api_key=ClaudeConfig.api_key)
    message = client.messages.create(
        model=ClaudeConfig.model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"Claude からのレスポンスにJSONが含まれていません: {text[:200]}")

    return json.loads(text[start:end])


def extract_search_keyword(product_title: str, category: str = "") -> str:
    """
    Amazon商品タイトル（＋カテゴリ）から最も検索されやすい日本語キーワードを1語返す。

    Returns:
        str: キーワード（例: "ネックピロー"）。失敗時は空文字。
    """
    try:
        import anthropic
    except ImportError:
        return ""

    if not ClaudeConfig.api_key or not product_title:
        return ""

    category_hint = f"\nカテゴリ: {category}" if category else ""

    prompt = (
        f"次のAmazon商品について、日本人の消費者がAmazonで最もよく検索するキーワードを"
        f"1語（または短い複合語）だけ日本語で答えてください。余計な説明は不要です。{category_hint}\n\n"
        f"商品タイトル: {product_title}"
    )

    client = anthropic.Anthropic(api_key=ClaudeConfig.api_key)
    message = client.messages.create(
        model=ClaudeConfig.model,
        max_tokens=30,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()
