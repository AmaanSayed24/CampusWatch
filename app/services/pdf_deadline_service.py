"""PDF deadline enrichment for assignment-like documents.

For classwork items the portal tracks only as uploaded documents (no API due
date), the assignment PDF is downloaded through the logged-in browser session
and analysed for deadline phrases ("Due Date", "Submit by", "Deadline", ...).
Results are cached per document URL in the `pdf_deadline_cache` table so each
PDF is downloaded and parsed at most once. Documents without a reliable
deadline keep the deadline as N/A.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page

from app.config.settings import Settings
from app.database.repository import Repository
from app.parsers.pdf_parser import PARSER_VERSION, extract_deadline_from_pdf

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB safety cap
DOWNLOAD_TIMEOUT_MS = 60_000
# Sentinel confidence for a validated non-PDF payload (e.g. the subject HTML
# page). Cached so it is never re-downloaded on every sync.
NOT_PDF_CONFIDENCE = -1.0


class PdfDeadlineService:
    def __init__(self, settings: Settings, repository: Repository):
        self._settings = settings
        self._repo = repository
        self._tz = settings.get_timezone()

    async def enrich(self, page: Page, records: list[dict]) -> list[dict]:
        """Fill in deadlines for document records by analysing their PDFs."""
        for raw in records:
            if raw.get("deadline_iso") or raw.get("deadline_text"):
                continue  # portal already provides a due date
            url = raw.get("source_url") or ""
            if not url:
                continue
            # Portal document links are not always named *.pdf; some are
            # API/viewer URLs. We therefore validate the downloaded payload
            # (%PDF) instead of relying on the URL suffix. Resolve relative
            # document paths against the classroom URL.
            url = urljoin(raw.get("url") or "", url)
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                continue

            cached = self._repo.get_pdf_deadline(url)
            if cached is not None and cached.parser_version == PARSER_VERSION:
                self._apply_cached_deadline(raw, cached)
                continue

            # First sight of this URL, or the extraction logic improved since
            # the cached analysis (PARSER_VERSION bump): download and analyse.
            pdf_bytes, validated_not_pdf = await self._download_pdf(page, url)
            if validated_not_pdf:
                self._repo.save_pdf_deadline(
                    url, None, NOT_PDF_CONFIDENCE, None, PARSER_VERSION
                )
                continue  # HTML page / viewer link: cache and skip
            if pdf_bytes is None:
                continue  # transient failure: retry on the next sync
            match = await asyncio.to_thread(
                extract_deadline_from_pdf, pdf_bytes, self._tz
            )
            self._repo.save_pdf_deadline(
                url,
                match.deadline if match else None,
                match.confidence if match else 0.0,
                match.snippet if match else None,
                PARSER_VERSION,
            )
            self._apply_cached_deadline(raw, self._repo.get_pdf_deadline(url))
        return records

    def _apply_cached_deadline(self, raw: dict, cached) -> None:
        """Copy a cached extraction result into the raw record (N/A stays)."""
        if cached is None or cached.deadline is None:
            return  # nothing reliable found (or non-PDF payload): keep N/A
        raw["deadline_iso"] = cached.deadline.isoformat()
        raw["description"] = (
            f"{raw.get('description') or 'Assignment document.'} "
            f'Deadline extracted from PDF (confidence {cached.confidence:.0%}): '
            f'"{cached.snippet}"'
        ).strip()
        logger.info(
            "PDF deadline for %s: %s (confidence %.0f%%)",
            raw.get("title"), cached.deadline, cached.confidence * 100,
        )

    async def _download_pdf(self, page: Page, url: str) -> tuple[bytes | None, bool]:
        """Fetch the payload through the browser session (shares cookies/auth).

        Returns (pdf_bytes, validated_not_pdf):
            (bytes, False) — valid PDF payload
            (None,  True)  — response OK but the payload is definitively not a
                             PDF (safe to cache permanently)
            (None,  False) — transient failure (retry on the next sync)
        """
        try:
            response = await page.context.request.get(url, timeout=DOWNLOAD_TIMEOUT_MS)
            if not response.ok:
                logger.debug("PDF download failed (%s): %s", response.status, url)
                return None, False
            body = await response.body()
            if not body or len(body) > MAX_PDF_BYTES:
                return None, False
            if not body.startswith(b"%PDF"):
                logger.debug("Validated non-PDF payload: %s", url)
                return None, True
            return bytes(body), False
        except Exception:
            logger.exception("Error downloading PDF: %s", url)
            return None, False
