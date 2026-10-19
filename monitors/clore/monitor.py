"""
Monitor Clore.ai marketplace.

Primary source:
  https://api.clore.ai/v1/marketplace

If CLORE_API_KEY is missing, the old public webapi is published only as
diagnostic data. The dashboard must not make it actionable.
"""

import asyncio
import logging
import os
import re
import sys

sys.path.insert(0, "/app")

import httpx

from shared.base_monitor import BaseMonitor
from shared.gpu_hashrates import get_gpu, normalize_gpu_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("monitor.clore")

CLORE_OFFICIAL_API_URL = "https://api.clore.ai/v1/marketplace"
CLORE_PUBLIC_API_URL = "https://clore.ai/webapi/marketplace/servers"
CLORE_TOKEN_CONTRACT = os.getenv(
    "CLORE_TOKEN_CONTRACT",
    "0xE60201989b8628F43dC0605f585a72Bcf1F1e977",
)
COINGECKO_TOKEN_PRICE_URL = "https://api.coingecko.com/api/v3/simple/token_price/ethereum"
COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
DEXSCREENER_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{contract}"

_COUNT_RE = re.compile(r"^(\d+)[xX]\s+(.+)$")


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _parse_gpu(specs: dict, gpu_array: list) -> tuple[int, str]:
    if gpu_array:
        first = gpu_array[0]
        if isinstance(first, str):
            return len(gpu_array), first
        if isinstance(first, (list, tuple)) and first:
            return len(gpu_array), str(first[0])
        if isinstance(first, dict):
            return len(gpu_array), str(first.get("name") or first.get("model") or "")

    gpu_str = str(specs.get("gpu", "") or "")
    match = _COUNT_RE.match(gpu_str)
    if match:
        return int(match.group(1)), match.group(2)
    return 1, gpu_str


def _pick_native_price(server: dict) -> tuple[float, str]:
    price = server.get("price") or {}
    on_demand = price.get("on_demand") or {}
    allowed = server.get("allowed_coins") or server.get("allowed_currencies") or list(on_demand.keys())
    for currency in allowed:
        value = on_demand.get(currency)
        native = _safe_float(value)
        if native > 0:
            return native, currency
    return 0.0, ""


def _currency_order() -> list[str]:
    raw = os.getenv("CLORE_CURRENCY_ORDER", "CLORE-Blockchain,USD-Blockchain,bitcoin")
    return [item.strip() for item in raw.split(",") if item.strip()]


async def _fetch_clore_price_usd(client: httpx.AsyncClient) -> tuple[float, str]:
    override = _safe_float(os.getenv("CLORE_TOKEN_PRICE_USD"))
    if override > 0:
        return override, "env:CLORE_TOKEN_PRICE_USD"

    try:
        resp = await client.get(
            COINGECKO_TOKEN_PRICE_URL,
            params={
                "contract_addresses": CLORE_TOKEN_CONTRACT.lower(),
                "vs_currencies": "usd",
            },
        )
        resp.raise_for_status()
        raw = resp.json()
        price = _safe_float((raw.get(CLORE_TOKEN_CONTRACT.lower()) or {}).get("usd"))
        if price > 0:
            return price, "coingecko_token_price"
    except Exception as exc:
        logger.warning("Clore CoinGecko token price failed: %s", exc)

    try:
        resp = await client.get(DEXSCREENER_TOKEN_URL.format(contract=CLORE_TOKEN_CONTRACT))
        resp.raise_for_status()
        raw = resp.json()
        prices = [
            _safe_float(pair.get("priceUsd"))
            for pair in raw.get("pairs", []) or []
            if _safe_float(pair.get("priceUsd")) > 0
        ]
        if prices:
            return prices[0], "dexscreener_token_price"
    except Exception as exc:
        logger.warning("Clore DexScreener token price failed: %s", exc)

    return 0.0, "unavailable"


