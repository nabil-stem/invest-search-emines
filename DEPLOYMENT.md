# Deployment guide — Vercel + RAG / qwen2.5

**TL;DR on the "local qwen2.5 on Vercel, no API" question:** not possible — Vercel
has no GPU, no long‑running process, and a ~3 GB / 300 s function limit, so it
**cannot run Ollama / a 7.6 GB model**. The local model always needs a host.
What *is* possible is below, in three flavours (A deterministic‑only, B
self‑hosted Ollama, C hosted Qwen2.5 API). The codebase is now configurable for
all three.

The frontend already reads `VITE_API_BASE_URL` and the backend reads
`LLM_PROVIDER` / `OPENAI_BASE_URL` / `OPENAI_MODEL` / `OLLAMA_BASE_URL`, so no code
changes are needed to switch modes — only environment variables.

---

## What runs where

| Layer | Vercel? | Notes |
|---|---|---|
| Frontend (React/Vite) | ✅ ideal | static build |
| Deterministic engine (scoring, budget, factual, sector, comparison, coverage, guardrails, conversation memory) | ✅ as Python function | pure pandas, no model |
| Lexical / BM25 retrieval | ✅ | pure Python |
| Semantic search (query embeddings) | ⚠️ needs `nomic-embed` (Ollama) or an embeddings API → otherwise **keyword‑only** |
| LLM narrative (qwen2.5 generation) | ❌ on Vercel | needs a model host (Option B) or an API (Option C) |

Most answers are **deterministic** and work everywhere; only the open‑ended
"recommend / explain" *narratives* need the LLM, and they fall back to the
deterministic templates when no model is reachable.

---

## Option A — Everything on Vercel, deterministic + BM25 (no model, no API)

Frontend + the Python API on one Vercel project. RAG = keyword/BM25; LLM
narrative → deterministic templates.

1. **Slim the Python deps** (the full `requirements.txt` includes Streamlit/
   matplotlib/folium and won't fit Vercel's function size). For this deploy use
   `requirements-vercel.txt`:
   ```bash
   cp requirements-vercel.txt requirements.txt   # for the Vercel build only
   ```
2. The repo already has root **`vercel.json`** (builds the frontend + `server.py`)
   and **`server.py`** (ASGI entry).
3. In the Vercel project settings, add env vars:
   ```
   OLLAMA_BASE_URL = http://127.0.0.1:1      # refused -> instant deterministic fallback
   RAG_SKIP_EMBEDDINGS = 1                    # keyword/BM25 retrieval
   ```
4. Deploy (`vercel --prod` or via Git import, Root Directory = repo root).

**Caveats:** cold starts load pandas + the data (~3–8 s) — use a **Pro** plan
(60 s limit) or expect occasional first‑request slowness on Hobby (10 s). If the
function exceeds the size limit, host the API on Render/Railway instead (below).

> More reliable variant: deploy the **frontend on Vercel** (Root Directory =
> `frontend`, it picks up `frontend/vercel.json`) and the **API on Render/Railway/
> Fly** (they run the FastAPI container without size/cold‑start pain). Set the
> frontend env `VITE_API_BASE_URL=https://<your-api-host>/api`.

---

## Option B — qwen2.5 actually generating (self‑hosted Ollama)

Keep the local model, just on a server instead of Vercel.

1. **Host the API + Ollama** on a box with enough RAM (≈8 GB for qwen2.5:7b; GPU
   optional but faster): a VPS (Hetzner/DigitalOcean), Fly.io, or RunPod.
   - Install Ollama, `ollama pull qwen2.5:7b nomic-embed-text`.
   - Run the API: `uvicorn server:app --host 0.0.0.0 --port 8000`
     (deps: `pip install -r requirements-vercel.txt`).
   - Env: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434`,
     `OLLAMA_CHAT_MODEL=qwen2.5:7b`.
2. **Frontend on Vercel**: Root Directory `frontend`, env
   `VITE_API_BASE_URL=https://<your-api-host>/api`.

This is the closest to "local qwen2.5" — the model simply lives on your server,
which the Vercel frontend calls.

---

## Option C — Hosted Qwen2.5 via an OpenAI‑compatible API (fully cloud)

Same Qwen2.5 family, served by a provider (Together / Groq / DeepInfra /
Fireworks). The API can run on Vercel functions or any host (no GPU needed).

