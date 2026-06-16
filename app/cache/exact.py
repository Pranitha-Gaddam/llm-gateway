import hashlib
import json
from app.services.llm import ChatCompletionRequest

def generate_exact_cache_key(payload: ChatCompletionRequest) -> str:
    """
    Takes the validated user payload request, serializes the internal structures 
    into a strict sorted string, and computes a unique SHA-256 fingerprint hash string.
    """
    # 1. Extract only the critical parts of the request that change the AI's output
    cacheable_data = {
        "model": payload.model,
        "messages": [msg.model_dump() for msg in payload.messages],
        "temperature": payload.temperature
    }
    
    # 2. Turn the dictionary into a standardized text string. 
    # sort_keys=True guarantees the dictionary properties are always in alphabetical order
    serialized_string = json.dumps(cacheable_data, sort_keys=True)
    
    # 3. Feed the string into the SHA-256 calculator
    # We must use .encode('utf-8') because cryptographic functions require raw bytes, not raw text strings
    hasher = hashlib.sha256(serialized_string.encode('utf-8'))
    
    # 4. Return the 64-character hexadecimal representation of the hash string
    # We prefix it with 'exact:' so we can distinguish it from vector caches on Day 2
    return f"exact:{hasher.hexdigest()}"