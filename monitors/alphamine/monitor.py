"""
Monitor AlphaMine / AlphaPool wallet dashboard.
Publishes to Redis key: monitor:alphamine
"""
import asyncio
import logging
import os
import re
import sys
from typing import Any

sys.path.insert(0, "/app")

import httpx

from shared.base_monitor import BaseMonitor
from shared.gpu_hashrates import normalize_gpu_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("monitor.alphamine")

ALPHAMINE_API_URL = "https://pearl.alphapool.tech/api/miner/{wallet}"


HASH_UNITS = {
    "H": 1.0,
    "KH": 1e3,
    "MH": 1e6,
    "GH": 1e9,
    "TH": 1e12,
    "PH": 1e15,
    "EH": 1e18,
}


def parse_hashrate_to_ths(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value) / 1e12
    text = str(value or "").strip().upper()
    if not text:
        return 0.0
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?H)(?:/S)?", text)
    if not match:
        return 0.0
    amount = float(match.group(1))
    multiplier = HASH_UNITS.get(match.group(2), 1.0)
    return amount * multiplier / 1e12


def raw_hashrate_to_ths(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value) / 1e12
    return 0.0


def first_present(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


class AlphaMineMonitor(BaseMonitor):
    def __init__(self, wallet: str, **kwargs):
        super().__init__(**kwargs)
        self.wallet = wallet
        self.url = ALPHAMINE_API_URL.format(wallet=wallet)

    async def fetch(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            raw = resp.json()

        workers = []
        for worker in raw.get("workers", []) or []:
            if not isinstance(worker, dict):
                continue
            name = str(first_present(worker, "name", "worker", "worker_name", "label") or "")
            gpu_raw = str(first_present(worker, "gpu", "gpu_card", "device", "card") or "")
            live_hash = first_present(worker, "hashrate_live", "current_hashrate", "hashrateLive")
            hash_1h = first_present(worker, "hashrate_1h", "hashrate1h", "estHash1h")
            hash_24h = first_present(worker, "hashrate", "hashrate_24h", "hashrate24h")
            hash_value = live_hash or hash_1h or hash_24h
            workers.append({
                "worker_name": name,
                "gpu_card": gpu_raw,
                "gpu_card_normalized": normalize_gpu_name(gpu_raw),
                "gpu_count": worker.get("gpu_count") or worker.get("gpus") or 1,
                "hashrate_ths": round(parse_hashrate_to_ths(hash_value), 4),
                "hashrate_formatted": str(hash_value or ""),
                "hashrate_live_ths": round(parse_hashrate_to_ths(live_hash), 4),
                "hashrate_1h_ths": round(parse_hashrate_to_ths(hash_1h), 4),
                "hashrate_24h_ths": round(parse_hashrate_to_ths(hash_24h), 4),
                "hashrate_live_formatted": str(live_hash or ""),
                "hashrate_1h_formatted": str(hash_1h or ""),
                "hashrate_24h_formatted": str(hash_24h or ""),
                "is_connected": bool(worker.get("online", worker.get("is_connected", True))),
                "last_seen_at": first_present(worker, "last_share", "last_seen", "lastSeen", "last_share_at"),
                "difficulty": worker.get("difficulty"),
                "shares24h": worker.get("shares24h") or worker.get("shares_24h") or 0,
                "stale_shares24h": worker.get("stale24h") or worker.get("stale_shares24h") or 0,
                "raw": worker,
            })

        total_hashrate_live_ths = sum(float(worker.get("hashrate_live_ths") or 0.0) for worker in workers)
        total_hashrate_1h_ths = (
            raw_hashrate_to_ths(raw.get("estHash1hRaw"))
            or parse_hashrate_to_ths(raw.get("estHash1h"))
        )
        total_hashrate_24h_ths = (
            raw_hashrate_to_ths(raw.get("estHash24hRaw"))
            or parse_hashrate_to_ths(raw.get("estHash24h"))
        )
        total_hashrate_ths = total_hashrate_live_ths or total_hashrate_1h_ths or total_hashrate_24h_ths
        online_workers = sum(1 for worker in workers if worker.get("is_connected"))
        return {
            "wallet_address": raw.get("address", self.wallet),
            "is_online": online_workers > 0 or total_hashrate_ths > 0,
            "mode": raw.get("mode", "PPLNS"),
            "worker_count": len(workers),
            "online_worker_count": online_workers,
            "total_hashrate_ths": round(total_hashrate_ths, 4),
            "total_hashrate_formatted": f"{total_hashrate_live_ths:.2f} TH/s live" if total_hashrate_live_ths else raw.get("estHash1h") or raw.get("estHash24h") or "",
            "hashrate_live_ths": round(total_hashrate_live_ths, 4),
            "hashrate_1h_ths": round(total_hashrate_1h_ths, 4),
            "hashrate_24h_ths": round(total_hashrate_24h_ths, 4),
            "hashrate_1h_formatted": raw.get("estHash1h", ""),
            "hashrate_24h_formatted": raw.get("estHash24h", ""),
            "pending_balance_prl": raw.get("balance_prl", 0.0),
            "total_paid_prl": raw.get("total_paid_prl", 0.0),
            "payments_count": raw.get("payments_count", 0),
            "shares24h": raw.get("shares24h", 0),
            "workers": workers,
            "payments": raw.get("payments", [])[:20],
            "blocks": raw.get("blocks", [])[:20],
            "first_seen": raw.get("first_seen", 0),
            "last_seen": raw.get("last_seen", 0),
        }


async def main() -> None:
    wallet = os.getenv("ALPHAMINE_WALLET") or os.getenv("AKOYA_WALLET", "")
    if not wallet:
        raise RuntimeError("ALPHAMINE_WALLET or AKOYA_WALLET env var is required")

    monitor = AlphaMineMonitor(
        wallet=wallet,
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=float(os.getenv("POLL_INTERVAL", 5)),
        redis_key="monitor:alphamine",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