1. Pick a provider and model, e.g. Together:
   ```
   LLM_PROVIDER   = openai
   OPENAI_BASE_URL= https://api.together.xyz/v1
   OPENAI_API_KEY = <key>
   OPENAI_MODEL   = Qwen/Qwen2.5-7B-Instruct-Turbo
   ```
   (Groq: `https://api.groq.com/openai/v1`, model `qwen-2.5-...`; DeepInfra:
   `https://api.deepinfra.com/v1/openai`, model `Qwen/Qwen2.5-7B-Instruct`.)
2. Deploy the API (Vercel Option A steps, or Render/Railway) with those env vars,
   and the frontend on Vercel pointing at it.
3. For semantic search in the cloud, either keep `RAG_SKIP_EMBEDDINGS=1`
   (keyword‑only) or add an embeddings endpoint later.

---

## Option D — ⭐ Free demo: Vercel frontend + proxy → tunnel → your PC (qwen2.5)

The recommended **free** setup. qwen2.5 + RAG + the data run on **your PC**; Vercel
serves the UI and a thin proxy; a tunnel connects them. The tunnel URL stays
server-side and an optional key keeps scanners off your PC.

```
Browser ──► Vercel (frontend + /api/* proxy) ──► ngrok / Cloudflare Tunnel ──► your PC (FastAPI + Ollama + qwen2.5)
```

Already in the repo:
- `frontend/api/[...path].ts` — Vercel proxy that forwards `/api/*` to your tunnel
  (reads `BACKEND_URL` / `BACKEND_KEY`, aliases `QWEN_API_URL` / `QWEN_API_KEY`).
- `api/main.py` — optional `BACKEND_KEY` guard (every `/api/*` needs the
  `x-backend-key` header when set; `/api/health` stays open).

### On your PC
```bash
ollama pull qwen2.5:7b nomic-embed-text
ollama serve                                   # keep running

# pick a long random secret and require it on the API:
#   PowerShell:  $env:BACKEND_KEY="<secret>"
#   bash:        export BACKEND_KEY=<secret>
uvicorn server:app --host 0.0.0.0 --port 8000  # deps: pip install -r requirements-vercel.txt

# expose it (ngrok is already installed here; Cloudflare Tunnel also works):
ngrok http 8000
#   -> https://xxxx.ngrok-free.app
# or: cloudflared tunnel --url http://localhost:8000  -> https://xxxx.trycloudflare.com
```

### On Vercel (deploy the frontend, Root Directory = `frontend`)
Project → Settings → Environment Variables:
```
BACKEND_URL = https://xxxx.ngrok-free.app      # the tunnel URL (no trailing slash)
BACKEND_KEY = <the same secret as on the PC>
```
Leave `VITE_API_BASE_URL` **unset** — the browser calls same-origin `/api/*`, which
the proxy forwards. Redeploy after changing env vars. The free ngrok URL changes
on each `ngrok http` run, so update `BACKEND_URL` when it does (a reserved/static
domain avoids this).

Notes: keep the PC + `ollama serve` + `uvicorn` + the tunnel running while the demo
is live. Vercel function timeout is 10 s (Hobby) / 60 s (Pro) — long LLM answers
may need Pro; the deterministic answers are fast either way.

## Environment variable reference

| Var | Purpose |
|---|---|
| `VITE_API_BASE_URL` | (frontend) backend base URL; default same‑origin `/api` |
| `BACKEND_URL` / `QWEN_API_URL` | (Vercel proxy) tunnel URL of your PC backend (Option D) |
| `BACKEND_KEY` / `QWEN_API_KEY` | shared secret: Vercel proxy sends it, the API requires it (Option D) |
| `LLM_PROVIDER` | `ollama` (default) / `openai` / `anthropic` |
| `OLLAMA_BASE_URL` | Ollama host; set to a refused address to force deterministic |
| `OLLAMA_CHAT_MODEL` | e.g. `qwen2.5:7b` |
| `OPENAI_BASE_URL` | OpenAI‑compatible endpoint (for hosted Qwen2.5) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | key + model id for the hosted API |
| `RAG_SKIP_EMBEDDINGS` | `1` = keyword/BM25 only (no embeddings) |
| `RAG_HYBRID_MODE`, `RAG_MAX_PER_SOURCE`, `RAG_NUM_PREDICT` | retrieval/generation tuning |

## Verify before deploying
- Frontend builds: `cd frontend && npm run build` (and `tsc --noEmit`).
- API runs deterministic without a model:
  `OLLAMA_BASE_URL=http://127.0.0.1:1 RAG_SKIP_EMBEDDINGS=1 uvicorn server:app`
  then `POST /api/chat {"message":"J'ai 800000 DH pour un commerce à Maarif"}`.
