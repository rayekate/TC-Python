#!/usr/bin/env python3
from __future__ import annotations
import argparse
import asyncio
import os
import sys
import time
import zipfile
import shutil
from pathlib import Path
from typing import List, Optional

# Load .env from project root if present (script lives in app/routers/)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

# ---------- project root & dir resolvers ----------
def _repo_root() -> Path:
    # app/routers/export_and_send.py -> parents[2] == project root
    return Path(__file__).resolve().parents[2]

def _resolve_dir(env_name: str, default_rel: str) -> Path:
    raw = os.getenv(env_name, default_rel)
    p = Path(raw)
    if not p.is_absolute():
        p = _repo_root() / raw  # anchor relative env values to project root
    return p.resolve()

def env_sessions_dir() -> Path:
    return _resolve_dir("SESSIONS_DIR", ".sessions")

def env_tdata_dir() -> Path:
    return _resolve_dir("TDATA_DIR", ".tdata")

def env_exports_dir() -> Path:
    return _resolve_dir("EXPORTS_DIR", ".exports")

def env_bot_token() -> str:
    return os.getenv("BOT_TOKEN", "715674815ef1b33e1d3c0479caa7972e")

def env_default_chat_id() -> str:
    return os.getenv("AUTO_SEND_CHAT_ID", "")

# ---------- opentele conversion ----------
class TDataError(RuntimeError):
    pass

async def session_to_tdata(session_path: Path, profile_root: Path) -> Path:
    try:
        from opentele.tl import TelegramClient  # type: ignore
        from opentele.api import UseCurrentSession  # type: ignore
    except Exception as e:
        raise TDataError(
            "opentele import failed. Use Python 3.12 and `pip install opentele`.\n"
            f"Import error: {e}"
        )

    if not session_path.is_file():
        raise TDataError(f"Session file not found: {session_path}")

    profile_root.mkdir(parents=True, exist_ok=True)
    tgt_dot = profile_root / "tdata"
    tgt_plain = profile_root / "tdata"
    if tgt_dot.exists():
        shutil.rmtree(tgt_dot, ignore_errors=True)
    if tgt_plain.exists():
        shutil.rmtree(tgt_plain, ignore_errors=True)

    try:
        client = TelegramClient(str(session_path))
        tdesk = await client.ToTDesktop(flag=UseCurrentSession)  # type: ignore
        tdesk.SaveTData(str(tgt_dot))
    except Exception as e:
        raise TDataError(f"tdata export failed: {e}")

    if tgt_dot.exists():
        return tgt_dot
    if tgt_plain.exists():
        return tgt_plain
    # Hard fail with context
    contents = [p.name for p in profile_root.glob("*")]
    raise TDataError(f"No tdata created under {profile_root}. Contents: {contents}")

# ---------- zipping ----------
def make_zip(paths: List[Path], zip_path: Path) -> int:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in paths:
            p = Path(p)
            if not p.exists():
                continue
            if p.is_file():
                zf.write(str(p), arcname=p.name)
            else:
                root_name = p.name
                for child in p.rglob("*"):
                    if child.is_dir():
                        continue
                    arcname = Path(root_name) / child.relative_to(p)
                    zf.write(str(child), arcname=str(arcname))
    return zip_path.stat().st_size

# ---------- bot upload ----------
def send_zip_via_bot(zip_path: Path, chat_id: str, caption: Optional[str] = None) -> dict:
    token = env_bot_token()
    if not token:
        raise RuntimeError("BOT_TOKEN missing. Set it in .env or environment.")
    if not zip_path.is_file():
        raise RuntimeError(f"zip file not found: {zip_path}")

    import requests
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(zip_path, "rb") as f:
        files = {"document": (zip_path.name, f)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        r = requests.post(url, data=data, files=files, timeout=120)
    js = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not js.get("ok"):
        raise RuntimeError(f"sendDocument error: HTTP {r.status_code}, body={js or r.text}")
    return js

# ---------- session discovery ----------
def discover_sessions(sdir: Path, phone: Optional[str]) -> list[Path]:
    sdir = Path(sdir)
    if phone:
        candidate = sdir / f"{phone}.session"
        return [candidate] if candidate.exists() else []
    if not sdir.exists():
        return []
    return sorted(sdir.glob("*.session"))

# ---------- main workflow ----------
async def process_one(session_file: Path, tdata_root: Path, exports_root: Path) -> None:
    session_file = Path(session_file)
    phone = session_file.stem
    profile_root = Path(tdata_root) / phone

    print(f"\n=== {phone} ===")
    try:
        tdata_path = await session_to_tdata(session_file, profile_root)
        print(f"[ok] tdata at: {tdata_path}")
    except Exception as e:
        print(f"[ERR] convert: {e}")
        return

    ts = int(time.time())
    zip_path = Path(exports_root) / f"{phone}-{ts}.zip"
    size = make_zip([Path(tdata_path), session_file], zip_path)
    print(f"[ok] zipped: {zip_path} ({size} bytes)")

    chat_id = env_default_chat_id()
    if not chat_id:
        print("[WARN] DEFAULT_TARGET_CHAT_ID missing; set it in .env")
        return
    try:
        res = send_zip_via_bot(zip_path, chat_id, caption=f"{phone} • {zip_path.name}")
        mid = res.get("result", {}).get("message_id")
        print(f"[ok] sent to {chat_id} (message {mid})")
    except Exception as e:
        print(f"[ERR] send: {e}")

async def amain(args) -> None:
    if sys.version_info[:2] != (3, 12):
        print(f"[WARN] Detected Python {sys.version.split()[0]}; opentele prefers 3.12.", flush=True)

    sdir = env_sessions_dir()
    tdir = env_tdata_dir()
    edir = env_exports_dir()
    edir.mkdir(parents=True, exist_ok=True)

    print(f"[debug] sdir = {sdir}")
    print(f"[debug] exists = {sdir.exists()}")
    print(f"[debug] sessions = {[p.name for p in Path(sdir).glob('*.session')]}")

    sessions = discover_sessions(sdir, args.phone)
    if not sessions:
        if args.phone:
            print(f"[INFO] No session found for {args.phone} in {sdir}")
        else:
            print(f"[INFO] No sessions found in {sdir}")
        return

    print(f"[INFO] Found {len(sessions)} session(s) in {sdir}")
    for s in sessions:
        await process_one(s, tdir, edir)

def parse_args():
    p = argparse.ArgumentParser(description="Export .session -> .tdata, zip, and send via bot.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true", help="Process all <phone>.session files in SESSIONS_DIR")
    g.add_argument("--phone", type=str, help="Process only this phone (expects <phone>.session)")
    args = p.parse_args()
    if args.all:
        args.phone = None
    return args

def main():
    args = parse_args()
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")

if __name__ == "__main__":
    main()
