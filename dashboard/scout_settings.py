import os
import time
from typing import Any

from shared.gpu_hashrates import normalize_gpu_name


VAST_AUTORENT_MODE = os.getenv("VAST_AUTORENT_MODE", "confirm")
SCOUT_TEST_SECONDS = int(os.getenv("SCOUT_TEST_SECONDS") or "1800")
SCOUT_WORKER_TIMEOUT_SECONDS = int(os.getenv("SCOUT_WORKER_TIMEOUT_SECONDS") or "900")
SCOUT_OFFLINE_TIMEOUT_SECONDS = int(os.getenv("SCOUT_OFFLINE_TIMEOUT_SECONDS") or "480")
SCOUT_ZERO_HASH_TIMEOUT_SECONDS = int(os.getenv("SCOUT_ZERO_HASH_TIMEOUT_SECONDS") or "300")
SCOUT_MIN_PROFIT_USD_HR = float(os.getenv("SCOUT_MIN_PROFIT_USD_HR") or "0.20")
SCOUT_MIN_HASH_RATIO = float(os.getenv("SCOUT_MIN_HASH_RATIO") or "0.45")
SCOUT_MAX_PARALLEL_TESTS = int(os.getenv("SCOUT_MAX_PARALLEL_TESTS") or "10")
SCOUT_STARTS_PER_TICK = int(os.getenv("SCOUT_STARTS_PER_TICK") or "1")
SCOUT_MAX_PRICE_USD_HR = float(os.getenv("SCOUT_MAX_PRICE_USD_HR") or "3.00")
SCOUT_POOL_SWITCH_MODE = os.getenv("SCOUT_POOL_SWITCH_MODE", "in_place_ab").strip().lower()
SCOUT_POOL_SWITCH_MODES = {"single_pool", "recreate", "in_place_ab"}
SCOUT_POOL_ORDER = ("akoya", "alphamine")
SCOUT_ALLOWED_GPU_MODELS = tuple(
    normalize_gpu_name(item)
    for item in (os.getenv("SCOUT_ALLOWED_GPU_MODELS") or "H100 SXM").split(",")
    if normalize_gpu_name(item)
)


def now_ts() -> float:
    return time.time()


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def defaults() -> dict[str, Any]:
    return {
        "enabled": VAST_AUTORENT_MODE == "auto",
        "clore_auto_enabled": False,
        "updated_at": now_ts(),
        "tests": {},
        "queue": {},
        "clore_auto_queue": {},
        "radar": {},
        "vast_gpu_triggers": [],
        "settings": {
            "test_seconds": SCOUT_TEST_SECONDS,
            "worker_timeout_seconds": SCOUT_WORKER_TIMEOUT_SECONDS,
            "offline_timeout_seconds": SCOUT_OFFLINE_TIMEOUT_SECONDS,
            "zero_hash_timeout_seconds": SCOUT_ZERO_HASH_TIMEOUT_SECONDS,
            "min_profit_usd_hr": SCOUT_MIN_PROFIT_USD_HR,
            "min_hash_ratio": SCOUT_MIN_HASH_RATIO,
            "max_parallel_tests": SCOUT_MAX_PARALLEL_TESTS,
            "starts_per_tick": SCOUT_STARTS_PER_TICK,
            "max_price_usd_hr": SCOUT_MAX_PRICE_USD_HR,
            "pool_switch_mode": SCOUT_POOL_SWITCH_MODE,
            "pool_order": list(SCOUT_POOL_ORDER),
            "allowed_gpu_models": list(SCOUT_ALLOWED_GPU_MODELS),
        },
    }


