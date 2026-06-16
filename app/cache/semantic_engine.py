import struct
import json
import hashlib
from redis.commands.search.query import Query
from app.cache import redis_client
from app.cache.vector_setup import INDEX_NAME

async def query_semantic_cache(query_embedding: list[float], threshold: float = 0.15) -> dict | None:
    """
    Executes a K-Nearest Neighbors (KNN) vector search against Redis.
    Returns the cached AI response string if a close matching meaning is found.
    """
    # Redis vector index parameters require floating-point values packed cleanly into raw bytes
    byte_vector = struct.pack(f"{len(query_embedding)}f", *query_embedding)
    
    # Construct a raw Redis hybrid vector search query.
    base_query = f"(*)=>[KNN 1 @embedding $vec_param AS vector_distance]"
    
    query = (
        Query(base_query)
        .sort_by("vector_distance")
        .paging(0, 1)
        .return_fields("prompt", "response", "vector_distance")
        .dialect(2) # Dialect 2 is mandatory for advanced vector queries in Redis Stack
    )
    
    query_params = {"vec_param": byte_vector}
    
    try:
        results = await redis_client.ft(INDEX_NAME).search(query, query_params)
        
        if results.docs:
            match = results.docs[0]
            distance = float(match.vector_distance)
            
            # Since Cosine DISTANCE is the opposite of SIMILARITY:
            # A distance of 0.10 means a 90% semantic match.
            if distance <= threshold:
                print(f"🧠 SEMANTIC MATCH FOUND! Distance: {round(distance, 4)} (Confidence: {round((1 - distance) * 100, 1)}%)")
                return json.loads(match.response)
                
        return None
    except Exception as e:
        print(f"⚠️ Semantic cache search failed down-stream: {str(e)}")
        return None


async def save_to_semantic_cache(prompt: str, response_data: dict, embedding: list[float]):
    """
    Saves a raw text question, its AI-generated response object, 
    and its semantic coordinate vector into Redis Stack as a JSON document.
    """
    doc_id = hashlib.md5(prompt.encode('utf-8')).hexdigest()
    redis_key = f"semantic:{doc_id}"
    
    # ✅ FIX: When using IndexType.JSON, save embedding directly as a raw Python list of floats.
    # Redis Stack processes the JSON array naturally without native packing conversions.
    document = {
        "prompt": prompt,
        "response": json.dumps(response_data),
        "embedding": embedding 
    }
    
    try:
        # Commit the record to the live cluster memory space
        await redis_client.json().set(redis_key, "$", document)
        print(f"💾 Successfully indexed semantic cache key: {redis_key}")
    except Exception as e:
        print(f"⚠️ Failed to write vector mapping to semantic layer: {str(e)}")