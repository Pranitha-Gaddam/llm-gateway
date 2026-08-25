import redis.asyncio as aioredis

from app.core.config import settings

# decode_responses=True so reads come back as str rather than bytes.
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
