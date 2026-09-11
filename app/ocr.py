"""OCR for image-based PDFs (design doc §17, step 3).

Faculty record sheets are frequently scanned or exported as a full-page
picture: the PDF has no text layer at all, so pypdf extracts zero characters
and deadline extraction has nothing to work with. This module adds OCR:

    1. winsdk  — Windows.Media.Ocr, the OCR engine built into Windows 10/11
                 (pure pip install, no external binaries). Preferred.
    2. pytesseract — Tesseract, used when the binary is installed.

Both are optional: when neither is available, callers get `None` and a clear
one-time log hint instead of a crash.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_HINT_SHOWN = False

# Common Tesseract install locations on Windows (checked when tesseract.exe
# is not on the PATH).
_TESSERACT_DIRS = (
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    r"C:\Tesseract-OCR",
)


def _tesseract_cmd() -> str | None:
    """Locate tesseract.exe, or None when it is not installed."""
    found = shutil.which("tesseract")
    if found:
        return found
    for directory in _TESSERACT_DIRS:
        candidate = rf"{directory}\tesseract.exe"
        try:
            subprocess.run(  # noqa: S603 - fixed arg, no shell
                [candidate, "--version"], capture_output=True, timeout=10
            )
            return candidate
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def ocr_engines_available() -> list[str]:
    """Names of the OCR engines usable on this machine."""
    engines: list[str] = []
    try:
        import winsdk  # noqa: F401

        engines.append("winsdk")
    except ImportError:
        pass
    if _tesseract_cmd() is not None:
        engines.append("tesseract")
    return engines


def _hint_unavailable() -> None:
    """Log the install hint once, not on every document."""
    global _HINT_SHOWN
    if not _HINT_SHOWN:
        _HINT_SHOWN = True
        logger.warning(
            "Image-based PDF found but no OCR engine is available. "
            "Install one: pip install winsdk  (Windows built-in OCR, no "
            "external binaries), or install Tesseract OCR and "
            "pip install pytesseract Pillow"
        )


def _run_winsdk(image_bytes: bytes) -> str | None:
    """OCR via the Windows built-in engine (Windows.Media.Ocr)."""
    try:
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    except ImportError:
        return None

    async def recognize() -> str:
        # Canonical pattern: a DataWriter over the stream converts Python
        # bytes into the WinRT IBuffer the decoder needs (write_async on the
        # raw output stream rejects plain bytes).
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(bytearray(image_bytes))
        await writer.store_async()
        await writer.flush_async()

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            # Fall back to any language pack that includes English.
            engine = OcrEngine.try_create_from_language(Language("en-US"))
        if engine is None:
            return ""
        result = await engine.recognize_async(bitmap)
        return result.text

    try:
        return asyncio.run(asyncio.wait_for(recognize(), timeout=120))
    except Exception:
        logger.debug("winsdk OCR failed", exc_info=True)
        return None


def _run_tesseract(image_bytes: bytes) -> str | None:
    """OCR via Tesseract (requires the tesseract binary)."""
    try:
        from io import BytesIO

        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    cmd = _tesseract_cmd()
    if cmd is None:
        return None
    pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        image = Image.open(BytesIO(image_bytes))
        return pytesseract.image_to_string(image)
    except Exception:
        logger.debug("tesseract OCR failed", exc_info=True)
        return None


def ocr_image_bytes(image_bytes: bytes) -> str | None:
    """OCR one image (PNG/JPEG bytes) with the first available engine."""
    for runner in (_run_winsdk, _run_tesseract):
        text = runner(image_bytes)
        if text:
            return text
    _hint_unavailable()
    return None
