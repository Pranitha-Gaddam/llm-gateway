import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.cache import redis_client
from app.cache.exact import EXACT_CACHE_TTL_SECONDS, generate_exact_cache_key
from app.cache.keys import owner_patterns, owner_tag
from app.cache.semantic_engine import (
    query_semantic_cache,
    save_to_semantic_cache,
    scope_tag,
)
from app.cache.vector_setup import init_vector_index
from app.core.config import settings
from app.services import guardrails
from app.services.embedding import get_embedding
from app.services.llm import ChatCompletionRequest, forward_to_openai
from app.services.rewrite import needs_resolution, resolve_followup

SEMANTIC_DISTANCE_THRESHOLD = 0.15
PLAYGROUND_PAGE = Path(__file__).parent / "static" / "playground.html"

TIER_EXACT = "HIT-EXACT"
TIER_SEMANTIC = "HIT-SEMANTIC"
TIER_MISS = "MISS"

BUDGET_MESSAGE = (
    "This demo has reached its daily API budget, so new questions aren't being "
    "sent upstream right now. Anything already cached still answers instantly — "
    "try one of the guided scenarios, or run the gateway yourself with your own key."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Provide it via Doppler "
            "(doppler run -- make run) or a local .env file."
        )

    await init_vector_index()
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=100)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=30.0)
    yield
    await app.state.http_client.aclose()
    await redis_client.aclose()


app = FastAPI(title="LLM Gateway Proxy", lifespan=lifespan)


def is_context_dependent(messages: list) -> bool:
    """True once a request carries conversation history beyond the opening turn."""
    return len([m for m in messages if m.role in ("user", "assistant")]) > 1


def _last_turns(messages: list) -> tuple[str, str, str]:
    """The system prompt, the preceding assistant turn, and the current question."""
    system_content = last_assistant = last_user = ""
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.role == "user" and not last_user:
            last_user = msg.content
            if i > 0 and messages[i - 1].role == "assistant":
                last_assistant = messages[i - 1].content
        elif msg.role == "system" and not system_content:
            system_content = msg.content
    return system_content, last_assistant, last_user


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


async def build_context_anchor(
    request: ChatCompletionRequest, http_client: httpx.AsyncClient
) -> str:
    """
    Reduce a request to the text whose meaning determines its answer.

    The system prompt is deliberately absent: it scopes which entries are
    comparable, which the scope tag handles, and including it would distort
    the distances between questions.
    """
    _, last_assistant, last_user = _last_turns(request.messages)

    if not is_context_dependent(request.messages) or not needs_resolution(last_user):
        return _normalize(last_user)

    if not await guardrails.budget_exhausted():
        resolved = await resolve_followup(last_assistant, last_user, http_client)
        if resolved:
            return _normalize(resolved)

    # Fall back to pairing the question with its context. This rarely matches,
    # but it is better than embedding a bare pronoun.
    return _normalize(f"ctx: {last_assistant} | q: {last_user}")


def _tagged(
    payload: dict,
    tier: str,
    duration: float,
    visitor_id: str,
    distance: float | None = None,
    status_code: int = 200,
):
    """
    Attach cache provenance to the response.

    These headers are the only telemetry the gateway emits; the playground
    aggregates them itself.
    """
    headers = {
        "X-Cache": tier,
        "X-Cache-Latency-Ms": f"{duration * 1000:.2f}",
    }
    if distance is not None:
        headers["X-Cache-Distance"] = f"{distance:.4f}"

    response = JSONResponse(content=payload, headers=headers, status_code=status_code)
    response.set_cookie(
        guardrails.VISITOR_COOKIE, visitor_id, max_age=86400, httponly=True, samesite="lax"
    )
    return response


