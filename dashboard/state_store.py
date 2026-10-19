import json
import time
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis


def load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def load_json_dict(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = default or {}
    if not path.exists():
        return dict(fallback)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)
    return data if isinstance(data, dict) else dict(fallback)


def save_json(path: Path, data: Any, *, indent: int | None = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def archive_json(data_dir: Path, prefix: str, data: Any) -> str:
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    archive_path = data_dir / f"{prefix}_archive_{stamp}.json"
    save_json(archive_path, data, indent=2)
    return str(archive_path)


async def redis_get_json(redis_client: aioredis.Redis, key: str, default: Any) -> Any:
    payload = await redis_client.get(key)
    if not payload:
        return default
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return default


async def redis_set_json(redis_client: aioredis.Redis, key: str, data: Any) -> None:
    await redis_client.set(key, json.dumps(data, ensure_ascii=False))


async def load_raw_monitor_state(redis_client: aioredis.Redis, keys: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    raw: dict[str, dict[str, Any]] = {}
    for key in keys:
        data = await redis_get_json(redis_client, key, {})
        raw[key] = data if isinstance(data, dict) and data else {}
        if not raw[key]:
            raw.pop(key, None)
    return raw
