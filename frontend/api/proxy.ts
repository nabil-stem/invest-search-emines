// Vercel serverless proxy: forwards every /api/* request to your backend
// (your PC running FastAPI + Ollama + qwen2.5, exposed via ngrok / Cloudflare
// Tunnel). The tunnel URL stays server-side (never shipped to the browser), and
// an optional shared key keeps random scanners off your PC.
//
// Vercel project env vars (Project Settings -> Environment Variables):
//   BACKEND_URL  = https://xxxx.ngrok-free.app   (or https://xxxx.trycloudflare.com)
//   BACKEND_KEY  = some-long-random-secret        (optional; must match the API)
// (QWEN_API_URL / QWEN_API_KEY are accepted as aliases.)

declare const process: {
  env: Record<string, string | undefined>;
};

export const config = { maxDuration: 60 };

function forwardedQuery(req: any) {
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

export default async function handler(req: any, res: any) {
  const backend = (process.env.BACKEND_URL || process.env.QWEN_API_URL || "").replace(/\/+$/, "");
  if (!backend) {
    res.status(503).json({ detail: "BACKEND_URL is not configured on Vercel" });
    return;
  }

  const rawPath = req.query?.path;
  const subPath = Array.isArray(rawPath) ? rawPath.join("/") : rawPath || "";
  const target = `${backend}/api/${subPath}${forwardedQuery(req)}`;

  const headers: Record<string, string> = {
    "content-type": "application/json",
    // Skip ngrok's free-tier browser interstitial for programmatic calls.
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
      : JSON.stringify(req.body ?? {});

  try {
    const upstream = await fetch(target, { method, headers, body });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader("content-type", upstream.headers.get("content-type") || "application/json");
    res.send(text);
  } catch (err: any) {
    res.status(502).json({ detail: "Backend unreachable via tunnel", error: String(err?.message || err) });
  }
}
