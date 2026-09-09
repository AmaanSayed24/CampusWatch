"""Probe the live portal API for a specific subject's classwork.

Run: .venv\\Scripts\\python.exe tools\\probe_subject.py
Navigates to the subject page, opens Classwork, captures and decrypts every
/api/ JSON response, and prints a condensed view of the classwork payloads.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

from app.automation.portal_crypto import decrypt_cryptojs  # noqa: E402
from app.config.settings import get_settings  # noqa: E402

SUBJECT_ID = "6a757266b376fb50a2dbd543"  # Data Structures
STATIC = re.compile(r"\.(js|css|png|jpg|jpeg|svg|gif|woff2?|ttf|ico|map)(\?|$)", re.I)


def summarise_work(w: dict, indent: str = "   ") -> None:
    a = w.get("assignment") or {}
    print(f"{indent}type={w.get('type')!r} title={w.get('title')!r} _id={w.get('_id')}")
    print(f"{indent}  deleted={w.get('deleted')} status={w.get('status')}")
    print(
        f"{indent}  hasDueDate={a.get('hasDueDate')} dueDateTime={a.get('dueDateTime')} "
        f"point={a.get('point')}"
    )
    t = w.get("trackAssignment") or {}
    print(f"{indent}  track: status={t.get('status')} submittedAt={t.get('submittedAt')}")


async def main() -> None:
    settings = get_settings()
    base = "{0.scheme}://{0.netloc}".format(urlparse(settings.portal_url))
    captured: dict[str, str] = {}

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(settings.browser_profile_dir),
            headless=False,
            viewport={"width": 1366, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()

        async def on_response(response) -> None:
            url = response.url
            path = urlparse(url).path
            if STATIC.search(path) or not path.startswith("/api/"):
                return
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                body = await response.text()
            except Exception:
                return
            if len(body) >= len(captured.get(path, "")):
                captured[path] = body
            print(f"  API: {response.request.method} {path} ({len(body)}b)")

        page.on("response", lambda r: asyncio.ensure_future(on_response(r)))

        subject_url = f"{base}/classrooms/6a3e63efff1f25a33fe0e974/subjects/{SUBJECT_ID}"
        # Replicate the sync code path exactly: /classrooms/join -> Open
        # classroom (in-tab) -> subjects page -> same-tab goto subject URL ->
        # click Classwork, capturing responses on the SAME page.
        await page.goto(f"{base}/classrooms/join", wait_until="domcontentloaded")
        await page.wait_for_timeout(4_000)
        await page.get_by_role("button", name=re.compile(r"^Open ", re.I)).first.click()
        await page.wait_for_timeout(4_000)
        print(f"subjects page url: {page.url}")

        java_url = f"{base}/classrooms/6a3e63efff1f25a33fe0e974/subjects/6a75726bb376fb50a2dbd5aa"
        await page.goto(java_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)
        await page.get_by_text("Classwork", exact=False).first.click(timeout=8_000)
        await page.wait_for_timeout(4_000)
        print("java classwork done (leaves page on Java Classwork tab)")

        await page.goto(subject_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(4_000)
        try:
            await page.get_by_text("Classwork", exact=False).first.click(timeout=8_000)
        except Exception as exc:
            print("classwork click failed:", exc)
        await page.wait_for_timeout(5_000)
        await page.screenshot(path=str(Path(__file__).parent / "dumps" / "probe_sync_path.png"), full_page=True)
        await page.screenshot(path=str(Path(__file__).parent / "dumps" / "probe_sync_path.png"), full_page=True)
        await page.wait_for_timeout(5_000)
        # Save decrypted classwork payloads for inspection.
        for path, body in captured.items():
            if "classroom-topics" in path or "classroom-works" in path:
                try:
                    data = json.loads(decrypt_cryptojs(json.loads(body)["response"]))
                    out = Path(__file__).parent / "dumps" / ("probe_" + path.strip("/").replace("/", "_") + ".json")
                    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
                    print("saved", out.name, len(json.dumps(data)))
                except Exception as exc:
                    print("save failed", path, exc)

        for path, body in sorted(captured.items()):
            print("=" * 70)
            print(path)
            try:
                data = json.loads(decrypt_cryptojs(json.loads(body)["response"]))
            except Exception as exc:
                print("  decrypt failed:", exc)
                print("  raw:", body[:200])
                continue
            if isinstance(data, dict):
                print(f"  keys: {sorted(data.keys())}")
                items = data.get("items", [])
                print(f"  items: {len(items)}  total: {data.get('total')}")
                for item in items:
                    if isinstance(item, dict) and "works" in item:
                        print(f"  topic: {item.get('title')!r} ({item.get('_id')}) works={len(item.get('works') or [])}")
                        for w in item.get("works") or []:
                            summarise_work(w)
                    else:
                        summarise_work(item)
                if not items:
                    print(json.dumps(data, indent=1)[:1500])
            else:
                print("  (non-dict)", repr(data)[:300])
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())