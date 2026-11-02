# LMS QA Automation

Python + Playwright, Windows, read-only Blackboard and Canvas inspection.
Tested locally with Python 3.12 and Playwright 1.64.1. Microsoft Edge must be installed for live runs.

## What this version does

- Blackboard Ultra outline inventory: expands observed folder/module toggles, records titles, IDs, parent relationships, URLs where exposed and visible/hidden labels.
- Canvas Modules inventory and existing page image/link QC with screenshots and HTML evidence.
- Conservative title comparison between both inventories; duplicate titles require review.
- Explicit BLOCKED, INCOMPLETE and NOT TESTED outcomes. Blackboard COLLECTED means outline collection only, not course QA passed.
- No migration, content edits, automatic repairs, AI API calls, video playback certification or academic validation.

## First-time setup on your or your TL's computer

Download/extract the source repository. Open **standalone Windows PowerShell**, not an agent-run terminal.
Navigate to the extracted folder (replace the example path):

```powershell
cd "D:\QA LMS"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe run_tests.py
```

`setup.ps1` runs the first three setup steps if local script policy permits it. Do not weaken execution policy just to run the helper; use the commands above instead.
Do not copy .venv from another computer. Proxy/package download restrictions may require your institution's IT.

## Web Control Dashboard (Recommended)

Run the interactive local Web Dashboard for a visual UI, live error cards, and embedded report preview:

```powershell
# Double click start_dashboard.bat OR run in PowerShell:
.\start_dashboard.bat
# Or using Python directly:
.\.venv\Scripts\python.exe web_dashboard_server.py --port 8080
```
- Open `http://127.0.0.1:8080` in your browser.
- Select **Canvas QC**, **Blackboard Inventory**, **Full Workflow Compare**, or **Quick Mock Test**.
- No terminal typing needed: confirm university logins with a single click in the Web UI.
- Direct tables listing broken images (with screenshot evidence popups), broken links (HTTP 404/500), and missing items.
- Interactive HTML report viewer with new-window & download options.

## Full read-only workflow (Command-Line)

1. Edge opens Blackboard course `_268444_1`.
2. Log in inside that window, complete MFA, confirm Financial Technology Individual Project MEC outline is visible.
3. Return to PowerShell and type `SCAN`, then Enter. Empty Enter cancels collection.
4. After inventory finishes, the Canvas scanner opens its own Edge window for course 350.
5. Log in there, verify the course and press Enter only when the Canvas scanner asks.
6. Read the printed statuses and reports. Login/access failures are not content passes.

Alternative browser: `--browser chrome`. Existing ordinary browser cookies are not shared.
The course status Closed/Unpublished or a teacher session does not prove student access.

## Individual operations

```powershell
# Blackboard inventory
.\.venv\Scripts\python.exe -m qc_core.bb_scanner
# Canvas QC
.\.venv\Scripts\python.exe run_qc.py --browser msedge --course-url "https://www.ole.mumbai.bristol.ac.uk/courses/350"
# Recompare saved inventories, without logging in; verify timestamps first
.\.venv\Scripts\python.exe run_workflow.py --compare-only
```

## Reports (local only)

- reports/blackboard_inventory.json (plus timestamped copy)
- reports/canvas_inventory.json
- reports/canvas_qc_results.json
- reports/latest_report.html (Canvas QC)
- reports/comparison_report.html and comparison_report.json

Canvas discovery covers observed Modules items only, excludes items outside Modules, and does not certify inventory completeness. Therefore comparison remains INCOMPLETE when target coverage is unverified. A MATCHED_TITLE row is a candidate correspondence, not matching file/text/media proof. Missing titles against incomplete inventories are NOT TESTED, not confirmed missing.
Blackboard visibility records item labels; effective student visibility also depends on ancestor restrictions, course state and enrollment. Unknown labels or incomplete expansion produce INCOMPLETE.

Images pending load are NOT TESTED. HTTP checks establish reachability only; a generic HTTP 200 page may be a soft error. Authentication restrictions, rate limits, network/server failures need review. Embedded video/audio playback is NOT TESTED. Individual passing pages do not mean all course QA passed.

Exit codes: Canvas 0 implemented checks passed, 1 defects, 2 blocked/incomplete; Blackboard 0 outline COLLECTED, 2 otherwise; comparison 2 because content equivalence remains unverified; 130 cancellation. Nonzero review statuses are not necessarily program crashes.

## GitHub / TL handoff

Use an institution-approved private repository. Share source, requirements, README, setup scripts, tests and synthetic test_samples only. Never share .auth, .venv, .env, reports, screenshots or real course assets. .gitignore excludes these; it cannot remove secrets already committed. Review staged files before pushing. Backups and broken *_backup.py files are excluded.
Each operator must have their own university course access. Passwords/MFA are entered only in the LMS browser. Saved session files can impersonate the user: keep them private, delete when no longer needed.

## Acceptance still required

Local tests are not real-course acceptance. Run both actual course inventories, review all expansion/coverage issues and timestamped results, manually confirm representative nested items and student access, review the eight previously flagged links in a fresh scan, and test videos separately. Auto-fix and vision-AI work need separate verified source-to-target mappings and institution-approved integration. No zero-defect guarantee is claimed.

Official references:
- https://playwright.dev/python/docs/auth
- https://playwright.dev/python/docs/browsers
- https://developerdocs.instructure.com/services/canvas/resources/modules
- https://developerdocs.instructure.com/services/canvas/basics/file.pagination