async def _fetch_currency_rates_usd(client: httpx.AsyncClient) -> dict[str, float | str]:
    rates: dict[str, float | str] = {
        "USD-Blockchain": 1.0,
        "source_usd": "fixed",
    }
    clore_price, clore_source = await _fetch_clore_price_usd(client)
    if clore_price > 0:
        rates["CLORE-Blockchain"] = clore_price
    rates["source_clore"] = clore_source

    btc_override = _safe_float(os.getenv("BTC_PRICE_USD"))
    if btc_override > 0:
        rates["bitcoin"] = btc_override
        rates["source_bitcoin"] = "env:BTC_PRICE_USD"
        return rates

    try:
        resp = await client.get(
            COINGECKO_SIMPLE_PRICE_URL,
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        resp.raise_for_status()
        btc_price = _safe_float((resp.json().get("bitcoin") or {}).get("usd"))
        if btc_price > 0:
            rates["bitcoin"] = btc_price
            rates["source_bitcoin"] = "coingecko_simple_price"
    except Exception as exc:
        logger.warning("Bitcoin CoinGecko price failed: %s", exc)
        rates["source_bitcoin"] = "unavailable"
    return rates


def _price_from_native(
    server: dict,
    rates_usd: dict[str, float | str],
    public_price_usd_day: float,
) -> tuple[float, str, float, str]:
    price = server.get("price") or {}
    on_demand = price.get("on_demand") or {}
    accepted = set(server.get("allowed_coins") or server.get("allowed_currencies") or list(on_demand.keys()))
    candidates: dict[str, tuple[float, float]] = {}
    for currency, raw_price in on_demand.items():
        if accepted and currency not in accepted:
            continue
        native = _safe_float(raw_price)
        if native <= 0:
            continue
        if currency == "USD-Blockchain":
            candidates[currency] = (native, native)
            continue
        rate = _safe_float(rates_usd.get(currency))
        if rate > 0:
            candidates[currency] = (native, native * rate)

    for currency in _currency_order():
        if currency in candidates:
            native, usd_day = candidates[currency]
            return usd_day, currency, native, f"{currency}_native_usd_rate"

    if candidates:
        currency, (native, usd_day) = min(candidates.items(), key=lambda item: item[1][1])
        return usd_day, currency, native, f"{currency}_native_usd_rate"

    native_price_day, price_currency = _pick_native_price(server)
    if public_price_usd_day > 0:
        return public_price_usd_day, price_currency, native_price_day, "public_usd_enrichment_fallback"
    return 0.0, price_currency, native_price_day, "native_no_usd_rate"


async def _fetch_public_servers() -> list[dict]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(CLORE_PUBLIC_API_URL)
        resp.raise_for_status()
        raw = resp.json()
    return raw.get("all_servers", []) or []


class CloreMonitor(BaseMonitor):
    async def fetch(self) -> dict:
        api_key = os.getenv("CLORE_API_KEY", "").strip()
        if api_key:
            try:
                return await self.fetch_official(api_key)
            except Exception as exc:
                logger.warning("Clore official API unavailable; diagnostic fallback: %s", exc)
                diagnostic = await self.fetch_public_diagnostic()
                diagnostic["official_enabled"] = True
                diagnostic["official_error"] = str(exc)
                diagnostic["diagnostic_only"] = True
                return diagnostic
        diagnostic = await self.fetch_public_diagnostic()
        diagnostic["official_enabled"] = False
        diagnostic["diagnostic_only"] = True
        diagnostic["error"] = "CLORE_API_KEY ausente; webapi publico publicado apenas como diagnostico"
        return diagnostic

    async def fetch_official(self, api_key: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            currency_rates_usd = await _fetch_currency_rates_usd(client)
            resp = await client.get(CLORE_OFFICIAL_API_URL, headers={"auth": api_key})
            resp.raise_for_status()
            raw = resp.json()

        if raw.get("code") not in {None, 0}:
            raise RuntimeError(f"Clore official API code={raw.get('code')} error={raw.get('error')}")

        all_servers: list = raw.get("servers", []) or []
        public_by_id: dict[str, dict] = {}
        try:
            public_by_id = {str(item.get("id")): item for item in await _fetch_public_servers()}
        except Exception as exc:
            logger.warning("Clore public price enrichment failed: %s", exc)
        total_servers = len(all_servers)
        available_count = sum(1 for item in all_servers if not item.get("rented", True))
        supported_servers = []
        available_supported = 0

        for server in all_servers:
            specs = server.get("specs") or {}
            public = public_by_id.get(str(server.get("id"))) or {}
            public_specs = public.get("specs") or {}
            gpu_count, gpu_raw = _parse_gpu(specs, [])
            norm = normalize_gpu_name(gpu_raw)
            if norm is None:
                continue
            gpu_data = get_gpu(gpu_raw)
            if gpu_data is None or not gpu_data.get("supported", False):
                continue

            rented = bool(server.get("rented", True))
            if not rented:
                available_supported += 1

            public_price = public.get("price") or {}
            public_price_usd = public_price.get("usd") or {}
            public_price_usd_day = _safe_float(public_price_usd.get("on_demand_usd"))
            price = server.get("price") or {}
            on_demand = price.get("on_demand") or {}
            allowed_coins = server.get("allowed_coins") or server.get("allowed_currencies") or list(on_demand.keys())
            price_usd_day, price_currency, native_price_day, price_source = _price_from_native(
                server,
                currency_rates_usd,
                public_price_usd_day,
            )
            price_usd_hr = price_usd_day / 24 if price_usd_day > 0 else 0.0
            pcie_lanes = int(specs.get("pcie_width") or public_specs.get("pcie_width") or 0)
            net = specs.get("net") or public_specs.get("net") or {}

            supported_servers.append({
                "server_id": server.get("id"),
                "gpu_model_raw": gpu_raw,
                "gpu_model_normalized": norm,
                "gpu_count": gpu_count,
                "gpu_vram_gb": specs.get("gpuram") or 0,
                "price_usd_hr": round(price_usd_hr, 4),
                "price_usd_day": round(price_usd_day, 4),
                "spot_price_usd_hr": 0.0,
                "price_btc_hr": round(_safe_float(on_demand.get("bitcoin")) / 24, 8),
                "price_clore_hr": round(_safe_float(on_demand.get("CLORE-Blockchain")) / 24, 8),
                "price_currency": price_currency,
                "native_price_day": native_price_day,
                "price": price,
                "price_source": price_source,
                "currency_rates_usd": {
                    key: value for key, value in currency_rates_usd.items() if isinstance(value, (int, float))
                },
                "allowed_coins": allowed_coins,
                "rented": rented,
                "availability_state": "marketplace_available" if not rented else "rented",
                "available_verified": False,
                "source": "official_api",
                "diagnostic_only": False,
                "reliability": round(_safe_float(server.get("reliability"), _safe_float(public.get("reliability"), 1.0)), 4),
                "rating_avg": (public.get("rating") or {}).get("avg") or 0.0,
                "rating_cnt": (public.get("rating") or {}).get("cnt") or 0,
                "country": net.get("cc") or "",
                "net_up_mbps": round(_safe_float(net.get("up")), 1),
                "net_down_mbps": round(_safe_float(net.get("down")), 1),
                "cuda_version": server.get("cuda_version") or public.get("cuda_version") or "",
                "pcie_lanes": pcie_lanes,
                "pcie_rev": specs.get("pcie_rev") or public_specs.get("pcie_rev") or 0,
                "meets_pcie": pcie_lanes >= 8,
                "ram_gb": specs.get("ram") or 0,
                "disk_speed_mbps": round(_safe_float(specs.get("disk_speed")), 1),
                "cpu": specs.get("cpu", ""),
                "mrl_min": server.get("mrl", 0),
                "autoprice": "official",
                "low_value": gpu_data.get("low_value", False),
            })

        logger.info(
            "Clore official: %s servers, %s available, %s supported, %s available+supported",
            total_servers,
            available_count,
            len(supported_servers),
            available_supported,
        )
        return {
            "official_enabled": True,
            "diagnostic_only": False,
            "total_servers": total_servers,
            "available_count": available_count,
            "supported_count": len(supported_servers),
            "available_supported_count": available_supported,
            "servers": supported_servers,
        }

    async def fetch_public_diagnostic(self) -> dict:
        all_servers: list = await _fetch_public_servers()
        total_servers = len(all_servers)
        available_count = sum(1 for item in all_servers if not item.get("rented", True))
        supported_servers = []
        available_supported = 0

        for server in all_servers:
            specs = server.get("specs") or {}
            gpu_count, gpu_raw = _parse_gpu(specs, server.get("gpu_array") or [])
            norm = normalize_gpu_name(gpu_raw)
            if norm is None:
                continue
            gpu_data = get_gpu(gpu_raw)
            if gpu_data is None or not gpu_data.get("supported", False):
                continue

            rented = bool(server.get("rented", True))
            if not rented:
                available_supported += 1

            price = server.get("price") or {}
            price_usd = price.get("usd") or {}
            on_demand = price.get("on_demand") or {}
            price_usd_day = _safe_float(price_usd.get("on_demand_usd"))
            spot_usd_day = _safe_float(price_usd.get("spot"))
            pcie_lanes = int(specs.get("pcie_width") or 0)
            net = specs.get("net") or {}
            rating = server.get("rating") or {}

            supported_servers.append({
                "server_id": server.get("id"),
                "gpu_model_raw": gpu_raw,
                "gpu_model_normalized": norm,
                "gpu_count": gpu_count,
                "gpu_vram_gb": specs.get("gpuram") or 0,
                "price_usd_hr": round(price_usd_day / 24, 4) if price_usd_day > 0 else 0.0,
                "price_usd_day": round(price_usd_day, 4),
                "spot_price_usd_hr": round(spot_usd_day / 24, 4) if spot_usd_day > 0 else 0.0,
                "price_btc_hr": on_demand.get("bitcoin") or 0,
                "price_clore_hr": on_demand.get("CLORE-Blockchain") or 0,
                "price_currency": "",
                "price_source": "public_webapi",
                "allowed_coins": [],
                "rented": rented,
                "availability_state": "observed",
                "available_verified": False,
                "source": "public_webapi",
                "diagnostic_only": True,
                "reliability": round(_safe_float(server.get("reliability")), 4),
                "rating_avg": rating.get("avg") or 0.0,
                "rating_cnt": rating.get("cnt") or 0,
                "country": net.get("cc") or "",
                "net_up_mbps": round(_safe_float(net.get("up")), 1),
                "net_down_mbps": round(_safe_float(net.get("down")), 1),
                "cuda_version": server.get("cuda_version") or "",
                "pcie_lanes": pcie_lanes,
                "pcie_rev": specs.get("pcie_rev") or 0,
                "meets_pcie": pcie_lanes >= 8,
                "ram_gb": specs.get("ram") or 0,
                "disk_speed_mbps": round(_safe_float(specs.get("disk_speed")), 1),
                "cpu": specs.get("cpu", ""),
                "mrl_min": server.get("mrl", 0),
                "autoprice": server.get("autoprice", ""),
                "low_value": gpu_data.get("low_value", False),
            })

        logger.info(
            "Clore diagnostic webapi: %s servers, %s available, %s supported, %s available+supported",
            total_servers,
            available_count,
            len(supported_servers),
            available_supported,
        )
        return {
            "total_servers": total_servers,
            "available_count": available_count,
            "supported_count": len(supported_servers),
            "available_supported_count": available_supported,
            "servers": supported_servers,
        }


async def main() -> None:
    monitor = CloreMonitor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", 6379)),
        poll_interval=float(os.getenv("POLL_INTERVAL", 30)),
        redis_key="monitor:clore",
    )
    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
