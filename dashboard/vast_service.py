import os
from typing import Any

import httpx
from fastapi import HTTPException


VAST_API_BASE_URL = "https://console.vast.ai"
VAST_BUNDLES_URL = f"{VAST_API_BASE_URL}/api/v0/bundles/"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def api_key() -> str:
    return os.getenv("VAST_API_KEY", "").strip()


def template_hash_id() -> str:
    return os.getenv("VAST_TEMPLATE_HASH_ID", "").strip()


def template_hash_id_for(strategy: str) -> str:
    if strategy == "alphamine":
        return os.getenv("VAST_ALPHAMINE_TEMPLATE_HASH_ID", "").strip()
    return os.getenv("VAST_AKOYA_TEMPLATE_HASH_ID", "").strip() or template_hash_id()


def image_for_strategy(strategy: str) -> str:
    if strategy == "alphamine":
        return (
            os.getenv("VAST_ALPHAMINE_IMAGE", "").strip()
            or os.getenv("ALPHAMINE_IMAGE", "").strip()
            or "alphaminetech/pearl-miner:latest"
        )
    return (
        os.getenv("VAST_AKOYA_IMAGE", "").strip()
        or os.getenv("AKOYA_IMAGE", "").strip()
        or "registry.akoyapool.com/akoya-miner:latest"
    )


def args_for_strategy(strategy: str) -> str:
    env_name = "VAST_ALPHAMINE_ARGS" if strategy == "alphamine" else "VAST_AKOYA_ARGS"
    return os.getenv(env_name, "").strip()


def onstart_for_strategy(strategy: str) -> str:
    env_name = "VAST_ALPHAMINE_ONSTART" if strategy == "alphamine" else "VAST_AKOYA_ONSTART"
    return os.getenv(env_name, "").strip()


def akoya_wallet() -> str:
    return os.getenv("AKOYA_WALLET", "").strip()


def alphamine_wallet() -> str:
    return os.getenv("ALPHAMINE_WALLET", "").strip() or akoya_wallet()


def wallet_for_strategy(strategy: str) -> str:
    return alphamine_wallet() if strategy == "alphamine" else akoya_wallet()


def pool_strategies() -> tuple[str, ...]:
    return ("akoya", "alphamine")


def strategy_label(strategy: str) -> str:
    return "AlphaMine" if strategy == "alphamine" else "Akoya"


def strategy_worker_name(strategy: str, item_id: Any) -> str:
    return f"vast-{item_id}"


def alphamine_difficulty_for_gpu(gpu_name: Any) -> str:
    text = str(gpu_name or "").upper()
    if any(part in text for part in ("RTX 5090", "H100", "H200", "B100")):
        return "1048576"
    if "RTX 4090" in text or "RTX 5080" in text:
        return "524288"
    if any(part in text for part in ("RTX 3080", "RTX 3090", "RTX 4070", "RTX 4080", "CMP 70", "CMP 90")):
        return "262144"
    if any(part in text for part in ("RTX 3060", "RTX 3070", "A100")):
        return "131072"
    return os.getenv("ALPHAMINE_DIFFICULTY", "").strip() or "65536"


def headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise HTTPException(status_code=400, detail="VAST_API_KEY ausente no dashboard")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def strategy_configured(strategy: str) -> bool:
    return bool((template_hash_id_for(strategy) or image_for_strategy(strategy)) and wallet_for_strategy(strategy))


def offer_price_hr(offer: dict[str, Any]) -> float:
    return safe_float(
        offer.get("discounted_dph_total")
        or offer.get("dph_total")
        or offer.get("search", {}).get("discountedTotalPerHour")
        or offer.get("search", {}).get("totalHour")
    )


