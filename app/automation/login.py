"""Login/session handling (§18).

Strategy:
  1. Open the portal URL.
  2. If no password field is visible, assume the persisted session is valid.
  3. If credentials are configured, fill the login form.
  4. If CAPTCHA/OTP is detected, or no credentials are configured, wait for
     manual login in the visible browser (never bypass security controls).
"""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.automation.browser import BrowserManager
from app.config.settings import Settings

logger = logging.getLogger(__name__)

PASSWORD_SELECTOR = "input[type='password']"
MFA_PATTERN = re.compile(r"captcha|otp|one\s*time|two\s*factor|2fa", re.IGNORECASE)


class LoginRequiredError(RuntimeError):
    """Raised when manual interaction is needed but the browser is headless."""


class LoginService:
    def __init__(self, settings: Settings, browser_manager: BrowserManager):
        self._settings = settings
        self._browser = browser_manager

    async def is_logged_in(self, page: Page) -> bool:
        try:
            await page.wait_for_selector(PASSWORD_SELECTOR, timeout=5_000)
            return False  # login form visible
        except PlaywrightTimeoutError:
            return True  # no password field -> assume authenticated

    async def ensure_authenticated(self, page: Page) -> Page:
        logger.info("Checking authentication state")
        await page.goto(self._settings.portal_url, wait_until="domcontentloaded")

        if await self.is_logged_in(page):
            logger.info("Authenticated via persisted session")
            return page

        username = self._settings.portal_username
        password = self._settings.portal_password

        if username and password:
            logger.info("Login form detected; filling stored credentials")
            await self._fill_login_form(page, username, password)
        else:
            logger.info("Login form detected; waiting for manual login")

        if await self._manual_interaction_needed(page):
            await self._wait_for_manual_login(page)

        if not await self.is_logged_in(page):
            await self._browser.screenshot("login_failure", page)
            raise LoginRequiredError("Could not confirm login after attempting authentication")

        logger.info("Authenticated successfully")
        return page

    async def _fill_login_form(self, page: Page, username: str, password: str) -> None:
        user_field = page.locator(
            "input[name='username'], input[name='email'], input[type='text'], input[type='email']"
        ).first
        pass_field = page.locator(PASSWORD_SELECTOR).first
        await user_field.fill(username)
        await pass_field.fill(password)
        await page.locator("button[type='submit'], input[type='submit']").first.click()
        await page.wait_for_load_state("domcontentloaded")

    async def _manual_interaction_needed(self, page: Page) -> bool:
        """CAPTCHA/OTP present, or the password field is still visible."""
        if await page.locator(PASSWORD_SELECTOR).count() > 0:
            content = await page.content()
            if MFA_PATTERN.search(content):
                logger.warning("CAPTCHA/OTP detected; manual completion required")
            return True
        return False

    async def _wait_for_manual_login(self, page: Page) -> None:
        if self._settings.browser_headless:
            await self._browser.screenshot("login_manual_required", page)
            raise LoginRequiredError(
                "Manual login required but the browser is headless. "
                "Run once with BROWSER_HEADLESS=false to establish a session."
            )
        print(
            "\n[ACTION REQUIRED] Please complete the login in the opened browser "
            f"(waiting up to {self._settings.manual_login_timeout_seconds}s)...\n"
        )
        try:
            await page.wait_for_selector(
                PASSWORD_SELECTOR, state="detached",
                timeout=self._settings.manual_login_timeout_seconds * 1000,
            )
        except PlaywrightTimeoutError:
            pass
