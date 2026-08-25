import hashlib
import json
import struct

from redis.commands.search.query import Query

from app.cache import redis_client
from app.cache.keys import filter_tag, semantic_key
from app.cache.vector_setup import INDEX_NAME, init_vector_index

SEMANTIC_CACHE_TTL_SECONDS = 3600


def scope_tag(
    model: str,
    temperature: float | None,
    system_prompt: str = "",
) -> str:
    """
    Identify which answers are interchangeable with one another.

    Model and temperature both change the output, and a system prompt changes
    the persona answering, so none of them may be crossed. Ownership is handled
    separately, in the key itself, so that one caller's entries stay
    enumerable.
    """
    raw = f"{model}:{temperature}:{system_prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


async def query_semantic_cache(
    query_embedding: list[float],
    owner: str,
    scope: str,
    threshold: float = 0.15,
) -> tuple[dict, float] | None:
    """
    Run a K-nearest-neighbour search for the closest cached answer.

    Returns (response, cosine_distance) when the nearest neighbour is within
    `threshold`, otherwise None. The distance is returned so callers can report
    how close the match actually was.
    """
    byte_vector = struct.pack(f"{len(query_embedding)}f", *query_embedding)

    # Pre-filter by scope, then run KNN over only that model's entries.
    query = (
        Query(f"(@scope:{{{filter_tag(owner, scope)}}})"
              "=>[KNN 1 @embedding $vec_param AS vector_distance]")
        .sort_by("vector_distance")
        .paging(0, 1)
        .return_fields("prompt", "response", "vector_distance")
        .dialect(2)  # Required for vector queries in Redis Stack.
    )

    try:
        results = await redis_client.ft(INDEX_NAME).search(
            query, {"vec_param": byte_vector}
        )
        if not results.docs:
            return None

        match = results.docs[0]
        distance = float(match.vector_distance)
        if distance > threshold:
            return None

        return json.loads(match.response), distance
    except Exception as e:
        # The index can disappear underneath a running gateway (FLUSHALL, or a
        # Redis restart without persistence). Rebuild it so the tier recovers
        # instead of silently degrading to Tier 1 for the rest of the process.
        if "no such index" in str(e).lower():
            print("Semantic index missing; rebuilding.")
            await init_vector_index()
        else:
            print(f"Semantic cache search failed: {e}")
        return None


async def save_to_semantic_cache(
    anchor: str,
    prompt: str,
    response_data: dict,
    embedding: list[float],
    owner: str,
    scope: str,
):
    """
    Store a response keyed by its context anchor.

    The document id is derived from the anchor rather than the prompt alone,
    so that the same follow-up question asked in two different conversations
    is stored as two separate entries.
    """
    redis_key = semantic_key(owner, scope, anchor)

    # IndexType.JSON expects the vector as a plain array of floats.
    document = {
        "prompt": prompt,
        "response": json.dumps(response_data),
        "embedding": embedding,
        "scope": filter_tag(owner, scope),
    }

    try:
        await redis_client.json().set(redis_key, "$", document)
        await redis_client.expire(redis_key, SEMANTIC_CACHE_TTL_SECONDS)
    except Exception as e:
        print(f"Failed to write semantic cache entry: {e}")
