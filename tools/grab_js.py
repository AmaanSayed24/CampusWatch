"""Diagnostic: save the portal's JS bundles so the API decryption key can be found.

Run:  .venv\\Scripts\\python.exe tools\\grab_js.py
Saves every JS response into tools/dumps/js/.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

from app.config.settings import get_settings  # noqa: E402

OUT = Path(__file__).parent / "dumps" / "js"


async def main() -> None:
    settings = get_settings()
    OUT.mkdir(parents=True, exist_ok=True)
    saved: set[str] = set()

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        async def on_response(response) -> None:
            url = response.url
            if not re.search(r"\.js(\?|$)", urlparse(url).path):
                return
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", urlparse(url).path)[-100:]
            if name in saved:
                return
            try:
                body = await response.body()
            except Exception:
                return
            saved.add(name)
            (OUT / name).write_bytes(body)
            print(f"JS: {name} ({len(body)}b)")

        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

        await page.goto(settings.portal_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(12_000)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
