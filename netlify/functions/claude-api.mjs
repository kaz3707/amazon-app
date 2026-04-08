import Anthropic from "@anthropic-ai/sdk";

const CLAUDE_API_KEY = process.env.CLAUDE_API_KEY;
const CLAUDE_MODEL = process.env.CLAUDE_MODEL || "claude-sonnet-4-6";

function jsonResponse(statusCode, body) {
  return {
    statusCode,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Content-Type",
    },
    body: JSON.stringify(body),
  };
}

export async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type" } };
  }

  if (!CLAUDE_API_KEY) {
    return jsonResponse(500, { error: "CLAUDE_API_KEY が設定されていません" });
  }

  const body = JSON.parse(event.body || "{}");
  const action = body.action;

  const client = new Anthropic({ apiKey: CLAUDE_API_KEY });

  try {
    if (action === "oem_suggest") {
      return await handleOemSuggest(client, body);
    } else if (action === "oem_deepdive") {
      return await handleOemDeepdive(client, body);
    } else if (action === "extract_keyword") {
      return await handleExtractKeyword(client, body);
    } else {
      return jsonResponse(400, { error: `不明なアクション: ${action}` });
    }
  } catch (err) {
    return jsonResponse(500, { error: err.message });
  }
}

async function handleOemSuggest(client, body) {
  const { product_title, category = "不明", competitor_titles = [] } = body;
  if (!product_title) return jsonResponse(400, { error: "product_title は必須です" });

  const competitorsText = competitor_titles.length > 0
    ? competitor_titles.slice(0, 6).map(t => `- ${t}`).join("\n")
    : "（なし）";

  const prompt = `あなたはAmazonセラー向けのOEM商品開発アドバイザーです。
以下の商品について、1688の工場で発注できる「物理的な商品改善・差別化案」を提案してください。

商品名: ${product_title}
Amazonカテゴリ: ${category}
競合商品タイトル（参考）:
${competitorsText}

【条件】
- 商品自体の構造・素材・機能・形状・色・サイズなど、物理的な変更のみ
- 説明書・保証書・パッケージ・ラベルなど付属品・梱包の話は除く
- 1688の工場に少ロット（MOQ100〜500個）で発注できる現実的なマイナーチェンジ
- 各案は具体的かつ独創的に（「高品質にする」「改善する」などの曖昧な表現は不可）
- cost_impact は「低（+10〜50円）」「中（+50〜200円）」「高（+200円〜）」のいずれか

以下のJSONのみで返答してください（前後に説明文不要）:
{"suggestions": [{"title": "改善案タイトル（15字以内）", "description": "具体的な改善内容（60字以内）", "reason": "なぜ売れやすくなるか（50字以内）", "cost_impact": "低（+10〜50円）"}]}

提案は5〜7件お願いします。`;

  const message = await client.messages.create({
    model: CLAUDE_MODEL,
    max_tokens: 1500,
    messages: [{ role: "user", content: prompt }],
  });

  const text = message.content[0].text.trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}") + 1;
  if (start === -1 || end === 0) {
    return jsonResponse(500, { error: "Claude からのレスポンスにJSONが含まれていません" });
  }
  return jsonResponse(200, JSON.parse(text.slice(start, end)));
}

async function handleOemDeepdive(client, body) {
  const { product_title, category = "不明", suggestion_title, suggestion_description } = body;
  if (!product_title || !suggestion_title) {
    return jsonResponse(400, { error: "product_title と suggestion_title は必須です" });
  }

  const prompt = `あなたはAmazonセラー向けのOEM商品開発アドバイザーです。
以下のOEM改善案について、4項目を詳しく分析してください。

商品名: ${product_title}
Amazonカテゴリ: ${category}
改善案タイトル: ${suggestion_title}
改善案の内容: ${suggestion_description}

以下のJSONのみで返答してください（前後に説明文不要）:
{
  "risks": ["発注・製造上のリスクや注意点を箇条書きで3〜4件（金型費用・品質トラブル・仕様指示の難しさ等）"],
  "appeals": ["Amazonタイトルや商品説明の箇条書きに使える訴求フレーズを3〜4件（具体的なキーワード入り）"],
  "problems_solved": ["この改善が解消する顧客の不満・悩みを3〜4件（「〜という悩み」形式で）"],
  "review_improvements": [
    {"review": "このカテゴリ商品に多いバッドレビュー内容（1件）", "resolved": true, "note": "この改善でどう解決するか（またはなぜ未解決か）"}
  ]
}

review_improvementsは3〜4件。resolved=trueなら完全解決、false なら要注意。`;

  const message = await client.messages.create({
    model: CLAUDE_MODEL,
    max_tokens: 1500,
    messages: [{ role: "user", content: prompt }],
  });

  const text = message.content[0].text.trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}") + 1;
  if (start === -1 || end === 0) {
    return jsonResponse(500, { error: "Claude からのレスポンスにJSONが含まれていません" });
  }
  return jsonResponse(200, JSON.parse(text.slice(start, end)));
}

async function handleExtractKeyword(client, body) {
  const { title, category = "" } = body;
  if (!title) return jsonResponse(200, { keyword: "" });

  const categoryHint = category ? `\nカテゴリ: ${category}` : "";
  const prompt = `次のAmazon商品について、日本人の消費者がAmazonで最もよく検索するキーワードを1語（または短い複合語）だけ日本語で答えてください。余計な説明は不要です。${categoryHint}\n\n商品タイトル: ${title}`;

  const message = await client.messages.create({
    model: CLAUDE_MODEL,
    max_tokens: 30,
    messages: [{ role: "user", content: prompt }],
  });

  return jsonResponse(200, { keyword: message.content[0].text.trim() });
}
