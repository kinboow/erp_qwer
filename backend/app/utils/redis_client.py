import redis
from redis.exceptions import RedisError
from app.config import settings


class RedisClient:
    def __init__(self):
        self.client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            db=settings.REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            retry_on_timeout=False
        )

    def get(self, key: str):
        try:
            return self.client.get(key)
        except RedisError:
            return None

    def set(self, key: str, value: str, ex: int = None):
        try:
            return self.client.set(key, value, ex=ex)
        except RedisError:
            return False

    def delete(self, key: str):
        try:
            return self.client.delete(key)
        except RedisError:
            return 0

    def exists(self, key: str):
        try:
            return self.client.exists(key)
        except RedisError:
            return 0

    def expire(self, key: str, seconds: int):
        try:
            return self.client.expire(key, seconds)
        except RedisError:
            return False

    def hget(self, name: str, key: str):
        try:
            return self.client.hget(name, key)
        except RedisError:
            return None

    def hset(self, name: str, key: str, value: str):
        try:
            return self.client.hset(name, key, value)
        except RedisError:
            return 0

    def hdel(self, name: str, key: str):
        try:
            return self.client.hdel(name, key)
        except RedisError:
            return 0


redis_client = RedisClient()
