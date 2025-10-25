import os
import zipfile
from pathlib import Path
from typing import Iterable, Tuple

def _iter_paths(root: str) -> Iterable[str]:
    root_path = Path(root)
    if root_path.is_file():
        yield str(root_path)
    else:
        for p in root_path.rglob("*"):
            yield str(p)

def make_zip(paths: list[str], zip_path: str) -> Tuple[str, int]:
    """
    Zip files/folders in `paths` into `zip_path`.
    Returns: (zip_path, size_bytes)
    """
    Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
    # Create zip; maintain relative names inside archive
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in paths:
            p_path = Path(p)
            if not p_path.exists():
                # Skip silently (or raise if you prefer strict behavior)
                continue
            if p_path.is_file():
                arcname = p_path.name
                zf.write(str(p_path), arcname)
            else:
                # Add the folder contents, preserving folder name as root
                for child in _iter_paths(str(p_path)):
                    child_path = Path(child)
                    if child_path.is_dir():
                        continue
                    arcname = str(child_path.relative_to(p_path.parent))
                    zf.write(str(child_path), arcname)
    size = os.path.getsize(zip_path)
    return zip_path, size
