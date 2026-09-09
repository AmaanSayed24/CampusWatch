"""Diagnostic: capture the portal's backend API responses for selector tuning.

Run:  .venv\\Scripts\\python.exe tools\\capture_portal.py

Walks Dashboard -> Classrooms -> each subject -> Classwork while recording
every JSON XHR/fetch response into tools/dumps/api/*.json.
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import Page, async_playwright  # noqa: E402

from app.config.settings import get_settings  # noqa: E402

OUT = Path(__file__).parent / "dumps" / "api"
STATIC = re.compile(r"\.(js|css|png|jpg|jpeg|svg|gif|woff2?|ttf|ico|map)(\?|$)", re.I)


class ApiRecorder:
    def __init__(self) -> None:
        self.seen: set = set()

    async def on_response(self, response) -> None:
        url = response.url
        if STATIC.search(urlparse(url).path):
            return
        if "json" not in response.headers.get("content-type", ""):
            return
        try:
            body = await response.text()
        except Exception:
            return
        key = (url, body[:200])
        if key in self.seen or len(body) < 3:
            return
        self.seen.add(key)
        stamp = datetime.now().strftime("%H%M%S%f")[:-3]
        safe = re.sub(r"[^A-Za-z0-9]+", "_", urlparse(url).path)[-80:].strip("_") or "root"
        (OUT / f"{stamp}_{safe}.json").write_text(body, encoding="utf-8")
        print(f"    API: {response.request.method} {urlparse(url).path} ({len(body)}b)")


def attach(page: Page, recorder: ApiRecorder) -> None:
    page.on(
        "response",
        lambda r: asyncio.ensure_future(recorder.on_response(r)),
    )


async def main() -> None:
    settings = get_settings()
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 900},
        )
        context.set_default_timeout(30_000)
        page = context.pages[0] if context.pages else await context.new_page()
        recorder = ApiRecorder()
        attach(page, recorder)

        base = "{0.scheme}://{0.netloc}".format(urlparse(settings.portal_url))

        await page.goto(settings.portal_url, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector("input[type='password']", timeout=5_000)
            print("Login required -> complete it in the browser window...")
            await page.wait_for_selector(
                "input[type='password']", state="detached", timeout=300_000
            )
        except Exception:
            pass
        await page.wait_for_timeout(3_000)

        # Classroom list -> open the first classroom.
        await page.goto(f"{base}/classrooms/join", wait_until="domcontentloaded")
        await page.wait_for_timeout(4_000)
        await page.get_by_role("button", name=re.compile("^Open ", re.I)).first.click()
        await page.wait_for_timeout(4_000)

        # Visit every subject, open its Classwork tab, record API traffic.
        total = await page.get_by_role("button", name=re.compile("^Open ", re.I)).count()
        print(f"Subjects with Open buttons: {total}")
        seen_urls: set[str] = set()

        for i in range(min(total, 8)):
            btn = page.get_by_role("button", name=re.compile("^Open ", re.I)).nth(i)
            name = " ".join((await btn.inner_text()).split())
            pages_before = list(context.pages)
            await btn.click()
            await page.wait_for_timeout(5_000)
            new_pages = [p for p in context.pages if p not in pages_before]
            target = new_pages[-1] if new_pages else page
            if target.url in seen_urls:
                continue
            seen_urls.add(target.url)
            if target is not page:
                attach(target, recorder)
            print(f"[{i}] {name} -> {target.url}")

            try:
                await target.get_by_text("Classwork", exact=False).first.click(timeout=8_000)
                await target.wait_for_timeout(6_000)
            except Exception as exc:
                print(f"    classwork tab failed: {exc}")

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
