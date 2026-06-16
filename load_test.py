import asyncio
import httpx
import time

# FIXED: Removed duplicate /v1/ segment to match your FastAPI route mapping definition
URL = "http://localhost:8000/v1/chat/completions"

async def fire_single_payload(client: httpx.AsyncClient, request_id: int):
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": f"Stateless benchmark query number {request_id}"}],
        "temperature": 0.7
    }
    try:
        response = await client.post(URL, json=payload, timeout=60.0)
        return response.status_code
    except Exception as e:
        return f"Failed: {str(e)}"

async def run_heavy_load_test(requests: int):
    # Python Convention: Using {requests:,} auto-formats large numbers with commas (e.g., 1,000)
    print(f"🏋️  Preparing {requests:,} concurrent payloads...")
    
    # BEST PRACTICE: Scale connection limits dynamically based on target request size
    # This prevents the test script itself from bottlenecking its own event loop
    limits = httpx.Limits(
        max_connections=requests, 
        max_keepalive_connections=max(20, requests // 2)
    )
    
    async with httpx.AsyncClient(limits=limits) as client:
        # ✅ DYNAMIC RANGE: Replaced the hardcoded 1001 slice with our parameter bound
        tasks = [fire_single_payload(client, i) for i in range(1, requests + 1)]
        
        print(f"🔥 FLOODING GATEWAY: Executing {requests:,} simultaneous requests...")
        start_time = time.perf_counter()
        
        # Fire them all completely concurrently over the uvloop worker space
        results = await asyncio.gather(*tasks)
        
        end_time = time.perf_counter()
        total_duration = end_time - start_time
        
        # Parse the execution metrics
        success_count = results.count(200)
        failed_count = len(results) - success_count
        
        print("\n📊 --- BENCHMARK RESULTS ---")
        print(f"Total Requests Processed: {len(results):,}")
        print(f"Successful HTTP 200s:    {success_count:,}")
        print(f"Failed/Dropped Packets:  {failed_count:,}")
        print(f"Total Execution Time:    {round(total_duration, 4)} seconds")
        print(f"Throughput Velocity:     {round(len(results) / total_duration, 1)} requests/sec")

if __name__ == "__main__":
    # 🎯 STEP LOAD CONTROL INTERFACE
    # Adjust this variable step-by-step to scale your load tests: 10 -> 100 -> 500 -> 1000
    TOTAL_CONCURRENT_REQUESTS = 1000
    
    asyncio.run(run_heavy_load_test(TOTAL_CONCURRENT_REQUESTS))