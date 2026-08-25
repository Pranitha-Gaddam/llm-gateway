from app.cache.keys import exact_key

# Tier 1 entries expire after an hour so stale answers don't live forever.
EXACT_CACHE_TTL_SECONDS = 3600


def normalize_prompt(prompt: str) -> str:
    """
    Fold away differences that do not change the question.

    Lowercasing and collapsing runs of whitespace means "  WHAT IS REDIS? "
    and "what is redis?" resolve to the same entry.
    """
    return " ".join(prompt.lower().split())


def generate_exact_cache_key(prompt: str, owner: str, scope: str) -> str:
    """Tier 1 key for a single-turn request."""
    return exact_key(owner, scope, normalize_prompt(prompt))
