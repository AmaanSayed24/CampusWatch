"""PDF deadline extraction (design doc §17, Phase 8).

Activated because real portal testing proved page metadata is insufficient for
document-type classwork: faculty upload assignment PDFs that carry no due date
in the portal API. Preferred order (per design doc):

    1. Read metadata from the assignment webpage     <- implemented (API)
    2. Read PDF text directly                        <- implemented here
    3. OCR for image-based PDFs                      <- not implemented

Extraction pipeline:
    PDF bytes -> pypdf text -> collapse whitespace
      -> (no text? -> OCR the page images: record sheets are scanned
          pictures with no text layer)
      -> find date/date-time candidates
      -> score each by deadline-keyword proximity ("Due Date", "Deadline",
         "Submit by", ...) and explicit time-of-day
      -> return the best candidate with a confidence score, or None when
         nothing reliable (below RELIABLE_CONFIDENCE) is found -> caller
         keeps the deadline as N/A.

Record-sheet disambiguation: tables often carry BOTH an "Assignment given
date" and an "Assignment submission end date" column, with the two dates
side by side in the row. A date whose nearest preceding marker is a "given"
marker is not a deadline (confidence 0.35); when equally scored dates sit
next to each other (same table row), the later one wins — the submission
end date is chronologically after the given date.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from app.ocr import ocr_engines_available, ocr_image_bytes
from app.parsers.deadline_parser import parse_deadline

logger = logging.getLogger(__name__)

# Bump when extraction logic improves (formats, keywords, scoring): cached
# results produced by an older version are re-analysed on the next sync.
# 3 = OCR layer for image PDFs + record-sheet date disambiguation.
PARSER_VERSION = 3

# Confidence at or above this is treated as a reliable deadline; anything
# below yields no deadline (N/A) for the assignment.
RELIABLE_CONFIDENCE = 0.6

# Keyword strength tiers, checked in a proximity window around each date.
STRONG_KEYWORDS = (
    "due date",
    "deadline",
    "submission deadline",
    "last date",
    "last date of submission",
    "submit by",
    "submit on or before",
    "submit before",
    "to be submitted by",
    "due on",
    "submission end date",
    "end date",
    "submission date",
)
WEAK_KEYWORDS = (
    "due",
    "submit",
    "submission",
    "on or before",
)
# Markers naming a NON-deadline date (e.g. the "Assignment given date"
# column of a record sheet). When the closest preceding marker is one of
# these, the date is capped below RELIABLE_CONFIDENCE.
NEGATIVE_KEYWORDS = (
    "given date",
    "date given",
    "assigned on",
    "issued on",
    "start date",
)

# Proximity window (characters) searched for keywords around each date.
WINDOW_BEFORE = 150
WINDOW_AFTER = 60

# Dates this close together (characters) are treated as one table row; when
# they carry the same score, the later date wins (submission end > given).
CLUSTER_GAP_CHARS = 60

# Max pages parsed from a PDF (bound the work for large files).
MAX_PAGES = 15

# A page with fewer extracted characters than this is considered to have no
# usable text layer (scanned image) and is sent to OCR.
THIN_PAGE_CHARS = 30

# Bound OCR work per PDF.
MAX_OCR_PAGES = 5

# Date / date-time patterns understood by deadline_parser, plus ISO dates.
DATE_PATTERN = re.compile(
    r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap][Mm])?)?"
    r"|\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}"
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
)

_TIME_HINT = re.compile(r"\d{1,2}:\d{2}")


@dataclass(frozen=True)
class PdfDeadlineMatch:
    """A deadline extracted from PDF text with its reliability score."""

    deadline: datetime  # naive wall-time in the configured timezone
    confidence: float  # 0.0 .. 1.0
    snippet: str  # surrounding text, for human verification


def extract_pdf_text(pdf_bytes: bytes, max_pages: int = MAX_PAGES) -> str:
    """Extract text from the first `max_pages` pages of a PDF."""
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue  # a broken page must not sink the whole extraction
    return "\n".join(parts)


def _keyword_score(window: str) -> tuple[float, int]:
    """Score a date's surrounding window by deadline-keyword presence.

    Returns (score, marker_position): `marker_position` is the character
    offset of the strongest marker inside the window (-1 = none), used by
    the same-row disambiguation to tell an "Assignment given date" column
    from a "submission end date" column.
    """
    lowered = window.lower()
    best_score, best_pos = 0.40, -1
    for keywords, score in (
        (STRONG_KEYWORDS, 0.85),
        (WEAK_KEYWORDS, 0.60),
        (NEGATIVE_KEYWORDS, 0.35),
    ):
        for keyword in keywords:
            position = lowered.rfind(keyword)
            if position >= 0 and (score, position) > (best_score, best_pos):
                best_score, best_pos = score, position
    return best_score, best_pos


def _disambiguate_row_dates(candidates: list[dict], collapsed: str) -> list[dict]:
    """Resolve dates that share one table row (record-sheet pattern).

    A row  | 21-09-2026 | 27-09-2026 |  under  "Assignment given date" /
    "Assignment submission end date"  headers extracts as two dates a few
    characters apart (in OCR text the headers sit ABOVE the values). Rules:
      - when two unmarked dates sit close together with a given/submission
        header pair nearby, the LATER date is the deadline;
      - when two same-row dates carry the same score, the later date wins;
      - a date whose nearest marker is a "given"-type marker is demoted;
      - a date following a "given date" marker with a "submission end date"
        marker later is the deadline (later date).
    """
    resolved = [dict(c) for c in candidates]

    # Rule: unmarked adjacent dates with a "given"/"submission end" pair ->
    # later date is the deadline.
    unmarked = [
        c for c in resolved if c["marker_pos"] < 0 and c["score"] == 0.40
    ]
    sorted_unmarked = sorted(unmarked, key=lambda c: c["match_start"])
    for left, right in zip(sorted_unmarked, sorted_unmarked[1:]):
        if right["match_start"] - left["match_start"] > CLUSTER_GAP_CHARS:
            continue  # not in one row
        extended = left["snippet"] + " " + right["snippet"]
        lowered = extended.lower()
        has_pair = "given date" in lowered and (
            "submission end date" in lowered or "end date" in lowered
        )
        if not has_pair:
            continue
        left["score"] = 0.35
        right["score"] = 0.85

    resolved.sort(key=lambda c: c["match_start"])  # document order
    for i in range(1, len(resolved)):
        prev, curr = resolved[i - 1], resolved[i]
        if curr["match_start"] - prev["match_start"] > CLUSTER_GAP_CHARS:
            continue  # different rows

        # Record-sheet pair: "given" marker before/preceding the first date
        # and "submission end date" marker on/after the second date -> the
        # second (later) date is the deadline.
        prev_window = prev["snippet"].lower()
        curr_window = curr["snippet"].lower()
        mid = max(0, prev["match_start"] + len(prev["snippet"]) + 20)
        if (
            "given date" in prev_window
            and (
                "submission end date" in curr_window
                or "submission end date" in collapsed[mid:curr["match_start"]].lower()
            )
            and curr["score"] >= prev["score"]
        ):
            prev["score"] = min(prev["score"], 0.35)
            continue

        # Same row: prefer the date whose column marker sits further right
        # ("end date" column) — that is the deadline, demote the other.
        if curr["marker_pos"] > prev["marker_pos"] and curr["score"] >= prev["score"]:
            prev["score"] = min(prev["score"], 0.35)
        elif prev["marker_pos"] > curr["marker_pos"] and prev["score"] >= curr["score"]:
            curr["score"] = min(curr["score"], 0.35)
        elif curr["score"] == prev["score"] and curr["score"] >= RELIABLE_CONFIDENCE:
            prev["score"] = 0.35
    return resolved


def analyse_text_for_deadline(text: str | None, tz: ZoneInfo) -> PdfDeadlineMatch | None:
    """Find the most reliable deadline mention in free text."""
    if not text:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return None

    candidates: list[dict] = []
    for match in DATE_PATTERN.finditer(collapsed):
        raw_date = match.group(0)
        deadline = parse_deadline(raw_date, tz)
        if deadline is None:
            continue

        start = max(0, match.start() - WINDOW_BEFORE)
        end = min(len(collapsed), match.end() + WINDOW_AFTER)
        window = collapsed[start:end]

        score, marker_pos = _keyword_score(window)
        if _TIME_HINT.search(raw_date):
            score = min(1.0, score + 0.05)

        # Storage convention: naive wall-time in the configured timezone.
        if deadline.tzinfo is not None:
            deadline = deadline.astimezone(tz).replace(tzinfo=None)

        candidates.append(
            {
                "score": score,
                "marker_pos": marker_pos,
                "match_start": match.start(),
                "deadline": deadline,
                "snippet": window.strip(),
            }
        )

    candidates = _disambiguate_row_dates(candidates, collapsed)

    best = max(candidates, key=lambda c: (c["score"], -c["match_start"]), default=None)
    if best is None or best["score"] < RELIABLE_CONFIDENCE:
        return None
    return PdfDeadlineMatch(
        deadline=best["deadline"], confidence=best["score"], snippet=best["snippet"]
    )


def _ocr_text_layers(pdf_bytes: bytes, max_pages: int = MAX_OCR_PAGES) -> str:
    """Extract text from an image/no-text-layer PDF.

    Two strategies, in order:
      1. OCR the embedded page images directly (scanned pictures) via the
         configured engine.
      2. Rasterize each page (pypdfium2) and OCR the pixels — covers record
         sheets whose table text was converted to VECTOR OUTLINES (glyphs as
         filled paths) rather than stored as an image, which is exactly what
         the Parul Software Engineering sheets are.

    Returns all recognized text; "" when nothing could be read.
    """
    engines = ocr_engines_available()
    if not engines:
        from app.ocr import _hint_unavailable

        _hint_unavailable()
        return ""

    parts: list[str] = []

    # Strategy 1: OCR embedded images.
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        reader = None

    if reader is not None:
        for page in reader.pages[:max_pages]:
            try:
                for image in page.images:
                    text = ocr_image_bytes(image.data)
                    if text:
                        parts.append(text)
            except Exception as exc:
                logger.debug("embedded-OCR page skipped: %s", exc)
                continue

    # Strategy 2: rasterize and OCR the rendered pixels.
    try:
        from pypdfium2 import PdfDocument
    except ImportError:
        pass  # optional fallback; skip if not installed
    else:
        try:
            out = BytesIO()
            out.write(pdf_bytes)
            out.seek(0)
            document = PdfDocument(out)
            for index in range(min(len(document), max_pages)):
                page = document[index]
                try:
                    image = page.render(scale=3.0).to_pil()
                    buffer = BytesIO()
                    image.convert("RGB").save(buffer, format="JPEG", quality=95)
                    text = ocr_image_bytes(buffer.getvalue())
                    if text:
                        parts.append(text)
                except Exception as exc:
                    logger.debug("rasterize-OCR page skipped: %s", exc)
                    continue
        except Exception as exc:
            logger.debug("pypdfium2 rasterization failed: %s", exc)

    return "\n".join(part for part in parts if part)


def extract_deadline_from_pdf(pdf_bytes: bytes, tz: ZoneInfo) -> PdfDeadlineMatch | None:
    """Extract a deadline from PDF bytes, or None when nothing reliable is found.

    Two extraction layers (design doc §17):
      1. pypdf text layer — plain question papers and text record sheets.
      2. OCR of the page images — scanned record sheets (image-only pages).
    """
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception:
        return None  # encrypted/corrupt/non-PDF payloads

    if len(text.strip()) < THIN_PAGE_CHARS:
        # Image/vector-outline PDF: no usable text layer -> OCR the page.
        logger.info("PDF has no text layer (%d chars); trying OCR", len(text.strip()))
        ocr_text = _ocr_text_layers(pdf_bytes)
        if ocr_text.strip():
            text = ocr_text
            logger.info("OCR extracted %d chars from the PDF images", len(text))
    return analyse_text_for_deadline(text, tz)

