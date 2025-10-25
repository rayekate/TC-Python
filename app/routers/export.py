from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
import os
import time
from pathlib import Path

from ..services.tdata import session_to_tdata, TDataError
from ..services.packer import make_zip
from ..services.bot_uploader import send_zip_via_bot, BotUploadError
from ..utils.locks import get_lock

router = APIRouter(prefix="/session/export", tags=["export"])


def _sessions_dir() -> str:
    return os.getenv("SESSIONS_DIR", ".sessions")


def _tdata_root() -> str:
    return os.getenv("TDATA_DIR", ".tdata")


def _exports_dir() -> str:
    return os.getenv("EXPORTS_DIR", ".exports")


def _session_path_for_phone(phone: str) -> str:
    phone = str(phone).strip()
    if not phone:
        raise ValueError("phone required")
    return str(Path(_sessions_dir()) / f"{phone}.session")


@router.post("/tdata")
async def export_tdata(req: Request):
    try:
        body = await req.json()
        phone = str(body.get("phone", "")).strip()
        if not phone:
            return JSONResponse({"ok": False, "error": "PHONE_REQUIRED"}, status_code=400)

        session_path = _session_path_for_phone(phone)
        tdata_path = await session_to_tdata(session_path, out_root=_tdata_root(), phone_hint=phone)

        size = 0
        for p in Path(tdata_path).rglob("*"):
            if p.is_file():
                size += p.stat().st_size

        return JSONResponse({"ok": True, "tdataPath": tdata_path, "bytes": size})
    except TDataError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e) or "TDATA_EXPORT_FAILED"}, status_code=500)


@router.post("/archive")
async def export_archive(req: Request):
    try:
        body = await req.json()
        phone = str(body.get("phone", "")).strip()
        include_session = bool(body.get("includeSession", False))
        if not phone:
            return JSONResponse({"ok": False, "error": "PHONE_REQUIRED"}, status_code=400)

        session_path = _session_path_for_phone(phone)

        # Always resolve the real data folder via converter
        tdata_path = await session_to_tdata(session_path, out_root=_tdata_root(), phone_hint=phone)

        ts = int(time.time())
        Path(_exports_dir()).mkdir(parents=True, exist_ok=True)
        zip_path = str(Path(_exports_dir()) / f"{phone}-{ts}.zip")

        paths = [tdata_path]
        if include_session:
            paths.append(session_path)

        zip_path, size = make_zip(paths, zip_path)
        return JSONResponse({"ok": True, "zipPath": zip_path, "size": size})
    except TDataError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e) or "ARCHIVE_FAILED"}, status_code=500)


@router.post("/send")
async def export_and_send(req: Request):
    try:
        body = await req.json()
        phone = str(body.get("phone", "")).strip()
        include_session = bool(body.get("includeSession", False))
        chat_id = str(body.get("chatId", "")).strip() or os.getenv("DEFAULT_TARGET_CHAT_ID", "")
        caption = body.get("caption")
        if not phone:
            return JSONResponse({"ok": False, "error": "PHONE_REQUIRED"}, status_code=400)
        if not chat_id:
            return JSONResponse({"ok": False, "error": "CHAT_ID_REQUIRED"}, status_code=400)

        session_path = _session_path_for_phone(phone)

        # Serialize conversion/zipping per session
        lock = get_lock(session_path)
        async with lock:
            tdata_path = await session_to_tdata(session_path, out_root=_tdata_root(), phone_hint=phone)

            ts = int(time.time())
            Path(_exports_dir()).mkdir(parents=True, exist_ok=True)
            zip_path = str(Path(_exports_dir()) / f"{phone}-{ts}.zip")

            paths = [tdata_path]
            if include_session:
                paths.append(session_path)

            zip_path, size = make_zip(paths, zip_path)

        res = send_zip_via_bot(zip_path, chat_id, caption=caption)
        msg = res.get("result", {})
        return JSONResponse({
            "ok": True,
            "zipPath": zip_path,
            "size": size,
            "chatId": msg.get("chat", {}).get("id", chat_id),
            "messageId": msg.get("message_id"),
        })
    except (TDataError, BotUploadError) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e) or "SEND_FAILED"}, status_code=500)


@router.get("/download")
async def download_zip(phone: str, ts: int):
    path = Path(_exports_dir()) / f"{phone}-{ts}.zip"
    if not path.exists():
        return JSONResponse({"ok": False, "error": "ZIP_NOT_FOUND"}, status_code=404)
    return FileResponse(str(path), media_type="application/zip", filename=path.name)
