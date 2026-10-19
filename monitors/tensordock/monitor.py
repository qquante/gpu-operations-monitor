"""
Monitor TensorDock locations, hostnodes, and instances.

Publishes to Redis key: monitor:tensordock

This monitor is read-only. It does not create or delete instances.
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
from shared.gpu_hashrates import get_gpu, normalize_gpu_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("monitor.tensordock")

TENSORDOCK_API_BASE_URL = "https://dashboard.tensordock.com/api/v2"


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


def _api_key() -> str:
    return os.getenv("TENSORDOCK_API_KEY", "").strip()


def _normalize_v0_name(v0_name: str, display_name: str = "") -> str | None:
    raw = display_name or v0_name
    direct = normalize_gpu_name(raw)
    if direct:
        return direct

    compact = re.sub(r"[^a-z0-9]+", "", v0_name.lower())
    rules = [
        ("geforcertx3060ti", "RTX 3060 Ti"),
        ("geforcertx3070ti", "RTX 3070 Ti"),
        ("geforcertx3070", "RTX 3070"),
        ("geforcertx3080ti", "RTX 3080 Ti"),
        ("geforcertx3080", "RTX 3080"),
        ("geforcertx3090ti", "RTX 3090 Ti"),
        ("geforcertx3090", "RTX 3090"),
        ("geforcertx4070ti", "RTX 4070 Ti"),
        ("geforcertx4080", "RTX 4080"),
        ("geforcertx4090", "RTX 4090"),
        ("geforcertx5080", "RTX 5080"),
        ("geforcertx5090", "RTX 5090"),
        ("rtxa4000", "RTX A4000"),
        ("rtxa5000", "RTX A5000"),
        ("rtxa6000", "RTX A6000"),
        ("a100sxm", "A100 SXM"),
        ("a100pcie", "A100 PCIe"),
        ("h100pcie", "H100 PCIe"),
        ("h100sxm", "H100 SXM"),
        ("h100", "H100 SXM"),
        ("h200", "H200"),
    ]
    for needle, normalized in rules:
        if needle in compact:
            return normalized
    return None


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _normalize_location_offer(location: dict[str, Any], gpu: dict[str, Any]) -> dict[str, Any] | None:
    v0_name = str(gpu.get("v0Name") or "")
    display_name = str(gpu.get("displayName") or "")
    norm = _normalize_v0_name(v0_name, display_name)
    gpu_data = get_gpu(norm or display_name or v0_name)
    if norm is None or gpu_data is None or not gpu_data.get("supported", False):
        return None

    price_usd_hr = _float(gpu.get("price_per_hr"))
    return {
        "provider": "tensordock",
        "offer_id": f"{location.get('id')}:{v0_name}",
        "location_id": location.get("id"),
        "hostnode_id": None,
        "gpu_v0_name": v0_name,
        "gpu_model_raw": display_name or v0_name,
        "gpu_model_normalized": norm,
        "gpu_count": _int(gpu.get("max_count"), 1),
        "max_count": _int(gpu.get("max_count"), 1),
        "gpu_vram_gb": 0,
        "price_usd_hr": round(price_usd_hr, 4),
        "price_usd_day": round(price_usd_hr * 24, 4),
        "city": location.get("city") or "",
        "state": location.get("stateprovince") or "",
        "country": location.get("country") or "",
        "tier": location.get("tier"),
        "resources": gpu.get("resources") or {},
        "pricing": gpu.get("pricing") or {},
        "network_features": gpu.get("network_features") or {},
        "available": price_usd_hr > 0 and _int(gpu.get("max_count")) > 0,
        "supported": True,
        "low_value": bool(gpu_data.get("low_value", False)),
        "expected_ths": _float(gpu_data.get("ths")),
        "recommended_pool": gpu_data.get("kernel") or "akoya",
        "difficulty": gpu_data.get("difficulty"),
    }


def _normalize_hostnode_offer(hostnode: dict[str, Any], gpu: dict[str, Any]) -> dict[str, Any] | None:
    v0_name = str(gpu.get("v0Name") or "")
    norm = _normalize_v0_name(v0_name)
    gpu_data = get_gpu(norm or v0_name)
    if norm is None or gpu_data is None or not gpu_data.get("supported", False):
        return None

    location = hostnode.get("location") or {}
    available_count = _int(gpu.get("availableCount"))
    price_usd_hr = _float(gpu.get("price_per_hr"))
    return {
        "provider": "tensordock",
        "offer_id": f"{hostnode.get('id')}:{v0_name}",
        "hostnode_id": hostnode.get("id"),
        "location_id": hostnode.get("location_id"),
        "gpu_v0_name": v0_name,
        "gpu_model_raw": v0_name,
        "gpu_model_normalized": norm,
        "gpu_count": available_count,
        "available_count": available_count,
        "gpu_vram_gb": 0,
        "price_usd_hr": round(price_usd_hr, 4),
        "price_usd_day": round(price_usd_hr * 24, 4),
        "engine": hostnode.get("engine") or "",
        "uptime_percentage": _float(hostnode.get("uptime_percentage")),
        "city": location.get("city") or "",
        "state": location.get("stateprovince") or "",
        "country": location.get("country") or "",
        "tier": location.get("tier"),
        "network_speed_gbps": _float(location.get("network_speed_gbps")),
        "network_speed_upload_gbps": _float(location.get("network_speed_upload_gbps")),
        "has_public_ip_available": bool((hostnode.get("available_resources") or {}).get("has_public_ip_available")),
        "resources": hostnode.get("available_resources") or {},
        "pricing": hostnode.get("pricing") or {},
        "available": price_usd_hr > 0 and available_count > 0,
        "supported": True,
        "low_value": bool(gpu_data.get("low_value", False)),
        "expected_ths": _float(gpu_data.get("ths")),
        "recommended_pool": gpu_data.get("kernel") or "akoya",
        "difficulty": gpu_data.get("difficulty"),
    }


def _normalize_instance(instance: dict[str, Any]) -> dict[str, Any]:
    attrs = instance.get("attributes") if isinstance(instance.get("attributes"), dict) else instance
    resources = attrs.get("resources") or {}
    gpus = resources.get("gpus") or {}
    first_gpu_key = next(iter(gpus), "")
    first_gpu = gpus.get(first_gpu_key) if isinstance(gpus.get(first_gpu_key), dict) else {}
    norm = _normalize_v0_name(first_gpu.get("v0Name") or first_gpu_key, first_gpu_key)
    return {
        "provider": "tensordock",
        "instance_id": instance.get("id") or attrs.get("id"),
        "name": attrs.get("name") or instance.get("name") or "",
        "status": attrs.get("status") or instance.get("status") or "",
        "ip_address": attrs.get("ipAddress") or instance.get("ipAddress") or "",
        "gpu_model_raw": first_gpu.get("v0Name") or first_gpu_key,
        "gpu_model_normalized": norm,
        "gpu_count": _int(first_gpu.get("count"), 1),
        "price_usd_hr": _float(attrs.get("rateHourly") or instance.get("rateHourly")),
        "resources": resources,
    }


class TensorDockMonitor(BaseMonitor):
    async def _fetch_locations(self, client: httpx.AsyncClient, errors: list[str]) -> list[dict[str, Any]]:
        try:
            resp = await client.get(f"{TENSORDOCK_API_BASE_URL}/locations")
            resp.raise_for_status()
            return resp.json().get("data", {}).get("locations", []) or []
        except Exception as exc:
            errors.append(f"locations: {exc!r}")

        try:
            async with httpx.AsyncClient(timeout=60, headers={"Accept": "application/json"}) as public_client:
                resp = await public_client.get(f"{TENSORDOCK_API_BASE_URL}/locations")
                resp.raise_for_status()
                return resp.json().get("data", {}).get("locations", []) or []
        except Exception as exc:
            errors.append(f"locations_public_fallback: {exc!r}")
            return []

    async def fetch(self) -> dict:
        api_key = _api_key()
        if not api_key:
            return {
                "configured": False,
                "error": "TENSORDOCK_API_KEY env var is not set",
                "offers": [],
                "hostnode_offers": [],
                "instances": [],
                "available_supported_count": 0,
            }

        offers: list[dict[str, Any]] = []
        hostnode_offers: list[dict[str, Any]] = []
        instances: list[dict[str, Any]] = []
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=60, headers=_auth_headers(api_key)) as client:
            locations = await self._fetch_locations(client, errors)
            for location in locations:
                for gpu in location.get("gpus", []) or []:
                    offer = _normalize_location_offer(location, gpu)
                    if offer:
                        offers.append(offer)

            try:
                resp = await client.get(f"{TENSORDOCK_API_BASE_URL}/hostnodes")
                resp.raise_for_status()
                hostnodes = resp.json().get("data", {}).get("hostnodes", []) or []
                for hostnode in hostnodes:
                    available = hostnode.get("available_resources") or {}
                    for gpu in available.get("gpus", []) or []:
                        offer = _normalize_hostnode_offer(hostnode, gpu)
                        if offer:
                            hostnode_offers.append(offer)
            except Exception as exc:
                errors.append(f"hostnodes: {exc!r}")

            try:
                resp = await client.get(f"{TENSORDOCK_API_BASE_URL}/instances")
                resp.raise_for_status()
                raw_instances = resp.json().get("data", {}).get("instances", []) or []
                instances = [_normalize_instance(item) for item in raw_instances]
            except Exception as exc:
                errors.append(f"instances: {exc!r}")

        available_source = hostnode_offers or offers
        available_supported_count = sum(1 for offer in available_source if offer.get("available"))
        logger.info(
            "TensorDock: %s location offers, %s hostnode offers, %s available, %s instances",
            len(offers),
            len(hostnode_offers),
            available_supported_count,
            len(instances),
        )

        return {
            "configured": True,
            "provider": "tensordock",
            "supported_count": len(hostnode_offers) or len(offers),
            "available_supported_count": available_supported_count,
            "location_offers_count": len(offers),
            "hostnode_offers_count": len(hostnode_offers),
            "active_instances_count": sum(1 for inst in instances if str(inst.get("status")).lower() == "running"),
            "offers": offers,
            "hostnode_offers": hostnode_offers,
            "instances": instances,
            "errors": errors[:20],
        }


async def main() -> None:
    poll_interval = max(30.0, float(os.getenv("POLL_INTERVAL", 30)))
    monitor = TensorDockMonitor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=poll_interval,
        redis_key="monitor:tensordock",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
