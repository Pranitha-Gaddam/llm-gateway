"""Limits that make it safe to expose the gateway on the owner's API key.

Rate limits alone do not protect a budget — anyone can cycle IPs for a fresh
window. The load-bearing control is the daily spend ceiling. Everything here is
inert unless PUBLIC_DEMO is set.
"""

import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from app.cache import redis_client
from app.core.config import settings

VISITOR_COOKIE = "gw_visitor"
MODERATION_URL = "https://api.openai.com/v1/moderations"

# Per million tokens. Only models on the allowlist can be requested, so this
# table only needs to cover those plus the rewrite model.
PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
DEFAULT_PRICING = (0.15, 0.60)


def new_visitor_id() -> str:
    return uuid.uuid4().hex


def _spend_key() -> str:
    return f"gateway:spend:{datetime.now(timezone.utc):%Y-%m-%d}"


def estimate_cost(usage: dict, model: str) -> float:
    """Dollar cost of one upstream call from its usage block."""
    inp, out = PRICING.get(model, DEFAULT_PRICING)
    return (
        usage.get("prompt_tokens", 0) / 1_000_000 * inp
        + usage.get("completion_tokens", 0) / 1_000_000 * out
    )


async def record_spend(usage: dict, model: str) -> None:
    """Add one call's cost to today's running total."""
    cost = estimate_cost(usage, model)
    if cost <= 0:
        return
    try:
        key = _spend_key()
        pipe = redis_client.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 172_800)  # two days, so yesterday stays readable
        await pipe.execute()
    except Exception as e:
        print(f"Spend tracking skipped: {e}")


async def spend_today() -> float:
    try:
        return float(await redis_client.get(_spend_key()) or 0.0)
    except Exception:
        return 0.0


async def budget_exhausted() -> bool:
    """
    Whether upstream calls should stop.

    Cache hits are deliberately still served when this is True: the demo
    degrades to what it already knows rather than going dark.
    """
    if not settings.PUBLIC_DEMO:
        return False
    return await spend_today() >= settings.DAILY_BUDGET_USD


def allowed_models() -> set[str]:
    return {m.strip() for m in settings.ALLOWED_MODELS.split(",") if m.strip()}


def check_request(model: str, messages: list) -> None:
    """
    Reject requests that would cost more than the demo is willing to spend.

    Without the model allowlist a visitor can ask for a frontier model and spend
    roughly twenty times the per-request budget.
    """
    if not settings.PUBLIC_DEMO:
        return

    permitted = allowed_models()
    if model not in permitted:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This demo only serves {', '.join(sorted(permitted))}. "
                f"Run it yourself with your own key to use {model}."
            ),
        )

    if len(messages) > settings.MAX_MESSAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Conversations are limited to {settings.MAX_MESSAGES} messages in this demo.",
        )

    total_chars = sum(len(m.content) for m in messages)
    if total_chars > settings.MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Input is limited to {settings.MAX_INPUT_CHARS} characters in this demo.",
        )


def clamp_max_tokens(requested: int | None) -> int:
    """Cap output length regardless of what the caller asked for."""
    if not settings.PUBLIC_DEMO:
        return requested
    ceiling = settings.MAX_OUTPUT_TOKENS
    return ceiling if requested is None else min(requested, ceiling)


async def check_rate_limit(visitor_id: str) -> None:
    """Fixed window per visitor. Slows honest traffic; the budget stops the rest."""
    if not settings.PUBLIC_DEMO:
        return

    window = settings.RATE_LIMIT_WINDOW_SECONDS
    bucket = int(time.time()) // window
    key = f"gateway:rate:{visitor_id}:{bucket}"

    try:
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        count, _ = await pipe.execute()
    except Exception as e:
        print(f"Rate limit check skipped: {e}")
        return

    if count > settings.RATE_LIMIT_REQUESTS:
        retry_after = window - (int(time.time()) % window)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit reached ({settings.RATE_LIMIT_REQUESTS} requests per "
                f"{window // 60} minutes). Try again in {retry_after}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )


async def check_moderation(text: str, http_client: httpx.AsyncClient) -> None:
    """
    Screen input before it reaches the chat API.

    Only runs on the miss path. A cache hit returns content that already passed
    this check when it was first stored, and the moderation endpoint is free.
    """
    if not settings.PUBLIC_DEMO or not settings.ENABLE_MODERATION:
        return

    try:
        response = await http_client.post(
            MODERATION_URL,
            json={"input": text[: settings.MAX_INPUT_CHARS]},
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        flagged = response.json()["results"][0]["flagged"]
    except HTTPException:
        raise
    except Exception as e:
        # Fail open: a moderation outage should not take the demo down.
        print(f"Moderation check skipped: {type(e).__name__}")
        return

    if flagged:
        raise HTTPException(
            status_code=400,
            detail="That request was flagged by content moderation and was not sent.",
        )
