# ACETime — student time tracker

A runnable, self-hosted Trello integration with a student portal, per-student time confirmation, and weekly spreadsheet exports. Python 3.12+ standard library; SQLite persistence; Docker Compose included. The hosted interactive preview is a separate sample-data demonstration, not a connected production tracker.

## Workflow

| Trello list | Behavior |
| --- | --- |
| To do: (This Sprint) | No time recorded |
| In process (working) | Starts/resumes a timer for each assigned Trello member |
| In Process (paused) | Stops the timer and preserves earlier time |
| Completed | Stops the timer; the student portal requests individual verification |

Map your actual list IDs during setup; the Completed list can have a different name. Moving to any other list, archiving, deleting, or moving out of the board also stops timing. Reopening completed work starts a new interval; previously confirmed intervals remain separate.

**Group work:** every member receives the full elapsed interval while assigned, then confirms their actual contribution separately. Hours are not divided between members. Assignment changes split intervals at the event time. One student account maps to one Trello member. Individual accounts prevent students from viewing or confirming someone else's records. The instructor can review and verify on behalf of a selected student; the audit records who confirmed.

**Confirmation:** elapsed time is a ceiling; students can reduce it to account for breaks. An explanatory note is required for adjustments greater than one minute. Direct verification remains capped at elapsed time. Use Time corrections to request changes to a finished interval (including confirmed work) or add missing time; an instructor must approve each request. Verification appears in the tracker; this is not a Trello Power-Up and cannot show a modal inside Trello. Students must open the tracker. No messages/comments are posted to Trello.

## Jenkins and Kubernetes

Use the included `Jenkinsfile` and [JENKINS-DEPLOYMENT.md](JENKINS-DEPLOYMENT.md) to build and deploy with the Jenkins kubeconfig credential `cet-time`. The deployment includes persistent storage, HTTP ingress configuration, health probes, and Jenkins-managed application secrets. The pipeline defaults to `docker.io/cithit/cet-time`, credential `roseaw-dockerhub`, and the supplied NFS export. Set the HTTP public URL as a job parameter.

## Run locally with Docker Compose

1. Copy `.env.example` to `.env` and choose a unique `ADMIN_PASSWORD` (12+ characters). The admin username is `admin`. This initial password is stored as a salted PBKDF2 hash on first startup. Changing the variable later does not change the stored password.
2. Create a Trello API key and a token with read access to the board and permission to register webhooks. Put the API key, token, and application's secret in `TRELLO_KEY`, `TRELLO_TOKEN`, and `TRELLO_SECRET` respectively. Do not enter them into ChatGPT or browser JavaScript. Official instructions: https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/
3. Run `docker compose up --build -d`. For development without Docker: `set -a; source .env; set +a` then `python3 server.py`. Open `http://localhost:8080`.
4. For live webhooks, place the server behind your HTTPS reverse proxy or Kubernetes ingress. Set `PUBLIC_URL` to the exact external origin (e.g., `https://time.example.edu`) and restart. Proxy `/webhook` publicly to this app; all portal APIs enforce login. The webhook validates Trello's signature and board ID. Do not protect the webhook with an interactive sign-in wall. Keep the remaining application behind your institution's network access controls if required. Compose binds only localhost; a reverse proxy on that host can forward to port 8080.
5. Log in as the instructor. Connections → Load my Trello boards → choose the board → map the four lists → Activate tracking. This step starts tracking now; it does not assume any earlier hours. Existing working cards start at activation.
6. Click **Register Trello webhook**. The exact callback is `PUBLIC_URL + /webhook`; Trello validates it with HEAD. Registration is idempotent in the portal. The API app secret is needed for signature verification. Official webhook documentation: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/
7. Create student logins under Connections, assigning each to the correct board member. Distribute credentials through your usual secure channel. Students sign in to their own account. Group cards require actual card members, not only a text label or checklist assignment.
8. Click Refresh & sync as the instructor after setup. The server also reconciles Trello history on startup and every five minutes, including after downtime. Sync paginates board history from activation and deduplicates events. Webhooks keep recording even when no one has the portal open; the portal refreshes every 30 seconds on Overview and Verify. Refresh & sync also catches events between activation and webhook registration. New board members appear after instructor sync.

## Weekly export

