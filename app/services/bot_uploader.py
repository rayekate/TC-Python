import os
import requests
from typing import Optional


class BotUploadError(RuntimeError):
    pass


def send_zip_via_bot(zip_path: str, chat_id: str, caption: Optional[str] = None) -> dict:
    bot_token = os.getenv("BOT_TOKEN", "")  # read at call time (not at import)
    if not bot_token:
        raise BotUploadError("BOT_TOKEN is not set in the environment.")
    if not os.path.isfile(zip_path):
        raise BotUploadError(f"zip file not found: {zip_path}")

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    with open(zip_path, "rb") as f:
        files = {"document": (os.path.basename(zip_path), f)}
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        r = requests.post(url, data=data, files=files, timeout=120)
        js = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not js.get("ok"):
            raise BotUploadError(f"sendDocument error: HTTP {r.status_code}, body={js or r.text}")
        return js
