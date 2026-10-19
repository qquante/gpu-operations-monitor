import os
import time
from pathlib import Path
from typing import Any

from shared.gpu_hashrates import normalize_gpu_name
from state_store import archive_json, load_json_dict, load_json_list, save_json


SCOUT_HISTORY_PATH = Path(os.getenv("SCOUT_HISTORY_PATH", "data/scout_history.json"))
SCOUT_MACHINE_INDEX_PATH = Path(os.getenv("SCOUT_MACHINE_INDEX_PATH", "data/scout_machine_index.json"))


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


def history_items() -> list[dict[str, Any]]:
    return load_json_list(SCOUT_HISTORY_PATH)


def save_history(items: list[dict[str, Any]]) -> None:
    save_json(SCOUT_HISTORY_PATH, items[:500], indent=2)


def archive_history(items: list[dict[str, Any]] | None = None) -> str:
    current = history_items() if items is None else items
    return archive_json(SCOUT_HISTORY_PATH.parent, SCOUT_HISTORY_PATH.stem, current)


def machine_key(machine_id: Any, host_id: Any, gpu: Any, gpu_count: Any) -> str:
    machine = str(machine_id or "").strip()
    host = str(host_id or "").strip()
    gpu_name = str(gpu or "").strip().lower()
    count = str(max(1, safe_int(gpu_count, 1)))
    if not machine or not host or not gpu_name:
        return ""
    return "|".join((machine, host, gpu_name, count))


def machine_key_from_item(item: dict[str, Any]) -> str:
    return machine_key(item.get("machine_id"), item.get("host_id"), item.get("gpu"), item.get("gpu_count"))


def same_hardware(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_key = machine_key_from_item(left)
    right_key = machine_key_from_item(right)
    if left_key and right_key and left_key == right_key:
        return True
    left_machine = str(left.get("machine_id") or "")
    right_machine = str(right.get("machine_id") or "")
    if left_machine and right_machine and left_machine == right_machine:
        return True
    left_host = str(left.get("host_id") or "")
    right_host = str(right.get("host_id") or "")
    if not left_host or not right_host or left_host != right_host:
        return False
    return (
        normalize_gpu_name(left.get("gpu")) == normalize_gpu_name(right.get("gpu"))
        and max(1, safe_int(left.get("gpu_count"), 1)) == max(1, safe_int(right.get("gpu_count"), 1))
    )


def machine_index_payload() -> dict[str, Any]:
    payload = load_json_dict(SCOUT_MACHINE_INDEX_PATH, {"machines": {}})
    if isinstance(payload, dict) and isinstance(payload.get("machines"), dict):
        return payload
    if isinstance(payload, dict):
        return {"machines": payload}
    return {"machines": {}}


def touch_machine_index(
    index: dict[str, Any],
    item: dict[str, Any],
    status: str,
    *,
    result: dict[str, Any] | None = None,
) -> tuple[bool, bool, dict[str, Any]]:
    key = machine_key_from_item(item)
    if not key:
        return False, False, {}
    current = now_ts()
    existed = key in index
    record = index.get(key) if isinstance(index.get(key), dict) else {}
    if not record:
        record = {
            "machine_key": key,
            "machine_id": item.get("machine_id"),
            "host_id": item.get("host_id"),
            "gpu": item.get("gpu"),
            "gpu_count": item.get("gpu_count"),
            "first_seen_at": current,
            "first_ask_id": item.get("ask_id") or item.get("id"),
        }
    record.update({
        "last_seen_at": current,
        "last_ask_id": item.get("ask_id") or item.get("id"),
        "last_price_usd_hr": item.get("price_usd_hr"),
        "last_status": status,
    })
    if status == "sniped" and not record.get("sniped_at"):
        record["sniped_at"] = current
    if result:
        record.update({
            "tested_at": result.get("ended_at") or current,
            "last_decision": result.get("decision"),
            "last_reason": result.get("reason"),
            "best_profit_usd_hr": result.get("profit_usd_hr"),
            "best_hash_ratio": result.get("hash_ratio"),
        })
    changed = record != index.get(key)
    index[key] = record
    return existed, changed, record


def machine_index_items() -> dict[str, Any]:
    payload = machine_index_payload()
    data = payload.get("machines") if isinstance(payload.get("machines"), dict) else {}
    if data:
        return data
    backfilled: dict[str, Any] = {}
    for item in history_items():
        if isinstance(item, dict):
            touch_machine_index(backfilled, item, "tested", result=item)
            for result in item.get("prior_results") or []:
                if isinstance(result, dict):
                    touch_machine_index(backfilled, result, "tested", result=result)
    return backfilled


def save_machine_index(items: dict[str, Any], baseline_at: float | None = None) -> None:
    existing = machine_index_payload()
    if baseline_at is None:
        baseline_at = safe_float(existing.get("baseline_at"))
    payload = {"machines": items, "updated_at": now_ts()}
    if baseline_at:
        payload["baseline_at"] = baseline_at
    save_json(SCOUT_MACHINE_INDEX_PATH, payload, indent=2)


def append_history(result: dict[str, Any]) -> None:
    items = history_items()
    items.insert(0, result)
    save_history(items)
    index = machine_index_items()
    _, changed, _ = touch_machine_index(index, result, "tested", result=result)
    if changed:
        save_machine_index(index)
