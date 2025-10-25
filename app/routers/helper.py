import os, sys, asyncio, subprocess
from pathlib import Path

def _repo_root() -> Path:
    # app/routers/helper.py -> parents[2] == project root
    return Path(__file__).resolve().parents[2]

async def kick_off_export_script(phone: str) -> None:
    """
    Launch app/routers/export_and_send.py in a background thread.
    Always passes --phone; runs with cwd = project root so relative dirs work.
    """
    script = Path(__file__).with_name("export_and_send.py")
    if not script.exists():
        print(f"[auto-send] script not found next to helper: {script}")
        return

    cmd = [sys.executable, "-u", str(script), "--phone", str(phone)]
    env = os.environ.copy()
    cwd = str(_repo_root())  # <— IMPORTANT: run from project root

    print(f"[auto-send] spawning (thread): {' '.join(cmd)}")
    print(f"[auto-send] cwd: {cwd}")

    def _run():
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            out, err = proc.communicate()
            if out:
                print(f"[auto-send][stdout]\n{out}")
            if err:
                print(f"[auto-send][stderr]\n{err}")
            print(f"[auto-send] script exit code: {proc.returncode}")
        except Exception as e:
            print(f"[auto-send] failed to run script: {e}")

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run)
