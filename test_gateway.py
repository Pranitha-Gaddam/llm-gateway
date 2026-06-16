import asyncio
import httpx

URL = "http://localhost:8000/v1/chat/completions"

async def test_pipeline():
    async with httpx.AsyncClient() as client:
        # ---------------------------------------------------------------------
        # TEST 1: First-Turn Stateless Query (Expect: CACHE MISS -> OpenAI)
        # ---------------------------------------------------------------------
        print("\n🍌 --- RUNNING TEST 1: Initial Global Query ---")
        payload_1 = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "What color is a banana?"}],
            "temperature": 0.7
        }
        res1 = await client.post(URL, json=payload_1, timeout=10.0)
        print(f"Status: {res1.status_code}")
        print(f"AI Response: {res1.json()['choices'][0]['message']['content']}")

        # ---------------------------------------------------------------------
        # TEST 2: Same Stateless Query (Expect: TIER 1 GLOBAL CACHE HIT)
        # ---------------------------------------------------------------------
        print("\n⚡ --- RUNNING TEST 2: Duplicate Global Query ---")
        res2 = await client.post(URL, json=payload_1, timeout=10.0)
        print(f"Status: {res2.status_code}")
        print(f"AI Response (Cached): {res2.json()['choices'][0]['message']['content']}")

        # ---------------------------------------------------------------------
        # TEST 3: Multi-Turn Conversation (Expect: Bypass Global Tier)
        # ---------------------------------------------------------------------
        print("\n🧵 --- RUNNING TEST 3: Conversational Thread (Context-Dependent) ---")
        payload_3 = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "I am writing a script to parse data."},
                {"role": "assistant", "content": "Great! What language are you using?"},
                {"role": "user", "content": "Can you explain this?"} 
            ],
            "temperature": 0.7
        }
        res3 = await client.post(URL, json=payload_3, timeout=10.0)
        print(f"Status: {res3.status_code}")

        # ---------------------------------------------------------------------
        # TEST 4A: Seed Semantic Cache (How a human actually logs an issue)
        # ---------------------------------------------------------------------
        print("\n🧠 --- RUNNING TEST 4A: Seed Semantic Cache (Phrasing A) ---")
        payload_4a = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "my react app is completely blank after building it"},
                {"role": "assistant", "content": "Check your browser console. Are you seeing any 404 errors for your asset paths or a JavaScript runtime crash?"},
                {"role": "user", "content": "yeah it looks like it can't find the main bundle js file"}
            ],
            "temperature": 0.7
        }
        res4a = await client.post(URL, json=payload_4a, timeout=10.0)
        print(f"Status: {res4a.status_code}")
        print(f"Response A: {res4a.json()['choices'][0]['message']['content'][:60]}...")

        # ---------------------------------------------------------------------
        # TEST 4B: Trigger Semantic Hit (Completely casual, different words)
        # ---------------------------------------------------------------------
        print("\n🎯 --- RUNNING TEST 4B: True Semantic Match (Phrasing B) ---")
        payload_4b = {
            "model": "gpt-4o",
            "messages": [
                # Natural rephrasing of the opening issue
                {"role": "user", "content": "my react build is showing a completely blank screen"},
                # Realistic variant of the assistant's context anchor
                {"role": "assistant", "content": "Open up your browser console. Do you notice any 404 asset path errors or a JavaScript runtime crash?"},
                # Natural rephrasing of the final question
                {"role": "user", "content": "yes, it looks like the main bundle js file is missing"}
            ],
            "temperature": 0.7
        }
        
        res4b = await client.post(URL, json=payload_4b, timeout=10.0)
        print(f"Status: {res4b.status_code}")
        print(f"Response B (Should match Response A text perfectly): {res4b.json()['choices'][0]['message']['content'][:60]}...")

if __name__ == "__main__":
    asyncio.run(test_pipeline())