def settings(scout: dict[str, Any] | None = None) -> dict[str, Any]:
    base = defaults()["settings"]
    incoming = (scout or {}).get("settings") if isinstance(scout, dict) else {}
    merged = dict(base)
    if isinstance(incoming, dict):
        merged.update({key: value for key, value in incoming.items() if value is not None})
    merged["test_seconds"] = max(60, safe_int(merged.get("test_seconds"), SCOUT_TEST_SECONDS))
    merged["worker_timeout_seconds"] = max(60, safe_int(merged.get("worker_timeout_seconds"), SCOUT_WORKER_TIMEOUT_SECONDS))
    merged["offline_timeout_seconds"] = max(60, safe_int(merged.get("offline_timeout_seconds"), SCOUT_OFFLINE_TIMEOUT_SECONDS))
    merged["zero_hash_timeout_seconds"] = max(60, safe_int(merged.get("zero_hash_timeout_seconds"), SCOUT_ZERO_HASH_TIMEOUT_SECONDS))
    merged["min_profit_usd_hr"] = safe_float(merged.get("min_profit_usd_hr"), SCOUT_MIN_PROFIT_USD_HR)
    merged["min_hash_ratio"] = safe_float(merged.get("min_hash_ratio"), SCOUT_MIN_HASH_RATIO)
    merged["max_parallel_tests"] = min(50, max(1, safe_int(merged.get("max_parallel_tests"), SCOUT_MAX_PARALLEL_TESTS)))
    merged["starts_per_tick"] = min(merged["max_parallel_tests"], max(1, safe_int(merged.get("starts_per_tick"), SCOUT_STARTS_PER_TICK)))
    merged["max_price_usd_hr"] = max(0.01, safe_float(merged.get("max_price_usd_hr"), SCOUT_MAX_PRICE_USD_HR))
    pool_order = merged.get("pool_order")
    merged["pool_order"] = [pool for pool in pool_order if pool in SCOUT_POOL_ORDER] if isinstance(pool_order, list) else list(SCOUT_POOL_ORDER)
    if not merged["pool_order"]:
        merged["pool_order"] = list(SCOUT_POOL_ORDER)
    pool_switch_mode = str(merged.get("pool_switch_mode") or "single_pool").strip().lower()
    merged["pool_switch_mode"] = pool_switch_mode if pool_switch_mode in SCOUT_POOL_SWITCH_MODES else "single_pool"
    allowed_gpu_models = merged.get("allowed_gpu_models")
    if isinstance(allowed_gpu_models, str):
        allowed_gpu_models = allowed_gpu_models.split(",")
    if not isinstance(allowed_gpu_models, list):
        allowed_gpu_models = list(SCOUT_ALLOWED_GPU_MODELS)
    merged["allowed_gpu_models"] = [
        normalize_gpu_name(item)
        for item in allowed_gpu_models
        if normalize_gpu_name(item)
    ]
    return merged


def normalize_trigger_gpu(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return normalize_gpu_name(text) or ""


def allowed_gpu_models(settings_value: dict[str, Any] | None = None) -> list[str]:
    raw = (settings_value or {}).get("allowed_gpu_models")
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        raw = list(SCOUT_ALLOWED_GPU_MODELS)
    return [normalize_gpu_name(item) for item in raw if normalize_gpu_name(item)]


def allowlist_reason(settings_value: dict[str, Any] | None = None) -> str:
    models = allowed_gpu_models(settings_value)
    label = ", ".join(models) if models else "sem restricao"
    return f"fora do allowlist Scout {label}"


def gpu_allowed(item: dict[str, Any], settings_value: dict[str, Any] | None = None) -> bool:
    models = allowed_gpu_models(settings_value)
    if not models:
        return True
    gpu = normalize_gpu_name(item.get("gpu") or item.get("gpu_model_normalized") or item.get("gpu_model_raw"))
    return bool(gpu and gpu in models)


def results_manual_allowlist_bypass(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(
        item.get("source") == "results"
        and item.get("allowlist_bypass")
        and item.get("manual_override")
    )


def gpu_allowlist_block_reason(item: dict[str, Any], settings_value: dict[str, Any] | None = None) -> str:
    if results_manual_allowlist_bypass(item):
        return ""
    return "" if gpu_allowed(item, settings_value) else allowlist_reason(settings_value)


def mark_allowlist_blocked(item: dict[str, Any], settings_value: dict[str, Any]) -> bool:
    reason = gpu_allowlist_block_reason(item, settings_value)
    if not reason:
        return False
    changed = False
    for key in (
        "transient_unavailable",
        "next_retry_at",
        "retry_attempts",
        "retry_started_at",
        "retry_until_at",
        "last_retry_at",
    ):
        if item.get(key):
            item[key] = False if key == "transient_unavailable" else 0
            changed = True
    if item.get("queue_status") not in {"blocked", "rented"}:
        item["queue_status"] = "blocked"
        changed = True
    if item.get("skip_reason") != reason:
        item["skip_reason"] = reason
        changed = True
    if item.get("sniper_status"):
        item["sniper_status"] = ""
        changed = True
    return changed
