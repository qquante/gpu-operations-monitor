import asyncio
import os
import time
from typing import Any

import httpx
from fastapi import HTTPException


CLORE_API_BASE_URL = "https://api.clore.ai/v1"
CLORE_MAX_RETRIES = max(1, int(os.getenv("CLORE_MAX_RETRIES", "6")))
CLORE_RATE_LIMIT_BACKOFF_SECONDS = max(1.0, float(os.getenv("CLORE_RATE_LIMIT_BACKOFF_SECONDS") or "2.0"))

_last_request_at = 0.0
_last_create_at = 0.0
_rate_lock = asyncio.Lock()


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
    return os.getenv("CLORE_API_KEY", "").strip()


def currency_order() -> list[str]:
    raw = os.getenv("CLORE_CURRENCY_ORDER", "CLORE-Blockchain,USD-Blockchain,bitcoin")
    return [item.strip() for item in raw.split(",") if item.strip()]


def currency_rejection_reasons(server: dict[str, Any], wallet_payload: dict[str, Any] | None = None) -> list[str]:
    price = server.get("price") or {}
    on_demand = price.get("on_demand") or {}
    accepted = set(server.get("allowed_coins") or server.get("allowed_currencies") or []) or set(on_demand.keys())
    balances = {}
    if wallet_payload:
        for wallet in wallet_payload.get("wallets", []) or []:
            balances[str(wallet.get("name") or "")] = safe_float(wallet.get("balance"))
    reasons = []
    for currency in currency_order():
        if accepted and currency not in accepted:
            reasons.append(f"{currency}: nao aceita pela oferta")
            continue
        native_price = safe_float(on_demand.get(currency))
        if native_price <= 0:
            reasons.append(f"{currency}: preco ausente")
            continue
        if balances and balances.get(currency, 0.0) < native_price:
            reasons.append(f"{currency}: saldo {balances.get(currency, 0.0):.8g} < preco {native_price:.8g}/dia")
            continue
        reasons.append(f"{currency}: ok")
    return reasons


def image_for_strategy(strategy: str) -> str:
    if strategy == "alphamine":
        return (
            os.getenv("CLORE_ALPHAMINE_IMAGE", "").strip()
            or os.getenv("ALPHAMINE_IMAGE", "").strip()
            or "alphaminetech/pearl-miner:latest"
        )
    return (
        os.getenv("CLORE_AKOYA_IMAGE", "").strip()
        or os.getenv("AKOYA_IMAGE", "").strip()
        or "registry.akoyapool.com/akoya-miner:latest"
    )


def akoya_wallet() -> str:
    return os.getenv("AKOYA_WALLET", "").strip()


def alphamine_wallet() -> str:
    return os.getenv("ALPHAMINE_WALLET", "").strip() or akoya_wallet()


def wallet_for_strategy(strategy: str) -> str:
    return alphamine_wallet() if strategy == "alphamine" else akoya_wallet()


def strategy_worker_name(strategy: str, server_id: Any) -> str:
    return f"clore-{server_id}"


def strategy_label(strategy: str) -> str:
    return "AlphaMine" if strategy == "alphamine" else "Akoya"


def pool_strategies() -> tuple[str, ...]:
    return ("akoya", "alphamine")


def headers() -> dict[str, str]:
    key = api_key()
    if not key:
        raise HTTPException(status_code=400, detail="CLORE_API_KEY ausente no dashboard")
    return {"auth": key, "Content-Type": "application/json"}


def sanitize_response(data: Any) -> Any:
    if isinstance(data, dict):
        safe = {}
        for key, value in data.items():
            lower = str(key).lower()
            if "key" in lower or "token" in lower or "secret" in lower or "password" in lower:
                safe[key] = "[redacted]"
            else:
                safe[key] = sanitize_response(value)
        return safe
    if isinstance(data, list):
        return [sanitize_response(item) for item in data]
    return data


async def _throttle(create: bool = False) -> None:
    global _last_request_at, _last_create_at
    async with _rate_lock:
        now = time.time()
        wait = max(0.0, 1.05 - (now - _last_request_at))
        if create:
            wait = max(wait, 5.1 - (now - _last_create_at))
        if wait > 0:
            await asyncio.sleep(wait)
        now = time.time()
        _last_request_at = now
        if create:
            _last_create_at = now


