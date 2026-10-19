"""
Monitor Pearl Network — lordofpearls.xyz/api/public
Publishes to Redis key: monitor:pearl
Interval: 5 seconds (configurable via POLL_INTERVAL env var)

Data published:
  network_hashrate_ths     — rede em TH/s
  network_hashrate_ehs     — rede em EH/s
  avg_block_time_s         — tempo médio de bloco
  blocks_per_day           — blocos por dia estimado
  reward_per_block         — recompensa do último bloco (PRL)
  prl_price_usd            — preço PRL em USD
  difficulty               — dificuldade atual
  best_block_height        — altura do melhor bloco
  mempool_size             — tamanho do mempool
  peer_count               — peers conectados
  supply / supply_pct      — supply circulante
  usd_per_th_per_day       — dict por pool: receita USD por TH/s por dia
  usd_per_th_per_hour      — dict por pool: receita USD por TH/s por hora
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app")

import httpx

from shared.base_monitor import BaseMonitor
from shared.gpu_hashrates import POOL_FEES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("monitor.pearl")

PEARL_API_URL = "https://lordofpearls.xyz/api/public"


class PearlMonitor(BaseMonitor):
    async def fetch(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(PEARL_API_URL)
            resp.raise_for_status()
            raw = resp.json()

        network = raw["network"]
        price_data = raw.get("price", {})
        chain = raw.get("chain", {})

        # ── Core values ────────────────────────────────────────────────────────
        network_hashps: float = network["networkhashps"]
        network_hash_ths: float = network_hashps / 1e12

        avg_block_time_s: float = network["avg_block_time_s"]
        blocks_per_day: float = 86400 / avg_block_time_s if avg_block_time_s > 0 else 0

        prl_price_usd: float = price_data.get("usd", 0.0)
        price_source: str = price_data.get("source", "")

        # Reward from the most recent confirmed block
        recent_blocks: list = raw.get("leaderboard", {}).get("recent_blocks", [])
        reward_per_block: float = recent_blocks[0]["reward"] if recent_blocks else 2686.0

        # ── $/TH/day per pool (formula from guide) ─────────────────────────────
        # $/TH/day = (blocks_per_day × reward × (1 - fee) × prl_price) / network_TH/s
        usd_per_th_per_day: dict[str, float] = {}
        usd_per_th_per_hour: dict[str, float] = {}

        for pool, fee in POOL_FEES.items():
            if network_hash_ths > 0 and prl_price_usd > 0:
                rate = (
                    blocks_per_day
                    * reward_per_block
                    * (1 - fee)
                    * prl_price_usd
                    / network_hash_ths
                )
            else:
                rate = 0.0
            usd_per_th_per_day[pool] = round(rate, 6)
            usd_per_th_per_hour[pool] = round(rate / 24, 8)

        leaderboard = raw.get("leaderboard", {})

        return {
            "network_hashrate_ths": round(network_hash_ths, 2),
            "network_hashrate_ehs": round(network_hash_ths / 1e6, 4),
            "avg_block_time_s": round(avg_block_time_s, 2),
            "blocks_per_day": round(blocks_per_day, 1),
            "reward_per_block": reward_per_block,
            "prl_price_usd": prl_price_usd,
            "price_source": price_source,
            "difficulty": network["difficulty"],
            "best_block_height": network["blocks"],
            "mempool_size": network.get("mempool_size", 0),
            "peer_count": chain.get("peers", 0),
            "supply": network.get("supply", 0),
            "supply_pct": network.get("supply_pct", 0),
            "supply_max": network.get("supply_max", 2_100_000_000),
            "usd_per_th_per_day": usd_per_th_per_day,
            "usd_per_th_per_hour": usd_per_th_per_hour,
            "leaderboard_24h_total_blocks": leaderboard.get("total_blocks", 0),
            "leaderboard_24h_unique_miners": leaderboard.get("unique_miners", 0),
        }


async def main() -> None:
    monitor = PearlMonitor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=float(os.getenv("POLL_INTERVAL", 5)),
        redis_key="monitor:pearl",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
