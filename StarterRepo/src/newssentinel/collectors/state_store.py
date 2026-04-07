from __future__ import annotations

from collections import deque
import json
import logging
from pathlib import Path
import re

log = logging.getLogger("collectors_state_store")


def _collector_state_path(collector_name: str, state_dir: str) -> Path:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", collector_name)
    return Path(state_dir) / f"{safe_name}.json"


def _normalize_seen_order(seen_order: deque[str], max_cache_size: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in list(seen_order)[-max_cache_size:]:
        if not isinstance(key, str):
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def load_collector_seen_cache(
    collector_name: str,
    state_dir: str,
    max_cache_size: int,
) -> tuple[set[str], deque[str]]:
    path = _collector_state_path(collector_name, state_dir)
    if not path.exists():
        return set(), deque()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.exception("Failed reading collector state file: %s", path)
        return set(), deque()

    seen_order_raw = payload.get("seen_order", [])
    if not isinstance(seen_order_raw, list):
        return set(), deque()

    seen_order = deque()
    seen_ids = set()
    for key in seen_order_raw[-max_cache_size:]:
        if not isinstance(key, str):
            continue
        if key in seen_ids:
            continue
        seen_ids.add(key)
        seen_order.append(key)
    return seen_ids, seen_order


def save_collector_seen_cache(
    collector_name: str,
    seen_order: deque[str],
    state_dir: str,
    max_cache_size: int,
) -> None:
    path = _collector_state_path(collector_name, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "collector": collector_name,
        "seen_order": _normalize_seen_order(seen_order, max_cache_size=max_cache_size),
    }

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    tmp.replace(path)
