"""FastAPI wrapper for the Invest Search analytical backend."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Load .env before importing routes/services so env-configurable knobs
# (OLLAMA_CHAT_MODEL, RAG_NUM_PREDICT, RAG_MAX_PER_SOURCE, ...) take effect for
# the API server too — previously only the Streamlit app loaded .env, so these
# were silently ignored here.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from api.routes import admin, chat, market, rag  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


app = FastAPI(
    title="Invest Search Intelligence API",
    description="API layer for medical market intelligence, scoring, and RAG-ready answers.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    # Allow a deployed frontend / tunnel to call the API directly (the Vercel
    # proxy is server-to-server and needs no CORS, but this covers direct calls).
    allow_origin_regex=r"https://.*\.(vercel\.app|ngrok-free\.app|ngrok\.app|trycloudflare\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional shared-secret guard. When BACKEND_KEY is set (e.g. your PC behind a
# public tunnel), every /api/* call must send a matching `x-backend-key` header —
# which the Vercel proxy adds. Unset (local dev) => no auth. /api/health is open
# so tunnels/uptime checks work.
BACKEND_KEY = os.environ.get("BACKEND_KEY", "").strip()


@app.middleware("http")
async def _backend_key_guard(request: Request, call_next):
    if BACKEND_KEY:
        path = request.url.path
        if path.startswith("/api/") and path != "/api/health" and request.method != "OPTIONS":
            if request.headers.get("x-backend-key") != BACKEND_KEY:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)

app.include_router(market.router, prefix="/api", tags=["market"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(rag.router, prefix="/api", tags=["rag"])
app.include_router(admin.router, prefix="/api", tags=["admin"])


@app.on_event("startup")
async def _warmup():
    """Preload the Ollama chat model so first requests don't cold-start."""
    import threading
    def _ping():
        try:
            import requests as _req
            from api.services.llm.providers import _pick_ollama_model, OLLAMA_URL
            model = _pick_ollama_model()
            _req.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": model, "messages": [{"role": "user", "content": "ok"}],
                      "stream": False, "options": {"num_predict": 1}},
                timeout=15,
            )
            logging.getLogger("invest_search").info("Ollama model %s warmed up", model)
        except Exception:
            pass
    threading.Thread(target=_ping, daemon=True).start()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "invest-search-api"}
