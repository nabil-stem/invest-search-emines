// Vercel serverless proxy (repo-root deploy; auto-detected as a function at
// /api/proxy). Forwards /api/* to the backend (PC running FastAPI + Ollama,
// exposed via ngrok). Injects ngrok's skip-warning header so the tunnel returns
// JSON, and an optional shared key. The repo-root vercel.json rewrites
// /api/:path* -> /api/proxy?path=:path*.
//
// Vercel env vars: BACKEND_URL (= ngrok https URL), BACKEND_KEY (optional).
// NOTE: the surrounding api/*.py backend is excluded from the deploy via
// .vercelignore, so only this JS file ships (no Python build).

module.exports.config = { maxDuration: 60 };

function forwardedQuery(req) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(req.query || {})) {
    if (key === "path") continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else if (value !== undefined) {
      params.append(key, String(value));
    }
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

module.exports = async function handler(req, res) {
  const backend = (process.env.BACKEND_URL || process.env.QWEN_API_URL || "").replace(/\/+$/, "");
  if (!backend) {
    res.status(503).json({ detail: "BACKEND_URL is not configured on Vercel" });
    return;
  }

  const rawPath = req.query && req.query.path;
  const subPath = Array.isArray(rawPath) ? rawPath.join("/") : rawPath || "";
  const target = `${backend}/api/${subPath}${forwardedQuery(req)}`;

  const headers = {
    "content-type": "application/json",
    "ngrok-skip-browser-warning": "1",
  };
  const key = process.env.BACKEND_KEY || process.env.QWEN_API_KEY;
  if (key) headers["x-backend-key"] = key;

  const method = (req.method || "GET").toUpperCase();
  const body =
    method === "GET" || method === "HEAD"
      ? undefined
      : typeof req.body === "string"
      ? req.body
      : JSON.stringify(req.body || {});

  try {
    const upstream = await fetch(target, { method, headers, body });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader("content-type", upstream.headers.get("content-type") || "application/json");
    res.send(text);
  } catch (err) {
    res.status(502).json({ detail: "Backend unreachable via tunnel", error: String((err && err.message) || err) });
  }
};
