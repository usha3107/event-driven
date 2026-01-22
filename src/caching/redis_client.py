import json
import logging
from redis import asyncio as aioredis
from src.core.config import settings

logger = logging.getLogger(__name__)

class RedisClient:
    def __init__(self):
        self.redis = None

    async def connect(self):
        if not self.redis:
            self.redis = await aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
            logger.info("Connected to Redis.")

    async def close(self):
        if self.redis:
            await self.redis.close()

    async def get_cached_order(self, order_id: str):
        if not self.redis:
            await self.connect()
        try:
            data = await self.redis.get(f"order:{order_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    async def set_cached_order(self, order_id: str, data: dict, ttl: int = 60):
        if not self.redis:
            await self.connect()
        try:
            await self.redis.set(f"order:{order_id}", json.dumps(data, default=str), ex=ttl)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    async def check_rate_limit(self, ip_address: str, limit: int, window: int) -> bool:
        """
        Returns True if request is allowed, False if rate limited.
        """
        if not settings.API_RATE_LIMIT_ENABLED:
            return True
            
        if not self.redis:
            await self.connect()
            
        key = f"rate_limit:{ip_address}"
        try:
            # Simple fixed window counter
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, window)
            
            return current <= limit
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return True # Fail open to avoid blocking users on cache failure

redis_client = RedisClient()

async def get_redis():
    if not redis_client.redis:
        await redis_client.connect()
    return redis_client
