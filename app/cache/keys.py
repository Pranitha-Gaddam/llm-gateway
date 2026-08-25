"""Cache key layout: `exact:{owner}:{scope}:{digest}`.

Owner and scope stay in the key rather than folded into the digest, so one
caller's entries can be listed and cleared without touching anyone else's.
The `semantic:` prefix is load-bearing — the Redis index is defined over it.
"""

import hashlib

SHARED_OWNER = "shared"


def owner_tag(visitor_id: str, public: bool) -> str:
    """Which pool of entries a request reads and writes."""
    if not public or not visitor_id:
        return SHARED_OWNER
    return hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()[:12]


def exact_key(owner: str, scope: str, prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return f"exact:{owner}:{scope}:{digest}"


def semantic_key(owner: str, scope: str, anchor: str) -> str:
    digest = hashlib.sha256(anchor.encode("utf-8")).hexdigest()
    return f"semantic:{owner}:{scope}:{digest}"


def owner_patterns(owner: str) -> list[str]:
    """Glob patterns matching every cache entry belonging to one owner."""
    return [f"exact:{owner}:*", f"semantic:{owner}:*"]


def filter_tag(owner: str, scope: str) -> str:
    """
    The value the vector search pre-filters on.

    The Redis key carries owner and scope in the clear so entries can be
    enumerated, but a RediSearch tag filter cannot: the query parser treats
    punctuation as operators. Hashing the pair to hex sidesteps escaping
    entirely while keeping the two searches equivalent.
    """
    return hashlib.sha256(f"{owner}:{scope}".encode("utf-8")).hexdigest()[:16]
