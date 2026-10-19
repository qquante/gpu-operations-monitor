"""
Monitor Vast.ai Marketplace — console.vast.ai/api/v0/bundles/
Publishes to Redis key: monitor:vastai
Interval: configurable via POLL_INTERVAL env var

Pearl mining filters:
  CUDA >= 12.9
  PCIe lanes >= x8, or pcie_bw >= 8.0 when lane count is missing
  On-demand availability: rentable=true, rented=false, is_bid=false
"""
import asyncio
import logging
import os
import sys
from collections import Counter

sys.path.insert(0, "/app")

import httpx

from shared.base_monitor import BaseMonitor
from shared.gpu_hashrates import get_gpu, normalize_gpu_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("monitor.vastai")

VASTAI_SEARCH_URL = "https://console.vast.ai/api/v0/bundles/"
MIN_CUDA = 12.9
MIN_PCIE_LANES = 8
MIN_PCIE_BW_FALLBACK = 8.0
SEARCH_LIMIT = 1000
SEARCH_BODY = {
    "limit": SEARCH_LIMIT,
    "type": "ondemand",
    "gpu_arch": {"eq": "nvidia"},
    "rentable": {"eq": True},
    "rented": {"eq": False},
    "cuda_max_good": {"gte": MIN_CUDA},
    "pcie_bw": {"gte": MIN_PCIE_BW_FALLBACK},
}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _meets_pcie_rule(offer: dict) -> bool:
    lanes = offer.get("gpu_lanes")
    if lanes is not None:
        return _float(lanes) >= MIN_PCIE_LANES
    return _float(offer.get("pcie_bw")) >= MIN_PCIE_BW_FALLBACK


class VastAiMonitor(BaseMonitor):
    async def fetch(self) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(VASTAI_SEARCH_URL, json=SEARCH_BODY)
            resp.raise_for_status()
            raw = resp.json()

        offers: list = raw.get("offers", [])
        total_offers = len(offers)
        available_count = 0
        available_supported_count = 0
        supported_offers = []
        usable_supported_count = 0
        unsupported_gpu_counts: Counter[str] = Counter()

        for offer in offers:
            rentable = bool(offer.get("rentable", False))
            rented = bool(offer.get("rented", False))
            is_bid = bool(offer.get("is_bid", False))
            on_demand_available = rentable and not rented and not is_bid
            if on_demand_available:
                available_count += 1

            gpu_raw = offer.get("gpu_name") or ""
            norm = normalize_gpu_name(gpu_raw)
            gpu_data = get_gpu(gpu_raw)

            if norm is None or gpu_data is None or not gpu_data.get("supported", False):
                unsupported_gpu_counts[str(gpu_raw or "unknown")] += 1
                continue

            if on_demand_available:
                available_supported_count += 1

            cuda_max_good = _float(offer.get("cuda_max_good"))
            meets_cuda = cuda_max_good >= MIN_CUDA
            meets_pcie = _meets_pcie_rule(offer)
            meets_guidelines = on_demand_available and meets_cuda and meets_pcie
            if meets_guidelines:
                usable_supported_count += 1

            price_usd_hr = _float(
                offer.get("discounted_dph_total")
                or offer.get("dph_total")
                or offer.get("search", {}).get("discountedTotalPerHour")
                or offer.get("search", {}).get("totalHour")
            )

            supported_offers.append({
                "offer_id": offer.get("id") or offer.get("ask_contract_id"),
                "bundle_id": offer.get("bundle_id"),
                "host_id": offer.get("host_id"),
                "machine_id": offer.get("machine_id"),
                "gpu_model_raw": gpu_raw,
                "gpu_model_normalized": norm,
                "gpu_count": _int(offer.get("num_gpus"), 1),
                "gpu_vram_gb": round(_float(offer.get("gpu_ram")) / 1024, 1),
                "price_usd_hr": round(price_usd_hr, 4),
                "price_usd_day": round(price_usd_hr * 24, 4),
                "rentable": rentable,
                "rented": rented,
                "is_bid": is_bid,
                "on_demand_available": on_demand_available,
                "meets_guidelines": meets_guidelines,
                "meets_cuda": meets_cuda,
                "meets_pcie": meets_pcie,
                "cuda_max_good": cuda_max_good,
                "pcie_lanes": _float(offer.get("gpu_lanes")),
                "pcie_bw_gbps": round(_float(offer.get("pcie_bw")), 2),
                "country": offer.get("geolocation") or "",
                "net_up_mbps": round(_float(offer.get("inet_up")), 1),
                "net_down_mbps": round(_float(offer.get("inet_down")), 1),
                "disk_space_gb": round(_float(offer.get("disk_space")), 1),
                "disk_bw_mbps": round(_float(offer.get("disk_bw")), 1),
                "cpu": offer.get("cpu_name") or "",
                "cpu_cores": _float(offer.get("cpu_cores_effective") or offer.get("cpu_cores")),
                "ram_gb": round(_float(offer.get("cpu_ram")) / 1024, 1),
                "reliability": round(_float(offer.get("reliability")), 4),
                "verification": offer.get("verification") or "",
                "low_value": gpu_data.get("low_value", False),
            })

        supported_count = len(supported_offers)
        logger.info(
            f"Vast.ai: {total_offers} offers, {available_count} available, "
            f"{supported_count} supported, {available_supported_count} available+supported, "
            f"{usable_supported_count} usable"
        )

        return {
            "total_offers": total_offers,
            "available_count": available_count,
            "supported_count": supported_count,
            "available_supported_count": available_supported_count,
            "usable_supported_count": usable_supported_count,
            "filters": {
                "min_cuda": MIN_CUDA,
                "min_pcie_lanes": MIN_PCIE_LANES,
                "min_pcie_bw_fallback": MIN_PCIE_BW_FALLBACK,
                "requires_on_demand": True,
                "search_limit": SEARCH_LIMIT,
            },
            "unsupported_gpu_counts": dict(unsupported_gpu_counts.most_common()),
            "offers": supported_offers,
        }


async def main() -> None:
    monitor = VastAiMonitor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=float(os.getenv("POLL_INTERVAL", 5)),
        redis_key="monitor:vastai",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
