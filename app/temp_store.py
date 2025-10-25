import time
from typing import Any, Dict

# super light in-memory store with 2-minute TTL safeguard
_STORE: Dict[str, Dict[str, Any]] = {}
_TTL_SECONDS = 60

def put_temp(key: str, value: Dict[str, Any]) -> None:
    _STORE[key] = {"value": value, "ts": time.time()}

def get_temp(key: str) -> Dict[str, Any] | None:
    item = _STORE.get(key)
    if not item:
        return None
    if time.time() - item["ts"] > _TTL_SECONDS:
        _STORE.pop(key, None)
        return None
    return item["value"]

def pop_temp(key: str) -> Dict[str, Any] | None:
    item = get_temp(key)
    if item is not None:
        _STORE.pop(key, None)
    return item