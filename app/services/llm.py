from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class ChatMessage(BaseModel):
    role: str  # "system", "user", or "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    """Mirrors the OpenAI chat completions payload, so existing clients can point here unchanged."""

    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None


async def forward_to_openai(
    payload: ChatCompletionRequest, http_client: httpx.AsyncClient
) -> Dict[str, Any]:
    """Forward a cache miss upstream over the shared connection pool."""
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    response = await http_client.post(
        OPENAI_CHAT_URL,
        json=payload.model_dump(exclude_none=True),
        headers=headers,
    )
    response.raise_for_status()
    return response.json()
