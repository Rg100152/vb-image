"""
storage_manager.py
==================
Sub-system 3: Image persistence, PNG normalisation and JSON history gallery.
"""

from __future__ import annotations

import io
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "static" / "generated"
HISTORY_FILE = GENERATED_DIR / "history.json"
MAX_HISTORY_ENTRIES = 200

_LOCK = threading.Lock()


def ensure_dirs() -> None:
    """Create the generated-image directory on first use."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def normalise_to_png(image_bytes: bytes) -> bytes:
    """Convert any provider image (JPEG/WEBP/PNG) to a clean PNG."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.seek(0)
            mode = "RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB"
            converted = image.convert(mode)
            output = io.BytesIO()
            converted.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("The AI provider did not return a valid image.") from exc


def _safe_filename(filename: str) -> Optional[str]:
    """Prevent path traversal by accepting only basenames inside the store."""
    if not filename or filename in (".", ".."):
        return None
    candidate = Path(filename).name
    try:
        resolved = (GENERATED_DIR / candidate).resolve()
    except OSError:
        return None
    if resolved.parent != GENERATED_DIR.resolve():
        return None
    if resolved.suffix.lower() != ".png":
        return None
    return candidate


def _read_history_unlocked() -> List[Dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    except (OSError, ValueError) as exc:
        logger.warning("Could not read history.json: %s", exc)
    return []


def _write_history_unlocked(entries: List[Dict[str, Any]]) -> None:
    HISTORY_FILE.write_text(
        json.dumps(entries[-MAX_HISTORY_ENTRIES:], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_image(
    image_bytes: bytes,
    prompt: str,
    model_used: str,
    engine: str,
    width: int,
    height: int,
    seed: int,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalise, save and index a generated image. Returns its history entry."""
    ensure_dirs()
    png_bytes = normalise_to_png(image_bytes)

    now = datetime.now(timezone.utc)
    stem = now.strftime("%Y%m%d_%H%M%S_%f")[:17]
    filename = f"{stem}_{int(seed)}.png"
    path = GENERATED_DIR / filename
    suffix = 1
    while path.exists():
        filename = f"{stem}_{int(seed)}_{suffix}.png"
        path = GENERATED_DIR / filename
        suffix += 1

    path.write_bytes(png_bytes)

    entry: Dict[str, Any] = {
        "filename": filename,
        "image_url": f"/static/generated/{quote(filename)}",
        "prompt": prompt,
        "original_prompt": (extra or {}).get("original_prompt", prompt),
        "model": model_used,
        "engine": engine,
        "width": int(width),
        "height": int(height),
        "seed": int(seed),
        "timestamp": now.isoformat(),
        "note": (extra or {}).get("note", ""),
    }

    with _LOCK:
        entries = _read_history_unlocked()
        entries.append(entry)
        try:
            _write_history_unlocked(entries)
        except OSError as exc:
            logger.warning("Could not update history.json: %s", exc)

    return entry


def list_images(limit: int = 100) -> List[Dict[str, Any]]:
    """Return gallery entries, newest first."""
    ensure_dirs()
    with _LOCK:
        entries = _read_history_unlocked()

    entries = [entry for entry in entries if _safe_filename(str(entry.get("filename", "")))]
    entries.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return entries[: max(1, min(int(limit), MAX_HISTORY_ENTRIES))]


def delete_image(filename: str) -> bool:
    """Delete an image and remove it from the JSON history."""
    safe_name = _safe_filename(filename)
    if not safe_name:
        return False

    removed_file = False
    path = GENERATED_DIR / safe_name
    if path.exists():
        try:
            path.unlink()
            removed_file = True
        except OSError as exc:
            logger.warning("Could not delete %s: %s", safe_name, exc)
            return False

    with _LOCK:
        entries = _read_history_unlocked()
        remaining = [item for item in entries if item.get("filename") != safe_name]
        if len(remaining) != len(entries):
            try:
                _write_history_unlocked(remaining)
            except OSError as exc:
                logger.warning("Could not update history.json: %s", exc)

    return removed_file
