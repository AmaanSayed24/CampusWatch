"""Browser management: persistent context, timeouts, failure screenshots (§21)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from app.config.settings import Settings

logger = logging.getLogger(__name__)


class BrowserManager:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._pw = None
        self._context: BrowserContext | None = None

    async def start(self) -> Page:
        """Launch a persistent Chromium context (keeps the login session)."""
        profile_dir = Path(self._settings.browser_profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Launching browser (headless=%s)", self._settings.browser_headless)
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=self._settings.browser_headless,
            viewport={"width": 1366, "height": 900},
        )
        self._context.set_default_timeout(self._settings.navigation_timeout_ms)
        page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        return page

    async def screenshot(self, name: str, page: Page) -> Path | None:
        """Save a debugging screenshot (e.g. login_failure_2026-09-08_1015.png)."""
        try:
            path = Path(self._settings.screenshots_dir)
            path.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
            file_path = path / f"{name}_{stamp}.png"
            await page.screenshot(path=str(file_path), full_page=True)
            logger.info("Saved screenshot: %s", file_path)
            return file_path
        except Exception:
            logger.exception("Failed to capture screenshot for %s", name)
            return None

    async def close(self) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception:
            logger.exception("Error closing browser context")
        finally:
            self._context = None
            if self._pw:
                try:
                    await self._pw.stop()
                except Exception:
                    logger.exception("Error stopping Playwright")
                self._pw = None
