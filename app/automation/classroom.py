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

    async def discover_subjects(self, page: Page) -> list[dict]:
        """Return normalized subject dicts: {portal_id, name, url}."""
        parsed = urlparse(self._settings.portal_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        subjects: list[dict] = []
        seen: set[str] = set()
        with ResponseCollector(page, ("/api/subjects",)) as collector:
            # The subject list API fires on the Classroom pages, not the
            # dashboard: join page first, then the classroom's subjects page.
            await page.goto(f"{origin}/classrooms/join", wait_until="domcontentloaded")
            await page.wait_for_timeout(3_000)
            open_button = page.get_by_role("button", name=re.compile(r"^Open ", re.I)).first
            if await open_button.count() > 0:
                await open_button.click()
            await page.wait_for_timeout(5_000)

            data = collector.decrypted("/api/subjects")
            if not data:
                logger.warning("No /api/subjects payload captured; cannot discover subjects")
                return []

            for item in data.get("items", []):
                if item.get("deleted"):
                    continue
                name = re.sub(r"\s+", " ", item.get("name") or "").strip()
                portal_id = item.get("_id")
                if not name or not portal_id or portal_id in seen:
                    continue
                seen.add(portal_id)
                url = f"{origin}/classrooms/{item.get('classroom')}/subjects/{portal_id}"
                subjects.append({"portal_id": portal_id, "name": name, "url": url})

        logger.info("Found %d subjects", len(subjects))
        return subjects
