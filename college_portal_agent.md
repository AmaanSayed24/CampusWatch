# College Portal Assignment Tracking Agent

## 1. Project Overview

**Project Name:** College Portal Assignment Tracking Agent  
**Suggested Internal Name:** CampusWatch  
**Language:** Python 3.12+  
**Primary Purpose:** Automatically monitor the college e-learning portal for new assignments, submission deadlines, changes, and pending work, then notify the student before deadlines.

The agent is intended for personal productivity. It behaves like a normal logged-in browser user and reads information that is already available through the student's portal account. It does not attempt to bypass authentication, CAPTCHA, access controls, or download restrictions.

---

## 2. Problem Statement

The college portal contains assignment information, but the portal does not provide sufficient personal reminders for upcoming submissions.

Typical manual workflow:

```text
Open portal
    -> Login
    -> Dashboard
    -> Classroom
    -> Select subject
    -> Check assignment section
    -> Open/check assignment
    -> Remember deadline
    -> Repeat for every subject
```

This is repetitive and easy to forget.

### Proposed solution

Create a local Python agent that periodically performs the same navigation automatically:

```text
Portal Login
    -> Dashboard
    -> Classroom
    -> Discover subjects
    -> Visit each subject
    -> Discover assignments
    -> Extract metadata
    -> Compare against local database
    -> Detect new/changed assignments
    -> Calculate urgency
    -> Send notifications
```

---

## 3. Core Objectives

### Must-have objectives

1. Log into the college portal securely.
2. Navigate from Dashboard -> Classroom -> Subject.
3. Discover all available subjects.
4. Check each subject for assignments.
5. Extract assignment title and available deadline/submission information.
6. Track previously seen assignments.
7. Detect newly added assignments.
8. Detect changed deadlines/details.
9. Calculate time remaining before submission.
10. Send reminder notifications.
11. Run automatically on a schedule.
12. Keep credentials and tracked data locally.

### Nice-to-have objectives

- Open the relevant portal assignment page directly from a notification.
- Generate a daily summary.
- Mark assignments as completed.
- Track submission status.
- Read assignment PDFs when required information is only visible inside the PDF viewer.
- OCR scanned PDFs as a fallback.
- Natural-language queries such as `What's due this week?`.
- Web dashboard for local monitoring.
- Missed-deadline alerts.
- Priority scoring.

---

## 4. Scope

### Version 1 scope

The first version should focus on reliable assignment tracking.

```text
Login
Subject discovery
Assignment discovery
Deadline extraction
Local persistence
New assignment detection
Deadline reminders
Desktop notifications
Scheduled execution
Logging/error handling
```

### Out of scope for Version 1

- Automatically submitting assignments.
- Bypassing CAPTCHA or MFA/OTP.
- Circumventing portal restrictions.
- Modifying or deleting portal data.
- Automatically answering assignments.
- Sharing credentials with external services.

---

## 5. Portal Navigation Model

Based on the current navigation flow:

```text
https://elearning.paruluniversity.ac.in/students/dashboard
        |
        v
    Dashboard
        |
        v
    Classroom
        |
        v
    Select Subject
        |
        v
 Assignment / relevant classroom section
        |
        v
 Assignment details / PDF viewer
```

The selectors for buttons, links, cards, and content should be discovered from the authenticated portal UI rather than hard-coded based on assumptions.

---

## 6. High-Level Architecture

```text
+--------------------------------------------------+
|              COLLEGE PORTAL                     |
| Login -> Dashboard -> Classroom -> Subjects     |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
|               BROWSER AUTOMATION                |
|                    Playwright                   |
|   - Login/session management                    |
|   - Navigation                                   |
|   - DOM extraction                               |
|   - PDF viewer interaction if required           |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
|                  PARSER LAYER                   |
|   - Subject parser                              |
|   - Assignment parser                           |
|   - Deadline parser                             |
|   - Status parser                               |
|   - PDF text extraction fallback                |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
|                  SERVICE LAYER                  |
|   Change detector                               |
|   Deadline engine                               |
|   Reminder engine                               |
|   Notification service                          |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
|                 STORAGE LAYER                   |
|                    SQLite                       |
| Subjects | Assignments | Runs | Notifications  |
+--------------------------+-----------------------+
                           |
                           v
+--------------------------------------------------+
|                USER INTERFACE                   |
| Desktop notifications / CLI / optional Web UI  |
+--------------------------------------------------+
```

