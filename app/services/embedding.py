import httpx
from fastapi import HTTPException
from app.core.config import settings

OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"

async def get_embedding(text: str, http_client: httpx.AsyncClient) -> list[float]:
    """
    Takes a raw text prompt and makes an asynchronous HTTP request to OpenAI's 
    embeddings API to convert the string into a 1,536-dimensional mathematical coordinate array.
    """
    if settings.MOCK_MODE:
        return [0.001] * 1536
    
    # 1. Protect against empty strings before hitting the network
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="Cannot generate embedding for empty text.")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
    }
    
    payload = {
        "input": text.strip(),
        "model": "text-embedding-3-small"
    }

    response = await http_client.post(OPENAI_EMBEDDING_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
