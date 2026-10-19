"""
Monitor RunPod GPU pricing and live Pods.

Publishes to Redis key: monitor:runpod

This monitor is read-only. It does not create or destroy Pods.
"""
import asyncio
import logging
import os
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
logger = logging.getLogger("monitor.runpod")

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
RUNPOD_REST_BASE_URL = "https://rest.runpod.io/v1"

GPU_TYPE_IDS = [
    "NVIDIA GeForce RTX 3060 Ti",
    "NVIDIA GeForce RTX 3070",
    "NVIDIA GeForce RTX 3080",
    "NVIDIA GeForce RTX 3080 Ti",
    "NVIDIA GeForce RTX 3090",
    "NVIDIA GeForce RTX 3090 Ti",
    "NVIDIA GeForce RTX 4070 Ti",
    "NVIDIA GeForce RTX 4080",
    "NVIDIA GeForce RTX 4090",
    "NVIDIA GeForce RTX 5080",
    "NVIDIA GeForce RTX 5090",
    "NVIDIA RTX A4000",
    "NVIDIA RTX A4500",
    "NVIDIA RTX A5000",
    "NVIDIA RTX A6000",
    "NVIDIA A40",
    "NVIDIA A100 80GB PCIe",
    "NVIDIA A100-SXM4-80GB",
    "NVIDIA H100 PCIe",
    "NVIDIA H100 80GB HBM3",
    "NVIDIA H100 NVL",
    "NVIDIA H200",
    "NVIDIA H200 NVL",
    "NVIDIA L4",
    "NVIDIA L40",
    "NVIDIA L40S",
]


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
    return os.getenv("RUNPOD_API_KEY", "").strip()


def _graphql_payload(gpu_id: str) -> dict[str, Any]:
    return {
        "operationName": "GpuTypePricing",
        "query": """
query GpuTypePricing($gpuTypesInput: GpuTypeFilter, $lowestPriceInput: GpuLowestPriceInput) {
  gpuTypes(input: $gpuTypesInput) {
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    securePrice
    communityPrice
    secureSpotPrice
    lowestPrice(input: $lowestPriceInput) {
      minimumBidPrice
      uninterruptablePrice
      stockStatus
      maxUnreservedGpuCount
      availableGpuCounts
      gpuTypeDatacenters {
        dataCenterId
        availability
        supportNetworkVolumes
      }
    }
  }
}
""",
        "variables": {
            "gpuTypesInput": {"id": gpu_id},
            "lowestPriceInput": {"gpuCount": 1},
        },
    }


def _normalized_offer(gpu_type: dict[str, Any]) -> dict[str, Any] | None:
    gpu_id = str(gpu_type.get("id") or "")
    norm = normalize_gpu_name(gpu_id or gpu_type.get("displayName"))
    gpu_data = get_gpu(norm or gpu_id)
    if norm is None or gpu_data is None or not gpu_data.get("supported", False):
        return None

    lowest = gpu_type.get("lowestPrice") or {}
    on_demand_price = _float(lowest.get("uninterruptablePrice"))
    spot_price = _float(lowest.get("minimumBidPrice") or gpu_type.get("secureSpotPrice"))
    available_counts = lowest.get("availableGpuCounts") or []
    datacenters = lowest.get("gpuTypeDatacenters") or []
    available_datacenters = [
        dc
        for dc in datacenters
        if str(dc.get("availability") or "").upper() == "AVAILABLE"
    ]

    return {
        "provider": "runpod",
        "offer_id": gpu_id,
        "gpu_type_id": gpu_id,
        "gpu_model_raw": gpu_id,
        "gpu_model_normalized": norm,
        "display_name": gpu_type.get("displayName") or norm,
        "gpu_count": 1,
        "gpu_vram_gb": _int(gpu_type.get("memoryInGb")),
        "price_usd_hr": round(on_demand_price, 4),
        "price_usd_day": round(on_demand_price * 24, 4),
        "spot_price_usd_hr": round(spot_price, 4),
        "secure_price_usd_hr": round(_float(gpu_type.get("securePrice")), 4),
        "community_price_usd_hr": round(_float(gpu_type.get("communityPrice")), 4),
        "stock_status": lowest.get("stockStatus") or "Unknown",
        "max_unreserved_gpu_count": _int(lowest.get("maxUnreservedGpuCount")),
        "available_gpu_counts": available_counts,
        "datacenters": datacenters,
        "available_datacenter_count": len(available_datacenters),
        "available": bool(on_demand_price > 0 and (available_counts or available_datacenters)),
        "supported": True,
        "low_value": bool(gpu_data.get("low_value", False)),
        "expected_ths": _float(gpu_data.get("ths")),
        "recommended_pool": gpu_data.get("kernel") or "akoya",
        "difficulty": gpu_data.get("difficulty"),
    }