---

## 7. Recommended Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| Language | Python 3.12+ | Main application |
| Browser automation | Playwright | Portal interaction |
| Browser | Chromium | Automated browser session |
| Database | SQLite | Local persistence |
| ORM / DB layer | SQLAlchemy | Database models and queries |
| Configuration | python-dotenv | Environment variables |
| Scheduling | APScheduler | Repeated monitoring |
| Notifications | plyer / Windows Toast | Desktop alerts |
| HTTP utilities | httpx | Optional API requests if needed |
| HTML parsing | BeautifulSoup4 | Optional static HTML parsing |
| PDF text extraction | pypdf / PyMuPDF | Optional PDF processing |
| OCR fallback | Tesseract via pytesseract | Optional scanned-document extraction |
| Logging | Python logging | Diagnostics |
| CLI | Typer | Command-line commands |
| Testing | pytest | Unit/integration tests |
| Formatting | Ruff | Linting/formatting |
| Type checking | mypy | Static checking (optional) |

### Important dependency principle

Do not install libraries simply because they are listed above. Start with the minimum set required for Version 1 and add PDF/OCR/web UI dependencies only when the actual portal behavior requires them.

---

## 8. Python Dependencies

### Initial `requirements.txt`

```txt
playwright
python-dotenv
sqlalchemy
apscheduler
plyer
typer
pydantic
pydantic-settings
pytest
ruff
```

### Optional PDF dependencies

```txt
pymupdf
pypdf
```

### Optional OCR dependencies

```txt
pytesseract
Pillow
```

OCR also requires the Tesseract OCR engine to be installed separately on Windows.

---

## 9. Folder Structure

Recommended production-ready structure:

```text
college-portal-agent/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   │
│   ├── automation/
│   │   ├── __init__.py
│   │   ├── browser.py
│   │   ├── login.py
│   │   ├── dashboard.py
│   │   ├── classroom.py
│   │   └── assignments.py
│   │
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── subject_parser.py
│   │   ├── assignment_parser.py
│   │   ├── deadline_parser.py
│   │   └── pdf_parser.py
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── repository.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── sync_service.py
│   │   ├── change_detector.py
│   │   ├── deadline_engine.py
│   │   ├── reminder_service.py
│   │   └── notification_service.py
│   │
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── scheduler.py
│   │
│   ├── cli/
│   │   ├── __init__.py
│   │   └── commands.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── dates.py
│       ├── hashing.py
│       └── logging.py
│
├── tests/
│   ├── test_deadline_engine.py
│   ├── test_change_detector.py
│   ├── test_parsers.py
│   └── test_repository.py
│
├── data/
│   ├── portal.db
│   ├── browser-profile/
│   └── exports/
│
├── logs/
│   └── agent.log
│
├── screenshots/
│   └── .gitkeep
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── README.md
└── run_agent.py
```

---

## 10. File-by-File Responsibilities

### `run_agent.py`

Main entry point for starting the application.

Example responsibilities:

```text
Initialize configuration
Initialize logging
Initialize database
Start requested command
```

### `app/main.py`

Application orchestration layer.

Example:

```python
sync_service.run_sync()
```

### `app/config/settings.py`

Loads configuration from `.env`.

Potential settings:

```text
PORTAL_URL
PORTAL_USERNAME
PORTAL_PASSWORD
CHECK_INTERVAL_MINUTES
REMINDER_HOURS
BROWSER_HEADLESS
NOTIFICATION_ENABLED
```

### `app/automation/browser.py`

Creates and manages Playwright browser/context/page objects.

Responsibilities:

- Launch browser.
- Reuse persistent session.
- Configure timeouts.
- Capture screenshots on failures.
- Close browser safely.

### `app/automation/login.py`

Contains only login-related logic.

Responsibilities:

- Open login page.
- Detect whether the session is already authenticated.
- Fill username/password when configured.
- Detect OTP/CAPTCHA and stop for manual interaction.
- Confirm successful login.

### `app/automation/dashboard.py`

Handles dashboard navigation.

```text
Dashboard -> Classroom
```

### `app/automation/classroom.py`

Handles subject discovery.

Responsibilities:

- Find classroom section.
- Collect subject links/cards/IDs.
- Return normalized `Subject` data.

### `app/automation/assignments.py`

Visits a subject and discovers assignment-related content.

Responsibilities:

- Open subject.
- Locate assignment area.
- Extract assignment records.
- Identify assignment detail pages.
- Open PDF viewer where necessary.

### `app/parsers/assignment_parser.py`

Transforms raw DOM data into normalized assignment objects.

### `app/parsers/deadline_parser.py`

Normalizes dates from different portal formats.

Example:

```text
15/09/2026
15-09-2026
Sep 15, 2026
15 September 2026
```

All values should be converted into a consistent timezone-aware datetime.

### `app/parsers/pdf_parser.py`

Optional fallback for assignment PDFs.

Preferred order:

```text
1. Read metadata from assignment webpage
2. Read PDF text directly if legitimately available to the browser/session
3. Inspect browser PDF viewer text
4. OCR only if document is image-based
```

Do not make PDF processing the primary strategy unless actual portal testing proves it necessary.

### `app/database/models.py`

Defines SQLAlchemy models.

### `app/database/repository.py`

Provides database operations such as:

```text
get_subjects()
upsert_subject()
get_assignment()
upsert_assignment()
get_due_soon_assignments()
record_sync_run()
record_notification()
```

### `app/services/sync_service.py`

Main monitoring workflow.

```text
Login
-> Discover subjects
-> Visit subjects
-> Parse assignments
-> Save/update database
-> Detect changes
-> Trigger reminders
```

### `app/services/change_detector.py`

Compares newly scraped assignment information against the database.

Detect:

- New assignment.
- Deadline changed.
- Title changed.
- Subject association changed.
- Assignment removed/hidden.

### `app/services/deadline_engine.py`

Calculates urgency.

Suggested states:

```text
OVERDUE
DUE_TODAY
DUE_WITHIN_24H
DUE_WITHIN_3_DAYS
DUE_WITHIN_7_DAYS
FUTURE
NO_DEADLINE
```

### `app/services/reminder_service.py`

Determines whether a reminder should be generated.

### `app/services/notification_service.py`

Sends desktop notifications.

Possible future providers:

```text
Windows notification
Telegram
Email
Discord webhook
```

### `app/scheduler/scheduler.py`

Runs synchronization periodically.

Suggested default:

```text
Every 60 minutes during normal hours
```

A manual `sync-now` command should always be available.

---

## 11. Database Design

SQLite is recommended for the initial project because everything can run locally without requiring a server.

### Table: `subjects`

```text
id                 INTEGER PRIMARY KEY
portal_id          TEXT UNIQUE
name               TEXT NOT NULL
url                TEXT
active             BOOLEAN
created_at         DATETIME
updated_at         DATETIME
```

### Table: `assignments`

```text
id                 INTEGER PRIMARY KEY
portal_id          TEXT
subject_id         INTEGER
external_key       TEXT UNIQUE
 title              TEXT
 description        TEXT
assigned_at        DATETIME
 deadline           DATETIME
status             TEXT
source_url         TEXT
content_hash       TEXT
first_seen_at      DATETIME
last_seen_at       DATETIME
created_at         DATETIME
updated_at         DATETIME
```

Remove the accidental leading space before `title` when implementing the actual SQLAlchemy model.

### Table: `notifications`

```text
id                 INTEGER PRIMARY KEY
assignment_id      INTEGER
notification_type  TEXT
sent_at            DATETIME
channel            TEXT
```

### Table: `sync_runs`

```text
id                 INTEGER PRIMARY KEY
started_at         DATETIME
finished_at        DATETIME
status             TEXT
subjects_checked   INTEGER
assignments_found  INTEGER
error_message      TEXT
```

---

## 12. Assignment Identity

A stable assignment identifier is critical so the agent does not create duplicates on every scan.

Preferred identity sources, in order:

```text
1. Portal's assignment ID
2. Assignment detail URL
3. Subject ID + title + deadline
4. Stable content hash as fallback
```

Do not use the display order (`Assignment 1`, `Assignment 2`) as the permanent identifier because portals may reorder items.

---

## 13. Change Detection

### New assignment

Condition:

```text
assignment external_key does not exist in database
```

Action:

```text
Insert record
Send NEW_ASSIGNMENT notification
```

### Deadline changed

Condition:

```text
old_deadline != new_deadline
```

Action:

```text
Update record
Send DEADLINE_CHANGED notification
```

### Existing unchanged assignment

Condition:

```text
external_key exists
content_hash unchanged
```

Action:

```text
Update last_seen_at only
Do not notify
```

---

## 14. Reminder Rules

Suggested default policy:

```text
New assignment discovered       -> Notify immediately
7 days remaining                -> Notify once
3 days remaining                -> Notify once
24 hours remaining              -> Notify once
3 hours remaining               -> Notify once
Deadline passed                 -> Optional overdue notification
```

The exact timings should be configurable.

Example configuration:

```env
REMINDER_WINDOWS=7d,3d,24h,3h
```

The application should prevent duplicate reminders through the `notifications` table.

---

## 15. Example Notification Messages

### New assignment

```text
📚 New Assignment

Subject: Data Structures
Assignment: Searching and Sorting
Due: 15 September 2026, 11:59 PM

Open portal: <link>
```

### 3-day reminder

```text
⏰ Assignment Reminder

Data Structures — Searching and Sorting
Due in 3 days.

Deadline: 15 September 2026
```

### Due today

```text
🚨 Due Today

Java — Exception Handling Assignment
Deadline: Today, 11:59 PM
```

### Deadline changed

```text
🔄 Deadline Updated

Web Technology — PHP Assignment
Old: 17 September 2026
New: 19 September 2026
```

---

## 16. Daily Summary

A daily summary can be generated at a configurable time.

Example:

```text
COLLEGE DAILY SUMMARY

🔴 Due today: 1
🟠 Due within 3 days: 2
🟡 Due within 7 days: 4
🆕 New since yesterday: 2

Today's tasks
1. Java — Exception Handling
2. Data Structures — Searching
```

---

## 17. PDF Handling Strategy

Assignment PDFs may be displayed through a viewer and may not expose a normal download button.

The agent should not attempt to circumvent technical restrictions.

### Extraction strategy

```text
                         Assignment page
                               |
                               v
               Is deadline/title visible in DOM?
                       /                \
                     YES                 NO
                      |                   |
                      v                   v
                Parse DOM        Is relevant PDF text
                                   visible to browser?
                                      /      \
                                    YES       NO
                                     |         |
                                     v         v
                              Extract text    OCR fallback
```

### Priority

The agent should always prefer page metadata over PDF parsing because page-level metadata is usually more stable and faster to extract.

### PDF data worth extracting

Only extract fields needed for tracking, such as:

```text
Assignment title
Due date
Submission instructions
Optional topic/description
```

Do not store unnecessary copies of documents.

---

## 18. Authentication and Security

### Never hard-code credentials

Bad:

```python
USERNAME = "myusername"
PASSWORD = "mypassword"
```

Preferred:

```env
PORTAL_USERNAME=your_username
PORTAL_PASSWORD=your_password
```

### Better approach: persistent local browser session

For portals involving OTP/MFA/CAPTCHA:

```text
First run
 -> Launch visible browser
 -> User logs in manually
 -> User completes OTP/CAPTCHA
 -> Browser session is persisted locally

Future runs
 -> Reuse session
 -> Check whether still authenticated
 -> Continue scanning
```

This reduces the need for the automation to handle MFA.

### Credential rules

- Never commit `.env` to Git.
- Never print passwords in logs.
- Never send credentials to notification services.
- Restrict local browser-profile permissions where practical.
- Keep the database local.

---

## 19. `.env.example`

```env
PORTAL_URL=https://elearning.paruluniversity.ac.in/students/dashboard
PORTAL_USERNAME=
PORTAL_PASSWORD=

BROWSER_HEADLESS=false
BROWSER_PROFILE_DIR=data/browser-profile

CHECK_INTERVAL_MINUTES=60

REMINDER_WINDOWS=7d,3d,24h,3h
DAILY_SUMMARY_TIME=08:00

NOTIFICATION_ENABLED=true
LOG_LEVEL=INFO
```

If persistent browser authentication is used, username/password variables may be unnecessary after the first manual login.

---

## 20. `.gitignore`

```gitignore
# Environment
.env

# Python
__pycache__/
*.py[cod]
.venv/
venv/

# Database
*.db

# Browser session
/data/browser-profile/

# Logs
/logs/

# Generated screenshots
/screenshots/

# Test/cache
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

---

## 21. Browser Automation Principles

### Prefer semantic selectors

Prefer:

```python
page.get_by_role("button", name="Classroom")
```

over fragile selectors such as:

```python
page.locator("div:nth-child(4) > div:nth-child(2)")
```

### Use stable identifiers

Prefer:

```text
id
name
href
aria-label
role
data-* attributes
```

### Use explicit waits

Use Playwright's locator auto-waiting and explicit conditions rather than fixed `sleep()` delays whenever possible.

Bad:

```python
await page.wait_for_timeout(5000)
```

Better:

```python
await page.get_by_text("Classroom").wait_for()
```

### Failure screenshots

On a navigation/parser error:

```text
screenshots/
    login_failure_2026-09-08_1015.png
    classroom_failure_2026-09-08_1018.png
```

This makes debugging portal UI changes much easier.

---

## 22. Main Synchronization Workflow

Pseudo-code:

```python
async def synchronize():
    browser = await browser_manager.get_browser()

    try:
        page = await login_service.ensure_authenticated(browser)

        await dashboard.open(page)
        subjects = await classroom.discover_subjects(page)

        for subject in subjects:
            try:
                assignments = await assignment_scraper.get_assignments(
                    page,
                    subject
                )

                for assignment in assignments:
                    normalized = parser.normalize(assignment)
                    change = change_detector.compare(normalized)
                    repository.upsert_assignment(normalized)

                    if change.is_new:
                        reminder_service.notify_new(normalized)

                    elif change.deadline_changed:
                        reminder_service.notify_deadline_change(change)

            except Exception as exc:
                logger.exception(
                    "Failed to process subject %s",
                    subject.name
                )

        reminder_service.process_due_soon()
        repository.record_successful_sync()

    except Exception:
        repository.record_failed_sync()
        raise

    finally:
        await browser_manager.close()
```

---

## 23. Suggested CLI

The project should be usable manually even when the scheduler is disabled.

Example commands:

```bash
python run_agent.py sync
python run_agent.py sync-now
python run_agent.py assignments
python run_agent.py upcoming
python run_agent.py overdue
python run_agent.py status
python run_agent.py test-notification
```

Example output:

```text
$ python run_agent.py upcoming

Upcoming assignments
--------------------
Data Structures     Searching & Sorting       15 Sep 2026
Java                Exception Handling        18 Sep 2026
Web Technology      PHP Assignment            20 Sep 2026
```

---

## 24. Scheduler Design

### Recommended schedule

Do not scrape continuously.

Start with:

```text
Every 60 minutes
```

Optionally reduce frequency during nighttime.

Example:

```text
08:00 - 22:00 -> every 60 minutes
22:00 - 08:00 -> no automatic checks
```

The user should be able to force a manual synchronization at any time.

---

## 25. Error Handling

Expected failures include:

```text
Internet unavailable
Portal unavailable
Session expired
Login failed
OTP required
CAPTCHA required
Subject page layout changed
Assignment section changed
Deadline format changed
PDF viewer changed
Timeout
Database locked
```

### Behavior

The agent should:

1. Log the failure.
2. Capture a screenshot where applicable.
3. Continue with the next subject when safe.
4. Avoid sending misleading notifications.
5. Mark the run as partially failed if required.
6. Notify the user only for important failures.

Example:

```text
⚠️ College portal sync issue

The portal could not be scanned successfully at 10:00 AM.
The browser session may have expired.
Please run: python run_agent.py sync-now
```

---

## 26. Logging

Suggested log levels:

```text
DEBUG
INFO
WARNING
ERROR
CRITICAL
```

Example:

```text
2026-09-08 10:00:04 INFO  Starting portal sync
2026-09-08 10:00:08 INFO  Authenticated successfully
2026-09-08 10:00:10 INFO  Found 6 subjects
2026-09-08 10:00:19 INFO  Data Structures: 3 assignments
2026-09-08 10:00:24 INFO  New assignment detected: Searching & Sorting
2026-09-08 10:00:31 WARNING Java classroom page took longer than expected
2026-09-08 10:00:42 INFO  Sync completed
```

Never log:

```text
Password
Session cookies
Authentication tokens
OTP
```

---

## 27. Timezone Handling

Use one consistent timezone for the system.

Recommended:

```text
Asia/Kolkata
```

Internally, store timezone-aware datetimes whenever possible.

This matters because a deadline such as:

```text
15 September 2026, 11:59 PM
```

must not accidentally be converted to another timezone and trigger a reminder at the wrong time.

---

## 28. Data Lifecycle

The agent should retain only what is necessary for tracking.

```text
Portal data
    -> Normalize
    -> Save assignment metadata
    -> Detect changes
    -> Notify
```

For the basic version, storing full PDF files is unnecessary.

Store:

```text
Title
Subject
Deadline
Portal URL
Status
Timestamps
Stable ID/hash
```

---

## 29. Status Model

Suggested assignment status values:

```text
PENDING
COMPLETED
OVERDUE
CANCELLED
UNKNOWN
```

In Version 1, the portal's explicit submission status should be used when available.

If the portal has no submission status, the user can manually mark an assignment as completed locally.

---

## 30. Future Smart Features

### A. Priority scoring

Score an assignment based on:

```text
Deadline proximity
Difficulty/estimated effort
Whether already started
Whether overdue
Subject priority
```

Example:

```text
Priority = CRITICAL
Data Structures assignment
Due in 8 hours
```

### B. Weekly workload report

```text
THIS WEEK

Assignments: 7
Due: 5
Completed: 2
Overdue: 0
```

### C. Calendar integration

Potential future integrations:

```text
Google Calendar
Microsoft Outlook Calendar
ICS export
```

### D. Telegram notifications

Potential later architecture:

```text
Agent -> Telegram Bot API -> Phone notification
```

### E. Local web dashboard

Potential stack:

```text
FastAPI + Jinja/React
```

Dashboard sections:

```text
Today
Upcoming
Overdue
Subjects
Sync history
Settings
```

### F. Natural-language assistant

A future local UI can support commands such as:

```text
What's due this week?
Show only Java assignments.
Which assignments are due tomorrow?
What was added today?
```

This should be added only after the underlying tracking system is reliable.

---

## 31. Optional AI Layer

AI is **not required** for the core agent.

The basic tracker is deterministic and should remain that way.

AI could later be used for:

```text
Summarizing assignment descriptions
Categorizing assignments
Estimating workload from instructions
Answering natural-language queries
```

AI should not be responsible for basic deadline extraction when the portal already provides structured text.

---

## 32. Testing Strategy

### Unit tests

Test:

```text
Date parsing
Deadline calculation
Change detection
Assignment identity
Reminder deduplication
Repository operations
```

### Integration tests

Test:

```text
Login/session detection
Dashboard navigation
Subject discovery
Assignment discovery
Portal parsing
```

### Regression tests

When the portal UI changes, preserve a small set of saved HTML fixtures or controlled test pages where permitted so parsers can be tested without repeatedly hitting the live portal.

---

## 33. Development Phases

### Phase 1 — Browser proof of concept

Goal:

```text
Open portal
Login manually
Navigate Dashboard -> Classroom
Select one subject
Print page structure
```

Deliverable:

```text
Working Playwright navigation
```

### Phase 2 — Subject discovery

Goal:

```text
Find every subject automatically
```

Deliverable:

```text
List[Subject]
```

### Phase 3 — Assignment extraction

Goal:

```text
Read assignment titles + deadlines
```

Deliverable:

```text
List[Assignment]
```

### Phase 4 — SQLite persistence

Goal:

```text
Save assignments and subjects
```

Deliverable:

```text
portal.db
```

### Phase 5 — Change detection

Goal:

```text
Detect new assignments and deadline changes
```

### Phase 6 — Notifications

Goal:

```text
Desktop reminder system
```

### Phase 7 — Scheduler

Goal:

```text
Automatic hourly monitoring
```

### Phase 8 — PDF fallback

Only implement after confirming PDF content is actually necessary.

### Phase 9 — Dashboard and smart features

Add only after the core system is stable.

---

## 34. Definition of Done for MVP

The MVP is complete when all of the following work reliably:

```text
[ ] Portal session can be opened
[ ] Authentication can be completed safely
[ ] Dashboard can be reached
[ ] Classroom can be opened
[ ] Subjects can be discovered automatically
[ ] Each subject can be scanned
[ ] Assignments can be detected
[ ] Deadlines can be extracted when displayed by portal
[ ] Data is saved to SQLite
[ ] Duplicate assignments are prevented
[ ] New assignments generate notifications
[ ] Upcoming deadlines generate notifications
[ ] Notification duplicates are prevented
[ ] Agent can run manually
[ ] Agent can run on a schedule
[ ] Errors are logged
[ ] Sensitive credentials are not logged or committed
```

---

## 35. Recommended First Implementation

Do **not** start by implementing the complete project at once.

Build the smallest reliable vertical slice:

```text
Playwright
   ↓
Login/session
   ↓
Dashboard
   ↓
Classroom
   ↓
ONE subject
   ↓
Print assignment elements
```

Once the actual HTML/DOM of one subject is known, implement the parser around real selectors.

Then expand:

```text
1 subject
   -> all subjects
   -> database
   -> notifications
   -> scheduler
   -> PDF fallback
```

This minimizes fragile code and makes debugging much easier.

---

## 36. Example Project Startup

### Create project

```bash
mkdir college-portal-agent
cd college-portal-agent
python -m venv .venv
.venv\Scripts\activate
```

### Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### Create initial files

```text
app/
run_agent.py
requirements.txt
.env.example
.gitignore
README.md
```

### First run

```bash
python run_agent.py sync-now
```

For the first development run, keep the browser visible:

```env
BROWSER_HEADLESS=false
```

This makes portal navigation and selector debugging much easier.

---

## 37. Recommended Architecture Principle

The most important design decision is to keep the system modular:

```text
Portal automation != Parsing != Database != Notifications != Scheduler
```

This means a portal UI change should primarily affect the automation/parser layer rather than the whole application.

For example:

```text
Portal HTML changed
      |
      v
assignment.py / assignment_parser.py
      |
      v
Database + reminders remain unchanged
```

This is the key difference between a quick script and a maintainable agent.

---

## 38. Final System Concept

```text
                         +------------------+
                         | College Portal   |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         | Playwright Agent |
                         +--------+---------+
                                  |
             +--------------------+--------------------+
             |                    |                    |
             v                    v                    v
        Authentication       Subject Scanner     Assignment Scanner
             |                    |                    |
             +--------------------+--------------------+
                                  |
                                  v
                         +------------------+
                         | Normalized Data  |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         | SQLite Database  |
                         +--------+---------+
                                  |
                     +------------+------------+
                     |                         |
                     v                         v
              Change Detector           Deadline Engine
                     |                         |
                     +------------+------------+
                                  |
                                  v
                         +------------------+
                         | Reminder Service |
                         +--------+---------+
                                  |
                  +---------------+----------------+
                  |               |                |
                  v               v                v
             Desktop          Telegram         Email
           Notification       (future)         (future)
```

---

## 39. Project Summary

**CampusWatch** is a personal Python automation agent that turns a college learning portal into a proactive assignment reminder system.

The core strategy is:

```text
Observe -> Extract -> Store -> Compare -> Remind
```

The initial implementation should remain simple and deterministic. Browser automation, local SQLite persistence, deadline logic, and desktop notifications are enough to deliver the main value. PDF processing and AI should be treated as optional extensions rather than prerequisites.

The safest and most maintainable implementation is one that uses the authenticated portal exactly as a normal user would, keeps credentials/session data on the user's own machine, and never attempts to bypass portal security controls.
