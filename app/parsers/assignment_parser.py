"""Assignment parsing: raw DOM/API records -> normalized assignment dicts (§12)."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from app.parsers.deadline_parser import extract_deadline_from_text, parse_deadline
from app.parsers.subject_parser import extract_portal_id_from_url
from app.utils import hashing


def normalize_assignment(raw: dict, subject_portal_id: str, tz: ZoneInfo) -> dict | None:
    """Normalize one raw assignment record.

    Expected raw keys:
        title (str), url (str|None), portal_id (str|None),
        description (str|None), deadline_text (str|None),
        deadline_iso (str|None, ISO-8601 from the portal API), status (str|None)
    """
    title = (raw.get("title") or "").strip()
    if not title:
        return None
    title = re.sub(r"\s+", " ", title)

    url = raw.get("url")
    portal_id = raw.get("portal_id") or extract_portal_id_from_url(url)

    deadline = _parse_iso_deadline(raw.get("deadline_iso"), tz)
    if deadline is None:
        deadline = parse_deadline(raw.get("deadline_text"), tz)
    if deadline is None:
        deadline = extract_deadline_from_text(raw.get("description"), tz)

    # Storage convention: naive wall-time in the configured timezone (SQLite
    # DateTime columns drop tzinfo anyway, and change_detector compares DB
    # values against incoming ones, so both sides must be normalized here).
    if deadline is not None:
        deadline = deadline.astimezone(tz).replace(tzinfo=None)

    if portal_id:
        external_key = hashing.sha256_text(f"{subject_portal_id}|{portal_id}")
    elif url:
        external_key = hashing.sha256_text(f"{subject_portal_id}|url|{url}")
    else:
        # Identity fallback per §12: subject + title + deadline.
        external_key = hashing.fallback_external_key(subject_portal_id, title, deadline)

    payload = {
        "title": title,
        "deadline": deadline.isoformat() if deadline else None,
        "description": (raw.get("description") or "").strip() or None,
        "status": (raw.get("status") or "PENDING").strip().upper(),
    }

    return {
        "portal_id": portal_id,
        "external_key": external_key,
        "title": title,
        "description": payload["description"],
        "assigned_at": None,
        "deadline": deadline,
        "status": payload["status"],
        # Preserve the actual document URL when PDF enrichment or document
        # tracking supplied one; fall back to the classroom URL.
        "source_url": raw.get("source_url") or url,
        "content_hash": hashing.content_hash(payload),
    }


def _parse_iso_deadline(value: str | None, tz: ZoneInfo) -> datetime | None:
    """Parse an ISO-8601 timestamp (e.g. '2026-09-04T08:11:32.075Z') into tz."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)
