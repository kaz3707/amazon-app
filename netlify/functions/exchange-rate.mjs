export async function handler(event) {
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
  };

  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers };
  }

  try {
    // open.er-api.com（無料・APIキー不要）
    let rate = null;
    try {
      const res = await fetch("https://open.er-api.com/v6/latest/CNY", { signal: AbortSignal.timeout(8000) });
      const data = await res.json();
      rate = data.rates?.JPY;
    } catch {}

    // フォールバック: frankfurter.app
    if (!rate) {
      try {
        const res = await fetch("https://api.frankfurter.app/latest?from=CNY&to=JPY", { signal: AbortSignal.timeout(8000) });
        const data = await res.json();
        rate = data.rates?.JPY;
      } catch {}
    }

    // 最終フォールバック
    if (!rate) rate = 21.5;

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ rate, pair: "CNY_JPY" }),
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: err.message }),
    };
  }
}