Select a student and a Monday week start under Weekly report. The app uses America/New_York by default; change TIMEZONE if needed. Work is attributed to the calendar week when it occurred, including across midnight, week boundaries, and daylight-saving changes. A student's verified adjustment is distributed proportionally over their original intervals. Completed work from an earlier week appears in that earlier week when verified later.

Verified hours only are included by default. Optional unverified hours include active and paused work and are explicitly labeled. Combined mode puts comma-separated activity names and progress descriptions in one row with hours totaled. The alternative exports one row per activity. Click **Copy spreadsheet row**, select an empty Activity cell, and paste:

Activity | Progress | Hours Worked

The clipboard contains tabs between the three columns, with no header. Total hours are rounded once to two decimals; separately rounded activity rows may differ by 0.01 from the total. Copy is user-initiated; no automated email or spreadsheet write is configured.

## Persistence and recovery

SQLite stores baseline cards, immutable raw action payloads, credentials as hashes, expiring sessions, confirmations, and an audit table. Keep the Docker volume. Back up the database using SQLite's online backup API or stop the container before copying the database. Credentials are server-only environment variables. HTTPS sets secure session cookies; sessions expire after 12 hours. Login attempts are limited per account. The Kubernetes deployment uses the supplied NFS export, one app replica, serialized in-process database access, SQLite DELETE rollback journaling, and synchronous FULL. NFS must supply reliable locking and synchronization; do not run other applications, replicas, or external tools against the live database. See JENKINS-DEPLOYMENT.md for NFS preparation and the storage probe. This implementation is not an SSO or multi-institution service.

Mapping is locked after activation to preserve historical interpretation. For another board or changed list IDs, use a new database. If a late event changes a previously confirmed interval, its confirmation no longer matches and the affected interval must be verified again. Do an instructor history sync before preparing final weekly reports, especially after downtime. Current board names reflect the stored baseline plus captured rename actions. Trello access revocation or missed webhooks can make the view stale; the displayed refresh time alone is not a delivery guarantee.

Account provides password changes with current-password verification. Instructors can reset student passwords, deactivate/reactivate students, and revoke sessions. Password changes, resets, access changes, and revocation sign out all affected sessions. Share unique reset credentials through your usual secure channel; no recovery email or secret default password is supplied. The instructor can inspect the latest 200 audit entries under Needs attention. There is no audit-download UI.

## Validation

Run `python3 -m unittest -v`. Timing tests cover group work, pause/resume, reassignment, reordered events, reopening, late-event confirmation invalidation, baseline activation, weekly clipping, and daylight-saving calendar weeks. API integration tests additionally check login, role enforcement, signed webhooks, duplicate delivery, student-specific verification, and spreadsheet report totals.

Live Trello credentials/webhook delivery and your HTTPS ingress must be verified in your environment. The review, correction approval, account, and student navigation flows have local browser smoke coverage; live Trello and production ingress still need environment validation. No live Trello board has been modified by creating this package.

## Branding

ACETime uses navy blue `#1D2458` and red `#E41937`, sampled from the supplied Miami University Polytechnic logo. Colors are defined in `static/style.css`; the sidebar, login wordmark, and browser title use the ACETime name.

The workspace uses a navy sidebar, a light content area, consistent SVG navigation icons, status-colored task cards, and a board completion indicator. The overview counts and progress use existing visible task/session data; recorded and verified hours remain all-date totals. Login, reports, corrections, account forms, and instructor review share the same responsive components. Navigation wraps into a compact grid on phones, with Sign out kept visible. The interface uses local system fonts and includes keyboard focus styles, a skip link, active-page navigation labels, and reduced-motion support. Hover and focus transitions are subtle and do not move controls; phone layouts retain readable labels and visible account actions.

## Individual break reminders

Open **Break reminders** to review student break clocks. The default threshold is **4 hours**, with a warning up to **15 minutes before** it is reached. Instructors can change the default or set a threshold for one Trello member (0.25–24 hours), and can reset that member to the default. Settings and per-student snoozes persist in the existing database; no schema migration or new Jenkins credential is required.

A break clock measures a student's current continuous working streak across their assigned cards. Overlapping timers count once. If at least one card remains working, the streak continues; pausing/finishing all working cards ends the streak, and the next working interval starts a new one. A reminder does not move cards or alter recorded hours. Students should move their working cards to **In Process (paused)** when actually taking a break. Students can snooze their own warning for 15 minutes.