def _budget_reply(model: str) -> dict:
    """Shaped like a chat completion so the client renders it as a normal reply."""
    return {
        "choices": [{"message": {"role": "assistant", "content": BUDGET_MESSAGE}}],
        "model": model,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest, raw_request: Request):
    start_time = time.perf_counter()
    http_client = raw_request.app.state.http_client
    visitor_id = raw_request.cookies.get(
        guardrails.VISITOR_COOKIE
    ) or guardrails.new_visitor_id()

    guardrails.check_request(request.model, request.messages)
    await guardrails.check_rate_limit(visitor_id)
    request.max_tokens = guardrails.clamp_max_tokens(request.max_tokens)

    current_user_prompt = next(
        (m.content for m in reversed(request.messages) if m.role == "user"), ""
    )
    if not current_user_prompt:
        upstream = await forward_to_openai(request, http_client)
        await guardrails.record_spend(upstream.get("usage", {}), request.model)
        return _tagged(
            upstream, TIER_MISS, time.perf_counter() - start_time, visitor_id
        )

    system_prompt, _, _ = _last_turns(request.messages)
    has_history = is_context_dependent(request.messages)

    # Answers produced under a different model, temperature, or system prompt are
    # never reused. Ownership is separate: visitors get their own pool only when
    # the gateway is public, because ordinary API clients carry no cookies and
    # would otherwise get a fresh namespace — and so never a cache hit — on
    # every single request.
    cache_owner = owner_tag(visitor_id, settings.PUBLIC_DEMO)
    cache_scope = scope_tag(request.model, request.temperature, system_prompt)
    exact_cache_key = None

    # Tier 1: exact match. Skipped for multi-turn requests, where an identical
    # question can have a different correct answer depending on the history.
    if not has_history:
        exact_cache_key = generate_exact_cache_key(
            current_user_prompt, cache_owner, cache_scope
        )
        try:
            cached = await redis_client.get(exact_cache_key)
            if cached:
                elapsed = time.perf_counter() - start_time
                return _tagged(json.loads(cached), TIER_EXACT, elapsed, visitor_id)
        except Exception as e:
            print(f"Tier 1 lookup skipped: {e}")

    # Tier 2: nearest-neighbour match on the resolved question.
    context_anchor = await build_context_anchor(request, http_client)
    query_vector = None
    try:
        query_vector = await get_embedding(context_anchor, http_client)
        match = await query_semantic_cache(
            query_vector, cache_owner, cache_scope,
            threshold=SEMANTIC_DISTANCE_THRESHOLD,
        )
        if match:
            response, distance = match
            elapsed = time.perf_counter() - start_time
            return _tagged(response, TIER_SEMANTIC, elapsed, visitor_id, distance)
    except Exception as e:
        print(f"Tier 2 lookup skipped: {e}")

    # Nothing cached. Everything past here costs money.
    if await guardrails.budget_exhausted():
        elapsed = time.perf_counter() - start_time
        return _tagged(
            _budget_reply(request.model), TIER_MISS, elapsed, visitor_id, status_code=200
        )

    await guardrails.check_moderation(current_user_prompt, http_client)

    openai_response = await forward_to_openai(request, http_client)
    await guardrails.record_spend(openai_response.get("usage", {}), request.model)
    elapsed = time.perf_counter() - start_time

    # Cache writes are best effort: a Redis failure must not fail the request
    # the caller already paid for upstream.
    try:
        if exact_cache_key:
            await redis_client.setex(
                exact_cache_key, EXACT_CACHE_TTL_SECONDS, json.dumps(openai_response)
            )
        if query_vector:
            await save_to_semantic_cache(
                context_anchor,
                current_user_prompt,
                openai_response,
                query_vector,
                cache_owner,
                cache_scope,
            )
    except Exception as e:
        print(f"Cache write skipped: {e}")

    return _tagged(openai_response, TIER_MISS, elapsed, visitor_id)


@app.get("/", response_class=HTMLResponse)
async def playground():
    """Interactive page for exercising the cache and seeing which tier answers."""
    return FileResponse(PLAYGROUND_PAGE)


@app.post("/v1/cache/reset")
async def reset_cache(raw_request: Request):
    """
    Drop cached entries so a run starts from a known state.

    Publicly this clears only the caller's own pool, which is what makes the
    guided scenarios repeatable without one visitor wiping another's answers.
    """
    visitor_id = raw_request.cookies.get(guardrails.VISITOR_COOKIE) or ""
    owner = owner_tag(visitor_id, settings.PUBLIC_DEMO)

    patterns = owner_patterns(owner)
    if not settings.PUBLIC_DEMO:
        patterns.append("rewrite:*")

    removed = 0
    for pattern in patterns:
        async for key in redis_client.scan_iter(match=pattern, count=500):
            await redis_client.delete(key)
            removed += 1
    return {"status": "cleared", "keys_removed": removed, "owner": owner}


@app.get("/health")
async def health():
    try:
        await redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = str(e)

    body = {
        "status": "ok" if redis_status == "connected" else "degraded",
        "redis": redis_status,
        "public_demo": settings.PUBLIC_DEMO,
    }
    if settings.PUBLIC_DEMO:
        spent = await guardrails.spend_today()
        body["budget"] = {
            "spent_today": round(spent, 4),
            "daily_limit": settings.DAILY_BUDGET_USD,
            "exhausted": spent >= settings.DAILY_BUDGET_USD,
        }
    return body
