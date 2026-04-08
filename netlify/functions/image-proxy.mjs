export async function handler(event) {
  const headers = {
    "Access-Control-Allow-Origin": "*",
  };

  if (event.httpMethod === "OPTIONS") {
    return { statusCode: 204, headers };
  }

  const url = event.queryStringParameters?.url;
  if (!url || !url.startsWith("https://")) {
    return {
      statusCode: 400,
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ error: "invalid url" }),
    };
  }

  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
      signal: AbortSignal.timeout(10000),
    });

    const buffer = await res.arrayBuffer();
    const contentType = res.headers.get("content-type") || "image/jpeg";

    return {
      statusCode: 200,
      headers: { ...headers, "Content-Type": contentType },
      body: Buffer.from(buffer).toString("base64"),
      isBase64Encoded: true,
    };
  } catch (err) {
    return {
      statusCode: 502,
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ error: err.message }),
    };
  }
}