def _normalized_pod(pod: dict[str, Any]) -> dict[str, Any]:
    gpu = pod.get("gpu") or {}
    machine = pod.get("machine") or {}
    gpu_id = gpu.get("id") or machine.get("gpuTypeId") or machine.get("gpuDisplayName") or ""
    norm = normalize_gpu_name(gpu_id)
    return {
        "provider": "runpod",
        "pod_id": pod.get("id"),
        "instance_id": pod.get("id"),
        "name": pod.get("name") or "",
        "status": pod.get("desiredStatus") or "",
        "gpu_model_raw": gpu_id,
        "gpu_model_normalized": norm,
        "gpu_count": _int(gpu.get("count"), 1),
        "price_usd_hr": _float(pod.get("adjustedCostPerHr") or pod.get("costPerHr")),
        "machine_id": pod.get("machineId") or "",
        "host_id": machine.get("podHostId") or "",
        "data_center_id": machine.get("dataCenterId") or "",
        "public_ip": pod.get("publicIp") or "",
        "port_mappings": pod.get("portMappings") or {},
        "image": pod.get("image") or "",
        "last_started_at": pod.get("lastStartedAt") or "",
        "interruptible": bool(pod.get("interruptible", False)),
    }


class RunPodMonitor(BaseMonitor):
    async def fetch(self) -> dict:
        api_key = _api_key()
        if not api_key:
            return {
                "configured": False,
                "error": "RUNPOD_API_KEY env var is not set",
                "offers": [],
                "pods": [],
                "available_supported_count": 0,
            }

        offers: list[dict[str, Any]] = []
        pods: list[dict[str, Any]] = []
        errors: list[str] = []

        async with httpx.AsyncClient(timeout=25) as client:
            for gpu_id in GPU_TYPE_IDS:
                try:
                    resp = await client.post(
                        RUNPOD_GRAPHQL_URL,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=_graphql_payload(gpu_id),
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    if body.get("errors"):
                        errors.append(f"{gpu_id}: {body['errors']}")
                        continue
                    for gpu_type in body.get("data", {}).get("gpuTypes", []) or []:
                        offer = _normalized_offer(gpu_type)
                        if offer:
                            offers.append(offer)
                except Exception as exc:
                    errors.append(f"{gpu_id}: {exc!r}")

            try:
                resp = await client.get(
                    f"{RUNPOD_REST_BASE_URL}/pods",
                    params={"includeMachine": "true"},
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                raw_pods = resp.json()
                if isinstance(raw_pods, list):
                    pods = [_normalized_pod(p) for p in raw_pods]
            except Exception as exc:
                errors.append(f"pods: {exc!r}")

        available_supported_count = sum(1 for offer in offers if offer.get("available"))
        logger.info(
            "RunPod: %s supported offers, %s available, %s pods",
            len(offers),
            available_supported_count,
            len(pods),
        )

        return {
            "configured": True,
            "provider": "runpod",
            "supported_count": len(offers),
            "available_supported_count": available_supported_count,
            "active_pods_count": sum(1 for pod in pods if pod.get("status") == "RUNNING"),
            "offers": offers,
            "pods": pods,
            "errors": errors[:20],
        }


async def main() -> None:
    poll_interval = max(30.0, float(os.getenv("POLL_INTERVAL", 30)))
    monitor = RunPodMonitor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=poll_interval,
        redis_key="monitor:runpod",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
