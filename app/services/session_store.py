# app/services/session_store.py
import os, shutil
from pathlib import Path

SESSIONS_DIR = os.getenv("SESSIONS_DIR", ".sessions")

async def tag_session_by_phone(session_path: str, phone: str, user_id: str) -> str:
    Path(SESSIONS_DIR).mkdir(parents=True, exist_ok=True)
    safe_phone = "".join(ch for ch in phone if ch.isdigit() or ch in "+")
    target = os.path.join(SESSIONS_DIR, f"{safe_phone or 'unknown'}__{user_id or 'uid'}.session")
    if session_path != target:
        shutil.copy2(session_path, target)  # keep original too; or use move() if you prefer
    return target
