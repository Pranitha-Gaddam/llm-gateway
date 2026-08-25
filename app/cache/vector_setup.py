from redis.exceptions import ResponseError
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

from app.cache import redis_client
from app.services.embedding import EMBEDDING_DIMENSIONS

INDEX_NAME = "llm_semantic_cache_v2"


async def init_vector_index():
    """
    Create the Redis Stack vector index on boot if it isn't already there.

    Safe to call concurrently: under multiple uvicorn workers every process
    runs this at once, so losing the race to create the index is expected and
    treated as success.
    """
    try:
        await redis_client.ft(INDEX_NAME).info()
        return
    except ResponseError:
        pass

    schema = (
        TextField("$.prompt", as_name="prompt"),
        TextField("$.response", as_name="response"),
        # Restricts each search to one (model, temperature) pair, so a cached
        # answer is never served for a request that asked for a different model.
        TagField("$.scope", as_name="scope"),
        VectorField(
            "$.embedding",
            "FLAT",  # Exact search; fine at cache-sized document counts.
            {
                "TYPE": "FLOAT32",
                "DIM": EMBEDDING_DIMENSIONS,
                "DISTANCE_METRIC": "COSINE",
            },
            as_name="embedding",
        ),
    )

    try:
        await redis_client.ft(INDEX_NAME).create_index(
            fields=schema,
            definition=IndexDefinition(prefix=["semantic:"], index_type=IndexType.JSON),
        )
    except ResponseError as e:
        if "already exists" not in str(e).lower():
            raise
