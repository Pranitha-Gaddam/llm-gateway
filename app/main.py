import httpx
import json
import hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request # Added Request
from app.core.config import settings
from app.services.llm import ChatCompletionRequest, forward_to_openai
from app.cache import redis_client
from app.cache.vector_setup import init_vector_index
from app.services.embedding import get_embedding
from app.cache.semantic_engine import query_semantic_cache, save_to_semantic_cache

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Initializing high-concurrency connection pools...", flush=True)
    await init_vector_index()
    
    # ✅ CONVENTION: Configure a global HTTP client with tuned pooling limits
    # max_connections=500 allows up to 500 concurrent sockets to stay open simultaneously
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=30.0)
    
    yield
    print("🛑 Closing high-concurrency connection pools...", flush=True)
    await app.state.http_client.aclose()
    await redis_client.close()

app = FastAPI(title="LLM Gateway Proxy", lifespan=lifespan)

def is_context_dependent(messages: list) -> bool:
    """
    Evaluates whether a message history contains conversational turns
    that would make the current question rely on prior context.
    """
    # Filter out system prompts to isolate human/AI context turns
    conversational_turns = [m for m in messages if m.role in ("user", "assistant")]
    return len(conversational_turns) > 1

def build_canonical_context_anchor(request: ChatCompletionRequest) -> str:
    """
    Extracts the crucial context windows (System rules + Prior Answer + Current Question),
    and normalizes the text string to maximize exact and semantic cache hit rates.
    """
    messages = request.messages
    system_content = ""
    last_assistant_content = ""
    last_user_content = ""
    
    # Traverse backward to capture the current question and immediate conversational context
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        role = msg.role
        content = msg.content
        
        if role == "user" and not last_user_content:
            last_user_content = content
            if i - 1 >= 0 and messages[i-1].role == "assistant":
                last_assistant_content = messages[i-1].content
        elif role == "system" and not system_content:
            system_content = content

    anchor_parts = []
    if system_content:
        anchor_parts.append(f"sys: {system_content}")
    if last_assistant_content:
        anchor_parts.append(f"ctx: {last_assistant_content}")
    if last_user_content:
        anchor_parts.append(f"q: {last_user_content}")
        
    raw_anchor = " | ".join(anchor_parts)
    return " ".join(raw_anchor.lower().split())

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    # Pass raw_request.app.state.http_client down into your downstream service functions
    current_user_prompt = next((m.content for m in reversed(request.messages) if m.role == "user"), "")
    if not current_user_prompt:
        return await forward_to_openai(request, raw_request.app.state.http_client)
        
    has_history = is_context_dependent(request.messages)
    context_anchor = build_canonical_context_anchor(request)

    if not has_history:
        global_payload = {"model": request.model, "prompt": current_user_prompt.strip().lower(), "temperature": request.temperature}
        global_hash = hashlib.sha256(json.dumps(global_payload, sort_keys=True).encode('utf-8')).hexdigest()
        global_cache_key = f"exact:global:{global_hash}"

        try:
            cached_global = await redis_client.get(global_cache_key)
            if cached_global:
                print(f"Global cache found: {str(e)}")
                return json.loads(cached_global)
        except Exception as e:
            print(f"⚠️ Tier 1 lookup bypassed: {str(e)}")

    query_vector = None
    try:
        # ✅ Updated to use global client pool
        query_vector = await get_embedding(context_anchor, raw_request.app.state.http_client)
        semantic_match = await query_semantic_cache(query_vector, threshold=0.15)
        if semantic_match:
            return semantic_match
    except Exception as e:
        print(f"⚠️ Tier 2 Semantic lookup bypassed: {str(e)}")

    # ✅ Updated to use global client pool
    openai_response = await forward_to_openai(request, raw_request.app.state.http_client)

    try:
        serialized_response = json.dumps(openai_response)
        if not has_history:
            await redis_client.setex(global_cache_key, 3600, serialized_response)
        if query_vector:
            await save_to_semantic_cache(current_user_prompt, openai_response, query_vector)
    except Exception as e:
        print(f"⚠️ Post-execution caching deferred: {str(e)}")

    return openai_response