def sanitize_response(data: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in data.items():
        lower = str(key).lower()
        if "key" in lower or "token" in lower or "secret" in lower:
            safe[key] = "[redacted]"
        else:
            safe[key] = value
    return safe


def env_for_strategy(strategy: str, worker_name: str, gpu_name: Any) -> dict[str, str]:
    if strategy == "alphamine":
        difficulty = os.getenv("ALPHAMINE_DIFFICULTY", "").strip() or alphamine_difficulty_for_gpu(gpu_name)
        env = {
            "PEARL_ADDRESS": wallet_for_strategy(strategy),
            "PEARL_WORKER": worker_name,
            "PEARL_POOL_HOST": os.getenv("ALPHAMINE_POOL_HOST", "us2.alphapool.tech").strip() or "us2.alphapool.tech",
            "PEARL_POOL_PORT": os.getenv("ALPHAMINE_POOL_PORT", "5566").strip() or "5566",
        }
        if difficulty:
            env["PEARL_DIFFICULTY"] = difficulty
    else:
        env = {
            "AKOYA_POOL_WALLET": wallet_for_strategy(strategy),
            "AKOYA_POOL_WORKER": worker_name,
        }
    return env


def instance_payload_for_strategy(strategy: str, worker_name: str, gpu_name: Any, env: dict[str, str]) -> dict[str, Any]:
    return {
        "template_hash_id": template_hash_id_for(strategy),
        "image": image_for_strategy(strategy),
        "runtype": "args",
        "disk": float(os.getenv("VAST_INSTANCE_DISK_GB") or "8"),
        "label": f"{strategy_label(strategy).upper()} {worker_name} {gpu_name or ''}".strip(),
        "env": env,
    }


def update_payload_for_strategy(instance_id: int, strategy: str, worker_name: str, gpu_name: Any, env: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": instance_id,
        "template_hash_id": template_hash_id_for(strategy),
        "image": image_for_strategy(strategy),
        "env": env,
        "label": f"{strategy_label(strategy).upper()} {worker_name} {gpu_name or ''}".strip(),
    }
    args = args_for_strategy(strategy)
    onstart = onstart_for_strategy(strategy)
    if args:
        payload["args"] = args
    if onstart:
        payload["onstart"] = onstart
    return payload


async def accept_ask(ask_id: int, opportunity: dict[str, Any], price_hr: float, strategy: str) -> dict[str, Any]:
    worker_name = strategy_worker_name(strategy, ask_id)
    env = env_for_strategy(strategy, worker_name, opportunity.get("gpu"))
    payload = instance_payload_for_strategy(strategy, worker_name, opportunity.get("gpu"), env)
    async with httpx.AsyncClient(timeout=30) as client:
        url = f"{VAST_API_BASE_URL}/api/v0/asks/{ask_id}/"
        response = await client.put(url, json=payload, headers=headers())
        if response.status_code in {404, 405}:
            response = await client.post(url, json=payload, headers=headers())
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code >= 400 or data.get("success") is False:
            detail = data.get("msg") or data.get("error") or response.text
            raise HTTPException(status_code=409, detail=detail)
    return {
        "success": bool(data.get("success", True)),
        "instance_id": data.get("new_contract") or data.get("contract_id") or data.get("id"),
        "worker_name": worker_name,
        "pool_strategy": strategy,
        "price_usd_hr": round_money(price_hr),
        "raw": sanitize_response(data),
    }


async def destroy_instance(instance_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(
            f"{VAST_API_BASE_URL}/api/v0/instances/{instance_id}/",
            headers=headers(),
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code == 404:
            return {"status": "not_found", "raw": sanitize_response(data) if isinstance(data, dict) else {}}
        if response.status_code >= 400:
            detail = data.get("msg") or data.get("error") or response.text if isinstance(data, dict) else response.text
            raise HTTPException(status_code=409, detail=detail)
    return {"status": "destroyed", "raw": sanitize_response(data) if isinstance(data, dict) else {}}


async def update_instance_pool_config(instance_id: int, strategy: str, worker_name: str, gpu_name: Any) -> dict[str, Any]:
    env = env_for_strategy(strategy, worker_name, gpu_name)
    payload = update_payload_for_strategy(instance_id, strategy, worker_name, gpu_name, env)
    if not payload.get("image"):
        raise HTTPException(status_code=409, detail=f"Imagem Vast ausente para {strategy_label(strategy)}")
    async with httpx.AsyncClient(timeout=30) as client:
        url = f"{VAST_API_BASE_URL}/api/v0/instances/update_template/{instance_id}/"
        response = await client.put(url, json=payload, headers=headers())
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code >= 400 or data.get("success", True) is False:
            detail = data.get("msg") or data.get("error") or response.text if isinstance(data, dict) else response.text
            raise HTTPException(status_code=409, detail=f"Falha ao atualizar template Vast: {detail}")
    return {
        "status": "updated",
        "endpoint": url,
        "target_pool": strategy,
        "template_hash_id": payload.get("template_hash_id"),
        "raw": sanitize_response(data) if isinstance(data, dict) else {},
    }


async def recycle_instance(instance_id: int) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.put(
            f"{VAST_API_BASE_URL}/api/v0/instances/recycle/{instance_id}/",
            headers=headers(),
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code >= 400 or data.get("success") is False:
            detail = data.get("msg") or data.get("error") or response.text if isinstance(data, dict) else response.text
            raise HTTPException(status_code=409, detail=detail)
    return {"status": "recycling", "raw": sanitize_response(data) if isinstance(data, dict) else {}}
