"""Portal API interception: capture and decrypt the Angular app's XHR payloads.

The SPA renders all data from its REST API; the DOM is an Ionic/Ant table shell
with click-handler buttons and no usable markup. So instead of scraping DOM we
listen for the API responses while the browser navigates normally, and decrypt
them with `portal_crypto`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Iterable
from urllib.parse import urlparse

from app.automation.portal_crypto import decrypt_cryptojs

logger = logging.getLogger(__name__)


def decrypt_api_body(body: str) -> dict | None:
    """Decrypt an `{"response": "<ciphertext>"}` API body into a dict."""
    try:
        wrapper = json.loads(body)
    except json.JSONDecodeError:
        logger.debug("API body is not JSON")
        return None
    payload = wrapper.get("response") if isinstance(wrapper, dict) else None
    if not payload:
        return None
    try:
        return json.loads(decrypt_cryptojs(payload))
    except Exception:
        logger.exception("Failed to decrypt API payload")
        return None


class ResponseCollector:
    """Listen for API responses matching path substrings while attached."""

    def __init__(self, page, path_patterns: Iterable[str]):
        self._page = page
        self._patterns = tuple(path_patterns)
        self._bodies: dict[str, str] = {}
        self._handler = None

    async def _on_response(self, response) -> None:
        path = urlparse(response.url).path
        for pattern in self._patterns:
            if pattern in path:
                try:
                    body = await response.text()
                except Exception:
                    return
                # Keep the largest body per pattern (retries may be empty).
                if len(body) >= len(self._bodies.get(pattern, "")):
                    self._bodies[pattern] = body
                return

    def __enter__(self) -> "ResponseCollector":
        self._handler = lambda r: asyncio.ensure_future(self._on_response(r))
        self._page.on("response", self._handler)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._handler is not None:
            self._page.remove_listener("response", self._handler)
            self._handler = None

    def first(self, pattern: str) -> str | None:
        """Raw body of the first pattern match, or None."""
        return self._bodies.get(pattern)

    async def wait_for(
        self, patterns: Iterable[str], page, timeout_ms: int, poll_ms: int = 500
    ) -> bool:
        """Poll until every pattern has a captured body (or timeout).

        Polling instead of a fixed sleep makes capture robust against slow
        SPA renders: the navigation continues as soon as the payloads arrive.
        Returns True when all patterns were captured.
        """
        patterns = tuple(patterns)
        deadline = time.monotonic() + timeout_ms / 1000
        while not all(self.first(p) for p in patterns):
            if time.monotonic() >= deadline:
                return False
            await page.wait_for_timeout(poll_ms)
        return True

    def decrypted(self, pattern: str) -> dict | None:
        body = self.first(pattern)
        return decrypt_api_body(body) if body else None
