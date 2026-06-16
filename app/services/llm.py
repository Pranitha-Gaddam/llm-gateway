import httpx
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.core.config import settings

# This mirrors an individual message block inside an LLM conversation array
class ChatMessage(BaseModel):
    role: str          # e.g., "system", "user", "assistant"
    content: str       # The actual text prompt content

# This mirrors the payload structure that OpenAI's SDK sends out
class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

async def forward_to_openai(payload: ChatCompletionRequest, http_client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    Takes our validated local schema payload, converts it back to a raw 
    JSON dictionary structure, and ships it off asynchronously using the 
    shared persistent connection pool.
    """
    # -------------------------------------------------------------------------
    # 🛡️ LOAD TEST TARGET SHORT-CIRCUIT
    # -------------------------------------------------------------------------
    if settings.MOCK_MODE:
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "This is a lightning-fast, zero-token mock response for load testing."
                }
            }]
        }

    url = "https://api.openai.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # ✅ FIX: Reusing the global shared pool instance instead of allocating a fresh context
    response = await http_client.post(
        url, 
        json=payload.model_dump(exclude_none=True), 
        headers=headers
    )
    
    # Ensure our gateway throws an immediate error if OpenAI breaks
    response.raise_for_status()
    
    # Return the parsed response dictionary back to the router endpoint
    return response.json()