"""RAG and semantic-search endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from api.services.rag import build_index, rag_status, semantic_search
from api.services.admin_refresh import expected_admin_token

router = APIRouter()


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=20)


@router.get("/rag/status")
def status() -> dict:
    data = rag_status()
    # llm_available is true when a narrative model can actually run: local Ollama
    # is up, OR a hosted API provider (openai/anthropic, incl. Qwen2.5 via an
    # OpenAI-compatible endpoint) is configured. Drives the UI "deterministic
    # mode" banner.
    from api.services.llm import get_provider

    provider = get_provider()
    data["llm_provider"] = provider
    data["llm_available"] = bool(data.get("ollama_available")) if provider == "ollama" else True
    return data


@router.post("/rag/reindex")
def reindex(force: bool = Query(True), x_admin_token: str | None = Header(default=None)) -> dict:
    expected = expected_admin_token()
    if not expected:
        raise HTTPException(status_code=503, detail="INVEST_SEARCH_ADMIN_TOKEN is not configured")
    if x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Admin token required")
    index = build_index(force=force)
    return {
        "chunk_count": index.get("chunk_count", 0),
        "embedding_model": index.get("embedding_model"),
        "chat_model": index.get("chat_model"),
    }


@router.post("/semantic-search")
def search(request: SearchRequest) -> dict:
    results = []
    for item in semantic_search(request.query, top_k=request.top_k):
        clean = {key: value for key, value in item.items() if key != "embedding"}
        if "text" in clean:
            clean["text"] = clean["text"][:900]
        results.append(clean)
    return {
        "query": request.query,
        "results": results,
    }
