"""PDF deadline extraction (design doc §17, Phase 8).

Activated because real portal testing proved page metadata is insufficient for
document-type classwork: faculty upload assignment PDFs that carry no due date
in the portal API. Preferred order (per design doc):

    1. Read metadata from the assignment webpage     <- implemented (API)
    2. Read PDF text directly                        <- implemented here
    3. OCR for image-based PDFs                      <- not implemented

Extraction pipeline:
    PDF bytes -> pypdf text -> collapse whitespace
      -> find date/date-time candidates
      -> score each by deadline-keyword proximity ("Due Date", "Deadline",
         "Submit by", ...) and explicit time-of-day
      -> return the best candidate with a confidence score, or None when
         nothing reliable (below RELIABLE_CONFIDENCE) is found -> caller
         keeps the deadline as N/A.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from app.parsers.deadline_parser import parse_deadline

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
)
WEAK_KEYWORDS = (
    "due",
    "submit",
    "submission",
    "on or before",
)

# Proximity window (characters) searched for keywords around each date.
WINDOW_BEFORE = 150
WINDOW_AFTER = 60

# Max pages parsed from a PDF (bound the work for large files).
MAX_PAGES = 15

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


def _keyword_score(window: str) -> float:
    """Score a date's surrounding window by deadline-keyword presence."""
    for keyword in STRONG_KEYWORDS:
        if keyword in window:
            return 0.85
    for keyword in WEAK_KEYWORDS:
        if keyword in window:
            return 0.60
    return 0.40  # a bare date with no deadline wording


def analyse_text_for_deadline(text: str | None, tz: ZoneInfo) -> PdfDeadlineMatch | None:
    """Find the most reliable deadline mention in free text."""
    if not text:
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return None

    best: tuple[float, int, datetime, str] | None = None
    for match in DATE_PATTERN.finditer(collapsed):
        raw_date = match.group(0)
        deadline = parse_deadline(raw_date, tz)
        if deadline is None:
            continue

        start = max(0, match.start() - WINDOW_BEFORE)
        end = min(len(collapsed), match.end() + WINDOW_AFTER)
        window = collapsed[start:end]

        confidence = _keyword_score(window.lower())
        if _TIME_HINT.search(raw_date):
            confidence = min(1.0, confidence + 0.05)

        # Storage convention: naive wall-time in the configured timezone.
        if deadline.tzinfo is not None:
            deadline = deadline.astimezone(tz).replace(tzinfo=None)

        candidate = (confidence, -match.start(), deadline, window.strip())
        if best is None or candidate[:2] > best[:2]:
            best = candidate

    if best is None or best[0] < RELIABLE_CONFIDENCE:
        return None
    return PdfDeadlineMatch(deadline=best[2], confidence=best[0], snippet=best[3])


def extract_deadline_from_pdf(pdf_bytes: bytes, tz: ZoneInfo) -> PdfDeadlineMatch | None:
    """Extract a deadline from PDF bytes, or None when nothing reliable is found."""
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception:
        return None  # encrypted/corrupt/non-PDF payloads
    return analyse_text_for_deadline(text, tz)

