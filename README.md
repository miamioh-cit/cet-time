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

**Confirmation:** elapsed time is a ceiling; students can reduce it to account for breaks. An explanatory note is required for adjustments greater than one minute. This version does not support adding time above elapsed time, editing an already confirmed submission, or manual entries. Verification appears in the tracker; this is not a Trello Power-Up and cannot show a modal inside Trello. Students must open the tracker. No messages/comments are posted to Trello.

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
8. Click Refresh & sync as the instructor after setup and after any downtime. Sync paginates board history from activation and deduplicates events. Webhooks keep recording even when no one has the portal open; the portal refreshes every 30 seconds on Overview and Verify. Refresh & sync also catches events between activation and webhook registration. New board members appear after instructor sync.

## Weekly export

Select a student and a Monday week start under Weekly report. The app uses America/New_York by default; change TIMEZONE if needed. Work is attributed to the calendar week when it occurred, including across midnight, week boundaries, and daylight-saving changes. A student's verified adjustment is distributed proportionally over their original intervals. Completed work from an earlier week appears in that earlier week when verified later.

Verified hours only are included by default. Optional unverified hours include active and paused work and are explicitly labeled. Combined mode puts comma-separated activity names and progress descriptions in one row with hours totaled. The alternative exports one row per activity. Click **Copy spreadsheet row**, select an empty Activity cell, and paste:

Activity | Progress | Hours Worked

The clipboard contains tabs between the three columns, with no header. Total hours are rounded once to two decimals; separately rounded activity rows may differ by 0.01 from the total. Copy is user-initiated; no automated email or spreadsheet write is configured.

## Persistence and recovery

SQLite stores baseline cards, immutable raw action payloads, credentials as hashes, expiring sessions, confirmations, and an audit table. Keep the Docker volume. Back up the database using SQLite's online backup API or stop the container before copying the database. Credentials are server-only environment variables. HTTPS sets secure session cookies; sessions expire after 12 hours. Login attempts are limited per account. The Kubernetes deployment uses the supplied NFS export, one app replica, serialized in-process database access, SQLite DELETE rollback journaling, and synchronous FULL. NFS must supply reliable locking and synchronization; do not run other applications, replicas, or external tools against the live database. See JENKINS-DEPLOYMENT.md for NFS preparation and the storage probe. This implementation is not an SSO or multi-institution service.

Mapping is locked after activation to preserve historical interpretation. For another board or changed list IDs, use a new database. If a late event changes a previously confirmed interval, its confirmation no longer matches and the affected interval must be verified again. Do an instructor history sync before preparing final weekly reports, especially after downtime. Current board names reflect the stored baseline plus captured rename actions. Trello access revocation or missed webhooks can make the view stale; the displayed refresh time alone is not a delivery guarantee.

Students have no password-change/recovery screen in this initial version. Plan an administrator-managed account recovery process before broad rollout; there is no secret default password. For a small pilot, create accounts with unique initial credentials. The admin can inspect the audit table directly; there is no audit-export UI.

## Validation

Run `python3 -m unittest -v`. Timing tests cover group work, pause/resume, reassignment, reordered events, reopening, late-event confirmation invalidation, baseline activation, weekly clipping, and daylight-saving calendar weeks. API integration tests additionally check login, role enforcement, signed webhooks, duplicate delivery, student-specific verification, and spreadsheet report totals.

Live Trello credentials/webhook delivery and your HTTPS ingress must be verified in your environment. Browser rendering was not tested in the build environment. No live Trello board has been modified by creating this package.

## Branding

ACETime uses navy blue `#1D2458` and red `#E41937`, sampled from the supplied Miami University Polytechnic logo. Colors are defined in `static/style.css`; the sidebar, login wordmark, and browser title use the ACETime name.

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

