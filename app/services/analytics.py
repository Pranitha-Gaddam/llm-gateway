# app/services/analytics.py

import time
from app.cache import redis_client

ANALYTICS_KEY = "gateway:analytics"

def calculate_estimated_savings(response_body: dict) -> float:
    """
    Derives monetary value based on saved token consumption footprints.
    Rates: $2.50/1M input tokens, $10.00/1M output tokens (GPT-4o standard).
    """
    try:
        usage = response_body.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        return ((prompt_tokens / 1_000_000) * 2.50) + ((completion_tokens / 1_000_000) * 10.00)
    except Exception:
        return 0.0025  # Fallback: quarter of a cent per request if empty/mocked

async def track_cache_hit(tier: str, execution_duration: float, response_payload: dict):
    """Logs atomic metrics inside Redis for Tier 1 or Tier 2 performance wins."""
    savings = calculate_estimated_savings(response_payload)
    field_target = "exact_hits" if tier == "tier1" else "semantic_hits"
    
    await redis_client.hget(ANALYTICS_KEY, field_target) # warm check if needed
    await redis_client.hincrby(ANALYTICS_KEY, field_target, 1)
    await redis_client.hincrbyfloat(ANALYTICS_KEY, "total_latency_saved", execution_duration)
    await redis_client.hincrbyfloat(ANALYTICS_KEY, "total_cost_saved", savings)

async def track_cache_miss(live_execution_duration: float):
    """Logs atomic metrics inside Redis when fallback upstream computation occurs."""
    await redis_client.hincrby(ANALYTICS_KEY, "cache_misses", 1)
    await redis_client.hincrbyfloat(ANALYTICS_KEY, "live_latency_sum", live_execution_duration)

async def compile_telemetry_report() -> dict:
    """Retrieves raw telemetry fields and builds high-signal performance insights."""
    metrics = await redis_client.hgetall(ANALYTICS_KEY)
    
    # Safe multi-environment dictionary key decoding
    decoded = {
        k.decode('utf-8') if isinstance(k, bytes) else k: 
        v.decode('utf-8') if isinstance(v, bytes) else v 
        for k, v in metrics.items()
    }
    
    exact_hits = int(decoded.get("exact_hits", 0))
    semantic_hits = int(decoded.get("semantic_hits", 0))
    cache_misses = int(decoded.get("cache_misses", 0))
    
    total_hits = exact_hits + semantic_hits
    total_requests = total_hits + cache_misses
    
    total_latency_saved = float(decoded.get("total_latency_saved", 0.0))
    live_latency_sum = float(decoded.get("live_latency_sum", 0.0))
    
    avg_live = round(live_latency_sum / cache_misses, 4) if cache_misses > 0 else 0.0
    avg_cached = round(total_latency_saved / total_hits, 4) if total_hits > 0 else 0.0
    
    return {
        "exact_hits": exact_hits,
        "semantic_hits": semantic_hits,
        "cache_misses": cache_misses,
        "exact_pct": round((exact_hits / total_requests) * 100, 1) if total_requests > 0 else 0.0,
        "semantic_pct": round((semantic_hits / total_requests) * 100, 1) if total_requests > 0 else 0.0,
        "miss_pct": round((cache_misses / total_requests) * 100, 1) if total_requests > 0 else 0.0,
        "efficiency_rate": round((total_hits / total_requests) * 100, 1) if total_requests > 0 else 0.0,
        "avg_live": avg_live,
        "avg_cached": avg_cached,
        "speed_multiplier": round(avg_live / avg_cached, 1) if avg_cached > 0 and avg_live > 0 else 0.0,
        "total_latency_saved": total_latency_saved,
        "total_cost_saved": float(decoded.get("total_cost_saved", 0.0))
    }