# simulate_traffic.py
import asyncio
import httpx
import random

URL = "http://localhost:8000/v1/chat/completions"

# 1. Stateless distinct prompts (Triggers Misses -> Populates Cache)
STATELESS_PROMPTS = [
    "What is the capital of France?",
    "Explain quantum computing in simple terms.",
    "How do I write an async function in Python?",
    "What is the distance between the Earth and the Moon?",
    "How does a Retrieval-Augmented Generation system work?",
    "What is the boiling point of nitrogen?",
    "Who wrote the play Hamlet?",
    "What is the purpose of an API gateway proxy?",
    "How do microservices communicate with each other?",
    "Tell me a short joke about computer science."
]

# 2. Rephrased or drifted variations (Triggers Tier 2 Semantic Matches)
SEMANTIC_VARIATIONS = [
    "Can you tell me France's capital city?",
    "Explain quantum computers simply.",
    "How to make an asynchronous function in python code?",
    "What's the distance from Earth to Moon?",
    "Can you explain the architecture of RAG systems?",
    "At what temperature does nitrogen boil?",
    "Which author wrote Hamlet?",
    "Why do engineers use an LLM gateway proxy?",
    "What are common communication patterns between microservices?",
    "Give me a quick funny CS joke."
]

# 3. Multi-turn conversational history tracks (Triggers contextual vector analysis)
CONVERSATIONAL_THREADS = [
    [
        {"role": "user", "content": "I want to learn about FastAPI."},
        {"role": "assistant", "content": "FastAPI is a modern, fast web framework for building APIs with Python."},
        {"role": "user", "content": "How do I implement background tasks in it?"} # Context-dependent turn
    ],
    [
        {"role": "user", "content": "Let's discuss Docker containers."},
        {"role": "assistant", "content": "Docker allows developers to package applications into isolated containers."},
        {"role": "user", "content": "What is the best way to optimize their image sizes?"} # Context-dependent turn
    ],
    [
        {"role": "user", "content": "Do you know about Redis Stack?"},
        {"role": "assistant", "content": "Yes, Redis Stack extends Redis with vector search, JSON documents, and indexing."},
        {"role": "user", "content": "Show me how to run a KNN query inside it."} # Context-dependent turn
    ]
]

async def fire_payload(client: httpx.AsyncClient, messages: list, desc: str):
    payload = {"model": "gpt-4o", "messages": messages, "temperature": 0.7}
    try:
        res = await client.post(URL, json=payload, timeout=10.0)
        print(f" -> Sent: [{desc}] | Status: {res.status_code}")
    except Exception as e:
        print(f" -> Error sending [{desc}]: {str(e)}")

async def main():
    print("🔥 Starting organic traffic simulation (30 targeted payloads)...")
    
    async with httpx.AsyncClient() as client:
        # Phase 1: Establish the baseline cache (10 Requests)
        print("\n📥 [Phase 1/3] Seeding the cache with distinct stateless queries...")
        for prompt in STATELESS_PROMPTS:
            msgs = [{"role": "user", "content": prompt}]
            await fire_payload(client, msgs, "Stateless Seed")
            await asyncio.sleep(0.1) # Smooth pacing
            
        # Phase 2: Fire exact duplicates and subtle adjustments (10 Requests)
        print("\n🔁 [Phase 2/3] Firing exact duplicates and casing adjustments...")
        for prompt in STATELESS_PROMPTS:
            # Randomly alternate between an exact duplication and a messy string casing variant
            chosen = prompt if random.random() > 0.5 else f"  {prompt.upper()}   "
            msgs = [{"role": "user", "content": chosen}]
            await fire_payload(client, msgs, "Tier 1 Exact Match attempt")
            
        # Phase 3: Fire semantic rephrasings and stateful loops (10 Requests)
        print("\n🧠 [Phase 3/3] Firing semantic variations and stateful history loops...")
        for prompt in SEMANTIC_VARIATIONS:
            msgs = [{"role": "user", "content": prompt}]
            await fire_payload(client, msgs, "Tier 2 Semantic Match attempt")
            
        for thread in CONVERSATIONAL_THREADS:
            await fire_payload(client, thread, "Context Thread Match attempt")

    print("\n✅ Simulation complete! Refresh http://localhost:8000/v1/analytics to view the telemetry distribution.")

if __name__ == "__main__":
    asyncio.run(main())