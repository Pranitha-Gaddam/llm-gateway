"""Resolves context-dependent follow-ups into standalone questions.

Embedding a follow-up alongside its conversation does not work: assistant turns
run long, so the vector is dominated by the passage. Measured, a standalone
question sits 0.25-0.40 from such an anchor, out of reach of the 0.15 threshold.
Resolving it first brings paraphrases to 0.00-0.13 while leaving genuinely
different questions at 0.19 or more.
"""

import hashlib

import httpx

from app.cache import redis_client
from app.core.config import settings
from app.services.guardrails import record_spend
from app.services.llm import OPENAI_CHAT_URL

REWRITE_CACHE_TTL_SECONDS = 3600
MAX_REWRITE_TOKENS = 60

REWRITE_SYSTEM_PROMPT = (
    "Rewrite the user's latest message as a standalone question that can be "
    "understood without the conversation. Keep it short and keep the user's "
    "wording where possible. Reply with the question only, nothing else."
)

# Openers that signal the message leans on what came before. Anything starting
# with one of these is worth resolving; self-contained questions are not, and
# skipping them keeps the rewrite off the critical path for most requests.
DEPENDENT_OPENERS = (
    "it ", "it's", "its ", "that ", "this ", "they ", "them ", "those ", "these ",
    "he ", "she ", "his ", "her ", "their ", "tell me more", "more about",
    "why", "how so", "how does it", "how do they", "what about", "and ", "but ",
    "go on", "continue", "explain that", "explain it", "elaborate", "such as",
)

# Very short messages are almost always context-dependent regardless of wording.
# The heuristic deliberately errs toward rewriting: a false positive costs one
# cheap, cached call, while a false negative embeds a bare pronoun and poisons
# the lookup.
SELF_CONTAINED_WORD_COUNT = 5


def needs_resolution(text: str) -> bool:
    """Whether this message only makes sense in light of the conversation."""
    stripped = text.strip().lower()
    if not stripped:
        return False
    if len(stripped.split()) < SELF_CONTAINED_WORD_COUNT:
        return True
    return stripped.startswith(DEPENDENT_OPENERS)


def _cache_key(previous_assistant: str, question: str) -> str:
    digest = hashlib.sha256(
        f"{previous_assistant}\n{question}".encode("utf-8")
    ).hexdigest()
    return f"rewrite:{digest}"


async def resolve_followup(
    previous_assistant: str,
    question: str,
    http_client: httpx.AsyncClient,
) -> str | None:
    """
    Turn a context-dependent question into a standalone one.

    Returns None when the caller should fall back to its own anchor, so a
    rewrite failure degrades the cache rather than failing the request.

    The result is cached: the rewrite runs before the cache lookup, so without
    this a repeated conversation would pay for a model call even on a hit.
    """
    key = _cache_key(previous_assistant, question)

    try:
        cached = await redis_client.get(key)
        if cached:
            return cached
    except Exception as e:
        print(f"Rewrite cache read skipped: {e}")

    transcript = f"assistant: {previous_assistant}\nuser: {question}"
    try:
        response = await http_client.post(
            OPENAI_CHAT_URL,
            json={
                "model": settings.REWRITE_MODEL,
                "messages": [
                    {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
                    {"role": "user", "content": transcript},
                ],
                "max_tokens": MAX_REWRITE_TOKENS,
                "temperature": 0.0,
            },
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        body = response.json()
    except Exception as e:
        print(f"Follow-up rewrite failed, falling back: {type(e).__name__}")
        return None

    resolved = body["choices"][0]["message"]["content"].strip()
    if not resolved:
        return None

    # This call spends real money, so it counts against the demo budget.
    await record_spend(body.get("usage", {}), settings.REWRITE_MODEL)

    try:
        await redis_client.setex(key, REWRITE_CACHE_TTL_SECONDS, resolved)
    except Exception as e:
        print(f"Rewrite cache write skipped: {e}")

    return resolved
