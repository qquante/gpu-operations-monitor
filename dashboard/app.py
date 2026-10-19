import asyncio
import json
import os
import time
from uuid import uuid4
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import redis.asyncio as aioredis
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import sys

sys.path.insert(0, "/app")

from state_store import archive_json, load_json_dict, load_json_list, load_raw_monitor_state, redis_get_json, redis_set_json, save_json
import scout_settings as scout_config
import scout_history as scout_records
import vast_service as vast
import clore_service as clore
from shared.gpu_hashrates import get_gpu, normalize_gpu_name


REDIS_KEYS = (
    "monitor:pearl",
    "monitor:akoya",
    "monitor:alphamine",
    "monitor:clore",
    "monitor:vastai",
    "monitor:runpod",
    "monitor:tensordock",
)
VAST_ACTIONS_KEY = "dashboard:vast:actions"
CLORE_ACTIONS_KEY = "dashboard:clore:actions"
SCOUT_STATE_KEY = "dashboard:scout:state"
RESULTS_STATE_KEY = "dashboard:results:state"
PEARL_LAST_GOOD_KEY = "dashboard:pearl:last_good"
VAST_BLACKLIST_PATH = Path(os.getenv("VAST_BLACKLIST_PATH", "data/vast_blacklist.json"))
SCOUT_HISTORY_PATH = Path(os.getenv("SCOUT_HISTORY_PATH", "data/scout_history.json"))
SCOUT_MACHINE_INDEX_PATH = Path(os.getenv("SCOUT_MACHINE_INDEX_PATH", "data/scout_machine_index.json"))
WORKER_HISTORY_PATH = Path(os.getenv("WORKER_HISTORY_PATH", "data/worker_history.json"))
FIXED_WORKER_COSTS_PATH = Path(os.getenv("FIXED_WORKER_COSTS_PATH", "data/fixed_worker_costs.json"))
REDIS_TTL_SECONDS = 30
PEARL_FALLBACK_TTL_SECONDS = max(
    REDIS_TTL_SECONDS,
    int(os.getenv("PEARL_FALLBACK_TTL_SECONDS") or "900"),
)
STATE_CACHE_MAX_AGE_SECONDS = int(os.getenv("STATE_CACHE_MAX_AGE_SECONDS") or "15")
WORKER_HISTORY_INTERVAL_SECONDS = int(os.getenv("WORKER_HISTORY_INTERVAL_SECONDS") or "60")
WORKER_HISTORY_RETENTION_SAMPLES = int(os.getenv("WORKER_HISTORY_RETENTION_SAMPLES") or "1440")
GREEN_MIN_PROFIT_DAY = float(os.getenv("VAST_MIN_PROFIT_DAY") or "3")
GREEN_MIN_ROI_PCT = float(os.getenv("VAST_MIN_ROI_PCT") or "20")
VAST_MAX_ACTIVE_RENTS = int(os.getenv("VAST_MAX_ACTIVE_RENTS") or "1")
VAST_AUTORENT_MODE = os.getenv("VAST_AUTORENT_MODE", "confirm")
CLORE_AUTORENT_MODE = os.getenv("CLORE_AUTORENT_MODE", "confirm")
SCOUT_TEST_SECONDS = int(os.getenv("SCOUT_TEST_SECONDS") or "1800")
SCOUT_WORKER_TIMEOUT_SECONDS = int(os.getenv("SCOUT_WORKER_TIMEOUT_SECONDS") or "900")
SCOUT_OFFLINE_TIMEOUT_SECONDS = int(os.getenv("SCOUT_OFFLINE_TIMEOUT_SECONDS") or "480")
SCOUT_ZERO_HASH_TIMEOUT_SECONDS = int(os.getenv("SCOUT_ZERO_HASH_TIMEOUT_SECONDS") or "300")
SCOUT_MIN_PROFIT_USD_HR = float(os.getenv("SCOUT_MIN_PROFIT_USD_HR") or "0.20")
SCOUT_MIN_HASH_RATIO = float(os.getenv("SCOUT_MIN_HASH_RATIO") or "0.45")
SCOUT_MAX_PARALLEL_TESTS = int(os.getenv("SCOUT_MAX_PARALLEL_TESTS") or "10")
SCOUT_WORKER_INTERVAL_SECONDS = int(os.getenv("SCOUT_WORKER_INTERVAL_SECONDS") or "20")
SCOUT_SAMPLE_INTERVAL_SECONDS = max(10, int(os.getenv("SCOUT_SAMPLE_INTERVAL_SECONDS") or "60"))
SCOUT_STARTS_PER_TICK = int(os.getenv("SCOUT_STARTS_PER_TICK") or "1")
SCOUT_MAX_PRICE_USD_HR = float(os.getenv("SCOUT_MAX_PRICE_USD_HR") or "3.00")
SCOUT_TRANSIENT_RETRY_SECONDS = int(os.getenv("SCOUT_TRANSIENT_RETRY_SECONDS") or "60")
SCOUT_TRANSIENT_RETRY_WINDOW_SECONDS = int(os.getenv("SCOUT_TRANSIENT_RETRY_WINDOW_SECONDS") or "900")
SCOUT_RADAR_RETENTION_SECONDS = int(os.getenv("SCOUT_RADAR_RETENTION_SECONDS") or "1800")
RESULTS_RETRY_SECONDS = int(os.getenv("RESULTS_RETRY_SECONDS") or "300")
VAST_INSTANCE_DETAIL_SYNC_INTERVAL_SECONDS = int(os.getenv("VAST_INSTANCE_DETAIL_SYNC_INTERVAL_SECONDS") or "180")
VAST_OFFLINE_RESCUE_ENABLED = os.getenv("VAST_OFFLINE_RESCUE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
VAST_OFFLINE_RESCUE_INTERVAL_SECONDS = max(60, int(os.getenv("VAST_OFFLINE_RESCUE_INTERVAL_SECONDS") or "180"))
VAST_OFFLINE_RESCUE_REGRAB_ENABLED = os.getenv("VAST_OFFLINE_RESCUE_REGRAB_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
CLORE_ORDER_SYNC_INTERVAL_SECONDS = max(10, int(os.getenv("CLORE_ORDER_SYNC_INTERVAL_SECONDS") or "60"))
CLORE_RERENT_APPROVED_ENABLED = os.getenv("CLORE_RERENT_APPROVED_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
CLORE_RERENT_INTERVAL_SECONDS = max(60, int(os.getenv("CLORE_RERENT_INTERVAL_SECONDS") or "180"))
SCOUT_CLORE_AUTO_AB_ENABLED = os.getenv("SCOUT_CLORE_AUTO_AB_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
CLORE_AUTO_COOLDOWN_SECONDS = max(60, int(os.getenv("CLORE_AUTO_COOLDOWN_SECONDS") or "300"))
CLORE_AUTO_QUEUE_RETENTION_SECONDS = max(
    CLORE_AUTO_COOLDOWN_SECONDS,
    int(os.getenv("CLORE_AUTO_QUEUE_RETENTION_SECONDS") or "1800"),
)
SCOUT_POOL_SWITCH_MODE = os.getenv("SCOUT_POOL_SWITCH_MODE", "in_place_ab").strip().lower()
SCOUT_POOL_SWITCH_MODES = {"single_pool", "recreate", "in_place_ab"}
SCOUT_POOL_ORDER = ("akoya", "alphamine")
CLORE_MANUAL_RENT_DECISIONS = {"green", "yellow", "alert"}
SCOUT_HARDWARE_BLOCK_RISKS = {"cuda_below_12_9", "cuda_unknown", "pcie_below_rule", "pcie_unknown"}
CLORE_AUTO_BLOCK_RISKS = {"reliability_low", "network_bad", "price_usd_missing", *SCOUT_HARDWARE_BLOCK_RISKS}
CLORE_AUTO_BAD_HISTORY_DECISIONS = {
    "blacklist",
    "blacklisted",
    "destroy",
    "destroyed",
    "failed",
    "no_worker",
    "offline",
    "order_lost",
    "runtime_error",
    "stopped",
    "switch_failed_destroy",
}
SCOUT_HARDWARE_REQUIREMENT = "CUDA 12.9+ e PCIe x8/x16"
SCOUT_ALLOWED_GPU_MODELS = tuple(
    normalize_gpu_name(item)
    for item in (os.getenv("SCOUT_ALLOWED_GPU_MODELS") or "H100 SXM").split(",")
    if normalize_gpu_name(item)
)
RESULTS_WATCH_HOST_ID = os.getenv("RESULTS_WATCH_HOST_ID", "445596").strip()
VAST_API_BASE_URL = "https://console.vast.ai"
VAST_BUNDLES_URL = f"{VAST_API_BASE_URL}/api/v0/bundles/"
VAST_SEARCH_BASE_URL = "https://cloud.vast.ai/create/"
CLORE_SEARCH_BASE_URL = "https://clore.ai/marketplace"
RUNPOD_CONSOLE_BASE_URL = "https://console.runpod.io/deploy"
TENSORDOCK_CONSOLE_BASE_URL = "https://dashboard.tensordock.com/deploy/gpu"
VAST_SEARCH_BASE_PARAMS = {
    "instanceDiskSizeMin": os.getenv("VAST_INSTANCE_DISK_GB", "8"),
    "instanceDurationMin": "94610000.00000021",
    "rentalType": "onDemand",
    "isAvxSupported": "false",
    "isHostSecure": "false",
    "isMachineIpStatic": "false",
    "isOfferAvailable": "true",
    "isOfferCompatible": "true",
    "isOfferVerified": "false",
    "isQueryInverted": "false",
    "machineReliabilityMin": "0.6604044743550609",
    "versionCudaMin": "12.9",
    "sorts": "priceInstanceHourly-asc,offerTflops-asc",
    "pageSize": "320",
}
VAST_GPU_SLUGS = {
    "RTX 5090": "rtx5090",
    "RTX 5080": "rtx5080",
    "RTX 5070 Ti": "rtx5070Ti",
    "RTX 5070": "rtx5070",
    "RTX 4090": "rtx4090",
    "RTX 4090 D": "rtx4090D",
    "RTX 4080 SUPER": "rtx4080Super",
    "RTX 4080": "rtx4080",
    "RTX 4070 Ti SUPER": "rtx4070TiSuper",
    "RTX 4070 Ti": "rtx4070Ti",
    "RTX 4070 SUPER": "rtx4070Super",
    "RTX 4070": "rtx4070",
    "RTX 4060 Ti": "rtx4060Ti",
    "RTX 4060": "rtx4060",
    "RTX 3090 Ti": "rtx3090Ti",
    "RTX 3090": "rtx3090",
    "RTX 3080 Ti": "rtx3080Ti",
    "RTX 3080": "rtx3080",
    "RTX 3070 Ti": "rtx3070Ti",
    "RTX 3070": "rtx3070",
    "RTX 3060 Ti": "rtx3060Ti",
    "RTX 3060": "rtx3060",
    "RTX A6000": "rtxA6000",
    "RTX A5000": "rtxA5000",
    "RTX A4500": "rtxA4500",
    "RTX A4000": "rtxA4000",
    "H100 SXM": "h100Sxm",
    "H100 PCIe": "h100Pcie",
    "H100": "h100Sxm",
    "H200": "h200",
}

HARDCODED_WORKER_COSTS = {
    "runpod01": {
        "provider": "RunPod",
        "cost_usd_hr": 3.29,
        "cost_source": "hardcoded",
        "future_source": "monitor:runpod",
    }
}


app = FastAPI(title="Pearl GPU Monitor Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")

redis_client: aioredis.Redis | None = None
vast_actions_lock = asyncio.Lock()
clients: set[WebSocket] = set()
latest_state: dict[str, Any] = {}
latest_actions: dict[str, Any] = {}
latest_clore_actions: dict[str, Any] = {}
latest_clore_wallets: dict[str, Any] = {}
latest_blacklist: dict[str, Any] = {"items": []}
latest_scout: dict[str, Any] = {}
latest_pearl_payload: dict[str, Any] = {}
last_vast_instance_detail_sync_at = time.time()
last_clore_order_sync_at = 0.0
last_clore_wallet_sync_at = 0.0


def now_ts() -> float:
    return time.time()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def parse_cuda(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.split()[0])
    except (ValueError, TypeError):
        return None


def scout_hardware_block_reason(item: dict[str, Any] | None) -> str:
    risks = set((item or {}).get("risks") or [])
    blocked = risks.intersection(SCOUT_HARDWARE_BLOCK_RISKS)
    if not blocked:
        return ""
    labels = {
        "cuda_below_12_9": "cuda abaixo de 12.9",
        "cuda_unknown": "cuda desconhecido",
        "pcie_below_rule": "pcie abaixo de x8",
        "pcie_unknown": "pcie desconhecido",
    }
    details = ", ".join(labels.get(risk, risk) for risk in sorted(blocked))
    return f"Filtro Scout: exige {SCOUT_HARDWARE_REQUIREMENT} ({details})"


def load_fixed_worker_costs() -> dict[str, dict[str, Any]]:
    data = load_json_dict(FIXED_WORKER_COSTS_PATH, {"items": []})
    raw_items: list[dict[str, Any]] = []
    if isinstance(data.get("items"), list):
        raw_items = [item for item in data.get("items", []) if isinstance(item, dict)]
    else:
        raw_items = [
            dict(value, worker_name=key)
            for key, value in data.items()
            if isinstance(value, dict)
        ]
    costs: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        worker_name = str(item.get("worker_name") or item.get("name") or "").strip()
        cost_hr = safe_float(item.get("cost_usd_hr"), -1)
        if not worker_name or cost_hr <= 0:
            continue
        costs[worker_name] = {
            "worker_name": worker_name,
            "provider": str(item.get("provider") or "Fixo").strip() or "Fixo",
            "cost_usd_hr": round_money(cost_hr),
            "enabled": bool(item.get("enabled", True)),
            "note": str(item.get("note") or "").strip(),
            "created_at": safe_float(item.get("created_at")) or now_ts(),
            "updated_at": safe_float(item.get("updated_at")) or now_ts(),
        }
    return costs


def save_fixed_worker_costs(costs: dict[str, dict[str, Any]]) -> None:
    items = sorted(
        [item for item in costs.values() if isinstance(item, dict)],
        key=lambda item: str(item.get("worker_name") or "").lower(),
    )
    save_json(FIXED_WORKER_COSTS_PATH, {"items": items}, indent=2)


def public_fixed_worker_cost(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "worker_name": item.get("worker_name", ""),
        "provider": item.get("provider", ""),
        "cost_usd_hr": round_money(safe_float(item.get("cost_usd_hr"))),
        "enabled": bool(item.get("enabled", True)),
        "note": item.get("note", ""),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def fixed_worker_cost_payload(payload: dict[str, Any], worker_name_override: str | None = None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    worker_name = str(worker_name_override or payload.get("worker_name") or "").strip()
    if not worker_name:
        raise HTTPException(status_code=400, detail="Worker obrigatorio")
    cost_hr = safe_float(payload.get("cost_usd_hr"), -1)
    if cost_hr <= 0:
        raise HTTPException(status_code=400, detail="Custo/h precisa ser maior que zero")
    current = now_ts()
    return {
        "worker_name": worker_name,
        "provider": str(payload.get("provider") or existing.get("provider") or "Fixo").strip() or "Fixo",
        "cost_usd_hr": round_money(cost_hr),
        "enabled": bool(payload.get("enabled", existing.get("enabled", True))),
        "note": str(payload.get("note") or existing.get("note") or "").strip(),
        "created_at": existing.get("created_at") or current,
        "updated_at": current,
    }


def fixed_worker_cost_config(costs: dict[str, dict[str, Any]], worker_name: Any, base_worker_name: Any = "") -> dict[str, Any] | None:
    for key in (str(worker_name or "").strip(), str(base_worker_name or "").strip()):
        if not key:
            continue
        item = costs.get(key)
        if not item or not bool(item.get("enabled", True)):
            continue
        cost_hr = safe_float(item.get("cost_usd_hr"))
        if cost_hr <= 0:
            continue
        return {
            "provider": item.get("provider") or "Fixo",
            "cost_usd_hr": cost_hr,
            "cost_source": "fixed_config",
            "future_source": str(FIXED_WORKER_COSTS_PATH),
            "note": item.get("note", ""),
        }
    return None


def decision_opportunity_visible(item: dict[str, Any] | None) -> bool:
    risks = set((item or {}).get("risks") or [])
    return not risks.intersection(SCOUT_HARDWARE_BLOCK_RISKS)


def opportunity_decision_label(value: Any) -> str:
    return {
        "green": "ALUGAR",
        "yellow": "MARGEM",
        "alert": "RISCO",
        "red": "NAO",
        "gray": "SEM CALC",
    }.get(str(value or ""), str(value or "-"))


def round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def vast_api_key() -> str:
    return vast.api_key()


def vast_template_hash_id() -> str:
    return vast.template_hash_id()


def vast_template_hash_id_for(strategy: str) -> str:
    return vast.template_hash_id_for(strategy)


def vast_image_for_strategy(strategy: str) -> str:
    return vast.image_for_strategy(strategy)


def vast_args_for_strategy(strategy: str) -> str:
    return vast.args_for_strategy(strategy)


def vast_onstart_for_strategy(strategy: str) -> str:
    return vast.onstart_for_strategy(strategy)


def akoya_wallet() -> str:
    return vast.akoya_wallet()


def alphamine_wallet() -> str:
    return vast.alphamine_wallet()


def wallet_for_strategy(strategy: str) -> str:
    return vast.wallet_for_strategy(strategy)


def vast_pool_strategies() -> tuple[str, ...]:
    return vast.pool_strategies()


def strategy_label(strategy: str) -> str:
    return vast.strategy_label(strategy)


def strategy_worker_name(strategy: str, item_id: Any) -> str:
    return vast.strategy_worker_name(strategy, item_id)


def alphamine_difficulty_for_gpu(gpu_name: Any) -> str:
    return vast.alphamine_difficulty_for_gpu(gpu_name)


def vast_headers() -> dict[str, str]:
    return vast.headers()


def green_max_price_usd_hr(revenue_hr: float | None) -> float | None:
    if revenue_hr is None or revenue_hr <= 0:
        return None
    roi_limited = revenue_hr / (1 + GREEN_MIN_ROI_PCT / 100)
    profit_limited = revenue_hr - (GREEN_MIN_PROFIT_DAY / 24)
    return round_money(max(0.0, min(roi_limited, profit_limited)))


def active_vast_rent_count(actions: dict[str, Any]) -> int:
    return sum(
        1
        for action in actions.values()
        if isinstance(action, dict) and action.get("state") in {"renting", "rented"}
    )


def vast_status_is_error(status_msg: Any, actual_status: Any = "") -> bool:
    text = str(status_msg or "").strip().lower()
    if not text:
        return False
    if text.startswith("success"):
        return False
    error_markers = (
        "error response",
        "failed to",
        "unknown flag",
        "oci runtime",
        "unresolvable cdi",
        "no such",
        "cannot",
    )
    return any(marker in text for marker in error_markers)


def scout_defaults() -> dict[str, Any]:
    return scout_config.defaults()


def scout_settings(scout: dict[str, Any] | None = None) -> dict[str, Any]:
    return scout_config.settings(scout)


def normalize_trigger_gpu(value: Any) -> str:
    return scout_config.normalize_trigger_gpu(value)


def scout_allowed_gpu_models(settings: dict[str, Any] | None = None) -> list[str]:
    return scout_config.allowed_gpu_models(settings)


def scout_allowlist_reason(settings: dict[str, Any] | None = None) -> str:
    return scout_config.allowlist_reason(settings)


def scout_gpu_allowed(item: dict[str, Any], settings: dict[str, Any] | None = None) -> bool:
    return scout_config.gpu_allowed(item, settings)


def results_manual_allowlist_bypass(item: dict[str, Any] | None) -> bool:
    return scout_config.results_manual_allowlist_bypass(item)


def scout_gpu_allowlist_block_reason(item: dict[str, Any], settings: dict[str, Any] | None = None) -> str:
    return scout_config.gpu_allowlist_block_reason(item, settings)


def scout_mark_allowlist_blocked(item: dict[str, Any], settings: dict[str, Any]) -> bool:
    return scout_config.mark_allowlist_blocked(item, settings)


def scout_vast_gpu_triggers(scout: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    raw = (scout or {}).get("vast_gpu_triggers") if isinstance(scout, dict) else []
    if not isinstance(raw, list):
        return []
    triggers: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        gpu_match = normalize_trigger_gpu(item.get("gpu_match") or item.get("gpu"))
        if not gpu_match:
            continue
        trigger_id = str(item.get("id") or "").strip() or f"vast-gpu-{uuid4().hex[:8]}"
        ignore_ask_ids = item.get("ignore_ask_ids")
        trigger = {
            "id": trigger_id,
            "enabled": bool(item.get("enabled", True)),
            "name": str(item.get("name") or f"Comprar {gpu_match}").strip(),
            "platform": "vastai",
            "gpu_match": gpu_match,
            "gpu_match_normalized": gpu_match,
            "gpu_count": max(1, safe_int(item.get("gpu_count"), 1)),
            "max_price_usd_hr": round_money(max(0.01, safe_float(item.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR))),
            "send_to_scout": True,
            "created_at": safe_float(item.get("created_at")) or now_ts(),
            "updated_at": safe_float(item.get("updated_at")) or safe_float(item.get("created_at")) or now_ts(),
            "ignore_ask_ids": [str(ask) for ask in ignore_ask_ids] if isinstance(ignore_ask_ids, list) else [],
        }
        triggers.append(trigger)
    return triggers


def public_vast_gpu_trigger(trigger: dict[str, Any], queue: dict[str, Any] | None = None) -> dict[str, Any]:
    items = [
        item
        for item in (queue or {}).values()
        if isinstance(item, dict) and item.get("source") == "trigger" and item.get("trigger_id") == trigger.get("id")
    ]
    latest = max(items, key=lambda item: safe_float(item.get("last_seen_at")), default={})
    return {
        "id": trigger.get("id"),
        "enabled": bool(trigger.get("enabled")),
        "name": trigger.get("name"),
        "platform": "vastai",
        "gpu_match": trigger.get("gpu_match"),
        "gpu_count": trigger.get("gpu_count"),
        "max_price_usd_hr": trigger.get("max_price_usd_hr"),
        "send_to_scout": True,
        "created_at": trigger.get("created_at"),
        "updated_at": trigger.get("updated_at"),
        "ignored_current_asks": len(trigger.get("ignore_ask_ids") or []),
        "recent_matches": len(items),
        "last_seen_at": latest.get("last_seen_at"),
        "last_attempt_at": latest.get("last_retry_at") or latest.get("sniped_at"),
        "last_status": latest.get("sniper_status") or latest.get("queue_status") or "",
    }


def normalize_vast_gpu_trigger_payload(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    current = now_ts()
    base = existing or {}
    gpu_match = normalize_trigger_gpu(payload.get("gpu_match") or payload.get("gpu") or base.get("gpu_match") or "H100 SXM")
    if not gpu_match:
        raise HTTPException(status_code=400, detail="GPU do trigger ausente")
    trigger_id = str(base.get("id") or payload.get("id") or f"vast-gpu-{uuid4().hex[:8]}").strip()
    trigger = {
        "id": trigger_id,
        "enabled": bool(payload.get("enabled", base.get("enabled", True))),
        "name": str(payload.get("name") or base.get("name") or f"Comprar {gpu_match}").strip(),
        "platform": "vastai",
        "gpu_match": gpu_match,
        "gpu_match_normalized": gpu_match,
        "gpu_count": max(1, safe_int(payload.get("gpu_count", base.get("gpu_count", 1)), 1)),
        "max_price_usd_hr": round_money(max(0.01, safe_float(payload.get("max_price_usd_hr", base.get("max_price_usd_hr", SCOUT_MAX_PRICE_USD_HR)), SCOUT_MAX_PRICE_USD_HR))),
        "send_to_scout": True,
        "created_at": safe_float(base.get("created_at")) or current,
        "updated_at": current,
        "ignore_ask_ids": [str(ask) for ask in base.get("ignore_ask_ids", [])] if isinstance(base.get("ignore_ask_ids"), list) else [],
    }
    return trigger


def vast_gpu_trigger_ignore_asks(state: dict[str, Any], trigger: dict[str, Any]) -> list[str]:
    ignored: list[str] = []
    wanted_gpu = normalize_trigger_gpu(trigger.get("gpu_match"))
    wanted_count = max(1, safe_int(trigger.get("gpu_count"), 1))
    for opportunity in state.get("opportunities", []):
        if opportunity.get("platform") != "vastai":
            continue
        if normalize_trigger_gpu(opportunity.get("gpu")) != wanted_gpu:
            continue
        if safe_int(opportunity.get("gpu_count"), 1) != wanted_count:
            continue
        ask_id = str(opportunity.get("id") or "")
        if ask_id:
            ignored.append(ask_id)
    return ignored


def scout_history_items() -> list[dict[str, Any]]:
    return scout_records.history_items()


def save_scout_history(items: list[dict[str, Any]]) -> None:
    scout_records.save_history(items)


def archive_scout_history(items: list[dict[str, Any]] | None = None) -> str:
    return scout_records.archive_history(items)


def archive_vast_actions(actions: dict[str, Any]) -> str:
    return archive_json(SCOUT_HISTORY_PATH.parent, "vast_actions", actions)


def append_scout_history(result: dict[str, Any]) -> None:
    scout_records.append_history(result)


def scout_machine_key(machine_id: Any, host_id: Any, gpu: Any, gpu_count: Any) -> str:
    return scout_records.machine_key(machine_id, host_id, gpu, gpu_count)


def scout_machine_key_from_item(item: dict[str, Any]) -> str:
    return scout_records.machine_key_from_item(item)


def scout_same_hardware(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    return scout_records.same_hardware(left, right)


def scout_machine_index_payload() -> dict[str, Any]:
    return scout_records.machine_index_payload()


def scout_machine_index_items() -> dict[str, Any]:
    return scout_records.machine_index_items()


def save_scout_machine_index(items: dict[str, Any], baseline_at: float | None = None) -> None:
    scout_records.save_machine_index(items, baseline_at)


def touch_scout_machine_index(
    index: dict[str, Any],
    item: dict[str, Any],
    status: str,
    *,
    result: dict[str, Any] | None = None,
) -> tuple[bool, bool, dict[str, Any]]:
    return scout_records.touch_machine_index(index, item, status, result=result)


def public_scout_test(test: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "test_id",
        "parent_test_id",
        "provider",
        "offer_id",
        "ask_id",
        "server_id",
        "order_id",
        "currency",
        "image",
        "status",
        "decision",
        "reason",
        "pool_strategy",
        "next_pool_strategy",
        "worker_name",
        "instance_id",
        "host_id",
        "machine_id",
        "vast_cur_state",
        "vast_actual_status",
        "vast_status_msg",
        "vast_pool_strategy_actual",
        "gpu",
        "gpu_count",
        "price_usd_hr",
        "max_price_usd_hr",
        "expected_ths",
        "started_at",
        "stage_deadline_at",
        "test_seconds",
        "worker_seen_at",
        "last_worker_seen_at",
        "zero_hash_started_at",
        "zero_hash_elapsed_s",
        "zero_hash_pool_failures",
        "failure_tag",
        "elapsed_s",
        "remaining_s",
        "latest_hashrate_ths",
        "latest_profit_usd_hr",
        "latest_hash_ratio",
        "prior_results",
        "switch_started_at",
        "switch_attempts",
        "switch_target_pool",
        "switch_error",
        "return_target_pool",
        "next_action",
        "manual_next_pool_strategy",
        "source",
        "source_label",
        "auto_decision",
        "auto_decision_label",
        "auto_log",
        "trigger_id",
        "trigger_name",
        "trigger_max_price_usd_hr",
        "opportunity_decision",
        "risks",
        "pcie",
        "cuda",
        "reliability",
        "net_up_mbps",
        "net_down_mbps",
    )
    return {key: test.get(key) for key in keys if key in test}


def public_scout_history(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "test_id",
        "provider",
        "offer_id",
        "ask_id",
        "server_id",
        "order_id",
        "currency",
        "image",
        "instance_id",
        "worker_name",
        "host_id",
        "machine_id",
        "gpu",
        "gpu_count",
        "pool_strategy",
        "price_usd_hr",
        "expected_ths",
        "vast_cur_state",
        "vast_actual_status",
        "vast_status_msg",
        "started_at",
        "worker_seen_at",
        "ended_at",
        "live_ths_avg",
        "live_ths_best",
        "hash_ratio",
        "revenue_usd_hr",
        "profit_usd_hr",
        "prior_results",
        "retest_allowed",
        "retest_reason",
        "previous_result_summary",
        "improvement_summary",
        "queue_priority_score",
        "source",
        "source_label",
        "auto_decision",
        "auto_decision_label",
        "auto_log",
        "trigger_id",
        "trigger_name",
        "trigger_max_price_usd_hr",
        "opportunity_decision",
        "risks",
        "failure_tag",
        "manual_next_pool_strategy",
        "pcie",
        "cuda",
        "reliability",
        "net_up_mbps",
        "net_down_mbps",
        "decision",
        "reason",
    )
    return {key: item.get(key) for key in keys if key in item}


def scout_runtime_error(action: dict[str, Any] | None) -> bool:
    if not action:
        return False
    return vast_status_is_error(action.get("vast_status_msg"), action.get("vast_actual_status"))


def scout_gpu_rank(gpu_name: Any) -> int:
    text = str(gpu_name or "").upper()
    order = (
        ("3060", 10),
        ("3070", 20),
        ("3080", 30),
        ("3090", 40),
        ("4070", 50),
        ("4080", 60),
        ("4090", 70),
        ("5070", 80),
        ("5080", 90),
        ("5090", 100),
        ("A4000", 110),
        ("A5000", 120),
        ("A6000", 130),
        ("A100", 140),
        ("H100", 150),
        ("H200", 160),
    )
    return next((rank for marker, rank in order if marker in text), 999)


def scout_candidate_allowed(opportunity: dict[str, Any], settings: dict[str, Any]) -> bool:
    if opportunity.get("platform") != "vastai":
        return False
    if not scout_gpu_allowed(opportunity, settings):
        return False
    if opportunity.get("decision") not in {"green", "yellow"}:
        return False
    price_hr = safe_float(opportunity.get("price_usd_hr"))
    if price_hr <= 0 or price_hr > safe_float(settings.get("max_price_usd_hr")):
        return False
    profit_hr = safe_float(opportunity.get("profit_usd_hr"), -999999)
    if profit_hr <= 0:
        return False
    risks = set(opportunity.get("risks") or [])
    severe = {
        "low_value_gpu",
        "price_usd_missing",
        "network_bad",
        "clore_cache_risk",
        *SCOUT_HARDWARE_BLOCK_RISKS,
    }
    return not severe.intersection(risks)


def base_vast_worker_name(worker_name: Any) -> str:
    name = str(worker_name or "")
    if not name.startswith("vast-"):
        return name
    return name.split(".gpu", 1)[0]


def vast_worker_gpu_suffix(worker_name: Any) -> str:
    name = str(worker_name or "")
    if ".gpu" not in name:
        return ""
    return f"gpu{name.split('.gpu', 1)[1]}"


def worker_history_key(worker: dict[str, Any]) -> str:
    instance_id = worker.get("vast_instance_id") or "no-instance"
    pool = worker.get("pool") or "unknown"
    worker_name = base_vast_worker_name(worker.get("worker_name"))
    return f"{instance_id}:{pool}:{worker_name}"


def worker_history_sample(worker: dict[str, Any], ts: float) -> dict[str, Any]:
    return {
        "ts": round(ts, 3),
        "ask_id": worker.get("ask_id"),
        "instance_id": worker.get("vast_instance_id"),
        "worker_name": base_vast_worker_name(worker.get("worker_name")),
        "pool": worker.get("pool"),
        "gpu": worker.get("gpu"),
        "gpu_count": worker.get("gpu_count"),
        "hashrate_ths": worker.get("hashrate_ths"),
        "hashrate_live_ths": worker.get("hashrate_live_ths"),
        "hashrate_1h_ths": worker.get("hashrate_1h_ths"),
        "hashrate_24h_ths": worker.get("hashrate_24h_ths"),
        "profit_usd_hr": worker.get("profit_usd_hr"),
        "revenue_usd_hr": worker.get("revenue_usd_hr"),
        "cost_usd_hr": worker.get("cost_usd_hr"),
        "is_connected": bool(worker.get("is_connected")),
    }


def record_worker_history(operation: dict[str, Any]) -> None:
    workers = [item for item in operation.get("workers", []) if isinstance(item, dict)]
    if not workers:
        return
    current = now_ts()
    history = load_json_dict(WORKER_HISTORY_PATH, {"workers": {}})
    groups = history.get("workers")
    if not isinstance(groups, dict):
        groups = {}
    changed = False
    interval = max(1, WORKER_HISTORY_INTERVAL_SECONDS)
    retention = max(10, WORKER_HISTORY_RETENTION_SAMPLES)
    for worker in workers:
        key = worker_history_key(worker)
        group = groups.get(key) if isinstance(groups.get(key), dict) else {}
        samples = group.get("samples") if isinstance(group.get("samples"), list) else []
        last_ts = safe_float(samples[-1].get("ts")) if samples and isinstance(samples[-1], dict) else 0.0
        if last_ts and current - last_ts < interval:
            continue
        samples.append(worker_history_sample(worker, current))
        group["samples"] = samples[-retention:]
        group["updated_at"] = current
        groups[key] = group
        changed = True
    if changed:
        history["workers"] = groups
        history["updated_at"] = current
        save_json(WORKER_HISTORY_PATH, history, indent=None)


def pool_switch_status(before_hash: float, before_profit: float | None, current_hash: float | None, current_profit: float | None) -> str:
    if current_hash is None:
        return "aguardando"
    if before_hash <= 0 and before_profit is None:
        return "sem dados"
    if before_profit is not None and current_profit is not None:
        return "melhorou" if current_profit >= before_profit else "piorou"
    if before_hash > 0:
        return "melhorou" if current_hash >= before_hash else "piorou"
    return "sem dados"


def pool_switch_status_class(status: str) -> str:
    if status == "melhorou":
        return "green"
    if status == "piorou":
        return "red"
    if status == "aguardando":
        return "yellow"
    return "gray"


def vast_action_summary(actions: dict[str, Any], operation: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = {"ready": 0, "renting": 0, "rented": 0, "active": 0, "failed": 0, "archived": 0, "instance_error": 0}
    workers: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for worker_item in (operation or {}).get("workers", []):
        worker_name = str(worker_item.get("worker_name") or "")
        base_name = base_vast_worker_name(worker_name)
        pool = worker_item.get("pool")
        for key in {
            (worker_name, pool),
            (base_name, pool),
            (worker_name, None),
            (base_name, None),
        }:
            workers.setdefault(key, []).append(worker_item)
    items = []
    pool_updates = []
    for ask_id, action in actions.items():
        if not isinstance(action, dict):
            continue
        state = str(action.get("state") or "failed")
        if state == "archived":
            counts["archived"] += 1
            continue
        pool_strategy = str(action.get("pool_strategy") or "akoya")
        action_worker_name = str(action.get("worker_name") or "")
        matched_workers = workers.get((action_worker_name, pool_strategy)) or []
        if not matched_workers and not action.get("pool_strategy"):
            matched_workers = workers.get((action_worker_name, None)) or []
        worker = next((item for item in matched_workers if item.get("is_connected")), None)
        if worker is None and matched_workers:
            worker = matched_workers[0]
        worker_hashrate = sum(safe_float(item.get("hashrate_ths")) for item in matched_workers)
        runtime_state = state
        status_msg = str(action.get("vast_status_msg") or "")
        actual_status = str(action.get("vast_actual_status") or "")
        has_runtime_error = vast_status_is_error(status_msg, actual_status)
        if state in {"renting", "rented"}:
            if has_runtime_error:
                runtime_state = "instance_error"
            elif worker and worker.get("is_connected"):
                runtime_state = "active"
            elif state == "rented" and worker:
                runtime_state = "worker_offline"
            elif state == "rented":
                runtime_state = "waiting_worker"
        counts[state] = counts.get(state, 0) + 1
        if runtime_state == "active":
            counts["active"] += 1
        if runtime_state == "instance_error":
            counts["instance_error"] += 1
        items.append({
            "ask_id": ask_id,
            "state": state,
            "runtime_state": runtime_state,
            "reason": action.get("reason", ""),
            "error": status_msg if has_runtime_error else action.get("error", ""),
            "status": status_msg if not has_runtime_error else "",
            "instance_id": action.get("instance_id"),
            "vast_cur_state": action.get("vast_cur_state", ""),
            "vast_actual_status": action.get("vast_actual_status", ""),
            "vast_pool_strategy_actual": action.get("vast_pool_strategy_actual", ""),
            "worker_name": action.get("worker_name", ""),
            "pool_strategy": pool_strategy,
            "gpu": action.get("gpu", ""),
            "gpu_count": action.get("gpu_count"),
            "host_id": action.get("host_id"),
            "machine_id": action.get("machine_id"),
            "price_usd_hr": action.get("price_usd_hr"),
            "max_safe_price_usd_hr": action.get("max_safe_price_usd_hr"),
            "updated_at": action.get("updated_at") or action.get("created_at"),
            "worker_connected": any(bool(item.get("is_connected")) for item in matched_workers),
            "worker_hashrate_ths": round(worker_hashrate, 2) if matched_workers else None,
            "offline_rescue_state": action.get("offline_rescue_state", ""),
            "offline_rescue_attempts": action.get("offline_rescue_attempts"),
            "offline_rescue_last_at": action.get("offline_rescue_last_at"),
            "offline_rescue_next_at": action.get("offline_rescue_next_at"),
            "offline_rescue_regrab_queued_at": action.get("offline_rescue_regrab_queued_at"),
            "offline_rescue_regrab_next_at": action.get("offline_rescue_regrab_next_at"),
        })
        if action.get("akoya_image_updated_at"):
            before_hash = safe_float(action.get("akoya_update_before_hashrate_ths"))
            current_hash = worker_hashrate if matched_workers else None
            delta = current_hash - before_hash if current_hash is not None and before_hash > 0 else None
            delta_pct = (delta / before_hash * 100) if delta is not None and before_hash > 0 else None
            status = pool_switch_status(before_hash, None, current_hash, None)
            pool_updates.append({
                "kind": "akoya_update",
                "ask_id": ask_id,
                "instance_id": action.get("instance_id"),
                "worker_name": action.get("worker_name", ""),
                "gpu": action.get("gpu", ""),
                "gpu_count": action.get("gpu_count"),
                "price_usd_hr": action.get("price_usd_hr"),
                "from_pool": "akoya",
                "to_pool": "akoya",
                "current_pool": pool_strategy,
                "before_hashrate_ths": round(before_hash, 2) if before_hash > 0 else None,
                "current_hashrate_ths": round(current_hash, 2) if current_hash is not None else None,
                "delta_hashrate_ths": round(delta, 2) if delta is not None else None,
                "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
                "before_profit_usd_hr": None,
                "current_profit_usd_hr": None,
                "delta_profit_usd_hr": None,
                "updated_at": action.get("akoya_image_updated_at"),
                "target_image": action.get("akoya_image") or "",
                "worker_connected": any(bool(item.get("is_connected")) for item in matched_workers),
                "status": status,
                "status_class": pool_switch_status_class(status),
                "reason": action.get("reason", ""),
            })
        if action.get("pool_switch_started_at"):
            before_hash = safe_float(action.get("pool_switch_before_hashrate_ths"))
            before_profit_raw = action.get("pool_switch_before_profit_usd_hr")
            before_profit = safe_float(before_profit_raw) if before_profit_raw is not None else None
            current_hash = worker_hashrate if matched_workers else None
            current_profit = safe_float(worker.get("profit_usd_hr")) if worker and worker.get("profit_usd_hr") is not None else None
            delta = current_hash - before_hash if current_hash is not None and before_hash > 0 else None
            delta_pct = (delta / before_hash * 100) if delta is not None and before_hash > 0 else None
            delta_profit = current_profit - before_profit if current_profit is not None and before_profit is not None else None
            status = pool_switch_status(before_hash, before_profit, current_hash, current_profit)
            pool_updates.append({
                "kind": "pool_switch",
                "ask_id": ask_id,
                "instance_id": action.get("instance_id"),
                "worker_name": action.get("worker_name", ""),
                "gpu": action.get("gpu", ""),
                "gpu_count": action.get("gpu_count"),
                "price_usd_hr": action.get("price_usd_hr"),
                "from_pool": action.get("pool_switch_from_pool"),
                "to_pool": action.get("pool_switch_to_pool"),
                "current_pool": pool_strategy,
                "before_hashrate_ths": round(before_hash, 2) if before_hash > 0 else None,
                "current_hashrate_ths": round(current_hash, 2) if current_hash is not None else None,
                "delta_hashrate_ths": round(delta, 2) if delta is not None else None,
                "delta_pct": round(delta_pct, 1) if delta_pct is not None else None,
                "before_profit_usd_hr": round_money(before_profit),
                "current_profit_usd_hr": round_money(current_profit),
                "delta_profit_usd_hr": round_money(delta_profit),
                "updated_at": action.get("pool_switch_started_at"),
                "target_image": action.get("pool_switch_target_image") or "",
                "worker_connected": any(bool(item.get("is_connected")) for item in matched_workers),
                "status": status,
                "status_class": pool_switch_status_class(status),
                "reason": action.get("reason", ""),
            })
    items.sort(key=lambda item: safe_float(item.get("updated_at")), reverse=True)
    pool_updates.sort(key=lambda item: safe_float(item.get("updated_at")), reverse=True)
    return {
        "active_count": active_vast_rent_count(actions),
        "max_active": VAST_MAX_ACTIVE_RENTS,
        "mode": VAST_AUTORENT_MODE,
        "default_disk_gb": float(os.getenv("VAST_INSTANCE_DISK_GB") or "8"),
        "counts": counts,
        "items": items,
        "akoya_updates": [item for item in pool_updates if item.get("kind") == "akoya_update"],
        "pool_updates": pool_updates,
    }


def clore_action_summary(actions: dict[str, Any], operation: dict[str, Any] | None = None) -> dict[str, Any]:
    counts: dict[str, int] = {"renting": 0, "rented": 0, "active": 0, "watching": 0, "failed": 0, "cancelled": 0, "blacklisted": 0, "archived": 0}
    workers_by_name = {
        str(worker.get("worker_name") or ""): worker
        for worker in (operation or {}).get("workers", [])
        if isinstance(worker, dict)
    }
    items = []
    for server_id, action in actions.items():
        if not isinstance(action, dict):
            continue
        state = str(action.get("state") or "failed")
        counts[state] = counts.get(state, 0) + 1
        worker = workers_by_name.get(str(action.get("worker_name") or ""))
        runtime_state = "active" if worker and worker.get("is_connected") else state
        if runtime_state == "active":
            counts["active"] = counts.get("active", 0) + 1
        items.append({
            "server_id": server_id,
            "order_id": action.get("order_id"),
            "state": state,
            "runtime_state": runtime_state,
            "reason": action.get("reason", ""),
            "error": action.get("error", ""),
            "order_sync_error": action.get("order_sync_error", ""),
            "worker_name": action.get("worker_name", ""),
            "pool_strategy": action.get("pool_strategy", ""),
            "gpu": action.get("gpu", ""),
            "gpu_count": action.get("gpu_count"),
            "price_usd_hr": action.get("price_usd_hr"),
            "currency": action.get("currency", ""),
            "image": action.get("image", ""),
            "clore_online": action.get("clore_online"),
            "clore_spend": action.get("clore_spend"),
            "clore_order_created_at": action.get("clore_order_created_at"),
            "clore_order_mrl_seconds": action.get("clore_order_mrl_seconds"),
            "clore_order_expires_at": action.get("clore_order_expires_at"),
            "clore_order_time_left_seconds": action.get("clore_order_time_left_seconds"),
            "clore_rerent_enabled": bool(action.get("clore_rerent_enabled")),
            "clore_rerent_next_at": action.get("clore_rerent_next_at"),
            "clore_rerent_error": action.get("clore_rerent_error", ""),
            "updated_at": action.get("updated_at") or action.get("created_at"),
            "worker_connected": bool(worker and worker.get("is_connected")),
            "worker_hashrate_ths": worker.get("hashrate_ths") if worker else None,
        })
    items.sort(key=lambda item: safe_float(item.get("updated_at")), reverse=True)
    wallets = latest_clore_wallets if isinstance(latest_clore_wallets, dict) else {}
    wallet_items = [item for item in wallets.get("wallets", []) if isinstance(item, dict)]
    usd_wallet = next((item for item in wallet_items if str(item.get("name") or "") == "USD-Blockchain"), {})
    clore_wallet = next((item for item in wallet_items if str(item.get("name") or "") == "CLORE-Blockchain"), {})
    wallet_balances = {
        str(item.get("name") or ""): safe_float(item.get("balance"))
        for item in wallet_items
        if str(item.get("name") or "")
    }
    return {
        "mode": CLORE_AUTORENT_MODE,
        "configured": bool(clore.api_key()),
        "counts": counts,
        "wallets": {
            "usd_balance": safe_float(usd_wallet.get("balance")) if usd_wallet else None,
            "clore_balance": safe_float(clore_wallet.get("balance")) if clore_wallet else None,
            "balances": wallet_balances,
            "sync_error": wallets.get("error", ""),
            "updated_at": wallets.get("updated_at"),
        },
        "currency_order": clore.currency_order(),
        "items": items,
    }


def build_snipers(actions: dict[str, Any], operation: dict[str, Any], scout: dict[str, Any]) -> dict[str, Any]:
    workers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for worker in operation.get("workers") or []:
        if not isinstance(worker, dict):
            continue
        ask_id = ask_id_from_vast_worker(str(worker.get("worker_name") or ""))
        pool = str(worker.get("pool") or "")
        if ask_id and pool:
            workers.setdefault((ask_id, pool), []).append(worker)

    tests_by_ask = {
        str(test.get("ask_id")): test
        for test in (scout.get("tests") or {}).values()
        if isinstance(test, dict) and test.get("ask_id") and test.get("is_new_machine")
    }
    queue_by_ask = {
        str(item.get("ask_id")): item
        for item in (scout.get("queue") or {}).values()
        if isinstance(item, dict) and item.get("ask_id") and item.get("is_new_machine")
    }
    history_by_ask: dict[str, dict[str, Any]] = {}
    for item in scout_history_items()[:200]:
        if not isinstance(item, dict) or not item.get("ask_id") or not item.get("is_new_machine"):
            continue
        history_by_ask.setdefault(str(item.get("ask_id")), item)

    ask_ids = {
        str(ask_id)
        for ask_id, action in actions.items()
        if isinstance(action, dict) and action.get("state") != "archived" and action.get("is_new_machine")
    }
    ask_ids.update(queue_by_ask.keys())
    ask_ids.update(tests_by_ask.keys())
    ask_ids.update(list(history_by_ask.keys())[:80])

    rows: list[dict[str, Any]] = []
    for ask_id in ask_ids:
        action = action_by_id(actions, ask_id) or {}
        test = tests_by_ask.get(ask_id) or {}
        history = history_by_ask.get(ask_id) or {}
        queue_item = queue_by_ask.get(ask_id) or {}
        pool = str(test.get("pool_strategy") or action.get("pool_strategy") or action.get("scout_final_pool") or history.get("pool_strategy") or "")
        pool_workers = workers.get((ask_id, pool), [])
        if not pool_workers:
            for (worker_ask, _worker_pool), group in workers.items():
                if worker_ask == ask_id:
                    pool_workers = group
                    pool = str(group[0].get("pool") or pool)
                    break

        results = []
        if history:
            results.extend(scout_history_pool_results(history))
        if test:
            results.extend(scout_pool_results(test))
            if test.get("samples") or test.get("pool_strategy"):
                results.append(scout_result_from_test(test, str(test.get("decision") or "testing"), str(test.get("reason") or "")))
        by_pool: dict[str, dict[str, Any]] = {}
        for result in results:
            result_pool = str(result.get("pool_strategy") or "")
            if result_pool:
                by_pool[result_pool] = result
        best = max(
            [item for item in by_pool.values() if item.get("profit_usd_hr") is not None],
            key=lambda item: safe_float(item.get("profit_usd_hr"), -999999),
            default=None,
        )

        status = "snipado"
        status_class = "yellow"
        decision = str(test.get("decision") or history.get("decision") or action.get("scout_final_decision") or action.get("state") or queue_item.get("queue_status") or "")
        if test and test.get("status") == "testing":
            if decision in {"waiting_worker", "switching_pool", "returning_best_pool"}:
                status = "trocando"
                status_class = "yellow"
            else:
                status = f"testando {strategy_label(pool)}"
                status_class = "alert"
        elif action.get("scout_approved") or action.get("scout_final") or decision == "keep":
            status = "aprovado"
            status_class = "green"
        elif decision == "blacklist":
            status = "blacklist"
            status_class = "red"
        elif decision == "destroy":
            status = "destruido"
            status_class = "red"
        elif decision in {"failed", "lost"} or action.get("state") == "failed":
            status = "perdido"
            status_class = "gray"
        elif action.get("state") == "waiting_market" or queue_item.get("transient_unavailable"):
            status = "retry Vast" if scout_transient_retry_due(queue_item) else "aguardando Vast"
            status_class = "yellow"
        elif action.get("state") == "renting":
            status = "snipado"
            status_class = "yellow"
        elif action.get("state") == "rented":
            status = "rodando"
            status_class = "green"
        elif queue_item:
            status = "novo na fila" if queue_item.get("queue_status") == "queued" else str(queue_item.get("queue_status") or "novo")
            status_class = "green" if queue_item.get("queue_status") == "queued" else "gray"

        current_hash = sum(safe_float(worker.get("hashrate_ths")) for worker in pool_workers)
        current_profit = sum(safe_float(worker.get("profit_usd_hr")) for worker in pool_workers) if pool_workers else None
        updated_at = max(
            safe_float(action.get("updated_at") or action.get("created_at")),
            safe_float(test.get("ended_at") or test.get("stage_started_at") or test.get("started_at")),
            safe_float(history.get("ended_at")),
            safe_float(queue_item.get("last_seen_at")),
        )
        rows.append({
            "ask_id": safe_int(ask_id),
            "instance_id": test.get("instance_id") or action.get("instance_id") or history.get("instance_id"),
            "gpu": test.get("gpu") or action.get("gpu") or history.get("gpu") or queue_item.get("gpu"),
            "gpu_count": test.get("gpu_count") or action.get("gpu_count") or history.get("gpu_count") or queue_item.get("gpu_count"),
            "host_id": test.get("host_id") or action.get("host_id") or history.get("host_id") or queue_item.get("host_id"),
            "machine_id": test.get("machine_id") or action.get("machine_id") or history.get("machine_id") or queue_item.get("machine_id"),
            "pool_current": pool,
            "status": status,
            "status_class": status_class,
            "price_usd_hr": test.get("price_usd_hr") or action.get("price_usd_hr") or history.get("price_usd_hr") or queue_item.get("price_usd_hr"),
            "akoya_profit_usd_hr": (by_pool.get("akoya") or {}).get("profit_usd_hr"),
            "alphamine_profit_usd_hr": (by_pool.get("alphamine") or {}).get("profit_usd_hr"),
            "best_pool": (best or {}).get("pool_strategy") or action.get("scout_final_pool") or "",
            "current_hashrate_ths": round(current_hash, 4) if pool_workers else None,
            "current_profit_usd_hr": round_money(current_profit) if current_profit is not None else None,
            "decision": decision,
            "reason": test.get("reason") or history.get("reason") or action.get("reason") or queue_item.get("skip_reason") or queue_item.get("retest_reason") or "",
            "machine_first_seen_at": test.get("machine_first_seen_at") or action.get("machine_first_seen_at") or history.get("machine_first_seen_at") or queue_item.get("machine_first_seen_at"),
            "marketplace_first_seen_at": test.get("marketplace_first_seen_at") or action.get("marketplace_first_seen_at") or history.get("marketplace_first_seen_at") or queue_item.get("first_seen_at"),
            "sniped_at": action.get("sniped_at") or test.get("started_at"),
            "last_seen_at": queue_item.get("last_seen_at") or action.get("updated_at") or history.get("ended_at"),
            "updated_at": updated_at,
        })

    rows.sort(key=lambda item: (
        item.get("status") not in {"testando Akoya", "testando AlphaMine", "trocando", "snipado"},
        -safe_float(item.get("updated_at")),
    ))
    return {
        "counts": {
            "total": len(rows),
            "testing": sum(1 for item in rows if str(item.get("status", "")).startswith("testando")),
            "queued": sum(1 for item in rows if item.get("status") == "novo na fila"),
            "approved": sum(1 for item in rows if item.get("status") == "aprovado"),
            "failed": sum(1 for item in rows if item.get("status") in {"destruido", "blacklist", "perdido"}),
        },
        "items": rows[:80],
    }


def action_by_id(actions: dict[str, Any], item_id: Any) -> dict[str, Any] | None:
    action = actions.get(str(item_id))
    return action if isinstance(action, dict) else None


def blacklist_items(blacklist: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(blacklist, dict):
        return []
    return [item for item in blacklist.get("items", []) if isinstance(item, dict)]


def vast_offer_is_blacklisted(item: dict[str, Any], blacklist: dict[str, Any] | None) -> bool:
    host_id = str(item.get("host_id") or "")
    machine_id = str(item.get("machine_id") or "")
    gpu = str(item.get("gpu_model_normalized") or item.get("gpu_model_raw") or "")
    gpu_normalized = normalize_gpu_name(gpu)
    for blocked in blacklist_items(blacklist):
        blocked_scope = str(blocked.get("scope") or "")
        blocked_machine = str(blocked.get("machine_id") or "")
        blocked_host = str(blocked.get("host_id") or "")
        blocked_gpu = normalize_gpu_name(blocked.get("gpu"))
        if blocked_scope == "gpu_model" and blocked_gpu and blocked_gpu == gpu_normalized:
            return True
        if blocked_machine and machine_id and blocked_machine == machine_id:
            return True
        if blocked_host and host_id and blocked_host == host_id and (not blocked_gpu or blocked_gpu == gpu_normalized):
            return True
    return False


def manual_results_override(item: dict[str, Any] | None) -> bool:
    return results_manual_allowlist_bypass(item)


def vast_worker_name(item_id: Any) -> str:
    return vast.strategy_worker_name("akoya", item_id)


def server_id_from_clore_worker(worker_name: Any) -> int:
    text = str(worker_name or "")
    if not text.startswith("clore-"):
        return 0
    return safe_int(text.split("-", 1)[1])


def vast_strategy_configured(strategy: str) -> bool:
    return vast.strategy_configured(strategy)


def vast_action_state(
    platform: str,
    item_id: Any,
    strategy: str,
    decision: str,
    price_hr: float | None,
    max_safe_price: float | None,
    risks: list[str],
    actions: dict[str, Any],
) -> dict[str, Any]:
    previous = action_by_id(actions, item_id)
    if previous and previous.get("state") in {"renting", "rented"}:
        return {
            "state": previous.get("state", "renting"),
            "reason": previous.get("reason", ""),
            "error": previous.get("error", ""),
        }
    if platform != "vastai":
        return {"state": "blocked", "reason": "Somente Vast usa aluguel por API"}
    if VAST_AUTORENT_MODE != "confirm":
        return {"state": "blocked", "reason": "Modo de aluguel nao esta em confirm"}
    if not vast_api_key():
        return {"state": "blocked", "reason": "VAST_API_KEY ausente"}
    if not vast_template_hash_id_for(strategy) and not vast_image_for_strategy(strategy):
        env_name = "VAST_ALPHAMINE_TEMPLATE_HASH_ID" if strategy == "alphamine" else "VAST_AKOYA_TEMPLATE_HASH_ID"
        image_env = "VAST_ALPHAMINE_IMAGE" if strategy == "alphamine" else "VAST_AKOYA_IMAGE"
        return {"state": "blocked", "reason": f"{env_name} ou {image_env} ausente"}
    if not wallet_for_strategy(strategy):
        env_name = "ALPHAMINE_WALLET/AKOYA_WALLET" if strategy == "alphamine" else "AKOYA_WALLET"
        return {"state": "blocked", "reason": f"{env_name} ausente"}
    if decision != "green":
        return {"state": "blocked", "reason": "Oferta nao esta verde"}
    severe = {
        "low_value_gpu",
        "price_usd_missing",
        "network_bad",
        "clore_cache_risk",
        *SCOUT_HARDWARE_BLOCK_RISKS,
    }
    if severe.intersection(risks):
        return {"state": "blocked", "reason": "Risco severo presente"}
    if price_hr is None or max_safe_price is None:
        return {"state": "blocked", "reason": "Preco/teto indisponivel"}
    if price_hr > max_safe_price:
        return {"state": "blocked", "reason": f"Preco ${price_hr:.2f}/h acima do teto verde ${max_safe_price:.2f}/h"}
    return {"state": "ready", "reason": "Pronta para confirmar aluguel"}


def clore_action_state(
    item_id: Any,
    strategy: str,
    decision: str,
    price_hr: float | None,
    max_safe_price: float | None,
    risks: list[str],
    actions: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    previous = action_by_id(actions, item_id)
    if previous and previous.get("state") in {"renting", "rented"}:
        return {
            "state": previous.get("state", "renting"),
            "reason": previous.get("reason", ""),
            "error": previous.get("error", ""),
        }
    if previous and previous.get("state") == "blacklisted":
        return {
            "state": "blocked",
            "reason": previous.get("reason") or "Servidor Clore blacklistado pelo Scout",
            "error": previous.get("error", ""),
        }
    previous_error = str(previous.get("error") or "") if previous and previous.get("state") == "failed" else ""
    if CLORE_AUTORENT_MODE != "confirm":
        return {"state": "blocked", "reason": "Modo Clore nao esta em confirm"}
    if not clore.api_key():
        return {"state": "blocked", "reason": "CLORE_API_KEY ausente"}
    if not clore.configured(strategy):
        return {"state": "blocked", "reason": f"Clore {clore.strategy_label(strategy)} sem imagem ou wallet"}
    if item.get("diagnostic_only") or item.get("source") != "official_api":
        return {"state": "blocked", "reason": "Clore nao verificada pela API oficial"}
    if item.get("rented", True):
        return {"state": "rented", "reason": "Servidor ja alugado na Clore"}
    allowed_coins = set(item.get("allowed_coins") or item.get("allowed_currencies") or [])
    configured_coins = set(clore.currency_order())
    if allowed_coins and configured_coins and not allowed_coins.intersection(configured_coins):
        return {"state": "blocked", "reason": "Oferta Clore nao aceita moedas configuradas"}
    if item.get("price"):
        eligible_currencies = clore.eligible_currencies(item, latest_clore_wallets)
        if not eligible_currencies:
            reasons = "; ".join(clore.currency_rejection_reasons(item, latest_clore_wallets))
            return {"state": "blocked", "reason": f"Sem saldo/moeda Clore: {reasons}"}
    if decision not in CLORE_MANUAL_RENT_DECISIONS:
        return {"state": "blocked", "reason": "Oferta sem lucro positivo para Scout"}
    if price_hr is None or max_safe_price is None:
        return {"state": "blocked", "reason": "Preco/teto indisponivel"}
    hardware_reason = scout_hardware_block_reason({"risks": risks})
    if hardware_reason:
        return {"state": "blocked", "reason": hardware_reason}
    if decision == "green" and price_hr > max_safe_price:
        return {"state": "blocked", "reason": f"Preco ${price_hr:.2f}/h acima do teto verde ${max_safe_price:.2f}/h"}
    if decision == "alert":
        reason = "RISCO liberado: revalidar na Clore e testar via Scout"
    elif decision == "yellow":
        reason = "MARGEM liberada: revalidar na Clore e testar via Scout"
    else:
        reason = "Revalidar na Clore e alugar por clique"
    if previous_error:
        reason = f"Ultima falha: {previous_error}"
    return {"state": "ready", "reason": reason, "error": previous_error}


def vast_rent_options(
    platform: str,
    item_id: Any,
    decision: str,
    price_hr: float | None,
    max_safe_price: float | None,
    risks: list[str],
    actions: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if platform != "vastai":
        return {}
    return {
        strategy: vast_action_state(platform, item_id, strategy, decision, price_hr, max_safe_price, risks, actions)
        for strategy in vast_pool_strategies()
    }


def clore_rent_options(
    item_id: Any,
    decision: str,
    price_hr: float | None,
    max_safe_price: float | None,
    risks: list[str],
    actions: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        strategy: clore_action_state(item_id, strategy, decision, price_hr, max_safe_price, risks, actions, item)
        for strategy in clore.pool_strategies()
    }


def source_status(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    current = now_ts()
    for key in REDIS_KEYS:
        payload = raw.get(key)
        if not payload:
            out[key] = {"ok": False, "age_s": None, "stale": True}
            continue
        if payload.get("_fallback"):
            age = max(0.0, current - safe_float(payload.get("_fallback_from_ts") or payload.get("_ts")))
            out[key] = {
                "ok": age <= PEARL_FALLBACK_TTL_SECONDS,
                "age_s": round(age, 1),
                "stale": age > PEARL_FALLBACK_TTL_SECONDS,
                "fallback": True,
            }
            continue
        age = max(0.0, current - safe_float(payload.get("_ts")))
        out[key] = {
            "ok": age <= REDIS_TTL_SECONDS,
            "age_s": round(age, 1),
            "stale": age > REDIS_TTL_SECONDS,
        }
    return out


def pool_for_gpu(gpu_data: dict[str, Any]) -> str:
    kernel = str(gpu_data.get("kernel", "akoya"))
    if kernel == "alphamine":
        return "alphamine"
    return kernel


def rate_for_pool(pearl: dict[str, Any] | None, pool: str) -> float | None:
    if not pearl:
        return None
    rates = pearl.get("usd_per_th_per_day") or {}
    return safe_float(rates.get(pool), 0.0) or None


def pearl_payload_usable(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    rates = payload.get("usd_per_th_per_day")
    if not isinstance(rates, dict):
        return False
    has_rate = any(safe_float(value) > 0 for value in rates.values())
    return has_rate and safe_float(payload.get("prl_price_usd")) > 0


def apply_pearl_fallback(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    global latest_pearl_payload
    current = now_ts()
    pearl = raw.get("monitor:pearl")
    if pearl_payload_usable(pearl):
        latest_pearl_payload = dict(pearl)
        source_ts = safe_float(pearl.get("_ts"))
        age = current - source_ts if source_ts > 0 else 0.0
        if source_ts > 0 and REDIS_TTL_SECONDS < age <= PEARL_FALLBACK_TTL_SECONDS:
            fallback = dict(pearl)
            fallback["_fallback"] = True
            fallback["_fallback_from_ts"] = source_ts
            fallback["_fallback_age_s"] = round(max(0.0, age), 1)
            patched = dict(raw)
            patched["monitor:pearl"] = fallback
            return patched
        return raw
    if not pearl_payload_usable(latest_pearl_payload):
        return raw
    source_ts = safe_float(latest_pearl_payload.get("_fallback_from_ts") or latest_pearl_payload.get("_ts"))
    if source_ts <= 0:
        return raw
    age = current - source_ts
    if age > PEARL_FALLBACK_TTL_SECONDS:
        return raw
    fallback = dict(latest_pearl_payload)
    fallback["_fallback"] = True
    fallback["_fallback_from_ts"] = source_ts
    fallback["_fallback_age_s"] = round(max(0.0, age), 1)
    patched = dict(raw)
    patched["monitor:pearl"] = fallback
    return patched


def decision_from_profit(
    profit_day: float | None,
    roi_pct: float | None,
    risks: list[str],
    can_calculate: bool,
) -> str:
    if not can_calculate:
        return "gray"
    if profit_day is None or roi_pct is None:
        return "gray"
    if profit_day <= 0:
        return "red"
    severe = {
        "low_value_gpu",
        "cuda_below_12_9",
        "cuda_unknown",
        "pcie_below_rule",
        "pcie_unknown",
        "price_usd_missing",
        "network_bad",
        "clore_cache_risk",
        "insufficient_vcpu",
        "insufficient_ram",
        "insufficient_storage",
    }
    if severe.intersection(risks):
        return "alert"
    if profit_day >= GREEN_MIN_PROFIT_DAY and roi_pct >= GREEN_MIN_ROI_PCT:
        return "green"
    return "yellow"


def base_risks(item: dict[str, Any], platform: str, gpu_data: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    risks.extend(item.get("resource_risks") or [])
    if gpu_data.get("low_value"):
        risks.append("low_value_gpu")
    if platform == "clore":
        if item.get("source") != "official_api" or item.get("diagnostic_only"):
            risks.append("clore_cache_risk")
        if not item.get("available_verified", False):
            risks.append("clore_unverified")
        cuda = parse_cuda(item.get("cuda_version"))
        if cuda is None:
            risks.append("cuda_unknown")
        elif cuda < 12.9:
            risks.append("cuda_below_12_9")
        if not item.get("meets_pcie", False):
            risks.append("pcie_below_rule")
    else:
        cuda = parse_cuda(item.get("cuda_max_good"))
        if cuda is not None and cuda < 12.9:
            risks.append("cuda_below_12_9")
        if not item.get("meets_pcie", True):
            risks.append("pcie_below_rule")

    reliability_raw = item.get("reliability")
    if reliability_raw not in {None, ""}:
        reliability = safe_float(reliability_raw)
        if reliability < 0.8:
            risks.append("reliability_low")
        elif reliability < 0.95:
            risks.append("reliability_watch")

    up = safe_float(item.get("net_up_mbps"))
    down = safe_float(item.get("net_down_mbps"))
    if (up and up < 10) or (down and down < 10):
        risks.append("network_bad")
    elif (up and up < 50) or (down and down < 50):
        risks.append("network_watch")
    return risks


def scout_metadata_risks(test: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    cuda = parse_cuda(test.get("cuda"))
    if cuda is None:
        risks.append("cuda_unknown")
    elif cuda < 12.9:
        risks.append("cuda_below_12_9")

    pcie = str(test.get("pcie") or "").strip().lower()
    if pcie.startswith("x"):
        lanes = safe_float(pcie.split()[0].lstrip("x"))
        if lanes and lanes < 8:
            risks.append("pcie_below_rule")
    elif pcie:
        risks.append("pcie_unknown")

    reliability_raw = test.get("reliability")
    if reliability_raw not in {None, ""}:
        reliability = safe_float(reliability_raw)
        if reliability < 0.8:
            risks.append("reliability_low")
        elif reliability < 0.95:
            risks.append("reliability_watch")

    up = safe_float(test.get("net_up_mbps"))
    down = safe_float(test.get("net_down_mbps"))
    if (up and up < 20) or (down and down < 20):
        risks.append("network_bad")
    elif (up and up < 100) or (down and down < 100):
        risks.append("network_watch")
    return risks


def calculate_opportunity(
    platform: str,
    item: dict[str, Any],
    pearl: dict[str, Any] | None,
    pearl_ok: bool,
    actions: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    gpu_name = item.get("gpu_model_normalized") or item.get("gpu_model_raw")
    gpu_data = get_gpu(gpu_name)
    if not gpu_data or not gpu_data.get("supported", False):
        return None

    gpu_count = safe_int(item.get("gpu_count"), 1)
    hashrate_ths = safe_float(gpu_data.get("ths")) * gpu_count
    pool = pool_for_gpu(gpu_data)
    rate_day = rate_for_pool(pearl, pool)
    price_hr = safe_float(item.get("price_usd_hr"))
    price_day = safe_float(item.get("price_usd_day")) or price_hr * 24
    risks = base_risks(item, platform, gpu_data)

    price_valid = price_day > 0 and not (platform == "clore" and item.get("diagnostic_only"))
    if not price_valid:
        risks.append("price_usd_missing")

    can_calculate = bool(pearl_ok and rate_day and price_valid)
    revenue_day = hashrate_ths * rate_day if can_calculate else None
    profit_day = revenue_day - price_day if revenue_day is not None else None
    revenue_hr = revenue_day / 24 if revenue_day is not None else None
    profit_hr = profit_day / 24 if profit_day is not None else None
    roi_pct = (profit_day / price_day * 100) if profit_day is not None and price_day > 0 else None
    decision = decision_from_profit(profit_day, roi_pct, risks, can_calculate)
    item_id = item.get("server_id") or item.get("offer_id")
    max_safe_price = green_max_price_usd_hr(revenue_hr)
    if platform == "clore":
        rent_options = clore_rent_options(
            item_id=item_id,
            decision=decision,
            price_hr=price_hr if price_valid else None,
            max_safe_price=max_safe_price,
            risks=risks,
            actions=actions or {},
            item=item,
        )
    else:
        rent_options = vast_rent_options(
            platform=platform,
            item_id=item_id,
            decision=decision,
            price_hr=price_hr if price_valid else None,
            max_safe_price=max_safe_price,
            risks=risks,
            actions=actions or {},
        )
    action = rent_options.get(pool) or next(iter(rent_options.values()), {"state": "blocked", "reason": ""})

    return {
        "platform": platform,
        "id": item_id,
        "rental_url": rental_url(platform, item_id),
        "search_url": marketplace_search_url(platform, gpu_name, gpu_count, item, max_safe_price, decision),
        "action_state": action["state"],
        "action_reason": action["reason"],
        "action_error": action.get("error", ""),
        "rent_options": rent_options,
        "max_safe_price_usd_hr": max_safe_price,
        "template_ready": bool(vast_template_hash_id_for(pool)),
        "worker_name_preview": (
            vast_worker_name(item_id) if platform == "vastai" and item_id else
            clore.strategy_worker_name(pool, item_id) if platform == "clore" and item_id else
            ""
        ),
        "gpu": gpu_name,
        "gpu_raw": item.get("gpu_model_raw"),
        "gpu_count": gpu_count,
        "host_id": item.get("host_id"),
        "machine_id": item.get("machine_id"),
        "pool": pool,
        "hashrate_ths": round(hashrate_ths, 2),
        "hashrate_source": "shared.gpu_hashrates",
        "price_usd_hr": round_money(price_hr) if price_valid else None,
        "cost_usd_day": round_money(price_day) if price_valid else None,
        "revenue_usd_hr": round_money(revenue_hr),
        "revenue_usd_day": round_money(revenue_day),
        "profit_usd_hr": round_money(profit_hr),
        "profit_usd_day": round_money(profit_day),
        "roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "calc_formula": (
            f"{round(hashrate_ths, 2)} TH/s * ${rate_day:.4f}/TH/d / 24 - ${price_hr:.4f}/h"
            if can_calculate
            else "aguardando preco/rede"
        ),
        "rate_usd_per_th_day": round_money(rate_day),
        "price_detail": item.get("price_detail") or item.get("price_source") or "custo/h oferta",
        "decision": decision,
        "risks": risks,
        "cuda": item.get("cuda_version") or item.get("cuda_max_good") or "",
        "pcie": pcie_label(item, platform),
        "pcie_ok": bool(item.get("meets_pcie", True)),
        "reliability": round(safe_float(item.get("reliability")), 4),
        "net_up_mbps": round_money(safe_float(item.get("net_up_mbps"))),
        "net_down_mbps": round_money(safe_float(item.get("net_down_mbps"))),
        "country": item.get("country") or "",
        "available": True,
        "raw": {
            "price_source": "usd",
            "low_value": bool(gpu_data.get("low_value", False)),
            "availability_state": item.get("availability_state", ""),
            "source": item.get("source", ""),
            "price_currency": item.get("price_currency", ""),
            "allowed_coins": item.get("allowed_coins") or [],
        },
    }


def rental_url(platform: str, item_id: Any) -> str:
    if not item_id:
        return ""
    if platform == "vastai":
        return f"https://console.vast.ai/create/?ask_id={item_id}"
    if platform == "runpod":
        return RUNPOD_CONSOLE_BASE_URL
    if platform == "tensordock":
        return TENSORDOCK_CONSOLE_BASE_URL
    return ""


def vast_gpu_slug(gpu_name: Any) -> str:
    text = str(gpu_name or "").strip()
    return VAST_GPU_SLUGS.get(text, "")


def marketplace_search_url(
    platform: str,
    gpu_name: Any,
    gpu_count: int,
    item: dict[str, Any],
    max_price_usd_hr: float | None,
    decision: str,
) -> str:
    if platform == "clore":
        return clore_search_url(gpu_name, item)
    if decision != "green":
        return ""
    if platform != "vastai":
        return ""
    slug = vast_gpu_slug(gpu_name)
    if not slug:
        return ""
    params = dict(VAST_SEARCH_BASE_PARAMS)
    params["gpuModelNames"] = slug
    if gpu_count > 0:
        params["gpuCountMin"] = str(gpu_count)
        params["gpuCountMax"] = str(gpu_count)
    if max_price_usd_hr is not None and max_price_usd_hr > 0:
        params["priceInstanceHourlyMax"] = f"{max_price_usd_hr:.4f}"
    return f"{VAST_SEARCH_BASE_URL}?{urlencode(params)}"


def clore_search_url(gpu_name: Any, item: dict[str, Any]) -> str:
    gpu = str(gpu_name or "").strip()
    if not gpu:
        return ""
    lanes = safe_int(item.get("pcie_lanes"))
    if lanes >= 16:
        pcie_width = 16
    elif lanes >= 8:
        pcie_width = 8
    else:
        return ""
    params = {
        "srp": "1",
        "cuda": "12.9",
        "sort": "min-gpu",
        "pw": str(pcie_width),
        "gpu": gpu,
    }
    return f"{CLORE_SEARCH_BASE_URL}?{urlencode(params)}"


def pcie_label(item: dict[str, Any], platform: str) -> str:
    if platform == "vastai":
        lanes = item.get("pcie_lanes")
        bw = item.get("pcie_bw_gbps")
        if lanes or bw:
            return f"x{safe_float(lanes):g} / {safe_float(bw):g} GB/s"
        return ""
    lanes = safe_float(item.get("pcie_lanes"))
    rev = item.get("pcie_rev")
    if lanes:
        return f"x{lanes:g} / gen {rev or '?'}"
    return "unknown"


def decision_rank(value: str) -> int:
    return {"green": 0, "yellow": 1, "alert": 2, "red": 3, "gray": 4}.get(value, 9)


def runpod_opportunity_items(runpod: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for offer in runpod.get("offers", []) or []:
        if not offer.get("available"):
            continue
        item = dict(offer)
        item["gpu_count"] = safe_int(item.get("gpu_count"), 1) or 1
        item["price_detail"] = "RunPod on-demand lowestPrice.uninterruptablePrice"
        items.append(item)
    return items


def tensordock_resource_plan(offer: dict[str, Any], gpu_count: int) -> tuple[dict[str, Any], list[str]]:
    resources = offer.get("resources") or {}
    pricing = offer.get("pricing") or {}
    vcpus = max(4, gpu_count * 2)
    ram_gb = max(8, gpu_count * 4)
    storage_gb = 100
    risks: list[str] = []
    max_vcpus = safe_int(resources.get("max_vcpus") or resources.get("vcpu_count"), 0)
    max_ram = safe_int(resources.get("max_ram_gb") or resources.get("ram_gb"), 0)
    max_storage = safe_int(resources.get("max_storage_gb") or resources.get("storage_gb"), 0)
    if max_vcpus and max_vcpus < vcpus:
        risks.append("insufficient_vcpu")
    if max_ram and max_ram < ram_gb:
        risks.append("insufficient_ram")
    if max_storage and max_storage < storage_gb:
        risks.append("insufficient_storage")
    plan = {
        "vcpu_count": vcpus,
        "ram_gb": ram_gb,
        "storage_gb": storage_gb,
        "vcpu_cost_usd_hr": safe_float(pricing.get("per_vcpu_hr")) * vcpus,
        "ram_cost_usd_hr": safe_float(pricing.get("per_gb_ram_hr")) * ram_gb,
        "storage_cost_usd_hr": safe_float(pricing.get("per_gb_storage_hr")) * storage_gb,
    }
    return plan, risks


def tensordock_opportunity_items(tensordock: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    source = tensordock.get("hostnode_offers") or tensordock.get("offers") or []
    for offer in source:
        if not offer.get("available"):
            continue
        max_count = safe_int(offer.get("available_count") or offer.get("max_count") or offer.get("gpu_count"), 1)
        max_count = max(1, min(max_count, 8))
        gpu_price_hr = safe_float(offer.get("price_usd_hr"))
        for count in range(1, max_count + 1):
            item = dict(offer)
            plan, resource_risks = tensordock_resource_plan(offer, count)
            extra_hr = plan["vcpu_cost_usd_hr"] + plan["ram_cost_usd_hr"] + plan["storage_cost_usd_hr"]
            total_hr = gpu_price_hr * count + extra_hr
            item["offer_id"] = f"{offer.get('offer_id')}#x{count}"
            item["gpu_count"] = count
            item["price_usd_hr"] = round_money(total_hr)
            item["price_usd_day"] = round_money(total_hr * 24)
            item["price_detail"] = (
                f"GPU ${gpu_price_hr:.4f}/h x{count} + CPU/RAM/disk ${extra_hr:.4f}/h "
                f"({plan['vcpu_count']} vCPU, {plan['ram_gb']} GB RAM, {plan['storage_gb']} GB)"
            )
            item["resource_risks"] = resource_risks
            items.append(item)
    return items


def build_opportunities(
    raw: dict[str, dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    actions: dict[str, Any],
    clore_actions: dict[str, Any] | None = None,
    blacklist: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    pearl = raw.get("monitor:pearl")
    pearl_ok = bool(statuses.get("monitor:pearl", {}).get("ok"))
    opportunities: list[dict[str, Any]] = []

    clore = raw.get("monitor:clore") or {}
    if statuses.get("monitor:clore", {}).get("ok"):
        for server in clore.get("servers", []):
            if server.get("rented", True):
                continue
            opp = calculate_opportunity("clore", server, pearl, pearl_ok, clore_actions or {})
            if opp and decision_opportunity_visible(opp):
                opportunities.append(opp)

    vast = raw.get("monitor:vastai") or {}
    if statuses.get("monitor:vastai", {}).get("ok"):
        for offer in vast.get("offers", []):
            if not offer.get("on_demand_available", False):
                continue
            if vast_offer_is_blacklisted(offer, blacklist):
                continue
            opp = calculate_opportunity("vastai", offer, pearl, pearl_ok, actions)
            if opp and decision_opportunity_visible(opp):
                opportunities.append(opp)

    runpod = raw.get("monitor:runpod") or {}
    if statuses.get("monitor:runpod", {}).get("ok"):
        for offer in runpod_opportunity_items(runpod):
            opp = calculate_opportunity("runpod", offer, pearl, pearl_ok, actions)
            if opp and decision_opportunity_visible(opp):
                opportunities.append(opp)

    tensordock = raw.get("monitor:tensordock") or {}
    if statuses.get("monitor:tensordock", {}).get("ok"):
        for offer in tensordock_opportunity_items(tensordock):
            opp = calculate_opportunity("tensordock", offer, pearl, pearl_ok, actions)
            if opp and decision_opportunity_visible(opp):
                opportunities.append(opp)

    opportunities.sort(
        key=lambda item: (
            decision_rank(item["decision"]),
            -(item["profit_usd_day"] if item["profit_usd_day"] is not None else -999999),
            -(item["roi_pct"] if item["roi_pct"] is not None else -999999),
        )
    )
    return opportunities


def build_operation(
    raw: dict[str, dict[str, Any]],
    statuses: dict[str, dict[str, Any]],
    actions: dict[str, Any],
    clore_actions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pearl = raw.get("monitor:pearl") or {}
    pearl_ok = bool(statuses.get("monitor:pearl", {}).get("ok"))
    workers = []

    pool_payloads = [
        ("akoya", raw.get("monitor:akoya") or {}, bool(statuses.get("monitor:akoya", {}).get("ok"))),
        ("alphamine", raw.get("monitor:alphamine") or {}, bool(statuses.get("monitor:alphamine", {}).get("ok"))),
    ]

    total_worker_count = 0
    total_online_count = 0
    total_hashrate = 0.0
    total_pending = 0.0
    total_paid = 0.0
    max_stale = 0.0
    total_maturing = 0
    next_maturity_values = []
    any_ok = False

    for pool, payload, pool_ok in pool_payloads:
        any_ok = any_ok or pool_ok
        total_worker_count += safe_int(payload.get("worker_count"))
        total_online_count += safe_int(payload.get("online_worker_count"))
        total_hashrate += safe_float(payload.get("total_hashrate_ths"))
        total_pending += safe_float(payload.get("pending_balance_prl"))
        total_paid += safe_float(payload.get("total_paid_prl"))
        max_stale = max(max_stale, safe_float(payload.get("stale_rate24h_pct")))
        total_maturing += safe_int(payload.get("maturing_blocks"))
        eta = safe_int(payload.get("next_maturity_eta_s"))
        if eta > 0:
            next_maturity_values.append(eta)

    for pool, payload, _pool_ok in pool_payloads:
        for worker in payload.get("workers", []):
            worker["_pool"] = pool

    raw_workers = [w for _, payload, _ in pool_payloads for w in payload.get("workers", [])]
    grouped_alpha_workers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    operation_source_workers = []
    for worker in raw_workers:
        pool = str(worker.get("_pool") or "akoya")
        name = str(worker.get("worker_name") or "")
        suffix = vast_worker_gpu_suffix(name)
        if pool == "alphamine" and suffix:
            grouped_alpha_workers.setdefault((pool, base_vast_worker_name(name)), []).append(worker)
        else:
            operation_source_workers.append(worker)

    for (pool, base_name), group in grouped_alpha_workers.items():
        first = dict(group[0])
        first["worker_name"] = base_name
        first["_pool"] = pool
        first["_gpu_worker_count"] = len(group)
        first["_gpu_worker_suffixes"] = sorted(vast_worker_gpu_suffix(item.get("worker_name")) for item in group)
        first["is_connected"] = any(bool(item.get("is_connected")) for item in group)
        for key in ("hashrate_ths", "hashrate_live_ths", "hashrate_1h_ths", "hashrate_24h_ths"):
            first[key] = sum(safe_float(item.get(key)) for item in group)
        for key in ("shares1h", "stale_shares1h"):
            first[key] = sum(safe_int(item.get(key)) for item in group)
        operation_source_workers.append(first)

    fixed_worker_costs = load_fixed_worker_costs()
    for worker in operation_source_workers:
        pool = str(worker.get("_pool") or "akoya")
        name = worker.get("worker_name", "")
        base_worker_name = base_vast_worker_name(name)
        gpu_suffix = vast_worker_gpu_suffix(name)
        cost_cfg = fixed_worker_cost_config(fixed_worker_costs, name, base_worker_name) or HARDCODED_WORKER_COSTS.get(name) or HARDCODED_WORKER_COSTS.get(base_worker_name)
        metadata_action = None
        action = None
        if not cost_cfg and name.startswith("clore-"):
            metadata_action = action_by_id(clore_actions or {}, server_id_from_clore_worker(name))
            if not metadata_action:
                continue
            if metadata_action.get("state") in {"archived", "cancelled"} and not worker.get("is_connected", False):
                continue
            if str(metadata_action.get("pool_strategy") or pool) != pool:
                continue
            action = metadata_action if metadata_action.get("state") in {"renting", "rented"} else None
            if safe_float(metadata_action.get("price_usd_hr")) > 0:
                cost_cfg = {
                    "provider": "Clore",
                    "cost_usd_hr": safe_float(metadata_action.get("price_usd_hr")),
                    "cost_source": "clore_action",
                    "future_source": "clore:my_orders",
                }
        if not cost_cfg and name.startswith("vast-"):
            metadata_action = action_by_id(actions, ask_id_from_vast_worker(name))
            if not metadata_action:
                continue
            if (
                metadata_action
                and metadata_action.get("state") == "archived"
                and "reset scout: destruida" in str(metadata_action.get("reason") or "").lower()
            ):
                continue
            if (
                metadata_action
                and metadata_action.get("state") == "archived"
                and not worker.get("is_connected", False)
            ):
                continue
            if (
                metadata_action
                and metadata_action.get("state") in {"renting", "rented"}
                and str(metadata_action.get("pool_strategy") or pool) != pool
            ):
                continue
            action = metadata_action
            if action and action.get("state") not in {"renting", "rented"}:
                action = None
            if action and str(action.get("pool_strategy") or pool) != pool:
                action = None
            if action:
                cost_cfg = {
                    "provider": "Vast.ai",
                    "cost_usd_hr": safe_float(action.get("price_usd_hr")),
                    "cost_source": "vast_action",
                    "future_source": "monitor:vast_instances",
                }
            elif (
                metadata_action
                and str(metadata_action.get("pool_strategy") or pool) == pool
                and safe_float(metadata_action.get("price_usd_hr")) > 0
            ):
                cost_cfg = {
                    "provider": "Vast.ai",
                    "cost_usd_hr": safe_float(metadata_action.get("price_usd_hr")),
                    "cost_source": "vast_action_metadata",
                    "future_source": "monitor:vast_instances",
                }
        hashrate = safe_float(worker.get("hashrate_ths"))
        rate_day = rate_for_pool(pearl, pool) if pearl_ok else None
        revenue_day = hashrate * rate_day if rate_day else None
        cost_hr = safe_float(cost_cfg.get("cost_usd_hr")) if cost_cfg else None
        cost_day = cost_hr * 24 if cost_hr else None
        profit_day = revenue_day - cost_day if revenue_day is not None and cost_day is not None else None
        revenue_hr = revenue_day / 24 if revenue_day is not None else None
        profit_hr = profit_day / 24 if profit_day is not None else None
        risks = []
        if not worker.get("is_connected", False):
            risks.append("worker_offline")
        if cost_cfg and cost_cfg.get("cost_source") == "fixed_config":
            risks.append("cost_fixed_config")
        if cost_cfg and cost_cfg.get("cost_source") == "hardcoded":
            risks.append("cost_hardcoded")
        if cost_cfg and cost_cfg.get("cost_source") == "vast_action_metadata":
            risks.append("cost_from_archived_action")
        if cost_day is None:
            risks.append("cost_not_configured")

        display_action = action or metadata_action
        action_gpu_count = safe_int(display_action.get("gpu_count"), 0) if display_action else 0
        worker_gpu_count = safe_int(worker.get("gpu_count"), 0)
        pool_gpu_count = action_gpu_count or worker_gpu_count or 1 if pool == "alphamine" else worker_gpu_count or action_gpu_count or 1
        rented_gpu_count = action_gpu_count or pool_gpu_count
        if action and rented_gpu_count != pool_gpu_count:
            risks.append("gpu_count_mismatch")
            gpu_data = get_gpu(worker.get("gpu_card_normalized") or worker.get("gpu_card") or action.get("gpu"))
            expected_hashrate = safe_float(gpu_data.get("ths") if gpu_data else None) * rented_gpu_count
            if expected_hashrate > 0 and hashrate < expected_hashrate * 0.65:
                risks.append("hashrate_below_rented_gpus")

        gpu_label = (
            worker.get("gpu_card_normalized")
            or worker.get("gpu_card")
            or (display_action.get("gpu") if display_action else "")
        )

        workers.append({
            "worker_name": name,
            "base_worker_name": base_worker_name,
            "ask_id": safe_int((display_action or {}).get("ask_id") or ask_id_from_vast_worker(name)),
            "server_id": safe_int((display_action or {}).get("server_id") or server_id_from_clore_worker(name)),
            "gpu_suffix": gpu_suffix,
            "pool": pool,
            "provider": cost_cfg.get("provider") if cost_cfg else "",
            "cost_source": cost_cfg.get("cost_source") if cost_cfg else "",
            "cost_future_source": cost_cfg.get("future_source") if cost_cfg else "",
            "gpu": gpu_label,
            "gpu_count": pool_gpu_count,
            "pool_gpu_count": pool_gpu_count,
            "akoya_gpu_count": pool_gpu_count if pool == "akoya" else None,
            "rented_gpu_count": rented_gpu_count,
            "vast_instance_id": display_action.get("instance_id") if display_action else None,
            "clore_order_id": display_action.get("order_id") if display_action else None,
            "clore_order_expires_at": display_action.get("clore_order_expires_at") if display_action else None,
            "clore_order_time_left_seconds": display_action.get("clore_order_time_left_seconds") if display_action else None,
            "clore_order_mrl_seconds": display_action.get("clore_order_mrl_seconds") if display_action else None,
            "offline_rescue_state": display_action.get("offline_rescue_state", "") if display_action else "",
            "offline_rescue_attempts": display_action.get("offline_rescue_attempts") if display_action else None,
            "offline_rescue_next_at": display_action.get("offline_rescue_next_at") if display_action else None,
            "is_connected": bool(worker.get("is_connected")),
            "hashrate_ths": round(hashrate, 2),
            "hashrate_live_ths": round(safe_float(worker.get("hashrate_live_ths")), 2),
            "hashrate_1h_ths": round(safe_float(worker.get("hashrate_1h_ths")), 2),
            "hashrate_24h_ths": round(safe_float(worker.get("hashrate_24h_ths")), 2),
            "difficulty": worker.get("difficulty"),
            "revenue_usd_hr": round_money(revenue_hr),
            "revenue_usd_day": round_money(revenue_day),
            "cost_usd_hr": round_money(cost_hr),
            "cost_usd_day": round_money(cost_day),
            "profit_usd_hr": round_money(profit_hr),
            "profit_usd_day": round_money(profit_day),
            "shares1h": safe_int(worker.get("shares1h")),
            "stale_shares1h": safe_int(worker.get("stale_shares1h")),
            "risks": risks,
        })

    workers.sort(
        key=lambda item: (
            not item.get("is_connected", False),
            -(item["profit_usd_day"] if item.get("profit_usd_day") is not None else -999999),
            -safe_float(item.get("hashrate_ths")),
            item.get("worker_name") or "",
        )
    )
    visible_worker_count = len(workers)
    visible_online_count = sum(1 for item in workers if item.get("is_connected"))
    visible_total_hashrate = sum(safe_float(item.get("hashrate_ths")) for item in workers)
    online_workers = [item for item in workers if item.get("is_connected")]
    online_revenue_usd_day = sum(safe_float(item.get("revenue_usd_day")) for item in online_workers if item.get("revenue_usd_day") is not None)
    online_profit_usd_day = sum(safe_float(item.get("profit_usd_day")) for item in online_workers if item.get("profit_usd_day") is not None)
    online_profit_usd_hr = sum(safe_float(item.get("profit_usd_hr")) for item in online_workers if item.get("profit_usd_hr") is not None)
    online_cost_usd_day = sum(safe_float(item.get("cost_usd_day")) for item in online_workers if item.get("cost_usd_day") is not None)
    online_cost_usd_hr = sum(safe_float(item.get("cost_usd_hr")) for item in online_workers if item.get("cost_usd_hr") is not None)
    prl_price_usd = safe_float(pearl.get("prl_price_usd"))
    online_gross_prl_day = online_revenue_usd_day / prl_price_usd if prl_price_usd > 0 else None
    online_net_prl_day = online_profit_usd_day / prl_price_usd if prl_price_usd > 0 else None

    provider_totals = {
        "vastai": {
            "provider": "Vast.ai",
            "online_worker_count": 0,
            "worker_count": 0,
            "total_hashrate_ths": 0.0,
            "online_revenue_usd_hr": 0.0,
            "online_revenue_usd_day": 0.0,
            "online_cost_usd_hr": 0.0,
            "online_cost_usd_day": 0.0,
            "online_profit_usd_hr": 0.0,
            "online_profit_usd_day": 0.0,
        },
        "clore": {
            "provider": "Clore",
            "online_worker_count": 0,
            "worker_count": 0,
            "total_hashrate_ths": 0.0,
            "online_revenue_usd_hr": 0.0,
            "online_revenue_usd_day": 0.0,
            "online_cost_usd_hr": 0.0,
            "online_cost_usd_day": 0.0,
            "online_profit_usd_hr": 0.0,
            "online_profit_usd_day": 0.0,
        },
    }
    for worker in workers:
        provider_text = str(worker.get("provider") or "")
        provider_key = "clore" if provider_text == "Clore" else "vastai" if provider_text == "Vast.ai" else ""
        if not provider_key:
            continue
        provider_totals[provider_key]["worker_count"] += 1
        if not worker.get("is_connected"):
            continue
        provider_totals[provider_key]["online_worker_count"] += 1
        provider_totals[provider_key]["total_hashrate_ths"] += safe_float(worker.get("hashrate_ths"))
        for key in (
            "revenue_usd_hr",
            "revenue_usd_day",
            "cost_usd_hr",
            "cost_usd_day",
            "profit_usd_hr",
            "profit_usd_day",
        ):
            value = worker.get(key)
            if value is None:
                continue
            provider_totals[provider_key][f"online_{key}"] += safe_float(value)
    for totals in provider_totals.values():
        totals["total_hashrate_ths"] = round(totals["total_hashrate_ths"], 2)
        for key in (
            "online_revenue_usd_hr",
            "online_revenue_usd_day",
            "online_cost_usd_hr",
            "online_cost_usd_day",
            "online_profit_usd_hr",
            "online_profit_usd_day",
        ):
            totals[key] = round_money(totals[key])

    return {
        "ok": any_ok,
        "wallet_address": akoya_wallet(),
        "is_online": visible_online_count > 0,
        "worker_count": visible_worker_count,
        "online_worker_count": visible_online_count,
        "total_hashrate_ths": round(visible_total_hashrate, 2),
        "pending_balance_prl": round(total_pending, 6),
        "total_paid_prl": round(total_paid, 6),
        "stale_rate24h_pct": round(max_stale, 3),
        "maturing_blocks": total_maturing,
        "next_maturity_eta_s": min(next_maturity_values) if next_maturity_values else 0,
        "online_totals": {
            "online_profit_usd_day": round_money(online_profit_usd_day),
            "online_profit_usd_hr": round_money(online_profit_usd_hr),
            "online_cost_usd_day": round_money(online_cost_usd_day),
            "online_cost_usd_hr": round_money(online_cost_usd_hr),
            "online_revenue_usd_day": round_money(online_revenue_usd_day),
            "online_gross_prl_day": round(online_gross_prl_day, 6) if online_gross_prl_day is not None else None,
            "online_net_prl_day": round(online_net_prl_day, 6) if online_net_prl_day is not None else None,
        },
        "provider_totals": provider_totals,
        "workers": workers,
        "pools": {
            pool: {
                "ok": ok,
                "wallet_address": payload.get("wallet_address", ""),
                "worker_count": safe_int(payload.get("worker_count")),
                "online_worker_count": safe_int(payload.get("online_worker_count")),
                "total_hashrate_ths": round(safe_float(payload.get("total_hashrate_ths")), 2),
                "pending_balance_prl": round(safe_float(payload.get("pending_balance_prl")), 6),
                "total_paid_prl": round(safe_float(payload.get("total_paid_prl")), 6),
            }
            for pool, payload, ok in pool_payloads
        },
    }


def build_network(raw: dict[str, dict[str, Any]], statuses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pearl = raw.get("monitor:pearl") or {}
    pearl_status = statuses.get("monitor:pearl", {})
    ok = bool(pearl_status.get("ok"))
    return {
        "ok": ok,
        "fallback": bool(pearl.get("_fallback") or pearl_status.get("fallback")),
        "fallback_age_s": safe_float(pearl.get("_fallback_age_s") or pearl_status.get("age_s")),
        "network_hashrate_ehs": safe_float(pearl.get("network_hashrate_ehs")),
        "network_hashrate_ths": safe_float(pearl.get("network_hashrate_ths")),
        "difficulty": safe_float(pearl.get("difficulty")),
        "blocks_per_day": safe_float(pearl.get("blocks_per_day")),
        "reward_per_block": safe_float(pearl.get("reward_per_block")),
        "prl_price_usd": safe_float(pearl.get("prl_price_usd")),
        "price_source": pearl.get("price_source", ""),
        "usd_per_th_per_day": pearl.get("usd_per_th_per_day", {}),
        "best_block_height": safe_int(pearl.get("best_block_height")),
    }


def summarize(opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"green": 0, "yellow": 0, "alert": 0, "red": 0, "gray": 0}
    for item in opportunities:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    best = next((item for item in opportunities if item["decision"] == "green"), None)
    return {
        "total_opportunities": len(opportunities),
        "counts": counts,
        "best": best,
    }


def summarize_by_gpu(opportunities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in opportunities:
        gpu = str(item.get("gpu") or "unknown")
        group = groups.setdefault(
            gpu,
            {
                "gpu": gpu,
                "total": 0,
                "green": 0,
                "yellow": 0,
                "alert": 0,
                "red": 0,
                "gray": 0,
                "min_cost_usd_hr": None,
                "max_cost_profit_usd_hr_per_gpu": None,
                "max_cost_profit_usd_day_per_gpu": None,
                "max_green_cost_usd_hr_per_gpu": None,
                "best_profit_usd_hr": None,
                "best_profit_usd_day": None,
                "best_roi_pct": None,
                "best_platform": "",
                "best_id": "",
                "best_url": "",
                "best_search_url": "",
                "best_pool": "",
                "best_hashrate_ths": None,
            },
        )
        decision = item.get("decision", "gray")
        group["total"] += 1
        group[decision] = group.get(decision, 0) + 1

        cost_hr = item.get("price_usd_hr")
        if cost_hr is not None:
            current_min = group["min_cost_usd_hr"]
            group["min_cost_usd_hr"] = cost_hr if current_min is None else min(current_min, cost_hr)

        revenue_hr = item.get("revenue_usd_hr")
        gpu_count = safe_int(item.get("gpu_count"), 1) or 1
        if revenue_hr is not None:
            max_cost_hr_per_gpu = revenue_hr / gpu_count
            current_max = group["max_cost_profit_usd_hr_per_gpu"]
            if current_max is None or max_cost_hr_per_gpu > current_max:
                group["max_cost_profit_usd_hr_per_gpu"] = round_money(max_cost_hr_per_gpu)
                group["max_cost_profit_usd_day_per_gpu"] = round_money(max_cost_hr_per_gpu * 24)
            max_green_hr = safe_float(item.get("max_safe_price_usd_hr")) / gpu_count
            current_green = group["max_green_cost_usd_hr_per_gpu"]
            if max_green_hr > 0 and (current_green is None or max_green_hr > current_green):
                group["max_green_cost_usd_hr_per_gpu"] = round_money(max_green_hr)

        profit_hr = item.get("profit_usd_hr")
        if profit_hr is None:
            continue
        current_best = group["best_profit_usd_hr"]
        if current_best is None or profit_hr > current_best:
            group["best_profit_usd_hr"] = profit_hr
            group["best_profit_usd_day"] = item.get("profit_usd_day")
            group["best_roi_pct"] = item.get("roi_pct")
            group["best_platform"] = item.get("platform", "")
            group["best_id"] = item.get("id", "")
            group["best_url"] = item.get("rental_url", "")
            group["best_search_url"] = item.get("search_url", "")
            group["best_pool"] = item.get("pool", "")
            group["best_hashrate_ths"] = item.get("hashrate_ths")

    out = list(groups.values())
    out.sort(
        key=lambda item: (
            -(item["best_profit_usd_hr"] if item["best_profit_usd_hr"] is not None else -999999),
            item["gpu"],
        )
    )
    return out


def compute_state(raw: dict[str, dict[str, Any]], actions: dict[str, Any], clore_actions: dict[str, Any] | None = None) -> dict[str, Any]:
    statuses = source_status(raw)
    opportunities = build_opportunities(raw, statuses, actions, clore_actions or {}, latest_blacklist)
    enrich_opportunities_with_scout_history(opportunities)
    operation = build_operation(raw, statuses, actions, clore_actions or {})
    return {
        "generated_at": now_ts(),
        "source_status": statuses,
        "network": build_network(raw, statuses),
        "operation": operation,
        "opportunities": opportunities,
        "gpu_summary": summarize_by_gpu(opportunities),
        "summary": summarize(opportunities),
        "vast_actions": vast_action_summary(actions, operation),
        "clore_actions": clore_action_summary(clore_actions or {}, operation),
        "snipers": build_snipers(actions, operation, latest_scout),
        "vast_blacklist": {
            "count": len(blacklist_items(latest_blacklist)),
            "items": blacklist_items(latest_blacklist),
        },
        "scout": latest_scout,
    }


async def load_raw_state() -> dict[str, dict[str, Any]]:
    global latest_pearl_payload
    assert redis_client is not None
    raw = await load_raw_monitor_state(redis_client, REDIS_KEYS)
    if pearl_payload_usable(raw.get("monitor:pearl")):
        await redis_set_json(redis_client, PEARL_LAST_GOOD_KEY, raw["monitor:pearl"])
    elif not pearl_payload_usable(latest_pearl_payload):
        cached = await redis_get_json(redis_client, PEARL_LAST_GOOD_KEY, {})
        if pearl_payload_usable(cached):
            latest_pearl_payload = dict(cached)
    return apply_pearl_fallback(raw)


async def load_vast_actions() -> dict[str, Any]:
    assert redis_client is not None
    data = await redis_get_json(redis_client, VAST_ACTIONS_KEY, {})
    return data if isinstance(data, dict) else {}


async def save_vast_actions(actions: dict[str, Any]) -> None:
    assert redis_client is not None
    await redis_set_json(redis_client, VAST_ACTIONS_KEY, actions)


async def load_clore_actions() -> dict[str, Any]:
    assert redis_client is not None
    data = await redis_get_json(redis_client, CLORE_ACTIONS_KEY, {})
    return data if isinstance(data, dict) else {}


async def save_clore_actions(actions: dict[str, Any]) -> None:
    assert redis_client is not None
    await redis_set_json(redis_client, CLORE_ACTIONS_KEY, actions)


async def load_scout_state() -> dict[str, Any]:
    assert redis_client is not None
    data = await redis_get_json(redis_client, SCOUT_STATE_KEY, scout_defaults())
    if not isinstance(data, dict):
        return scout_defaults()
    defaults = scout_defaults()
    data.setdefault("enabled", defaults["enabled"])
    data.setdefault("clore_auto_enabled", defaults.get("clore_auto_enabled", False))
    data.setdefault("tests", {})
    data.setdefault("queue", {})
    data.setdefault("clore_auto_queue", {})
    data.setdefault("radar", {})
    data["vast_gpu_triggers"] = scout_vast_gpu_triggers(data)
    data["settings"] = scout_settings(data)
    return data


def prune_scout_runtime_state(state: dict[str, Any]) -> bool:
    settings = scout_settings(state)
    tests = state.get("tests") if isinstance(state.get("tests"), dict) else {}
    active: dict[str, Any] = {}
    changed = False
    for test_id, test in tests.items():
        if not isinstance(test, dict):
            changed = True
            continue
        if test.get("status") != "testing":
            changed = True
            continue
        samples = test.get("samples")
        if isinstance(samples, list) and len(samples) > 180:
            test["samples"] = samples[-180:]
            changed = True
        active[str(test_id)] = test
    if active != tests:
        state["tests"] = active
        changed = True
    queue = state.get("queue") if isinstance(state.get("queue"), dict) else {}
    if not isinstance(state.get("queue"), dict):
        state["queue"] = {}
        changed = True
        queue = {}
    radar = state.get("radar") if isinstance(state.get("radar"), dict) else {}
    if not isinstance(state.get("radar"), dict):
        state["radar"] = {}
        changed = True
        radar = {}
    clore_auto_queue = state.get("clore_auto_queue") if isinstance(state.get("clore_auto_queue"), dict) else {}
    if not isinstance(state.get("clore_auto_queue"), dict):
        state["clore_auto_queue"] = {}
        changed = True
        clore_auto_queue = {}
    current = now_ts()
    kept_queue: dict[str, Any] = {}
    for ask_id, item in queue.items():
        if not isinstance(item, dict):
            changed = True
            continue
        if scout_mark_allowlist_blocked(item, settings):
            changed = True
            continue
        if item.get("transient_unavailable") and not scout_transient_retry_active(item, current):
            scout_expire_transient_retry(item)
            changed = True
        if scout_deprioritize_nonqueued_trigger(item):
            changed = True
        if not scout_operational_queue_item(item, current):
            if scout_radar_item_recent(item, current):
                radar[str(ask_id)] = item
            changed = True
            continue
        kept_queue[str(ask_id)] = item
    if len(kept_queue) > 200:
        sorted_items = sorted(
            kept_queue.items(),
            key=lambda pair: (
                pair[1].get("queue_status") == "queued",
                safe_float(pair[1].get("priority_score"), -999999),
                safe_float(pair[1].get("last_seen_at")),
            ),
            reverse=True,
        )
        kept_queue = dict(sorted_items[:200])
        changed = True
    if kept_queue != queue:
        state["queue"] = kept_queue
        changed = True
    kept_radar: dict[str, Any] = {}
    for ask_id, item in radar.items():
        if not isinstance(item, dict):
            changed = True
            continue
        if scout_mark_allowlist_blocked(item, settings):
            changed = True
        if item.get("transient_unavailable") and not scout_transient_retry_active(item, current):
            scout_expire_transient_retry(item)
            changed = True
        if scout_deprioritize_nonqueued_trigger(item):
            changed = True
        if scout_operational_queue_item(item, current):
            kept_queue[str(ask_id)] = item
            changed = True
            continue
        if scout_radar_item_recent(item, current):
            kept_radar[str(ask_id)] = item
        else:
            changed = True
    if len(kept_radar) > 160:
        sorted_radar = sorted(
            kept_radar.items(),
            key=lambda pair: (
                safe_float(pair[1].get("priority_score"), -999999),
                safe_float(pair[1].get("last_seen_at")),
            ),
            reverse=True,
        )
        kept_radar = dict(sorted_radar[:160])
        changed = True
    if kept_queue != state.get("queue"):
        state["queue"] = kept_queue
        changed = True
    if kept_radar != radar:
        state["radar"] = kept_radar
        changed = True
    active_test_ids = set(active.keys())
    kept_clore_auto_queue: dict[str, Any] = {}
    for server_id, item in clore_auto_queue.items():
        if not isinstance(item, dict):
            changed = True
            continue
        status = str(item.get("queue_status") or "")
        test_id = str(item.get("test_id") or "")
        if status in {"renting", "rented"} and test_id and test_id not in active_test_ids:
            item.update({
                "queue_status": "blocked",
                "sniper_status": "encerrado",
                "skip_reason": "Teste Scout encerrado; ver Results",
                "updated_at": current,
            })
            status = "blocked"
            changed = True
        next_retry = safe_float(item.get("next_retry_at"))
        last_seen = safe_float(item.get("last_seen_at") or item.get("updated_at") or item.get("first_seen_at"))
        if status == "cooldown" and next_retry > current:
            kept_clore_auto_queue[str(server_id)] = item
            continue
        if status in {"queued", "renting", "rented"}:
            kept_clore_auto_queue[str(server_id)] = item
            continue
        if last_seen > 0 and current - last_seen <= CLORE_AUTO_QUEUE_RETENTION_SECONDS:
            kept_clore_auto_queue[str(server_id)] = item
        else:
            changed = True
    if len(kept_clore_auto_queue) > 120:
        sorted_clore = sorted(
            kept_clore_auto_queue.items(),
            key=lambda pair: (
                pair[1].get("queue_status") == "queued",
                safe_float(pair[1].get("profit_usd_hr"), -999999),
                safe_float(pair[1].get("roi_pct"), -999999),
                safe_float(pair[1].get("last_seen_at")),
            ),
            reverse=True,
        )
        kept_clore_auto_queue = dict(sorted_clore[:120])
        changed = True
    if kept_clore_auto_queue != clore_auto_queue:
        state["clore_auto_queue"] = kept_clore_auto_queue
        changed = True
    return changed


async def save_scout_state(state: dict[str, Any]) -> None:
    assert redis_client is not None
    prune_scout_runtime_state(state)
    state["updated_at"] = now_ts()
    await redis_set_json(redis_client, SCOUT_STATE_KEY, state)


def results_defaults() -> dict[str, Any]:
    return {"updated_at": now_ts(), "queue": {}}


async def load_results_state() -> dict[str, Any]:
    assert redis_client is not None
    data = await redis_get_json(redis_client, RESULTS_STATE_KEY, results_defaults())
    if not isinstance(data, dict):
        return results_defaults()
    data.setdefault("queue", {})
    return data


async def save_results_state(state: dict[str, Any]) -> None:
    assert redis_client is not None
    queue = state.get("queue") if isinstance(state.get("queue"), dict) else {}
    settings = scout_settings({})
    current = now_ts()
    kept: dict[str, Any] = {}
    for item_id, item in queue.items():
        if not isinstance(item, dict):
            continue
        allowlist_reason = scout_gpu_allowlist_block_reason(item, settings)
        if allowlist_reason:
            item.update({
                "status": "blocked",
                "last_error": allowlist_reason,
                "next_retry_at": 0,
                "updated_at": current,
            })
        status = str(item.get("status") or "")
        updated = safe_float(item.get("updated_at") or item.get("created_at"))
        if status == "archived" and updated and updated < current - 86400:
            continue
        kept[str(item_id)] = item
    state["queue"] = kept
    state["updated_at"] = current
    await redis_set_json(redis_client, RESULTS_STATE_KEY, state)


def load_vast_blacklist() -> dict[str, Any]:
    data = load_json_dict(VAST_BLACKLIST_PATH, {"items": []})
    return data if isinstance(data.get("items"), list) else {"items": []}


def save_vast_blacklist(blacklist: dict[str, Any]) -> None:
    save_json(VAST_BLACKLIST_PATH, blacklist, indent=2)


def add_vast_blacklist_item(blacklist: dict[str, Any], action: dict[str, Any], reason: str) -> dict[str, Any]:
    item = {
        "scope": action.get("scope") or "machine",
        "created_at": now_ts(),
        "reason": reason or "Blacklist manual pelo dashboard",
        "ask_id": action.get("ask_id"),
        "instance_id": action.get("instance_id"),
        "worker_name": action.get("worker_name", ""),
        "gpu": action.get("gpu", ""),
        "gpu_count": action.get("gpu_count"),
        "host_id": action.get("host_id"),
        "machine_id": action.get("machine_id"),
        "price_usd_hr": action.get("price_usd_hr"),
        "status": action.get("vast_status_msg", ""),
    }
    if reason and "Destroy manual pelo Scout" in reason:
        item["source"] = "manual_scout_destroy"
    items = blacklist_items(blacklist)
    exists = any(
        str(existing.get("machine_id") or "") == str(item.get("machine_id") or "")
        and str(existing.get("gpu") or "") == str(item.get("gpu") or "")
        for existing in items
        if item.get("machine_id")
    )
    if not exists:
        items.insert(0, item)
    blacklist["items"] = items
    return item


def add_vast_gpu_model_blacklist_item(blacklist: dict[str, Any], gpu: Any, reason: str) -> dict[str, Any]:
    gpu_name = normalize_gpu_name(gpu)
    if not gpu_name:
        raise HTTPException(status_code=400, detail="GPU invalida para blacklist")
    current = now_ts()
    item = {
        "scope": "gpu_model",
        "gpu": gpu_name,
        "reason": reason or "Bloqueio por modelo via Results",
        "created_at": current,
    }
    items = blacklist_items(blacklist)
    exists = any(
        str(existing.get("scope") or "") == "gpu_model"
        and normalize_gpu_name(existing.get("gpu")) == gpu_name
        for existing in items
    )
    if not exists:
        items.insert(0, item)
    blacklist["items"] = items
    return item


def vast_instance_worker_name(instance: dict[str, Any]) -> str:
    for item in instance.get("extra_env") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            key, value = item[0], item[1]
        elif isinstance(item, dict):
            key, value = item.get("key") or item.get("name"), item.get("value")
        else:
            continue
        if key in {"AKOYA_POOL_WORKER", "PEARL_WORKER"}:
            return str(value or "").strip()
    label = str(instance.get("label") or "")
    for part in label.split():
        if part.startswith("vast-"):
            return part.strip()
    return ""


def vast_instance_pool_strategy(instance: dict[str, Any]) -> str:
    image_text = " ".join(
        str(instance.get(key) or "")
        for key in (
            "image",
            "docker_image",
            "template_image",
            "status_msg",
            "actual_status",
        )
    ).lower()
    if any(marker in image_text for marker in ("alphamine", "alpha-miner", "pearl_")):
        return "alphamine"
    if any(marker in image_text for marker in ("akoya", "akoya-miner")):
        return "akoya"
    for item in instance.get("extra_env") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            key = item[0]
        elif isinstance(item, dict):
            key = item.get("key") or item.get("name")
        else:
            continue
        if key in {"PEARL_ADDRESS", "PEARL_WORKER", "PEARL_POOL_HOST"}:
            return "alphamine"
        if key in {"AKOYA_POOL_WALLET", "AKOYA_POOL_WORKER"}:
            return "akoya"
    label = str(instance.get("label") or "").lower()
    if "alphamine" in label or "alpha" in label:
        return "alphamine"
    return "akoya"


def ask_id_from_vast_worker(worker_name: str) -> str:
    base_name = base_vast_worker_name(worker_name)
    if not base_name.startswith("vast-"):
        return ""
    ask_id = base_name.removeprefix("vast-")
    return ask_id if ask_id.isdigit() else ""


def vast_instance_price_hr(instance: dict[str, Any], fallback: Any = None) -> float | None:
    price = safe_float(
        instance.get("dph_total")
        or instance.get("search", {}).get("discountedTotalPerHour")
        or instance.get("search", {}).get("totalHour")
        or fallback
    )
    return round_money(price) if price > 0 else round_money(safe_float(fallback)) if fallback is not None else None


def upsert_action_from_vast_instance(actions: dict[str, Any], instance: dict[str, Any]) -> bool:
    worker_name = vast_instance_worker_name(instance)
    ask_id = ask_id_from_vast_worker(worker_name)
    if not ask_id:
        return False

    now = now_ts()
    action = actions.get(ask_id)
    created = not isinstance(action, dict)
    if created:
        action = {
            "ask_id": safe_int(ask_id),
            "worker_name": worker_name,
            "created_at": now,
            "reason": "Instancia Vast detectada pela API; sincronizada automaticamente",
        }
        actions[ask_id] = action

    assert isinstance(action, dict)
    gpu_name = normalize_gpu_name(instance.get("gpu_name")) or instance.get("gpu_name") or action.get("gpu", "")
    actual_pool_strategy = vast_instance_pool_strategy(instance)
    pool_strategy = action.get("pool_strategy") or actual_pool_strategy
    cur_state = str(instance.get("cur_state") or instance.get("next_state") or "")
    actual_status = str(instance.get("actual_status") or "")
    status_msg = str(instance.get("status_msg") or "")

    before = dict(action)
    action.update({
        "state": "rented",
        "ask_id": safe_int(ask_id),
        "worker_name": worker_name,
        "gpu": gpu_name,
        "pool_strategy": pool_strategy,
        "vast_pool_strategy_actual": actual_pool_strategy,
        "gpu_count": safe_int(instance.get("num_gpus"), safe_int(action.get("gpu_count"), 1)),
        "price_usd_hr": vast_instance_price_hr(instance, action.get("price_usd_hr")),
        "instance_id": instance.get("id") or action.get("instance_id"),
        "host_id": instance.get("host_id") or action.get("host_id"),
        "machine_id": instance.get("machine_id") or action.get("machine_id"),
        "vast_cur_state": cur_state,
        "vast_actual_status": actual_status,
        "vast_status_msg": status_msg,
        "updated_at": now,
    })
    if created or str(before.get("state")) == "archived":
        action["reason"] = "Instancia Vast ativa; sincronizada automaticamente"
    if cur_state.lower() in {"destroyed", "deleted", "offline"}:
        action["state"] = "archived"
        action["reason"] = f"Arquivada automaticamente; estado Vast={cur_state}"
    return before != action


async def sync_vast_actions_with_instances(actions: dict[str, Any]) -> dict[str, Any]:
    global last_vast_instance_detail_sync_at
    if not vast_api_key():
        return actions
    changed = False
    async with httpx.AsyncClient(timeout=12) as client:
        try:
            response = await client.get(f"{VAST_API_BASE_URL}/api/v0/instances/", headers=vast_headers())
            if response.status_code < 400:
                data = response.json()
                instances = data.get("instances") if isinstance(data, dict) else []
                if isinstance(instances, list):
                    live_instance_ids = {instance.get("id") for instance in instances if isinstance(instance, dict)}
                    for instance in instances:
                        if isinstance(instance, dict):
                            changed = upsert_action_from_vast_instance(actions, instance) or changed
                    for action in actions.values():
                        if not isinstance(action, dict) or action.get("state") not in {"renting", "rented"}:
                            continue
                        instance_id = action.get("instance_id")
                        if instance_id and instance_id not in live_instance_ids:
                            action["state"] = "archived"
                            action["reason"] = "Arquivada automaticamente; instancia nao aparece mais na Vast"
                            action["updated_at"] = now_ts()
                            changed = True
        except httpx.HTTPError:
            pass

        current = now_ts()
        run_detail_sync = (
            VAST_INSTANCE_DETAIL_SYNC_INTERVAL_SECONDS > 0
            and current - last_vast_instance_detail_sync_at >= VAST_INSTANCE_DETAIL_SYNC_INTERVAL_SECONDS
        )
        if not run_detail_sync:
            if changed:
                await save_vast_actions(actions)
            return actions
        last_vast_instance_detail_sync_at = current

        active_actions = [
            (ask_id, action)
            for ask_id, action in list(actions.items())
            if isinstance(action, dict)
            and action.get("state") in {"renting", "rented"}
            and action.get("instance_id")
        ]
        semaphore = asyncio.Semaphore(8)

        async def fetch_instance_detail(ask_id: str, action: dict[str, Any]) -> tuple[str, dict[str, Any], int | None, dict[str, Any] | None]:
            async with semaphore:
                instance_id = action.get("instance_id")
                try:
                    response = await client.get(
                        f"{VAST_API_BASE_URL}/api/v0/instances/{instance_id}/",
                        headers=vast_headers(),
                    )
                except httpx.HTTPError:
                    return ask_id, action, None, None
                if response.status_code >= 400:
                    return ask_id, action, response.status_code, None
                data = response.json()
                return ask_id, action, response.status_code, data if isinstance(data, dict) else {}

        detail_results = await asyncio.gather(
            *(fetch_instance_detail(str(ask_id), action) for ask_id, action in active_actions),
            return_exceptions=True,
        )
        for detail_result in detail_results:
            if isinstance(detail_result, Exception):
                continue
            ask_id, action, status_code, data = detail_result
            if not isinstance(action, dict):
                continue
            instance_id = action.get("instance_id")
            if status_code == 404:
                action["state"] = "archived"
                action["reason"] = "Arquivada automaticamente; instancia nao existe mais na Vast"
                action["updated_at"] = now_ts()
                changed = True
                continue
            if not status_code or status_code >= 400 or not isinstance(data, dict):
                continue
            instance = data.get("instances") if isinstance(data, dict) else None
            if isinstance(instance, list):
                instance = instance[0] if instance else None
            if instance is None and isinstance(data, dict) and data.get("id"):
                instance = data
            if not isinstance(instance, dict):
                action["state"] = "archived"
                action["reason"] = "Arquivada automaticamente; instancia nao aparece mais na Vast"
                action["updated_at"] = now_ts()
                changed = True
                continue
            cur_state = str(instance.get("cur_state") or instance.get("next_state") or "")
            actual_status = str(instance.get("actual_status") or "")
            status_msg = str(instance.get("status_msg") or "")
            actual_pool_strategy = vast_instance_pool_strategy(instance)
            action["vast_cur_state"] = cur_state
            action["vast_actual_status"] = actual_status
            action["vast_status_msg"] = status_msg
            action["vast_pool_strategy_actual"] = actual_pool_strategy
            action["host_id"] = instance.get("host_id") or action.get("host_id")
            action["machine_id"] = instance.get("machine_id") or action.get("machine_id")
            action["price_usd_hr"] = round_money(
                safe_float(
                    instance.get("dph_total")
                    or instance.get("search", {}).get("discountedTotalPerHour")
                    or instance.get("search", {}).get("totalHour")
                    or action.get("price_usd_hr")
                )
            )
            if cur_state.lower() in {"destroyed", "deleted", "offline"}:
                action["state"] = "archived"
                action["reason"] = f"Arquivada automaticamente; estado Vast={cur_state}"
            changed = True
    if changed:
        await save_vast_actions(actions)
    return actions


def clore_action_should_watch(action: dict[str, Any]) -> bool:
    if not CLORE_RERENT_APPROVED_ENABLED:
        return False
    if action.get("clore_rerent_disabled"):
        return False
    if action.get("state") in {"blacklisted", "cancelled", "archived"}:
        return False
    if action.get("clore_watch_approved"):
        return True
    if action.get("scout_final") or action.get("scout_approved"):
        return True
    return safe_float(action.get("scout_final_profit_usd_hr"), -999999) >= SCOUT_MIN_PROFIT_USD_HR


def clore_transient_blacklist_should_watch(action: dict[str, Any]) -> bool:
    if not isinstance(action, dict) or action.get("state") != "blacklisted":
        return False
    reason = str(action.get("reason") or "")
    error = str(action.get("error") or "")
    text = f"{reason} {error}".lower()
    if "nao conseguiu iniciar" not in text:
        return False
    transient_markers = (
        "order_not_active",
        "ficou rented",
        "http 500",
        "http 502",
        "bad gateway",
        "currency-not-allowed",
    )
    return any(marker in text for marker in transient_markers)


def restore_clore_watch_action(action: dict[str, Any], server_id: int, reason: str) -> bool:
    previous = dict(action)
    successful_pool = str(((action.get("create_result") or {}).get("pool_strategy")) or action.get("scout_final_pool") or "akoya").strip().lower()
    if successful_pool not in clore.pool_strategies():
        successful_pool = "akoya"
    current = now_ts()
    action.update({
        "state": "watching",
        "pool_strategy": successful_pool,
        "worker_name": clore.strategy_worker_name(successful_pool, server_id),
        "clore_watch_approved": True,
        "clore_rerent_enabled": True,
        "clore_rerent_next_at": min(safe_float(action.get("clore_rerent_next_at")) or current, current),
        "clore_rerent_error": "",
        "reason": reason,
        "updated_at": current,
    })
    action.pop("blacklisted_at", None)
    action.pop("blacklist_reason", None)
    action.pop("scout_test_id", None)
    return previous != action


async def sync_clore_actions_with_orders(actions: dict[str, Any], force: bool = False) -> dict[str, Any]:
    global last_clore_order_sync_at
    if not actions or not clore.api_key():
        return actions
    changed = False
    for key, action in list(actions.items()):
        if not isinstance(action, dict):
            continue
        if clore_transient_blacklist_should_watch(action):
            server_id = safe_int(action.get("server_id") or key)
            if server_id > 0 and restore_clore_watch_action(
                action,
                server_id,
                "Watch Clore: falha transitoria ao alternar pool; aguardando server voltar para realugar",
            ):
                actions[str(server_id)] = action
                changed = True
    if changed:
        await save_clore_actions(actions)
    has_active = any(
        isinstance(action, dict) and action.get("state") in {"renting", "rented", "watching"}
        for action in actions.values()
    )
    if not has_active:
        return actions
    current = now_ts()
    if not force and current - last_clore_order_sync_at < CLORE_ORDER_SYNC_INTERVAL_SECONDS:
        return actions
    last_clore_order_sync_at = current
    try:
        payload = await clore.my_orders(return_completed=False)
    except Exception as exc:
        now = now_ts()
        for action in actions.values():
            if isinstance(action, dict) and action.get("state") in {"renting", "rented"}:
                action["order_sync_error"] = getattr(exc, "detail", str(exc))
                action["updated_at"] = now
                changed = True
        if changed:
            await save_clore_actions(actions)
        return actions

    now = now_ts()
    orders = payload.get("orders") or []
    by_server = {str(order.get("si") or ""): order for order in orders if isinstance(order, dict)}
    for server_id, action in list(actions.items()):
        if not isinstance(action, dict):
            continue
        order = by_server.get(str(server_id))
        before = dict(action)
        if not order:
            if action.get("state") in {"renting", "rented"}:
                if clore_action_should_watch(action):
                    action["state"] = "watching"
                    action["reason"] = "Ordem Clore expirou/sumiu; aguardando server voltar para realugar"
                    action["clore_rerent_enabled"] = True
                    action["clore_rerent_next_at"] = min(
                        safe_float(action.get("clore_rerent_next_at")) or now,
                        now,
                    )
                else:
                    action["state"] = "failed"
                    action["reason"] = "Ordem Clore nao aparece mais em my_orders"
                action["updated_at"] = now
        else:
            native_price_day = safe_float(order.get("price")) or safe_float(action.get("native_price_day"))
            order_ct = safe_float(order.get("ct"))
            order_mrl = safe_int(order.get("mrl"))
            expires_at = order_ct + order_mrl if order_ct > 0 and order_mrl > 0 else None
            time_left = max(0.0, expires_at - now) if expires_at else None
            expired = bool(order.get("expired"))
            next_state = "failed" if expired else "rented"
            if expired and clore_action_should_watch(action):
                next_state = "watching"
            action.update({
                "order_id": order.get("id") or action.get("order_id"),
                "state": next_state,
                "server_id": safe_int(server_id),
                "native_price_day": native_price_day,
                "price_usd_day": action.get("price_usd_day"),
                "price_usd_hr": action.get("price_usd_hr"),
                "currency": order.get("currency") or action.get("currency", ""),
                "image": order.get("image") or action.get("image", ""),
                "clore_server_id": order.get("si"),
                "clore_order_expired": bool(order.get("expired")),
                "clore_order_created_at": order_ct or action.get("clore_order_created_at"),
                "clore_order_mrl_seconds": order_mrl or action.get("clore_order_mrl_seconds"),
                "clore_order_expires_at": expires_at or action.get("clore_order_expires_at"),
                "clore_order_time_left_seconds": round(time_left) if time_left is not None else action.get("clore_order_time_left_seconds"),
                "clore_online": order.get("online"),
                "clore_spend": order.get("spend"),
                "clore_mon_container": order.get("mon_container"),
                "clore_pub_cluster": order.get("pub_cluster") or [],
                "clore_tcp_ports": order.get("tcp_ports") or [],
                "order_sync_error": "",
                "updated_at": now,
            })
            if expired and clore_action_should_watch(action):
                action["reason"] = "Ordem Clore expirada; aguardando server voltar para realugar"
                action["clore_rerent_enabled"] = True
                action["clore_rerent_next_at"] = min(safe_float(action.get("clore_rerent_next_at")) or now, now)
        changed = changed or before != action
    if changed:
        await save_clore_actions(actions)
    return actions


async def sync_clore_wallets(force: bool = False) -> dict[str, Any]:
    global last_clore_wallet_sync_at, latest_clore_wallets
    if not clore.api_key():
        latest_clore_wallets = {}
        return latest_clore_wallets
    current = now_ts()
    if not force and current - last_clore_wallet_sync_at < CLORE_ORDER_SYNC_INTERVAL_SECONDS:
        return latest_clore_wallets
    last_clore_wallet_sync_at = current
    try:
        payload = await clore.wallets()
        payload["updated_at"] = now_ts()
        latest_clore_wallets = payload
    except Exception as exc:
        latest_clore_wallets = {
            "wallets": latest_clore_wallets.get("wallets", []) if isinstance(latest_clore_wallets, dict) else [],
            "error": getattr(exc, "detail", str(exc)),
            "updated_at": now_ts(),
        }
    return latest_clore_wallets


def vast_rescue_action_is_good(action: dict[str, Any]) -> bool:
    if action.get("offline_rescue_enabled") is True:
        return True
    if action.get("scout_final") or action.get("scout_approved") or action.get("scout_final_approved"):
        return True
    profit = safe_float(action.get("scout_final_profit_usd_hr"), -999999)
    return profit >= SCOUT_MIN_PROFIT_USD_HR


def vast_rescue_archived_reason(action: dict[str, Any]) -> bool:
    reason = str(action.get("reason") or "").lower()
    return "arquivada automaticamente" in reason or "estado vast=offline" in reason


def vast_rescue_pool(action: dict[str, Any]) -> str:
    pool = str(action.get("pool_strategy") or action.get("vast_pool_strategy_actual") or "akoya").strip().lower()
    return pool if pool in vast_pool_strategies() else "akoya"


def vast_rescue_target(action: dict[str, Any], ask_id: Any) -> dict[str, Any]:
    max_price = (
        safe_float(action.get("max_safe_price_usd_hr"))
        or safe_float(action.get("price_usd_hr"))
        or safe_float(scout_settings().get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR)
    )
    return {
        "ask_id": safe_int(action.get("ask_id") or ask_id),
        "instance_id": action.get("instance_id"),
        "gpu": action.get("gpu"),
        "gpu_count": action.get("gpu_count"),
        "host_id": action.get("host_id"),
        "machine_id": action.get("machine_id"),
        "price_usd_hr": action.get("price_usd_hr"),
        "max_price_usd_hr": max_price,
        "preferred_pool": vast_rescue_pool(action),
        "pool_strategy": vast_rescue_pool(action),
        "pcie": action.get("pcie"),
        "cuda": action.get("cuda"),
        "reliability": action.get("reliability"),
        "net_up_mbps": action.get("net_up_mbps"),
        "net_down_mbps": action.get("net_down_mbps"),
    }


def vast_rescue_worker_offline(action: dict[str, Any], ask_id: Any, operation: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    pool = vast_rescue_pool(action)
    worker_name = str(action.get("worker_name") or strategy_worker_name(pool, ask_id))
    worker = find_operation_worker(operation, worker_name, pool)
    if worker and worker.get("is_connected"):
        return False, worker
    if worker:
        return True, worker
    actual_status = str(action.get("vast_actual_status") or "").strip().lower()
    cur_state = str(action.get("vast_cur_state") or "").strip().lower()
    if actual_status == "offline" or cur_state == "offline":
        return True, None
    return False, None


async def maybe_queue_vast_rescue_regrab(
    actions: dict[str, Any],
    action: dict[str, Any],
    ask_id: str,
    state: dict[str, Any],
    scout: dict[str, Any],
    current: float,
) -> bool:
    if not VAST_OFFLINE_RESCUE_REGRAB_ENABLED:
        return False
    if not vast_rescue_action_is_good(action) or not vast_rescue_archived_reason(action):
        return False
    if safe_float(action.get("offline_rescue_regrab_next_at")) > current:
        return False

    results_state = await load_results_state()
    target = vast_rescue_target(action, ask_id)
    queue_item = results_upsert_queue_item(
        results_state,
        "hardware",
        target,
        "Rescue Vast: aguardando mesmo hardware voltar ao marketplace",
    )
    queue_item.update({
        "source": "vast_offline_rescue",
        "manual_override": True,
        "allowlist_bypass": True,
        "next_retry_at": 0,
    })
    await results_attempt_queue_item(results_state, queue_item, state, actions, scout, force=True)
    await save_results_state(results_state)

    status = str(queue_item.get("status") or "")
    last_ask_id = safe_int(queue_item.get("last_ask_id") or queue_item.get("ask_id") or ask_id)
    started = status == "started"
    if started:
        new_action = action_by_id(actions, last_ask_id)
        if new_action:
            new_action.update({
                "offline_rescue_enabled": True,
                "offline_rescue_state": "regrab_started",
                "offline_rescue_source_ask_id": safe_int(ask_id),
                "offline_rescue_regrab_started_at": current,
                "offline_rescue_regrab_queue_id": queue_item.get("id"),
            })
            actions[str(last_ask_id)] = new_action
        return True

    action.update({
        "offline_rescue_enabled": True,
        "offline_rescue_state": "regrab_waiting",
        "offline_rescue_regrab_queued_at": action.get("offline_rescue_regrab_queued_at") or current,
        "offline_rescue_regrab_last_at": current,
        "offline_rescue_regrab_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
        "offline_rescue_regrab_queue_id": queue_item.get("id"),
        "offline_rescue_regrab_status": status,
        "offline_rescue_regrab_error": queue_item.get("last_error", ""),
        "updated_at": current,
    })
    actions[str(ask_id)] = action
    return True


async def maybe_rescue_vast_offline_actions(actions: dict[str, Any], state: dict[str, Any], scout: dict[str, Any]) -> bool:
    if not VAST_OFFLINE_RESCUE_ENABLED:
        return False
    current = now_ts()
    changed = False
    operation = state.get("operation") if isinstance(state.get("operation"), dict) else {}

    for ask_id, action in list(actions.items()):
        if not isinstance(action, dict):
            continue
        state_name = str(action.get("state") or "")
        if state_name == "archived":
            changed = await maybe_queue_vast_rescue_regrab(actions, action, str(ask_id), state, scout, current) or changed
            continue
        if state_name not in {"renting", "rented"}:
            continue
        if not vast_rescue_action_is_good(action):
            continue
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            continue

        offline, worker = vast_rescue_worker_offline(action, ask_id, operation)
        if not offline:
            if worker and action.get("offline_rescue_state") and action.get("offline_rescue_state") != "online":
                action.update({
                    "offline_rescue_state": "online",
                    "offline_rescue_next_at": 0,
                    "offline_rescue_online_at": current,
                    "offline_rescue_last_error": "",
                    "updated_at": current,
                })
                actions[str(ask_id)] = action
                changed = True
            continue

        if not safe_float(action.get("offline_rescue_first_seen_at")):
            action.update({
                "offline_rescue_enabled": True,
                "offline_rescue_state": "waiting_retry",
                "offline_rescue_first_seen_at": current,
                "offline_rescue_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
                "updated_at": current,
            })
            actions[str(ask_id)] = action
            changed = True
            continue

        next_at = safe_float(action.get("offline_rescue_next_at"))
        if next_at > current:
            continue

        attempts = safe_int(action.get("offline_rescue_attempts")) + 1
        try:
            recycle_result = await recycle_vast_instance(instance_id)
            action.update({
                "offline_rescue_enabled": True,
                "offline_rescue_state": "recycling",
                "offline_rescue_attempts": attempts,
                "offline_rescue_last_at": current,
                "offline_rescue_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
                "offline_rescue_result": recycle_result,
                "offline_rescue_last_error": "",
                "reason": f"Rescue automatico: worker offline; recycle sem trocar imagem (tentativa {attempts})",
                "updated_at": current,
            })
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            action.update({
                "offline_rescue_enabled": True,
                "offline_rescue_state": "retry_error",
                "offline_rescue_attempts": attempts,
                "offline_rescue_last_at": current,
                "offline_rescue_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
                "offline_rescue_last_error": str(detail),
                "reason": f"Rescue automatico: recycle falhou; retry em {VAST_OFFLINE_RESCUE_INTERVAL_SECONDS // 60} min",
                "updated_at": current,
            })
        actions[str(ask_id)] = action
        changed = True
    return changed


def clore_watch_has_active_test(scout: dict[str, Any], server_id: int) -> bool:
    tests = scout.get("tests") if isinstance(scout.get("tests"), dict) else {}
    return any(
        isinstance(test, dict)
        and str(test.get("provider") or "").lower() == "clore"
        and safe_int(test.get("server_id") or test.get("offer_id")) == server_id
        and test.get("status") == "testing"
        for test in tests.values()
    )


async def maybe_rerent_clore_watch_actions(
    actions: dict[str, Any],
    clore_actions: dict[str, Any],
    state: dict[str, Any],
    scout: dict[str, Any],
) -> bool:
    if not CLORE_RERENT_APPROVED_ENABLED:
        return False
    current = now_ts()
    changed = False
    for key, action in list(clore_actions.items()):
        if not isinstance(action, dict):
            continue
        if action.get("state") != "watching" or not clore_action_should_watch(action):
            continue
        server_id = safe_int(action.get("server_id") or key)
        if server_id <= 0:
            continue
        if clore_watch_has_active_test(scout, server_id):
            continue
        if safe_float(action.get("clore_rerent_next_at")) > current:
            continue
        opportunity = find_clore_opportunity_by_id(state, server_id)
        pool = str(action.get("scout_final_pool") or action.get("pool_strategy") or "akoya").strip().lower()
        if pool not in clore.pool_strategies():
            pool = "akoya"
        rent_option = ((opportunity or {}).get("rent_options") or {}).get(pool) or {}
        if not opportunity or rent_option.get("state") != "ready":
            reason = "Server Clore ainda nao voltou ao marketplace"
            if opportunity:
                reason = rent_option.get("reason") or "Server Clore ainda nao esta pronto para realugar"
            action.update({
                "clore_rerent_enabled": True,
                "clore_rerent_last_at": current,
                "clore_rerent_next_at": current + CLORE_RERENT_INTERVAL_SECONDS,
                "clore_rerent_error": reason,
                "reason": f"Watch Clore: {reason}; retry em {CLORE_RERENT_INTERVAL_SECONDS // 60} min",
                "updated_at": current,
            })
            clore_actions[str(server_id)] = action
            changed = True
            continue
        try:
            test = await start_scout_clore_rent(
                scout,
                actions,
                clore_actions,
                state,
                server_id,
                pool,
                opportunity_override=opportunity,
            )
            new_action = action_by_id(clore_actions, server_id)
            if new_action:
                new_action.update({
                    "clore_rerent_enabled": True,
                    "clore_rerent_started_at": current,
                    "clore_rerent_error": "",
                    "reason": f"Watch Clore realugou server {server_id}; teste {test.get('test_id')}",
                    "updated_at": now_ts(),
                })
                clore_actions[str(server_id)] = new_action
            changed = True
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            action.update({
                "clore_rerent_enabled": True,
                "clore_rerent_last_at": current,
                "clore_rerent_next_at": current + CLORE_RERENT_INTERVAL_SECONDS,
                "clore_rerent_error": str(detail),
                "reason": f"Watch Clore: realuguel falhou; retry em {CLORE_RERENT_INTERVAL_SECONDS // 60} min",
                "updated_at": current,
            })
            clore_actions[str(server_id)] = action
            changed = True
    if changed:
        await save_clore_actions(clore_actions)
        await save_scout_state(scout)
    return changed


async def refresh_state_unlocked(run_scout_autostart: bool = False) -> dict[str, Any]:
    global latest_state, latest_actions, latest_clore_actions, latest_blacklist, latest_scout
    raw = await load_raw_state()
    latest_blacklist = load_vast_blacklist()
    latest_actions = await load_vast_actions()
    latest_actions = await sync_vast_actions_with_instances(latest_actions)
    latest_clore_actions = await load_clore_actions()
    latest_clore_actions = await sync_clore_actions_with_orders(latest_clore_actions)
    await sync_clore_wallets()
    latest_scout = await load_scout_state()
    latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    scout_changed = adopt_orphan_scout_tests(latest_scout, latest_actions, latest_state)
    if scout_changed:
        await save_vast_actions(latest_actions)
    scout_changed = await evaluate_scout_state(latest_scout, latest_actions, latest_state, latest_clore_actions) or scout_changed
    latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    clore_watch_changed = await maybe_rerent_clore_watch_actions(latest_actions, latest_clore_actions, latest_state, latest_scout)
    if clore_watch_changed:
        latest_clore_actions = await load_clore_actions()
        latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    rescue_changed = await maybe_rescue_vast_offline_actions(latest_actions, latest_state, latest_scout)
    if rescue_changed:
        await save_vast_actions(latest_actions)
        latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    if run_scout_autostart and await maybe_autostart_scout(latest_scout, latest_actions, latest_state):
        scout_changed = True
        latest_actions = await load_vast_actions()
        latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    if await maybe_autostart_clore_scout(latest_scout, latest_actions, latest_clore_actions, latest_state):
        scout_changed = True
        latest_clore_actions = await load_clore_actions()
        latest_state = compute_state(raw, latest_actions, latest_clore_actions)
    if scout_changed:
        await save_scout_state(latest_scout)
    record_worker_history(latest_state.get("operation") or {})
    return latest_state


async def refresh_state() -> dict[str, Any]:
    async with vast_actions_lock:
        return await refresh_state_unlocked()


async def broadcast(state: dict[str, Any]) -> None:
    if not clients:
        return
    payload = json.dumps(state, ensure_ascii=False)
    disconnected = []
    for ws in clients:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        clients.discard(ws)


def find_opportunity_by_id(state: dict[str, Any], ask_id: int) -> dict[str, Any] | None:
    for item in state.get("opportunities", []):
        if item.get("platform") == "vastai" and str(item.get("id")) == str(ask_id):
            return item
    return None


def find_clore_opportunity_by_id(state: dict[str, Any], server_id: int) -> dict[str, Any] | None:
    for item in state.get("opportunities", []):
        if item.get("platform") == "clore" and str(item.get("id")) == str(server_id):
            return item
    return None


def find_operation_worker(operation: dict[str, Any], worker_name: str, pool: str) -> dict[str, Any] | None:
    base_name = base_vast_worker_name(worker_name)
    for worker in operation.get("workers", []):
        if worker.get("pool") != pool:
            continue
        if base_vast_worker_name(worker.get("worker_name")) == base_name:
            return worker
    return None


def scout_sample_from_worker(test: dict[str, Any], worker: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    hashrate = safe_float(worker.get("hashrate_live_ths") if worker else 0.0)
    if hashrate <= 0 and worker:
        hashrate = safe_float(worker.get("hashrate_ths"))
    rates = (state.get("network") or {}).get("usd_per_th_per_day") or {}
    rate_day = safe_float(rates.get(test.get("pool_strategy")))
    revenue_hr = (hashrate * rate_day / 24) if rate_day else None
    cost_hr = safe_float(test.get("price_usd_hr"))
    profit_hr = revenue_hr - cost_hr if revenue_hr is not None else None
    return {
        "ts": now_ts(),
        "hashrate_ths": round(hashrate, 4),
        "revenue_usd_hr": round_money(revenue_hr),
        "profit_usd_hr": round_money(profit_hr),
    }


def scout_result_from_test(test: dict[str, Any], decision: str, reason: str) -> dict[str, Any]:
    samples = [s for s in test.get("samples", []) if isinstance(s, dict)]
    hashes = [safe_float(s.get("hashrate_ths")) for s in samples if safe_float(s.get("hashrate_ths")) > 0]
    profits = [safe_float(s.get("profit_usd_hr")) for s in samples if s.get("profit_usd_hr") is not None]
    avg_hash = sum(hashes) / len(hashes) if hashes else 0.0
    best_hash = max(hashes) if hashes else 0.0
    avg_profit = sum(profits) / len(profits) if profits else None
    expected = safe_float(test.get("expected_ths"))
    result = {
        "test_id": test.get("test_id"),
        "provider": test.get("provider") or "vastai",
        "offer_id": test.get("offer_id") or test.get("server_id") or test.get("ask_id"),
        "ask_id": test.get("ask_id"),
        "server_id": test.get("server_id"),
        "order_id": test.get("order_id"),
        "currency": test.get("currency"),
        "image": test.get("image"),
        "instance_id": test.get("instance_id"),
        "worker_name": test.get("worker_name"),
        "host_id": test.get("host_id"),
        "machine_id": test.get("machine_id"),
        "gpu": test.get("gpu"),
        "gpu_count": test.get("gpu_count"),
        "pool_strategy": test.get("pool_strategy"),
        "price_usd_hr": test.get("price_usd_hr"),
        "expected_ths": round_money(expected),
        "vast_cur_state": test.get("vast_cur_state", ""),
        "vast_actual_status": test.get("vast_actual_status", ""),
        "vast_status_msg": test.get("vast_status_msg", ""),
        "started_at": test.get("stage_started_at") or test.get("started_at"),
        "worker_seen_at": test.get("worker_seen_at"),
        "ended_at": now_ts(),
        "live_ths_avg": round(avg_hash, 4),
        "live_ths_best": round(best_hash, 4),
        "hash_ratio": round(avg_hash / expected, 4) if expected > 0 and avg_hash > 0 else 0.0,
        "revenue_usd_hr": round_money((avg_profit or 0) + safe_float(test.get("price_usd_hr"))) if avg_profit is not None else None,
        "profit_usd_hr": round_money(avg_profit),
        "decision": decision,
        "reason": reason,
    }
    for key in (
        "retest_allowed",
        "retest_reason",
        "previous_result_summary",
        "improvement_summary",
        "queue_priority_score",
        "machine_key",
        "is_new_machine",
        "machine_first_seen_at",
        "marketplace_first_seen_at",
        "marketplace_last_seen_at",
        "source",
        "source_label",
        "auto_decision",
        "auto_decision_label",
        "auto_log",
        "trigger_id",
        "trigger_name",
        "trigger_max_price_usd_hr",
        "opportunity_decision",
        "risks",
        "failure_tag",
        "manual_next_pool_strategy",
        "pcie",
        "cuda",
        "reliability",
        "net_up_mbps",
        "net_down_mbps",
    ):
        if key in test:
            result[key] = test.get(key)
    return result


def scout_price_gate_applies(test: dict[str, Any]) -> bool:
    provider = str(test.get("provider") or "vastai").lower()
    if provider != "clore":
        return True
    return str(test.get("opportunity_decision") or "").lower() == "green"


def scout_expected_ths(gpu_name: Any, gpu_count: Any) -> float:
    gpu_data = get_gpu(gpu_name)
    return round(safe_float((gpu_data or {}).get("ths")) * max(1, safe_int(gpu_count, 1)), 4)


def scout_pool_result_is_viable(result: dict[str, Any], min_profit_usd_hr: float, min_hash_ratio: float) -> bool:
    return safe_float(result.get("profit_usd_hr"), -999999) >= min_profit_usd_hr and safe_float(result.get("hash_ratio")) >= min_hash_ratio


def scout_pool_results(test: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in test.get("prior_results") or [] if isinstance(item, dict)]


def scout_best_pool_result(test: dict[str, Any], min_profit_usd_hr: float, min_hash_ratio: float) -> dict[str, Any] | None:
    viable = [item for item in scout_pool_results(test) if scout_pool_result_is_viable(item, min_profit_usd_hr, min_hash_ratio)]
    if not viable:
        return None
    return max(viable, key=lambda item: safe_float(item.get("profit_usd_hr"), -999999))


def seal_scout_action(
    actions: dict[str, Any],
    test: dict[str, Any],
    pool_strategy: str,
    profit_usd_hr: float | None,
    reason: str,
    decision: str,
) -> bool:
    ask_id = str(test.get("ask_id") or "")
    action = action_by_id(actions, ask_id)
    if not action:
        return False
    current = now_ts()
    action.update({
        "state": "rented",
        "pool_strategy": pool_strategy,
        "worker_name": strategy_worker_name(pool_strategy, ask_id),
        "reason": reason,
        "scout_final": True,
        "scout_approved": True,
        "scout_final_decision": decision,
        "scout_final_pool": pool_strategy,
        "scout_final_profit_usd_hr": round_money(profit_usd_hr),
        "scout_final_at": current,
        "scout_final_test_id": test.get("test_id"),
        "updated_at": current,
    })
    for key in (
        "scout_test_id",
        "switch_target_pool",
        "return_target_pool",
        "switch_error",
    ):
        action.pop(key, None)
    actions[ask_id] = action
    return True


def scout_next_action_label(test: dict[str, Any], settings: dict[str, Any]) -> str:
    decision = str(test.get("decision") or "")
    if decision == "returning_best_pool":
        return f"Voltar para {strategy_label(test.get('return_target_pool') or test.get('pool_strategy'))}"
    if decision in {"waiting_worker", "switching_pool"}:
        return f"Aguardar worker {strategy_label(test.get('pool_strategy'))}"
    if decision in {"measuring", "testing_pool"}:
        return f"Medindo {strategy_label(test.get('pool_strategy'))}"
    next_pool = scout_next_untested_pool(test, settings)
    if settings.get("pool_switch_mode") == "in_place_ab" and next_pool:
        return f"Trocar para {strategy_label(next_pool)}"
    if settings.get("pool_switch_mode") == "recreate" and next_pool:
        return f"Recriar em {strategy_label(next_pool)}"
    return "Manter ou destruir"


def public_scout_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ask_id",
        "gpu",
        "gpu_count",
        "price_usd_hr",
        "expected_ths",
        "profit_usd_hr",
        "roi_pct",
        "host_id",
        "machine_id",
        "cuda",
        "pcie",
        "reliability",
        "net_up_mbps",
        "net_down_mbps",
        "risks",
        "machine_key",
        "is_new_machine",
        "machine_first_seen_at",
        "first_seen_at",
        "last_seen_at",
        "priority_score",
        "queue_status",
        "sniper_status",
        "skip_reason",
        "transient_unavailable",
        "retry_started_at",
        "last_retry_at",
        "next_retry_at",
        "retry_until_at",
        "retry_attempts",
        "last_retry_error",
        "sniped_at",
        "retest_allowed",
        "retest_reason",
        "previous_result_summary",
        "improvement_summary",
        "source",
        "trigger_id",
        "trigger_name",
        "trigger_gpu_match",
        "trigger_created_at",
        "trigger_max_price_usd_hr",
        "max_price_usd_hr",
    )
    return {key: item.get(key) for key in keys if key in item}


def scout_transient_vast_error(detail: Any) -> bool:
    text = str(detail or "").lower()
    transient_markers = (
        "no_such_ask",
        "no such ask",
        "no longer available",
        "not available",
        "not rentable",
        "nao esta mais disponivel",
        "não esta mais disponivel",
        "não está mais disponível",
        "ask voltou indisponivel",
        "ask voltou indisponível",
    )
    return any(marker in text for marker in transient_markers)


def scout_vast_rate_limit_error(detail: Any) -> bool:
    text = str(detail or "").lower()
    return "429" in text or "too many requests" in text or "api requests too frequent" in text


def scout_transient_retry_due(item: dict[str, Any], current: float | None = None) -> bool:
    if not item.get("transient_unavailable"):
        return False
    current = current or now_ts()
    retry_until = safe_float(item.get("retry_until_at"))
    next_retry = safe_float(item.get("next_retry_at"))
    return retry_until > 0 and current <= retry_until and next_retry > 0 and current >= next_retry


def scout_transient_retry_active(item: dict[str, Any], current: float | None = None) -> bool:
    if not item.get("transient_unavailable"):
        return False
    current = current or now_ts()
    retry_until = safe_float(item.get("retry_until_at"))
    next_retry = safe_float(item.get("next_retry_at"))
    return retry_until > 0 and current <= retry_until and next_retry > 0


def scout_reset_transient_retry(item: dict[str, Any]) -> None:
    for key in (
        "transient_unavailable",
        "retry_started_at",
        "last_retry_at",
        "next_retry_at",
        "retry_until_at",
        "retry_attempts",
        "last_retry_error",
        "marketplace_absent_at",
    ):
        item.pop(key, None)


def scout_expire_transient_retry(item: dict[str, Any]) -> bool:
    if not item.get("transient_unavailable"):
        return False
    for key in (
        "transient_unavailable",
        "retry_started_at",
        "last_retry_at",
        "next_retry_at",
        "retry_until_at",
        "retry_attempts",
        "last_retry_error",
    ):
        item.pop(key, None)
    item["queue_status"] = "cooldown"
    item["sniper_status"] = "aguardando nova aparicao"
    item["skip_reason"] = "Janela de retry Vast encerrou; aguardando nova aparicao"
    return True


def scout_operational_queue_item(item: dict[str, Any], current: float | None = None) -> bool:
    status = str(item.get("queue_status") or "")
    if status in {"queued", "renting", "rented"}:
        return True
    return status == "cooldown" and scout_transient_retry_active(item, current)


def scout_radar_item_recent(item: dict[str, Any], current: float | None = None) -> bool:
    current = current or now_ts()
    status = str(item.get("queue_status") or "")
    if status not in {"blocked", "lost", "cooldown"}:
        return False
    last_seen = safe_float(item.get("last_seen_at") or item.get("updated_at") or item.get("first_seen_at"))
    return bool(last_seen and last_seen >= current - SCOUT_RADAR_RETENTION_SECONDS)


def scout_deprioritize_nonqueued_trigger(item: dict[str, Any]) -> bool:
    if item.get("source") != "trigger" or item.get("queue_status") == "queued":
        return False
    if safe_float(item.get("priority_score"), -999999) < 10000:
        return False
    item["priority_score"] = round(
        safe_float(item.get("profit_usd_hr")) * 120 + safe_float(item.get("roi_pct")) * 0.35,
        4,
    )
    return True


def scout_history_pool_results(item: dict[str, Any]) -> list[dict[str, Any]]:
    results = [result for result in item.get("prior_results") or [] if isinstance(result, dict)]
    if item.get("pool_strategy"):
        results.append(item)
    return results


def scout_history_matches(opportunity: dict[str, Any], item: dict[str, Any]) -> bool:
    provider = str(opportunity.get("platform") or "").lower()
    item_provider = str(item.get("provider") or "").lower()
    opportunity_id = str(opportunity.get("id") or "")
    item_ids = {
        str(value)
        for value in (
            item.get("offer_id"),
            item.get("ask_id"),
            item.get("server_id"),
            item.get("id"),
        )
        if value not in {None, ""}
    }
    if provider and item_provider and provider == item_provider and opportunity_id and opportunity_id in item_ids:
        return True

    machine_id = str(opportunity.get("machine_id") or "")
    host_id = str(opportunity.get("host_id") or "")
    gpu = str(opportunity.get("gpu") or "")
    gpu_count = safe_int(opportunity.get("gpu_count"), 1)
    item_machine = str(item.get("machine_id") or "")
    item_host = str(item.get("host_id") or "")
    item_gpu = str(item.get("gpu") or "")
    item_gpu_count = safe_int(item.get("gpu_count"), 1)
    if machine_id and item_machine and machine_id == item_machine:
        return True
    return bool(host_id and item_host and host_id == item_host and gpu == item_gpu and gpu_count == item_gpu_count)


def scout_hardware_history(opportunity: dict[str, Any], limit: int = 500) -> list[dict[str, Any]]:
    matches = [item for item in scout_history_items()[:limit] if isinstance(item, dict) and scout_history_matches(opportunity, item)]
    matches.sort(key=lambda item: safe_float(item.get("ended_at")), reverse=True)
    return matches


def scout_history_record_key(item: dict[str, Any]) -> str:
    for key in ("test_id", "order_id", "instance_id"):
        value = item.get(key)
        if value not in {None, ""}:
            return f"{key}:{value}"
    provider = item.get("provider") or ""
    offer_id = item.get("offer_id") or item.get("server_id") or item.get("ask_id") or ""
    started_at = item.get("started_at") or item.get("ended_at") or ""
    return f"fallback:{provider}:{offer_id}:{started_at}"


def scout_unique_history_records(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(history, key=lambda record: safe_float(record.get("ended_at")), reverse=True):
        key = scout_history_record_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def scout_active_tests_for_opportunity(opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    tests = latest_scout.get("tests") if isinstance(latest_scout, dict) else {}
    if not isinstance(tests, dict):
        return []
    matches = [
        test
        for test in tests.values()
        if isinstance(test, dict)
        and test.get("status") == "testing"
        and scout_history_matches(opportunity, test)
    ]
    matches.sort(key=lambda item: safe_float(item.get("started_at") or item.get("stage_started_at")), reverse=True)
    return matches


def scout_record_hash_values(record: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for result in scout_history_pool_results(record):
        value = safe_float(result.get("live_ths_avg"))
        if value <= 0:
            value = safe_float(result.get("latest_hashrate_ths"))
        if value <= 0:
            value = safe_float(result.get("live_ths_best"))
        if value > 0:
            values.append(value)
    if values:
        return values
    samples = [sample for sample in record.get("samples") or [] if isinstance(sample, dict)]
    sample_hashes = [safe_float(sample.get("hashrate_ths")) for sample in samples if safe_float(sample.get("hashrate_ths")) > 0]
    if sample_hashes:
        return [sum(sample_hashes) / len(sample_hashes)]
    latest = safe_float(record.get("latest_hashrate_ths"))
    return [latest] if latest > 0 else []


def scout_opportunity_history_summary(opportunity: dict[str, Any]) -> dict[str, Any]:
    history = scout_unique_history_records(scout_hardware_history(opportunity))
    active = scout_active_tests_for_opportunity(opportunity)
    active_keys = {scout_history_record_key(item) for item in active}
    records = active + [item for item in history if scout_history_record_key(item) not in active_keys]
    hashes: list[float] = []
    for item in records:
        hashes.extend(scout_record_hash_values(item))
    latest = records[0] if records else {}
    best_profit = None
    for item in records:
        for result in scout_history_pool_results(item):
            profit = safe_float(result.get("profit_usd_hr"), -999999)
            if profit > -999999 and (best_profit is None or profit > best_profit):
                best_profit = profit
    return {
        "history_seen": bool(records),
        "history_count": len(records),
        "history_completed_count": len(history),
        "history_active_count": len(active),
        "history_avg_ths": round_money(sum(hashes) / len(hashes)) if hashes else None,
        "history_best_ths": round_money(max(hashes)) if hashes else None,
        "history_last_ths": round_money(hashes[0]) if hashes else None,
        "history_last_decision": latest.get("decision") or latest.get("status") or "",
        "history_last_pool": latest.get("pool_strategy") or "",
        "history_last_at": latest.get("ended_at") or latest.get("started_at") or latest.get("stage_started_at"),
        "history_best_profit_usd_hr": round_money(best_profit),
    }


def enrich_opportunities_with_scout_history(opportunities: list[dict[str, Any]]) -> None:
    for opportunity in opportunities:
        opportunity.update(scout_opportunity_history_summary(opportunity))


def scout_result_quality(result: dict[str, Any], settings: dict[str, Any]) -> str:
    decision = str(result.get("decision") or "")
    profit = safe_float(result.get("profit_usd_hr"), -999999)
    ratio = safe_float(result.get("hash_ratio"))
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    min_ratio = safe_float(settings.get("min_hash_ratio"), SCOUT_MIN_HASH_RATIO)
    if profit >= min_profit or (ratio >= 0.8 and profit >= min_profit - 0.10):
        return "good"
    if decision in {"destroy", "blacklist", "failed", "no_worker", "offline"}:
        return "bad"
    if ratio and ratio < min_ratio:
        return "bad"
    if profit < min_profit:
        return "bad"
    return "neutral"


def scout_previous_summary(history: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any] | None:
    if not history:
        return None
    best_profit = None
    best_ratio = None
    quality = "neutral"
    latest = history[0]
    for item in history:
        for result in scout_history_pool_results(item):
            profit = safe_float(result.get("profit_usd_hr"), -999999)
            ratio = safe_float(result.get("hash_ratio"))
            if best_profit is None or profit > best_profit:
                best_profit = profit
            if best_ratio is None or ratio > best_ratio:
                best_ratio = ratio
            result_quality = scout_result_quality(result, settings)
            if result_quality == "good":
                quality = "good"
            elif result_quality == "bad" and quality != "good":
                quality = "bad"
    return {
        "ask_id": latest.get("ask_id"),
        "instance_id": latest.get("instance_id"),
        "ended_at": latest.get("ended_at"),
        "price_usd_hr": latest.get("price_usd_hr"),
        "best_profit_usd_hr": round_money(best_profit),
        "best_hash_ratio": round_money(best_ratio),
        "quality": quality,
        "count": len(history),
    }


def scout_retest_decision(opportunity: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    history = scout_hardware_history(opportunity)
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    if not history:
        current_profit = safe_float(opportunity.get("profit_usd_hr"), -999999)
        if current_profit < min_profit:
            return {
                "allowed": False,
                "reason": f"lucro previsto ${current_profit:.2f}/h abaixo do minimo ${min_profit:.2f}/h",
                "previous": None,
                "improvement": "novo hardware sem lucro minimo",
            }
        return {"allowed": True, "reason": "maquina sem historico", "previous": None, "improvement": "novo hardware"}
    previous = scout_previous_summary(history, settings) or {}
    current = now_ts()
    previous_price = safe_float(previous.get("price_usd_hr"))
    current_price = safe_float(opportunity.get("price_usd_hr"))
    previous_profit = safe_float(previous.get("best_profit_usd_hr"), -999999)
    current_profit = safe_float(opportunity.get("profit_usd_hr"), -999999)
    previous_count = safe_int((history[0] or {}).get("gpu_count"), 1)
    current_count = safe_int(opportunity.get("gpu_count"), 1)
    age_days = (current - safe_float(previous.get("ended_at"))) / 86400 if previous.get("ended_at") else 999
    improvements: list[str] = []
    if previous_price > 0 and current_price > 0 and current_price <= previous_price * 0.85:
        improvements.append("preco caiu >=15%")
    profit_meets_minimum = current_profit >= min_profit
    if profit_meets_minimum and current_profit > -999999 and (
        (previous_profit <= 0 and current_profit > 0)
        or (previous_profit > 0 and current_profit >= previous_profit * 1.20)
    ):
        improvements.append("lucro previsto subiu >=20%")
    if current_count > previous_count:
        improvements.append("gpu_count aumentou")
    if age_days >= 7:
        improvements.append("historico >7 dias")
    if previous.get("quality") == "good" and current_price <= safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR):
        improvements.append("historico bom e preco dentro do teto")
    if improvements and profit_meets_minimum:
        return {"allowed": True, "reason": "; ".join(improvements), "previous": previous, "improvement": "; ".join(improvements)}
    if improvements:
        return {
            "allowed": False,
            "reason": f"{'; '.join(improvements)}; lucro previsto ${current_profit:.2f}/h abaixo do minimo ${min_profit:.2f}/h",
            "previous": previous,
            "improvement": "; ".join(improvements),
        }
    return {"allowed": False, "reason": "machine ja testada sem melhoria", "previous": previous, "improvement": "sem melhoria forte"}


def scout_queue_block_reason(opportunity: dict[str, Any], settings: dict[str, Any], actions: dict[str, Any]) -> str:
    if opportunity.get("platform") != "vastai":
        return "somente Vast entra no Scout"
    allowlist_reason = scout_gpu_allowlist_block_reason(opportunity, settings)
    if allowlist_reason:
        return allowlist_reason
    gpu_data = get_gpu(opportunity.get("gpu"))
    if not gpu_data or not gpu_data.get("supported", False):
        return "gpu nao permitida"
    price_hr = safe_float(opportunity.get("price_usd_hr"))
    if price_hr <= 0:
        return "preco invalido"
    max_price = safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR)
    if price_hr > max_price:
        return f"preco acima do teto Scout ${max_price:.2f}/h"
    existing = action_by_id(actions, opportunity.get("id"))
    if existing and existing.get("state") in {"renting", "rented"}:
        return "ask ja ativo"
    hardware_reason = scout_hardware_block_reason(opportunity)
    if hardware_reason:
        return hardware_reason
    risks = set(opportunity.get("risks") or [])
    if "network_bad" in risks:
        return "rede ruim"
    return ""


def scout_trigger_hard_block_reason(
    opportunity: dict[str, Any],
    trigger: dict[str, Any],
    actions: dict[str, Any],
    settings: dict[str, Any],
) -> str:
    if opportunity.get("platform") != "vastai":
        return "trigger somente Vast"
    allowlist_reason = scout_gpu_allowlist_block_reason(opportunity, settings)
    if allowlist_reason:
        return allowlist_reason
    gpu = normalize_trigger_gpu(opportunity.get("gpu"))
    if gpu != normalize_trigger_gpu(trigger.get("gpu_match")):
        return "gpu diferente do trigger"
    wanted_count = max(1, safe_int(trigger.get("gpu_count"), 1))
    if safe_int(opportunity.get("gpu_count"), 1) != wanted_count:
        return f"qtd GPU diferente do trigger x{wanted_count}"
    gpu_data = get_gpu(opportunity.get("gpu"))
    if not gpu_data or not gpu_data.get("supported", False):
        return "gpu nao permitida"
    price_hr = safe_float(opportunity.get("price_usd_hr"))
    max_price = safe_float(trigger.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR)
    if price_hr <= 0:
        return "preco invalido"
    if price_hr > max_price:
        return f"preco acima do trigger ${max_price:.2f}/h"
    existing = action_by_id(actions, opportunity.get("id"))
    if existing and existing.get("state") in {"renting", "rented"}:
        return "ask ja ativo"
    hardware_reason = scout_hardware_block_reason(opportunity)
    if hardware_reason:
        return hardware_reason
    risks = set(opportunity.get("risks") or [])
    if "network_bad" in risks:
        return "rede ruim"
    history = scout_hardware_history(opportunity)
    if history:
        min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
        current_profit = safe_float(opportunity.get("profit_usd_hr"), -999999)
        if current_profit < min_profit:
            return f"machine ja testada; lucro previsto ${current_profit:.2f}/h abaixo do minimo ${min_profit:.2f}/h"
    return ""


def scout_trigger_visible_after_create(
    opportunity: dict[str, Any],
    trigger: dict[str, Any],
    previous_item: dict[str, Any] | None,
    current: float,
) -> bool:
    created_at = safe_float(trigger.get("created_at"))
    if created_at <= 0:
        return True
    ask_id = str(opportunity.get("id") or "")
    ignored = ask_id and ask_id in set(trigger.get("ignore_ask_ids") or [])
    first_seen = safe_float((previous_item or {}).get("first_seen_at")) or current
    reappeared = bool((previous_item or {}).get("marketplace_absent_at")) and current >= created_at
    if ignored and not reappeared:
        return False
    return first_seen >= created_at or reappeared


def scout_matching_vast_gpu_trigger(
    opportunity: dict[str, Any],
    triggers: list[dict[str, Any]],
    previous_item: dict[str, Any] | None,
    current: float,
) -> dict[str, Any] | None:
    if opportunity.get("platform") != "vastai":
        return None
    gpu = normalize_trigger_gpu(opportunity.get("gpu"))
    for trigger in triggers:
        if not trigger.get("enabled"):
            continue
        if gpu != normalize_trigger_gpu(trigger.get("gpu_match")):
            continue
        if safe_int(opportunity.get("gpu_count"), 1) != max(1, safe_int(trigger.get("gpu_count"), 1)):
            continue
        if scout_trigger_visible_after_create(opportunity, trigger, previous_item, current):
            return trigger
    return None


def scout_queue_priority(opportunity: dict[str, Any], retest: dict[str, Any], settings: dict[str, Any]) -> float:
    profit = safe_float(opportunity.get("profit_usd_hr"))
    roi = safe_float(opportunity.get("roi_pct"))
    price = safe_float(opportunity.get("price_usd_hr"))
    max_price = safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR)
    rank = scout_gpu_rank(opportunity.get("gpu"))
    risks = set(opportunity.get("risks") or [])
    score = profit * 120 + roi * 0.35 + max(0, 180 - rank) * 0.08 + safe_int(opportunity.get("gpu_count"), 1) * 2
    if max_price > 0 and price > 0:
        score += max(0.0, (max_price - price) / max_price) * 30
    if not retest.get("previous"):
        score += 20
    if retest.get("allowed") and (retest.get("previous") or {}).get("quality") == "good":
        score += 15
    if "pcie_below_rule" in risks:
        score -= 18
    if "reliability_watch" in risks:
        score -= 10
    if "reliability_low" in risks:
        score -= 25
    if "network_watch" in risks:
        score -= 10
    if safe_int(opportunity.get("gpu_count"), 1) >= 4 and price > max_price * 0.75:
        score -= 8
    return round(score, 4)


def scout_queue_item_from_opportunity(
    opportunity: dict[str, Any],
    settings: dict[str, Any],
    actions: dict[str, Any],
    previous_item: dict[str, Any] | None = None,
    machine_existed: bool = False,
    machine_record: dict[str, Any] | None = None,
    baseline_at: float = 0.0,
    triggers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    current = now_ts()
    trigger = scout_matching_vast_gpu_trigger(opportunity, triggers or [], previous_item, current)
    retest = scout_retest_decision(opportunity, settings)
    block_reason = scout_trigger_hard_block_reason(opportunity, trigger, actions, settings) if trigger else scout_queue_block_reason(opportunity, settings, actions)
    status = "blocked" if block_reason else "queued"
    machine_key = scout_machine_key_from_item(opportunity)
    if status == "queued" and not machine_key:
        status = "blocked"
        block_reason = "sem machine/host para sniper"
    machine_first_seen_at = safe_float((machine_record or {}).get("first_seen_at")) or current
    is_new_machine = bool(machine_key and baseline_at > 0 and machine_first_seen_at > baseline_at)
    if status == "queued" and not is_new_machine and not trigger:
        status = "blocked"
        block_reason = "machine ja vista; fora do sniper novo"
    if status == "queued" and not is_new_machine and not trigger and not retest.get("allowed"):
        status = "blocked"
        block_reason = retest.get("reason") or "machine ja testada sem melhoria"
    item = {
        "ask_id": safe_int(opportunity.get("id")),
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "price_usd_hr": opportunity.get("price_usd_hr"),
        "expected_ths": opportunity.get("hashrate_ths"),
        "profit_usd_hr": opportunity.get("profit_usd_hr"),
        "roi_pct": opportunity.get("roi_pct"),
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "cuda": opportunity.get("cuda"),
        "pcie": opportunity.get("pcie"),
        "reliability": opportunity.get("reliability"),
        "net_up_mbps": opportunity.get("net_up_mbps"),
        "net_down_mbps": opportunity.get("net_down_mbps"),
        "risks": opportunity.get("risks") or [],
        "machine_key": machine_key,
        "is_new_machine": is_new_machine,
        "machine_first_seen_at": machine_first_seen_at,
        "sniper_baseline_at": baseline_at,
        "first_seen_at": (previous_item or {}).get("first_seen_at") or current,
        "last_seen_at": current,
        "priority_score": scout_queue_priority(opportunity, retest, settings),
        "queue_status": status,
        "skip_reason": block_reason,
        "retest_allowed": bool(retest.get("allowed")),
        "retest_reason": retest.get("reason", ""),
        "previous_result_summary": retest.get("previous"),
        "improvement_summary": retest.get("improvement", ""),
    }
    if trigger:
        item.update({
            "source": "trigger",
            "trigger_id": trigger.get("id"),
            "trigger_name": trigger.get("name"),
            "trigger_gpu_match": trigger.get("gpu_match"),
            "trigger_created_at": trigger.get("created_at"),
            "trigger_max_price_usd_hr": trigger.get("max_price_usd_hr"),
            "max_price_usd_hr": trigger.get("max_price_usd_hr"),
            "retest_reason": f"trigger Vast {trigger.get('name')}" if status == "queued" else item.get("retest_reason"),
            "improvement_summary": "trigger Vast" if status == "queued" else item.get("improvement_summary"),
        })
        if status == "queued":
            item["retest_allowed"] = True
            item["priority_score"] = max(
                safe_float(scout_queue_priority(opportunity, retest, settings)),
                100000 + safe_float(opportunity.get("profit_usd_hr")),
            )
            item["sniper_status"] = "trigger Vast"
    if previous_item and previous_item.get("transient_unavailable"):
        retry_until = safe_float(previous_item.get("retry_until_at"))
        if previous_item.get("marketplace_absent_at") and status == "queued":
            scout_reset_transient_retry(item)
        elif retry_until and current <= retry_until:
            for key in (
                "transient_unavailable",
                "retry_started_at",
                "last_retry_at",
                "next_retry_at",
                "retry_until_at",
                "retry_attempts",
                "last_retry_error",
            ):
                if key in previous_item:
                    item[key] = previous_item.get(key)
            item["queue_status"] = "cooldown"
            item["sniper_status"] = "retry Vast" if scout_transient_retry_due(item, current) else "aguardando Vast"
            item["skip_reason"] = item.get("last_retry_error") or "Ask indisponivel na Vast; aguardando retry"
        else:
            for key in (
                "transient_unavailable",
                "retry_started_at",
                "last_retry_at",
                "next_retry_at",
                "retry_until_at",
                "retry_attempts",
                "last_retry_error",
                "marketplace_absent_at",
            ):
                if key in previous_item:
                    item[key] = previous_item.get(key)
            item["queue_status"] = "cooldown"
            item["sniper_status"] = "aguardando Vast"
            item["skip_reason"] = "Janela de retry Vast encerrou; aguardando nova aparicao"
    elif previous_item and previous_item.get("queue_status") in {"renting", "rented"}:
        item["queue_status"] = previous_item.get("queue_status")
    if item.get("source") == "trigger" and item.get("queue_status") != "queued":
        item["priority_score"] = scout_queue_priority(opportunity, retest, settings)
        scout_deprioritize_nonqueued_trigger(item)
    return item


def update_scout_queue_from_opportunities(scout: dict[str, Any], actions: dict[str, Any], state: dict[str, Any]) -> bool:
    settings = scout_settings(scout)
    triggers = scout_vast_gpu_triggers(scout)
    queue = scout.get("queue") if isinstance(scout.get("queue"), dict) else {}
    radar = scout.get("radar") if isinstance(scout.get("radar"), dict) else {}
    index_payload = scout_machine_index_payload()
    machine_index = index_payload.get("machines") if isinstance(index_payload.get("machines"), dict) else {}
    baseline_at = safe_float(index_payload.get("baseline_at"))
    baseline_created = baseline_at <= 0
    if baseline_at <= 0:
        baseline_at = now_ts()
        index_payload["baseline_at"] = baseline_at
        scout["sniper_baseline_at"] = baseline_at
        machine_index_changed = True
    else:
        machine_index_changed = False
    current_ids: set[str] = set()
    changed = False
    active_asks = {
        str(test.get("ask_id"))
        for test in (scout.get("tests") or {}).values()
        if isinstance(test, dict) and test.get("status") == "testing" and test.get("ask_id")
    }
    for opportunity in state.get("opportunities", []):
        if opportunity.get("platform") != "vastai":
            continue
        ask_id = str(opportunity.get("id") or "")
        if not ask_id:
            continue
        current_ids.add(ask_id)
        previous = queue.get(ask_id) if isinstance(queue.get(ask_id), dict) else None
        if previous is None:
            previous = radar.get(ask_id) if isinstance(radar.get(ask_id), dict) else None
        machine_existed, index_changed, machine_record = touch_scout_machine_index(machine_index, opportunity, "seen")
        if baseline_created and not machine_existed and machine_record:
            machine_record["first_seen_at"] = baseline_at
            machine_index[machine_record["machine_key"]] = machine_record
            index_changed = True
        machine_index_changed = machine_index_changed or index_changed
        item = scout_queue_item_from_opportunity(
            opportunity,
            settings,
            actions,
            previous,
            machine_existed,
            machine_record,
            baseline_at,
            triggers,
        )
        if ask_id in active_asks:
            item["queue_status"] = "rented"
            item["skip_reason"] = "teste ativo"
        if item != previous:
            queue[ask_id] = item
            changed = True

    for ask_id, item in list(queue.items()):
        if not isinstance(item, dict):
            queue.pop(ask_id, None)
            changed = True
            continue
        if scout_mark_allowlist_blocked(item, settings):
            changed = True
            continue
        if ask_id not in current_ids and item.get("source") == "trigger":
            item["queue_status"] = "cooldown"
            item["sniper_status"] = "aguardando Vast"
            item["skip_reason"] = "ask do trigger sumiu da Vast; aguardando nova aparicao"
            item["marketplace_absent_at"] = item.get("marketplace_absent_at") or now_ts()
            if item.get("transient_unavailable"):
                item["next_retry_at"] = 0
            changed = True
        elif ask_id not in current_ids and item.get("transient_unavailable"):
            item["queue_status"] = "cooldown"
            item["sniper_status"] = "aguardando Vast"
            item["skip_reason"] = "ask sumiu da Vast; aguardando nova aparicao"
            item["marketplace_absent_at"] = item.get("marketplace_absent_at") or now_ts()
            item["next_retry_at"] = 0
            changed = True
        elif ask_id not in current_ids and item.get("queue_status") == "queued":
            item["queue_status"] = "lost"
            item["skip_reason"] = "ask sumiu da Vast antes do aluguel"
            changed = True
        elif ask_id not in current_ids and not item.get("marketplace_absent_at"):
            item["marketplace_absent_at"] = now_ts()
            changed = True
    current = now_ts()
    operational_queue: dict[str, Any] = {}
    radar_items: dict[str, Any] = {}
    for ask_id, item in queue.items():
        if not isinstance(item, dict):
            changed = True
            continue
        if scout_mark_allowlist_blocked(item, settings):
            changed = True
        if item.get("transient_unavailable") and not scout_transient_retry_active(item, current):
            scout_expire_transient_retry(item)
            changed = True
        if scout_deprioritize_nonqueued_trigger(item):
            changed = True
        if scout_operational_queue_item(item, current):
            operational_queue[str(ask_id)] = item
        elif scout_radar_item_recent(item, current):
            radar_items[str(ask_id)] = item
        else:
            changed = True
    for ask_id, item in radar.items():
        if ask_id in operational_queue or ask_id in radar_items or not isinstance(item, dict):
            continue
        if scout_radar_item_recent(item, current):
            radar_items[str(ask_id)] = item
    if operational_queue != scout.get("queue"):
        changed = True
    if radar_items != scout.get("radar"):
        changed = True
    scout["queue"] = operational_queue
    scout["radar"] = radar_items
    scout["sniper_baseline_at"] = baseline_at
    if machine_index_changed:
        save_scout_machine_index(machine_index, baseline_at)
    return changed


def scout_queue_counts(queue: dict[str, Any]) -> dict[str, int]:
    counts = {"queued": 0, "renting": 0, "rented": 0, "lost": 0, "blocked": 0, "cooldown": 0}
    for item in queue.values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("queue_status") or "blocked")
        counts[status] = counts.get(status, 0) + 1
    return counts


def clore_auto_queue(scout: dict[str, Any]) -> dict[str, Any]:
    queue = scout.get("clore_auto_queue")
    if not isinstance(queue, dict):
        queue = {}
        scout["clore_auto_queue"] = queue
    return queue


def clore_auto_active_server_ids(scout: dict[str, Any], clore_actions: dict[str, Any]) -> set[str]:
    active: set[str] = set()
    tests = scout.get("tests") if isinstance(scout.get("tests"), dict) else {}
    for test in tests.values():
        if not isinstance(test, dict) or test.get("status") != "testing":
            continue
        if str(test.get("provider") or "").lower() != "clore":
            continue
        server_id = test.get("server_id") or test.get("offer_id")
        if server_id not in {None, ""}:
            active.add(str(server_id))
    for key, action in clore_actions.items():
        if not isinstance(action, dict) or action.get("state") not in {"renting", "rented"}:
            continue
        server_id = action.get("server_id") or key
        if server_id not in {None, ""}:
            active.add(str(server_id))
    return active


def clore_auto_candidate_strategy(opportunity: dict[str, Any]) -> tuple[str, str]:
    pool = str(opportunity.get("pool") or "").strip().lower()
    if pool not in clore.pool_strategies():
        return "", "pool Clore ausente"
    option = ((opportunity.get("rent_options") or {}).get(pool) or {})
    if option.get("state") != "ready":
        return "", option.get("reason") or f"{clore.strategy_label(pool)} nao pronto"
    return pool, ""


def clore_auto_history_bad_reason(opportunity: dict[str, Any], settings: dict[str, Any]) -> str:
    records = scout_unique_history_records(scout_hardware_history(opportunity))
    if not records:
        return ""
    for record in records:
        for result in scout_history_pool_results(record):
            decision = str(result.get("decision") or result.get("status") or "").strip().lower()
            if decision in CLORE_AUTO_BAD_HISTORY_DECISIONS:
                return f"historico ruim: {decision}"
            if scout_result_quality(result, settings) == "bad":
                profit = result.get("profit_usd_hr")
                ratio = result.get("hash_ratio")
                if ratio not in {None, ""}:
                    return f"historico hash baixo: {round(safe_float(ratio) * 100, 1)}%"
                if profit not in {None, ""}:
                    return f"historico lucro baixo: ${safe_float(profit):.2f}/h"
                return "historico ruim sem worker/hash"
    return ""


def clore_auto_block_reason(
    opportunity: dict[str, Any],
    settings: dict[str, Any],
    active_server_ids: set[str],
) -> str:
    server_id = str(opportunity.get("id") or "")
    if opportunity.get("platform") != "clore":
        return "nao e Clore"
    if not server_id:
        return "server Clore ausente"
    if server_id in active_server_ids:
        return "server Clore ja esta em teste/alugado"
    decision = str(opportunity.get("decision") or "")
    if decision != "green":
        return "auto Clore so pega ALUGAR"
    strategy, strategy_reason = clore_auto_candidate_strategy(opportunity)
    if not strategy:
        return strategy_reason
    risks = set(opportunity.get("risks") or [])
    blocked_risks = risks.intersection(CLORE_AUTO_BLOCK_RISKS)
    if blocked_risks:
        return "risco auto: " + ", ".join(sorted(blocked_risks))
    profit_hr = safe_float(opportunity.get("profit_usd_hr"), -999999)
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    if profit_hr < min_profit:
        return f"lucro ${profit_hr:.2f}/h abaixo do minimo ${min_profit:.2f}/h"
    price_hr = safe_float(opportunity.get("price_usd_hr"))
    max_price = safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR)
    if price_hr <= 0:
        return "preco Clore ausente"
    if price_hr > max_price:
        return f"custo ${price_hr:.2f}/h acima do max Scout ${max_price:.2f}/h"
    history_reason = clore_auto_history_bad_reason(opportunity, settings)
    if history_reason:
        return history_reason
    return ""


def clore_auto_priority_score(opportunity: dict[str, Any]) -> float:
    profit = safe_float(opportunity.get("profit_usd_hr"), -999999)
    roi = safe_float(opportunity.get("roi_pct"), -999999)
    reliability = safe_float(opportunity.get("reliability"), -999999)
    history_bonus = 1.0 if opportunity.get("history_seen") and safe_float(opportunity.get("history_best_profit_usd_hr"), -999999) > 0 else 0.0
    return round(profit * 1_000_000 + roi * 1_000 + reliability * 10 + history_bonus, 4)


def clore_auto_queue_item_from_opportunity(
    opportunity: dict[str, Any],
    settings: dict[str, Any],
    strategy: str,
    existing: dict[str, Any],
    current: float,
) -> dict[str, Any]:
    last_seen = safe_float(existing.get("last_seen_at"))
    if last_seen <= 0 or current - last_seen >= 30:
        last_seen = current
    return {
        "server_id": safe_int(opportunity.get("id")),
        "offer_id": safe_int(opportunity.get("id")),
        "pool_strategy": strategy,
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "price_usd_hr": opportunity.get("price_usd_hr"),
        "expected_ths": opportunity.get("hashrate_ths"),
        "profit_usd_hr": opportunity.get("profit_usd_hr"),
        "roi_pct": opportunity.get("roi_pct"),
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "cuda": opportunity.get("cuda"),
        "pcie": opportunity.get("pcie"),
        "reliability": opportunity.get("reliability"),
        "net_up_mbps": opportunity.get("net_up_mbps"),
        "net_down_mbps": opportunity.get("net_down_mbps"),
        "risks": opportunity.get("risks") or [],
        "history_seen": opportunity.get("history_seen"),
        "history_count": opportunity.get("history_count"),
        "history_avg_ths": opportunity.get("history_avg_ths"),
        "history_best_profit_usd_hr": opportunity.get("history_best_profit_usd_hr"),
        "queue_status": "queued",
        "sniper_status": "auto Clore",
        "skip_reason": f"Auto Clore: decisao {opportunity_decision_label(opportunity.get('decision'))}; candidato pronto",
        "first_seen_at": existing.get("first_seen_at") or current,
        "last_seen_at": last_seen,
        "priority_score": clore_auto_priority_score(opportunity),
        "min_profit_usd_hr": settings.get("min_profit_usd_hr"),
        "max_price_usd_hr": settings.get("max_price_usd_hr"),
        "source": "auto_clore",
    }


def clore_auto_mark_cooldown(item: dict[str, Any], reason: str, current: float) -> None:
    attempts = safe_int(item.get("retry_attempts")) + 1
    item.update({
        "queue_status": "cooldown",
        "sniper_status": "cooldown",
        "skip_reason": f"Auto Clore falhou: {reason}; retry em {CLORE_AUTO_COOLDOWN_SECONDS // 60} min",
        "last_retry_error": reason,
        "last_retry_at": current,
        "next_retry_at": current + CLORE_AUTO_COOLDOWN_SECONDS,
        "retry_attempts": attempts,
        "updated_at": current,
    })


def update_clore_auto_queue_from_opportunities(
    scout: dict[str, Any],
    clore_actions: dict[str, Any],
    state: dict[str, Any],
    settings: dict[str, Any],
) -> bool:
    queue = clore_auto_queue(scout)
    active_server_ids = clore_auto_active_server_ids(scout, clore_actions)
    current = now_ts()
    changed = False
    seen_ids: set[str] = set()
    for opportunity in state.get("opportunities", []):
        if not isinstance(opportunity, dict) or opportunity.get("platform") != "clore":
            continue
        server_id = str(opportunity.get("id") or "")
        if not server_id:
            continue
        seen_ids.add(server_id)
        existing = queue.get(server_id) if isinstance(queue.get(server_id), dict) else {}
        if existing.get("queue_status") == "cooldown" and safe_float(existing.get("next_retry_at")) > current:
            continue
        strategy, _ = clore_auto_candidate_strategy(opportunity)
        block_reason = clore_auto_block_reason(opportunity, settings, active_server_ids)
        if block_reason:
            if existing and existing.get("queue_status") in {"queued", "renting"}:
                existing.update({
                    "queue_status": "blocked",
                    "sniper_status": "bloqueado",
                    "skip_reason": block_reason,
                    "last_seen_at": current,
                    "updated_at": current,
                })
                queue[server_id] = existing
                changed = True
            continue
        item = clore_auto_queue_item_from_opportunity(opportunity, settings, strategy, existing, current)
        if queue.get(server_id) != item:
            queue[server_id] = item
            changed = True
    for server_id, item in list(queue.items()):
        if not isinstance(item, dict):
            queue.pop(server_id, None)
            changed = True
            continue
        if server_id in seen_ids or item.get("queue_status") == "cooldown":
            continue
        if item.get("queue_status") in {"queued", "renting"}:
            clore_auto_mark_cooldown(item, "server Clore sumiu do marketplace", current)
            changed = True
    return changed


def clore_auto_error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)


async def maybe_autostart_clore_scout(
    scout: dict[str, Any],
    actions: dict[str, Any],
    clore_actions: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    if not scout.get("clore_auto_enabled"):
        return False
    settings = scout_settings(scout)
    queue_changed = update_clore_auto_queue_from_opportunities(scout, clore_actions, state, settings)
    active_tests = [
        test for test in (scout.get("tests") or {}).values()
        if isinstance(test, dict) and test.get("status") == "testing"
    ]
    slots = max(0, safe_int(settings.get("max_parallel_tests"), SCOUT_MAX_PARALLEL_TESTS) - len(active_tests))
    if slots <= 0:
        return queue_changed
    active_server_ids = clore_auto_active_server_ids(scout, clore_actions)
    opportunity_by_id = {
        str(item.get("id")): item
        for item in state.get("opportunities", [])
        if isinstance(item, dict) and item.get("platform") == "clore" and item.get("id")
    }
    queue_items = sorted(
        [
            item for item in clore_auto_queue(scout).values()
            if isinstance(item, dict) and item.get("queue_status") == "queued"
        ],
        key=lambda item: (
            -safe_float(item.get("profit_usd_hr"), -999999),
            -safe_float(item.get("roi_pct"), -999999),
            -safe_float(item.get("reliability"), -999999),
            -safe_float(item.get("history_best_profit_usd_hr"), -999999),
            safe_float(item.get("first_seen_at")),
        ),
    )
    started_any = False
    starts_left = min(safe_int(settings.get("starts_per_tick"), SCOUT_STARTS_PER_TICK), slots)
    for item in queue_items:
        if starts_left <= 0:
            break
        server_id = safe_int(item.get("server_id") or item.get("offer_id"))
        if server_id <= 0:
            item.update({"queue_status": "blocked", "sniper_status": "bloqueado", "skip_reason": "server Clore invalido"})
            queue_changed = True
            continue
        opportunity = opportunity_by_id.get(str(server_id))
        if not opportunity:
            clore_auto_mark_cooldown(item, "server Clore sumiu do marketplace", now_ts())
            queue_changed = True
            continue
        strategy, strategy_reason = clore_auto_candidate_strategy(opportunity)
        block_reason = clore_auto_block_reason(opportunity, settings, active_server_ids)
        if block_reason:
            item.update({
                "queue_status": "blocked",
                "sniper_status": "bloqueado",
                "skip_reason": block_reason or strategy_reason,
                "last_seen_at": now_ts(),
            })
            queue_changed = True
            continue
        current = now_ts()
        item.update({
            "queue_status": "renting",
            "sniper_status": "alugando agora",
            "skip_reason": "Auto Clore: criando ordem e teste Scout",
            "last_seen_at": current,
            "updated_at": current,
        })
        await save_scout_state(scout)
        try:
            test = await start_scout_clore_rent(
                scout,
                actions,
                clore_actions,
                state,
                server_id,
                strategy,
                source="auto_clore",
            )
        except Exception as exc:
            detail = clore_auto_error_detail(exc)
            clore_auto_mark_cooldown(item, detail, now_ts())
            queue_changed = True
            continue
        item.update({
            "queue_status": "rented",
            "sniper_status": "teste Scout ativo",
            "skip_reason": f"Auto Clore iniciou {test.get('test_id')}",
            "test_id": test.get("test_id"),
            "order_id": test.get("order_id"),
            "last_seen_at": now_ts(),
            "updated_at": now_ts(),
        })
        active_server_ids.add(str(server_id))
        active_tests.append(test)
        started_any = True
        starts_left -= 1
    return started_any or queue_changed


def results_history_records(limit: int = 500) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in scout_history_items()[:limit]:
        if not isinstance(item, dict):
            continue
        measured_pools = {
            str(result.get("pool_strategy") or "")
            for result in item.get("prior_results") or []
            if isinstance(result, dict) and result.get("decision") == "pool_measured"
        }
        for result in scout_history_pool_results(item):
            if not isinstance(result, dict) or not result.get("pool_strategy"):
                continue
            if (
                result is item
                and result.get("decision") in {"keep", "switch_failed_keep_current"}
                and str(result.get("pool_strategy") or "") in measured_pools
            ):
                continue
            record = dict(result)
            for key in (
                "test_id",
                "ask_id",
                "instance_id",
                "worker_name",
                "host_id",
                "machine_id",
                "gpu",
                "gpu_count",
                "price_usd_hr",
                "expected_ths",
                "source",
                "trigger_id",
                "trigger_name",
                "failure_tag",
                "pcie",
                "cuda",
                "reliability",
                "net_up_mbps",
                "net_down_mbps",
            ):
                if key not in record and key in item:
                    record[key] = item.get(key)
            dedupe = (
                str(record.get("test_id") or ""),
                str(record.get("pool_strategy") or ""),
                str(record.get("decision") or ""),
                str(record.get("ended_at") or ""),
            )
            if dedupe in seen:
                continue
            seen.add(dedupe)
            records.append(record)
    records.sort(key=lambda record: safe_float(record.get("ended_at")), reverse=True)
    return records


def results_hardware_key(item: dict[str, Any]) -> str:
    return "|".join(
        (
            str(item.get("machine_id") or ""),
            str(item.get("host_id") or ""),
            normalize_gpu_name(item.get("gpu")),
            str(max(1, safe_int(item.get("gpu_count"), 1))),
        )
    )


def results_pattern_key(item: dict[str, Any]) -> str:
    return "|".join(
        (
            normalize_gpu_name(item.get("gpu")),
            str(max(1, safe_int(item.get("gpu_count"), 1))),
            str(item.get("pcie") or "-"),
            str(item.get("host_id") or "-"),
        )
    )


def results_queue_id(kind: str, item: dict[str, Any]) -> str:
    if kind == "offer":
        return f"offer:{safe_int(item.get('ask_id') or item.get('id'))}"
    if kind == "hardware":
        return f"hardware:{results_hardware_key(item)}"
    if kind == "pattern":
        return f"pattern:{results_pattern_key(item)}"
    return f"gpu:{normalize_gpu_name(item.get('gpu'))}"


AKOYA_21_BENCHMARK_THS: dict[str, float] = {
    "B200": 661.51,
    "B300 SXM6 AC": 70.81,
    "H100 SXM": 645.28,
    "H100 PCIe": 384.95,
    "H100 NVL": 470.00,
    "H200": 651.40,
    "H200 NVL": 553.80,
    "RTX PRO 6000 Blackwell Server Edition": 327.80,
    "RTX 5090": 293.20,
    "RTX PRO 6000 Blackwell Workstation Edition": 266.20,
    "RTX 4090": 237.10,
    "L40S": 211.10,
    "RTX 5080": 172.10,
    "RTX 6000 Ada Generation": 163.77,
    "A100 PCIe": 134.70,
    "A100 SXM": 52.91,
    "A100 SXM 40GB": 46.85,
    "RTX 5070": 96.72,
    "RTX PRO 4000 Blackwell": 91.13,
    "RTX 3090": 88.25,
    "RTX A6000": 86.27,
    "RTX 3080": 74.14,
    "RTX 4000 Ada Generation": 68.81,
    "RTX 5060 Ti": 67.49,
    "RTX 4060 Ti": 65.31,
    "RTX A5000": 61.20,
    "L4": 58.45,
    "RTX 3070": 55.01,
    "RTX PRO 5000 Blackwell": 52.62,
    "A10": 50.65,
    "RTX 2000 Ada Generation": 35.92,
    "RTX 3090 Ti": 19.02,
    "RTX A4500": 15.22,
}
PRIME_REEVALUATE_GPUS = {"RTX 4090", "RTX 5090", "RTX 3090", "RTX 3080", "RTX A6000", "RTX A5000", "RTX 3070"}


def prime_gpu_name(value: Any) -> str:
    normalized = normalize_gpu_name(value)
    if normalized:
        return normalized
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper().replace("GEFORCE ", "")
    aliases = {
        "NVIDIA H100 80GB HBM3": "H100 SXM",
        "H100 80GB HBM3": "H100 SXM",
        "NVIDIA H200": "H200",
        "NVIDIA L40S": "L40S",
        "NVIDIA L4": "L4",
        "NVIDIA A10": "A10",
        "A100 80GB PCIE": "A100 PCIe",
        "A100-SXM4-80GB": "A100 SXM",
        "A100-SXM4-40GB": "A100 SXM 40GB",
        "RTX PRO 6000 S": "RTX PRO 6000 Blackwell Server Edition",
        "RTX PRO 6000 WS": "RTX PRO 6000 Blackwell Workstation Edition",
        "RTX PRO 4000": "RTX PRO 4000 Blackwell",
        "RTX PRO 5000": "RTX PRO 5000 Blackwell",
        "RTX 4000ADA": "RTX 4000 Ada Generation",
        "RTX 5000 ADA": "RTX PRO 5000 Blackwell",
    }
    if upper in aliases:
        return aliases[upper]
    for key in AKOYA_21_BENCHMARK_THS:
        if key.upper() in upper or upper in key.upper():
            return key
    return text


def prime_benchmark_ths(gpu: Any) -> float | None:
    gpu_name = prime_gpu_name(gpu)
    return AKOYA_21_BENCHMARK_THS.get(gpu_name)


def prime_records_for_offer(records: list[dict[str, Any]], offer: dict[str, Any]) -> list[dict[str, Any]]:
    gpu = normalize_gpu_name(offer.get("gpu"))
    gpu_count = safe_int(offer.get("gpu_count"), 1)
    machine_id = str(offer.get("machine_id") or "")
    host_id = str(offer.get("host_id") or "")
    matched = []
    for record in records:
        if normalize_gpu_name(record.get("gpu")) != gpu:
            continue
        if safe_int(record.get("gpu_count"), 1) != gpu_count:
            continue
        same_machine = machine_id and str(record.get("machine_id") or "") == machine_id
        same_host = host_id and str(record.get("host_id") or "") == host_id
        if same_machine or same_host:
            matched.append(record)
    matched.sort(key=lambda item: safe_float(item.get("profit_usd_hr"), -999999), reverse=True)
    return matched


def prime_gpu_record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for record in records:
        gpu = normalize_gpu_name(record.get("gpu"))
        if not gpu:
            continue
        group = groups.setdefault(gpu, {
            "gpu": gpu,
            "samples": 0,
            "profitable_samples": 0,
            "best_profit_usd_hr": None,
            "best_pool": "",
            "best_hashrate_ths": None,
            "last_seen_at": None,
        })
        group["samples"] += 1
        if safe_float(record.get("profit_usd_hr"), -999999) > 0:
            group["profitable_samples"] += 1
        group["last_seen_at"] = max(safe_float(group.get("last_seen_at")), safe_float(record.get("ended_at")))
        if group["best_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr"), -999999) > safe_float(group.get("best_profit_usd_hr"), -999999):
            group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            group["best_pool"] = record.get("pool_strategy")
            group["best_hashrate_ths"] = record.get("live_ths_avg") or record.get("latest_hashrate_ths") or record.get("expected_ths")
    return groups


def prime_offer_projection(
    opportunity: dict[str, Any],
    pearl: dict[str, Any],
    records: list[dict[str, Any]],
    gpu_summary: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gpu = normalize_gpu_name(opportunity.get("gpu"))
    gpu_count = max(1, safe_int(opportunity.get("gpu_count"), 1))
    price_hr = safe_float(opportunity.get("price_usd_hr"))
    rate_day = rate_for_pool(pearl, "akoya")
    benchmark_ths = prime_benchmark_ths(gpu)
    matched_records = prime_records_for_offer(records, opportunity)
    best_real = matched_records[0] if matched_records else None
    if best_real and safe_float(best_real.get("live_ths_avg")) > 0:
        hashrate = safe_float(best_real.get("live_ths_avg"))
        hash_source = "real_scout"
        confidence = "alta"
    elif benchmark_ths:
        hashrate = benchmark_ths * gpu_count
        hash_source = "akoya_2_1_benchmark"
        confidence = "media"
    else:
        hashrate = safe_float(opportunity.get("hashrate_ths"))
        hash_source = "shared_database"
        confidence = "baixa"
    revenue_hr = (hashrate * rate_day / 24) if rate_day else None
    profit_hr = revenue_hr - price_hr if revenue_hr is not None and price_hr > 0 else None
    roi_pct = (profit_hr / price_hr * 100) if profit_hr is not None and price_hr > 0 else None
    gpu_history = gpu_summary.get(gpu or "") or {}
    return {
        "gpu": gpu,
        "gpu_count": gpu_count,
        "hashrate_ths": round(hashrate, 2),
        "hash_source": hash_source,
        "confidence": confidence,
        "revenue_usd_hr": round_money(revenue_hr),
        "profit_usd_hr": round_money(profit_hr),
        "roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "best_real_profit_usd_hr": round_money((best_real or {}).get("profit_usd_hr")) if best_real else None,
        "best_real_pool": (best_real or {}).get("pool_strategy") if best_real else "",
        "gpu_best_profit_usd_hr": round_money(gpu_history.get("best_profit_usd_hr")),
        "gpu_best_pool": gpu_history.get("best_pool", ""),
        "history_hits": len(matched_records),
    }


def prime_offer_status(opportunity: dict[str, Any], actions: dict[str, Any], scout: dict[str, Any], settings: dict[str, Any], results_queue: dict[str, Any]) -> tuple[str, str, dict[str, Any] | None]:
    active = results_active_match(actions, scout, opportunity)
    if active:
        return "active", "Ja alugada/testando", None
    queue_id = results_queue_id("offer", {"ask_id": opportunity.get("id"), "gpu": opportunity.get("gpu")})
    queued = results_queue.get(queue_id) if isinstance(results_queue.get(queue_id), dict) else None
    if queued and queued.get("status") in {"waiting", "renting", "blocked"}:
        return str(queued.get("status")), str(queued.get("last_error") or "na fila Results"), queued
    allowlist_reason = scout_gpu_allowlist_block_reason(opportunity, settings)
    if allowlist_reason:
        return "blocked", allowlist_reason, None
    risks = set(opportunity.get("risks") or [])
    if {"cuda_below_12_9", "network_bad", "price_usd_missing"}.intersection(risks):
        return "blocked", ", ".join(sorted(risks)), None
    if safe_float(opportunity.get("price_usd_hr")) <= 0:
        return "blocked", "preco invalido", None
    return "ready", "pronta para teste manual", None


def prime_gpu_universe_rows(rows: list[dict[str, Any]], records: list[dict[str, Any]], raw_vast_offers: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    gpu_summary = prime_gpu_record_summary(records)
    by_gpu: dict[str, dict[str, Any]] = {}
    for gpu, ths in AKOYA_21_BENCHMARK_THS.items():
        by_gpu[gpu] = {
            "gpu": gpu,
            "akoya21_ths": ths,
            "current_offers": 0,
            "best_current_ask": None,
            "best_current_price_usd_hr": None,
            "best_current_profit_usd_hr": None,
            "best_current_status": "no_offer",
            "best_history_profit_usd_hr": None,
            "best_history_pool": "",
            "history_samples": 0,
            "hash_source": "akoya_2_1_benchmark",
        }
    for gpu, summary in gpu_summary.items():
        row = by_gpu.setdefault(gpu, {
            "gpu": gpu,
            "akoya21_ths": prime_benchmark_ths(gpu),
            "current_offers": 0,
            "best_current_ask": None,
            "best_current_price_usd_hr": None,
            "best_current_profit_usd_hr": None,
            "best_current_status": "no_offer",
            "hash_source": "real_scout",
        })
        row["best_history_profit_usd_hr"] = round_money(summary.get("best_profit_usd_hr"))
        row["best_history_pool"] = summary.get("best_pool", "")
        row["history_samples"] = summary.get("samples", 0)
    rate_day = safe_float((latest_state.get("network") or {}).get("usd_per_th_per_day", {}).get("akoya"))
    for offer in raw_vast_offers or []:
        if not isinstance(offer, dict):
            continue
        gpu = prime_gpu_name(offer.get("gpu_model_normalized") or offer.get("gpu_model_raw"))
        if not gpu:
            continue
        gpu_count = max(1, safe_int(offer.get("gpu_count"), 1))
        akoya_ths = prime_benchmark_ths(gpu)
        price = safe_float(offer.get("price_usd_hr"))
        projected_profit = (akoya_ths * gpu_count * rate_day / 24 - price) if akoya_ths and rate_day and price > 0 else None
        row = by_gpu.setdefault(gpu, {
            "gpu": gpu,
            "akoya21_ths": akoya_ths,
            "current_offers": 0,
            "best_current_ask": None,
            "best_current_price_usd_hr": None,
            "best_current_profit_usd_hr": None,
            "best_current_status": "no_offer",
            "best_history_profit_usd_hr": round_money((gpu_summary.get(gpu) or {}).get("best_profit_usd_hr")),
            "best_history_pool": (gpu_summary.get(gpu) or {}).get("best_pool", ""),
            "history_samples": (gpu_summary.get(gpu) or {}).get("samples", 0),
            "hash_source": "raw_vast",
        })
        if not row.get("akoya21_ths") and akoya_ths:
            row["akoya21_ths"] = akoya_ths
        row["current_offers"] = safe_int(row.get("current_offers")) + 1
        current_best_profit = safe_float(row.get("best_current_profit_usd_hr"), -999999)
        current_best_price = safe_float(row.get("best_current_price_usd_hr"), 999999)
        if (
            projected_profit is not None
            and projected_profit > current_best_profit
        ) or (
            row.get("best_current_profit_usd_hr") is None
            and price > 0
            and price < current_best_price
        ):
            row["best_current_ask"] = safe_int(offer.get("offer_id"))
            row["best_current_price_usd_hr"] = round_money(price)
            row["best_current_profit_usd_hr"] = round_money(projected_profit)
            row["best_current_gpu_count"] = offer.get("gpu_count")
            row["best_current_machine_id"] = offer.get("machine_id")
            row["best_current_host_id"] = offer.get("host_id")
            row["best_current_pcie"] = f"x{safe_int(offer.get('pcie_lanes'))} / {safe_float(offer.get('pcie_bw_gbps')):.1f} GB/s" if offer.get("pcie_lanes") or offer.get("pcie_bw_gbps") else ""
            row["best_current_cuda"] = offer.get("cuda_max_good")
            row["best_current_reliability"] = offer.get("reliability")
            row["best_current_net_up_mbps"] = offer.get("net_up_mbps")
            row["best_current_net_down_mbps"] = offer.get("net_down_mbps")
    for item in rows:
        gpu = normalize_gpu_name(item.get("gpu"))
        if not gpu:
            continue
        row = by_gpu.setdefault(gpu, {
            "gpu": gpu,
            "akoya21_ths": prime_benchmark_ths(gpu),
            "current_offers": 0,
            "best_history_profit_usd_hr": round_money((gpu_summary.get(gpu) or {}).get("best_profit_usd_hr")),
            "best_history_pool": (gpu_summary.get(gpu) or {}).get("best_pool", ""),
            "history_samples": (gpu_summary.get(gpu) or {}).get("samples", 0),
        })
        profit = safe_float(item.get("akoya21_profit_usd_hr"), -999999)
        if row.get("best_current_profit_usd_hr") is None or profit > safe_float(row.get("best_current_profit_usd_hr"), -999999):
            row["best_current_ask"] = item.get("ask_id")
            row["best_current_price_usd_hr"] = item.get("price_usd_hr")
            row["best_current_profit_usd_hr"] = item.get("akoya21_profit_usd_hr")
            row["best_current_status"] = item.get("status")
            row["best_current_gpu_count"] = item.get("gpu_count")
            row["best_current_machine_id"] = item.get("machine_id")
            row["best_current_host_id"] = item.get("host_id")
            row["best_current_pcie"] = item.get("pcie")
            row["best_current_cuda"] = item.get("cuda")
            row["best_current_reliability"] = item.get("reliability")
            row["best_current_net_up_mbps"] = item.get("net_up_mbps")
            row["best_current_net_down_mbps"] = item.get("net_down_mbps")
    result = list(by_gpu.values())
    result.sort(
        key=lambda item: (
            safe_int(item.get("current_offers")) > 0,
            safe_float(item.get("best_current_profit_usd_hr"), -999999),
            safe_float(item.get("best_history_profit_usd_hr"), -999999),
            safe_float(item.get("akoya21_ths"), -999999),
        ),
        reverse=True,
    )
    return result


def prime_raw_offer_projection(offer: dict[str, Any], rate_day: float, rows_by_ask: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ask_id = safe_int(offer.get("offer_id"))
    existing = rows_by_ask.get(str(ask_id))
    if existing:
        return dict(existing)
    gpu = prime_gpu_name(offer.get("gpu_model_normalized") or offer.get("gpu_model_raw"))
    gpu_count = max(1, safe_int(offer.get("gpu_count"), 1))
    akoya_ths = prime_benchmark_ths(gpu)
    price = safe_float(offer.get("price_usd_hr"))
    hashrate = akoya_ths * gpu_count if akoya_ths else None
    profit = (hashrate * rate_day / 24 - price) if hashrate and rate_day and price > 0 else None
    pcie = f"x{safe_int(offer.get('pcie_lanes'))} / {safe_float(offer.get('pcie_bw_gbps')):.1f} GB/s" if offer.get("pcie_lanes") or offer.get("pcie_bw_gbps") else ""
    return {
        "ask_id": ask_id,
        "id": ask_id,
        "gpu": gpu,
        "gpu_count": gpu_count,
        "machine_id": offer.get("machine_id"),
        "host_id": offer.get("host_id"),
        "pool": "akoya",
        "price_usd_hr": round_money(price),
        "akoya21_hashrate_ths": round(hashrate, 2) if hashrate is not None else None,
        "akoya21_profit_usd_hr": round_money(profit),
        "hash_source": "akoya_2_1_benchmark" if akoya_ths else "raw_vast",
        "confidence": "media" if akoya_ths else "baixa",
        "status": "manual",
        "status_reason": "raw Vast; teste manual",
        "action_label": "Testar manual",
        "pcie": pcie,
        "pcie_lanes": offer.get("pcie_lanes"),
        "pcie_bw_gbps": offer.get("pcie_bw_gbps"),
        "cuda": offer.get("cuda_max_good"),
        "reliability": offer.get("reliability"),
        "net_up_mbps": offer.get("net_up_mbps"),
        "net_down_mbps": offer.get("net_down_mbps"),
        "risks": [],
        "rental_url": rental_url("vastai", ask_id),
    }


def prime_gpu_sections(rows: list[dict[str, Any]], records: list[dict[str, Any]], raw_vast_offers: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rate_day = safe_float((latest_state.get("network") or {}).get("usd_per_th_per_day", {}).get("akoya"))
    rows_by_ask = {str(item.get("ask_id") or item.get("id")): item for item in rows if item.get("ask_id") or item.get("id")}
    grouped: dict[str, dict[str, Any]] = {}

    def ensure_group(gpu: Any) -> dict[str, Any]:
        gpu_name = prime_gpu_name(gpu)
        group = grouped.setdefault(gpu_name, {
            "gpu": gpu_name,
            "akoya21_ths": prime_benchmark_ths(gpu_name),
            "offers": [],
            "history_samples": 0,
            "best_history_profit_usd_hr": None,
            "best_history_pool": "",
            "best_offer_profit_usd_hr": None,
            "best_offer_ask": None,
            "current_offers": 0,
        })
        return group

    for record in records:
        gpu = normalize_gpu_name(record.get("gpu")) or prime_gpu_name(record.get("gpu"))
        if not gpu:
            continue
        group = ensure_group(gpu)
        group["history_samples"] = safe_int(group.get("history_samples")) + 1
        if group["best_history_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr"), -999999) > safe_float(group.get("best_history_profit_usd_hr"), -999999):
            group["best_history_profit_usd_hr"] = round_money(record.get("profit_usd_hr"))
            group["best_history_pool"] = record.get("pool_strategy")

    seen_asks: set[str] = set()
    for item in rows:
        gpu = item.get("gpu")
        if not gpu:
            continue
        group = ensure_group(gpu)
        ask_id = str(item.get("ask_id") or item.get("id") or "")
        if ask_id:
            seen_asks.add(ask_id)
        group["offers"].append(item)

    for offer in raw_vast_offers or []:
        if not isinstance(offer, dict):
            continue
        ask_id = str(offer.get("offer_id") or "")
        if not ask_id or ask_id in seen_asks:
            continue
        item = prime_raw_offer_projection(offer, rate_day, rows_by_ask)
        gpu = item.get("gpu")
        if not gpu:
            continue
        group = ensure_group(gpu)
        group["offers"].append(item)
        seen_asks.add(ask_id)

    sections = []
    for group in grouped.values():
        offers = group.get("offers") or []
        offers.sort(
            key=lambda item: (
                safe_float(item.get("akoya21_profit_usd_hr"), -999999),
                -safe_float(item.get("price_usd_hr"), 999999),
            ),
            reverse=True,
        )
        group["offers"] = offers[:80]
        group["current_offers"] = len(offers)
        best = offers[0] if offers else {}
        group["best_offer_profit_usd_hr"] = best.get("akoya21_profit_usd_hr")
        group["best_offer_ask"] = best.get("ask_id")
        sections.append(group)
    sections.sort(
        key=lambda item: (
            safe_int(item.get("current_offers")) > 0,
            safe_float(item.get("best_offer_profit_usd_hr"), -999999),
            safe_float(item.get("best_history_profit_usd_hr"), -999999),
            safe_float(item.get("akoya21_ths"), -999999),
        ),
        reverse=True,
    )
    return sections


def build_prime_state_payload(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    results_state: dict[str, Any],
    raw_vast_offers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = scout_settings(scout)
    pearl = (state.get("network") or {})
    records = results_history_records()
    gpu_summary = prime_gpu_record_summary(records)
    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    rows = []
    for opportunity in state.get("opportunities", []):
        if not isinstance(opportunity, dict) or opportunity.get("platform") != "vastai":
            continue
        projection = prime_offer_projection(opportunity, pearl, records, gpu_summary)
        status, reason, queued = prime_offer_status(opportunity, actions, scout, settings, queue)
        price_hr = safe_float(opportunity.get("price_usd_hr"))
        profit = safe_float(projection.get("profit_usd_hr"), -999999)
        history_bonus = min(0.75, safe_float(projection.get("best_real_profit_usd_hr")) * 0.25) if projection.get("history_hits") else 0.0
        gpu_bonus = 0.25 if safe_float(projection.get("gpu_best_profit_usd_hr"), -999999) > 0 else 0.0
        price_bonus = max(0.0, 0.35 - price_hr * 0.03) if price_hr > 0 else 0.0
        host_bonus = 0.20 if projection.get("history_hits") else 0.0
        risk_penalty = 0.0
        risks = set(opportunity.get("risks") or [])
        if "network_watch" in risks or "reliability_watch" in risks:
            risk_penalty += 0.15
        if "network_bad" in risks or "cuda_below_12_9" in risks or "low_value_gpu" in risks:
            risk_penalty += 1.0
        prime_score = profit + history_bonus + gpu_bonus + price_bonus + host_bonus - risk_penalty
        action_label = "Ja alugada" if status == "active" else "Testar/Alugar via Scout"
        rows.append({
            "id": opportunity.get("id"),
            "ask_id": opportunity.get("id"),
            "gpu": projection.get("gpu") or opportunity.get("gpu"),
            "gpu_count": projection.get("gpu_count"),
            "machine_id": opportunity.get("machine_id"),
            "host_id": opportunity.get("host_id"),
            "pool": "akoya",
            "price_usd_hr": opportunity.get("price_usd_hr"),
            "current_profit_usd_hr": opportunity.get("profit_usd_hr"),
            "akoya21_profit_usd_hr": projection.get("profit_usd_hr"),
            "akoya21_revenue_usd_hr": projection.get("revenue_usd_hr"),
            "akoya21_hashrate_ths": projection.get("hashrate_ths"),
            "hash_source": projection.get("hash_source"),
            "confidence": projection.get("confidence"),
            "roi_pct": projection.get("roi_pct"),
            "prime_score": round_money(prime_score),
            "best_real_profit_usd_hr": projection.get("best_real_profit_usd_hr"),
            "best_real_pool": projection.get("best_real_pool"),
            "gpu_best_profit_usd_hr": projection.get("gpu_best_profit_usd_hr"),
            "gpu_best_pool": projection.get("gpu_best_pool"),
            "history_hits": projection.get("history_hits"),
            "status": status,
            "status_reason": reason,
            "action_label": action_label,
            "queue": results_queue_public(queued) if queued else None,
            "pcie": opportunity.get("pcie"),
            "cuda": opportunity.get("cuda"),
            "reliability": opportunity.get("reliability"),
            "net_up_mbps": opportunity.get("net_up_mbps"),
            "net_down_mbps": opportunity.get("net_down_mbps"),
            "risks": opportunity.get("risks") or [],
            "rental_url": opportunity.get("rental_url"),
        })
    rows.sort(key=lambda item: safe_float(item.get("prime_score"), -999999), reverse=True)
    radar = [item for item in rows if item.get("hash_source") == "akoya_2_1_benchmark"]
    reevaluate = [
        item for item in rows
        if normalize_gpu_name(item.get("gpu")) in PRIME_REEVALUATE_GPUS
        or (item.get("hash_source") == "akoya_2_1_benchmark" and safe_float(item.get("akoya21_profit_usd_hr"), -999999) > 0)
    ]
    premium_hosts = results_profitable_hosts_payload(state, actions, scout, records, settings, results_state)
    public_queue = [results_queue_public(item) for item in queue.values() if isinstance(item, dict) and item.get("status") != "archived"]
    public_queue.sort(key=lambda item: safe_float(item.get("updated_at") or item.get("created_at")), reverse=True)
    return {
        "updated_at": now_ts(),
        "summary": {
            "vast_offers": len(rows),
            "ready": len([item for item in rows if item.get("status") == "ready"]),
            "active": len([item for item in rows if item.get("status") == "active"]),
            "akoya21_profitable": len([item for item in rows if safe_float(item.get("akoya21_profit_usd_hr"), -999999) > 0]),
            "best_prime_score": rows[0].get("prime_score") if rows else None,
            "best_profit_usd_hr": rows[0].get("akoya21_profit_usd_hr") if rows else None,
            "best_gpu": rows[0].get("gpu") if rows else "",
            "queue_waiting": len([item for item in public_queue if item.get("status") == "waiting"]),
        },
        "now": rows[:80],
        "akoya21_radar": radar[:80],
        "real_history": build_results_state_payload(state, actions, scout, results_state).get("hardware", [])[:80],
        "gpu_universe": prime_gpu_universe_rows(rows, records, raw_vast_offers),
        "gpu_sections": prime_gpu_sections(rows, records, raw_vast_offers),
        "reevaluate": reevaluate[:80],
        "premium_hosts": premium_hosts,
        "queue": public_queue[:100],
        "benchmarks": [{"gpu": gpu, "akoya21_ths": ths} for gpu, ths in sorted(AKOYA_21_BENCHMARK_THS.items())],
    }


def results_learned_max_price(record: dict[str, Any], settings: dict[str, Any]) -> float:
    price = safe_float(record.get("price_usd_hr"))
    profit = safe_float(record.get("profit_usd_hr"))
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    learned = price + max(0.0, profit) - min_profit if price > 0 else 0.0
    return round_money(max(safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR), learned)) or SCOUT_MAX_PRICE_USD_HR


def results_active_match(actions: dict[str, Any], scout: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
    ask_id = str(target.get("ask_id") or "")
    instance_id = str(target.get("instance_id") or "")
    machine_id = str(target.get("machine_id") or "")
    host_id = str(target.get("host_id") or "")
    gpu = normalize_gpu_name(target.get("gpu"))
    gpu_count = max(1, safe_int(target.get("gpu_count"), 1))

    def matches(item: dict[str, Any]) -> bool:
        if ask_id and str(item.get("ask_id") or "") == ask_id:
            return True
        if instance_id and str(item.get("instance_id") or "") == instance_id:
            return True
        item_gpu = normalize_gpu_name(item.get("gpu"))
        item_count = max(1, safe_int(item.get("gpu_count"), 1))
        if not gpu or item_gpu != gpu or item_count != gpu_count:
            return False
        if machine_id:
            return str(item.get("machine_id") or "") == machine_id
        return bool(host_id and str(item.get("host_id") or "") == host_id)

    for action in actions.values():
        if isinstance(action, dict) and action.get("state") in {"renting", "rented"} and matches(action):
            return action
    for test in (scout.get("tests") or {}).values():
        if isinstance(test, dict) and test.get("status") == "testing" and matches(test):
            return test
    return None


def results_offer_ready(
    opportunity: dict[str, Any],
    max_price_usd_hr: float,
    settings: dict[str, Any],
    allowlist_bypass: bool = False,
) -> bool:
    if opportunity.get("platform") != "vastai":
        return False
    if not allowlist_bypass and not scout_gpu_allowed(opportunity, settings):
        return False
    if safe_float(opportunity.get("profit_usd_hr"), -999999) <= 0:
        return False
    price = safe_float(opportunity.get("price_usd_hr"))
    if price <= 0 or price > max_price_usd_hr:
        return False
    risks = set(opportunity.get("risks") or [])
    hard_risks = {"cuda_below_12_9", "network_bad", "price_usd_missing"}
    if not allowlist_bypass:
        hard_risks.add("low_value_gpu")
    if hard_risks.intersection(risks):
        return False
    options = opportunity.get("rent_options") or {}
    return any((options.get(pool) or {}).get("state") == "ready" for pool in settings.get("pool_order") or SCOUT_POOL_ORDER) or scout_candidate_allowed(opportunity, settings)


def results_preferred_pool(records: list[dict[str, Any]]) -> str:
    best = max(records, key=lambda item: safe_float(item.get("profit_usd_hr"), -999999), default={})
    pool = str(best.get("pool_strategy") or "")
    return pool if pool in SCOUT_POOL_ORDER else "akoya"


def results_find_offer(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    target: dict[str, Any],
    kind: str,
    max_price_usd_hr: float,
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    gpu = normalize_gpu_name(target.get("gpu"))
    wanted_count = safe_int(target.get("gpu_count"), 0)
    machine_id = str(target.get("machine_id") or "")
    host_id = str(target.get("host_id") or "")
    pcie = str(target.get("pcie") or "")
    wanted_ask_id = str(target.get("ask_id") or target.get("last_ask_id") or "")
    allowlist_bypass = results_manual_allowlist_bypass(target)
    candidates = []
    for opportunity in state.get("opportunities", []):
        if not isinstance(opportunity, dict) or opportunity.get("platform") != "vastai":
            continue
        if normalize_gpu_name(opportunity.get("gpu")) != gpu:
            continue
        if kind == "offer" and wanted_ask_id and str(opportunity.get("id") or "") != wanted_ask_id:
            same_machine = machine_id and str(opportunity.get("machine_id") or "") == machine_id
            same_host = host_id and str(opportunity.get("host_id") or "") == host_id
            if not same_machine and not same_host:
                continue
        if kind in {"hardware", "pattern", "offer"} and wanted_count and safe_int(opportunity.get("gpu_count"), 1) != wanted_count:
            continue
        if kind == "hardware":
            same_machine = machine_id and str(opportunity.get("machine_id") or "") == machine_id
            same_host = host_id and str(opportunity.get("host_id") or "") == host_id
            if not same_machine and not same_host:
                continue
        if kind == "pattern":
            if host_id and str(opportunity.get("host_id") or "") != host_id:
                continue
            if pcie and str(opportunity.get("pcie") or "") != pcie:
                continue
        if results_active_match(actions, scout, opportunity):
            continue
        if not results_offer_ready(opportunity, max_price_usd_hr, settings, allowlist_bypass):
            continue
        candidates.append(opportunity)
    candidates.sort(
        key=lambda item: (
            str(item.get("machine_id") or "") == machine_id,
            str(item.get("host_id") or "") == host_id,
            safe_float(item.get("profit_usd_hr"), -999999),
            -safe_float(item.get("price_usd_hr")),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def results_exact_offer_for_queue(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    queue_item: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    if queue_item.get("kind") != "offer":
        return None
    ask_id = safe_int(queue_item.get("ask_id") or queue_item.get("last_ask_id"))
    if not ask_id:
        return None
    opportunity = find_opportunity_by_id(state, ask_id)
    if not opportunity or opportunity.get("platform") != "vastai":
        return None
    if results_active_match(actions, scout, opportunity):
        return None
    if scout_gpu_allowlist_block_reason({**opportunity, **queue_item}, settings) and not manual_results_override(queue_item):
        return None
    price = safe_float(opportunity.get("price_usd_hr"))
    max_price = safe_float(queue_item.get("max_price_usd_hr"), safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR))
    if price <= 0 or (max_price > 0 and price > max_price):
        return None
    risks = set(opportunity.get("risks") or [])
    if {"cuda_below_12_9", "network_bad", "price_usd_missing"}.intersection(risks):
        return None
    return opportunity


def results_manual_opportunity_from_target(target: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    ask_id = safe_int(target.get("ask_id") or target.get("id"))
    gpu = normalize_gpu_name(target.get("gpu") or target.get("gpu_model_normalized") or target.get("gpu_model_raw"))
    if not ask_id or not gpu:
        return None
    gpu_count = max(1, safe_int(target.get("gpu_count"), 1))
    price = safe_float(target.get("price_usd_hr"))
    risks: list[str] = []
    up = safe_float(target.get("net_up_mbps"))
    down = safe_float(target.get("net_down_mbps"))
    if (up and up < 10) or (down and down < 10):
        risks.append("network_bad")
    pool_order = settings.get("pool_order") or SCOUT_POOL_ORDER
    rent_options = {
        pool: {"state": "ready", "reason": "Override manual Results"}
        for pool in pool_order
    }
    return {
        "platform": "vastai",
        "id": ask_id,
        "ask_id": ask_id,
        "gpu": gpu,
        "gpu_raw": target.get("gpu_raw") or target.get("gpu"),
        "gpu_count": gpu_count,
        "host_id": target.get("host_id"),
        "machine_id": target.get("machine_id"),
        "pool": target.get("preferred_pool") or "akoya",
        "hashrate_ths": scout_expected_ths(gpu, gpu_count),
        "price_usd_hr": round_money(price) if price > 0 else price,
        "profit_usd_hr": round_money(safe_float(target.get("profit_usd_hr"))) if target.get("profit_usd_hr") is not None else None,
        "roi_pct": target.get("roi_pct"),
        "max_safe_price_usd_hr": max(safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR), price),
        "rent_options": rent_options,
        "action_state": "ready",
        "action_reason": "Override manual Results",
        "risks": risks,
        "cuda": target.get("cuda") or "",
        "pcie": target.get("pcie") or "",
        "reliability": target.get("reliability"),
        "net_up_mbps": target.get("net_up_mbps"),
        "net_down_mbps": target.get("net_down_mbps"),
        "available": True,
        "manual_results_opportunity": True,
    }


def results_queue_public(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "kind",
        "ask_id",
        "gpu",
        "gpu_count",
        "machine_id",
        "host_id",
        "pcie",
        "preferred_pool",
        "max_price_usd_hr",
        "status",
        "attempts",
        "last_error",
        "next_retry_at",
        "created_at",
        "updated_at",
        "last_attempt_at",
        "last_ask_id",
        "last_instance_id",
        "manual_override",
        "allowlist_bypass",
        "user_requested_at",
    )
    return {key: item.get(key) for key in keys if key in item}


def build_worst_gpu_rows(records: list[dict[str, Any]], settings: dict[str, Any], blacklist: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    min_hash_ratio = safe_float(settings.get("min_hash_ratio"), SCOUT_MIN_HASH_RATIO)
    blacklisted_gpus = {
        normalize_gpu_name(item.get("gpu"))
        for item in blacklist_items(blacklist)
        if str(item.get("scope") or "") == "gpu_model"
    }
    for record in records:
        gpu = normalize_gpu_name(record.get("gpu")) or str(record.get("gpu") or "")
        if not gpu:
            continue
        profit = safe_float(record.get("profit_usd_hr"), -999999)
        if profit <= -999998:
            continue
        ratio = safe_float(record.get("hash_ratio"))
        group = groups.setdefault(gpu, {
            "gpu": gpu,
            "samples": 0,
            "bad_samples": 0,
            "viable_samples": 0,
            "profitable_samples": 0,
            "sum_profit_usd_hr": 0.0,
            "worst_profit_usd_hr": None,
            "best_profit_usd_hr": None,
            "last_seen_at": None,
            "reasons": {},
        })
        group["samples"] += 1
        group["sum_profit_usd_hr"] += profit
        group["last_seen_at"] = max(safe_float(group.get("last_seen_at")), safe_float(record.get("ended_at")))
        group["worst_profit_usd_hr"] = profit if group["worst_profit_usd_hr"] is None else min(safe_float(group.get("worst_profit_usd_hr")), profit)
        group["best_profit_usd_hr"] = profit if group["best_profit_usd_hr"] is None else max(safe_float(group.get("best_profit_usd_hr"), -999999), profit)
        if profit > 0:
            group["profitable_samples"] += 1
        if profit >= min_profit and ratio >= min_hash_ratio:
            group["viable_samples"] += 1
        else:
            group["bad_samples"] += 1
            reason = str(record.get("reason") or record.get("decision") or "bad")
            group["reasons"][reason] = group["reasons"].get(reason, 0) + 1

    rows = []
    for group in groups.values():
        samples = max(1, safe_int(group.get("samples")))
        bad_samples = safe_int(group.get("bad_samples"))
        viable_samples = safe_int(group.get("viable_samples"))
        avg_profit = group["sum_profit_usd_hr"] / samples
        bad_rate = bad_samples / samples
        if samples < 2 or (viable_samples > 0 and bad_rate < 0.75 and avg_profit >= 0):
            continue
        reason = max((group.get("reasons") or {}).items(), key=lambda item: item[1], default=("", 0))[0]
        rows.append({
            "gpu": group.get("gpu"),
            "samples": samples,
            "bad_samples": bad_samples,
            "viable_samples": viable_samples,
            "profitable_samples": safe_int(group.get("profitable_samples")),
            "bad_rate_pct": round_money(bad_rate * 100),
            "avg_profit_usd_hr": round_money(avg_profit),
            "worst_profit_usd_hr": round_money(group.get("worst_profit_usd_hr")),
            "best_profit_usd_hr": round_money(group.get("best_profit_usd_hr")),
            "last_seen_at": group.get("last_seen_at"),
            "reason": reason,
            "blacklisted": group.get("gpu") in blacklisted_gpus,
        })
    rows.sort(key=lambda item: (-safe_float(item.get("bad_rate_pct")), safe_float(item.get("avg_profit_usd_hr")), -safe_int(item.get("samples"))))
    return rows[:40]


def scout_next_untested_pool(test: dict[str, Any], settings: dict[str, Any]) -> str:
    tested = {str(item.get("pool_strategy") or "") for item in scout_pool_results(test)}
    current_pool = str(test.get("pool_strategy") or "")
    for pool in settings.get("pool_order") or SCOUT_POOL_ORDER:
        if pool != current_pool and pool not in tested:
            return pool
    return ""


def scout_append_pool_result(test: dict[str, Any], decision: str, reason: str) -> dict[str, Any]:
    result = scout_result_from_test(test, decision, reason)
    test.setdefault("prior_results", []).append(result)
    append_scout_history(result)
    return result


def adopt_orphan_scout_tests(scout: dict[str, Any], actions: dict[str, Any], state: dict[str, Any]) -> bool:
    tests = scout.setdefault("tests", {})
    known_asks = {str(test.get("ask_id")) for test in tests.values() if isinstance(test, dict)}
    settings = scout_settings(scout)
    current = now_ts()
    operation = state.get("operation") or {}
    changed = False

    for ask_id, action in list(actions.items()):
        if not isinstance(action, dict) or str(ask_id) in known_asks:
            continue
        if action.get("state") not in {"renting", "rented"}:
            continue
        if action.get("scout_preserved") or action.get("scout_final") or action.get("scout_approved"):
            continue
        if not action.get("scout_test_id"):
            continue

        pool = str(action.get("pool_strategy") or "akoya")
        worker_name = str(action.get("worker_name") or strategy_worker_name(pool, ask_id))
        worker = find_operation_worker(operation, worker_name, pool)
        gpu = action.get("gpu") or (worker or {}).get("gpu")
        gpu_count = action.get("gpu_count") or (worker or {}).get("rented_gpu_count") or (worker or {}).get("gpu_count") or 1
        test_seconds = settings["test_seconds"]
        worker_online = bool(worker and worker.get("is_connected"))
        adopted_started = current - max(0, test_seconds - 60) if worker_online else current
        test_id = str(action.get("scout_test_id") or f"scout-{ask_id}-{pool}-adopted-{uuid4().hex[:8]}")
        sample = {
            "ts": current,
            "hashrate_ths": round(safe_float((worker or {}).get("hashrate_ths")), 4),
            "revenue_usd_hr": round_money((worker or {}).get("revenue_usd_hr")),
            "profit_usd_hr": round_money((worker or {}).get("profit_usd_hr")),
        }

        action["scout_test_id"] = test_id
        action["reason"] = f"Scout readotado: medindo {strategy_label(pool)}"
        action["updated_at"] = current
        tests[test_id] = {
            "test_id": test_id,
            "parent_test_id": "",
            "ask_id": safe_int(ask_id),
            "status": "testing",
            "decision": "measuring",
            "reason": f"Readotado sem destruir; medindo {strategy_label(pool)}",
            "pool_strategy": pool,
            "next_pool_strategy": "",
            "worker_name": worker_name,
            "instance_id": action.get("instance_id"),
            "host_id": action.get("host_id"),
            "machine_id": action.get("machine_id"),
            "gpu": gpu,
            "gpu_count": gpu_count,
            "price_usd_hr": action.get("price_usd_hr"),
            "expected_ths": scout_expected_ths(gpu, gpu_count),
            "started_at": adopted_started,
            "stage_started_at": adopted_started,
            "stage_deadline_at": adopted_started + test_seconds,
            "test_seconds": test_seconds,
            "worker_timeout_seconds": settings["worker_timeout_seconds"],
            "offline_timeout_seconds": settings["offline_timeout_seconds"],
            "min_profit_usd_hr": settings["min_profit_usd_hr"],
            "min_hash_ratio": settings["min_hash_ratio"],
            "max_price_usd_hr": settings["max_price_usd_hr"],
            "worker_seen_at": current if worker_online else None,
            "last_worker_seen_at": current if worker_online else None,
            "samples": [sample] if worker_online else [],
        }
        known_asks.add(str(ask_id))
        changed = True

    return changed


async def revalidate_vast_ask(ask_id: int) -> dict[str, Any]:
    body = {
        "limit": 1,
        "type": "ondemand",
        "ask_contract_id": {"eq": ask_id},
        "rentable": {"eq": True},
        "rented": {"eq": False},
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(VAST_BUNDLES_URL, json=body, headers=vast_headers())
        response.raise_for_status()
        data = response.json()
    offers = data.get("offers") or []
    if not offers:
        raise HTTPException(status_code=409, detail="Ask nao esta mais disponivel/rentable na Vast")
    offer = offers[0]
    if bool(offer.get("rented", False)) or not bool(offer.get("rentable", False)):
        raise HTTPException(status_code=409, detail="Ask voltou indisponivel/rented na revalidacao")
    return offer


def vast_offer_price_hr(offer: dict[str, Any]) -> float:
    return vast.offer_price_hr(offer)


def sanitize_vast_response(data: dict[str, Any]) -> dict[str, Any]:
    return vast.sanitize_response(data)


async def accept_vast_ask(ask_id: int, opportunity: dict[str, Any], price_hr: float, strategy: str) -> dict[str, Any]:
    return await vast.accept_ask(ask_id, opportunity, price_hr, strategy)


def vast_env_for_strategy(strategy: str, worker_name: str, gpu_name: Any) -> dict[str, str]:
    return vast.env_for_strategy(strategy, worker_name, gpu_name)


def vast_instance_payload_for_strategy(strategy: str, worker_name: str, gpu_name: Any, env: dict[str, str]) -> dict[str, Any]:
    return vast.instance_payload_for_strategy(strategy, worker_name, gpu_name, env)


def vast_update_payload_for_strategy(instance_id: int, strategy: str, worker_name: str, gpu_name: Any, env: dict[str, str]) -> dict[str, Any]:
    return vast.update_payload_for_strategy(instance_id, strategy, worker_name, gpu_name, env)


async def destroy_vast_instance(instance_id: int) -> dict[str, Any]:
    return await vast.destroy_instance(instance_id)


async def update_vast_instance_pool_config(instance_id: int, strategy: str, worker_name: str, gpu_name: Any) -> dict[str, Any]:
    return await vast.update_instance_pool_config(instance_id, strategy, worker_name, gpu_name)


async def recycle_vast_instance(instance_id: int) -> dict[str, Any]:
    return await vast.recycle_instance(instance_id)


async def switch_vast_instance_pool(
    actions: dict[str, Any],
    test: dict[str, Any],
    target_pool: str,
    reason: str,
) -> dict[str, Any]:
    instance_id = safe_int(test.get("instance_id"))
    if instance_id <= 0:
        raise HTTPException(status_code=409, detail="Instancia ausente para troca in-place")
    ask_id = str(test.get("ask_id"))
    worker_name = strategy_worker_name(target_pool, ask_id)
    update_result = await update_vast_instance_pool_config(instance_id, target_pool, worker_name, test.get("gpu"))
    recycle_result = await recycle_vast_instance(instance_id)
    current = now_ts()
    switch_attempts = safe_int(test.get("switch_attempts")) + 1
    test.update({
        "decision": "waiting_worker",
        "reason": reason,
        "pool_strategy": target_pool,
        "switch_target_pool": target_pool,
        "switch_attempts": switch_attempts,
        "worker_name": worker_name,
        "stage_started_at": current,
        "stage_deadline_at": current + safe_float(test.get("test_seconds"), SCOUT_TEST_SECONDS),
        "worker_seen_at": None,
        "last_worker_seen_at": None,
        "samples": [],
        "latest_hashrate_ths": 0.0,
        "latest_profit_usd_hr": None,
        "latest_hash_ratio": None,
        "zero_hash_started_at": None,
        "zero_hash_elapsed_s": 0,
        "failure_tag": "",
        "switch_started_at": current,
        "switch_error": "",
        "switch_result": {"update": update_result, "recycle": recycle_result},
    })
    action = action_by_id(actions, ask_id)
    if action:
        action.update({
            "pool_strategy": target_pool,
            "switch_target_pool": target_pool,
            "switch_attempts": switch_attempts,
            "worker_name": worker_name,
            "reason": reason,
            "updated_at": current,
            "switch_error": "",
            "switch_result": {"update": update_result, "recycle": recycle_result},
        })
        actions[ask_id] = action
        await save_vast_actions(actions)
    return {"update": update_result, "recycle": recycle_result}


async def start_scout_rent(
    scout: dict[str, Any],
    actions: dict[str, Any],
    state: dict[str, Any],
    ask_id: int,
    strategy: str,
    parent_test_id: str | None = None,
) -> dict[str, Any]:
    opportunity = find_opportunity_by_id(state, ask_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Oferta Vast nao encontrada no estado atual")
    settings = scout_settings(scout)
    queue = scout.get("queue") if isinstance(scout.get("queue"), dict) else {}
    queue_item = queue.get(str(ask_id)) if isinstance(queue.get(str(ask_id)), dict) else None
    manual_override = manual_results_override(queue_item)
    allowlist_target = {**opportunity, **(queue_item or {})}
    allowlist_reason = scout_gpu_allowlist_block_reason(allowlist_target, settings)
    if allowlist_reason and not manual_override:
        raise HTTPException(status_code=409, detail=allowlist_reason)
    hardware_reason = scout_hardware_block_reason(opportunity)
    if hardware_reason:
        raise HTTPException(status_code=409, detail=hardware_reason)
    if vast_offer_is_blacklisted(opportunity, load_vast_blacklist()) and not manual_override:
        raise HTTPException(status_code=409, detail="Hardware bloqueado na blacklist Vast")
    rent_option = (opportunity.get("rent_options") or {}).get(strategy) or {}
    scout_ready = scout_candidate_allowed(opportunity, settings)
    queue_ready = bool(
        queue_item
        and (
            queue_item.get("queue_status") == "queued"
            or (queue_item.get("queue_status") == "renting" and (queue_item.get("is_new_machine") or queue_item.get("source") == "trigger"))
        )
    )
    if rent_option.get("state") != "ready" and not scout_ready and not queue_ready:
        raise HTTPException(status_code=409, detail=rent_option.get("reason") or "Pool nao pronto para teste")

    now = now_ts()
    test_id = f"scout-{ask_id}-{strategy}-{uuid4().hex[:8]}"
    if queue_item:
        queue_item["queue_status"] = "renting"
        queue_item["sniper_status"] = "trigger Vast alugando" if queue_item.get("source") == "trigger" else ("alugando agora" if queue_item.get("is_new_machine") else "renting")
        queue_item["skip_reason"] = "enviando aceite para Vast"
        queue_item["last_seen_at"] = now
        queue_item["sniped_at"] = now
        machine_index = scout_machine_index_items()
        _, index_changed, _ = touch_scout_machine_index(machine_index, queue_item, "sniped")
        if index_changed:
            save_scout_machine_index(machine_index)
    actions[str(ask_id)] = {
        "state": "renting",
        "reason": (
            f"Trigger Vast {(queue_item or {}).get('trigger_name')} alugando {strategy_label(strategy)}"
            if (queue_item or {}).get("source") == "trigger"
            else (f"Sniper novo alugando {strategy_label(strategy)}" if (queue_item or {}).get("is_new_machine") else f"Scout testando {strategy_label(strategy)}")
        ),
        "ask_id": ask_id,
        "worker_name": strategy_worker_name(strategy, ask_id),
        "pool_strategy": strategy,
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "price_usd_hr": opportunity.get("price_usd_hr"),
        "max_safe_price_usd_hr": opportunity.get("max_safe_price_usd_hr"),
        "created_at": now,
        "updated_at": now,
        "scout_test_id": test_id,
        "machine_key": (queue_item or {}).get("machine_key") or scout_machine_key_from_item(opportunity),
        "is_new_machine": (queue_item or {}).get("is_new_machine", False),
        "machine_first_seen_at": (queue_item or {}).get("machine_first_seen_at"),
        "marketplace_first_seen_at": (queue_item or {}).get("first_seen_at"),
        "sniped_at": now,
        "sniper_status": "trigger Vast alugando" if (queue_item or {}).get("source") == "trigger" else ("alugando agora" if (queue_item or {}).get("is_new_machine") else ""),
        "source": (queue_item or {}).get("source"),
        "trigger_id": (queue_item or {}).get("trigger_id"),
        "trigger_name": (queue_item or {}).get("trigger_name"),
    }
    if not vast_strategy_configured(strategy):
        detail = f"Template/imagem ou wallet ausente para {strategy_label(strategy)}"
        actions[str(ask_id)].update({
            "state": "failed",
            "reason": "Falha ao iniciar Scout",
            "error": detail,
            "updated_at": now_ts(),
        })
        if queue_item:
            queue_item["queue_status"] = "cooldown"
            queue_item["sniper_status"] = "falhou"
            queue_item["skip_reason"] = detail
            queue_item["last_seen_at"] = now_ts()
        await save_vast_actions(actions)
        await save_scout_state(scout)
        raise HTTPException(status_code=409, detail=detail)
    await save_vast_actions(actions)

    try:
        offer = await revalidate_vast_ask(ask_id)
        revalidated_price = vast_offer_price_hr(offer)
        max_safe = safe_float((queue_item or {}).get("max_price_usd_hr") or settings.get("max_price_usd_hr"))
        if revalidated_price <= 0:
            raise HTTPException(status_code=409, detail="Preco Vast indisponivel na revalidacao")
        if max_safe <= 0 or revalidated_price > max_safe:
            raise HTTPException(status_code=409, detail=f"Preco fora do teto Scout: ${revalidated_price:.4f}/h > ${max_safe:.4f}/h")
        result = await accept_vast_ask(ask_id, opportunity, revalidated_price, strategy)
    except Exception as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        current = now_ts()
        rate_limited = scout_vast_rate_limit_error(detail)
        if scout_transient_vast_error(detail) or rate_limited:
            retry_started = safe_float((queue_item or {}).get("retry_started_at")) or current
            retry_until = safe_float((queue_item or {}).get("retry_until_at")) or (retry_started + SCOUT_TRANSIENT_RETRY_WINDOW_SECONDS)
            attempts = safe_int((queue_item or {}).get("retry_attempts"), 0) + 1
            retry_delay = max(SCOUT_TRANSIENT_RETRY_SECONDS, 120) if rate_limited else SCOUT_TRANSIENT_RETRY_SECONDS
            retry_reason = "Rate limit Vast; aguardando retry" if rate_limited else "Ask indisponivel na Vast; aguardando retry"
            actions[str(ask_id)].update({
                "state": "waiting_market",
                "reason": retry_reason,
                "error": str(detail),
                "updated_at": current,
            })
            if queue_item:
                queue_item["queue_status"] = "cooldown"
                queue_item["sniper_status"] = "rate limit Vast" if rate_limited and current < retry_until else ("aguardando Vast" if current < retry_until else "aguardando nova aparicao")
                queue_item["skip_reason"] = retry_reason
                queue_item["transient_unavailable"] = True
                queue_item["retry_started_at"] = retry_started
                queue_item["last_retry_at"] = current
                queue_item["next_retry_at"] = current + retry_delay if current < retry_until else 0
                queue_item["retry_until_at"] = retry_until
                queue_item["retry_attempts"] = attempts
                queue_item["last_retry_error"] = str(detail)
                queue_item["last_seen_at"] = current
            await save_vast_actions(actions)
            await save_scout_state(scout)
            raise

        failed = {
            "test_id": test_id,
            "ask_id": ask_id,
            "gpu": opportunity.get("gpu"),
            "gpu_count": opportunity.get("gpu_count"),
            "host_id": opportunity.get("host_id"),
            "machine_id": opportunity.get("machine_id"),
            "pool_strategy": strategy,
            "price_usd_hr": opportunity.get("price_usd_hr"),
            "expected_ths": opportunity.get("hashrate_ths"),
            "started_at": now,
            "ended_at": current,
            "decision": "failed",
            "reason": str(detail),
            "machine_key": (queue_item or {}).get("machine_key") or scout_machine_key_from_item(opportunity),
            "is_new_machine": (queue_item or {}).get("is_new_machine", False),
            "machine_first_seen_at": (queue_item or {}).get("machine_first_seen_at"),
            "marketplace_first_seen_at": (queue_item or {}).get("first_seen_at"),
        }
        append_scout_history(failed)
        actions[str(ask_id)].update({
            "state": "failed",
            "reason": "Falha ao iniciar Scout",
            "error": str(detail),
            "updated_at": current,
        })
        if queue_item:
            queue_item["queue_status"] = "cooldown"
            queue_item["sniper_status"] = "falhou"
            queue_item["skip_reason"] = str(detail)
            queue_item["last_seen_at"] = current
        await save_vast_actions(actions)
        await save_scout_state(scout)
        raise

    action = actions[str(ask_id)]
    action.update({
        "state": "rented",
        "reason": f"Scout medindo {strategy_label(strategy)} por {settings['test_seconds'] // 60} min",
        "instance_id": result.get("instance_id"),
        "worker_name": result.get("worker_name"),
        "pool_strategy": result.get("pool_strategy", strategy),
        "price_usd_hr": result.get("price_usd_hr"),
        "updated_at": now_ts(),
        "vast_response": result.get("raw", {}),
    })
    if queue_item:
        queue_item["queue_status"] = "rented"
        queue_item["sniper_status"] = "testando"
        queue_item["skip_reason"] = "teste Scout ativo"
        queue_item["last_seen_at"] = now_ts()
        scout_reset_transient_retry(queue_item)
    scout.setdefault("tests", {})[test_id] = {
        "test_id": test_id,
        "parent_test_id": parent_test_id,
        "ask_id": ask_id,
        "status": "testing",
        "decision": "measuring",
        "reason": f"Medindo {strategy_label(strategy)}",
        "pool_strategy": strategy,
        "next_pool_strategy": next((p for p in settings["pool_order"] if p != strategy), ""),
        "worker_name": result.get("worker_name"),
        "instance_id": result.get("instance_id"),
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "pcie": opportunity.get("pcie"),
        "cuda": opportunity.get("cuda"),
        "reliability": opportunity.get("reliability"),
        "net_up_mbps": opportunity.get("net_up_mbps"),
        "net_down_mbps": opportunity.get("net_down_mbps"),
        "price_usd_hr": result.get("price_usd_hr"),
        "expected_ths": opportunity.get("hashrate_ths"),
        "started_at": now,
        "stage_started_at": now,
        "stage_deadline_at": now + settings["test_seconds"],
        "test_seconds": settings["test_seconds"],
        "worker_timeout_seconds": settings["worker_timeout_seconds"],
        "offline_timeout_seconds": settings["offline_timeout_seconds"],
        "zero_hash_timeout_seconds": settings["zero_hash_timeout_seconds"],
        "zero_hash_started_at": None,
        "zero_hash_elapsed_s": 0,
        "zero_hash_pool_failures": 0,
        "failure_tag": "",
        "min_profit_usd_hr": settings["min_profit_usd_hr"],
        "min_hash_ratio": settings["min_hash_ratio"],
        "max_price_usd_hr": (queue_item or {}).get("max_price_usd_hr") or settings["max_price_usd_hr"],
        "worker_seen_at": None,
        "last_worker_seen_at": None,
        "samples": [],
    }
    if queue_item:
        scout["tests"][test_id].update({
            "retest_allowed": queue_item.get("retest_allowed"),
            "retest_reason": queue_item.get("retest_reason"),
            "previous_result_summary": queue_item.get("previous_result_summary"),
            "improvement_summary": queue_item.get("improvement_summary"),
            "queue_priority_score": queue_item.get("priority_score"),
            "machine_key": queue_item.get("machine_key"),
            "is_new_machine": queue_item.get("is_new_machine"),
            "machine_first_seen_at": queue_item.get("machine_first_seen_at"),
            "marketplace_first_seen_at": queue_item.get("first_seen_at"),
            "marketplace_last_seen_at": queue_item.get("last_seen_at"),
            "source": queue_item.get("source"),
            "trigger_id": queue_item.get("trigger_id"),
            "trigger_name": queue_item.get("trigger_name"),
            "trigger_max_price_usd_hr": queue_item.get("trigger_max_price_usd_hr"),
        })
    await save_vast_actions(actions)
    await save_scout_state(scout)
    return scout["tests"][test_id]


async def start_scout_clore_rent(
    scout: dict[str, Any],
    actions: dict[str, Any],
    clore_actions: dict[str, Any],
    state: dict[str, Any],
    server_id: int,
    strategy: str,
    parent_test_id: str | None = None,
    opportunity_override: dict[str, Any] | None = None,
    allow_test_fallback: bool = False,
    source: str = "manual_clore",
) -> dict[str, Any]:
    strategy = strategy.strip().lower()
    if strategy not in clore.pool_strategies():
        raise HTTPException(status_code=400, detail="Pool Clore invalido")
    opportunity = find_clore_opportunity_by_id(state, server_id)
    if not opportunity and allow_test_fallback and isinstance(opportunity_override, dict):
        opportunity = dict(opportunity_override)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Servidor Clore nao encontrado no estado atual")
    settings = scout_settings(scout)
    rent_option = (opportunity.get("rent_options") or {}).get(strategy) or {}
    if rent_option.get("state") != "ready" and not allow_test_fallback:
        raise HTTPException(status_code=409, detail=rent_option.get("reason") or "Clore nao pronta para Scout")
    hardware_reason = scout_hardware_block_reason(opportunity)
    if hardware_reason:
        raise HTTPException(status_code=409, detail=hardware_reason)
    decision = str(opportunity.get("decision") or "")
    if decision and decision not in CLORE_MANUAL_RENT_DECISIONS and not allow_test_fallback:
        raise HTTPException(status_code=409, detail="Clore bloqueada: decisao atual nao e ALUGAR/MARGEM/RISCO")
    previous = action_by_id(clore_actions, server_id)
    if previous and previous.get("state") in {"renting", "rented"}:
        raise HTTPException(status_code=409, detail="Servidor Clore ja tem acao ativa")
    if not clore.configured(strategy):
        raise HTTPException(status_code=409, detail=f"Imagem/API/wallet Clore ausente para {clore.strategy_label(strategy)}")

    market = await clore.marketplace()
    server = next((item for item in market.get("servers", []) or [] if safe_int(item.get("id")) == server_id), None)
    if not server:
        raise HTTPException(status_code=409, detail="Servidor Clore nao existe mais no marketplace oficial")
    if server.get("rented", True):
        raise HTTPException(status_code=409, detail="Servidor Clore ficou rented antes do Scout")

    wallets = await clore.wallets()
    currencies = clore.eligible_currencies(server, wallets)
    if not currencies:
        reasons = "; ".join(clore.currency_rejection_reasons(server, wallets))
        suffix = f": {reasons}" if reasons else ""
        raise HTTPException(status_code=409, detail=f"Nenhuma moeda Clore aceita tem saldo/configuracao{suffix}")

    price_day = safe_float(opportunity.get("cost_usd_day")) or safe_float(opportunity.get("price_usd_hr")) * 24
    if price_day <= 0:
        raise HTTPException(status_code=409, detail="Preco USD Clore ausente para Scout")
    price_hr = price_day / 24
    max_safe_price = safe_float(opportunity.get("max_safe_price_usd_hr")) or safe_float(settings.get("max_price_usd_hr"))
    if decision == "green" and max_safe_price > 0 and price_hr > max_safe_price:
        raise HTTPException(status_code=409, detail=f"Preco Clore ${price_hr:.2f}/h acima do teto ${max_safe_price:.2f}/h")

    spot = await clore.spot_marketplace(server_id)
    spot_server = ((spot.get("market") or {}).get("server") or {}) if spot.get("exists", True) else {}
    if spot.get("exists") is False:
        raise HTTPException(status_code=409, detail="Mercado Clore nao existe mais para este server")
    if spot_server and not spot_server.get("online", True):
        raise HTTPException(status_code=409, detail="Servidor Clore esta offline na revalidacao")
    if spot_server and str(spot_server.get("visibility") or "public") != "public":
        raise HTTPException(status_code=409, detail="Servidor Clore nao esta publico na revalidacao")

    now = now_ts()
    test_id = f"scout-clore-{server_id}-{strategy}-{uuid4().hex[:8]}"
    worker_name = clore.strategy_worker_name(strategy, server_id)
    first_currency = currencies[0]
    first_native_price_day = clore_marketplace_native_price_day(server, first_currency)
    risks = opportunity.get("risks") or []
    source_label = "Auto Clore" if source == "auto_clore" else "Scout manual Clore"
    decision_label = opportunity_decision_label(decision)
    auto_log = (
        f"Auto Clore: decisao {decision_label}; lucro prev ${safe_float(opportunity.get('profit_usd_hr')):.2f}/h; "
        f"custo ${price_hr:.2f}/h; pool {clore.strategy_label(strategy)}"
        if source == "auto_clore"
        else ""
    )
    scout_price_gate = max_safe_price if decision == "green" else max(
        safe_float(settings.get("max_price_usd_hr")),
        price_hr,
    )
    clore_actions[str(server_id)] = {
        "provider": "clore",
        "server_id": server_id,
        "state": "renting",
        "pool_strategy": strategy,
        "worker_name": worker_name,
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "price_usd_hr": round_money(price_hr),
        "price_usd_day": round_money(price_day),
        "native_price_day": first_native_price_day,
        "max_safe_price_usd_hr": max_safe_price,
        "opportunity_decision": decision,
        "risks": risks,
        "currency": first_currency,
        "image": clore.image_for_strategy(strategy),
        "reason": f"{source_label} medindo {clore.strategy_label(strategy)}",
        "source": source,
        "source_label": source_label,
        "auto_decision": decision if source == "auto_clore" else "",
        "auto_decision_label": decision_label if source == "auto_clore" else "",
        "auto_log": auto_log,
        "created_at": now,
        "updated_at": now,
        "scout_test_id": test_id,
    }
    await save_clore_actions(clore_actions)

    create_errors: list[str] = []
    result = None
    for candidate_currency in currencies:
        native_price_day = clore_marketplace_native_price_day(server, candidate_currency)
        if native_price_day <= 0:
            continue
        action_server = clore_marketplace_server_payload(server, opportunity, candidate_currency, native_price_day, price_day)
        clore_actions[str(server_id)].update({
            "currency": candidate_currency,
            "native_price_day": native_price_day,
            "updated_at": now_ts(),
        })
        await save_clore_actions(clore_actions)
        try:
            result = await clore.create_order(server_id, strategy, action_server, native_price_day, candidate_currency)
            break
        except HTTPException as exc:
            detail = str(exc.detail)
            create_errors.append(f"{candidate_currency}: {detail}")
            if "currency-not-allowed" in detail:
                continue
            clore_actions[str(server_id)].update({
                "state": "failed",
                "error": detail,
                "updated_at": now_ts(),
            })
            await save_clore_actions(clore_actions)
            raise
    if result is None:
        clore_actions[str(server_id)].update({
            "state": "failed",
            "error": "Nenhuma moeda Clore criou ordem: " + "; ".join(create_errors),
            "updated_at": now_ts(),
        })
        await save_clore_actions(clore_actions)
        raise HTTPException(status_code=409, detail="Nenhuma moeda Clore criou ordem: " + "; ".join(create_errors))

    clore_actions[str(server_id)].update({
        "state": "renting",
        "create_result": result,
        "worker_name": result.get("worker_name") or worker_name,
        "updated_at": now_ts(),
    })
    await save_clore_actions(clore_actions)
    clore_actions = await sync_clore_actions_with_orders(clore_actions, force=True)
    action = action_by_id(clore_actions, server_id) or clore_actions[str(server_id)]
    order_id = action.get("order_id")
    next_pool = next((pool for pool in settings["pool_order"] if pool != strategy), "")
    scout.setdefault("tests", {})[test_id] = {
        "test_id": test_id,
        "parent_test_id": parent_test_id,
        "provider": "clore",
        "offer_id": server_id,
        "server_id": server_id,
        "order_id": order_id,
        "currency": action.get("currency") or first_currency,
        "image": action.get("image") or clore.image_for_strategy(strategy),
        "status": "testing",
        "decision": "waiting_worker",
        "reason": f"Medindo Clore {clore.strategy_label(strategy)}",
        "pool_strategy": strategy,
        "next_pool_strategy": next_pool,
        "manual_next_pool_strategy": next_pool,
        "worker_name": action.get("worker_name") or worker_name,
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "pcie": opportunity.get("pcie"),
        "cuda": opportunity.get("cuda"),
        "reliability": opportunity.get("reliability"),
        "net_up_mbps": opportunity.get("net_up_mbps"),
        "net_down_mbps": opportunity.get("net_down_mbps"),
        "opportunity_decision": decision,
        "risks": risks,
        "price_usd_hr": action.get("price_usd_hr") or round_money(price_hr),
        "expected_ths": opportunity.get("hashrate_ths") or opportunity.get("expected_ths"),
        "started_at": now,
        "stage_started_at": now,
        "stage_deadline_at": now + settings["test_seconds"],
        "test_seconds": settings["test_seconds"],
        "worker_timeout_seconds": settings["worker_timeout_seconds"],
        "offline_timeout_seconds": settings["offline_timeout_seconds"],
        "zero_hash_timeout_seconds": settings["zero_hash_timeout_seconds"],
        "zero_hash_started_at": None,
        "zero_hash_elapsed_s": 0,
        "zero_hash_pool_failures": 0,
        "failure_tag": "",
        "min_profit_usd_hr": settings["min_profit_usd_hr"],
        "min_hash_ratio": settings["min_hash_ratio"],
        "max_safe_price_usd_hr": max_safe_price,
        "max_price_usd_hr": scout_price_gate or settings["max_price_usd_hr"],
        "worker_seen_at": None,
        "last_worker_seen_at": None,
        "samples": [],
        "source": source,
        "source_label": source_label,
        "auto_decision": decision if source == "auto_clore" else "",
        "auto_decision_label": decision_label if source == "auto_clore" else "",
        "auto_log": auto_log,
    }
    await save_clore_actions(clore_actions)
    await save_scout_state(scout)
    return scout["tests"][test_id]


def results_build_scout_queue_item(
    opportunity: dict[str, Any],
    queue_item: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    current = now_ts()
    return {
        "ask_id": safe_int(opportunity.get("id")),
        "gpu": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "price_usd_hr": opportunity.get("price_usd_hr"),
        "expected_ths": opportunity.get("hashrate_ths"),
        "profit_usd_hr": opportunity.get("profit_usd_hr"),
        "roi_pct": opportunity.get("roi_pct"),
        "host_id": opportunity.get("host_id"),
        "machine_id": opportunity.get("machine_id"),
        "cuda": opportunity.get("cuda"),
        "pcie": opportunity.get("pcie"),
        "reliability": opportunity.get("reliability"),
        "net_up_mbps": opportunity.get("net_up_mbps"),
        "net_down_mbps": opportunity.get("net_down_mbps"),
        "risks": opportunity.get("risks") or [],
        "machine_key": scout_machine_key_from_item(opportunity),
        "is_new_machine": False,
        "machine_first_seen_at": current,
        "first_seen_at": current,
        "last_seen_at": current,
        "priority_score": 80000 + safe_float(opportunity.get("profit_usd_hr")),
        "queue_status": "queued",
        "skip_reason": "Results: aluguel solicitado por historico lucrativo",
        "retest_allowed": True,
        "retest_reason": f"Results {queue_item.get('kind')} lucrativo",
        "improvement_summary": "results lucrativo",
        "source": "results",
        "results_id": queue_item.get("id"),
        "results_kind": queue_item.get("kind"),
        "results_label": queue_item.get("gpu"),
        "manual_override": bool(queue_item.get("manual_override")),
        "allowlist_bypass": bool(queue_item.get("allowlist_bypass")),
        "user_requested_at": queue_item.get("user_requested_at"),
        "max_price_usd_hr": queue_item.get("max_price_usd_hr") or settings.get("max_price_usd_hr"),
    }


async def results_attempt_queue_item(
    results_state: dict[str, Any],
    queue_item: dict[str, Any],
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    current = now_ts()
    if not force and safe_float(queue_item.get("next_retry_at")) > current:
        return queue_item
    settings = scout_settings(scout)
    manual_override = manual_results_override(queue_item)
    allowlist_reason = scout_gpu_allowlist_block_reason(queue_item, settings)
    if allowlist_reason and not manual_override:
        queue_item.update({
            "status": "blocked",
            "last_error": allowlist_reason,
            "next_retry_at": 0,
            "updated_at": current,
        })
        return queue_item
    active = results_active_match(actions, scout, queue_item)
    if active:
        queue_item.update({
            "status": "active",
            "last_error": "Ja existe aluguel/teste local para esse alvo",
            "last_instance_id": active.get("instance_id"),
            "last_ask_id": active.get("ask_id"),
            "updated_at": current,
        })
        return queue_item
    offer = results_exact_offer_for_queue(state, actions, scout, queue_item, settings)
    if not offer and queue_item.get("kind") == "offer":
        manual_offer = results_manual_opportunity_from_target(queue_item, settings)
        if manual_offer:
            state.setdefault("opportunities", []).append(manual_offer)
            offer = manual_offer
    if not offer:
        offer = results_find_offer(
            state,
            actions,
            scout,
            queue_item,
            str(queue_item.get("kind") or "gpu"),
            safe_float(queue_item.get("max_price_usd_hr"), safe_float(settings.get("max_price_usd_hr"))),
            settings,
        )
    if not offer:
        queue_item.update({
            "status": "waiting",
            "last_error": "Sem oferta Vast lucrativa compativel agora",
            "next_retry_at": current + RESULTS_RETRY_SECONDS,
            "updated_at": current,
        })
        return queue_item

    ask_id = safe_int(offer.get("id"))
    preferred_pool = str(queue_item.get("preferred_pool") or "")
    pool_order = [preferred_pool] + [pool for pool in settings["pool_order"] if pool != preferred_pool]
    scout.setdefault("queue", {})[str(ask_id)] = results_build_scout_queue_item(offer, queue_item, settings)
    queue_item.update({
        "status": "renting",
        "last_attempt_at": current,
        "last_ask_id": ask_id,
        "attempts": safe_int(queue_item.get("attempts")) + 1,
        "updated_at": current,
    })
    await save_results_state(results_state)
    last_error = ""
    for pool in pool_order:
        if not pool or not vast_strategy_configured(pool):
            continue
        try:
            test = await start_scout_rent(scout, actions, state, ask_id, pool)
            queue_item.update({
                "status": "started",
                "last_error": "",
                "next_retry_at": 0,
                "last_instance_id": test.get("instance_id"),
                "updated_at": now_ts(),
            })
            return queue_item
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            last_error = str(detail)
            if scout_vast_rate_limit_error(detail) or scout_transient_vast_error(detail):
                break
    queue_item.update({
        "status": "waiting" if scout_vast_rate_limit_error(last_error) or scout_transient_vast_error(last_error) else "blocked",
        "last_error": last_error or "Falha ao iniciar Scout pelo Results",
        "next_retry_at": current + RESULTS_RETRY_SECONDS if scout_vast_rate_limit_error(last_error) or scout_transient_vast_error(last_error) else 0,
        "updated_at": now_ts(),
    })
    return queue_item


def results_upsert_queue_item(results_state: dict[str, Any], kind: str, target: dict[str, Any], reason: str = "") -> dict[str, Any]:
    current = now_ts()
    item_id = results_queue_id(kind, target)
    queue = results_state.setdefault("queue", {})
    item = queue.get(item_id) if isinstance(queue.get(item_id), dict) else {}
    item.update({
        "id": item_id,
        "kind": kind,
        "gpu": target.get("gpu"),
        "gpu_count": target.get("gpu_count"),
        "ask_id": target.get("ask_id") or target.get("id"),
        "machine_id": target.get("machine_id"),
        "host_id": target.get("host_id"),
        "pcie": target.get("pcie"),
        "cuda": target.get("cuda"),
        "reliability": target.get("reliability"),
        "net_up_mbps": target.get("net_up_mbps"),
        "net_down_mbps": target.get("net_down_mbps"),
        "preferred_pool": target.get("preferred_pool") or target.get("pool_strategy") or "akoya",
        "max_price_usd_hr": target.get("max_price_usd_hr"),
        "source": "results",
        "manual_override": True,
        "allowlist_bypass": True,
        "user_requested_at": item.get("user_requested_at") or current,
        "status": "waiting",
        "last_error": reason or item.get("last_error") or "Aguardando oferta Vast compativel",
        "next_retry_at": current + RESULTS_RETRY_SECONDS,
        "created_at": item.get("created_at") or current,
        "updated_at": current,
        "attempts": safe_int(item.get("attempts")),
    })
    queue[item_id] = item
    return item


def results_host_watch_payload(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    records: list[dict[str, Any]],
    settings: dict[str, Any],
    results_state: dict[str, Any],
    host_id: str = RESULTS_WATCH_HOST_ID,
) -> dict[str, Any]:
    host_id = str(host_id or "").strip()
    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    current_offers: list[dict[str, Any]] = []
    for opportunity in state.get("opportunities", []):
        if not isinstance(opportunity, dict) or opportunity.get("platform") != "vastai":
            continue
        if str(opportunity.get("host_id") or "") != host_id:
            continue
        allowlist_reason = scout_gpu_allowlist_block_reason(opportunity, settings)
        risks = set(opportunity.get("risks") or [])
        ready = (
            not allowlist_reason
            and not results_active_match(actions, scout, opportunity)
            and results_offer_ready(
                opportunity,
                max(
                    safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
                    safe_float(opportunity.get("price_usd_hr")),
                ),
                settings,
            )
        )
        active = results_active_match(actions, scout, opportunity)
        queue_id = results_queue_id("offer", {"ask_id": opportunity.get("id"), "gpu": opportunity.get("gpu")})
        queued = queue.get(queue_id) if isinstance(queue.get(queue_id), dict) else None
        if active:
            action_status = "active"
            status_reason = "ja alugada/testando"
        elif allowlist_reason:
            action_status = "blocked"
            status_reason = allowlist_reason
        elif queued and queued.get("status") in {"waiting", "renting", "blocked"}:
            action_status = queued.get("status")
            status_reason = queued.get("last_error") or "na fila Results"
        elif ready:
            action_status = "ready"
            status_reason = "H100 SXM elegivel para Scout"
        elif risks:
            action_status = "blocked"
            status_reason = ", ".join(sorted(risks))
        else:
            action_status = "no_offer"
            status_reason = "sem condicao lucrativa/pronta agora"
        current_offers.append({
            "id": queue_id,
            "ask_id": opportunity.get("id"),
            "gpu": opportunity.get("gpu"),
            "gpu_count": opportunity.get("gpu_count"),
            "machine_id": opportunity.get("machine_id"),
            "host_id": opportunity.get("host_id"),
            "price_usd_hr": opportunity.get("price_usd_hr"),
            "profit_usd_hr": opportunity.get("profit_usd_hr"),
            "roi_pct": opportunity.get("roi_pct"),
            "pcie": opportunity.get("pcie"),
            "cuda": opportunity.get("cuda"),
            "reliability": opportunity.get("reliability"),
            "net_up_mbps": opportunity.get("net_up_mbps"),
            "net_down_mbps": opportunity.get("net_down_mbps"),
            "eligible": not allowlist_reason,
            "action_status": action_status,
            "status_reason": status_reason,
            "queue": results_queue_public(queued) if queued else None,
        })
    current_offers.sort(key=lambda item: (item.get("eligible") is True, safe_float(item.get("profit_usd_hr"), -999999)), reverse=True)

    history_groups: dict[str, dict[str, Any]] = {}
    for record in records:
        if str(record.get("host_id") or "") != host_id:
            continue
        key = results_hardware_key(record)
        group = history_groups.setdefault(key, {
            "gpu": normalize_gpu_name(record.get("gpu")) or record.get("gpu"),
            "gpu_count": safe_int(record.get("gpu_count"), 1),
            "machine_id": record.get("machine_id"),
            "host_id": record.get("host_id"),
            "count": 0,
            "best_profit_usd_hr": None,
            "best_price_usd_hr": None,
            "best_pool": "",
            "last_seen_at": None,
            "last_decision": "",
        })
        group["count"] += 1
        group["last_seen_at"] = max(safe_float(group.get("last_seen_at")), safe_float(record.get("ended_at")))
        if group["best_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr")) > safe_float(group.get("best_profit_usd_hr"), -999999):
            group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            group["best_price_usd_hr"] = record.get("price_usd_hr")
            group["best_pool"] = record.get("pool_strategy")
            group["last_decision"] = record.get("decision")
    history = list(history_groups.values())
    history.sort(key=lambda item: safe_float(item.get("best_profit_usd_hr"), -999999), reverse=True)
    return {
        "host_id": host_id,
        "current_offers": current_offers[:80],
        "history": history[:80],
    }


def results_profitable_hosts_payload(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    records: list[dict[str, Any]],
    settings: dict[str, Any],
    results_state: dict[str, Any],
    raw_vast_offers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    min_profit = safe_float(settings.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    host_groups: dict[str, dict[str, Any]] = {}
    for record in records:
        host_id = str(record.get("host_id") or "")
        if not host_id or safe_float(record.get("profit_usd_hr"), -999999) < min_profit:
            continue
        group = host_groups.setdefault(host_id, {
            "host_id": host_id,
            "hits": 0,
            "machines": set(),
            "gpus": set(),
            "profit_total": 0.0,
            "avg_profit_usd_hr": 0.0,
            "best_profit_usd_hr": None,
            "best_price_usd_hr": None,
            "min_price_usd_hr": None,
            "max_seen_price_usd_hr": None,
            "best_pool": "",
            "last_seen_at": None,
        })
        profit = safe_float(record.get("profit_usd_hr"))
        price = safe_float(record.get("price_usd_hr"))
        group["hits"] += 1
        group["profit_total"] = safe_float(group.get("profit_total")) + profit
        group["avg_profit_usd_hr"] = round_money(safe_float(group.get("profit_total")) / max(1, safe_int(group.get("hits"), 1)))
        if record.get("machine_id"):
            group["machines"].add(str(record.get("machine_id")))
        gpu = normalize_gpu_name(record.get("gpu")) or str(record.get("gpu") or "")
        if gpu:
            group["gpus"].add(gpu)
        if price > 0:
            current_min = safe_float(group.get("min_price_usd_hr"))
            current_max = safe_float(group.get("max_seen_price_usd_hr"))
            group["min_price_usd_hr"] = price if current_min <= 0 else min(current_min, price)
            group["max_seen_price_usd_hr"] = max(current_max, price)
        group["last_seen_at"] = max(safe_float(group.get("last_seen_at")), safe_float(record.get("ended_at")))
        if group["best_profit_usd_hr"] is None or profit > safe_float(group.get("best_profit_usd_hr"), -999999):
            group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            group["best_price_usd_hr"] = record.get("price_usd_hr")
            group["best_pool"] = record.get("pool_strategy")

    host_ids = set(host_groups.keys())
    current_by_host: dict[str, list[dict[str, Any]]] = {host_id: [] for host_id in host_ids}
    current_offers: list[dict[str, Any]] = []
    seen_offer_ids: set[str] = set()
    for opportunity in state.get("opportunities", []):
        if not isinstance(opportunity, dict) or opportunity.get("platform") != "vastai":
            continue
        host_id = str(opportunity.get("host_id") or "")
        if host_id not in host_ids:
            continue
        seen_offer_ids.add(str(opportunity.get("id") or ""))
        allowlist_reason = scout_gpu_allowlist_block_reason(opportunity, settings)
        active = results_active_match(actions, scout, opportunity)
        queue_id = results_queue_id("offer", {"ask_id": opportunity.get("id"), "gpu": opportunity.get("gpu")})
        queued = queue.get(queue_id) if isinstance(queue.get(queue_id), dict) else None
        ready = (
            not allowlist_reason
            and not active
            and results_offer_ready(
                opportunity,
                max(safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR), safe_float(opportunity.get("price_usd_hr"))),
                settings,
            )
        )
        if active:
            action_status = "active"
            status_reason = "ja alugada/testando"
        elif allowlist_reason:
            action_status = "blocked"
            status_reason = allowlist_reason
        elif queued and queued.get("status") in {"waiting", "renting", "blocked"}:
            action_status = queued.get("status")
            status_reason = queued.get("last_error") or "na fila Results"
        elif ready:
            action_status = "ready"
            status_reason = "H100 SXM elegivel para Scout"
        else:
            action_status = "no_offer"
            status_reason = "sem oferta lucrativa/pronta agora"
        item = {
            "id": queue_id,
            "ask_id": opportunity.get("id"),
            "host_id": opportunity.get("host_id"),
            "gpu": opportunity.get("gpu"),
            "gpu_count": opportunity.get("gpu_count"),
            "machine_id": opportunity.get("machine_id"),
            "price_usd_hr": opportunity.get("price_usd_hr"),
            "profit_usd_hr": opportunity.get("profit_usd_hr"),
            "roi_pct": opportunity.get("roi_pct"),
            "pcie": opportunity.get("pcie"),
            "cuda": opportunity.get("cuda"),
            "reliability": opportunity.get("reliability"),
            "net_up_mbps": opportunity.get("net_up_mbps"),
            "net_down_mbps": opportunity.get("net_down_mbps"),
            "eligible": not allowlist_reason,
            "action_status": action_status,
            "status_reason": status_reason,
            "queue": results_queue_public(queued) if queued else None,
        }
        current_by_host[host_id].append(item)
        current_offers.append(item)

    for offer in raw_vast_offers or []:
        if not isinstance(offer, dict):
            continue
        host_id = str(offer.get("host_id") or "")
        offer_id = str(offer.get("offer_id") or "")
        if host_id not in host_ids or not offer_id or offer_id in seen_offer_ids:
            continue
        if not offer.get("on_demand_available", False) and not offer.get("rentable", False):
            continue
        item_for_allowlist = {
            "gpu": offer.get("gpu_model_normalized") or offer.get("gpu_model_raw"),
            "gpu_model_normalized": offer.get("gpu_model_normalized"),
            "gpu_model_raw": offer.get("gpu_model_raw"),
        }
        raw_target = {
            "ask_id": safe_int(offer_id),
            "gpu": item_for_allowlist.get("gpu"),
            "gpu_count": offer.get("gpu_count"),
            "machine_id": offer.get("machine_id"),
            "host_id": offer.get("host_id"),
        }
        allowlist_reason = scout_gpu_allowlist_block_reason(item_for_allowlist, settings)
        active = results_active_match(actions, scout, raw_target)
        if active:
            action_status = "active"
            status_reason = "ja alugada/testando"
        elif allowlist_reason:
            action_status = "blocked"
            status_reason = allowlist_reason
        else:
            action_status = "ready"
            status_reason = "raw Vast H100; enviar ao Scout"
        item = {
            "id": results_queue_id("offer", {"ask_id": offer_id, "gpu": item_for_allowlist.get("gpu")}),
            "ask_id": safe_int(offer_id),
            "host_id": offer.get("host_id"),
            "gpu": item_for_allowlist.get("gpu"),
            "gpu_count": offer.get("gpu_count"),
            "machine_id": offer.get("machine_id"),
            "price_usd_hr": offer.get("price_usd_hr"),
            "profit_usd_hr": None,
            "roi_pct": None,
            "pcie": f"x{safe_int(offer.get('pcie_lanes'))} / {safe_float(offer.get('pcie_bw_gbps')):.1f} GB/s" if offer.get("pcie_lanes") or offer.get("pcie_bw_gbps") else "",
            "cuda": offer.get("cuda_max_good"),
            "reliability": offer.get("reliability"),
            "net_up_mbps": offer.get("net_up_mbps"),
            "net_down_mbps": offer.get("net_down_mbps"),
            "eligible": not allowlist_reason,
            "action_status": action_status,
            "status_reason": status_reason,
            "queue": None,
            "raw_only": True,
        }
        current_by_host[host_id].append(item)
        current_offers.append(item)

    host_rows: list[dict[str, Any]] = []
    for host_id, group in host_groups.items():
        offers = current_by_host.get(host_id) or []
        h100_offers = [item for item in offers if scout_gpu_allowed(item, settings)]
        ready_h100 = [item for item in h100_offers if item.get("action_status") == "ready"]
        best_current = max(h100_offers, key=lambda item: safe_float(item.get("profit_usd_hr"), -999999), default=None)
        host_rows.append({
            "host_id": host_id,
            "hits": group.get("hits"),
            "machines_count": len(group.get("machines") or []),
            "gpus": sorted(group.get("gpus") or []),
            "avg_profit_usd_hr": group.get("avg_profit_usd_hr"),
            "best_profit_usd_hr": group.get("best_profit_usd_hr"),
            "best_price_usd_hr": group.get("best_price_usd_hr"),
            "min_price_usd_hr": group.get("min_price_usd_hr"),
            "max_seen_price_usd_hr": group.get("max_seen_price_usd_hr"),
            "best_pool": group.get("best_pool"),
            "last_seen_at": group.get("last_seen_at"),
            "current_offers_count": len(offers),
            "current_h100_count": len(h100_offers),
            "ready_h100_count": len(ready_h100),
            "best_current_h100": best_current,
            "action_status": "ready" if ready_h100 else ("active" if any(item.get("action_status") == "active" for item in h100_offers) else "no_offer"),
        })
    host_rows.sort(key=lambda item: (safe_float(item.get("avg_profit_usd_hr"), -999999), safe_float(item.get("best_profit_usd_hr"), -999999)), reverse=True)
    current_offers.sort(
        key=lambda item: (
            item.get("eligible") is True,
            item.get("action_status") == "ready",
            safe_float(item.get("profit_usd_hr"), -999999),
        ),
        reverse=True,
    )
    return {
        "min_profit_usd_hr": min_profit,
        "hosts": host_rows[:60],
        "current_offers": current_offers[:120],
    }


def remove_scout_queue_entries_for_target(scout: dict[str, Any], target: dict[str, Any], reason: str) -> int:
    removed = 0
    ask_id = str(target.get("ask_id") or "")
    current = now_ts()
    for bucket_name in ("queue", "radar"):
        bucket = scout.get(bucket_name) if isinstance(scout.get(bucket_name), dict) else {}
        if not isinstance(bucket, dict):
            continue
        for item_id, item in list(bucket.items()):
            if not isinstance(item, dict):
                continue
            same_ask = ask_id and str(item.get("ask_id") or item_id) == ask_id
            if not same_ask and not scout_same_hardware(item, target):
                continue
            removed += 1
            bucket.pop(item_id, None)
        scout[bucket_name] = bucket
    scout["manual_destroy_blocked_at"] = current
    scout["manual_destroy_blocked_reason"] = reason
    return removed


def archive_results_queue_entries_for_target(results_state: dict[str, Any], target: dict[str, Any], reason: str) -> int:
    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    archived = 0
    current = now_ts()
    for item in queue.values():
        if not isinstance(item, dict) or item.get("status") == "archived":
            continue
        if not scout_same_hardware(item, target):
            continue
        item.update({
            "status": "archived",
            "last_error": reason,
            "next_retry_at": 0,
            "updated_at": current,
        })
        archived += 1
    return archived


async def safe_cancel_clore_order(order_id: int, reason: str) -> dict[str, Any]:
    try:
        return await clore.cancel_order(order_id, reason)
    except HTTPException as exc:
        detail = str(exc.detail)
        if "order_not_active" in detail.lower():
            return {
                "status": "already_inactive",
                "reason": reason,
                "error": detail,
            }
        raise


async def finish_scout_test(
    scout: dict[str, Any],
    actions: dict[str, Any],
    test: dict[str, Any],
    decision: str,
    reason: str,
    destroy: bool = False,
    blacklist: bool = False,
    final_pool: str | None = None,
    final_profit_usd_hr: float | None = None,
    clore_actions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = str(test.get("provider") or "vastai").lower()
    is_clore = provider == "clore"
    ask_id = str(test.get("ask_id"))
    server_id = str(test.get("server_id") or test.get("offer_id") or "")
    action = action_by_id(clore_actions or {}, server_id) if is_clore else action_by_id(actions, ask_id)
    instance_id = safe_int(test.get("instance_id") or (action or {}).get("instance_id"))
    order_id = safe_int(test.get("order_id") or (action or {}).get("order_id"))
    destroy_result = None
    if is_clore and destroy and order_id > 0:
        destroy_result = await safe_cancel_clore_order(order_id, reason)
    elif is_clore and destroy:
        destroy_result = {"status": "missing_order_id", "reason": reason}
    elif destroy and instance_id > 0:
        destroy_result = await destroy_vast_instance(instance_id)
    if blacklist and not is_clore:
        blacklist_state = load_vast_blacklist()
        blacklist_source = dict(test)
        if action:
            blacklist_source.update(action)
        add_vast_blacklist_item(blacklist_state, blacklist_source, reason)
        save_vast_blacklist(blacklist_state)

    result = scout_result_from_test(test, decision, reason)
    if test.get("prior_results"):
        result["prior_results"] = test.get("prior_results")
    if final_pool and decision in {"keep", "switch_failed_keep_current"}:
        final_pool_text = str(final_pool)
        prior_matches = [
            item for item in scout_pool_results(test)
            if str(item.get("pool_strategy") or "") == final_pool_text
        ]
        selected = max(prior_matches, key=lambda item: safe_float(item.get("profit_usd_hr"), -999999), default={})
        for key in (
            "pool_strategy",
            "live_ths_avg",
            "live_ths_best",
            "hash_ratio",
            "revenue_usd_hr",
            "profit_usd_hr",
            "price_usd_hr",
            "expected_ths",
            "worker_seen_at",
            "vast_cur_state",
            "vast_actual_status",
            "vast_status_msg",
        ):
            if key in selected:
                result[key] = selected.get(key)
        result["pool_strategy"] = final_pool_text
        result["selected_pool_result_ended_at"] = selected.get("ended_at")
        if final_profit_usd_hr is not None:
            result["profit_usd_hr"] = round_money(final_profit_usd_hr)
    result["destroy_result"] = destroy_result
    append_scout_history(result)

    test.update({
        "status": decision,
        "decision": decision,
        "reason": reason,
        "ended_at": now_ts(),
        "destroy_result": destroy_result,
    })
    if not is_clore:
        queue = scout.get("queue") if isinstance(scout.get("queue"), dict) else {}
        queue_item = queue.get(ask_id) if isinstance(queue.get(ask_id), dict) else None
        if queue_item:
            queue_item["queue_status"] = "rented" if decision in {"keep", "switch_failed_keep_current"} else "cooldown"
            queue_item["skip_reason"] = reason
            queue_item["last_seen_at"] = now_ts()
    if is_clore and action and not destroy and decision in {"keep", "switch_failed_keep_current"}:
        pool = str(final_pool or test.get("pool_strategy") or action.get("pool_strategy") or "akoya")
        profit = final_profit_usd_hr
        if profit is None:
            profit = safe_float(result.get("profit_usd_hr"), safe_float(test.get("latest_profit_usd_hr")))
        current = now_ts()
        action.update({
            "state": "rented",
            "pool_strategy": pool,
            "worker_name": clore.strategy_worker_name(pool, server_id),
            "reason": reason,
            "scout_final": True,
            "scout_approved": True,
            "scout_final_decision": decision,
            "scout_final_pool": pool,
            "scout_final_profit_usd_hr": round_money(profit),
            "scout_final_at": current,
            "scout_final_test_id": test.get("test_id"),
            "updated_at": current,
        })
        action.pop("scout_test_id", None)
        if clore_actions is not None:
            clore_actions[server_id] = action
            await save_clore_actions(clore_actions)
    elif action and not destroy and decision in {"keep", "switch_failed_keep_current"}:
        pool = str(final_pool or test.get("pool_strategy") or action.get("pool_strategy") or "akoya")
        profit = final_profit_usd_hr
        if profit is None:
            profit = safe_float(result.get("profit_usd_hr"), safe_float(test.get("latest_profit_usd_hr")))
        seal_scout_action(actions, test, pool, profit, f"Scout aprovado em {strategy_label(pool)}: ${safe_float(profit):.2f}/h", decision)
        await save_vast_actions(actions)
    if is_clore and action and destroy:
        final_state = "blacklisted" if blacklist else ("cancelled" if order_id > 0 else "archived")
        action.update({
            "state": final_state,
            "reason": f"Scout encerrou Clore: {reason}",
            "cancel_result": destroy_result,
            "cancelled_at": now_ts() if order_id > 0 else action.get("cancelled_at"),
            "updated_at": now_ts(),
        })
        if blacklist:
            action["blacklisted_at"] = now_ts()
            action["blacklist_reason"] = reason
        if clore_actions is not None:
            clore_actions[server_id] = action
            await save_clore_actions(clore_actions)
    elif action and destroy:
        action.update({
            "state": "archived",
            "reason": f"Scout encerrou: {reason}",
            "updated_at": now_ts(),
            "destroy_result": destroy_result,
        })
        actions[ask_id] = action
        await save_vast_actions(actions)
    return result


def clore_opportunity_fallback_from_test(test: dict[str, Any]) -> dict[str, Any]:
    price_hr = safe_float(test.get("price_usd_hr"))
    max_price = safe_float(test.get("max_price_usd_hr"))
    server_id = safe_int(test.get("server_id") or test.get("offer_id"))
    return {
        "id": server_id,
        "server_id": server_id,
        "platform": "clore",
        "gpu": test.get("gpu"),
        "gpu_count": test.get("gpu_count"),
        "pcie": test.get("pcie"),
        "cuda": test.get("cuda"),
        "reliability": test.get("reliability"),
        "net_up_mbps": test.get("net_up_mbps"),
        "net_down_mbps": test.get("net_down_mbps"),
        "price_usd_hr": round_money(price_hr),
        "cost_usd_day": round_money(price_hr * 24) if price_hr > 0 else None,
        "max_safe_price_usd_hr": max_price if max_price > 0 else test.get("max_safe_price_usd_hr"),
        "hashrate_ths": test.get("expected_ths"),
        "expected_ths": test.get("expected_ths"),
        "decision": test.get("opportunity_decision"),
        "risks": test.get("risks") or [],
        "rent_options": {},
    }


async def cancel_clore_test_order(
    clore_actions: dict[str, Any] | None,
    test: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    if clore_actions is None:
        return {"status": "no_clore_actions"}
    server_id = str(test.get("server_id") or test.get("offer_id") or "")
    action = action_by_id(clore_actions, server_id)
    order_id = safe_int(test.get("order_id") or (action or {}).get("order_id"))
    result: dict[str, Any] = {"status": "missing_order_id"}
    if order_id > 0:
        result = await safe_cancel_clore_order(order_id, reason)
    current = now_ts()
    if action:
        action.update({
            "state": "cancelled",
            "reason": reason,
            "cancel_result": result,
            "cancelled_at": current if order_id > 0 else action.get("cancelled_at"),
            "updated_at": current,
        })
        action.pop("scout_test_id", None)
        clore_actions[server_id] = action
        await save_clore_actions(clore_actions)
    return result


async def maybe_start_next_clore_pool(
    scout: dict[str, Any],
    actions: dict[str, Any],
    clore_actions: dict[str, Any] | None,
    state: dict[str, Any],
    test: dict[str, Any],
    result: dict[str, Any],
    reason: str,
) -> bool:
    if not SCOUT_CLORE_AUTO_AB_ENABLED:
        return False
    settings = scout_settings(scout)
    next_pool = scout_next_untested_pool(test, settings)
    if not next_pool:
        return False
    server_id = safe_int(test.get("server_id") or test.get("offer_id"))
    if server_id <= 0:
        return False

    current_pool = str(test.get("pool_strategy") or "")
    switch_reason = f"{reason}; cancelando {strategy_label(current_pool)} e testando {strategy_label(next_pool)}"
    try:
        cancel_result = await cancel_clore_test_order(clore_actions, test, switch_reason)
        test.update({
            "status": "switch_pool",
            "decision": "switch_pool",
            "reason": switch_reason,
            "ended_at": now_ts(),
            "destroy_result": cancel_result,
            "next_action": f"Testar {strategy_label(next_pool)}",
        })
        fallback = clore_opportunity_fallback_from_test(test)
        next_test = await start_scout_clore_rent(
            scout,
            actions,
            clore_actions or {},
            state,
            server_id,
            next_pool,
            parent_test_id=str(test.get("test_id") or ""),
            opportunity_override=fallback,
            allow_test_fallback=True,
        )
        next_test["prior_results"] = list(test.get("prior_results") or [])
        next_test["reason"] = f"Medindo Clore {strategy_label(next_pool)} apos {strategy_label(current_pool)}"
        await save_scout_state(scout)
        return True
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        failed = dict(result)
        failed.update({
            "test_id": f"{test.get('test_id')}:next",
            "pool_strategy": next_pool,
            "decision": "next_pool_unavailable",
            "reason": f"Nao conseguiu iniciar {strategy_label(next_pool)} na Clore: {detail}",
            "ended_at": now_ts(),
        })
        append_scout_history(failed)
        if clore_actions is not None:
            server_key = str(server_id)
            action = action_by_id(clore_actions, server_key) or {
                "provider": "clore",
                "server_id": server_id,
                "worker_name": clore.strategy_worker_name(next_pool, server_id),
                "created_at": test.get("started_at") or now_ts(),
            }
            action.update({
                "state": "watching",
                "pool_strategy": next_pool,
                "reason": failed["reason"],
                "error": str(detail),
                "clore_watch_approved": True,
                "clore_rerent_enabled": True,
                "clore_rerent_next_at": now_ts() + CLORE_RERENT_INTERVAL_SECONDS,
                "updated_at": now_ts(),
            })
            clore_actions[server_key] = action
            await save_clore_actions(clore_actions)
        test.update({
            "status": "watching",
            "decision": "watching",
            "reason": failed["reason"],
            "ended_at": now_ts(),
        })
        return True


async def maybe_start_next_scout_pool(
    scout: dict[str, Any],
    actions: dict[str, Any],
    state: dict[str, Any],
    test: dict[str, Any],
    result: dict[str, Any],
) -> None:
    next_pool = test.get("next_pool_strategy")
    if not next_pool:
        return
    try:
        next_test = await start_scout_rent(
            scout,
            actions,
            state,
            safe_int(test.get("ask_id")),
            str(next_pool),
            parent_test_id=str(test.get("test_id") or ""),
        )
        next_test["prior_results"] = [result]
        await save_scout_state(scout)
    except Exception as exc:
        failed = dict(result)
        failed.update({
            "test_id": f"{test.get('test_id')}:next",
            "pool_strategy": next_pool,
            "decision": "next_pool_unavailable",
            "reason": f"Nao conseguiu iniciar segundo pool: {getattr(exc, 'detail', str(exc))}",
            "ended_at": now_ts(),
        })
        append_scout_history(failed)


async def finish_best_scout_pool(
    scout: dict[str, Any],
    actions: dict[str, Any],
    test: dict[str, Any],
    min_profit_usd_hr: float,
    min_hash_ratio: float,
) -> None:
    best = scout_best_pool_result(test, min_profit_usd_hr, min_hash_ratio)
    current_pool = str(test.get("pool_strategy") or "")
    if not best:
        await finish_scout_test(
            scout,
            actions,
            test,
            "destroy",
            f"Nenhum pool atingiu lucro >= ${min_profit_usd_hr:.2f}/h e hash >= {min_hash_ratio:.0%}",
            destroy=True,
            blacklist=False,
        )
        return

    best_pool = str(best.get("pool_strategy") or "")
    best_profit = safe_float(best.get("profit_usd_hr"))
    if best_pool == current_pool:
        await finish_scout_test(
            scout,
            actions,
            test,
            "keep",
            f"Manter {strategy_label(best_pool)}: melhor lucro real ${best_profit:.2f}/h",
            destroy=False,
            blacklist=False,
            final_pool=best_pool,
            final_profit_usd_hr=best_profit,
        )
        return

    try:
        await switch_vast_instance_pool(
            actions,
            test,
            best_pool,
            f"Voltando para {strategy_label(best_pool)}: melhor lucro ${best_profit:.2f}/h",
        )
        test["decision"] = "returning_best_pool"
        test["return_target_pool"] = best_pool
        test["next_action"] = f"Manter {strategy_label(best_pool)}"
    except Exception as exc:
        current_result = next((item for item in scout_pool_results(test) if item.get("pool_strategy") == current_pool), None)
        if current_result and scout_pool_result_is_viable(current_result, min_profit_usd_hr, min_hash_ratio):
            await finish_scout_test(
                scout,
                actions,
                test,
                "switch_failed_keep_current",
                f"Falha ao voltar para {strategy_label(best_pool)}; mantendo {strategy_label(current_pool)} lucrativo: {getattr(exc, 'detail', str(exc))}",
                destroy=False,
                blacklist=False,
                final_pool=current_pool,
                final_profit_usd_hr=safe_float(current_result.get("profit_usd_hr")),
            )
        else:
            await finish_scout_test(
                scout,
                actions,
                test,
                "destroy",
                f"Falha ao voltar para melhor pool e pool atual nao e lucrativo: {getattr(exc, 'detail', str(exc))}",
                destroy=True,
                blacklist=False,
            )


async def route_completed_scout_pool(
    scout: dict[str, Any],
    actions: dict[str, Any],
    state: dict[str, Any],
    test: dict[str, Any],
    result_decision: str,
    result_reason: str,
    min_profit_usd_hr: float,
    min_hash_ratio: float,
    clore_actions: dict[str, Any] | None = None,
) -> None:
    settings = scout_settings(scout)
    result = scout_append_pool_result(test, result_decision, result_reason)
    if str(test.get("provider") or "vastai").lower() == "clore":
        if scout_pool_result_is_viable(result, min_profit_usd_hr, min_hash_ratio):
            profit = safe_float(result.get("profit_usd_hr"))
            await finish_scout_test(
                scout,
                actions,
                test,
                "keep",
                f"Manter Clore {strategy_label(test.get('pool_strategy'))}: lucro real ${profit:.2f}/h",
                destroy=False,
                blacklist=False,
                final_pool=str(test.get("pool_strategy") or "akoya"),
                final_profit_usd_hr=profit,
                clore_actions=clore_actions,
            )
        else:
            if await maybe_start_next_clore_pool(
                scout,
                actions,
                clore_actions,
                state,
                test,
                result,
                result_reason,
            ):
                return
            await finish_scout_test(
                scout,
                actions,
                test,
                "blacklist",
                f"Cancelar Clore: {result_reason}",
                destroy=True,
                blacklist=True,
                clore_actions=clore_actions,
            )
        return
    if settings["pool_switch_mode"] == "recreate":
        await finish_scout_test(scout, actions, test, "switch_pool", "Teste completo; alternando pool por recriacao", destroy=True)
        await maybe_start_next_scout_pool(scout, actions, state, test, result)
        return
    if settings["pool_switch_mode"] != "in_place_ab":
        await decide_completed_scout_test(
            scout,
            actions,
            test,
            action_by_id(actions, test.get("ask_id")),
            safe_float(result.get("profit_usd_hr"), -999999),
            safe_float(result.get("hash_ratio")),
            min_profit_usd_hr,
            min_hash_ratio,
        )
        return

    next_pool = scout_next_untested_pool(test, settings)
    if next_pool:
        try:
            await switch_vast_instance_pool(
                actions,
                test,
                next_pool,
                f"Trocar para {strategy_label(next_pool)} sem perder GPU",
            )
            test["next_action"] = f"Testar {strategy_label(next_pool)}"
        except Exception as exc:
            test["switch_error"] = getattr(exc, "detail", str(exc))
            best = scout_best_pool_result(test, min_profit_usd_hr, min_hash_ratio)
            if best:
                await finish_scout_test(
                    scout,
                    actions,
                    test,
                    "switch_failed_keep_current",
                    f"Falha ao trocar pool; mantendo {strategy_label(test.get('pool_strategy'))}: {test['switch_error']}",
                    destroy=False,
                    blacklist=False,
                    final_pool=str(test.get("pool_strategy") or "akoya"),
                    final_profit_usd_hr=safe_float(best.get("profit_usd_hr")),
                )
            else:
                await finish_scout_test(
                    scout,
                    actions,
                    test,
                    "destroy",
                    f"Falha ao trocar pool e pool atual nao foi lucrativo: {test['switch_error']}",
                    destroy=True,
                    blacklist=False,
                )
        return

    await finish_best_scout_pool(scout, actions, test, min_profit_usd_hr, min_hash_ratio)


async def route_zero_hash_scout_pool(
    scout: dict[str, Any],
    actions: dict[str, Any],
    state: dict[str, Any],
    test: dict[str, Any],
    zero_hash_timeout_seconds: int,
    min_profit_usd_hr: float,
    min_hash_ratio: float,
    clore_actions: dict[str, Any] | None = None,
) -> None:
    current_pool = str(test.get("pool_strategy") or "")
    failures = safe_int(test.get("zero_hash_pool_failures")) + 1
    test["zero_hash_pool_failures"] = failures
    test["failure_tag"] = "zero_hash_5m"
    result = scout_append_pool_result(
        test,
        "zero_hash_5m",
        f"Worker online mas 0 TH/s por {zero_hash_timeout_seconds // 60} min em {strategy_label(current_pool)}",
    )
    settings = scout_settings(scout)
    next_pool = scout_next_untested_pool(test, settings)
    if str(test.get("provider") or "vastai").lower() == "clore":
        if await maybe_start_next_clore_pool(
            scout,
            actions,
            clore_actions,
            state,
            test,
            result,
            result.get("reason") or f"Worker online mas 0 TH/s em {strategy_label(current_pool)}",
        ):
            return
        await finish_scout_test(
            scout,
            actions,
            test,
            "blacklist",
            f"Cancelar Clore: worker online mas 0 TH/s por {zero_hash_timeout_seconds // 60} min em {strategy_label(current_pool)}",
            destroy=True,
            blacklist=True,
            clore_actions=clore_actions,
        )
        return

    async def cleanup_zero_hash_target() -> None:
        remove_scout_queue_entries_for_target(scout, test, "zero_hash_all_pools_5m")
        results_state = await load_results_state()
        if archive_results_queue_entries_for_target(results_state, test, "zero_hash_all_pools_5m"):
            await save_results_state(results_state)

    if next_pool:
        try:
            await switch_vast_instance_pool(
                actions,
                test,
                next_pool,
                f"Worker zerado em {strategy_label(current_pool)}; tentando {strategy_label(next_pool)}",
            )
            test["zero_hash_pool_failures"] = failures
            test["failure_tag"] = "zero_hash_5m"
            test["next_action"] = f"Testar {strategy_label(next_pool)}"
        except Exception as exc:
            test["switch_error"] = getattr(exc, "detail", str(exc))
            await finish_scout_test(
                scout,
                actions,
                test,
                "blacklist",
                f"zero_hash_all_pools_5m: falha ao trocar pool apos hash zero: {test['switch_error']}",
                destroy=True,
                blacklist=True,
            )
            await cleanup_zero_hash_target()
        return

    await finish_scout_test(
        scout,
        actions,
        test,
        "blacklist",
        f"zero_hash_all_pools_5m: worker online mas 0 TH/s por {zero_hash_timeout_seconds // 60} min em todos os pools",
        destroy=True,
        blacklist=True,
    )
    await cleanup_zero_hash_target()


async def decide_completed_scout_test(
    scout: dict[str, Any],
    actions: dict[str, Any],
    test: dict[str, Any],
    action: dict[str, Any] | None,
    profit_hr: float,
    hash_ratio: float,
    min_profit_usd_hr: float,
    min_hash_ratio: float,
) -> None:
    if hash_ratio < min_hash_ratio:
        await finish_scout_test(
            scout,
            actions,
            test,
            "destroy",
            f"Hash real {hash_ratio:.0%} do esperado, abaixo de {min_hash_ratio:.0%}",
            destroy=True,
            blacklist=False,
        )
        return

    if profit_hr >= min_profit_usd_hr:
        await finish_scout_test(
            scout,
            actions,
            test,
            "keep",
            f"Lucro real ${profit_hr:.2f}/h >= ${min_profit_usd_hr:.2f}/h",
            destroy=False,
            blacklist=False,
            final_pool=str(test.get("pool_strategy") or (action or {}).get("pool_strategy") or "akoya"),
            final_profit_usd_hr=profit_hr,
        )
        return

    await finish_scout_test(
        scout,
        actions,
        test,
        "destroy",
        f"Lucro real ${profit_hr:.2f}/h abaixo de ${min_profit_usd_hr:.2f}/h",
        destroy=True,
        blacklist=False,
    )


async def evaluate_scout_state(
    scout: dict[str, Any],
    actions: dict[str, Any],
    state: dict[str, Any],
    clore_actions: dict[str, Any] | None = None,
) -> bool:
    changed = False
    operation = state.get("operation") or {}
    current = now_ts()
    settings = scout_settings(scout)
    for test_id, test in list((scout.get("tests") or {}).items()):
        if not isinstance(test, dict) or test.get("status") != "testing":
            continue
        test_seconds = max(60, safe_int(test.get("test_seconds"), settings["test_seconds"]))
        worker_timeout_seconds = max(60, safe_int(test.get("worker_timeout_seconds"), settings["worker_timeout_seconds"]))
        offline_timeout_seconds = max(60, safe_int(test.get("offline_timeout_seconds"), settings["offline_timeout_seconds"]))
        zero_hash_timeout_seconds = max(60, safe_int(test.get("zero_hash_timeout_seconds"), settings["zero_hash_timeout_seconds"]))
        min_profit_usd_hr = safe_float(test.get("min_profit_usd_hr"), settings["min_profit_usd_hr"])
        min_hash_ratio = safe_float(test.get("min_hash_ratio"), settings["min_hash_ratio"])
        max_price_usd_hr = safe_float(test.get("max_price_usd_hr"), settings["max_price_usd_hr"])

        provider = str(test.get("provider") or "vastai").lower()
        is_clore = provider == "clore"
        if is_clore:
            opportunity = find_clore_opportunity_by_id(state, test.get("server_id") or test.get("offer_id"))
            if opportunity:
                for key in (
                    "host_id",
                    "machine_id",
                    "gpu",
                    "gpu_count",
                    "pcie",
                    "cuda",
                    "reliability",
                    "net_up_mbps",
                    "net_down_mbps",
                    "risks",
                ):
                    if not test.get(key) and opportunity.get(key) is not None:
                        test[key] = opportunity.get(key)
                if not test.get("opportunity_decision"):
                    test["opportunity_decision"] = opportunity.get("decision")
        action = action_by_id(clore_actions or {}, test.get("server_id") or test.get("offer_id")) if is_clore else action_by_id(actions, test.get("ask_id"))
        if action:
            test["instance_id"] = test.get("instance_id") or action.get("instance_id")
            test["order_id"] = test.get("order_id") or action.get("order_id")
            test["currency"] = test.get("currency") or action.get("currency")
            test["image"] = test.get("image") or action.get("image")
            test["opportunity_decision"] = test.get("opportunity_decision") or action.get("opportunity_decision")
            test["risks"] = test.get("risks") or action.get("risks")
            test["host_id"] = action.get("host_id") or test.get("host_id")
            test["machine_id"] = action.get("machine_id") or test.get("machine_id")
            test["price_usd_hr"] = action.get("price_usd_hr") or test.get("price_usd_hr")
            if not is_clore:
                test["vast_cur_state"] = action.get("vast_cur_state", "")
                test["vast_actual_status"] = action.get("vast_actual_status", "")
                test["vast_status_msg"] = action.get("vast_status_msg", "")
            test["vast_pool_strategy_actual"] = action.get("vast_pool_strategy_actual", "")
        if is_clore and not test.get("risks"):
            test["risks"] = scout_metadata_risks(test)
        worker = find_operation_worker(operation, str(test.get("worker_name") or ""), str(test.get("pool_strategy") or ""))

        if is_clore and action and action.get("state") in {"failed", "archived"}:
            await route_completed_scout_pool(
                scout,
                actions,
                state,
                test,
                "order_lost",
                action.get("reason") or action.get("error") or "Ordem Clore nao esta mais ativa",
                min_profit_usd_hr,
                min_hash_ratio,
                clore_actions=clore_actions,
            )
            changed = True
            continue
        if is_clore and action and action.get("state") in {"cancelled", "blacklisted"}:
            decision = "blacklist" if action.get("state") == "blacklisted" else "destroy"
            await finish_scout_test(
                scout,
                actions,
                test,
                decision,
                action.get("reason") or "Ordem Clore cancelada",
                destroy=False,
                blacklist=False,
                clore_actions=clore_actions,
            )
            changed = True
            continue

        if scout_price_gate_applies(test) and safe_float(test.get("price_usd_hr")) > max_price_usd_hr:
            await finish_scout_test(
                scout,
                actions,
                test,
                "destroy",
                f"Preco ${safe_float(test.get('price_usd_hr')):.2f}/h acima do teto Scout ${max_price_usd_hr:.2f}/h",
                destroy=True,
                blacklist=False,
                clore_actions=clore_actions,
            )
            changed = True
            continue

        if not is_clore and scout_runtime_error(action):
            next_pool = scout_next_untested_pool(test, settings)
            if settings.get("pool_switch_mode") == "in_place_ab" and next_pool:
                await route_completed_scout_pool(
                    scout,
                    actions,
                    state,
                    test,
                    "runtime_error",
                    f"Erro runtime/CDI/GPU em {strategy_label(test.get('pool_strategy'))}; tentando {strategy_label(next_pool)} na mesma GPU",
                    min_profit_usd_hr,
                    min_hash_ratio,
                )
            else:
                await finish_scout_test(
                    scout,
                    actions,
                    test,
                    "blacklist",
                    "Erro runtime/CDI/GPU em todos os pools testados",
                    destroy=True,
                    blacklist=True,
                )
            changed = True
            continue

        sample = scout_sample_from_worker(test, worker, state)
        if worker and worker.get("is_connected"):
            test["worker_seen_at"] = test.get("worker_seen_at") or current
            test["last_worker_seen_at"] = current
            if test.get("decision") == "waiting_worker":
                test["decision"] = "testing_pool"
                test["reason"] = f"Medindo {strategy_label(test.get('pool_strategy'))}"
            if safe_float(sample.get("hashrate_ths")) <= 0:
                test["zero_hash_started_at"] = test.get("zero_hash_started_at") or current
                test["zero_hash_elapsed_s"] = round(current - safe_float(test.get("zero_hash_started_at"), current), 1)
                test["failure_tag"] = "zero_hash_5m"
            else:
                test["zero_hash_started_at"] = None
                test["zero_hash_elapsed_s"] = 0
                if test.get("failure_tag") == "zero_hash_5m":
                    test["failure_tag"] = ""

        stage_started = safe_float(test.get("stage_started_at"), current)
        worker_seen = safe_float(test.get("worker_seen_at"))
        last_seen = safe_float(test.get("last_worker_seen_at"))
        elapsed = current - stage_started
        samples = test.setdefault("samples", [])
        last_sample_at = safe_float(test.get("last_sample_saved_at"))
        if (
            not samples
            or current - last_sample_at >= SCOUT_SAMPLE_INTERVAL_SECONDS
            or elapsed >= test_seconds
        ):
            samples.append(sample)
            test["samples"] = samples[-180:]
            test["last_sample_saved_at"] = sample.get("ts") or current
            changed = True

        actual_pool = str(test.get("vast_pool_strategy_actual") or "")
        target_pool = str(test.get("pool_strategy") or "")
        if (
            not is_clore
            and
            test.get("decision") == "waiting_worker"
            and actual_pool
            and target_pool
            and actual_pool != target_pool
            and elapsed >= 120
            and safe_int(test.get("switch_attempts")) < 2
        ):
            try:
                await switch_vast_instance_pool(
                    actions,
                    test,
                    target_pool,
                    f"Reenviando troca para {strategy_label(target_pool)}; Vast ainda mostra {strategy_label(actual_pool)}",
                )
                test["next_action"] = f"Aguardar worker {strategy_label(target_pool)}"
            except Exception as exc:
                test["switch_error"] = getattr(exc, "detail", str(exc))
            changed = True
            continue

        if not is_clore and test.get("decision") == "returning_best_pool" and worker and worker.get("is_connected"):
            best_pool = str(test.get("return_target_pool") or test.get("pool_strategy") or "")
            best = next((item for item in scout_pool_results(test) if item.get("pool_strategy") == best_pool), None)
            best_profit = safe_float((best or {}).get("profit_usd_hr"))
            await finish_scout_test(
                scout,
                actions,
                test,
                "keep",
                f"Manter {strategy_label(best_pool)}: melhor lucro real ${best_profit:.2f}/h",
                destroy=False,
                blacklist=False,
                final_pool=best_pool,
                final_profit_usd_hr=best_profit,
            )
            changed = True
            continue

        if not worker_seen and elapsed >= worker_timeout_seconds:
            if test.get("decision") == "returning_best_pool":
                await finish_scout_test(
                    scout,
                    actions,
                    test,
                    "destroy",
                    f"Worker nao voltou em {strategy_label(test.get('pool_strategy'))} apos troca para melhor pool",
                    destroy=True,
                    blacklist=False,
                    clore_actions=clore_actions,
                )
                changed = True
                continue
            await route_completed_scout_pool(
                scout,
                actions,
                state,
                test,
                "no_worker",
                f"Worker nao apareceu em {worker_timeout_seconds // 60} min",
                min_profit_usd_hr,
                min_hash_ratio,
                clore_actions=clore_actions,
            )
            changed = True
            continue

        if worker_seen and last_seen and current - last_seen >= offline_timeout_seconds:
            await route_completed_scout_pool(
                scout,
                actions,
                state,
                test,
                "offline",
                f"Worker ficou offline por {offline_timeout_seconds // 60} min",
                min_profit_usd_hr,
                min_hash_ratio,
                clore_actions=clore_actions,
            )
            changed = True
            continue

        if (
            worker
            and worker.get("is_connected")
            and safe_float(sample.get("hashrate_ths")) <= 0
            and safe_float(test.get("zero_hash_started_at")) > 0
            and current - safe_float(test.get("zero_hash_started_at")) >= zero_hash_timeout_seconds
        ):
            await route_zero_hash_scout_pool(
                scout,
                actions,
                state,
                test,
                zero_hash_timeout_seconds,
                min_profit_usd_hr,
                min_hash_ratio,
                clore_actions=clore_actions,
            )
            changed = True
            continue

        test["elapsed_s"] = round(elapsed, 1)
        test["remaining_s"] = max(0, round(test_seconds - elapsed, 1))
        test["latest_hashrate_ths"] = sample["hashrate_ths"]
        test["latest_profit_usd_hr"] = sample["profit_usd_hr"]
        expected = safe_float(test.get("expected_ths"))
        test["latest_hash_ratio"] = round(safe_float(sample.get("hashrate_ths")) / expected, 4) if expected > 0 else None
        test["next_action"] = scout_next_action_label(test, settings)

        if elapsed < test_seconds:
            changed = True
            continue

        if (
            is_clore
            and worker_seen
            and (
                not bool((state.get("network") or {}).get("ok"))
                or sample.get("profit_usd_hr") is None
            )
        ):
            test["decision"] = "waiting_price"
            test["reason"] = "Aguardando preco/rede Pearl para decidir Clore sem falso negativo"
            test["remaining_s"] = 60
            test["next_action"] = "Aguardar preco Pearl"
            changed = True
            continue

        await route_completed_scout_pool(
            scout,
            actions,
            state,
            test,
            "pool_measured",
            f"Teste de {test_seconds // 60} min completo em {strategy_label(test.get('pool_strategy'))}",
            min_profit_usd_hr,
            min_hash_ratio,
            clore_actions=clore_actions,
        )
        changed = True
    return changed


async def maybe_autostart_scout(scout: dict[str, Any], actions: dict[str, Any], state: dict[str, Any]) -> bool:
    if not scout.get("enabled"):
        return False
    settings = scout_settings(scout)
    queue_changed = update_scout_queue_from_opportunities(scout, actions, state)
    active_tests = [
        test for test in (scout.get("tests") or {}).values()
        if isinstance(test, dict) and test.get("status") == "testing"
    ]
    active_seen_asks = {
        str(test.get("ask_id"))
        for test in (scout.get("tests") or {}).values()
        if isinstance(test, dict) and test.get("ask_id")
    }
    active_hardware = {
        (
            str(test.get("machine_id") or ""),
            str(test.get("host_id") or ""),
            str(test.get("gpu") or ""),
        )
        for test in active_tests
        if test.get("machine_id") or test.get("host_id")
    }
    started_any = False
    opportunity_by_id = {
        str(item.get("id")): item
        for item in state.get("opportunities", [])
        if item.get("platform") == "vastai" and item.get("id")
    }
    queue_items = sorted(
        [
            item for item in (scout.get("queue") or {}).values()
            if isinstance(item, dict)
            and (item.get("is_new_machine") or item.get("source") == "trigger")
            and (
                item.get("queue_status") == "queued"
                or scout_transient_retry_due(item)
            )
        ],
        key=lambda item: (
            -safe_float(item.get("priority_score"), -999999),
            safe_float(item.get("first_seen_at")),
        ),
    )
    stop_autostart = False
    for queue_item in queue_items:
        ask_id = safe_int(queue_item.get("ask_id"))
        opportunity = opportunity_by_id.get(str(ask_id))
        if not opportunity:
            queue_item["queue_status"] = "cooldown" if queue_item.get("transient_unavailable") else "lost"
            queue_item["sniper_status"] = "aguardando Vast" if queue_item.get("transient_unavailable") else "lost"
            queue_item["skip_reason"] = "ask sumiu da Vast; aguardando nova aparicao" if queue_item.get("transient_unavailable") else "ask sumiu da Vast antes do aluguel"
            if queue_item.get("transient_unavailable"):
                queue_item["marketplace_absent_at"] = queue_item.get("marketplace_absent_at") or now_ts()
            started_any = True
            continue
        hardware_key = (
            str(opportunity.get("machine_id") or ""),
            str(opportunity.get("host_id") or ""),
            str(opportunity.get("gpu") or ""),
        )
        if (hardware_key[0] or hardware_key[1]) and hardware_key in active_hardware:
            queue_item["queue_status"] = "rented"
            queue_item["sniper_status"] = "ja ativo"
            queue_item["skip_reason"] = "hardware ja tem teste ativo"
            queue_item["last_seen_at"] = now_ts()
            continue
        if not ask_id or str(ask_id) in active_seen_asks:
            queue_item["queue_status"] = "rented"
            queue_item["sniper_status"] = "ja ativo"
            queue_item["skip_reason"] = "ask ja tem teste ativo"
            queue_item["last_seen_at"] = now_ts()
            continue
        current = now_ts()
        queue_item["queue_status"] = "renting"
        queue_item["sniper_status"] = "retry Vast" if queue_item.get("transient_unavailable") else ("trigger Vast alugando" if queue_item.get("source") == "trigger" else "alugando agora")
        queue_item["skip_reason"] = "retry Vast: tentando alugar novamente" if queue_item.get("transient_unavailable") else ("trigger Vast: tentando alugar agora" if queue_item.get("source") == "trigger" else "sniper novo: tentando alugar agora")
        queue_item["last_seen_at"] = current
        await save_scout_state(scout)
        started_this_item = False
        for strategy in settings["pool_order"]:
            if vast_strategy_configured(strategy):
                try:
                    test = await start_scout_rent(scout, actions, state, ask_id, strategy)
                except Exception as exc:
                    active_seen_asks.add(str(ask_id))
                    if scout_vast_rate_limit_error(exc):
                        stop_autostart = True
                    break
                active_tests.append(test)
                active_hardware.add(hardware_key)
                active_seen_asks.add(str(ask_id))
                started_any = True
                started_this_item = True
                break
        if not started_this_item and queue_item.get("queue_status") == "renting":
            queue_item["queue_status"] = "cooldown"
            queue_item["sniper_status"] = "falhou"
            queue_item["skip_reason"] = "nenhum pool configurado para sniper"
            queue_item["last_seen_at"] = now_ts()
        if stop_autostart:
            break
    return started_any or queue_changed


async def redis_listener() -> None:
    assert redis_client is not None
    backoff = 1.0
    while True:
        pubsub = None
        try:
            pubsub = redis_client.pubsub()
            await pubsub.psubscribe("monitor:*")
            print("[redis-listener] subscribed monitor:*", flush=True)
            backoff = 1.0
            async for message in pubsub.listen():
                if message.get("type") not in {"pmessage", "message"}:
                    continue
                channel = message.get("channel")
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8", errors="ignore")
                run_scout_autostart = str(channel or "").endswith("monitor:vastai")
                async with vast_actions_lock:
                    state = await refresh_state_unlocked(run_scout_autostart=run_scout_autostart)
                await broadcast(state)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[redis-listener] {exc}; reconnect in {backoff:.0f}s", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        finally:
            if pubsub is not None:
                try:
                    if hasattr(pubsub, "aclose"):
                        await pubsub.aclose()
                    else:
                        result = pubsub.close()
                        if asyncio.iscoroutine(result):
                            await result
                except Exception:
                    pass


async def scout_worker_tick() -> None:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=True)
    await broadcast(state)


async def scout_worker() -> None:
    while True:
        await asyncio.sleep(SCOUT_WORKER_INTERVAL_SECONDS)
        try:
            await scout_worker_tick()
        except Exception as exc:
            print(f"[scout-worker] {exc}", flush=True)


def build_results_state_payload(
    state: dict[str, Any],
    actions: dict[str, Any],
    scout: dict[str, Any],
    results_state: dict[str, Any],
    raw_vast_offers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = scout_settings(scout)
    records = results_history_records()
    blacklist = load_vast_blacklist()
    profitable = [record for record in records if safe_float(record.get("profit_usd_hr"), -999999) > 0]

    gpu_groups: dict[str, dict[str, Any]] = {}
    hardware_groups: dict[str, dict[str, Any]] = {}
    pattern_groups: dict[str, dict[str, Any]] = {}
    for record in profitable:
        gpu = normalize_gpu_name(record.get("gpu")) or str(record.get("gpu") or "")
        if not gpu:
            continue
        max_price = results_learned_max_price(record, settings)
        gpu_group = gpu_groups.setdefault(gpu, {
            "id": results_queue_id("gpu", {"gpu": gpu}),
            "gpu": gpu,
            "count": 0,
            "hardware_count": 0,
            "hardware_keys": set(),
            "best_profit_usd_hr": None,
            "best_price_usd_hr": None,
            "best_pool": "",
            "max_price_usd_hr": safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
            "records": [],
        })
        gpu_group["count"] += 1
        gpu_group["hardware_keys"].add(results_hardware_key(record))
        gpu_group["records"].append(record)
        gpu_group["max_price_usd_hr"] = max(safe_float(gpu_group.get("max_price_usd_hr")), max_price)
        if gpu_group["best_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr")) > safe_float(gpu_group.get("best_profit_usd_hr"), -999999):
            gpu_group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            gpu_group["best_price_usd_hr"] = record.get("price_usd_hr")
            gpu_group["best_pool"] = record.get("pool_strategy")

        hw_key = results_hardware_key(record)
        hw_group = hardware_groups.setdefault(hw_key, {
            "id": results_queue_id("hardware", record),
            "gpu": gpu,
            "gpu_count": safe_int(record.get("gpu_count"), 1),
            "machine_id": record.get("machine_id"),
            "host_id": record.get("host_id"),
            "count": 0,
            "best_profit_usd_hr": None,
            "best_price_usd_hr": None,
            "best_pool": "",
            "max_price_usd_hr": safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
            "last_seen_at": None,
            "records": [],
        })
        hw_group["count"] += 1
        hw_group["records"].append(record)
        hw_group["max_price_usd_hr"] = max(safe_float(hw_group.get("max_price_usd_hr")), max_price)
        hw_group["last_seen_at"] = max(safe_float(hw_group.get("last_seen_at")), safe_float(record.get("ended_at")))
        if hw_group["best_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr")) > safe_float(hw_group.get("best_profit_usd_hr"), -999999):
            hw_group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            hw_group["best_price_usd_hr"] = record.get("price_usd_hr")
            hw_group["best_pool"] = record.get("pool_strategy")

        pattern_key = results_pattern_key(record)
        pattern_group = pattern_groups.setdefault(pattern_key, {
            "id": results_queue_id("pattern", record),
            "gpu": gpu,
            "gpu_count": safe_int(record.get("gpu_count"), 1),
            "pcie": record.get("pcie"),
            "host_id": record.get("host_id"),
            "count": 0,
            "machine_ids": set(),
            "best_profit_usd_hr": None,
            "avg_profit_usd_hr": 0.0,
            "profit_total": 0.0,
            "best_price_usd_hr": None,
            "min_price_usd_hr": None,
            "max_seen_price_usd_hr": None,
            "best_pool": "",
            "max_price_usd_hr": safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
            "net_up_mbps": None,
            "net_down_mbps": None,
            "reliability": None,
            "records": [],
        })
        pattern_group["count"] += 1
        if record.get("machine_id"):
            pattern_group["machine_ids"].add(str(record.get("machine_id")))
        pattern_group["records"].append(record)
        pattern_group["profit_total"] = safe_float(pattern_group.get("profit_total")) + safe_float(record.get("profit_usd_hr"))
        pattern_group["avg_profit_usd_hr"] = round_money(safe_float(pattern_group.get("profit_total")) / max(1, safe_int(pattern_group.get("count"), 1)))
        pattern_group["max_price_usd_hr"] = max(safe_float(pattern_group.get("max_price_usd_hr")), max_price)
        price = safe_float(record.get("price_usd_hr"))
        if price > 0:
            current_min = safe_float(pattern_group.get("min_price_usd_hr"))
            current_max = safe_float(pattern_group.get("max_seen_price_usd_hr"))
            pattern_group["min_price_usd_hr"] = price if current_min <= 0 else min(current_min, price)
            pattern_group["max_seen_price_usd_hr"] = max(current_max, price)
        pattern_group["net_up_mbps"] = max(safe_float(pattern_group.get("net_up_mbps")), safe_float(record.get("net_up_mbps"))) or pattern_group.get("net_up_mbps")
        pattern_group["net_down_mbps"] = max(safe_float(pattern_group.get("net_down_mbps")), safe_float(record.get("net_down_mbps"))) or pattern_group.get("net_down_mbps")
        pattern_group["reliability"] = max(safe_float(pattern_group.get("reliability")), safe_float(record.get("reliability"))) or pattern_group.get("reliability")
        if pattern_group["best_profit_usd_hr"] is None or safe_float(record.get("profit_usd_hr")) > safe_float(pattern_group.get("best_profit_usd_hr"), -999999):
            pattern_group["best_profit_usd_hr"] = record.get("profit_usd_hr")
            pattern_group["best_price_usd_hr"] = record.get("price_usd_hr")
            pattern_group["best_pool"] = record.get("pool_strategy")

    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    for item in queue.values():
        if isinstance(item, dict):
            allowlist_reason = scout_gpu_allowlist_block_reason(item, settings)
            if allowlist_reason:
                item.update({"status": "blocked", "last_error": allowlist_reason, "next_retry_at": 0})
    public_queue = [results_queue_public(item) for item in queue.values() if isinstance(item, dict) and item.get("status") != "archived"]
    public_queue.sort(key=lambda item: safe_float(item.get("updated_at") or item.get("created_at")), reverse=True)

    def decorate_group(group: dict[str, Any], kind: str) -> dict[str, Any]:
        target = dict(group)
        target["preferred_pool"] = results_preferred_pool(group.get("records") or [])
        offer = results_find_offer(state, actions, scout, target, kind, safe_float(group.get("max_price_usd_hr")), settings)
        active = results_active_match(actions, scout, target)
        queued = queue.get(group.get("id")) if isinstance(queue.get(group.get("id")), dict) else None
        public = {key: value for key, value in group.items() if key not in {"records", "hardware_keys", "machine_ids", "profit_total"}}
        public["hardware_count"] = len(group.get("hardware_keys") or []) if "hardware_keys" in group else group.get("hardware_count", 1)
        if "machine_ids" in group:
            public["machines_count"] = len(group.get("machine_ids") or [])
        public["preferred_pool"] = target["preferred_pool"]
        public["current_offer"] = {
            "ask_id": offer.get("id"),
            "gpu_count": offer.get("gpu_count"),
            "machine_id": offer.get("machine_id"),
            "host_id": offer.get("host_id"),
            "pcie": offer.get("pcie"),
            "price_usd_hr": offer.get("price_usd_hr"),
            "profit_usd_hr": offer.get("profit_usd_hr"),
            "roi_pct": offer.get("roi_pct"),
        } if offer else None
        public["active"] = {
            "ask_id": active.get("ask_id"),
            "instance_id": active.get("instance_id"),
            "state": active.get("state") or active.get("status"),
        } if active else None
        public["queue"] = results_queue_public(queued) if queued else None
        if active:
            public["action_status"] = "active"
        elif queued and queued.get("status") in {"waiting", "renting", "blocked"}:
            public["action_status"] = queued.get("status")
        elif offer:
            public["action_status"] = "ready"
        else:
            public["action_status"] = "no_offer"
        return public

    gpu_rows = [decorate_group(group, "gpu") for group in gpu_groups.values()]
    gpu_rows.sort(key=lambda item: safe_float(item.get("best_profit_usd_hr"), -999999), reverse=True)
    hardware_rows = [decorate_group(group, "hardware") for group in hardware_groups.values()]
    hardware_rows.sort(key=lambda item: safe_float(item.get("best_profit_usd_hr"), -999999), reverse=True)
    pattern_rows = [decorate_group(group, "pattern") for group in pattern_groups.values()]
    pattern_rows.sort(key=lambda item: (safe_float(item.get("avg_profit_usd_hr"), -999999), safe_float(item.get("best_profit_usd_hr"), -999999)), reverse=True)
    host_watch = results_host_watch_payload(state, actions, scout, records, settings, results_state)
    host_intelligence = results_profitable_hosts_payload(state, actions, scout, records, settings, results_state, raw_vast_offers)

    best_record = max(profitable, key=lambda item: safe_float(item.get("profit_usd_hr"), -999999), default={})
    next_retry = min(
        [safe_float(item.get("next_retry_at")) for item in queue.values() if isinstance(item, dict) and safe_float(item.get("next_retry_at")) > now_ts()],
        default=0,
    )
    return {
        "updated_at": now_ts(),
        "summary": {
            "profitable_results": len(profitable),
            "profitable_gpus": len(gpu_rows),
            "profitable_hardware": len(hardware_rows),
            "profitable_patterns": len(pattern_rows),
            "best_profit_usd_hr": best_record.get("profit_usd_hr"),
            "best_gpu": best_record.get("gpu"),
            "queue_waiting": len([item for item in queue.values() if isinstance(item, dict) and item.get("status") == "waiting"]),
            "next_retry_at": next_retry or None,
        },
        "gpus": gpu_rows,
        "hardware": hardware_rows,
        "patterns": pattern_rows,
        "host_watch": host_watch,
        "host_intelligence": host_intelligence,
        "worst_gpus": build_worst_gpu_rows(records, settings, blacklist),
        "recent_results": [public_scout_history(item) for item in records[:120]],
        "queue": public_queue[:100],
    }


async def results_worker_tick() -> None:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        results_state = await load_results_state()
        queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
        current = now_ts()
        due = [
            item for item in queue.values()
            if isinstance(item, dict)
            and item.get("status") in {"waiting", "renting"}
            and safe_float(item.get("next_retry_at")) <= current
        ][:5]
        changed = False
        for item in due:
            before = dict(item)
            await results_attempt_queue_item(results_state, item, state, actions, scout)
            changed = changed or before != item
        if changed:
            await save_results_state(results_state)
            await refresh_state_unlocked(run_scout_autostart=False)


async def results_worker() -> None:
    while True:
        await asyncio.sleep(RESULTS_RETRY_SECONDS)
        try:
            await results_worker_tick()
        except Exception as exc:
            print(f"[results-worker] {exc}", flush=True)


@app.on_event("startup")
async def startup() -> None:
    global redis_client
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_client = aioredis.from_url(f"redis://{redis_host}:{redis_port}", decode_responses=True)
    await redis_client.ping()
    await refresh_state()
    asyncio.create_task(redis_listener())
    asyncio.create_task(scout_worker())
    asyncio.create_task(results_worker())


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(Path("static/index.html"))


@app.get("/config")
async def config_page() -> FileResponse:
    return FileResponse(Path("static/config.html"))


@app.get("/scout")
async def scout_page() -> FileResponse:
    return FileResponse(Path("static/scout.html"))


@app.get("/results")
async def results_page() -> FileResponse:
    return FileResponse(Path("static/results.html"))


@app.get("/prime")
async def prime_page() -> FileResponse:
    return FileResponse(Path("static/prime.html"))


@app.get("/tests")
async def tests_page() -> FileResponse:
    return FileResponse(Path("static/scout.html"))


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    if latest_state:
        age = now_ts() - safe_float(latest_state.get("generated_at"))
        if vast_actions_lock.locked() or age <= STATE_CACHE_MAX_AGE_SECONDS:
            return latest_state
    return await refresh_state()


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    scout = await load_scout_state()
    triggers = scout_vast_gpu_triggers(scout)
    scout["vast_gpu_triggers"] = triggers
    queue = scout.get("queue") if isinstance(scout.get("queue"), dict) else {}
    radar = scout.get("radar") if isinstance(scout.get("radar"), dict) else {}
    trigger_items = {**radar, **queue}
    return {
        "vast": {
            "akoya_template_hash_id": vast_template_hash_id_for("akoya"),
            "alphamine_template_hash_id": vast_template_hash_id_for("alphamine"),
            "akoya_image": vast_image_for_strategy("akoya"),
            "alphamine_image": vast_image_for_strategy("alphamine"),
            "akoya_ready": bool((vast_template_hash_id_for("akoya") or vast_image_for_strategy("akoya")) and akoya_wallet()),
            "alphamine_ready": bool((vast_template_hash_id_for("alphamine") or vast_image_for_strategy("alphamine")) and alphamine_wallet()),
            "max_active_rents": VAST_MAX_ACTIVE_RENTS,
            "autorent_mode": VAST_AUTORENT_MODE,
            "disk_gb": float(os.getenv("VAST_INSTANCE_DISK_GB") or "8"),
        },
        "pools": {
            "akoya_wallet": akoya_wallet(),
            "alphamine_wallet": alphamine_wallet(),
            "alphamine_pool_host": os.getenv("ALPHAMINE_POOL_HOST", "us2.alphapool.tech"),
            "alphamine_pool_port": os.getenv("ALPHAMINE_POOL_PORT", "5566"),
            "alphamine_difficulty": os.getenv("ALPHAMINE_DIFFICULTY", "").strip() or "auto por GPU",
        },
        "blacklist": {
            "count": len(blacklist_items(load_vast_blacklist())),
            "items": blacklist_items(load_vast_blacklist()),
        },
        "vast_gpu_triggers": [public_vast_gpu_trigger(trigger, trigger_items) for trigger in triggers],
        "fixed_worker_costs": [public_fixed_worker_cost(item) for item in load_fixed_worker_costs().values()],
    }


@app.post("/api/config/fixed-worker-costs")
async def api_config_fixed_worker_cost_create(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    costs = load_fixed_worker_costs()
    item = fixed_worker_cost_payload(payload, existing=costs.get(str(payload.get("worker_name") or "").strip()))
    costs[item["worker_name"]] = item
    save_fixed_worker_costs(costs)
    return {"fixed_worker_costs": [public_fixed_worker_cost(row) for row in costs.values()], "item": public_fixed_worker_cost(item)}


@app.put("/api/config/fixed-worker-costs/{worker_name}")
async def api_config_fixed_worker_cost_update(worker_name: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    costs = load_fixed_worker_costs()
    existing = costs.get(worker_name)
    item = fixed_worker_cost_payload(payload, worker_name_override=worker_name, existing=existing)
    costs[item["worker_name"]] = item
    save_fixed_worker_costs(costs)
    return {"fixed_worker_costs": [public_fixed_worker_cost(row) for row in costs.values()], "item": public_fixed_worker_cost(item)}


@app.delete("/api/config/fixed-worker-costs/{worker_name}")
async def api_config_fixed_worker_cost_delete(worker_name: str) -> dict[str, Any]:
    costs = load_fixed_worker_costs()
    if worker_name not in costs:
        raise HTTPException(status_code=404, detail="Custo fixo nao encontrado")
    removed = costs.pop(worker_name)
    save_fixed_worker_costs(costs)
    return {"deleted": worker_name, "item": public_fixed_worker_cost(removed), "fixed_worker_costs": [public_fixed_worker_cost(row) for row in costs.values()]}


@app.get("/api/results/state")
async def api_results_state() -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        raw = await load_raw_state()
        results_state = await load_results_state()
        vast = raw.get("monitor:vastai") or {}
        return build_results_state_payload(state, latest_actions, latest_scout, results_state, vast.get("offers") or [])


@app.get("/api/prime/state")
async def api_prime_state() -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        raw = await load_raw_state()
        results_state = await load_results_state()
        vast = raw.get("monitor:vastai") or {}
        return build_prime_state_payload(state, latest_actions, latest_scout, results_state, vast.get("offers") or [])


async def api_results_rent_target(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        results_state = await load_results_state()
        payload_state = build_results_state_payload(state, actions, scout, results_state)
        rows = payload_state["hardware"] if kind == "hardware" else payload_state["patterns"] if kind == "pattern" else payload_state["gpus"]
        wanted_id = str(payload.get("id") or "")
        wanted_gpu = normalize_gpu_name(payload.get("gpu"))
        wanted_machine = str(payload.get("machine_id") or "")
        wanted_host = str(payload.get("host_id") or "")
        wanted_pcie = str(payload.get("pcie") or "")
        target = next(
            (
                item for item in rows
                if (wanted_id and item.get("id") == wanted_id)
                or (
                    kind == "gpu"
                    and wanted_gpu
                    and normalize_gpu_name(item.get("gpu")) == wanted_gpu
                )
                or (
                    kind == "hardware"
                    and wanted_machine
                    and str(item.get("machine_id") or "") == wanted_machine
                    and normalize_gpu_name(item.get("gpu")) == wanted_gpu
                    and safe_int(item.get("gpu_count"), 1) == safe_int(payload.get("gpu_count"), 1)
                )
                or (
                    kind == "pattern"
                    and wanted_gpu
                    and normalize_gpu_name(item.get("gpu")) == wanted_gpu
                    and safe_int(item.get("gpu_count"), 1) == safe_int(payload.get("gpu_count"), 1)
                    and (not wanted_host or str(item.get("host_id") or "") == wanted_host)
                    and (not wanted_pcie or str(item.get("pcie") or "") == wanted_pcie)
                )
            ),
            None,
        )
        if not target:
            raise HTTPException(status_code=404, detail="Resultado lucrativo nao encontrado")
        active = results_active_match(actions, scout, target)
        if active:
            return {"status": "active", "active": active, "target": target}
        queue_item = results_upsert_queue_item(results_state, kind, target, "Solicitado pelo /results")
        queue_item["next_retry_at"] = 0
        await results_attempt_queue_item(results_state, queue_item, state, actions, scout, force=True)
        await save_results_state(results_state)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {"status": queue_item.get("status"), "queue_item": results_queue_public(queue_item), "target": target}


@app.post("/api/results/rent/gpu")
async def api_results_rent_gpu(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return await api_results_rent_target("gpu", payload)


@app.post("/api/results/rent/hardware")
async def api_results_rent_hardware(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return await api_results_rent_target("hardware", payload)


@app.post("/api/results/rent/pattern")
async def api_results_rent_pattern(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    return await api_results_rent_target("pattern", payload)


@app.post("/api/results/rent/offer")
async def api_results_rent_offer(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        settings = scout_settings(scout)
        results_state = await load_results_state()
        ask_id = safe_int(payload.get("ask_id") or payload.get("id"))
        opportunity = find_opportunity_by_id(state, ask_id)
        if not opportunity:
            raw = await load_raw_state()
            vast = raw.get("monitor:vastai") or {}
            raw_offer = next((offer for offer in vast.get("offers", []) if safe_int(offer.get("offer_id")) == ask_id), None)
            if raw_offer:
                statuses = source_status(raw)
                opportunity = calculate_opportunity(
                    "vastai",
                    raw_offer,
                    raw.get("monitor:pearl"),
                    bool(statuses.get("monitor:pearl", {}).get("ok")),
                    actions,
                )
                if opportunity:
                    state.setdefault("opportunities", []).append(opportunity)
        if not opportunity:
            if not payload.get("gpu"):
                raise HTTPException(status_code=404, detail="Oferta Vast nao encontrada")
            target = {
                "ask_id": ask_id,
                "id": ask_id,
                "gpu": normalize_gpu_name(payload.get("gpu")),
                "gpu_count": safe_int(payload.get("gpu_count"), 1),
                "machine_id": payload.get("machine_id"),
                "host_id": payload.get("host_id"),
                "pcie": payload.get("pcie"),
                "cuda": payload.get("cuda"),
                "reliability": payload.get("reliability"),
                "net_up_mbps": payload.get("net_up_mbps"),
                "net_down_mbps": payload.get("net_down_mbps"),
                "price_usd_hr": payload.get("price_usd_hr"),
                "profit_usd_hr": payload.get("profit_usd_hr"),
                "max_price_usd_hr": max(
                    safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
                    safe_float(payload.get("price_usd_hr")),
                ),
                "preferred_pool": payload.get("preferred_pool") or "akoya",
            }
            opportunity = results_manual_opportunity_from_target(target, settings)
            if opportunity:
                state.setdefault("opportunities", []).append(opportunity)
            active = results_active_match(actions, scout, target)
            if active:
                return {"status": "active", "active": active, "target": target}
            queue_item = results_upsert_queue_item(results_state, "offer", target, "Ask sumiu; retry manual pelo /results")
            queue_item["next_retry_at"] = 0
            await results_attempt_queue_item(results_state, queue_item, state, actions, scout, force=True)
            await save_results_state(results_state)
            await refresh_state_unlocked(run_scout_autostart=False)
            return {"status": queue_item.get("status"), "queue_item": results_queue_public(queue_item), "target": target}
        active = results_active_match(actions, scout, opportunity)
        if active:
            return {"status": "active", "active": active, "target": opportunity}
        max_price = max(
            safe_float(settings.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR),
            safe_float(opportunity.get("price_usd_hr")),
        )
        target = dict(opportunity)
        target["ask_id"] = ask_id
        target["max_price_usd_hr"] = max_price
        target["preferred_pool"] = payload.get("preferred_pool") or "akoya"
        queue_item = results_upsert_queue_item(results_state, "offer", target, "Solicitado pelo /results host")
        queue_item["next_retry_at"] = 0
        await results_attempt_queue_item(results_state, queue_item, state, actions, scout, force=True)
        await save_results_state(results_state)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {"status": queue_item.get("status"), "queue_item": results_queue_public(queue_item), "target": target}


@app.post("/api/results/queue/{item_id}/retry")
async def api_results_queue_retry(item_id: str) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        results_state = await load_results_state()
        queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
        item = queue.get(item_id)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="Item Results nao encontrado")
        item["next_retry_at"] = 0
        await results_attempt_queue_item(results_state, item, state, actions, scout, force=True)
        await save_results_state(results_state)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {"queue_item": results_queue_public(item)}


@app.post("/api/results/queue/{item_id}/archive")
async def api_results_queue_archive(item_id: str) -> dict[str, Any]:
    results_state = await load_results_state()
    queue = results_state.get("queue") if isinstance(results_state.get("queue"), dict) else {}
    item = queue.get(item_id)
    if not isinstance(item, dict):
        raise HTTPException(status_code=404, detail="Item Results nao encontrado")
    item["status"] = "archived"
    item["updated_at"] = now_ts()
    await save_results_state(results_state)
    return {"queue_item": results_queue_public(item)}


@app.post("/api/results/blacklist/gpu")
async def api_results_blacklist_gpu(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    async with vast_actions_lock:
        gpu = normalize_gpu_name(payload.get("gpu"))
        if not gpu:
            raise HTTPException(status_code=400, detail="GPU invalida")
        reason = str(payload.get("reason") or "Modelo ruim no Results; bloquear sniper/teste")
        blacklist = load_vast_blacklist()
        item = add_vast_gpu_model_blacklist_item(blacklist, gpu, reason)
        save_vast_blacklist(blacklist)
        await refresh_state_unlocked()
        return {"blacklist_item": item, "count": len(blacklist_items(blacklist))}


@app.post("/api/config/vast-gpu-triggers")
async def api_config_vast_gpu_trigger_create(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        trigger = normalize_vast_gpu_trigger_payload(payload)
        trigger["created_at"] = now_ts()
        trigger["updated_at"] = trigger["created_at"]
        trigger["ignore_ask_ids"] = vast_gpu_trigger_ignore_asks(state, trigger)
        triggers = scout_vast_gpu_triggers(scout)
        triggers.append(trigger)
        scout["vast_gpu_triggers"] = triggers
        await save_scout_state(scout)
        return public_vast_gpu_trigger(trigger, scout.get("queue") if isinstance(scout.get("queue"), dict) else {})


@app.put("/api/config/vast-gpu-triggers/{trigger_id}")
async def api_config_vast_gpu_trigger_update(trigger_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        scout = latest_scout if isinstance(latest_scout, dict) else await load_scout_state()
        triggers = scout_vast_gpu_triggers(scout)
        index = next((idx for idx, item in enumerate(triggers) if item.get("id") == trigger_id), -1)
        if index < 0:
            raise HTTPException(status_code=404, detail="Trigger Vast nao encontrado")
        existing = triggers[index]
        updated = normalize_vast_gpu_trigger_payload(payload, existing)
        gpu_changed = normalize_trigger_gpu(updated.get("gpu_match")) != normalize_trigger_gpu(existing.get("gpu_match"))
        count_changed = safe_int(updated.get("gpu_count"), 1) != safe_int(existing.get("gpu_count"), 1)
        enabled_changed = bool(updated.get("enabled")) and not bool(existing.get("enabled"))
        if gpu_changed or count_changed or enabled_changed:
            updated["created_at"] = now_ts()
            updated["ignore_ask_ids"] = vast_gpu_trigger_ignore_asks(state, updated)
        triggers[index] = updated
        scout["vast_gpu_triggers"] = triggers
        await save_scout_state(scout)
        return public_vast_gpu_trigger(updated, scout.get("queue") if isinstance(scout.get("queue"), dict) else {})


@app.delete("/api/config/vast-gpu-triggers/{trigger_id}")
async def api_config_vast_gpu_trigger_delete(trigger_id: str) -> dict[str, Any]:
    scout = await load_scout_state()
    triggers = scout_vast_gpu_triggers(scout)
    kept = [item for item in triggers if item.get("id") != trigger_id]
    if len(kept) == len(triggers):
        raise HTTPException(status_code=404, detail="Trigger Vast nao encontrado")
    scout["vast_gpu_triggers"] = kept
    await save_scout_state(scout)
    return {"deleted": trigger_id, "vast_gpu_triggers": [public_vast_gpu_trigger(item, scout.get("queue") if isinstance(scout.get("queue"), dict) else {}) for item in kept]}


@app.get("/api/scout/state")
async def api_scout_state() -> dict[str, Any]:
    scout = await load_scout_state()
    scout["settings"] = scout_settings(scout)
    if prune_scout_runtime_state(scout):
        await save_scout_state(scout)
    tests = scout.get("tests") if isinstance(scout.get("tests"), dict) else {}
    active_tests = [test for test in tests.values() if isinstance(test, dict) and test.get("status") == "testing"]
    queue = scout.get("queue") if isinstance(scout.get("queue"), dict) else {}
    radar = scout.get("radar") if isinstance(scout.get("radar"), dict) else {}
    display_items_by_ask = {
        str(item.get("ask_id") or ask_id): item
        for ask_id, item in radar.items()
        if isinstance(item, dict)
    }
    for ask_id, item in queue.items():
        if isinstance(item, dict):
            display_items_by_ask[str(item.get("ask_id") or ask_id)] = item
    queue_items = sorted(
        [item for item in display_items_by_ask.values() if isinstance(item, dict)],
        key=lambda item: (
            item.get("queue_status") == "queued",
            safe_float(item.get("priority_score"), -999999),
            safe_float(item.get("last_seen_at")),
        ),
        reverse=True,
    )[:80]
    queue_counts = scout_queue_counts(queue)
    radar_counts = scout_queue_counts(radar)
    clore_auto_queue_items = clore_auto_queue(scout)
    clore_auto_counts = scout_queue_counts(clore_auto_queue_items)
    history = scout_history_items()[:100]
    return {
        "enabled": bool(scout.get("enabled")),
        "clore_auto_enabled": bool(scout.get("clore_auto_enabled")),
        "updated_at": scout.get("updated_at"),
        "settings": scout["settings"],
        "active_tests": [public_scout_test(test) for test in active_tests],
        "queue": [public_scout_queue_item(item) for item in queue_items],
        "history": [public_scout_history(item) for item in history],
        "summary": {
            "enabled": bool(scout.get("enabled")),
            "clore_auto_enabled": bool(scout.get("clore_auto_enabled")),
            "active": len(active_tests),
            "queue": queue_counts,
            "radar": radar_counts,
            "clore_auto": clore_auto_counts,
            "history_count": len(history),
            "min_profit_usd_hr": scout["settings"]["min_profit_usd_hr"],
            "test_minutes": scout["settings"]["test_seconds"] // 60,
            "max_parallel_tests": scout["settings"]["max_parallel_tests"],
            "max_price_usd_hr": scout["settings"]["max_price_usd_hr"],
            "pool_switch_mode": scout["settings"]["pool_switch_mode"],
            "zero_hash_minutes": scout["settings"]["zero_hash_timeout_seconds"] // 60,
        },
    }


@app.post("/api/scout/settings")
async def api_scout_settings(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    scout = await load_scout_state()
    current = scout_settings(scout)
    if "max_parallel_tests" in payload:
        current["max_parallel_tests"] = min(50, max(1, safe_int(payload.get("max_parallel_tests"), current["max_parallel_tests"])))
    if "min_profit_usd_hr" in payload:
        current["min_profit_usd_hr"] = max(0.0, safe_float(payload.get("min_profit_usd_hr"), current["min_profit_usd_hr"]))
    if "test_minutes" in payload:
        current["test_seconds"] = max(5, safe_int(payload.get("test_minutes"), current["test_seconds"] // 60)) * 60
    if "worker_timeout_minutes" in payload:
        current["worker_timeout_seconds"] = max(1, safe_int(payload.get("worker_timeout_minutes"), current["worker_timeout_seconds"] // 60)) * 60
    if "zero_hash_timeout_minutes" in payload:
        current["zero_hash_timeout_seconds"] = max(1, safe_int(payload.get("zero_hash_timeout_minutes"), current["zero_hash_timeout_seconds"] // 60)) * 60
    if "max_price_usd_hr" in payload:
        current["max_price_usd_hr"] = max(0.01, safe_float(payload.get("max_price_usd_hr"), current["max_price_usd_hr"]))
    if "pool_switch_mode" in payload:
        mode = str(payload.get("pool_switch_mode") or "").strip().lower()
        if mode in SCOUT_POOL_SWITCH_MODES:
            current["pool_switch_mode"] = mode
    scout["settings"] = current
    await save_scout_state(scout)
    return {"settings": current}


@app.post("/api/scout/start")
async def api_scout_start_provider(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    provider = str(payload.get("provider") or "vastai").strip().lower()
    offer_id = safe_int(payload.get("offer_id") or payload.get("ask_id") or payload.get("server_id"))
    requested_strategy = str(payload.get("strategy") or "").strip().lower()
    if provider == "vast":
        provider = "vastai"
    if provider not in {"vastai", "clore"}:
        raise HTTPException(status_code=400, detail="Provider Scout invalido")
    if offer_id <= 0:
        raise HTTPException(status_code=400, detail="Oferta/ID ausente para Scout")

    async with vast_actions_lock:
        state = await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        clore_actions = dict(latest_clore_actions)
        scout = await load_scout_state()
        settings = scout_settings(scout)
        if provider == "clore":
            opportunity = find_clore_opportunity_by_id(state, offer_id)
            if not opportunity:
                raise HTTPException(status_code=404, detail="Servidor Clore nao encontrado")
            options = opportunity.get("rent_options") or {}
            strategy = requested_strategy or next(
                (pool for pool in settings["pool_order"] if (options.get(pool) or {}).get("state") == "ready"),
                "",
            )
            if not strategy:
                raise HTTPException(status_code=409, detail="Nenhum pool Clore pronto para Scout manual")
            test = await start_scout_clore_rent(scout, actions, clore_actions, state, offer_id, strategy)
            await refresh_state_unlocked(run_scout_autostart=False)
            return test

        opportunity = find_opportunity_by_id(state, offer_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Oferta Vast nao encontrada")
        options = opportunity.get("rent_options") or {}
        strategy = requested_strategy or next(
            (
                pool for pool in settings["pool_order"]
                if (options.get(pool) or {}).get("state") == "ready" or scout_candidate_allowed(opportunity, settings)
            ),
            "",
        )
        if not strategy:
            raise HTTPException(status_code=409, detail="Nenhum pool pronto para Scout nesse ask")
        test = await start_scout_rent(scout, actions, state, offer_id, strategy)
        await refresh_state_unlocked(run_scout_autostart=False)
        return test


@app.post("/api/scout/start/{ask_id}")
async def api_scout_start(ask_id: int) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked()
        actions = dict(latest_actions)
        scout = await load_scout_state()
        opportunity = find_opportunity_by_id(state, ask_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Oferta Vast nao encontrada")
        options = opportunity.get("rent_options") or {}
        settings = scout_settings(scout)
        strategy = next(
            (
                pool for pool in settings["pool_order"]
                if (options.get(pool) or {}).get("state") == "ready" or scout_candidate_allowed(opportunity, settings)
            ),
            "",
        )
        if not strategy:
            raise HTTPException(status_code=409, detail="Nenhum pool pronto para Scout nesse ask")
        test = await start_scout_rent(scout, actions, state, ask_id, strategy)
        await refresh_state_unlocked()
        return test


@app.post("/api/scout/stop/{test_id}")
async def api_scout_stop(test_id: str) -> dict[str, Any]:
    async with vast_actions_lock:
        scout = await load_scout_state()
        test = (scout.get("tests") or {}).get(test_id)
        if not isinstance(test, dict):
            raise HTTPException(status_code=404, detail="Teste Scout nao encontrado")
        test.update({"status": "stopped", "decision": "stopped", "reason": "Parado manualmente", "ended_at": now_ts()})
        append_scout_history(scout_result_from_test(test, "stopped", "Parado manualmente"))
        await save_scout_state(scout)
        await refresh_state_unlocked()
        return test


@app.post("/api/scout/pause")
async def api_scout_pause() -> dict[str, Any]:
    scout = await load_scout_state()
    scout["enabled"] = False
    await save_scout_state(scout)
    return scout


@app.post("/api/scout/resume")
async def api_scout_resume() -> dict[str, Any]:
    scout = await load_scout_state()
    scout["enabled"] = True
    await save_scout_state(scout)
    asyncio.create_task(scout_worker_tick())
    return scout


@app.post("/api/scout/clore-auto/pause")
async def api_scout_clore_auto_pause() -> dict[str, Any]:
    scout = await load_scout_state()
    scout["clore_auto_enabled"] = False
    await save_scout_state(scout)
    return scout


@app.post("/api/scout/clore-auto/resume")
async def api_scout_clore_auto_resume() -> dict[str, Any]:
    scout = await load_scout_state()
    scout["clore_auto_enabled"] = True
    await save_scout_state(scout)
    asyncio.create_task(scout_worker_tick())
    return scout


@app.post("/api/scout/clear-history")
async def api_scout_clear_history() -> dict[str, Any]:
    scout = await load_scout_state()
    tests = scout.get("tests") if isinstance(scout.get("tests"), dict) else {}
    active_tests = {
        test_id: test
        for test_id, test in tests.items()
        if isinstance(test, dict) and test.get("status") == "testing"
    }
    removed_tests = len(tests) - len(active_tests)
    removed_history = len(scout_history_items())
    scout["tests"] = active_tests
    save_scout_history([])
    await save_scout_state(scout)
    return {
        "ok": True,
        "removed_history": removed_history,
        "removed_finished_tests": removed_tests,
        "active_tests": len(active_tests),
    }


@app.post("/api/scout/reset")
async def api_scout_reset(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    destroy_active = bool(payload.get("destroy_active", True))
    destroy_all_active = bool(payload.get("destroy_all_active_except_preserved", False))
    archive_history = bool(payload.get("archive_history", True))
    clear_vast_history = bool(payload.get("clear_vast_history", False))
    clear_vast_blacklist = bool(payload.get("clear_vast_blacklist", False))
    preserve_instance_ids = {
        safe_int(item)
        for item in payload.get("preserve_instance_ids", [])
        if safe_int(item) > 0
    }
    preserve_ask_ids = {
        str(safe_int(item))
        for item in payload.get("preserve_ask_ids", [])
        if safe_int(item) > 0
    }
    async with vast_actions_lock:
        actions = await load_vast_actions()
        scout = await load_scout_state()
        tests = scout.get("tests") if isinstance(scout.get("tests"), dict) else {}
        history = scout_history_items()
        removed_history = len(history)
        archive_path = archive_scout_history(history) if archive_history and history else ""
        actions_archive_path = archive_vast_actions(actions) if clear_vast_history and actions else ""
        destroyed = 0
        archived_actions = 0
        preserved_actions = 0
        removed_vast_actions = 0
        destroy_errors: list[dict[str, Any]] = []
        destroyed_instances: list[dict[str, Any]] = []

        for ask_id, action in list(actions.items()):
            if not isinstance(action, dict):
                continue
            instance_id = safe_int(action.get("instance_id"))
            should_preserve = instance_id in preserve_instance_ids or str(ask_id) in preserve_ask_ids
            if should_preserve:
                preserved_pool = str(action.get("vast_pool_strategy_actual") or action.get("pool_strategy") or "akoya")
                action["state"] = "rented"
                action["reason"] = "Preservada no reset: maquina lucrativa 38283931"
                action["scout_preserved"] = True
                action["pool_strategy"] = preserved_pool if preserved_pool in SCOUT_POOL_ORDER else "akoya"
                action.pop("switch_target_pool", None)
                action.pop("return_target_pool", None)
                action.pop("switch_error", None)
                action["updated_at"] = now_ts()
                action.pop("scout_test_id", None)
                actions[str(ask_id)] = action
                preserved_actions += 1
                continue
            if not destroy_all_active:
                continue
            is_active_action = action.get("state") in {"renting", "rented", "active", "ativo"}
            if not is_active_action or instance_id <= 0:
                continue
            if destroy_active:
                try:
                    destroy_result = await destroy_vast_instance(instance_id)
                    destroyed += 1
                    destroyed_instances.append({
                        "ask_id": ask_id,
                        "instance_id": instance_id,
                        "destroy_result": destroy_result,
                    })
                except Exception as exc:
                    destroy_errors.append({"ask_id": ask_id, "instance_id": instance_id, "error": str(exc)})
                    continue
            action.update({
                "state": "archived",
                "reason": "Reset Scout: destruida para recomecar; preservando apenas 38283931",
                "updated_at": now_ts(),
            })
            actions[str(ask_id)] = action
            archived_actions += 1

        for test in list(tests.values()):
            if not isinstance(test, dict):
                continue
            ask_id = str(test.get("ask_id") or "")
            action = action_by_id(actions, ask_id)
            instance_id = safe_int(test.get("instance_id") or (action or {}).get("instance_id"))
            if instance_id in preserve_instance_ids or ask_id in preserve_ask_ids:
                continue
            if destroy_all_active:
                continue
            if destroy_active and instance_id > 0 and test.get("status") == "testing":
                try:
                    await destroy_vast_instance(instance_id)
                    destroyed += 1
                    destroyed_instances.append({"ask_id": ask_id, "instance_id": instance_id})
                except Exception as exc:
                    destroy_errors.append({"test_id": test.get("test_id"), "instance_id": instance_id, "error": str(exc)})
            if action and action.get("scout_test_id"):
                action.update({
                    "state": "archived",
                    "reason": "Scout resetado; teste anterior apagado",
                    "updated_at": now_ts(),
                })
                actions[ask_id] = action
                archived_actions += 1

        if clear_vast_history:
            for ask_id, action in list(actions.items()):
                if not isinstance(action, dict):
                    continue
                instance_id = safe_int(action.get("instance_id"))
                should_preserve = instance_id in preserve_instance_ids or str(ask_id) in preserve_ask_ids
                if should_preserve:
                    continue
                if action.get("state") in {"failed", "archived"}:
                    actions.pop(str(ask_id), None)
                    removed_vast_actions += 1

        scout["enabled"] = False
        scout["tests"] = {}
        scout["queue"] = {}
        scout["settings"] = scout_settings(scout)
        scout["settings"]["worker_timeout_seconds"] = max(scout["settings"].get("worker_timeout_seconds", 0), 900)
        blacklist_state = load_vast_blacklist()
        before_blacklist = len(blacklist_items(blacklist_state))
        if clear_vast_blacklist:
            blacklist_state["items"] = []
        else:
            blacklist_state["items"] = [
                item
                for item in blacklist_items(blacklist_state)
                if "scout" not in str(item.get("reason") or "").lower()
            ]
        removed_blacklist = before_blacklist - len(blacklist_state["items"])
        save_scout_history([])
        save_vast_blacklist(blacklist_state)
        await save_vast_actions(actions)
        await save_scout_state(scout)
        await refresh_state_unlocked()
        return {
            "ok": True,
            "destroyed_active": destroyed,
            "archived_actions": archived_actions,
            "removed_tests": len(tests),
            "removed_history": removed_history,
            "removed_scout_blacklist": removed_blacklist,
            "destroy_errors": destroy_errors,
            "destroyed_instances": destroyed_instances,
            "preserved_actions": preserved_actions,
            "archive_path": archive_path,
            "actions_archive_path": actions_archive_path,
            "removed_vast_actions": removed_vast_actions,
        }


@app.post("/api/scout/destroy/{test_id}")
async def api_scout_destroy(test_id: str, payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    async with vast_actions_lock:
        state = await refresh_state_unlocked()
        actions = dict(latest_actions)
        scout = await load_scout_state()
        test = (scout.get("tests") or {}).get(test_id)
        if not isinstance(test, dict):
            raise HTTPException(status_code=404, detail="Teste Scout nao encontrado")
        settings = scout_settings(scout)
        min_profit = safe_float(test.get("min_profit_usd_hr"), settings["min_profit_usd_hr"])
        min_hash_ratio = safe_float(test.get("min_hash_ratio"), settings["min_hash_ratio"])
        best = scout_best_pool_result(test, min_profit, min_hash_ratio)
        latest_viable = (
            safe_float(test.get("latest_profit_usd_hr"), -999999) >= min_profit
            and safe_float(test.get("latest_hash_ratio")) >= min_hash_ratio
        )
        if (best or latest_viable) and not payload.get("force_profitable_destroy"):
            best_pool = str((best or {}).get("pool_strategy") or test.get("pool_strategy") or "")
            best_profit = safe_float((best or {}).get("profit_usd_hr"), safe_float(test.get("latest_profit_usd_hr")))
            raise HTTPException(
                status_code=409,
                detail=f"Teste tem pool lucrativo ({strategy_label(best_pool)} ${best_profit:.2f}/h). Confirme destroy manual.",
            )
        destroy_reason = "Destroy manual pelo Scout"
        clore_actions = dict(latest_clore_actions)
        result = await finish_scout_test(
            scout,
            actions,
            test,
            "destroy",
            destroy_reason,
            destroy=True,
            blacklist=True,
            clore_actions=clore_actions,
        )
        action = action_by_id(actions, test.get("ask_id"))
        target = dict(test)
        if action:
            target.update(action)
        removed_queue_items = remove_scout_queue_entries_for_target(scout, target, destroy_reason)
        results_state = await load_results_state()
        archived_results_items = archive_results_queue_entries_for_target(results_state, target, destroy_reason)
        if archived_results_items:
            await save_results_state(results_state)
        await save_scout_state(scout)
        await refresh_state_unlocked()
        return {
            "test": test,
            "result": result,
            "state": state.get("generated_at"),
            "manual_blacklist": True,
            "removed_queue_items": removed_queue_items,
            "archived_results_items": archived_results_items,
        }


@app.delete("/api/config/blacklist/{index}")
async def api_config_blacklist_delete(index: int) -> dict[str, Any]:
    async with vast_actions_lock:
        blacklist = load_vast_blacklist()
        items = blacklist_items(blacklist)
        if index < 0 or index >= len(items):
            raise HTTPException(status_code=404, detail="Item da blacklist nao encontrado")
        removed = items.pop(index)
        blacklist["items"] = items
        save_vast_blacklist(blacklist)
        await refresh_state_unlocked()
        return {"removed": removed, "count": len(items)}


@app.get("/api/vast/actions")
async def api_vast_actions() -> dict[str, Any]:
    actions = await load_vast_actions()
    raw = await load_raw_state()
    statuses = source_status(raw)
    operation = build_operation(raw, statuses, actions)
    return vast_action_summary(actions, operation)


@app.get("/api/clore/actions")
async def api_clore_actions() -> dict[str, Any]:
    actions = await load_clore_actions()
    raw = await load_raw_state()
    statuses = source_status(raw)
    vast_actions = await load_vast_actions()
    operation = build_operation(raw, statuses, vast_actions, actions)
    return clore_action_summary(actions, operation)


def clore_marketplace_native_price_day(server: dict[str, Any], currency: str) -> float:
    price = server.get("price") or {}
    on_demand = price.get("on_demand") or {}
    return safe_float(on_demand.get(currency))


def clore_marketplace_server_payload(server: dict[str, Any], opportunity: dict[str, Any], currency: str, native_price_day: float, price_usd_day: float) -> dict[str, Any]:
    return {
        "server_id": server.get("id"),
        "gpu_model_raw": opportunity.get("gpu_raw") or opportunity.get("gpu"),
        "gpu_model_normalized": opportunity.get("gpu"),
        "gpu_count": opportunity.get("gpu_count"),
        "price_usd_hr": round_money(price_usd_day / 24) if price_usd_day > 0 else opportunity.get("price_usd_hr"),
        "price_usd_day": round_money(price_usd_day) if price_usd_day > 0 else opportunity.get("cost_usd_day"),
        "native_price_day": native_price_day,
        "price_currency": currency,
        "allowed_coins": server.get("allowed_coins") or [],
    }


@app.post("/api/clore/rent/{server_id}/{strategy}")
async def api_clore_rent_strategy(server_id: int, strategy: str) -> dict[str, Any]:
    strategy = strategy.strip().lower()
    if strategy not in clore.pool_strategies():
        raise HTTPException(status_code=400, detail="Pool invalido")
    async with vast_actions_lock:
        await refresh_state_unlocked(run_scout_autostart=False)
        opportunity = next(
            (
                item for item in latest_state.get("opportunities", [])
                if item.get("platform") == "clore" and safe_int(item.get("id")) == server_id
            ),
            None,
        )
        if not opportunity:
            raise HTTPException(status_code=404, detail="Servidor Clore nao encontrado nas oportunidades atuais")
        rent_option = (opportunity.get("rent_options") or {}).get(strategy) or {}

        actions = dict(latest_clore_actions)
        previous = action_by_id(actions, server_id)

        async def fail_clore_rent(detail: str, status_code: int = 409) -> None:
            current = now_ts()
            created_at = previous.get("created_at") if previous else current
            actions[str(server_id)] = {
                "provider": "clore",
                "server_id": server_id,
                "state": "failed",
                "pool_strategy": strategy,
                "worker_name": clore.strategy_worker_name(strategy, server_id),
                "gpu": opportunity.get("gpu"),
                "gpu_count": opportunity.get("gpu_count"),
                "price_usd_hr": round_money(safe_float(opportunity.get("price_usd_hr"))),
                "price_usd_day": round_money(safe_float(opportunity.get("cost_usd_day"))),
                "max_safe_price_usd_hr": opportunity.get("max_safe_price_usd_hr"),
                "reason": f"Falha aluguel manual Clore {clore.strategy_label(strategy)}",
                "error": detail,
                "created_at": created_at,
                "updated_at": current,
            }
            await save_clore_actions(actions)
            raise HTTPException(status_code=status_code, detail=detail)

        if rent_option.get("state") != "ready":
            await fail_clore_rent(rent_option.get("reason") or "Clore nao pronta para aluguel")
        if previous and previous.get("state") in {"renting", "rented"}:
            raise HTTPException(status_code=409, detail="Servidor Clore ja tem acao ativa")

        market = await clore.marketplace()
        server = next((item for item in market.get("servers", []) or [] if safe_int(item.get("id")) == server_id), None)
        if not server:
            await fail_clore_rent("Servidor Clore nao existe mais no marketplace oficial")
        if server.get("rented", True):
            await fail_clore_rent("Servidor Clore ficou rented antes do clique")

        wallets = await clore.wallets()
        currencies = clore.eligible_currencies(server, wallets)
        if not currencies:
            reasons = "; ".join(clore.currency_rejection_reasons(server, wallets))
            suffix = f": {reasons}" if reasons else ""
            await fail_clore_rent(f"Nenhuma moeda aceita pela oferta tem saldo/configuracao{suffix}")
        currency = currencies[0]
        native_price_day = clore_marketplace_native_price_day(server, currency)
        if native_price_day <= 0:
            await fail_clore_rent(f"Preco nativo ausente para {currency}")
        price_day = safe_float(opportunity.get("cost_usd_day"))
        if price_day <= 0:
            await fail_clore_rent("Preco USD enriquecido ausente para calcular lucro")
        price_hr = price_day / 24
        max_safe_price = safe_float(opportunity.get("max_safe_price_usd_hr"))
        decision = str(opportunity.get("decision") or "")
        if decision == "green" and max_safe_price > 0 and price_hr > max_safe_price:
            await fail_clore_rent(f"Preco subiu para ${price_hr:.2f}/h acima do teto ${max_safe_price:.2f}/h")

        spot = await clore.spot_marketplace(server_id)
        spot_server = ((spot.get("market") or {}).get("server") or {}) if spot.get("exists", True) else {}
        if spot.get("exists") is False:
            await fail_clore_rent("Mercado Clore nao existe mais para este server")
        if spot_server and not spot_server.get("online", True):
            await fail_clore_rent("Servidor Clore esta offline na revalidacao")
        if spot_server and str(spot_server.get("visibility") or "public") != "public":
            await fail_clore_rent("Servidor Clore nao esta publico na revalidacao")

        action_server = clore_marketplace_server_payload(server, opportunity, currency, native_price_day, price_day)
        current = now_ts()
        actions[str(server_id)] = {
            "provider": "clore",
            "server_id": server_id,
            "state": "renting",
            "pool_strategy": strategy,
            "worker_name": clore.strategy_worker_name(strategy, server_id),
            "gpu": opportunity.get("gpu"),
            "gpu_count": opportunity.get("gpu_count"),
            "price_usd_hr": round_money(price_hr),
            "price_usd_day": round_money(price_day),
            "native_price_day": native_price_day,
            "max_safe_price_usd_hr": opportunity.get("max_safe_price_usd_hr"),
            "currency": currency,
            "image": clore.image_for_strategy(strategy),
            "reason": f"Aluguel manual Clore {clore.strategy_label(strategy)} pelo dashboard",
            "created_at": current,
            "updated_at": current,
        }
        await save_clore_actions(actions)
        create_errors: list[str] = []
        try:
            result = None
            for candidate_currency in currencies:
                candidate_native_price_day = clore_marketplace_native_price_day(server, candidate_currency)
                if candidate_native_price_day <= 0:
                    continue
                action_server = clore_marketplace_server_payload(server, opportunity, candidate_currency, candidate_native_price_day, price_day)
                actions[str(server_id)].update({
                    "currency": candidate_currency,
                    "native_price_day": candidate_native_price_day,
                    "updated_at": now_ts(),
                })
                await save_clore_actions(actions)
                try:
                    result = await clore.create_order(server_id, strategy, action_server, candidate_native_price_day, candidate_currency)
                    break
                except HTTPException as exc:
                    detail = str(exc.detail)
                    create_errors.append(f"{candidate_currency}: {detail}")
                    if "currency-not-allowed" in detail:
                        continue
                    raise
            if result is None:
                if any("currency-not-allowed" in item for item in create_errors):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Clore recusou as moedas elegiveis no create_order. "
                            "A API pode mostrar saldo/preco, mas ainda recusar uma moeda no create_order. "
                            "Erros: " + "; ".join(create_errors)
                        ),
                    )
                raise HTTPException(status_code=409, detail="Nenhuma moeda Clore criou ordem: " + "; ".join(create_errors))
            actions[str(server_id)].update({
                "state": "renting",
                "create_result": result,
                "worker_name": result.get("worker_name") or actions[str(server_id)].get("worker_name"),
                "updated_at": now_ts(),
            })
            await save_clore_actions(actions)
            actions = await sync_clore_actions_with_orders(actions, force=True)
        except Exception as exc:
            actions[str(server_id)].update({
                "state": "failed",
                "error": getattr(exc, "detail", str(exc)),
                "updated_at": now_ts(),
            })
            await save_clore_actions(actions)
            raise
        await refresh_state_unlocked(run_scout_autostart=False)
        return actions[str(server_id)]


@app.post("/api/clore/actions/{server_id}/cancel")
async def api_clore_cancel_action(server_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        actions = await load_clore_actions()
        action = action_by_id(actions, server_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Clore nao encontrada")
        order_id = safe_int(action.get("order_id"))
        if order_id <= 0:
            actions[str(server_id)]["state"] = "archived"
            actions[str(server_id)]["reason"] = "Arquivada sem order_id Clore"
            actions[str(server_id)]["updated_at"] = now_ts()
            await save_clore_actions(actions)
            await refresh_state_unlocked(run_scout_autostart=False)
            return actions[str(server_id)]
        reason = str((body or {}).get("reason") or "Cancelamento manual pelo dashboard")
        result = await safe_cancel_clore_order(order_id, reason)
        action.update({
            "state": "cancelled",
            "reason": reason,
            "cancel_result": result,
            "cancelled_at": now_ts(),
            "updated_at": now_ts(),
        })
        actions[str(server_id)] = action
        await save_clore_actions(actions)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {"action": action, "cancel_result": result}


@app.post("/api/vast/actions/{ask_id}/archive")
async def api_vast_archive(ask_id: int) -> dict[str, Any]:
    async with vast_actions_lock:
        actions = await load_vast_actions()
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        if action.get("state") == "rented":
            action["state"] = "archived"
            action["reason"] = "Arquivada apos destroy manual na Vast; nao altera a instancia remotamente"
            action["updated_at"] = now_ts()
        else:
            actions.pop(str(ask_id), None)
        await save_vast_actions(actions)
        await refresh_state_unlocked()
        return action


@app.post("/api/vast/actions/{ask_id}/destroy")
async def api_vast_destroy_action(ask_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        await refresh_state_unlocked()
        actions = dict(latest_actions)
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            raise HTTPException(status_code=409, detail="Acao sem instance_id Vast para destruir")
        destroy_result = await destroy_vast_instance(instance_id)
        reason = str((body or {}).get("reason") or "Destroy manual pela Operacao Pools")
        action["state"] = "archived"
        action["reason"] = reason
        action["destroyed_at"] = now_ts()
        action["destroy_result"] = destroy_result
        action["updated_at"] = now_ts()
        actions[str(ask_id)] = action
        await save_vast_actions(actions)

        scout = await load_scout_state()
        target = {
            "ask_id": ask_id,
            "instance_id": instance_id,
            "machine_id": action.get("machine_id"),
            "host_id": action.get("host_id"),
            "gpu": action.get("gpu"),
            "gpu_count": action.get("gpu_count"),
        }
        remove_scout_queue_entries_for_target(scout, target, reason)
        for test in (scout.get("tests") or {}).values():
            if isinstance(test, dict) and safe_int(test.get("instance_id")) == instance_id:
                test.update({"status": "stopped", "decision": "destroy", "reason": reason, "ended_at": now_ts()})
        await save_scout_state(scout)

        results_state = await load_results_state()
        archive_results_queue_entries_for_target(results_state, target, reason)
        await save_results_state(results_state)
        await refresh_state_unlocked()
        return {"action": action, "destroy_result": destroy_result}


@app.post("/api/vast/actions/{ask_id}/update-akoya")
async def api_vast_update_akoya_action(ask_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            raise HTTPException(status_code=409, detail="Acao sem instance_id Vast para atualizar")
        pool_strategy = str(action.get("pool_strategy") or action.get("vast_pool_strategy_actual") or "akoya").strip().lower()
        if pool_strategy != "akoya":
            raise HTTPException(status_code=409, detail="Atualizacao Akoya permitida apenas para worker em Akoya")

        worker_name = str(action.get("worker_name") or strategy_worker_name("akoya", ask_id))
        gpu_name = action.get("gpu")
        raw = await load_raw_state()
        statuses = source_status(raw)
        operation = build_operation(raw, statuses, actions)
        worker = find_operation_worker(operation, worker_name, "akoya")
        before_hashrate = safe_float((worker or {}).get("hashrate_ths"))
        update_result = await update_vast_instance_pool_config(instance_id, "akoya", worker_name, gpu_name)
        recycle_result = await recycle_vast_instance(instance_id)
        reason = str((body or {}).get("reason") or "Atualizacao manual Akoya Miner pelo dashboard")
        current = now_ts()
        action.update({
            "state": "rented",
            "pool_strategy": "akoya",
            "worker_name": worker_name,
            "reason": f"{reason}; recycle iniciado",
            "akoya_image_updated_at": current,
            "akoya_image": vast_image_for_strategy("akoya"),
            "akoya_update_before_hashrate_ths": round_money(before_hashrate),
            "akoya_update_result": update_result,
            "akoya_recycle_result": recycle_result,
            "updated_at": current,
        })
        actions[str(ask_id)] = action
        await save_vast_actions(actions)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {
            "action": action,
            "target_image": vast_image_for_strategy("akoya"),
            "update_result": update_result,
            "recycle_result": recycle_result,
        }


@app.post("/api/vast/actions/{ask_id}/recycle")
async def api_vast_recycle_action(ask_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            raise HTTPException(status_code=409, detail="Acao sem instance_id Vast para reciclar")

        current = now_ts()
        attempts = safe_int(action.get("offline_rescue_attempts")) + 1
        reason = str((body or {}).get("reason") or "Recycle manual pela Operacao Pools")
        try:
            recycle_result = await recycle_vast_instance(instance_id)
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            action.update({
                "offline_rescue_enabled": True,
                "offline_rescue_state": "retry_error",
                "offline_rescue_attempts": attempts,
                "offline_rescue_last_at": current,
                "offline_rescue_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
                "offline_rescue_last_error": str(detail),
                "reason": f"{reason}; recycle falhou; retry automatico armado",
                "updated_at": current,
            })
            actions[str(ask_id)] = action
            await save_vast_actions(actions)
            raise

        action.update({
            "state": "rented",
            "offline_rescue_enabled": True,
            "offline_rescue_state": "recycling",
            "offline_rescue_first_seen_at": action.get("offline_rescue_first_seen_at") or current,
            "offline_rescue_attempts": attempts,
            "offline_rescue_last_at": current,
            "offline_rescue_next_at": current + VAST_OFFLINE_RESCUE_INTERVAL_SECONDS,
            "offline_rescue_result": recycle_result,
            "offline_rescue_last_error": "",
            "reason": f"{reason}; recycle sem trocar imagem iniciado",
            "updated_at": current,
        })
        actions[str(ask_id)] = action
        await save_vast_actions(actions)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {"action": action, "recycle_result": recycle_result}


@app.post("/api/vast/actions/{ask_id}/switch-pool")
async def api_vast_switch_pool_action(ask_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        await refresh_state_unlocked(run_scout_autostart=False)
        actions = dict(latest_actions)
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            raise HTTPException(status_code=409, detail="Acao sem instance_id Vast para trocar pool")

        target_pool = str((body or {}).get("target_pool") or "").strip().lower()
        if target_pool not in vast_pool_strategies():
            raise HTTPException(status_code=400, detail="Pool alvo invalida")
        current_pool = str(action.get("pool_strategy") or action.get("vast_pool_strategy_actual") or "").strip().lower()
        if current_pool not in vast_pool_strategies():
            current_pool = "akoya"
        if target_pool == current_pool:
            raise HTTPException(status_code=409, detail="Pool alvo ja esta ativa nessa acao")

        current_worker_name = str(action.get("worker_name") or strategy_worker_name(current_pool, ask_id))
        target_worker_name = strategy_worker_name(target_pool, ask_id)
        gpu_name = action.get("gpu")
        raw = await load_raw_state()
        statuses = source_status(raw)
        operation = build_operation(raw, statuses, actions)
        worker = find_operation_worker(operation, current_worker_name, current_pool)
        before_hashrate = safe_float((worker or {}).get("hashrate_ths"))
        before_profit = (worker or {}).get("profit_usd_hr")
        current = now_ts()

        update_result = await update_vast_instance_pool_config(instance_id, target_pool, target_worker_name, gpu_name)
        recycle_result = await recycle_vast_instance(instance_id)
        reason = str((body or {}).get("reason") or f"Troca manual para {strategy_label(target_pool)} pelo dashboard")
        action.update({
            "state": "rented",
            "pool_strategy": target_pool,
            "worker_name": target_worker_name,
            "reason": f"{reason}; recycle iniciado",
            "pool_switch_started_at": current,
            "pool_switch_from_pool": current_pool,
            "pool_switch_to_pool": target_pool,
            "pool_switch_before_hashrate_ths": round_money(before_hashrate),
            "pool_switch_before_profit_usd_hr": round_money(safe_float(before_profit)) if before_profit is not None else None,
            "pool_switch_before_image": vast_image_for_strategy(current_pool),
            "pool_switch_target_image": vast_image_for_strategy(target_pool),
            "pool_switch_result": {"update": update_result, "recycle": recycle_result},
            "updated_at": current,
        })
        actions[str(ask_id)] = action
        await save_vast_actions(actions)
        await refresh_state_unlocked(run_scout_autostart=False)
        return {
            "action": action,
            "from_pool": current_pool,
            "target_pool": target_pool,
            "target_image": vast_image_for_strategy(target_pool),
            "update_result": update_result,
            "recycle_result": recycle_result,
        }


@app.post("/api/vast/actions/{ask_id}/blacklist")
async def api_vast_blacklist(ask_id: int, body: dict[str, Any] | None = None) -> dict[str, Any]:
    async with vast_actions_lock:
        await refresh_state_unlocked()
        actions = dict(latest_actions)
        action = action_by_id(actions, ask_id)
        if not action:
            raise HTTPException(status_code=404, detail="Acao Vast nao encontrada")
        instance_id = safe_int(action.get("instance_id"))
        if instance_id <= 0:
            raise HTTPException(status_code=409, detail="Acao sem instance_id Vast para destruir")

        reason = str((body or {}).get("reason") or "Blacklist manual pelo dashboard")
        blacklist = load_vast_blacklist()
        blacklist_item = add_vast_blacklist_item(blacklist, action, reason)
        destroy_result = await destroy_vast_instance(instance_id)
        save_vast_blacklist(blacklist)
        action["state"] = "archived"
        action["reason"] = "Arquivada e blacklistada; destroy enviado para Vast"
        action["blacklisted_at"] = now_ts()
        action["blacklist_reason"] = reason
        action["destroy_result"] = destroy_result
        action["updated_at"] = now_ts()
        actions[str(ask_id)] = action
        await save_vast_actions(actions)
        await refresh_state_unlocked()
        return {"action": action, "blacklist_item": blacklist_item, "destroy_result": destroy_result}


@app.post("/api/vast/rent/{ask_id}")
async def api_vast_rent(ask_id: int) -> dict[str, Any]:
    return await api_vast_rent_strategy(ask_id, "akoya")


@app.post("/api/vast/rent/{ask_id}/{strategy}")
async def api_vast_rent_strategy(ask_id: int, strategy: str) -> dict[str, Any]:
    strategy = strategy.strip().lower()
    if strategy not in vast_pool_strategies():
        raise HTTPException(status_code=400, detail="Estrategia invalida")
    async with vast_actions_lock:
        state = await refresh_state_unlocked()
        actions = dict(latest_actions)
        opportunity = find_opportunity_by_id(state, ask_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Oferta Vast nao encontrada no estado atual")
        rent_option = (opportunity.get("rent_options") or {}).get(strategy) or {}
        if rent_option.get("state") != "ready":
            raise HTTPException(status_code=409, detail=rent_option.get("reason") or "Oferta nao esta pronta")

        now = now_ts()
        actions[str(ask_id)] = {
            "state": "renting",
            "reason": f"Revalidando ask e enviando aceite para Vast ({strategy_label(strategy)})",
            "ask_id": ask_id,
            "worker_name": strategy_worker_name(strategy, ask_id),
            "pool_strategy": strategy,
            "gpu": opportunity.get("gpu"),
            "gpu_count": opportunity.get("gpu_count"),
            "price_usd_hr": opportunity.get("price_usd_hr"),
            "max_safe_price_usd_hr": opportunity.get("max_safe_price_usd_hr"),
            "created_at": now,
            "updated_at": now,
        }
        await save_vast_actions(actions)

        try:
            offer = await revalidate_vast_ask(ask_id)
            revalidated_price = vast_offer_price_hr(offer)
            max_safe = safe_float(opportunity.get("max_safe_price_usd_hr"))
            if revalidated_price <= 0:
                raise HTTPException(status_code=409, detail="Preco Vast indisponivel na revalidacao")
            if max_safe <= 0 or revalidated_price > max_safe:
                raise HTTPException(
                    status_code=409,
                    detail=f"Preco subiu/ultrapassou teto: ${revalidated_price:.4f}/h > ${max_safe:.4f}/h",
                )
            result = await accept_vast_ask(ask_id, opportunity, revalidated_price, strategy)
            actions[str(ask_id)].update({
                "state": "rented",
                "reason": f"Instancia Vast criada; aguardando worker aparecer no {strategy_label(strategy)}",
                "instance_id": result.get("instance_id"),
                "worker_name": result.get("worker_name"),
                "pool_strategy": result.get("pool_strategy", strategy),
                "price_usd_hr": result.get("price_usd_hr"),
                "updated_at": now_ts(),
                "vast_response": result.get("raw", {}),
            })
            await save_vast_actions(actions)
            await refresh_state_unlocked()
            return actions[str(ask_id)]
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            actions[str(ask_id)].update({
                "state": "failed",
                "reason": "Falha ao alugar",
                "error": str(detail),
                "updated_at": now_ts(),
            })
            await save_vast_actions(actions)
            if isinstance(exc, HTTPException):
                raise exc
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.websocket("/ws")
async def ws_state(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    try:
        state = latest_state or await refresh_state()
        await websocket.send_text(json.dumps(state, ensure_ascii=False))
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        clients.discard(websocket)
    finally:
        clients.discard(websocket)
