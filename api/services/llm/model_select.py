"""Single source of truth for Ollama chat-model selection.

Previously `rag.py` and `llm/providers.py` each carried their own copy of this
logic, and both preference lists were topped by `qwen3.6` / `qwen3.5` — model
tags that Alibaba never released and that are not installed locally, so they
silently fell through to whatever real model happened to be present.

This module keeps one cleaned preference list of *real* tags, honours the
`OLLAMA_CHAT_MODEL` env override (used by the A/B eval to pin a specific model),
and exposes small helpers shared by retrieval and generation.
"""

from __future__ import annotations

import os

import requests

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# Real, installable Ollama tags only. The eval pins an exact model via
# OLLAMA_CHAT_MODEL, so this list only matters when nothing is pinned.
#
# qwen2.5:7b is preferred over qwen3:8b as the default: the A/B eval
# (docs/model_comparison.md) found them within ~2 points on accuracy, but
# qwen2.5:7b is more number-faithful (0.97 vs 0.90 — it doesn't invent figures,
# the worst failure mode for an investment tool) and ~15% faster. Its only gap
# (occasionally omitting the density KPI) is already backfilled by
# build_rag_answer's deterministic KPI merge.
MODEL_PREFERENCES = [
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen3:latest",
    "qwen3",
    "qwen2.5:3b",
    "glm-4.7-flash:latest",
    "glm-4.7-flash",
    "qwen2.5:1.5b",
    "qwen2.5:0.5b",
]

# Tags we consider too small to produce a quality investment note. The caller
# falls back to the deterministic scoring template for these.
SMALL_MODEL_TAGS = ("0.5b", "1b", "1.5b", "tiny")

# Default used only when Ollama is unreachable / has no models installed.
FALLBACK_MODEL = "qwen2.5:0.5b"


def ollama_models() -> list[str]:
    """Return installed Ollama model tags, or [] if Ollama is unreachable."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return [m["name"] for m in r.json().get("models", [])] if r.ok else []
    except requests.RequestException:
        return []


def is_small_model(model: str) -> bool:
    """True for tiny models whose answers we should not surface to users."""
    return any(tag in model.lower() for tag in SMALL_MODEL_TAGS)


def pick_chat_model() -> str:
    """Resolve the chat model: env override > preference list > first installed."""
    pinned = os.environ.get("OLLAMA_CHAT_MODEL", "").strip()
    if pinned:
        return pinned

    installed = ollama_models()
    for model in MODEL_PREFERENCES:
        if model in installed:
            return model
    # Fall back to the first capable (non-tiny, non-embedding) installed model.
    for model in installed:
        lower = model.lower()
        if ("qwen" in lower or "glm" in lower) and not is_small_model(model) and "embed" not in lower:
            return model
    return installed[0] if installed else FALLBACK_MODEL
