"""Hashing helpers for assignment identity and change detection (§12)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(payload: dict) -> str:
    """Stable hash of the meaningful assignment fields.

    Dicts are serialized with sorted keys so ordering never changes the hash.
    """
    normalized = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value
    serialized = json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)
    return sha256_text(serialized)


def fallback_external_key(subject_portal_id: str, title: str, deadline: datetime | None) -> str:
    """Identity fallback: subject + title + deadline (design doc §12, option 3)."""
    deadline_part = deadline.isoformat() if deadline else "no-deadline"
    return sha256_text(f"{subject_portal_id}|{title.strip().lower()}|{deadline_part}")
