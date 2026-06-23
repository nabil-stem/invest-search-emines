"""LLM provider abstraction: Ollama (default), optional OpenAI/Anthropic, deterministic fallback."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import requests

from api.services.llm.model_select import (
    is_small_model as _is_small_model,
    ollama_models as _ollama_models,
    pick_chat_model as _pick_ollama_model,
)
from api.services.llm.prompts import SYSTEM_PROMPT, build_prompt

log = logging.getLogger("invest_search.llm")

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
RAG_LLM_TIMEOUT = float(os.environ.get("RAG_LLM_TIMEOUT_SECONDS", "120"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# OpenAI-compatible endpoint + model. Lets the SAME provider call a hosted
# Qwen2.5 API (Together / Groq / DeepInfra / Fireworks are OpenAI-compatible),
# e.g. OPENAI_BASE_URL=https://api.together.xyz/v1 and
# OPENAI_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

CONTEXT_LIMIT = int(os.environ.get("RAG_CHAT_CONTEXT_LIMIT", "1"))
CONTEXT_CHARS = int(os.environ.get("RAG_CHAT_CONTEXT_CHARS", "320"))
# Generation token budget. The prompt asks for 6 sections (reco, rationale,
# KPIs, risks, next steps, sources); 150 tokens truncated answers before the
# risks/next-steps sections ever rendered (A/B eval: has_risk=0.00 for both
# models). 400 lets the full structure complete at ~+4s latency.
NUM_PREDICT = int(os.environ.get("RAG_NUM_PREDICT", "400"))
NUM_CTX = int(os.environ.get("RAG_NUM_CTX", "1536"))


def get_provider() -> str:
    if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        return "openai"
    if LLM_PROVIDER == "anthropic" and ANTHROPIC_API_KEY:
        return "anthropic"
    return "ollama"


def selected_model() -> str:
    provider = get_provider()
    if provider == "openai":
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    return _pick_ollama_model()


def _generate_ollama(system: str, prompt: str) -> str:
    model = _pick_ollama_model()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.15, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
        "keep_alive": "10m",
    }
    t0 = time.time()
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=RAG_LLM_TIMEOUT)
    r.raise_for_status()
    content = r.json()["message"]["content"]
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    content = re.sub(r"^```(?:markdown|md)?\s*", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"\s*```$", "", content).strip()
    content = _normalize_markdown_headers(content)
    elapsed = round(time.time() - t0, 2)
    log.info("ollama model=%s elapsed=%ss tokens~%d", model, elapsed, len(content.split()))
    return content


def _generate_openai(system: str, prompt: str) -> str:
    import openai
    client = openai.OpenAI(
        api_key=OPENAI_API_KEY,
        **({"base_url": OPENAI_BASE_URL} if OPENAI_BASE_URL else {}),
    )
    r = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=600,
    )
    content = r.choices[0].message.content or ""
    return _normalize_markdown_headers(content)


def _generate_anthropic(system: str, prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    r = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return r.content[0].text


def _normalize_markdown_headers(md: str) -> str:
    """Force every section heading to level-2 (`##`) so LLM answers get the same
    styled layout as the deterministic templates. Small models tend to emit
    `### Note d'investissement` then `#### 1. **Recommandation**`; we strip the
    redundant title, the numbering and the bold, and flatten to `##`.
    """
    out: list[str] = []
    for line in md.split("\n"):
        m = re.match(r"^\s*#{1,6}\s*(.+?)\s*$", line)
        if not m:
            out.append(line)
            continue
        title = m.group(1)
        title = re.sub(r"^\d+[.)]\s*", "", title)   # drop "1. "
        title = title.strip("* ").strip()            # drop ** and spaces
        if re.match(r"(?i)^note d.?investissement$", title):
            continue  # redundant wrapper title
        out.append(f"## {title}")
    return "\n".join(out).strip()


def generate_answer(
    question: str,
    scoring: dict,
    contexts: list[dict[str, Any]],
) -> tuple[str, str]:
    """Generate an answer. Returns (markdown, provider_name).

    For small local models (qwen2.5:0.5b etc.), raises so the caller
    uses the high-quality scoring template instead of low-quality LLM output.
    For capable models (qwen3+, API providers), generates a full answer.
    """
    provider = get_provider()

    if provider == "ollama":
        model = _pick_ollama_model()
        if _is_small_model(model):
            raise RuntimeError(f"Skipping LLM: {model} too small for quality answers")

    system, prompt = build_prompt(
        question, scoring, contexts,
        context_limit=CONTEXT_LIMIT, context_chars=CONTEXT_CHARS,
    )

    try:
        if provider == "openai":
            text, provider_tag = _generate_openai(system, prompt), "api_openai"
        elif provider == "anthropic":
            text, provider_tag = _generate_anthropic(system, prompt), "api_anthropic"
        else:
            text, provider_tag = _generate_ollama(system, prompt), "ollama"
        if not text.strip():
            raise RuntimeError(f"{provider} returned an empty answer")
        return text, provider_tag
    except Exception as exc:
        log.warning("LLM generation failed (%s): %s", provider, exc)
        raise
