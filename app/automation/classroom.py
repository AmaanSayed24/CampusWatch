"""Classroom handling: subject discovery via the portal's REST API (§10).

The portal SPA (elearning.paruluniversity.ac.in) renders subjects from
`GET /api/subjects` (payload encrypted, see portal_crypto). Subject identity
is the Mongo `_id`; the subject page URL is
`/classrooms/{classroom_id}/subjects/{subject_id}`.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from playwright.async_api import Page

from app.automation.portal_api import ResponseCollector
from app.config.settings import Settings

logger = logging.getLogger(__name__)


class ClassroomScraper:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def discover_subjects(
        self, page: Page, classroom_urls: list[str] | None = None
    ) -> list[dict]:
        """Return normalized subject dicts: {portal_id, name, url}.

        Attempt 1 uses the UI flow (join page -> "Open" button). Later
        attempts navigate directly to previously seen classroom URLs — no
        clicking, no SPA route quirks — which makes the retry deterministic.
        """
        parsed = urlparse(self._settings.portal_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        subjects: list[dict] = []
        seen: set[str] = set()
        plans: list[str] = ["ui", *(f"url:{url}" for url in (classroom_urls or []))]
        for attempt, plan in enumerate(plans, 1):
            with ResponseCollector(page, ("/api/subjects",)) as collector:
                if plan == "ui":
                    # The subject list API fires on the Classroom pages, not
                    # the dashboard: join page first, then the classroom's
                    # subjects page.
                    join_url = f"{origin}/classrooms/join"
                    await page.goto(join_url, wait_until="domcontentloaded")
                    # The Open button renders late on a cold SPA; wait for it
                    # instead of a fixed sleep.
                    open_button = page.get_by_role(
                        "button", name=re.compile(r"^Open ", re.I)
                    ).first
                    try:
                        await open_button.wait_for(state="visible", timeout=15_000)
                    except Exception:
                        logger.debug("Open button never became visible on the join page")
                    if await open_button.count() > 0:
                        await open_button.click()
                else:
                    await page.goto(plan[4:], wait_until="domcontentloaded")
                # Poll until the subjects payload arrives (max 20 s) instead
                # of a fixed sleep: slow renders no longer get missed.
                await collector.wait_for(("/api/subjects",), page, timeout_ms=20_000)

                data = collector.decrypted("/api/subjects")
                if data:
                    for item in data.get("items", []):
                        if item.get("deleted"):
                            continue
                        name = re.sub(r"\s+", " ", item.get("name") or "").strip()
                        portal_id = item.get("_id")
                        if not name or not portal_id or portal_id in seen:
                            continue
                        seen.add(portal_id)
                        url = (
                            f"{origin}/classrooms/{item.get('classroom')}"
                            f"/subjects/{portal_id}"
                        )
                        subjects.append({"portal_id": portal_id, "name": name, "url": url})

            if subjects or attempt == len(plans):
                break
            logger.warning("No /api/subjects payload captured (plan %s); retrying", plan)
            await page.wait_for_timeout(3_000)

        if not subjects:
            logger.warning("No /api/subjects payload captured; cannot discover subjects")
        logger.info("Found %d subjects", len(subjects))
        return subjects
