"""Change detector: compare scraped assignments against stored state (§13)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.database.models import Assignment


@dataclass
class ChangeResult:
    is_new: bool = False
    deadline_changed: bool = False
    title_changed: bool = False
    content_changed: bool = False
    old_deadline: datetime | None = None
    new_deadline: datetime | None = None
    old_title: str | None = None
    new_title: str | None = None
    existing: Assignment | None = field(default=None, repr=False)

    @property
    def has_changes(self) -> bool:
        return self.is_new or self.deadline_changed or self.title_changed or self.content_changed


def compare(incoming: dict, existing: Assignment | None) -> ChangeResult:
    """Compare a normalized assignment dict with the stored record.

    Rules (§13):
      - external_key not in DB            -> new assignment
      - old_deadline != new_deadline      -> deadline changed
      - title changed                     -> title changed
      - content_hash changed              -> content changed (update, notify only
                                             when deadline/title changed)
      - otherwise                         -> unchanged (update last_seen_at only)
    """
    if existing is None:
        return ChangeResult(
            is_new=True,
            new_deadline=incoming.get("deadline"),
            new_title=incoming.get("title"),
        )

    result = ChangeResult(
        existing=existing, old_title=existing.title, new_title=incoming.get("title")
    )
    result.old_deadline = existing.deadline
    result.new_deadline = incoming.get("deadline")

    if result.old_deadline != result.new_deadline:
        result.deadline_changed = True

    if (existing.title or "").strip() != (incoming.get("title") or "").strip():
        result.title_changed = True

    new_hash = incoming.get("content_hash")
    if new_hash and existing.content_hash and new_hash != existing.content_hash:
        result.content_changed = True

    return result
