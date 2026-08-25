"""Self-checking walkthrough of the gateway's caching behaviour.

Every step states what it expects, sends a real request, and verifies the
outcome against the X-Cache header the gateway returns. Nothing here is narrated
without being checked, so the output is evidence rather than a claim.

Usage: start the gateway, then `doppler run -- python demo.py`.
"""

import asyncio
import random
import sys

import httpx

BASE = "http://localhost:8000"
URL = f"{BASE}/v1/chat/completions"
MODEL = "gpt-4o-mini"
MAX_TOKENS = 150

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

# Rotated per run so a second run starts from genuine cache misses. A random
# nonce cannot do this for the semantic tier: a meaningless token is precisely
# what an embedding ignores, so the subject itself has to change.
TOPICS = ["Redis", "Docker", "Kafka", "GraphQL", "Kubernetes",
          "PostgreSQL", "Terraform", "RabbitMQ", "MongoDB", "Nginx"]
SUBJECTS = ["a reverse proxy", "a message queue", "a service mesh", "a CDN"]
REWORDS = [
    ("How do I reverse a string in Python?", "What is the way to reverse a string in Python?"),
    ("How do I center a div in CSS?", "How can I center a div using CSS?"),
    ("What does a load balancer do?", "What is the purpose of a load balancer?"),
]

results = []


def heading(text):
    print(f"\n{BOLD}{text}{RESET}\n{DIM}{'-' * 68}{RESET}")


async def check(client, description, messages, expect, note=""):
    """Send one request and verify which tier served it."""
    response = await client.post(
        URL,
        json={"model": MODEL, "messages": messages,
              "temperature": 0.7, "max_tokens": MAX_TOKENS},
        timeout=90.0,
    )
    if response.status_code != 200:
        print(f"  [{RED}ERROR{RESET}] {description}: HTTP {response.status_code}")
        results.append((description, False))
        return None

    body = response.json()
    tier = response.headers.get("X-Cache", "?")
    latency = float(response.headers.get("X-Cache-Latency-Ms", 0))
    distance = response.headers.get("X-Cache-Distance")

    passed = tier == expect
    results.append((description, passed))

    mark = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    detail = f"served by {tier}, {latency:.0f}ms"
    if distance:
        detail += f", distance {distance}"
    if not passed:
        detail += f" {RED}(expected {expect}){RESET}"

    print(f"  [{mark}] {description}")
    print(f"         {DIM}{detail}{RESET}")
    if note:
        print(f"         {DIM}{note}{RESET}")
    return body["choices"][0]["message"]["content"], latency


async def main():
    topic_a, topic_b = random.sample(TOPICS, 2)
    subject = random.choice(SUBJECTS)
    first_wording, second_wording = random.choice(REWORDS)
    nonce = f"{random.randint(1000, 9999)}"

    async with httpx.AsyncClient() as client:
        try:
            health = (await client.get(f"{BASE}/health", timeout=10.0)).json()
        except Exception:
            print(f"{RED}Cannot reach the gateway at {BASE}.{RESET}")
            print("Start it with:  make run")
            sys.exit(1)

        if health.get("status") != "ok":
            print(f"{RED}Gateway is degraded: {health}{RESET}")
            sys.exit(1)

        # Every expectation below assumes nothing is cached yet. Without this a
        # second run would see hits where it expects misses, and report failures
        # for a gateway that is working correctly.
        reset = await client.post(f"{BASE}/v1/cache/reset", timeout=30.0)
        if reset.status_code == 403:
            print(f"{RED}This gateway is running as a public demo, so the cache "
                  f"cannot be cleared.{RESET}")
            print("Run demo.py against a local instance with PUBLIC_DEMO=false.")
            sys.exit(1)
        cleared = reset.json().get("keys_removed", 0)

        print(f"\n{BOLD}LLM Gateway — verified walkthrough{RESET}")
        print(f"{DIM}Gateway: {BASE}   Model: {MODEL}   "
              f"cache cleared ({cleared} keys){RESET}")
        if health.get("budget"):
            b = health["budget"]
            print(f"{DIM}Budget:  ${b['spent_today']:.4f} of ${b['daily_limit']:.2f} used today{RESET}")

        heading("1. Tier 1 — exact match on single-turn prompts")
        q = f"What is {subject}? ({nonce})"
        miss = await check(client, "First ask goes upstream",
                           [{"role": "user", "content": q}], "MISS")
        hit = await check(client, "The same question is served from cache",
                          [{"role": "user", "content": q}], "HIT-EXACT")
        await check(client, "Different casing and spacing still hits",
                    [{"role": "user", "content": f"   WHAT IS {subject.upper()}? ({nonce})   "}],
                    "HIT-EXACT",
                    note="the key is hashed after lowering case and collapsing whitespace")

        heading("2. Tier 2 — matching a reworded question")
        await check(client, "Original phrasing",
                    [{"role": "user", "content": first_wording}], "MISS")
        await check(client, "Reworded, nothing shared but the meaning",
                    [{"role": "user", "content": second_wording}], "HIT-SEMANTIC",
                    note="no marker links these two; the vector index matched them")

        heading("3. Follow-ups are resolved before they are embedded")
        opener_a = f"Who created {topic_a} and when?"
        reply_a, _ = await check(client, f"Chat 1 opens on {topic_a}",
                                 [{"role": "user", "content": opener_a}], "MISS")
        thread_a = [{"role": "user", "content": opener_a},
                    {"role": "assistant", "content": reply_a},
                    {"role": "user", "content": "How does it work?"}]
        await check(client, "Chat 1 asks a follow-up that means nothing alone",
                    thread_a, "MISS",
                    note=f'resolved to "How does {topic_a} work?" before embedding')

        opener_b = f"Who created {topic_b} and when?"
        reply_b, _ = await check(client, f"Chat 2 opens on {topic_b} instead",
                                 [{"role": "user", "content": opener_b}], "MISS")
        await check(client, "Chat 2 asks the identical follow-up",
                    [{"role": "user", "content": opener_b},
                     {"role": "assistant", "content": reply_b},
                     {"role": "user", "content": "How does it work?"}],
                    "MISS",
                    note=f"same words as chat 1, but it resolves to {topic_b} — correctly no match")

        await check(client, "Chat 3 asks that question outright, with no history",
                    [{"role": "user", "content": f"Explain how {topic_a} works"}],
                    "HIT-SEMANTIC",
                    note="matches what chat 1's follow-up resolved to")

        heading("4. The resolved question is itself cached")
        await check(client, "Replaying chat 1's follow-up pays for no second rewrite",
                    thread_a, "HIT-SEMANTIC")

        passed = sum(1 for _, ok in results if ok)
        total = len(results)
        heading("Summary")
        colour = GREEN if passed == total else RED
        print(f"  {colour}{passed}/{total} checks passed{RESET}")
        if miss and hit and hit[1] > 0:
            print(f"  Cache hit {miss[1] / hit[1]:.0f}x faster than a miss "
                  f"{DIM}({hit[1]:.1f}ms vs {miss[1]:.0f}ms){RESET}")
        print(f"\n  Playground: {BOLD}{BASE}/{RESET}")
        print(f"  Any single request: {DIM}curl -i {URL} ... | grep -i x-cache{RESET}\n")

        sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
