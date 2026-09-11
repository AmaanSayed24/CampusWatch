# CampusWatch — College Portal Assignment Tracking Agent

A local Python agent that monitors the Parul University e-learning portal
(`elearning.paruluniversity.ac.in`) for assignments, tracks deadlines, and sends
desktop reminders before submissions are due.

**Strategy:** `Observe -> Extract -> Store -> Compare -> Remind`

## Features

- **Real assignment discovery** — the portal is an Angular SPA with AES-encrypted
  API responses; the agent drives a real browser, intercepts the portal's own
  API calls, and decrypts them (stdlib-only implementation) to find your actual
  subjects and classwork.
- **Deadline tracking** — due dates are parsed from the portal API *and* from
  assignment PDFs (keyword-aware extraction with confidence scoring).
- **Change detection** — new assignments and deadline changes are detected
  across syncs, with desktop notifications.
- **10-minute dashboard** — every scan ends with a full assignment summary
  (subject, title, deadline, classification, total count) sent as a desktop
  notification and recorded in `logs/agent.log`.
- **Reminder windows** — configurable `7d, 3d, 24h, 3h` reminders plus a daily
  summary, driven by an APScheduler loop.
- **Local & private** — everything (database, browser profile, logs) stays on
  your machine.

## How it works

The portal is an Angular SPA: subjects and classwork are rendered from a REST
API whose responses are AES-encrypted (CryptoJS passphrase mode, OpenSSL
salted format). DOM scraping is therefore unreliable, so the agent instead
drives a real browser and **intercepts + decrypts the portal's own API
responses**:

```text
Login (persisted browser session)
   -> /classrooms/join -> open the classroom
   -> intercept GET /api/subjects            -> discover the real subjects
   -> for each subject: open page + Classwork tab
      intercept GET /api/classroom-works/{id} and /api/classroom-topics/{id}
      -> extract works (assignments + assignment-named documents)
   -> normalize (title, due date, points, status)
   -> compare against local SQLite database
   -> detect new / deadline-changed assignments
   -> send desktop notifications (new, deadline windows, overdue)
```

### 10-minute dashboard summary

The scheduler scans every `CHECK_INTERVAL_MINUTES` (default **10**). After each
scan the agent classifies **every** outstanding assignment and sends the full
summary as one desktop notification:

- each entry: subject name, assignment title, deadline
- classification: **OVERDUE** (deadline passed), **UPCOMING** (future
  deadline), **NO DEADLINE** (no date available)
- overdue assignments are retained, never filtered out
- total counts in the header (outstanding / overdue / upcoming / no deadline /
  submitted)
- the complete text is also written to `logs/agent.log` (`SUMMARY |` lines),
  so long summaries are never lost to notification truncation (the OS toast
  itself is capped at ~250 chars — the header + counts are what you see on
  screen)

Existing SQLite tracking, change detection and windowed reminders all continue
to work on top of this flow.


The AES passphrase was recovered from the portal's JS bundle and is implemented
in `app/automation/portal_crypto.py` using only the standard library.

### What gets tracked

- **Portal-tracked assignments** (`type: "assignment"`) carry real due dates,
  points, and submission state (e.g. *Data Structures → Assignment 1*).
- **Documents titled like assignments** (e.g. PDFs named "Assignment 1" that
  faculty upload) are tracked too, but the portal stores no due date for them,
  so they appear as "due N/A".

### PDF deadline extraction

Document-type assignments rarely carry a due date in the portal API. When a
document's source is a PDF, the agent downloads it through the logged-in
browser session and **analyses its text for deadline phrases** ("Due Date",
"Deadline", "Submit by", "Last date of submission", "on or before", ...) and
date / date-time values. Each candidate date is scored by:

- keyword proximity (strong phrase 0.85, weaker wording 0.60, bare date 0.40)
- explicit time-of-day (+0.05)

The highest-scoring candidate with **confidence ≥ 0.6** is accepted as the
deadline and its surrounding snippet stored for verification; otherwise the
assignment falls back to **N/A** (`app/parsers/pdf_parser.py`).

Results are cached in the `pdf_deadline_cache` table (keyed by document URL
hash), so each PDF is downloaded and parsed at most once. Extraction order
follows the design doc (§17): webpage metadata → PDF text (implemented) → OCR
for image-only PDFs (not implemented).

The agent behaves like a normal logged-in browser user (Playwright + persistent
browser profile). It never bypasses authentication, CAPTCHA, or portal
restrictions, and all credentials/data stay on your machine.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

> Already using this project? Just run `pip install -r requirements.txt` again
> to pick up new dependencies (e.g. `pypdf`) and re-run `playwright install`.

Create your local config:

```bash
copy .env.example .env
# edit .env as needed
```

Recommended: leave `PORTAL_USERNAME`/`PORTAL_PASSWORD` empty and log in manually
in the visible browser on the first run — the session is persisted in
`data/browser-profile/` and reused afterwards.

## First run

1. `copy .env.example .env` and adjust as needed.
2. Run `.venv\Scripts\python.exe run_agent.py sync-now` once.
3. Complete the login (CAPTCHA/OTP if asked) in the browser window that opens.
4. Re-run `sync-now` — the session is now persisted and reused automatically.
5. Optional: `run_agent.py test-notification` to verify desktop notifications.

## Usage

Run with the project's virtual environment (not a system Python):

```powershell
.venv\Scripts\python.exe run_agent.py <command>
```

| Command | Purpose |
|---|---|
| `sync` | Start the scheduler (immediate sync, then every `CHECK_INTERVAL_MINUTES`, default 10). |
| `sync-now` | Run a single manual sync pass against the portal. |
| `assignments` | List all tracked assignments. |
| `upcoming` | List assignments due within the largest reminder window. |
| `overdue` | List assignments past their deadline. |
| `status` | Show the result of the last sync run. |
| `test-notification` | Verify desktop notifications work on this machine. |

## Project layout

```text
app/
  config/      settings loaded from .env
  automation/  Playwright: browser, login, classroom + assignment scrapers,
               portal API interception (portal_api) and response decryption
               (portal_crypto)
  parsers/     API records -> normalized models, deadline parsing, PDF deadline
               extraction (pdf_parser)
  database/    SQLAlchemy models, connection, repository
  services/    sync, change detection, deadline engine, reminders, notifications,
               PDF deadline enrichment (pdf_deadline_service)
  scheduler/   APScheduler loop
  cli/         Typer commands
  utils/       dates, hashing, logging
tests/         unit tests: parsers, deadline engine, change detector, repository,
               PDF deadline extraction (test_pdf_deadline.py)
tools/         diagnostics: capture_portal.py (walks the portal recording API
               responses), grab_js.py (dumps JS bundles), decrypt_api.py
               (decrypts captured payloads)
data/          portal.db + browser profile (local only)
logs/          agent.log
screenshots/   failure screenshots for debugging portal UI changes
```

### Conventions worth knowing

- Deadlines are stored in SQLite as **naive wall-time in the configured
  timezone** (`TIMEZONE`, default `Asia/Kolkata`); `normalize_assignment` does
  the conversion, and the reminder engine compares like with like.
- Subject/assignment identity uses the portal's Mongo `_id` values, so records
  stay stable across syncs.
- Subjects that disappear from the portal are deactivated (not deleted).
- On Windows the CLI forces UTF-8 output, so emoji like ➖/❗ render correctly in
  both the terminal and piped output.

## Security rules

- Never commit `.env`; never log passwords, cookies, tokens, or OTPs.
- Keep the database and browser profile local.
- The agent only reads data visible to your own logged-in account.

