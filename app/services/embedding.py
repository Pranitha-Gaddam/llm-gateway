import httpx
from fastapi import HTTPException

from app.core.config import settings

OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536  # Fixed by EMBEDDING_MODEL; must match the index schema.


async def get_embedding(text: str, http_client: httpx.AsyncClient) -> list[float]:
    """Convert text into an embedding vector for semantic cache lookups."""
    if not text or not text.strip():
        raise HTTPException(
            status_code=400, detail="Cannot generate embedding for empty text."
        )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
    }
    payload = {"input": text.strip(), "model": EMBEDDING_MODEL}

    response = await http_client.post(
        OPENAI_EMBEDDING_URL, json=payload, headers=headers
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]