async def request(method: str, path: str, *, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None, create: bool = False) -> dict[str, Any]:
    last_detail = ""
    for attempt in range(CLORE_MAX_RETRIES):
        await _throttle(create=create)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                f"{CLORE_API_BASE_URL}{path}",
                headers=headers(),
                json=json_body,
                params=params,
            )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        code = data.get("code") if isinstance(data, dict) else None
        if response.status_code == 429 or code == 5:
            last_detail = (data.get("error") or response.text or "code=5 rate limit") if isinstance(data, dict) else response.text
            retry_after = safe_float(response.headers.get("retry-after"), 0.0)
            await asyncio.sleep(max(retry_after, CLORE_RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1)))
            continue
        if response.status_code >= 400:
            detail = data.get("error") or response.text if isinstance(data, dict) else response.text
            raise HTTPException(status_code=409, detail=f"Clore API HTTP {response.status_code}: {detail}")
        if code not in {None, 0}:
            detail = data.get("error") or data.get("message") or f"codigo {code}"
            raise HTTPException(status_code=409, detail=f"Clore API: {detail}")
        return data if isinstance(data, dict) else {}
    raise HTTPException(status_code=429, detail=f"Clore API rate limit persistente: {last_detail or 'code=5'}")


async def marketplace() -> dict[str, Any]:
    return await request("GET", "/marketplace")


async def spot_marketplace(server_id: int) -> dict[str, Any]:
    return await request("GET", "/spot_marketplace", params={"market": server_id})


async def my_orders(return_completed: bool = False) -> dict[str, Any]:
    return await request("GET", "/my_orders", params={"return_completed": str(return_completed).lower()})


async def wallets() -> dict[str, Any]:
    return await request("GET", "/wallets")


async def renter_fees() -> dict[str, Any]:
    return await request("GET", "/renter_fees")


def env_for_strategy(strategy: str, worker_name: str, gpu_name: Any) -> dict[str, str]:
    if strategy == "alphamine":
        env = {
            "PEARL_ADDRESS": wallet_for_strategy(strategy),
            "PEARL_WORKER": worker_name,
            "PEARL_POOL_HOST": os.getenv("ALPHAMINE_POOL_HOST", "us2.alphapool.tech").strip() or "us2.alphapool.tech",
            "PEARL_POOL_PORT": os.getenv("ALPHAMINE_POOL_PORT", "5566").strip() or "5566",
        }
        difficulty = os.getenv("ALPHAMINE_DIFFICULTY", "").strip()
        if difficulty:
            env["PEARL_DIFFICULTY"] = difficulty
        return env
    return {
        "AKOYA_POOL_WALLET": wallet_for_strategy(strategy),
        "AKOYA_POOL_WORKER": worker_name,
    }


def configured(strategy: str) -> bool:
    return bool(api_key() and image_for_strategy(strategy) and wallet_for_strategy(strategy))


def choose_currency(server: dict[str, Any], wallet_payload: dict[str, Any] | None = None) -> str:
    currencies = eligible_currencies(server, wallet_payload)
    return currencies[0] if currencies else ""


def eligible_currencies(server: dict[str, Any], wallet_payload: dict[str, Any] | None = None) -> list[str]:
    price = server.get("price") or {}
    on_demand = price.get("on_demand") or {}
    accepted = set(server.get("allowed_coins") or server.get("allowed_currencies") or []) or set(on_demand.keys())
    balances = {}
    if wallet_payload:
        for wallet in wallet_payload.get("wallets", []) or []:
            balances[str(wallet.get("name") or "")] = safe_float(wallet.get("balance"))
    currencies: list[str] = []
    for currency in currency_order():
        if accepted and currency not in accepted:
            continue
        native_price = safe_float(on_demand.get(currency))
        if native_price <= 0:
            continue
        if balances and balances.get(currency, 0.0) < native_price:
            continue
        currencies.append(currency)
    return currencies


async def create_order(server_id: int, strategy: str, server: dict[str, Any], native_price_day: float, currency: str) -> dict[str, Any]:
    worker_name = strategy_worker_name(strategy, server_id)
    image = image_for_strategy(strategy)
    if not image:
        raise HTTPException(status_code=409, detail=f"Imagem Clore ausente para {strategy_label(strategy)}")
    payload = {
        "currency": currency,
        "image": image,
        "renting_server": server_id,
        "type": "on-demand",
        "env": env_for_strategy(strategy, worker_name, server.get("gpu_model_normalized") or server.get("gpu_model_raw")),
        "required_price": native_price_day,
    }
    data = await request("POST", "/create_order", json_body=payload, create=True)
    return {
        "success": True,
        "server_id": server_id,
        "worker_name": worker_name,
        "pool_strategy": strategy,
        "price_usd_hr": round_money(safe_float(server.get("price_usd_hr"))),
        "price_usd_day": round_money(safe_float(server.get("price_usd_day"))),
        "native_price_day": native_price_day,
        "currency": currency,
        "image": image,
        "raw": sanitize_response(data),
    }


async def cancel_order(order_id: int, issue: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"id": order_id}
    if issue:
        payload["issue"] = issue[:2048]
    data = await request("POST", "/cancel_order", json_body=payload)
    return {"status": "cancelled", "raw": sanitize_response(data)}
