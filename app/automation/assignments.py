"""Assignment discovery inside a subject (§10).

The portal renders subject classwork from two encrypted API endpoints:
  GET /api/classroom-works/{subject_id}   (flat items)
  GET /api/classroom-topics/{subject_id}  (topics, each embedding `works`)
We visit the subject page, open its Classwork tab, capture both payloads and
normalize them into raw assignment records for the assignment parser.
"""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page

from app.automation.portal_api import ResponseCollector
from app.config.settings import Settings

logger = logging.getLogger(__name__)

# Only works that look like assignments are tracked (not lecture notes etc.).
ASSIGNMENT_TYPE = "assignment"
ASSIGNMENT_TITLE = re.compile(r"assign", re.IGNORECASE)


class AssignmentScraper:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def get_assignments(self, page: Page, subject: dict) -> list[dict]:
        """Visit a subject page and return raw assignment records.

        The Classwork payloads arrive as XHR responses which are occasionally
        missed (slow render / navigation race). When nothing was captured we
        retry the page load once before giving up for this subject.
        """
        subject_id = subject.get("portal_id")
        subject_url = subject.get("url")
        if not subject_id or not subject_url:
            return []

        works_url = f"/api/classroom-works/{subject_id}"
        topics_url = f"/api/classroom-topics/{subject_id}"

        attempts = 2
        for attempt in range(1, attempts + 1):
            works: dict[str, dict] = {}
            with ResponseCollector(page, (works_url, topics_url)) as collector:
                if attempt == 1:
                    await page.goto(subject_url, wait_until="domcontentloaded")
                else:
                    await page.reload(wait_until="domcontentloaded")
                try:
                    await page.get_by_text("Classwork", exact=False).first.click(timeout=8_000)
                except Exception:
                    logger.debug("Classwork tab click failed for %s", subject.get("name"))
                await page.wait_for_timeout(4_000)

                works_data = collector.decrypted(works_url)
                topics_data = collector.decrypted(topics_url)
                logger.debug(
                    "%s payloads (attempt %d): works=%s topics=%s",
                    subject.get("name"),
                    attempt,
                    "captured(%d items)" % len(works_data.get("items", []))
                    if works_data
                    else "none",
                    "captured(%d items)" % len(topics_data.get("items", []))
                    if topics_data
                    else "none",
                )
                for data in (works_data, topics_data):
                    if not data:
                        continue
                    for item in data.get("items", []):
                        # classroom-works items are the works themselves; topic items
                        # embed their works under `works`.
                        if "works" in item:
                            candidates = item.get("works") or []
                        else:
                            candidates = [item]
                        for work in candidates:
                            work_id = work.get("_id")
                            if work_id and not work.get("deleted"):
                                works[work_id] = work

            if works or attempt == attempts:
                break
            logger.warning(
                "No classwork payloads captured for %s; retrying page load",
                subject.get("name"),
            )
            await page.wait_for_timeout(3_000)

        records = [raw for raw in (self._to_raw(w, subject) for w in works.values()) if raw]
        logger.info("%s: %d assignments", subject.get("name"), len(records))
        return records

    def _to_raw(self, work: dict, subject: dict) -> dict | None:
        """Map one classwork item to a raw record, or None when not trackable."""
        title = re.sub(r"\s+", " ", work.get("title") or "").strip()
        if not title:
            return None

        work_type = (work.get("type") or "").lower()
        is_assignment = work_type == ASSIGNMENT_TYPE
        if not is_assignment and not ASSIGNMENT_TITLE.search(title):
            return None  # study material / notes -> not an assignment

        assignment_info = work.get("assignment") or {}
        deadline_iso = None
        if assignment_info.get("hasDueDate") and assignment_info.get("dueDateTime"):
            deadline_iso = assignment_info["dueDateTime"]

        status = "PENDING"
        track = work.get("trackAssignment") or {}
        if track.get("submittedAt") or track.get("status") == "ended":
            status = "SUBMITTED"

        document_url = work.get("document")
        source_url = (
            document_url if (document_url and not is_assignment) else subject.get("url")
        )
        description = f"Classwork item of type {work_type or 'unknown'}."
        points = assignment_info.get("point")
        if points is not None:
            description += f" Points: {points}."
        if work.get("taken") is not None:
            description += f" Taken: {work.get('taken')}."
        return {
            "title": title,
            "url": subject.get("url"),
            "portal_id": work.get("_id"),
            "description": description,
            "deadline_text": None,
            "deadline_iso": deadline_iso,
            "status": status,
            "source_url": source_url,
        }
