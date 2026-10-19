import asyncio
import json
import os
import socket
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
STATE_PATH = Path(os.getenv("SPHERON_SNIPER_STATE_PATH", str(DATA_DIR / "spheron_sniper_state.json")))
CONFIG_PATH = Path(os.getenv("SPHERON_CONTROL_CONFIG_PATH", str(DATA_DIR / "spheron_control_config.json")))
FIXED_COSTS_PATH = Path(os.getenv("FIXED_WORKER_COSTS_PATH", str(DATA_DIR / "fixed_worker_costs.json")))
EARNINGS_PATH = Path(os.getenv("SPHERON_EARNINGS_PATH", str(DATA_DIR / "spheron_earnings_history.json")))
AKOYA_REDIS_KEY = "monitor:akoya"
PEARL_REDIS_KEY = "monitor:pearl"
TERMINAL_STATUSES = {"terminated", "deleted", "destroyed", "failed", "error", "terminated-provider"}

DEFAULT_CONFIG: dict[str, Any] = {
    "create_enabled": True,
    "target_preset": "h100-sxm5-1x",
    "desired_online_gpus": 10,
    "global_active_limit": 20,
    "ssh_parallel": 10,
    "create_interval_seconds": 20,
    "max_price_usd_hr": 1.8,
    "low_credits_threshold": 5,
    "auto_destroy_bad_enabled": True,
    "bad_hash_min_ths": 620,
    "bad_hash_grace_seconds": 1200,
    "bad_hash_samples_required": 3,
}

TARGET_PRESETS: dict[str, dict[str, Any]] = {
    "h100-sxm5-1x": {
        "gpu_type": "H100_SXM5",
        "gpu_count": 1,
        "provider": "spheron-es",
        "offer_id": "EU North 1::gpu-h100-sxm::1gpu-16vcpu-200gb::spot",
        "region": "EU North 1",
        "instance_type": "SPOT",
        "default_hourly_rate_usd": 1.728,
    }
}

OURBIT_PRL_DEPTH_URL = "https://api.ourbit.com/api/v3/depth?symbol=PRLUSDT&limit=100"
OURBIT_PRL_TICKER_URL = "https://api.ourbit.com/api/v3/ticker/24hr?symbol=PRLUSDT"
PEARL_TRADE_PRL_DEPTH_URL = "https://api.pearl-trade.com/v1/markets/USDC-ARB/orderbook?depth=30"
PEARL_TRADE_PRL_TRADES_URL = "https://api.pearl-trade.com/v1/markets/USDC-ARB/trades?limit=500"
BINANCE_PRL_FUTURES_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth?symbol=PRLUSDT&limit=100"
BINANCE_PRL_FUTURES_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=PRLUSDT"
SAFETRADE_PRL_MARKETS_URL = "https://api.coinpaprika.com/v1/coins/prl-pearl-1/markets"
SAFETRADE_PRL_BOOK_URL = "https://safetrade.com/api/v2/trade/public/markets/prlusdt/depth?limit=100"
SAFETRADE_PRL_TICKER_URL = "https://safetrade.com/api/v2/trade/public/tickers/prlusdt"
SAFETRADE_BOOK_CACHE_PATH = Path(os.getenv("SAFETRADE_BOOK_CACHE_PATH", str(DATA_DIR / "safetrade_books_cache.json")))
WPRL_DEXSCREENER_URLS = (
    "https://api.dexscreener.com/latest/dex/tokens/0x07696dcab55e62cfef953666b29fe1970518cb00",
    "https://api.dexscreener.com/latest/dex/tokens/0xcB139040490ba48a7D2CCdC4848226b63986DB3f",
)
PEARL_TRADE_WPRL_ADDRESS = "0xcb139040490ba48a7d2ccdc4848226b63986db3f"
PERLE_COINGECKO_TICKERS_URL = "https://api.coingecko.com/api/v3/coins/perle/tickers?include_exchange_logo=false&depth=true"
PERLE_COINPAPRIKA_MARKETS_URL = "https://api.coinpaprika.com/v1/coins/prl-perle/markets"

