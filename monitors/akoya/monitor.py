"""
Monitor Akoya Pool — akoyapool.com/api/v1/miners/{wallet}
Publishes to Redis key: monitor:akoya
Interval: 5 seconds (configurable via POLL_INTERVAL env var)

Data published:
  is_online                   — wallet online?
  worker_count                — total workers registered
  online_worker_count         — workers currently connected
  total_hashrate_ths          — total pool hashrate in TH/s
  pending_balance_prl         — PRL pending payout
  total_paid_prl              — total PRL paid out
  total_shares24h             — total shares last 24h
  accepted_shares24h          — accepted shares last 24h
  stale_shares24h             — stale shares last 24h
  stale_rate24h_pct           — stale rate percentage
  maturing_blocks             — blocks maturing (not yet paid)
  next_maturity_eta_s         — seconds until next block maturity
  workers                     — list of per-worker dicts
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app")

import httpx

from shared.base_monitor import BaseMonitor
from shared.gpu_hashrates import normalize_gpu_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("monitor.akoya")

AKOYA_API_URL = "https://akoyapool.com/api/v1/miners/{wallet}"


class AkoyaMonitor(BaseMonitor):
    def __init__(self, wallet: str, **kwargs):
        super().__init__(**kwargs)
        self.wallet = wallet
        self.url = AKOYA_API_URL.format(wallet=wallet)

    async def fetch(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self.url)
            resp.raise_for_status()
            raw = resp.json()

        d = raw["data"]

        total_hashrate_raw: float = d.get("total_hashrate", 0.0)
        total_hashrate_ths: float = total_hashrate_raw / 1e12

        total_shares = d.get("total_shares24_h", 0)
        stale_shares = d.get("stale_shares24_h", 0)
        stale_rate = round(stale_shares / total_shares * 100, 2) if total_shares > 0 else 0.0

        workers = []
        for inst in d.get("instances", []):
            raw_gpu = inst.get("gpu_card", "")
            norm_gpu = normalize_gpu_name(raw_gpu)
            hashrate_raw = inst.get("hashrate", 0.0)
            workers.append({
                "instance_id": inst.get("instance_id", ""),
                "worker_name": inst.get("worker_name", ""),
                "gpu_card": raw_gpu,
                "gpu_card_normalized": norm_gpu,
                "gpu_count": inst.get("gpu_count", 1),
                "hashrate_ths": round(hashrate_raw / 1e12, 4),
                "hashrate_formatted": inst.get("hashrate_formatted", ""),
                "is_connected": inst.get("is_connected", False),
                "connected_at": inst.get("connected_at"),
                "last_seen_at": inst.get("last_seen_at"),
                "shares1h": inst.get("shares1_h", 0),
                "stale_shares1h": inst.get("stale_shares1_h", 0),
            })

        return {
            "wallet_address": d.get("wallet_address", self.wallet),
            "is_online": d.get("is_online", False),
            "worker_count": d.get("worker_count", 0),
            "online_worker_count": d.get("online_worker_count", 0),
            "total_hashrate_ths": round(total_hashrate_ths, 4),
            "total_hashrate_formatted": d.get("total_hashrate_formatted", ""),
            "pending_balance_prl": d.get("pending_balance", 0.0),
            "total_paid_prl": d.get("total_paid", 0.0),
            "total_shares24h": total_shares,
            "accepted_shares24h": d.get("accepted_shares24_h", 0),
            "stale_shares24h": stale_shares,
            "stale_rate24h_pct": stale_rate,
            "maturing_blocks": d.get("maturing_pool_blocks_count", 0),
            "next_maturity_eta_s": d.get("next_pool_block_maturity_eta_seconds", 0),
            "workers": workers,
            "server_time": raw.get("server_time"),
        }


async def main() -> None:
    wallet = os.getenv("AKOYA_WALLET", "")
    if not wallet:
        raise RuntimeError("AKOYA_WALLET env var is required")

    monitor = AkoyaMonitor(
        wallet=wallet,
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=float(os.getenv("POLL_INTERVAL", 5)),
        redis_key="monitor:akoya",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
