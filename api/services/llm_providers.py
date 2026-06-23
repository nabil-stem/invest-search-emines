"""LLM provider abstraction layer.

Supports Ollama (local, default), OpenAI (optional), Anthropic (optional),
and a deterministic fallback that always works without any LLM.
"""

from __future__ import annotations

import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

logger = logging.getLogger("invest_search.llm")

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_MODEL = os.environ.get("OLLAMA_CHAT_MODEL", "")
RAG_LLM_TIMEOUT = float(os.environ.get("RAG_LLM_TIMEOUT_SECONDS", "120"))

_PREFERENCE_ORDER = [
    "qwen3.6:latest",
    "qwen3.6",
    "qwen3.5:latest",
    "qwen3.5",
    "qwen3:latest",
    "qwen3",
    "glm-4.7-flash:latest",
    "glm-4.7-flash",
    "qwen2.5:14b",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "qwen2.5:1.5b",
    "qwen2.5:0.5b",
]

assert "qwen2.5:0.5b" != _PREFERENCE_ORDER[0], "tiny qwen must not be the first-choice model"
assert RAG_LLM_TIMEOUT <= 150, f"LLM timeout must not exceed 150s, got {RAG_LLM_TIMEOUT}"


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_s: float
    timed_out: bool = False


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system: str, user: str) -> LLMResponse: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self._model: str | None = None

    @property
    def name(self) -> str:
        return "ollama"

    def _choose_model(self) -> str:
        if OLLAMA_CHAT_MODEL:
            return OLLAMA_CHAT_MODEL
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
            r.raise_for_status()
            installed = [m["name"] for m in r.json().get("models", [])]
        except requests.RequestException:
            return "qwen2.5:0.5b"

        for pref in _PREFERENCE_ORDER:
            if pref in installed:
                return pref
        for m in installed:
            lower = m.lower()
            if ("qwen" in lower or "glm" in lower) and not any(tag in lower for tag in ["0.5b", "1b", "1.5b", "tiny", "embed"]):
                return m
        return installed[0] if installed else "qwen2.5:0.5b"

    @property
    def model(self) -> str:
        if self._model is None:
            self._model = self._choose_model()
        return self._model

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def generate(self, system: str, user: str) -> LLMResponse:
        model = self.model
        if "qwen3" in model.lower():
            user += "\n/no_think"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_ctx": 2048, "num_predict": 350},
        }
        t0 = time.time()
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat", json=payload, timeout=RAG_LLM_TIMEOUT
            )
            resp.raise_for_status()
            text = resp.json()["message"]["content"]
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"\s*```$", "", text).strip()
            return LLMResponse(
                text=text, provider="ollama", model=model,
                latency_s=round(time.time() - t0, 2),
            )
        except requests.exceptions.Timeout:
            logger.warning("Ollama timed out after %.1fs (model=%s)", RAG_LLM_TIMEOUT, model)
            return LLMResponse(
                text="", provider="ollama", model=model,
                latency_s=round(time.time() - t0, 2), timed_out=True,
            )


class OpenAIProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY", "").strip())

    def generate(self, system: str, user: str) -> LLMResponse:
        import openai

        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        t0 = time.time()
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            max_tokens=800,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        return LLMResponse(
            text=text, provider="openai",
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            latency_s=round(time.time() - t0, 2),
        )


class AnthropicProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def generate(self, system: str, user: str) -> LLMResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        t0 = time.time()
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        return LLMResponse(
            text=text, provider="anthropic",
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            latency_s=round(time.time() - t0, 2),
        )


def get_provider() -> LLMProvider:
    pref = os.environ.get("LLM_PROVIDER", "ollama").lower()
    providers: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }
    if pref in providers:
        p = providers[pref]()
        if p.is_available():
            return p
        logger.info("Preferred provider %s not available, trying fallbacks", pref)

    for name, cls in providers.items():
        if name == pref:
            continue
        p = cls()
        if p.is_available():
            logger.info("Using fallback provider: %s", name)
            return p

    return OllamaProvider()


_provider: LLMProvider | None = None


def provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider
