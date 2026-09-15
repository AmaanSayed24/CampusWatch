# CampusWatch — College Portal Assignment Tracking Agent

A local Python automation and monitoring agent that monitors the Parul University
e-learning portal for assignments, tracks deadlines, detects changes, and sends
desktop notifications.

**Strategy:** `Observe -> Extract -> Store -> Compare -> Remind`

## What CampusWatch is

CampusWatch is primarily an **autonomous web automation and monitoring agent**.

It uses Playwright to operate a real logged-in browser session, observes the
portal's API responses, decrypts the portal's encrypted payloads, extracts
assignment data, stores it locally, compares successive syncs, evaluates
deadlines, and sends notifications.

It is **not an AI/ML or LLM agent** in the current implementation. Its decisions
are rule-based and deterministic.

## Features

- **Real assignment discovery** — the portal is an Angular SPA with encrypted
  API responses. CampusWatch drives a real browser, intercepts the portal's own
  API calls, decrypts them, and discovers subjects and classwork.
- **Deadline tracking** — deadlines are read from portal assignment metadata.
  PDF text extraction is also implemented for document records when a valid,
  discoverable PDF source URL is available.
- **Change detection** — new assignments and deadline changes are detected
  across syncs.
- **Automated reminders** — configurable reminder windows such as
  `7d,3d,24h,3h` are supported.
- **Full assignment summary** — the scheduler performs a complete assignment
  summary every 10 minutes by default. The summary includes assignments with
  deadlines, overdue assignments, and assignments with no deadline.
- **Desktop notifications** — sync events, reminders, and assignment summaries
  can be delivered through Windows desktop notifications.
- **Local storage** — the SQLite database, browser profile, logs, and other
  runtime data remain on the local machine.

## How it works

The portal is an Angular SPA. Subjects and classwork are rendered from REST
API responses whose payloads are AES-encrypted using the portal's CryptoJS
passphrase/OpenSSL-salted format.

Instead of relying only on DOM scraping, CampusWatch observes the portal's own
API traffic:

```text
Login / persisted browser session
        |
        v
Open classroom area
        |
        v
Intercept GET /api/subjects
        |
        v
Discover subjects
        |
        v
For each subject:
    open subject page
    open Classwork tab
    intercept:
        GET /api/classroom-works/{id}
        GET /api/classroom-topics/{id}
        |
        v
Extract trackable classwork
        |
        v
Normalize title, deadline, status, source
        |
        +----> PDF deadline enrichment when a PDF source is available
        |
        v
Store/update SQLite
        |
        v
Compare with previous state
        |
        +----> new assignment
        +----> deadline changed
        |
        v
Deadline/reminder evaluation
        |
        v
Desktop notifications + assignment summary
```

## Scheduling

The current scheduler performs two interval jobs:

1. **Portal sync** — every `CHECK_INTERVAL_MINUTES` (default: `10`).
2. **Full assignment summary** — every `ASSIGNMENT_SUMMARY_INTERVAL_MINUTES`
   (default: `10`).

An immediate sync is also performed when `run_agent.py sync` starts.

The old daily-summary function remains in the codebase for compatibility, but
it is **not scheduled by the current scheduler**. The active scheduler uses the
10-minute full assignment summary.

### Full assignment summary

Every summary includes all currently tracked assignments, grouped by subject.

Each assignment is classified as:

- `OVERDUE` — deadline has passed.
- `DUE TODAY` — deadline is today.
- `UPCOMING` — deadline is in the future.
- `No deadline` — no deadline is available.

Overdue and no-deadline assignments are intentionally retained in the summary.

The complete summary is written to `logs/agent.log`. Windows desktop toast
notifications may truncate long text, so the log is the reliable full record.

## Deadline and PDF extraction

### Portal deadlines

For portal-tracked assignments, the scraper reads the assignment's due-date
metadata when the portal provides it.

### PDF deadlines

The PDF deadline parser uses `pypdf` to:

1. Extract text from a PDF.
2. Normalize the extracted text.
3. Find date/date-time candidates.
4. Score candidates according to deadline-related wording and time-of-day.
5. Accept the highest-scoring candidate when its confidence is at least `0.6`.

Examples of deadline wording considered include phrases such as:

- `Due Date`
- `Deadline`
- `Submit by`
- `Last date of submission`
- `On or before`

The extraction result can include a confidence score and surrounding text snippet.

PDF results are cached in the `pdf_deadline_cache` table using a hash of the
document URL.

### Current PDF limitation

The current implementation does **not** include OCR.

It can extract text from PDFs that contain a usable text layer. Scanned/image-only
PDFs are therefore not guaranteed to produce a deadline.

Also, the current assignment scraper only uses a document URL exposed directly
through the supported classwork record. Portal documents nested inside structures
such as `trackAssignment.answers[].documents[]` are **not currently promoted to
PDF sources by the scraper**.

Therefore the project should not claim that all uploaded assignment PDFs are
automatically analysed.

## What gets tracked

CampusWatch tracks classwork that is either:

- explicitly marked by the portal as `type: "assignment"`, or
- has an assignment-like title containing `assign`.

Portal-tracked assignments can contain real due dates, points, and submission
state.

Assignment-like document records can also be tracked, but they may have no
portal deadline and therefore appear as `N/A` unless a usable PDF source is
found and a reliable deadline is extracted.

## Reminders

Reminder windows are configured through:

```text
REMINDER_WINDOWS=7d,3d,24h,3h
```

The reminder engine checks the configured windows and prevents duplicate
notifications for the same assignment/window.

Overdue reminder notifications are controlled separately:

```text
NOTIFY_OVERDUE=false
```

With the default setting, overdue assignments still appear in the full
assignment summary, but a separate overdue notification is not sent.

## CLI usage

Run commands using the project's virtual environment:

```powershell
.venv\Scripts\python.exe run_agent.py <command>
```

| Command | Purpose |
|---|---|
| `sync` | Start the scheduler. Performs an immediate sync and then repeats on the configured interval. |
| `sync-now` | Run one manual portal sync. |
| `assignments` | List all tracked assignments. |
| `upcoming` | List assignments due within the largest configured reminder window. |
| `overdue` | List assignments whose deadline has passed. |
| `status` | Show the last recorded sync run. |
| `test-notification` | Test Windows desktop notifications. |

The current CLI does **not** provide `gui`, `set-deadline`, or
`clear-deadline` commands.

## Setup

Create and activate the virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Create local configuration:

```powershell
copy .env.example .env
```

Edit `.env` only on your machine.

For the first login, the recommended configuration is:

```text
BROWSER_HEADLESS=false
PORTAL_USERNAME=
PORTAL_PASSWORD=
```

Run:

```powershell
.venv\Scripts\python.exe run_agent.py sync-now
```

A visible browser opens. Complete the university login, including CAPTCHA or
OTP if requested. The Playwright persistent browser profile is stored under
`data/browser-profile/` and reused on later runs.

Then run:

```powershell
.venv\Scripts\python.exe run_agent.py sync
```

## Windows Task Scheduler

The simplest reliable setup for the current default
`BROWSER_HEADLESS=false` configuration is to run the task at user logon while
the Windows user session is available.

### GUI method

1. Open **Task Scheduler**.
2. Select **Task Scheduler Library**.
3. Click **Create Task...**.
4. On **General**:
   - Name: `CampusWatch`
   - Select **Run only when user is logged on**.
5. On **Triggers**:
   - Create a trigger **At log on**.
6. On **Actions**:
   - Action: **Start a program**
   - Program/script:

```text
C:\Users\sayed\OneDrive\Documents\Project\S_Agent\.venv\Scripts\python.exe
```

   - Add arguments:

```text
run_agent.py sync
```

   - Start in:

```text
C:\Users\sayed\OneDrive\Documents\Project\S_Agent
```

7. On **Conditions**, disable the AC-power-only restriction if you want it to
   run while the laptop is on battery.
8. On **Settings**, enable **Allow task to be run on demand**.
9. Save the task.
10. Right-click `CampusWatch` and choose **Run** to test it.

### PowerShell method

Run PowerShell as your normal Windows user:

```powershell
$action = New-ScheduledTaskAction `
  -Execute "C:\Users\sayed\OneDrive\Documents\Project\S_Agent\.venv\Scripts\python.exe" `
  -Argument "run_agent.py sync" `
  -WorkingDirectory "C:\Users\sayed\OneDrive\Documents\Project\S_Agent"

$trigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask `
  -TaskName "CampusWatch" `
  -Action $action `
  -Trigger $trigger `
  -Description "Runs the CampusWatch assignment monitoring agent."
```

Test it:

```powershell
Start-ScheduledTask -TaskName "CampusWatch"
Get-ScheduledTaskInfo -TaskName "CampusWatch"
```

A successful task execution normally reports:

```text
LastTaskResult : 0
```

To remove the task:

```powershell
Unregister-ScheduledTask -TaskName "CampusWatch" -Confirm:$false
```

### Headless scheduled operation

If you want CampusWatch to run when nobody is logged into the Windows desktop,
configure:

```text
BROWSER_HEADLESS=true
```

and verify that the persisted browser session works headlessly before changing
the Task Scheduler account/session settings.

## Configuration

Important `.env` values include:

```text
PORTAL_URL=https://elearning.paruluniversity.ac.in/students/dashboard

BROWSER_HEADLESS=false
BROWSER_PROFILE_DIR=data/browser-profile

CHECK_INTERVAL_MINUTES=10
ASSIGNMENT_SUMMARY_INTERVAL_MINUTES=10

REMINDER_WINDOWS=7d,3d,24h,3h
DAILY_SUMMARY_TIME=08:00
NOTIFY_OVERDUE=false

NOTIFICATION_ENABLED=true

LOG_LEVEL=INFO
TIMEZONE=Asia/Kolkata
```

`DAILY_SUMMARY_TIME` is retained as a configuration value for the existing
daily-summary service, but the current scheduler does not schedule that daily
summary.

## Project layout

```text
app/
  config/          Settings loaded from .env
  automation/      Playwright browser, login, classroom and assignment
                   scraping, API interception and portal decryption
  parsers/         Subject, assignment, deadline and PDF parsing
  database/        SQLAlchemy models, database connection and repository
  services/        Sync, change detection, deadline engine, reminders,
                   notifications and PDF deadline enrichment
  scheduler/       APScheduler interval jobs
  cli/             Typer command-line interface
  utils/           Dates, hashing and logging

tests/              Unit tests for parsers, repository, change detection,
                    deadline engine and PDF deadline extraction

tools/              Portal diagnostics and API/JS inspection utilities

data/               Local SQLite database and persistent browser profile
logs/               Agent log
screenshots/        Failure screenshots
```

## Dependencies

Main runtime dependencies:

```text
playwright
python-dotenv
sqlalchemy
apscheduler
plyer
typer
pydantic
pydantic-settings
pypdf
tzdata
```

Development/testing dependencies include:

```text
pytest
ruff
```

No OCR package such as `pypdfium2`, `winsdk`, Pillow, or Tesseract integration is
part of the current project.

## Data and privacy

CampusWatch is designed as a local application.

- Keep `.env` private.
- Never commit passwords, cookies, access tokens, or OTPs.
- Keep the SQLite database and browser profile local.
- The browser uses the user's own authenticated session.
- CampusWatch does not bypass CAPTCHA, authentication, or portal access controls.
- The agent reads data available to the authenticated account.

## Time handling

Deadlines are stored in SQLite as naive wall-time values in the configured
timezone.

The default timezone is:

```text
Asia/Kolkata
```

The deadline engine compares deadlines against the same configured local
timezone.

## Testing

From the project directory:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The current project snapshot passes its automated test suite.

## Current status

The current project snapshot contains:

- working portal/browser automation
- encrypted API interception and decryption
- subject and assignment discovery
- SQLite persistence
- change detection
- deadline parsing
- PDF text deadline extraction
- cached PDF extraction results
- configurable reminder windows
- desktop notifications
- 10-minute portal sync
- 10-minute full assignment summaries
- CLI operation
- Windows Task Scheduler support

It does **not** currently contain:

- an AI/LLM reasoning layer
- OCR for image-only PDFs
- the claimed Tkinter desktop GUI
- manual deadline override CLI commands

These distinctions are intentional so the README accurately describes the
current implementation rather than planned or previously proposed features.
