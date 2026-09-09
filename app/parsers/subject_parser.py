"""Subject parsing: raw portal data -> normalized subject dicts."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.utils import hashing


def extract_portal_id_from_url(
    url: str | None,
    param_names: tuple[str, ...] = ("id", "subject_id", "cid", "courseid"),
) -> str | None:
    """Try to pull a stable subject id out of a portal URL query string."""
    if not url:
        return None
    query = parse_qs(urlparse(url).query)
    for name in param_names:
        values = query.get(name)
        if values and values[0]:
            return values[0]
    return None


def normalize_subject(raw: dict) -> dict | None:
    """Normalize one raw subject record discovered on the classroom page.

    Expected raw keys: name (str), url (str|None), portal_id (str|None).
    Returns None when the record has no usable identity.
    """
    name = (raw.get("name") or "").strip()
    url = raw.get("url")
    portal_id = raw.get("portal_id") or extract_portal_id_from_url(url)

    if not name:
        return None
    if not portal_id:
        # Stable fallback identity: hashed name (+url).
        portal_id = hashing.sha256_text(f"subject|{name.lower()}|{url or ''}")[:16]

    return {
        "portal_id": portal_id,
        "name": re.sub(r"\s+", " ", name),
        "url": url,
    }
