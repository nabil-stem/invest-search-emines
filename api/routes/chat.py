"""Chat and intelligence answer endpoints (conversational)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services.conversation import run_turn

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""
    timestamp: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    category: str = "Small Private Clinic"
    locale: str = "fr"
    # Conversational memory passed by the client (stateless server):
    history: list[ChatMessage] = Field(default_factory=list)
    investor_profile: dict | None = None
    debug: bool = False
    # Explicit "Recherche Web" fallback (free DuckDuckGo, unverified results).
    web_search: bool = False


@router.post("/chat")
def chat(request: ChatRequest) -> dict:
    return run_turn(
        message=request.message,
        history=[m.model_dump() for m in request.history],
        profile_dict=request.investor_profile,
        debug=request.debug,
        web_search=request.web_search,
    )
