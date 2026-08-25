"""Throughput benchmark for the cache-hit path.

One prompt is sent to warm the cache, then the same prompt is fired 1000 times
concurrently. Only the warm-up reaches the provider, so a run costs a fraction
of a cent and measures the thing that matters for a caching gateway: how fast it
serves what it already knows.
"""

import asyncio
import time
import uuid

import httpx

URL = "http://localhost:8000/v1/chat/completions"
TOTAL_CONCURRENT_REQUESTS = 1000

# Unique per run, so the warm-up is a genuine miss rather than a leftover entry.
PROMPT = f"What is an LLM gateway proxy? (benchmark {uuid.uuid4().hex[:8]})"


def payload():
    return {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0.7,
        "max_tokens": 150,
    }


async def fire(client: httpx.AsyncClient):
    try:
        response = await client.post(URL, json=payload(), timeout=60.0)
        return response.status_code, response.headers.get("X-Cache", "?")
    except Exception as e:
        return f"failed: {type(e).__name__}", "?"


async def main():
    limits = httpx.Limits(
        max_connections=TOTAL_CONCURRENT_REQUESTS,
        max_keepalive_connections=max(20, TOTAL_CONCURRENT_REQUESTS // 2),
    )

    # One client throughout: cache entries are scoped per visitor, and the
    # visitor cookie is set on the warm-up response. A fresh client would miss
    # on every request.
    async with httpx.AsyncClient(limits=limits) as client:
        print("Warming the cache (one upstream call)...")
        status, tier = await fire(client)
        if status != 200:
            print(f"Warm-up failed: {status}. Is the gateway running?")
            return
        print(f"  warm-up served by {tier}\n")

        print(f"Firing {TOTAL_CONCURRENT_REQUESTS:,} concurrent requests...")
        start = time.perf_counter()
        results = await asyncio.gather(
            *(fire(client) for _ in range(TOTAL_CONCURRENT_REQUESTS))
        )
        duration = time.perf_counter() - start

        ok = sum(1 for s, _ in results if s == 200)
        hits = sum(1 for _, t in results if t and t.startswith("HIT"))

        print("\n--- Results ---")
        print(f"Total requests:  {len(results):,}")
        print(f"HTTP 200:        {ok:,}")
        print(f"Cache hits:      {hits:,}")
        print(f"Upstream calls:  {len(results) - hits:,}")
        print(f"Duration:        {round(duration, 4)}s")
        print(f"Throughput:      {round(len(results) / duration, 1)} req/sec")
        print(f"Mean latency:    {round(duration / len(results) * 1000, 2)}ms")


if __name__ == "__main__":
    asyncio.run(main())
