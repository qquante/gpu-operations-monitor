"""
Base class for all monitors.
Each monitor inherits this, implements fetch(), and gets:
  - Redis connection
  - Polling loop at fixed interval
  - Exponential backoff on errors
  - Publishes JSON to Redis key + pub/sub channel
"""
import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class BaseMonitor(ABC):
    def __init__(
        self,
        redis_host: str,
        redis_port: int,
        poll_interval: float,
        redis_key: str,
    ) -> None:
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.poll_interval = poll_interval
        self.redis_key = redis_key
        self.redis: aioredis.Redis | None = None
        self.redis_ttl_seconds = max(30, int(os.getenv("REDIS_TTL_SECONDS") or "30"))
        self._backoff: float = 1.0
        self._max_backoff: float = 60.0

    async def _connect_redis(self) -> None:
        self.redis = aioredis.from_url(
            f"redis://{self.redis_host}:{self.redis_port}",
            decode_responses=True,
        )
        await self.redis.ping()
        logger.info(
            f"[{self.redis_key}] Redis connected at "
            f"{self.redis_host}:{self.redis_port}"
        )

    @abstractmethod
    async def fetch(self) -> dict:
        """Fetch data from source. Must return a dict."""

    async def _publish(self, data: dict) -> None:
        data["_ts"] = time.time()
        payload = json.dumps(data, ensure_ascii=False)
        await self.redis.set(self.redis_key, payload, ex=self.redis_ttl_seconds)
        # Pub/sub only needs to wake listeners; the full payload stays in the key.
        await self.redis.publish(
            self.redis_key,
            json.dumps({"key": self.redis_key, "ts": data["_ts"]}, ensure_ascii=False),
        )

    async def run(self) -> None:
        await self._connect_redis()
        logger.info(
            f"[{self.redis_key}] Started — polling every {self.poll_interval}s"
        )
        while True:
            start = time.monotonic()
            try:
                data = await self.fetch()
                await self._publish(data)
                self._backoff = 1.0
                elapsed = time.monotonic() - start
                logger.debug(
                    f"[{self.redis_key}] OK in {elapsed:.2f}s"
                )
            except Exception as exc:
                logger.error(
                    f"[{self.redis_key}] Error: {exc!r} "
                    f"— retry in {self._backoff:.0f}s"
                )
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, self._max_backoff)
                continue

            # Sleep for remaining interval
            elapsed = time.monotonic() - start
            sleep_for = max(0.0, self.poll_interval - elapsed)
            await asyncio.sleep(sleep_for)
