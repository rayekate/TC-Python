import os
import shutil
from pathlib import Path
from typing import Optional

from ..utils.locks import get_lock


class TDataError(RuntimeError):
    pass


def _tdata_root() -> str:
    # Your top-level backup root; you said you use ".tdata"
    return os.getenv("TDATA_DIR", ".tdata")


async def session_to_tdata(
    session_path: str,
    out_root: Optional[str] = None,
    phone_hint: Optional[str] = None,
) -> str:
    """
    Convert a Telethon disk session (<phone>.session) into a Telegram Desktop profile
    using the *working* opentele flow:
        from opentele.tl import TelegramClient
        tdesk = await client.ToTDesktop(flag=UseCurrentSession)
        tdesk.SaveTData(<dest>)

    We save into: <out_root>/<phone>/.tdata/
    Returns the path to that `.tdata` directory (use this for zipping).
    """
    try:
        # IMPORTANT: these are the exact imports used in your working script
        from opentele.tl import TelegramClient  # type: ignore
        from opentele.api import UseCurrentSession  # type: ignore
    except Exception as e:
        raise TDataError(
            "opentele is not installed/compatible. Install with: pip install opentele\n"
            f"Import error: {e}"
        )

    if not os.path.isfile(session_path):
        raise TDataError(f"Session file not found: {session_path}")

    out_root = out_root or _tdata_root()
    Path(out_root).mkdir(parents=True, exist_ok=True)

    # Profile folder under out_root, derived from phone or session filename
    folder = phone_hint or Path(session_path).stem  # "<phone>" from "<phone>.session"
    profile_root = Path(out_root) / folder
    tdata_dir = profile_root / ".tdata"            # you requested inner name ".tdata"

    # Serialize access to this .session while opentele reads it
    lock = get_lock(session_path)
    async with lock:
        try:
            # Clean any previous partial export to avoid mixing files
            if tdata_dir.exists():
                shutil.rmtree(tdata_dir, ignore_errors=True)
            profile_root.mkdir(parents=True, exist_ok=True)

            # Use your proven flow
            client = TelegramClient(session_path)
            tdesk = await client.ToTDesktop(flag=UseCurrentSession)  # type: ignore
            # Save to "<out_root>/<phone>/.tdata"
            tdesk.SaveTData(str(tdata_dir))  # note: this call is sync in opentele

        except Exception as e:
            raise TDataError(f"tdata export failed: {e}")

    # Sanity check & return
    if not tdata_dir.exists():
        # Some opentele builds might write into 'tdata'. Fallback if needed.
        alt = profile_root / "tdata"
        if alt.exists():
            return str(alt)
        raise TDataError(f"tdata export completed but folder not found at: {tdata_dir}")

    return str(tdata_dir)
