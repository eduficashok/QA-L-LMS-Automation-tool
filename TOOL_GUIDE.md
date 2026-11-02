# LMS QA Automation Tool — Complete Guide
**Version:** 1.0 | **Platform:** Windows / macOS | **Language:** Python 3.12  
**Author:** QA Team — Bristol University LMS Migration Project

---

## Table of Contents
1. [What is this Tool?](#1-what-is-this-tool)
2. [System Requirements](#2-system-requirements)
3. [Project Structure](#3-project-structure)
4. [First-Time Setup](#4-first-time-setup)
5. [How to Launch the Tool](#5-how-to-launch-the-tool)
6. [Architecture — How it Works Inside](#6-architecture--how-it-works-inside)
7. [Scan Modes — What Each Mode Does](#7-scan-modes--what-each-mode-does)
8. [What Gets Checked — Full QC Breakdown](#8-what-gets-checked--full-qc-breakdown)
9. [Link Check Logic — Status Codes Explained](#9-link-check-logic--status-codes-explained)
10. [Understanding the HTML Report](#10-understanding-the-html-report)
11. [SKIPPED Items — Why They Are Skipped](#11-skipped-items--why-they-are-skipped)
12. [SSO / MFA Login Flow](#12-sso--mfa-login-flow)
13. [Online Sharing — Cloudflare / LocalTunnel](#13-online-sharing--cloudflare--localtunnel)
14. [Positive Outcomes](#14-positive-outcomes)
15. [Negative Outcomes & Known Limitations](#15-negative-outcomes--known-limitations)
16. [Safety Guarantees — What the Tool NEVER Does](#16-safety-guarantees--what-the-tool-never-does)
17. [Will it Disturb LMS / Blackboard?](#17-will-it-disturb-lms--blackboard)
18. [Troubleshooting Common Issues](#18-troubleshooting-common-issues)
19. [Glossary](#19-glossary)

---

## 1. What is this Tool?

The **LMS QA Automation Tool** is a read-only automated quality control scanner built for Bristol University's LMS migration project (Blackboard Ultra → Canvas).

### The Problem it Solves
Manually checking every page, image, link, and video embed inside large university courses takes **hours per course** and is prone to human error. A QA analyst checking 50 modules × 10 pages each would need to inspect **500+ pages** manually.

### The Solution
This tool uses a **real browser** (Chromium) controlled by automation code to:
- Visit every module and page in a Canvas course automatically
- Check every image for rendering failures
- Check every hyperlink for HTTP errors
- Record all embedded media (videos, iframes)
- Inventory every item in a Blackboard Ultra course
- Cross-compare Blackboard vs Canvas content titles

A full course scan that takes **3–4 hours manually** is completed in **5–15 minutes automatically**, with a professional HTML report as evidence.

---

## 2. System Requirements

### Minimum Requirements

| Component | Requirement |
|---|---|
| **Operating System** | Windows 10/11 or macOS 12+ |
| **Python** | Version 3.12+ |
| **RAM** | 4 GB minimum (8 GB recommended) |
| **Disk Space** | 500 MB free (for Playwright browsers) |
| **Internet** | Active connection required |
| **Browser** | Chromium (auto-downloaded by Playwright) |

### Python Packages Required
```
playwright==1.64.1
```
> Playwright automatically downloads Chromium (~150 MB) on first run.

### NOT Required
- Node.js (for tool itself — only needed for optional LocalTunnel online sharing)
- Any cloud accounts or subscriptions
- Admin/root privileges

---

## 3. Project Structure

```
QA-L-LMS-Automation-tool-main/
│
├── 🚀 LAUNCHERS
│   ├── start_dashboard.bat         ← Windows: Double-click to launch locally
│   ├── start_mac.command           ← macOS: Double-click to launch (for TL)
│   └── start_online_dashboard.bat  ← Windows: Launch + create public sharing link
│
├── 📦 SETUP FILES
│   ├── setup.ps1                   ← PowerShell setup (auto-called by .bat)
│   ├── requirements.txt            ← Python package list (playwright)
│   ├── cloudflared.exe             ← Cloudflare tunnel binary (online sharing)
│   └── MAC_GUIDE.txt               ← Quick-start guide for macOS user (TL)
│
├── 🧠 MAIN SERVER
│   └── web_dashboard_server.py     ← Core backend: HTTP server + scan engine bridge
│
├── 🎨 WEB DASHBOARD UI
│   └── web_ui/
│       └── index.html              ← Single-page dashboard (all tabs, live logs, report viewer)
│
├── ⚙️ QC ENGINE (Core Scanning Logic)
│   └── qc_core/
│       ├── scanner.py              ← Canvas LMS page-by-page scanner
│       ├── bb_scanner.py           ← Blackboard Ultra inventory scanner
│       ├── checks.py               ← Image checker + Link checker + Embed recorder
│       ├── reporter.py             ← Generates the final HTML report
│       ├── comparison.py           ← Cross-LMS title comparison engine
│       ├── config.py               ← URLs, timeouts, SSO patterns, paths
│       └── __init__.py             ← Python package marker
│
├── 🧪 MOCK TEST DATA
│   └── test_samples/               ← Offline HTML pages for dry-run testing
│
├── 📊 REPORTS OUTPUT (auto-generated)
│   └── reports/
│       ├── latest_report.html      ← Most recent scan's full QC report
│       ├── canvas_qc_results.json  ← Raw Canvas scan data (JSON)
│       ├── canvas_inventory.json   ← Raw Canvas modules inventory (JSON)
│       └── screenshots/            ← PNG screenshots of broken images
│
└── 🔐 SESSION STORAGE (auto-generated)
    └── .auth/
        └── storage_state.json      ← Saved browser session (SSO cookies)
```

---

## 4. First-Time Setup

### Windows Setup

1. **Open** the project folder in File Explorer
2. **Double-click** `start_dashboard.bat`
3. The script automatically:
   - Creates a Python virtual environment (`.venv/`)
   - Installs `playwright` package
   - Downloads Chromium browser (~150 MB — first time only)
   - Starts the web dashboard on port 8080
   - Opens your browser to `http://127.0.0.1:8080`

> First-time setup takes ~3–5 minutes due to browser download. After that, startup is instant.

### macOS Setup (for TL)

1. **Receive** the ZIP file from the QA team
2. **Double-click** the ZIP to extract
3. **Double-click** `start_mac.command`
4. If macOS shows a security warning → Right-click → Open → Open
5. The script auto-installs Python dependencies and opens the dashboard

### Manual Setup (Advanced)

```bash
# 1. Create virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browsers
playwright install chromium

# 4. Start the dashboard
python web_dashboard_server.py --port 8080
```

---

## 5. How to Launch the Tool

### Option A — Local Use (Windows)
```
Double-click → start_dashboard.bat
→ Opens: http://127.0.0.1:8080
```

### Option B — Online Sharing (Team Lead / Remote Access)
```
Double-click → start_online_dashboard.bat
→ Shows a public HTTPS link like:
   https://lms-qa-ashok.loca.lt
→ Share this link with TL (works on any browser, any OS)
```

### Option C — macOS Standalone (TL's MacBook)
```
Double-click → start_mac.command
→ Tool runs entirely on TL's Mac
→ No dependency on QA team's laptop
```

---

## 6. Architecture — How it Works Inside

```
┌──────────────────────────────────────────────────────────────┐
│                      WEB BROWSER (TL/User)                   │
│              https://lms-qa-ashok.loca.lt                    │
│              or http://127.0.0.1:8080                        │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ▼
┌──────────────────────────────────────────────────────────────┐
│               web_dashboard_server.py                        │
│         (Python ThreadingHTTPServer on port 8080)            │
│                                                              │
│  Routes:                                                     │
│  GET  /               → Serves web_ui/index.html            │
│  POST /api/scan        → Starts scan worker thread           │
│  GET  /api/status      → Returns live scan state & logs      │
│  GET  /api/errors      → Returns categorized error summary   │
│  POST /api/confirm_login → Signals SSO login complete        │
│  POST /api/cancel      → Cancels running scan                │
│  GET  /reports/*       → Serves HTML reports & screenshots   │
└───────────────┬──────────────────────────────────────────────┘
                │ Spawns in background thread
                ▼
┌──────────────────────────────────────────────────────────────┐
│                    QC SCAN WORKER THREAD                     │
│                                                              │
│   Mode: Canvas    → qc_core/scanner.py                      │
│   Mode: Blackboard → qc_core/bb_scanner.py                  │
│   Mode: Workflow   → bb_scanner.py + scanner.py + compare   │
└───────────────┬──────────────────────────────────────────────┘
                │ Controls
                ▼
┌──────────────────────────────────────────────────────────────┐
│                  PLAYWRIGHT BROWSER ENGINE                   │
│                 (Headless Chromium)                          │
│                                                              │
│  1. Launches isolated browser context (fresh session)        │
│  2. Loads saved SSO cookies from .auth/storage_state.json   │
│  3. Navigates to course URL                                  │
│  4. Discovers all module items (pages, files, links)         │
│  5. For each page:                                           │
│     a. Navigates to page                                     │
│     b. Waits for content to fully render                     │
│     c. Runs checks.py → images, links, embeds               │
│     d. Saves screenshots of broken items                     │
│  6. Generates HTML report via reporter.py                    │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Reason |
|---|---|
| **Headless browser (not requests library)** | LMS pages require JavaScript to render. Raw HTTP requests get blank pages. |
| **Authenticated session** | Link checks use real SSO cookies — avoids false positives from auth-walls. |
| **ThreadingHTTPServer** | Dashboard stays responsive while scan runs in background. |
| **Separate browser contexts** | Canvas and Blackboard scans never share cookies or state. |
| **stdout interceptor** | All scanner print() output is captured and streamed to dashboard live logs. |

---

## 7. Scan Modes — What Each Mode Does

### Mode 1: Canvas QC Scan
**What it does:**
- Logs into Canvas (Bristol Ole) using saved SSO session
- Navigates to the course Modules page
- Iterates through every module and every item inside each module
- For each content page:
  - Extracts and checks all images
  - Extracts and checks all hyperlinks
  - Records all embedded media (video, audio, iframes)
- Generates a full HTML QC report

**Input:** Canvas course URL (e.g., `https://ole.mumbai.bristol.ac.uk/courses/350`)  
**Output:** `reports/latest_report.html` + `reports/screenshots/`

---

### Mode 2: Blackboard Ultra Inventory Scan
**What it does:**
- Logs into Blackboard Ultra using saved SSO session
- Navigates the course content tree
- Records every item: modules, documents, assignments, tests, links, folders
- Notes visibility status (visible / hidden from students)
- Saves a structured inventory (JSON + HTML)

**Input:** Blackboard Ultra course URL  
**Output:** `reports/canvas_inventory.json` (BB inventory data)

---

### Mode 3: Full Workflow (BB + Canvas + Comparison)
**What it does:**
- Step 1: Runs Blackboard inventory scan
- Step 2: Runs Canvas QC scan  
- Step 3: Compares Blackboard items vs Canvas modules by title
- Produces a cross-LMS comparison report showing:
  - Matched items (title found in both LMS)
  - Possibly missing items (in BB but not found in Canvas)
  - Needs review (duplicate titles)

**Input:** Both Blackboard URL + Canvas URL  
**Output:** `reports/latest_report.html` + `reports/comparison_report.html`

---

## 8. What Gets Checked — Full QC Breakdown

### 8.1 Image Checks (`checks.py → check_images()`)

The tool inspects every `<img>` tag inside the course page content area.

**Detection method:**
```
Image is BROKEN if:
  → src attribute is empty / missing
  OR
  → image.complete = true BUT naturalWidth = 0
     (browser tried to load it, but it failed to render)
```

**On failure:**
- Highlights the broken image with a red border in the browser
- Takes a full screenshot as visual evidence
- Saves screenshot to `reports/screenshots/broken_img_*.png`

**Statuses:**

| Status | Meaning |
|---|---|
| ✅ PASS | Image loaded and rendered (naturalWidth > 0) |
| ❌ FAIL | Image failed to load or render |
| ⏭️ NOT TESTED | Image was still loading when check ran |

---

### 8.2 Link Checks (`checks.py → check_links()`)

The tool extracts every `<a href="...">` from page content and validates each one using the **authenticated browser session** (carrying real SSO cookies).

**HTTP Status Code Decisions:**

| HTTP Code | Classification | Reason |
|---|---|---|
| 200–399 | ✅ PASS / OK | Link resolved successfully |
| 401, 403 | ⏭️ NOT TESTED (ACCESS_RESTRICTED) | Auth-required — not a broken link |
| 404, 410 | ❌ FAIL (BROKEN_LINK) | Page confirmed deleted/missing |
| 429 | ⏭️ NOT TESTED (RATE_LIMITED) | Bot protection — not confirmed broken |
| 500+ | ⏭️ NOT TESTED (SERVER_ERROR) | Server down during check — recheck needed |
| Timeout (12s) | ⏭️ NOT TESTED (TIMEOUT) | Slow server — not classified as broken |
| DNS Failure | ⏭️ NOT TESTED (DNS_FAILURE) | Domain unreachable — needs manual recheck |
| SSO redirect | ⏭️ NOT TESTED (AUTH_REQUIRED) | Redirected to login — not a broken link |

**Special link types (automatically skipped):**

| Type | Example | Why Skipped |
|---|---|---|
| JavaScript links | `javascript:void(0)` | Cannot HTTP-check |
| Email links | `mailto:staff@bristol.ac.uk` | Protocol-only |
| Phone links | `tel:+441234567890` | Protocol-only |
| Page anchors | `#section-2` | Same-page scroll, verified locally |

---

### 8.3 Embed / Media Recording (`checks.py → check_embeds()`)

Records all embedded media elements on each page. **Does NOT test playback** (automated video playback verification is not in scope).

**Detected elements:**
- `<video>` — HTML5 video tags
- `<audio>` — HTML5 audio tags
- `<iframe>` — YouTube, Vimeo, Kaltura, Panopto, Canvas Studio embeds
- `<object>` / `<embed>` — Legacy media objects

**Status:** Always `NOT TESTED` with note: *"Manual playback check recommended"*

---

### 8.4 Blackboard Inventory (`bb_scanner.py`)

Crawls the Blackboard Ultra course tree and records:
- Module/folder names
- Document titles
- Assignment titles
- Link items (external URLs)
- Visibility (visible to students / hidden)
- Item type (content, assessment, folder, link, etc.)

---

### 8.5 Cross-LMS Comparison (`comparison.py`)

Compares Blackboard inventory against Canvas modules using **normalized title matching**.

**Normalization:** Lowercase, remove extra spaces, Unicode-normalize (handles special characters, accents).

**Match statuses:**

| Status | Meaning |
|---|---|
| MATCHED_TITLE | Unique title found in both LMS |
| NEEDS REVIEW | Duplicate/ambiguous title found |
| POSSIBLY MISSING | Title in BB but not found in Canvas |
| NOT TESTED | One scan was blocked or incomplete |

> **Important:** Title match ≠ content equivalence. Only the titles are compared — content, formatting, file attachments, and media are NOT verified by comparison.

---

## 9. Link Check Logic — Status Codes Explained

```
START: Found link href
       │
       ├─ javascript: → SKIP (NOT TESTED / JAVASCRIPT)
       ├─ mailto: / tel: → SKIP (NOT TESTED / PROTOCOL)
       ├─ #anchor → CHECK locally (PASS / NOT TESTED)
       │
       └─ http / https →
              │
              SEND authenticated GET request (with SSO cookies)
              Max redirects: 5 | Timeout: 12 seconds
              │
              ├─ Redirected to SSO/login URL? → NOT TESTED (AUTH_REQUIRED)
              │
              ├─ 200–399 → ✅ PASS
              ├─ 401 / 403 → NOT TESTED (ACCESS_RESTRICTED)
              ├─ 404 / 410 → ❌ FAIL (BROKEN_LINK)
              ├─ 429 → NOT TESTED (RATE_LIMITED)
              ├─ 500+ → NOT TESTED (SERVER_ERROR)
              │
              ├─ Timeout (>12s) → NOT TESTED (TIMEOUT)
              ├─ DNS failure → NOT TESTED (DNS_FAILURE)
              └─ Connection refused → NOT TESTED (CONNECTION_REFUSED)
```

---

## 10. Understanding the HTML Report

The generated `reports/latest_report.html` contains:

### Report Sections

| Section | What it Shows |
|---|---|
| **Summary Bar** | Total pages scanned, broken images, broken links, embeds found, skipped items |
| **Broken Images** | Page name, image alt text, reason for failure, screenshot thumbnail |
| **Broken Links** | Page name, link text, full URL, HTTP error code |
| **Auth-Required Links** | Links that redirect to SSO (informational — not broken) |
| **Embedded Media** | All iframes/videos found (not tested — manual check needed) |
| **Skipped Items** | Module items not scanned, with exact reason |
| **Comparison Table** | BB vs Canvas title match results (Workflow mode only) |

### Summary Count Meaning

```
Total Pages Scanned: 45
  → 45 Canvas content pages were fully inspected

Broken Images: 3
  → 3 <img> tags failed to render across all pages

Broken Links: 7
  → 7 links returned HTTP 404/410

Auth-Required Links: 12
  → 12 links redirect to SSO login (not broken — just require login)

Embeds Found: 8
  → 8 video/iframe embeds detected (manual playback check needed)

Skipped Items: 14
  → 14 module items were not scannable (see SKIPPED section)
```

---

## 11. SKIPPED Items — Why They Are Skipped

Some module items cannot be automated-scanned and are marked **SKIPPED** with a reason:

| Item Type | Example | Why Skipped |
|---|---|---|
| **Subheader** | "Section A: Core Reading Material" | Display-only text separator — no content page |
| **External Tool (LTI)** | Turnitin, Zoom, publisher tools | Launches a third-party app — cannot be automated (security/auth boundary) |
| **File Attachment** | `.pdf`, `.docx`, `.pptx` | Binary file — no HTML to scan |
| **External URL** | Links directly to external sites | Checked in link checker instead |
| **Assignment** | Quiz, submission portal | Interactive — would require form submission |
| **Discussion** | Forum threads | Requires posting — read-only restriction |

> **Skipped ≠ Broken.** Skipped items are safely recorded for manual review, but they are NOT flagged as errors.

---

## 12. SSO / MFA Login Flow

Bristol University LMS uses **Microsoft Entra ID (Azure AD)** with SSO and optional MFA (Multi-Factor Authentication).

### How the Tool Handles SSO

```
First Run:
1. Tool opens a VISIBLE browser window
2. Dashboard shows: "Waiting for your manual login..."
3. User manually logs into Canvas/Blackboard with SSO + MFA
4. User clicks "I Have Logged In" in the dashboard
5. Tool saves the authenticated session to .auth/storage_state.json

Subsequent Runs:
1. Tool loads saved session from .auth/storage_state.json
2. If session is still valid → scans directly (no login needed)
3. If session expired → repeats login flow
```

### Why Manual SSO is Required
- SSO pages use JavaScript, CAPTCHA, and device trust checks
- Automating the actual login would violate university IT security policy
- The tool saves the **result** of your login (session cookies), not your credentials

> **Security:** Your password is never stored. Only the browser session cookies are saved (same as a browser's "Remember Me" feature).

---

## 13. Online Sharing — Cloudflare / LocalTunnel

When you want Team Lead or other team members to access the dashboard remotely without installing anything:

### LocalTunnel (Recommended)
```
Run: start_online_dashboard.bat
Gets: https://lms-qa-ashok.loca.lt

First visit shows a security warning page → Enter the IP shown → Continue
(One-time per device, valid for 7 days)
```

### How it Works
```
TL's Mac Browser
      │ HTTPS
      ▼
LocalTunnel Server (cloud relay)
      │ TCP tunnel
      ▼
Your Laptop (port 8080)
      │
      ▼
web_dashboard_server.py → Playwright → LMS
```

### Important Constraints

| Constraint | Details |
|---|---|
| **Your laptop must stay ON** | Scanning happens on your machine — tunnel just relays the UI |
| **Link changes on restart** | Every time you restart the tunnel, a new URL may be generated (lms-qa-ashok is fixed with LocalTunnel) |
| **Cloudflare free tunnels** | Sometimes return Error 1033 (regional routing delays) — use LocalTunnel as fallback |
| **Not for production** | These are temporary tunnels — not guaranteed uptime |

---

## 14. Positive Outcomes

### What the Tool Successfully Detects ✅

| Scenario | Outcome |
|---|---|
| Image URL is broken (404) | Detected as FAIL + screenshot saved |
| Image src attribute is empty | Detected as FAIL + screenshot saved |
| Page link returns HTTP 404 | Detected as FAIL (BROKEN_LINK) |
| Page link returns HTTP 410 (Gone) | Detected as FAIL (BROKEN_LINK) |
| Course module is fully intact | All images PASS, all links PASS |
| BB content migrated to Canvas | MATCHED_TITLE in comparison |
| Video embed is present | Recorded as embed (manual review recommended) |
| Module item is a subheader | Safely SKIPPED with reason logged |
| LTI tool item exists | Safely SKIPPED with reason logged |
| SSO session expired | Prompts for manual re-login gracefully |
| Scan cancelled mid-way | Clean cancellation, partial results saved |

---

## 15. Negative Outcomes & Known Limitations

### What the Tool CANNOT Detect ❌

| Limitation | Explanation |
|---|---|
| **Video playback errors** | Tool records embeds but does NOT press play — manual check needed |
| **Wrong video (correct embed, wrong content)** | Title/URL checked but video content is not watched |
| **PDF/document content errors** | Binary files are not opened — only presence is noted |
| **Broken images requiring login to render** | If image is behind SSO and session expired, may show false PASS |
| **Mobile/responsive layout issues** | Scans in desktop viewport only |
| **Accessibility (a11y) issues** | Not in scope — alt text is recorded but not evaluated |
| **Content accuracy** | Does not read/compare page text content |
| **Assignment correctness** | Does not open, submit, or evaluate assignments |
| **Canvas gradebook or settings** | Only scans Modules content — not grade settings |
| **Blackboard exact content** | Inventory captures titles + visibility only, not page body content |
| **LTI tool functionality** | External tools are skipped — cannot be automated |
| **Newly posted content after scan** | Report reflects state at time of scan only |

### Known Technical Limitations

| Issue | Workaround |
|---|---|
| **LocalTunnel first-visit security warning** | Enter the shown IP address once |
| **Cloudflare Error 1033** | Wait 60 seconds or use LocalTunnel instead |
| **Session expired mid-scan** | Dashboard prompts re-login — confirm and continue |
| **Very large courses (500+ pages)** | Scan may take 30–60 min — keep laptop plugged in |
| **Rate limiting by LMS** | Tool backs off automatically — may add extra delay |
| **Flaky network during link check** | Some links show TIMEOUT — not marked as broken, requires recheck |

---

## 16. Safety Guarantees — What the Tool NEVER Does

> This section is critical for institutional compliance and LMS admin approval.

### ❌ The Tool Will NEVER:

| Action | Status |
|---|---|
| Submit an assignment or quiz | ❌ Never |
| Post in a discussion forum | ❌ Never |
| Edit or delete any course content | ❌ Never |
| Change student grades or records | ❌ Never |
| Enrol or un-enrol users | ❌ Never |
| Send messages to students | ❌ Never |
| Modify course settings or visibility | ❌ Never |
| Store your university password | ❌ Never |
| Send data to any third-party server | ❌ Never (except tunnel relay for UI) |
| Access other courses without URL | ❌ Never |
| Perform destructive HTTP methods (PUT/POST/DELETE to LMS API) | ❌ Never |

### ✅ The Tool ONLY:

| Action | Details |
|---|---|
| HTTP GET requests | Read-only page retrieval |
| Screenshot capture | Of broken images only, saved locally |
| JSON report generation | Saved to local `reports/` folder |
| HTML report generation | Saved to local `reports/` folder |
| Session cookie storage | Saved locally in `.auth/` — never transmitted |

---

## 17. Will it Disturb LMS / Blackboard?

**Short answer: No.**

**Detailed answer:**

The tool behaves exactly like a logged-in QA person manually clicking through course pages. From the LMS server's perspective, it sees standard browser GET requests with valid session cookies.

### Request Behaviour
- All requests use standard HTTP GET with full browser headers
- Requests are sequential (one page at a time) — not parallel bulk crawling
- 12-second timeout per link check — slow, considerate crawling
- 2-second stabilization wait after each page load — respects server load

### What LMS Server Sees
```
Normal user session → GET /courses/350/modules
Normal user session → GET /courses/350/pages/introduction
Normal user session → GET /external-resource.pdf  ← link check
...
```
This is **indistinguishable from a human QA reviewer** clicking through the course.

### Risks to LMS: None
- No database writes
- No admin API calls
- No file uploads
- No form submissions
- No logins without user confirmation

---

## 18. Troubleshooting Common Issues

### Dashboard won't open
```
Problem: start_dashboard.bat runs but browser shows error
Fix: Check if port 8080 is in use by another program
     Run: netstat -ano | findstr :8080
     Then: Close the conflicting program or change port
```

### Scan stuck at "Waiting for Login"
```
Problem: SSO login page not completing
Fix 1: Complete the SSO login in the browser that opened
Fix 2: Click "I Have Logged In" button AFTER the page shows your name
Fix 3: If MFA prompt → approve on your phone first, THEN click button
```

### Error 1033 (Cloudflare Tunnel)
```
Problem: Public link shows Cloudflare error
Fix 1: Wait 60 seconds — edge propagation takes time
Fix 2: Close CMD window → Re-run start_online_dashboard.bat
Fix 3: Use LocalTunnel (loca.lt) instead of Cloudflare
```

### LocalTunnel IP verification page
```
Problem: Link shows security warning asking for IP
Fix: Type the IP shown on the page (e.g., 152.57.81.212) → Click Continue
Note: This is one-time per device per 7 days
```

### Images show as PASS but look broken visually
```
Problem: Image passes check but displays wrong or placeholder
Reason: The image URL works (200 OK) but the content may be wrong
Fix: Manual visual inspection still needed for wrong-content images
```

### Scan is very slow (1+ hour)
```
Reason: Large course with many pages, many links to check per page
Fix 1: Use max_pages parameter to scan a subset first
Fix 2: Close other applications to free RAM for Chromium
Fix 3: Use wired internet connection for faster link checks
```

### `.auth/storage_state.json` error
```
Problem: Session file corrupted
Fix: Delete the .auth/ folder
     Next scan will re-prompt for fresh SSO login
```

---

## 19. Glossary

| Term | Meaning |
|---|---|
| **LMS** | Learning Management System (Canvas, Blackboard) |
| **Canvas** | New LMS at Bristol University (`ole.mumbai.bristol.ac.uk`) |
| **Blackboard Ultra** | Legacy LMS being migrated from (`ole.bris.ac.uk`) |
| **SSO** | Single Sign-On — university login using Microsoft account |
| **MFA** | Multi-Factor Authentication — phone approval during login |
| **Playwright** | Microsoft open-source browser automation library |
| **Chromium** | Open-source browser engine (Chrome without Google branding) |
| **Headless** | Browser running without visible window (background mode) |
| **LTI** | Learning Tools Interoperability — third-party tool embedded in LMS (e.g., Turnitin) |
| **naturalWidth** | JavaScript property — 0 means image failed to render |
| **HTTP 404** | "Not Found" — page or file has been deleted |
| **HTTP 410** | "Gone" — page permanently removed |
| **HTTP 401/403** | "Unauthorized/Forbidden" — access control, not a broken link |
| **Tunnel** | Secure pipe from your laptop to the internet (Cloudflare / LocalTunnel) |
| **ThreadingHTTPServer** | Python server that handles multiple requests simultaneously |
| **Storage State** | Saved browser cookies and session data |
| **QC** | Quality Control |
| **Inventory** | Complete list of items in a Blackboard course |

---

*Document generated: November 2026 | LMS QA Automation Tool v1.0*  
*For internal Bristol University QA team use only.*

