"""ASGI entry point for serverless / container deployment.

Exposes the FastAPI ``app`` for any ASGI host — Vercel (@vercel/python), Render,
Railway, Fly.io, or plain ``uvicorn server:app``.

Deployment modes (set via environment variables):

* Deterministic / BM25 only (no model, e.g. Vercel serverless):
    OLLAMA_BASE_URL=http://127.0.0.1:1   # refused -> instant fallback, no 3s wait
    RAG_SKIP_EMBEDDINGS=1                 # skip semantic, use keyword/BM25
  Retrieval = lexical; LLM narrative falls back to the deterministic templates.

* Hosted Qwen2.5 via an OpenAI-compatible API (Together / Groq / DeepInfra):
    LLM_PROVIDER=openai
    OPENAI_BASE_URL=https://api.together.xyz/v1
    OPENAI_API_KEY=...
    OPENAI_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo

* Self-hosted Ollama + qwen2.5 (VPS / GPU host):
    LLM_PROVIDER=ollama
    OLLAMA_BASE_URL=https://your-ollama-host:11434
    OLLAMA_CHAT_MODEL=qwen2.5:7b
"""

from __future__ import annotations

import os

# Keep request latency bounded on serverless (a missing model must not hang).
os.environ.setdefault("OLLAMA_CHAT_TIMEOUT", "8")
os.environ.setdefault("RAG_LLM_TIMEOUT_SECONDS", "20")

from api.main import app  # noqa: E402  (ASGI app served by the platform)

__all__ = ["app"]