Every signed-in student receives an in-app reminder on any screen. **Enable browser notifications** requests permission for an optional desktop alert to that student; instructors viewing student clocks do not receive the student's desktop alerts. The app checks reminders every 30 seconds; browser background throttling, operating-system notification settings, or network failures can delay alerts. ACETime must remain open and signed in. No closed-browser push, email, Slack, or Trello messages are sent. This is a configurable work reminder, not a payroll or break-compliance system.

The sample preview includes **Show a near-4-hour example** on the Break reminders screen so you can try reminders without waiting four hours.

## Current deployment defaults

The Jenkins/Kubernetes path is HTTP-only for now. It uses NFS server `10.48.228.25`, export `/srv/nfs/roseaw`, a dedicated `cet-time` subdirectory, and a static Retain PV. No TLS Secret is required. Prepare the server-side directory before deployment and keep one application replica. Run the included `storage_check.py` on the mounted export before using student records; local tests cannot certify NFS locking/fsync reliability.
## Copy a weekly email report

Open **Student Workspace → Email report**, choose a Monday week start, and generate the email. Instructor accounts get a section for every registered student login (using its display name and linked Trello member); student accounts can generate only their own report. All students are included even when they have no verified hours. Create the student accounts in Connections if a student is missing.

The report uses the same calculations as Weekly report and defaults to verified hours. Include unverified time only when wanted; estimates are labeled. Edit the subject, greeting, or closing, then use **Copy subject** and **Copy email body** to paste into Gmail. On HTTP, copying falls back to selecting the text for Ctrl+C/Command+C if browser clipboard access is unavailable. Nothing is sent automatically, and no Gmail credentials or Google integration are needed.

## Work dates and task completion dates

Weekly report and Email report show daily task entries in the reporting timezone (America/New_York by default). Working intervals crossing midnight are split between work dates, including daylight-saving transitions. Verified adjustments are distributed proportionally across the original working intervals; daily reporting does not change total hours. Unfinished tasks can appear when Include unverified time is enabled.

Completed on shows the most recent recorded move into Completed for a currently completed task. It is independent of the work date and can fall outside the selected week. Reopened tasks show Not completed. Tasks already completed before tracking started show Date not recorded rather than an invented date. Spreadsheet copy retains the existing three-column format, with the work date in Activity and completion information in Progress. Email reports include work dates, durations, and completion dates for each student.



## Corrections, review, and account controls

**Time corrections** lets a student request a replacement total for one finished interval, including already confirmed work, or request a missing interval for a task assigned to them. A reason is required. Missing intervals must be in the past, at most 24 hours long, and cannot contain more claimed hours than elapsed time. A correction to a recorded interval can exceed its original elapsed time, up to 24 hours. Students can see only their own requests; instructors can select a registered student. Requests do not change reports until approved.

**Needs attention** is instructor-only. It includes tracking health, correction requests, completed intervals awaiting confirmation, overlapping task intervals, intervals longer than 12 hours, adjustments greater than 15 minutes, and the latest 200 audit entries. Approval and rejection require a review note. A request whose recorded interval or confirmed amount changed cannot be approved: reject it and request a fresh correction. Requests can be processed only once. Approved missing intervals and corrections flow through the same daily, weekly, and email calculations. Original Trello events and review decisions remain in the database.

Overlap notices appear on workspace screens and in the verification dialog, for current and historical overlaps. Warnings do not divide group hours or automatically subtract time. Confirm actual contribution or request a correction. Missing-time approval can itself create overlaps, so instructors should review the interval dates as well as the requested hours.

Tracking health distinguishes the last signed webhook received from the last successful full history sync. The single server process retries reconciliation every five minutes; errors and syncs older than 15 minutes flag potentially incomplete reports. A recent sync is not proof of webhook delivery. The manual Sync now button remains available. Full history replay and network sync currently serialize database access; large boards or Trello outages can delay portal requests. Keep a single replica.

The new correction, manual-session, and account-status tables are created automatically at startup without changing existing user columns. Back up the database before upgrading. Docker includes the new server module. These features require the connected app; the separate sample preview displays an availability message for the new screens. No automatic email or Trello messages are sent.


## Light and dark mode

Use **Dark mode** on the sign-in screen or in the workspace header to toggle the appearance. Light mode remains the initial default. The choice is saved in this browser, survives sign-in/sign-out and reloads, and updates other tabs on the same origin. When browser storage is unavailable, switching still works for the current page. The theme is applied before styles load to avoid showing a light page before a saved dark theme. Both themes cover reports, forms, task cards, alerts, and verification dialogs. This is a browser preference, not an account setting.


## Search, weekly review, and CSV downloads

The Overview task board can be searched by task or assigned student name and filtered by status and time verification. The existing student filter scopes both board records and time totals. Search/status/verification narrow the displayed cards without changing recorded totals. Clear filters resets the board filters.

**Weekly review** checks a selected Monday week for configuration, recent successful Trello reconciliation, unconfirmed intervals (including unfinished work), unresolved corrections, long-running timers, and overlapping intervals. Overlaps are advisory; the checklist does not lock or certify a timesheet. A stale sync or an unfinished timer should be reviewed before final reporting. Instructors can review the class or one registered student; students see only themselves. Totals use the same calculations as Weekly report and Email report.

Download **CSV** as daily task entries or student totals. CSV opens in Excel, includes a UTF-8 BOM, and treats task/student text as text to prevent spreadsheet formula execution. Class exports require instructor access and include every registered student, including zero-hour accounts. Student downloads cannot request another student's records. Verified hours are the default; unverified time is included only when explicitly selected and is labeled. Task rows are rounded individually to two decimals; summary totals are rounded once, so summing displayed daily rows can differ by a centihour.

## Forgotten timer reminders

Tasks recording continuously for **8 hours** are flagged on every workspace screen. Instructors can set the threshold from 0.5 to 72 hours under Weekly review. Touching intervals split by assignment changes still count as one continuous card/student timer; an actual pause resets the streak. Students can snooze their own task reminder for one hour. The reminder does not stop timers, change hours, or move Trello cards. Pause work in Trello and request corrections for inaccurate time. Reminders update while the portal is open and signed in, using the existing 30-second polling; no closed-browser push or messages are sent.

## Automatic database backups and recovery

The single application process creates a verified SQLite snapshot on its first backup-worker pass, then every **6 hours** after the latest successful snapshot. The newest **28** snapshots are retained by default. Snapshots use SQLite's online backup API while holding the app's database lock, pass `PRAGMA quick_check`, and are published by atomic rename only after completion. Failed snapshots do not trigger retention deletion; failed attempts retry after five minutes. Partial files are never listed as downloadable snapshots. Portal requests can wait during a large snapshot.

The instructor-only **Backups** screen shows schedule/status and saved snapshots, supports **Back up now**, and downloads database copies. Backup files contain account hashes, sessions, student records, and audit history: keep downloaded files private. Files are not served through the static file routes. Their default location is `backups/` beside `DATABASE_PATH`, inside the existing persistent data mount. No extra Jenkins credential is required.

Configure `BACKUP_INTERVAL_HOURS` (default 6), `BACKUP_KEEP` (default 28), and optionally `BACKUP_DIRECTORY` on the server. Docker Compose persists the default directory in its data volume; Kubernetes persists it under `/app/data/backups` on the existing NFS mount. A custom directory must be writable and mounted persistently. The built-in snapshots share the default storage failure domain: download/copy snapshots to independent storage for protection against loss of the server/export. This release does not configure off-site replication. Watch available space and backup status; local tests cannot certify production NFS durability.

To recover data, first stop the running app and preserve its current data directory. Restore a chosen snapshot into a **new** file for inspection:

```sh
python backups.py --restore /path/to/acetime-snapshot.sqlite3 --output /path/to/restored.sqlite3
```

The utility refuses to overwrite an existing output and verifies the restored database. With the app still stopped, retain the old database separately, replace the database at `DATABASE_PATH` with the verified restored file, restore the application's file ownership, and restart. Never replace or copy over a live SQLite database. Restoring an older snapshot also restores its older account/session state. Git backup branches protect code; database snapshots protect recorded data. Reverting code does not restore data.

Additional checks: `node test_theme.cjs`, `node test_productivity.cjs`, `node test_email_report.cjs`, and `node test_report_dates.cjs`. Python regression tests include backup rotation, failed-backup preservation, restoration, CSV permissions/totals, weekly readiness, and private reminder snoozing.
