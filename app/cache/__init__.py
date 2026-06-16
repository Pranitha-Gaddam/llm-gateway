import redis.asyncio as aioredis
from app.core.config import settings

# Initialize a global, un-connected Redis client instance placeholder.
# decode_responses=True automatically decodes binary database bytes into clean Python text strings.
redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)