app = FastAPI(title="Spheron Control Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://safetrade.com",
        "https://safe.trade",
        "http://localhost:8091",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.middleware("http")
async def allow_private_network_access(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = origin in {"https://safetrade.com", "https://safe.trade", "http://localhost:8091"}
    if request.method == "OPTIONS" and request.headers.get("access-control-request-private-network") == "true":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["Vary"] = "Origin"
    return response


def now_ts() -> float:
    return time.time()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def default_book_amounts() -> list[float]:
    amounts: list[float] = []
    for raw in (os.getenv("PEARL_BOOK_AMOUNTS_PRL") or "10,100,1000").split(","):
        amount = safe_float(raw)
        if amount > 0:
            amounts.append(amount)
    return amounts or [10.0, 100.0, 1000.0]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def safetrade_cache_ttl_seconds() -> int:
    return max(1, safe_int(os.getenv("SAFETRADE_BOOK_CACHE_TTL_SECONDS"), 30))


def safetrade_stale_cache_seconds() -> int:
    return max(safetrade_cache_ttl_seconds(), safe_int(os.getenv("SAFETRADE_BOOK_STALE_SECONDS"), 600))


def safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(default or {})
    return data if isinstance(data, dict) else dict(default or {})


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def public_config() -> dict[str, Any]:
    raw = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update({key: value for key, value in raw.items() if key in DEFAULT_CONFIG})
    merged["create_enabled"] = safe_bool(merged.get("create_enabled"), True)
    merged["target_preset"] = str(merged.get("target_preset") or "h100-sxm5-1x")
    merged["desired_online_gpus"] = max(0, safe_int(merged.get("desired_online_gpus"), 10))
    merged["global_active_limit"] = max(1, safe_int(merged.get("global_active_limit"), 20))
    merged["ssh_parallel"] = max(1, safe_int(merged.get("ssh_parallel"), 10))
    merged["create_interval_seconds"] = max(5, safe_int(merged.get("create_interval_seconds"), 20))
    merged["max_price_usd_hr"] = round(max(0.0, safe_float(merged.get("max_price_usd_hr"), 1.8)), 6)
    merged["low_credits_threshold"] = round(max(0.0, safe_float(merged.get("low_credits_threshold"), 5)), 2)
    merged["auto_destroy_bad_enabled"] = safe_bool(merged.get("auto_destroy_bad_enabled"), True)
    merged["bad_hash_min_ths"] = round(max(0.0, safe_float(merged.get("bad_hash_min_ths"), 620)), 3)
    merged["bad_hash_grace_seconds"] = max(0, safe_int(merged.get("bad_hash_grace_seconds"), 1200))
    merged["bad_hash_samples_required"] = max(1, safe_int(merged.get("bad_hash_samples_required"), 3))
    if merged["target_preset"] not in TARGET_PRESETS:
        merged["target_preset"] = "h100-sxm5-1x"
    return merged


def redis_payload(key: str) -> dict[str, Any]:
    host = os.getenv("REDIS_HOST", "redis")
    port = safe_int(os.getenv("REDIS_PORT"), 6379)
    command = f"*2\r\n$3\r\nGET\r\n${len(key)}\r\n{key}\r\n".encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=1) as sock:
            sock.settimeout(1)
            sock.sendall(command)
            header = b""
            while not header.endswith(b"\r\n"):
                chunk = sock.recv(1)
                if not chunk:
                    return {}
                header += chunk
            if header.startswith(b"$-1") or not header.startswith(b"$"):
                return {}
            length = safe_int(header[1:].strip(), -1)
            if length <= 0:
                return {}
            data = b""
            while len(data) < length:
                chunk = sock.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
    except OSError:
        return {}
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def akoya_rates(pearl: dict[str, Any]) -> dict[str, Any]:
    per_hour = pearl.get("usd_per_th_per_hour") if isinstance(pearl.get("usd_per_th_per_hour"), dict) else {}
    per_day = pearl.get("usd_per_th_per_day") if isinstance(pearl.get("usd_per_th_per_day"), dict) else {}
    rate_hr = safe_float(per_hour.get("akoya"))
    rate_day = safe_float(per_day.get("akoya"))
    if rate_hr <= 0 and rate_day > 0:
        rate_hr = rate_day / 24
    if rate_day <= 0 and rate_hr > 0:
        rate_day = rate_hr * 24
    return {
        "usd_per_th_per_hour": round(rate_hr, 8) if rate_hr > 0 else None,
        "usd_per_th_per_day": round(rate_day, 8) if rate_day > 0 else None,
        "prl_price_usd": pearl.get("prl_price_usd"),
        "network_hashrate_ehs": pearl.get("network_hashrate_ehs"),
        "blocks_per_day": pearl.get("blocks_per_day"),
        "ok": bool(pearl),
    }


def parse_book_amounts(raw: str | None = None) -> list[float]:
    source = raw if raw else ",".join(str(item) for item in default_book_amounts())
    amounts: list[float] = []
    for item in source.split(","):
        amount = safe_float(item)
        if amount > 0:
            amounts.append(round(amount, 8))
    return amounts or default_book_amounts()


def number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    parsed = safe_float(value)
    return parsed if parsed != 0 or str(value).strip() in {"0", "0.0"} else None


def normalize_book_side(levels: Any) -> list[list[float]]:
    normalized: list[list[float]] = []
    if not isinstance(levels, list):
        return normalized
    for item in levels:
        price: Any = None
        qty: Any = None
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            price, qty = item[0], item[1]
        elif isinstance(item, dict):
            price = item.get("price") or item.get("p")
            qty = item.get("amount") or item.get("quantity") or item.get("qty") or item.get("volume") or item.get("q")
        price_f = safe_float(price)
        qty_f = safe_float(qty)
        if price_f > 0 and qty_f > 0:
            normalized.append([price_f, qty_f])
    return normalized


def normalize_pearl_trade_side(levels: Any) -> list[list[float]]:
    normalized: list[list[float]] = []
    if not isinstance(levels, list):
        return normalized
    for item in levels:
        if not isinstance(item, dict):
            continue
        price = safe_float(item.get("price")) / 1_000_000
        qty = safe_float(item.get("qtySats")) / 100_000_000
        if price > 0 and qty > 0:
            normalized.append([price, qty])
    return normalized


def pearl_trade_ticker_from_trades(payload: Any) -> dict[str, Any]:
    trades = payload.get("trades") if isinstance(payload, dict) and isinstance(payload.get("trades"), list) else []
    if not trades:
        return {}
    last_trade = trades[0] if isinstance(trades[0], dict) else {}
    cutoff = now_ts() - 86400
    volume_prl = 0.0
    volume_usdc = 0.0
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        created_at = safe_float(trade.get("created_at"))
        if created_at and created_at < cutoff:
            continue
        volume_prl += safe_float(trade.get("qty_sats")) / 100_000_000
        volume_usdc += safe_float(trade.get("quote_units")) / 1_000_000
    return {
        "lastPrice": safe_float(last_trade.get("price_micro_per_prl")) / 1_000_000,
        "volume": volume_prl,
        "quoteVolume": volume_usdc,
        "closeTime": last_trade.get("created_at"),
    }


def quote_sell_from_bids(bids: list[list[float]], amount_prl: float) -> dict[str, Any]:
    remaining = amount_prl
    got_quote = 0.0
    levels_used = 0
    worst_price = None
    for price, qty in bids:
        if remaining <= 0:
            break
        fill = min(remaining, qty)
        got_quote += fill * price
        remaining -= fill
        levels_used += 1
        worst_price = price
    filled = amount_prl - remaining
    avg_price = got_quote / filled if filled > 0 else None
    return {
        "requested_prl": round(amount_prl, 8),
        "filled_prl": round(filled, 8),
        "unfilled_prl": round(max(0.0, remaining), 8),
        "quote_out": round(got_quote, 8),
        "avg_sell_price": round(avg_price, 8) if avg_price is not None else None,
        "worst_fill_price": round(worst_price, 8) if worst_price is not None else None,
        "levels_used": levels_used,
        "complete": remaining <= 0.00000001,
    }


def depth_within_pct(bids: list[list[float]], pct: float) -> dict[str, Any]:
    if not bids:
        return {"base": 0.0, "quote": 0.0}
    best_bid = bids[0][0]
    min_price = best_bid * (1 - pct / 100)
    base = 0.0
    quote = 0.0
    for price, qty in bids:
        if price < min_price:
            break
        base += qty
        quote += price * qty
    return {"base": round(base, 8), "quote": round(quote, 8)}


async def fetch_json(client: httpx.AsyncClient, url: str) -> Any:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


def safetrade_headers() -> dict[str, str]:
    cookie = os.getenv("SAFETRADE_COOKIE", "").strip()
    cf_clearance = os.getenv("SAFETRADE_CF_CLEARANCE", "").strip()
    if not cookie and cf_clearance:
        cookie = f"cf_clearance={cf_clearance}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://safetrade.com/exchange/PRL-USDT?type=basic",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


async def fetch_safetrade_json(client: httpx.AsyncClient, url: str) -> Any:
    response = await client.get(url, headers=safetrade_headers())
    response.raise_for_status()
    return response.json()


def normalize_safetrade_ticker(ticker: Any, trades: Any = None) -> dict[str, Any]:
    raw = ticker if isinstance(ticker, dict) else {}
    normalized = {
        "lastPrice": raw.get("last") or raw.get("lastPrice"),
        "volume": raw.get("amount") or raw.get("volume"),
        "quoteVolume": raw.get("volume") or raw.get("quoteVolume"),
        "closeTime": raw.get("at") or raw.get("updated_at"),
    }
    trade_items = trades if isinstance(trades, list) else []
    if trade_items and isinstance(trade_items[0], dict):
        latest = trade_items[0]
        normalized["lastPrice"] = normalized["lastPrice"] or latest.get("price")
        normalized["closeTime"] = normalized["closeTime"] or latest.get("created_at")
    return normalized


def safetrade_cache_payload(max_age_seconds: int | None = None) -> dict[str, Any] | None:
    payload = load_json(SAFETRADE_BOOK_CACHE_PATH)
    if not payload or payload.get("error"):
        return None
    ts = safe_float(payload.get("ts"))
    max_age = max_age_seconds if max_age_seconds is not None else safetrade_cache_ttl_seconds()
    if ts <= 0 or now_ts() - ts > max_age:
        return None
    if not isinstance(payload.get("bids"), list) and not isinstance(payload.get("asks"), list):
        return None
    return payload


def safetrade_market_from_cache(payload: dict[str, Any], amounts: list[float], stale: bool = False) -> dict[str, Any]:
    depth = {
        "bids": payload.get("bids") if isinstance(payload.get("bids"), list) else [],
        "asks": payload.get("asks") if isinstance(payload.get("asks"), list) else [],
        "timestamp": payload.get("ts"),
    }
    market = cex_book_market(
        exchange="SafeTrade",
        pair="PRL/USDT",
        asset="Pearl PRL",
        relation="Pearl mineravel listado pela CoinPaprika",
        depth=depth,
        ticker=normalize_safetrade_ticker(payload.get("ticker"), payload.get("trades")),
        amounts=amounts,
        url="https://safetrade.com/exchange/PRL-USDT?type=basic",
        note=(
            "Ultimo book via Chrome local; cache esta velho porque a SafeTrade voltou 403/Cloudflare."
            if stale
            else "Book real via Chrome persistente local; sessao/Cloudflare ficam no perfil do navegador."
        ),
    )
    market["book_status"] = "book_stale_browser" if stale else "book_real_browser"
    market["market_id"] = payload.get("market") or "prlusdt"
    market["cache_age_seconds"] = round(now_ts() - safe_float(payload.get("ts")), 3)
    return market


def valid_browser_cache_side(levels: Any) -> list[list[float]]:
    normalized = normalize_book_side(levels)
    return [[round(price, 12), round(qty, 12)] for price, qty in normalized[:500]]


def save_safetrade_browser_cache(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")
    market = str(payload.get("market") or "prlusdt").strip().lower()
    if market != "prlusdt":
        raise HTTPException(status_code=400, detail="only prlusdt is supported")
    bids = valid_browser_cache_side(payload.get("bids"))
    asks = valid_browser_cache_side(payload.get("asks"))
    if not bids and not asks:
        raise HTTPException(status_code=400, detail="payload must include bids or asks")
    cache = {
        "ts": now_ts(),
        "source": "safetrade_browser_manual",
        "market": market,
        "bids": bids,
        "asks": asks,
        "sequence": payload.get("sequence"),
        "ticker": payload.get("ticker") if isinstance(payload.get("ticker"), dict) else None,
        "trades": payload.get("trades") if isinstance(payload.get("trades"), list) else None,
        "error": None,
    }
    save_json(SAFETRADE_BOOK_CACHE_PATH, cache)
    return {
        "ok": True,
        "cache_path": str(SAFETRADE_BOOK_CACHE_PATH),
        "market": market,
        "bids": len(bids),
        "asks": len(asks),
        "ts": cache["ts"],
    }


def cex_book_market(
    *,
    exchange: str,
    pair: str,
    asset: str,
    relation: str,
    depth: dict[str, Any],
    ticker: dict[str, Any] | None,
    amounts: list[float],
    url: str,
    note: str = "",
) -> dict[str, Any]:
    bids = normalize_book_side(depth.get("bids"))
    asks = normalize_book_side(depth.get("asks"))
    best_bid = bids[0][0] if bids else number_or_none((ticker or {}).get("bidPrice"))
    best_ask = asks[0][0] if asks else number_or_none((ticker or {}).get("askPrice"))
    spread_pct = None
    if best_bid and best_ask:
        spread_pct = ((best_ask - best_bid) / best_bid) * 100
    quotes = {str(amount): quote_sell_from_bids(bids, amount) for amount in amounts}
    return {
        "exchange": exchange,
        "pair": pair,
        "kind": "cex_book",
        "asset": asset,
        "relation": relation,
        "book_status": "book_real" if bids or asks else "book_empty",
        "best_bid": round(best_bid, 10) if best_bid is not None else None,
        "best_ask": round(best_ask, 10) if best_ask is not None else None,
        "last": number_or_none((ticker or {}).get("lastPrice")),
        "spread_pct": round(spread_pct, 6) if spread_pct is not None else None,
        "base_volume_24h": number_or_none((ticker or {}).get("volume")),
        "quote_volume_24h": number_or_none((ticker or {}).get("quoteVolume")),
        "sell_quotes": quotes,
        "sell_depth_2pct": depth_within_pct(bids, 2),
        "sell_depth_5pct": depth_within_pct(bids, 5),
        "sell_depth_10pct": depth_within_pct(bids, 10),
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "updated_at": depth.get("timestamp") or depth.get("E") or (ticker or {}).get("closeTime"),
        "url": url,
        "note": note,
    }


async def fetch_pearl_trade_market(client: httpx.AsyncClient, amounts: list[float]) -> dict[str, Any]:
    depth, trades = await asyncio.gather(
        fetch_json(client, PEARL_TRADE_PRL_DEPTH_URL),
        fetch_json(client, PEARL_TRADE_PRL_TRADES_URL),
    )
    normalized_depth = {
        "bids": normalize_pearl_trade_side(depth.get("bids") if isinstance(depth, dict) else []),
        "asks": normalize_pearl_trade_side(depth.get("asks") if isinstance(depth, dict) else []),
    }
    ticker = pearl_trade_ticker_from_trades(trades)
    market = cex_book_market(
        exchange="Pearl Trade",
        pair="PRL/USDC",
        asset="Pearl Research PRL",
        relation="orderbook oficial Pearl Trade, mercado USDC-ARB",
        depth=normalized_depth,
        ticker=ticker,
        amounts=amounts,
        url="https://pearl-trade.com/?ref=PEARL",
        note="Book real da Pearl Trade. Price vem em micro-USDC e qtySats em 1e8 PRL; convertido no backend.",
    )
    market["fee_pct"] = 1.0
    for quote in market.get("sell_quotes", {}).values():
        if isinstance(quote, dict) and quote.get("quote_out") is not None:
            quote["fee_pct"] = 1.0
            quote["quote_out_after_fee"] = round(safe_float(quote.get("quote_out")) * 0.99, 8)
    market["market_id"] = (depth or {}).get("market") if isinstance(depth, dict) else "USDC-ARB"
    return market


async def fetch_ourbit_market(client: httpx.AsyncClient, amounts: list[float]) -> dict[str, Any]:
    depth, ticker = await asyncio.gather(
        fetch_json(client, OURBIT_PRL_DEPTH_URL),
        fetch_json(client, OURBIT_PRL_TICKER_URL),
    )
    return cex_book_market(
        exchange="Ourbit",
        pair="PRL/USDT",
        asset="Pearl Token PRL",
        relation="provavel Pearl mineravel atual da Ourbit; confirmar deposito/rede antes de enviar",
        depth=depth,
        ticker=ticker,
        amounts=amounts,
        url="https://www.ourbit.com/exchange/PRL_USDT",
    )


async def fetch_binance_futures_market(client: httpx.AsyncClient, amounts: list[float]) -> dict[str, Any]:
    depth, ticker = await asyncio.gather(
        fetch_json(client, BINANCE_PRL_FUTURES_DEPTH_URL),
        fetch_json(client, BINANCE_PRL_FUTURES_TICKER_URL),
    )
    return cex_book_market(
        exchange="Binance Futures",
        pair="PRL/USDT PERP",
        asset="Perle/PRL derivative",
        relation="nao e spot para vender Pearl minerado; serve so como derivativo/lookalike",
        depth=depth,
        ticker=ticker,
        amounts=amounts,
        url="https://www.binance.com/en/futures/PRLUSDT",
        note="Derivativo futures, sem deposito spot de Pearl mineravel.",
    )


async def fetch_safetrade_market(client: httpx.AsyncClient, amounts: list[float]) -> dict[str, Any]:
    cached = safetrade_cache_payload()
    if cached:
        return safetrade_market_from_cache(cached, amounts)

    direct_error = ""
    try:
        depth, ticker = await asyncio.gather(
            fetch_safetrade_json(client, SAFETRADE_PRL_BOOK_URL),
            fetch_safetrade_json(client, SAFETRADE_PRL_TICKER_URL),
        )
        market = cex_book_market(
            exchange="SafeTrade",
            pair="PRL/USDT",
            asset="Pearl PRL",
            relation="Pearl mineravel listado pela CoinPaprika",
            depth=depth if isinstance(depth, dict) else {},
            ticker=normalize_safetrade_ticker(ticker),
            amounts=amounts,
            url="https://safetrade.com/exchange/PRL-USDT?type=basic",
            note="API oficial SafeTrade: /api/v2/trade/public/markets/prlusdt/depth",
        )
        market["book_status"] = "book_real_http"
        return market
    except Exception as exc:
        direct_error = str(exc)

    stale_cached = safetrade_cache_payload(safetrade_stale_cache_seconds())
    if stale_cached:
        market = safetrade_market_from_cache(stale_cached, amounts, stale=True)
        market["note"] = f"{market['note']} Erro atual: {direct_error[:140]}"
        return market

    price = None
    volume = None
    updated = None
    try:
        markets = await fetch_json(client, SAFETRADE_PRL_MARKETS_URL)
        if isinstance(markets, dict):
            items = markets.get("value") if isinstance(markets.get("value"), list) else []
        else:
            items = markets if isinstance(markets, list) else []
        for item in items:
            if not isinstance(item, dict) or str(item.get("exchange_id")) != "safetrade":
                continue
            usd = (item.get("quotes") or {}).get("USD") if isinstance(item.get("quotes"), dict) else {}
            price = number_or_none((usd or {}).get("price"))
            volume = number_or_none((usd or {}).get("volume_24h"))
            updated = item.get("last_updated")
            break
    except Exception as exc:
        direct_error = f"{direct_error}; fallback {exc}"

    return {
        "exchange": "SafeTrade",
        "pair": "PRL/USDT",
        "kind": "cex_book",
        "asset": "Pearl PRL",
        "relation": "Pearl mineravel listado pela CoinPaprika",
        "book_status": "fallback_sem_book",
        "best_bid": None,
        "best_ask": None,
        "last": price,
        "spread_pct": None,
        "base_volume_24h": None,
        "quote_volume_24h": volume,
        "sell_quotes": {str(amount): None for amount in amounts},
        "sell_depth_2pct": None,
        "sell_depth_5pct": None,
        "sell_depth_10pct": None,
        "bid_levels": 0,
        "ask_levels": 0,
        "updated_at": updated,
        "url": "https://safetrade.com/exchange/PRL-USDT?type=basic",
        "note": f"API oficial SafeTrade bloqueada/indisponivel para este servidor; usando fallback agregado. Erro: {direct_error[:180]}",
    }


async def fetch_wprl_dex_markets(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    payloads = await asyncio.gather(
        *(fetch_json(client, url) for url in WPRL_DEXSCREENER_URLS),
        return_exceptions=True,
    )
    pairs: list[dict[str, Any]] = []
    for payload in payloads:
        if isinstance(payload, Exception):
            pairs.append({
                "dex_error": str(payload),
            })
            continue
        if isinstance(payload, dict) and isinstance(payload.get("pairs"), list):
            pairs.extend([item for item in payload.get("pairs", []) if isinstance(item, dict)])
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        if pair.get("dex_error"):
            rows.append({
                "exchange": "DexScreener",
                "pair": "WPRL/*",
                "kind": "dex_pool",
                "asset": "Wrapped Pearl WPRL",
                "relation": "erro consultando pool DEX",
                "book_status": "erro",
                "note": pair.get("dex_error"),
            })
            continue
        if not isinstance(pair, dict):
            continue
        base = pair.get("baseToken") if isinstance(pair.get("baseToken"), dict) else {}
        quote = pair.get("quoteToken") if isinstance(pair.get("quoteToken"), dict) else {}
        base_address = str(base.get("address") or "").lower()
        source_label = "Pearl Trade wPRL" if base_address == PEARL_TRADE_WPRL_ADDRESS else "PearlBridge WPRL"
        liquidity = pair.get("liquidity") if isinstance(pair.get("liquidity"), dict) else {}
        volume = pair.get("volume") if isinstance(pair.get("volume"), dict) else {}
        txns = pair.get("txns") if isinstance(pair.get("txns"), dict) else {}
        h24 = txns.get("h24") if isinstance(txns.get("h24"), dict) else {}
        rows.append({
            "exchange": f"{str(pair.get('dexId') or 'DEX').title()} {','.join(pair.get('labels') or [])}".strip(),
            "pair": f"{base.get('symbol') or 'WPRL'}/{quote.get('symbol') or '-'}",
            "kind": "dex_pool",
            "asset": source_label,
            "relation": "Pearl-related wrapped token; sem order book, usar quote de swap para execucao exata",
            "book_status": "dex_liquidity_sem_book",
            "best_bid": None,
            "best_ask": None,
            "last": number_or_none(pair.get("priceUsd")),
            "spread_pct": None,
            "base_volume_24h": None,
            "quote_volume_24h": number_or_none(volume.get("h24")),
            "liquidity_usd": number_or_none(liquidity.get("usd")),
            "liquidity_base": number_or_none(liquidity.get("base")),
            "liquidity_quote": number_or_none(liquidity.get("quote")),
            "txns_24h": safe_int(h24.get("buys")) + safe_int(h24.get("sells")),
            "pair_address": pair.get("pairAddress"),
            "updated_at": pair.get("pairCreatedAt"),
            "url": pair.get("url"),
            "note": f"AMM nao tem bids/asks. Fonte: {source_label}. Para preco executavel exato, integrar Uniswap Quoter.",
        })
    rows.sort(key=lambda item: safe_float(item.get("liquidity_usd")), reverse=True)
    return rows


async def fetch_perle_lookalikes(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    try:
        payload = await fetch_json(client, PERLE_COINPAPRIKA_MARKETS_URL)
        items = payload.get("value") if isinstance(payload, dict) and isinstance(payload.get("value"), list) else payload
        if not isinstance(items, list):
            items = []
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            usd = (item.get("quotes") or {}).get("USD") if isinstance(item.get("quotes"), dict) else {}
            rows.append({
                "exchange": item.get("exchange_name") or "-",
                "pair": item.get("pair") or "-",
                "kind": "lookalike_aggregated",
                "asset": "Perle PRL / outro PRL",
                "relation": "nao assumir que aceita Pearl minerado",
                "book_status": "agregador_sem_book",
                "last": number_or_none((usd or {}).get("price")),
                "spread_pct": None,
                "quote_volume_24h": number_or_none((usd or {}).get("volume_24h")),
                "url": item.get("market_url"),
                "updated_at": item.get("last_updated"),
                "note": "CoinPaprika: mercado de Perle PRL/lookalike, sem book exato.",
            })
        rows.sort(key=lambda item: safe_float(item.get("quote_volume_24h")), reverse=True)
        return rows
    except Exception as exc:
        primary_error = str(exc)
    try:
        payload = await fetch_json(client, PERLE_COINGECKO_TICKERS_URL)
    except Exception as exc:
        return [{
            "exchange": "Agregadores",
            "pair": "PRL/*",
            "kind": "lookalike_error",
            "asset": "Perle PRL",
            "book_status": "erro",
            "note": f"CoinPaprika: {primary_error}; CoinGecko: {exc}",
        }]
    tickers = payload.get("tickers") if isinstance(payload, dict) and isinstance(payload.get("tickers"), list) else []
    rows: list[dict[str, Any]] = []
    for item in tickers[:60]:
        if not isinstance(item, dict):
            continue
        market = item.get("market") if isinstance(item.get("market"), dict) else {}
        rows.append({
            "exchange": market.get("name") or "-",
            "pair": f"{item.get('base')}/{item.get('target')}",
            "kind": "lookalike_aggregated",
            "asset": "Perle PRL / outro PRL",
            "relation": "nao assumir que aceita Pearl minerado",
            "book_status": "agregador_sem_book",
            "last": number_or_none(item.get("last")),
            "spread_pct": number_or_none(item.get("bid_ask_spread_percentage")),
            "quote_volume_24h": number_or_none((item.get("converted_volume") or {}).get("usd") if isinstance(item.get("converted_volume"), dict) else None),
            "url": item.get("trade_url"),
            "updated_at": item.get("last_traded_at"),
            "note": "Listagem por ticker PRL; conferir contrato/rede antes de usar.",
        })
    rows.sort(key=lambda item: safe_float(item.get("quote_volume_24h")), reverse=True)
    return rows


async def pearl_books_payload(amounts_raw: str | None = None) -> dict[str, Any]:
    amounts = parse_book_amounts(amounts_raw)
    timeout = httpx.Timeout(12.0, connect=5.0)
    headers = {"User-Agent": "monitor-gpu/pearl-books"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        tasks = [
            fetch_pearl_trade_market(client, amounts),
            fetch_ourbit_market(client, amounts),
            fetch_safetrade_market(client, amounts),
            fetch_wprl_dex_markets(client),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    markets: list[dict[str, Any]] = []
    source_names = ("Pearl Trade", "Ourbit", "SafeTrade", "WPRL DexScreener")
    for index, result in enumerate(results):
        if isinstance(result, Exception):
            markets.append({
                "exchange": source_names[index] if index < len(source_names) else "unknown",
                "pair": "-",
                "kind": "error",
                "book_status": "erro",
                "note": str(result),
            })
            continue
        if isinstance(result, list):
            markets.extend(result)
        elif isinstance(result, dict):
            markets.append(result)

    return {
        "ts": now_ts(),
        "amounts_prl": amounts,
        "markets": markets,
        "lookalikes": [],
        "notes": [
            "Somente Pearl Research: native PRL em CEXs provaveis e WPRL via PearlBridge.",
            "CEX spot usa bids do order book para simular venda.",
            "DEX/Uniswap nao tem book; a tela mostra liquidez/preco de pool e precisa de Quoter para execucao exata.",
        ],
    }


def is_terminal(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "").lower()
    return status in TERMINAL_STATUSES or status.startswith("terminated")


def matches_target(record: dict[str, Any], target: dict[str, Any]) -> bool:
    return (
        str(record.get("gpu_type") or "") == target["gpu_type"]
        and safe_int(record.get("gpu_count"), target["gpu_count"]) == target["gpu_count"]
        and str(record.get("offer_id") or "") == target["offer_id"]
        and str(record.get("provider") or "") == target["provider"]
        and str(record.get("region") or "") == target["region"]
        and str(record.get("instance_type") or "").upper() == target["instance_type"]
    )


def fixed_costs_by_worker() -> dict[str, dict[str, Any]]:
    data = load_json(FIXED_COSTS_PATH, {"items": []})
    items = data.get("items") if isinstance(data.get("items"), list) else []
    return {
        str(item.get("worker_name") or ""): item
        for item in items
        if isinstance(item, dict) and item.get("worker_name")
    }


def akoya_workers_by_name(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    workers = payload.get("workers") if isinstance(payload.get("workers"), list) else []
    return {
        str(worker.get("worker_name") or ""): worker
        for worker in workers
        if isinstance(worker, dict) and worker.get("worker_name")
    }


def record_total_usage_usd(record: dict[str, Any]) -> float:
    detail = record.get("failure_detail") if isinstance(record.get("failure_detail"), dict) else {}
    ui_card = record.get("ui_card") if isinstance(record.get("ui_card"), dict) else {}
    for source in (record, detail, ui_card):
        for key in ("total_usage_usd", "totalCost", "totalUsage", "totalUsageUsd", "total_cost_usd"):
            if source.get(key) not in (None, ""):
                return safe_float(source.get(key))
    return 0.0


def corrected_hourly_rate(record: dict[str, Any], cost_cfg: dict[str, Any], target: dict[str, Any]) -> float:
    record_rate = safe_float(record.get("hourly_rate"))
    fixed_rate = safe_float(cost_cfg.get("cost_usd_hr"))
    rate = record_rate if record_rate > 0 else fixed_rate
    target_rate = safe_float(target.get("default_hourly_rate_usd"))
    if matches_target(record, target) and target_rate > 0 and 0 < rate < target_rate * 0.75:
        return target_rate
    return rate


def parse_runtime_hours(value: Any) -> float:
    text = str(value or "").strip().lower()
    if not text:
        return 0.0
    parts = text.split()
    return safe_float(parts[0]) if parts else 0.0


def is_billable_running(
    record: dict[str, Any],
    target_match: bool,
    akoya_mining: bool = False,
) -> bool:
    return (
        target_match
        and not is_terminal(record)
        and (
            akoya_mining
            or (
                str(record.get("status") or "").lower() == "running"
                and str(record.get("ssh_status") or "").lower() == "succeeded"
            )
        )
    )


def deployment_group(
    record: dict[str, Any],
    target_match: bool,
    akoya_mining: bool = False,
) -> tuple[str, int]:
    status = str(record.get("status") or "").lower()
    ssh_status = str(record.get("ssh_status") or "").lower()
    bootstrap_status = str(record.get("bootstrap_status") or "").lower()
    phase = str(record.get("phase") or "").lower()
    succeeded = ssh_status == "succeeded" or bootstrap_status == "completed"
    terminal = is_terminal(record)

    if target_match and not terminal and (
        akoya_mining or (status == "running" and ssh_status == "succeeded")
    ):
        return "DEPLOYED", 0
    if target_match and succeeded:
        return "OFF OK", 1
    if target_match and not terminal and (
        status in {"deploying", "pending"}
        or ssh_status in {"ssh_pending", "pending", "deploying"}
        or bootstrap_status in {"pending", "running", "bootstrapping"}
        or phase in {"pending", "discovered", "bootstrapping"}
    ):
        return "DEPLOYING", 2
    return "FAILED", 3


def update_earnings_history(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    history = load_json(EARNINGS_PATH, {"workers": {}})
    workers = history.get("workers") if isinstance(history.get("workers"), dict) else {}
    now = now_ts()
    changed = False
    for row in rows:
        worker_key = str(row.get("worker") or row.get("short_id") or "")
        if not worker_key:
            continue
        item = workers.get(worker_key) if isinstance(workers.get(worker_key), dict) else {}
        earned = safe_float(item.get("earned_usd"))
        revenue_hr = safe_float(row.get("revenue_usd_hr"))
        last_sample = safe_float(item.get("last_sample_ts"), now)
        if revenue_hr > 0 and bool(row.get("akoya_connected")) and not bool(row.get("terminal")):
            elapsed = max(0.0, min(now - last_sample, 300.0))
            earned += revenue_hr * elapsed / 3600.0
        workers[worker_key] = {
            **item,
            "worker": row.get("worker"),
            "short_id": row.get("short_id"),
            "earned_usd": round(earned, 6),
            "last_sample_ts": now,
            "last_hashrate_ths": row.get("akoya_hashrate_ths"),
            "last_revenue_usd_hr": row.get("revenue_usd_hr"),
        }
        changed = True
    if changed:
        history["workers"] = workers
        history["updated_at"] = now
        save_json(EARNINGS_PATH, history)
    return workers


def deployment_rows(
    state: dict[str, Any],
    config: dict[str, Any],
    akoya: dict[str, Any],
    rates: dict[str, Any],
) -> list[dict[str, Any]]:
    target = TARGET_PRESETS[config["target_preset"]]
    costs = fixed_costs_by_worker()
    akoya_by_name = akoya_workers_by_name(akoya)
    history = load_json(EARNINGS_PATH, {"workers": {}})
    history_workers = history.get("workers") if isinstance(history.get("workers"), dict) else {}
    deployments = state.get("deployments") if isinstance(state.get("deployments"), dict) else {}
    rows: list[dict[str, Any]] = []
    for record in deployments.values():
        if not isinstance(record, dict):
            continue
        worker = str(record.get("worker") or "")
        akoya_worker = akoya_by_name.get(worker) or {}
        hashrate = safe_float(akoya_worker.get("hashrate_ths"))
        connected = bool(akoya_worker.get("is_connected"))
        akoya_mining = connected and hashrate > 0
        cost_cfg = costs.get(worker) or {}
        hourly_rate = corrected_hourly_rate(record, cost_cfg, target)
        total_usage = record_total_usage_usd(record)
        target_match = matches_target(record, target)
        billable_running = is_billable_running(record, target_match, akoya_mining)
        group, group_rank = deployment_group(record, target_match, akoya_mining)
        succeeded_once = group in {"DEPLOYED", "OFF OK"}
        billed_hours = total_usage / hourly_rate if target_match and total_usage > 0 and hourly_rate > 0 else 0.0
        if billable_running and billed_hours <= 0:
            billed_hours = parse_runtime_hours(record.get("ui_runtime"))
        cost_hr = hourly_rate if billable_running else 0.0
        revenue_hr = hashrate * safe_float(rates.get("usd_per_th_per_hour")) if connected and hashrate > 0 else 0.0
        history_key = worker or str(record.get("short_id") or str(record.get("id") or "")[:8])
        history_item = history_workers.get(history_key) if isinstance(history_workers.get(history_key), dict) else {}
        estimate_revenue_hr = revenue_hr if revenue_hr > 0 else safe_float(history_item.get("last_revenue_usd_hr"))
        revenue_day = revenue_hr * 24
        cost_day = cost_hr * 24 if cost_hr > 0 else 0.0
        profit_hr = revenue_hr - cost_hr if billable_running else None
        profit_day = revenue_day - cost_day if billable_running else None
        estimated_earned = estimate_revenue_hr * billed_hours if target_match and succeeded_once and billed_hours > 0 else 0.0
        estimated_profit = estimated_earned - total_usage if target_match and total_usage > 0 else 0.0
        row = {
            "id": record.get("id", ""),
            "short_id": record.get("short_id") or str(record.get("id") or "")[:8],
            "worker": worker,
            "target_match": target_match,
            "billable_running": billable_running,
            "deployment_group": group,
            "deployment_group_rank": group_rank,
            "created_by": record.get("created_by", ""),
            "status": record.get("status", ""),
            "phase": record.get("phase", ""),
            "ip_address": record.get("ip_address", ""),
            "ssh_status": record.get("ssh_status", ""),
            "bootstrap_status": record.get("bootstrap_status", ""),
            "pool_status": record.get("pool_status", ""),
            "gpu_type": record.get("gpu_type", ""),
            "gpu_count": safe_int(record.get("gpu_count"), 1),
            "provider": record.get("provider", ""),
            "region": record.get("region", ""),
            "hourly_rate": round(hourly_rate, 6) if hourly_rate else None,
            "billed_hours": round(billed_hours, 6) if billed_hours > 0 else 0.0,
            "total_usage_usd": round(total_usage, 6) if total_usage > 0 else 0.0,
            "cost_usd_hr": round(cost_hr, 6) if cost_hr > 0 else None,
            "cost_usd_day": round(cost_day, 6) if cost_day > 0 else None,
            "revenue_usd_hr": round(revenue_hr, 6) if revenue_hr > 0 else 0.0,
            "revenue_usd_day": round(revenue_day, 6) if revenue_day > 0 else 0.0,
            "estimate_revenue_usd_hr": round(estimate_revenue_hr, 6) if estimate_revenue_hr > 0 else 0.0,
            "profit_usd_hr": round(profit_hr, 6) if profit_hr is not None else None,
            "profit_usd_day": round(profit_day, 6) if profit_day is not None else None,
            "earned_usd": round(estimated_earned, 6),
            "total_profit_usd": round(estimated_profit, 6),
            "akoya_connected": connected,
            "akoya_hashrate_ths": round(hashrate, 4),
            "akoya_gpu_count": safe_int(akoya_worker.get("gpu_count"), 0),
            "akoya_last_seen_at": akoya_worker.get("last_seen_at"),
            "bad_hash_samples": safe_int(record.get("bad_hash_samples")),
            "low_hash_status": record.get("low_hash_status", ""),
            "low_hash_reason": record.get("low_hash_reason", ""),
            "destroy_pending": bool(record.get("destroy_pending")),
            "destroy_reason": record.get("destroy_reason", ""),
            "destroy_requested_at": record.get("destroy_requested_at"),
            "destroy_confirmed_at": record.get("destroy_confirmed_at"),
            "failure_reason": record.get("failure_reason") or record.get("last_error") or "",
            "last_error": record.get("last_error", ""),
            "updated_at": safe_float(record.get("updated_at")),
            "terminal": is_terminal(record),
        }
        rows.append(row)
    fallback_revenue_hr = 0.0
    live_revenue_rates = [
        safe_float(row.get("revenue_usd_hr"))
        for row in rows
        if row.get("target_match") and row.get("billable_running") and safe_float(row.get("revenue_usd_hr")) > 0
    ]
    if live_revenue_rates:
        fallback_revenue_hr = sum(live_revenue_rates) / len(live_revenue_rates)
    if fallback_revenue_hr > 0:
        for row in rows:
            if (
                row.get("target_match")
                and row.get("deployment_group") == "OFF OK"
                and safe_float(row.get("billed_hours")) > 0
                and safe_float(row.get("estimate_revenue_usd_hr")) <= 0
            ):
                estimated_earned = fallback_revenue_hr * safe_float(row.get("billed_hours"))
                total_usage = safe_float(row.get("total_usage_usd"))
                row["estimate_revenue_usd_hr"] = round(fallback_revenue_hr, 6)
                row["earned_usd"] = round(estimated_earned, 6)
                row["total_profit_usd"] = round(estimated_earned - total_usage, 6)
    rows.sort(
        key=lambda item: (
            safe_int(item.get("deployment_group_rank"), 99),
            -1 if bool(item.get("akoya_connected")) and safe_float(item.get("akoya_hashrate_ths")) > 0 else 0,
            -safe_float(item.get("updated_at")),
        )
    )
    return rows


def state_payload() -> dict[str, Any]:
    config = public_config()
    state = load_json(STATE_PATH, {})
    akoya = redis_payload(AKOYA_REDIS_KEY)
    pearl = redis_payload(PEARL_REDIS_KEY)
    rates = akoya_rates(pearl)
    rows = deployment_rows(state, config, akoya, rates)
    target_rows = [row for row in rows if row["target_match"]]
    active_rows = [row for row in target_rows if not row["terminal"]]
    billable_rows = [row for row in target_rows if row.get("billable_running")]
    usage_rows = [row for row in target_rows if safe_float(row.get("total_usage_usd")) > 0]
    terminal_rows = [row for row in target_rows if row["terminal"]]
    online_rows = [row for row in active_rows if row["akoya_connected"] and safe_float(row["akoya_hashrate_ths"]) > 0]
    online_gpu_count = sum(max(1, safe_int(row.get("akoya_gpu_count"), row.get("gpu_count") or 1)) for row in online_rows)
    total_hashrate = sum(safe_float(row.get("akoya_hashrate_ths")) for row in online_rows)
    total_cost_hr = sum(safe_float(row.get("cost_usd_hr")) for row in billable_rows)
    total_cost_day = total_cost_hr * 24
    total_revenue_hr = sum(safe_float(row.get("revenue_usd_hr")) for row in billable_rows)
    total_revenue_day = total_revenue_hr * 24
    total_profit_hr = total_revenue_hr - total_cost_hr
    total_profit_day = total_revenue_day - total_cost_day
    total_usage_usd = sum(safe_float(row.get("total_usage_usd")) for row in usage_rows)
    total_earned_usd = sum(safe_float(row.get("earned_usd")) for row in usage_rows)
    total_profit_usd = total_earned_usd - total_usage_usd
    cooldown_until = safe_float(state.get("cooldown_until"))
    cooldown_remaining = max(0, int(cooldown_until - now_ts()))
    active_slots_remaining = max(0, config["global_active_limit"] - len(active_rows))
    online_gap = max(0, config["desired_online_gpus"] - online_gpu_count)
    wait_reasons: list[str] = []
    if not config["create_enabled"]:
        wait_reasons.append("creates pausados")
    if cooldown_remaining:
        wait_reasons.append(f"cooldown {cooldown_remaining}s")
    if active_slots_remaining <= 0:
        wait_reasons.append("limite ativo cheio")
    if online_gap <= 0:
        wait_reasons.append("meta online atingida")
    return {
        "ts": now_ts(),
        "config": config,
        "state_path": str(STATE_PATH),
        "config_path": str(CONFIG_PATH),
        "summary": {
            "credits_balance": state.get("credits_balance"),
            "cooldown_remaining_seconds": cooldown_remaining,
            "online_gpu_count": online_gpu_count,
            "online_worker_count": len(online_rows),
            "active_target_count": len(active_rows),
            "terminal_target_count": len(terminal_rows),
            "ui_running_cards": safe_int(state.get("last_ui_scrape_running_cards")),
            "ui_running_unique": safe_int(state.get("last_ui_scrape_running_unique")),
            "ui_duplicate_short_ids": state.get("last_ui_scrape_duplicate_short_ids") or [],
            "all_spheron_count": len([row for row in rows if str(row.get("worker") or "").startswith("spheron-")]),
            "total_hashrate_ths": round(total_hashrate, 4),
            "total_cost_usd_hr": round(total_cost_hr, 6),
            "total_cost_usd_day": round(total_cost_day, 6),
            "total_revenue_usd_hr": round(total_revenue_hr, 6),
            "total_revenue_usd_day": round(total_revenue_day, 6),
            "total_profit_usd_hr": round(total_profit_hr, 6),
            "total_profit_usd_day": round(total_profit_day, 6),
            "total_usage_usd": round(total_usage_usd, 6),
            "total_earned_usd": round(total_earned_usd, 6),
            "total_profit_usd": round(total_profit_usd, 6),
            "active_slots_remaining": active_slots_remaining,
            "online_gap": online_gap,
            "wait_reason": "; ".join(wait_reasons) if wait_reasons else "criando quando offer aparecer",
            "last_error": state.get("last_error", ""),
            "last_ui_scrape_at": state.get("last_ui_scrape_at"),
        },
        "deployments": rows,
        "target_deployments": target_rows,
        "akoya": {
            "ok": bool(akoya),
            "worker_count": akoya.get("worker_count"),
            "online_worker_count": akoya.get("online_worker_count"),
            "total_hashrate_ths": akoya.get("total_hashrate_ths"),
            "server_time": akoya.get("server_time"),
        },
        "pearl": rates,
    }


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/books")
async def books_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "books.html")


@app.get("/safetrade-bridge")
async def safetrade_bridge_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "safetrade_bridge.html")


@app.get("/api/spheron/state")
async def api_state() -> dict[str, Any]:
    return state_payload()


@app.get("/api/books")
async def api_books(amounts: str | None = None) -> dict[str, Any]:
    return await pearl_books_payload(amounts)


@app.post("/api/safetrade/browser-cache")
async def api_safetrade_browser_cache(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return save_safetrade_browser_cache(payload)


@app.get("/api/safetrade/browser-cache")
async def api_safetrade_browser_cache_status() -> dict[str, Any]:
    payload = load_json(SAFETRADE_BOOK_CACHE_PATH)
    if not payload:
        return {
            "ok": False,
            "cache_path": str(SAFETRADE_BOOK_CACHE_PATH),
            "status": "missing",
        }
    bids = payload.get("bids") if isinstance(payload.get("bids"), list) else []
    asks = payload.get("asks") if isinstance(payload.get("asks"), list) else []
    age = now_ts() - safe_float(payload.get("ts"))
    return {
        "ok": True,
        "cache_path": str(SAFETRADE_BOOK_CACHE_PATH),
        "status": "fresh" if age <= safetrade_cache_ttl_seconds() else "stale",
        "age_seconds": round(age, 3),
        "market": payload.get("market"),
        "source": payload.get("source"),
        "sequence": payload.get("sequence"),
        "bids": len(bids),
        "asks": len(asks),
        "error": payload.get("error"),
    }


@app.post("/api/safetrade/browser-cache-form")
async def api_safetrade_browser_cache_form(request: Request) -> dict[str, Any]:
    body = (await request.body()).decode("utf-8", errors="replace")
    fields = parse_qs(body, keep_blank_values=True)
    raw_payload = fields.get("payload", [""])[0]
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid payload json: {exc}") from exc
    return save_safetrade_browser_cache(payload)


@app.get("/api/spheron/config")
async def api_config() -> dict[str, Any]:
    return {"config": public_config(), "path": str(CONFIG_PATH)}


@app.put("/api/spheron/config")
async def api_config_update(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")
    config = public_config()
    for key in DEFAULT_CONFIG:
        if key in payload:
            config[key] = payload[key]
    config = {**DEFAULT_CONFIG, **config}
    config["create_enabled"] = safe_bool(config.get("create_enabled"), True)
    config["target_preset"] = "h100-sxm5-1x"
    config["desired_online_gpus"] = max(0, safe_int(config.get("desired_online_gpus"), 10))
    config["global_active_limit"] = max(1, safe_int(config.get("global_active_limit"), 20))
    config["ssh_parallel"] = max(1, safe_int(config.get("ssh_parallel"), 10))
    config["create_interval_seconds"] = max(5, safe_int(config.get("create_interval_seconds"), 20))
    config["max_price_usd_hr"] = round(max(0.0, safe_float(config.get("max_price_usd_hr"), 1.8)), 6)
    config["low_credits_threshold"] = round(max(0.0, safe_float(config.get("low_credits_threshold"), 5)), 2)
    config["auto_destroy_bad_enabled"] = safe_bool(config.get("auto_destroy_bad_enabled"), True)
    config["bad_hash_min_ths"] = round(max(0.0, safe_float(config.get("bad_hash_min_ths"), 620)), 3)
    config["bad_hash_grace_seconds"] = max(0, safe_int(config.get("bad_hash_grace_seconds"), 1200))
    config["bad_hash_samples_required"] = max(1, safe_int(config.get("bad_hash_samples_required"), 3))
    save_json(CONFIG_PATH, config)
    return {"config": config, "state": state_payload()}
