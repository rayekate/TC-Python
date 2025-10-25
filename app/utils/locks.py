import asyncio
from typing import Dict

# Simple in-process lock registry keyed by session_path
_LOCKS: Dict[str, asyncio.Lock] = {}

def get_lock(key: str) -> asyncio.Lock:
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock
