import os
import json
from datetime import datetime, timezone
import sys
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Tuple, Any, Optional

from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

from .config import (
    DEFAULT_COURSE_URL,
    DEFAULT_MODULES_URL,
    SCREENSHOTS_DIR,
    REPORTS_DIR,
    AUTH_STATE_FILE,
    PAGE_NAV_TIMEOUT_MS,
    CONTENT_STABILIZE_WAIT_MS
)
from .checks import check_images, check_links, check_embeds
from .reporter import generate_html_report


class LMSScanner:
    def __init__(
        self,
        course_url: str = DEFAULT_COURSE_URL,
        headless: bool = False,
        auth_file: Path = AUTH_STATE_FILE,
        browser_channel: str = "chromium"
    ):
        self.course_url = course_url.rstrip("/")
        if self.course_url.endswith("/modules") or self.course_url.endswith(".html") or self.course_url.endswith(".htm"):
            self.modules_url = self.course_url
        else:
            self.modules_url = f"{self.course_url}/modules"
        self.browser_channel = browser_channel
        self.headless = headless
        self.auth_file = auth_file

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self.scanned_pages: List[Dict[str, Any]] = []
        self.skipped_items: List[Dict[str, Any]] = []
        self.inventory = []
        self.inventory_status = "INCOMPLETE"
        self.status = "INCOMPLETE"
        self.status_reason = "Scan not completed"

    def access_problem(self, response=None):
        actual = urlparse(self.page.url)
        expected = urlparse(self.course_url)
        path = actual.path.lower()
        if actual.netloc != expected.netloc:
            return "Redirected outside course host; access not verified"
        if re.search(r"/(login|signin|sign-in|sso|saml|oauth|unauthorized|access_denied)(/|$)", path):
            return "Authentication/access page reached"
        if response and response.status in (401, 403):
            return f"Course access denied: HTTP {response.status}"
        if self.page.locator('input[type="password"]').count():
            return "Login form reached"
        text = self.page.locator('body').inner_text().lower()
        if any(message in text for message in ('access denied', 'you are unauthorized', 'you do not have permission to access')):
            return "Course access denied"
        return None

    def start_browser(self):
        """Launches the visible browser session."""
        print(f"\n[1/5] Launching browser (Headless: {self.headless})...")
        self.playwright = sync_playwright().start()

        options = dict(headless=self.headless, slow_mo=50 if not self.headless else 0,
                       args=["--start-maximized"] if not self.headless else [])
        if self.browser_channel != "chromium":
            options["channel"] = self.browser_channel
        print(f"[*] Browser selected: {self.browser_channel}; visible: {not self.headless}")
        self.browser = self.playwright.chromium.launch(**options)

        # Load existing auth state if present
        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1280, "height": 850}
        }
        if self.auth_file.exists():
            try:
                context_kwargs["storage_state"] = str(self.auth_file)
                print(f"[*] Found local session state at: {self.auth_file}")
            except Exception as e:
                print(f"[!] Warning: Could not load auth state: {e}")

        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()
        if not self.headless:
            self.page.bring_to_front()

    def handle_manual_login(self):
        """
        Requirements 1, 2, 3:
        Opens the course/login page in the visible browser and waits for the user
        to manually complete SSO / MFA. Antigravity never handles the user's password.
        """
        print("\n" + "=" * 75)
        print(" LMS QUALITY CONTROL SCANNER - MANUAL LOGIN REQUIRED")
        print("=" * 75)
        print(f" Navigating to: {self.course_url}")
        print(" A visible browser window is now open.")
        print("")
        print(" 1. Please log in directly inside the browser window.")
        print(" 2. Complete your university SSO and MFA (Duo/Authenticator) if prompted.")
        print(" 3. SAFETY NOTICE: This tool will NEVER ask you to type or paste your")
        print("    password in chat or terminal.")
        print(" 4. Once you have logged in and can see your Canvas Course 350 page,")
        print("    come back to this terminal window and press [ENTER] to begin.")
        print("=" * 75 + "\n")

        try:
            self.page.goto(self.course_url, wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS)
        except Exception as e:
            print(f"[!] Notice during initial load: {e}")

        # Wait for the user to press Enter
        try:
            input(">> Press [ENTER] once you are logged in and ready to scan... ")
        except EOFError:
            raise RuntimeError("Interactive terminal required: login confirmation was not received")

        # Save session state locally for convenience (Requirement 11: local only, gitignored)
        try:
            self.auth_file.parent.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(self.auth_file))
            print(f"[*] Session saved locally to {self.auth_file} (excluded from git).")
        except Exception as err:
            print(f"[!] Note: Could not save session state: {err}")

    def discover_module_items(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Navigates to the modules page and parses all modules and items.
        Separates scannable content pages from items that must be skipped by policy.
        """
        print(f"\n[2/5] Navigating to course modules: {self.modules_url}...")
        try:
            response = self.page.goto(self.modules_url, wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS)
            time.sleep(2.0)  # Allow Canvas client-side module rendering
        except Exception as e:
            self.status = "INCOMPLETE"
            self.status_reason = f"Modules navigation failed: {e}"
            return [], []

        reason = self.access_problem(response)
        if reason:
            self.status = "BLOCKED"
            self.status_reason = reason
            return [], []
        expected = urlparse(self.modules_url)
        actual = urlparse(self.page.url)
        if (expected.netloc, expected.path.rstrip('/')) != (actual.netloc, actual.path.rstrip('/')):
            self.status_reason = "Expected modules page was not reached"
            return [], []
        if not self.page.locator('#context_modules, .context_modules, .context_module').count():
            self.status_reason = "Modules container unavailable; course content not verified"
            return [], []

        # Extract modules and module items from Canvas DOM
        extracted_data = self.page.evaluate("""
        () => {
            const results = [];
            // Canvas module container: #context_modules or .context_modules
            const moduleNodes = document.querySelectorAll('.context_module');

            if (moduleNodes.length > 0) {
                moduleNodes.forEach((modEl, modIdx) => {
                    const headerEl = modEl.querySelector('.header .name, .ig-header-title, h2, h3');
                    const moduleName = headerEl ? (headerEl.innerText || headerEl.textContent || '').trim() : `Module ${modIdx + 1}`;

                    const itemNodes = modEl.querySelectorAll('.context_module_item, .ig-row');
                    itemNodes.forEach((itemEl, itemIdx) => {
                        const titleEl = itemEl.querySelector('.item_name a.title, a.ig-title, a.title, .title, span.title');
                        const linkEl = itemEl.querySelector('a.title, a.ig-title, a[href]');

                        const title = titleEl ? (titleEl.innerText || titleEl.textContent || '').trim() : `Item ${itemIdx + 1}`;
                        const href = linkEl ? linkEl.getAttribute('href') : '';
                        const className = itemEl.className || '';

                        // Determine item type
                        let type = 'Unknown';
                        if (className.includes('context_module_sub_header') || className.includes('sub-header')) {
                            type = 'Subheader';
                        } else if (className.includes('attachment') || href.includes('/files/')) {
                            type = 'File Attachment';
                        } else if (className.includes('context_external_tool') || href.includes('/external_tools/')) {
                            type = 'External Tool (LTI)';
                        } else if (className.includes('external_url') || (!href.includes('/courses/') && href.startsWith('http'))) {
                            type = 'External Link';
                        } else if (className.includes('wiki_page') || href.includes('/pages/')) {
                            type = 'Canvas Page';
                        } else if (className.includes('assignment') || href.includes('/assignments/')) {
                            type = 'Assignment';
                        } else if (className.includes('discussion_topic') || href.includes('/discussion_topics/')) {
                            type = 'Discussion';
                        } else if (className.includes('quiz') || href.includes('/quizzes/')) {
                            type = 'Quiz';
                        } else if (href) {
                            type = 'Content Item';
                        }

                        results.push({
                            module_name: moduleName,
                            title: title,
                            href: href,
                            type: type,
                            class_name: className
                        });
                    });
                });
            }

            return results;
        }
        """)

        self.inventory = [dict(x, id=f"canvas_item_{i}", url=urljoin(self.modules_url,x.get("href") or ""))
                          for i,x in enumerate(extracted_data)]
        self.inventory_status = "OBSERVED" if self.inventory else "INCOMPLETE"
        scannable = []
        skipped = []

        # Empty modules are not content pages.
        for idx, item in enumerate(extracted_data):
            title = item.get("title", f"Item #{idx + 1}")
            module_name = item.get("module_name", "General")
            raw_href = item.get("href", "")
            item_type = item.get("type", "Unknown")

            item_id = f"item_{idx + 1}_{re.sub(r'[^a-zA-Z0-9]', '', title)[:20]}"

            # Rule 1: Subheaders have no page content
            if item_type == "Subheader" or not raw_href or raw_href.strip() == "#":
                skipped.append({
                    "id": item_id,
                    "title": title,
                    "module_name": module_name,
                    "type": "Subheader",
                    "url": None,
                    "skip_reason": "Subheader / text separator (no page content)"
                })
                continue

            full_url = urljoin(self.page.url, raw_href)

            # Rule 2: External tool (LTI) launches
            if item_type == "External Tool (LTI)" or "/external_tools/" in full_url:
                skipped.append({
                    "id": item_id,
                    "title": title,
                    "module_name": module_name,
                    "type": item_type,
                    "url": full_url,
                    "skip_reason": "External LTI Tool (Interactive external launch skipped for safety)"
                })
                continue

            # Rule 3: File downloads / attachments
            if item_type == "File Attachment" or "/files/" in full_url:
                skipped.append({
                    "id": item_id,
                    "title": title,
                    "module_name": module_name,
                    "type": item_type,
                    "url": full_url,
                    "skip_reason": "File Attachment / download preview (not a Canvas content page)"
                })
                continue

            # Rule 4: External links
            if item_type == "External Link" or (urlparse(full_url).netloc and urlparse(full_url).netloc != urlparse(self.page.url).netloc):
                skipped.append({
                    "id": item_id,
                    "title": title,
                    "module_name": module_name,
                    "type": "External Link",
                    "url": full_url,
                    "skip_reason": "External site link (not a Canvas content page)"
                })
                continue

            course_match = re.search(r"/courses/\d+", urlparse(self.course_url).path)
            if course_match:
                allowed_prefix = course_match.group(0) + "/"
                path = urlparse(full_url).path
                if not path.startswith(allowed_prefix) or not any(
                    part in path for part in ('/pages/', '/assignments/', '/discussion_topics/', '/quizzes/', '/modules/items/')
                ):
                    skipped.append(dict(item, url=full_url, skip_reason="Not an allowed course content route"))
                    continue

            # Rule 5: Canvas content pages (Pages, Assignments, Discussions, Quizzes)
            scannable.append({
                "id": item_id,
                "title": title,
                "module_name": module_name,
                "type": item_type,
                "url": full_url
            })

        return scannable, skipped

    def scan_content_page(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Navigates to an individual Canvas content page and performs all QC checks:
        1. Rendered images check (naturalWidth, loading failure, screenshot on failure)
        2. Content links check (using authenticated session, distinguishing auth/timeouts)
        3. Videos and embeds detection (recorded as NOT TESTED)
        """
        url = item["url"]
        title = item["title"]
        item_id = item["id"]

        print(f"  -> Scanning [{item['type']}]: {title}")
        print(f"     URL: {url}")

        page_result: Dict[str, Any] = {
            "id": item_id,
            "title": title,
            "module_name": item["module_name"],
            "type": item["type"],
            "url": url,
            "images": [],
            "links": [],
            "embeds": [],
            "error": None
        }

        try:
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=PAGE_NAV_TIMEOUT_MS)
            reason = self.access_problem(response)
            if reason:
                self.status = "BLOCKED"
                self.status_reason = reason
                page_result["error"] = reason
                page_result["overall_status"] = "NOT TESTED"
                return page_result
            if response and response.status >= 400:
                raise RuntimeError(f"Content returned HTTP {response.status}")
            # Wait for content to stabilize
            time.sleep(CONTENT_STABILIZE_WAIT_MS / 1000.0)

            # Wait for user content container if it exists
            try:
                self.page.wait_for_selector(".user_content, #content, main, article", timeout=5000)
            except Exception:
                pass

            # 1. Check Images (Requirement 5 & 8)
            images = check_images(self.page, item_id, SCREENSHOTS_DIR)
            page_result["images"] = images

            # 2. Check Links (Requirement 6)
            links = check_links(self.page, self.context, url)
            page_result["links"] = links

            # 3. Check Videos & Embeds (Requirement 7)
            embeds = check_embeds(self.page)
            page_result["embeds"] = embeds

            # Log summary for this page
            broken_imgs = sum(1 for img in images if img["status"] == "FAIL")
            broken_links = sum(1 for lk in links if lk["status"] == "FAIL")
            embed_count = len(embeds)

            status_str = "PASS" if (broken_imgs == 0 and broken_links == 0) else "FAIL"
            page_result["overall_status"] = status_str if not any(x.get("status") != "PASS" for x in images + links + embeds) else ("FAIL" if status_str == "FAIL" else "NOT TESTED")
            print(f"     [Result: {page_result['overall_status']}] Images: {len(images)} ({broken_imgs} broken) | Links: {len(links)} ({broken_links} broken) | Embeds: {embed_count}")

        except Exception as e:
            print(f"     [!] Error while scanning page: {e}")
            page_result["error"] = str(e)
            page_result["overall_status"] = "NOT TESTED"

        return page_result

    def run_qc(self, max_pages: Optional[int] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Path]:
        """
        Executes the full Quality Control scan workflow.
        Returns (scanned_pages, skipped_items, report_path).
        """
        try:
            self.scanned_pages = []
            self.skipped_items = []
            self.inventory = []
            self.inventory_status = "INCOMPLETE"
            self.status = "INCOMPLETE"
            self.status_reason = "No scannable course content found"
            self.start_browser()

            # Manual login step (visible browser + SSO/MFA prompt)
            if not self.headless:
                self.handle_manual_login()

            # Discover module items
            scannable_items, skipped_items = self.discover_module_items()
            self.skipped_items = skipped_items

            print(f"\n[3/5] Discovered {len(scannable_items)} scannable content pages and {len(skipped_items)} skipped items.")

            if max_pages and max_pages > 0:
                print(f"[*] Limiting scan to first {max_pages} pages (--max-pages).")
                scannable_items = scannable_items[:max_pages]

            # Scan each content page
            print("\n[4/5] Executing Read-Only QC Checks on content pages...")
            for idx, item in enumerate(scannable_items, 1):
                print(f"Item ({idx}/{len(scannable_items)}):")
                result = self.scan_content_page(item)
                self.scanned_pages.append(result)
                if self.status == "BLOCKED":
                    break

            if self.status != "BLOCKED" and self.scanned_pages:
                if any(p.get("overall_status") == "FAIL" for p in self.scanned_pages):
                    self.status = "FAIL"
                elif skipped_items or (max_pages and len(self.scanned_pages) >= max_pages) or any(p.get("overall_status") != "PASS" for p in self.scanned_pages):
                    self.status = "INCOMPLETE"
                else:
                    self.status = "PASS"
                self.status_reason = "Status covers implemented checks only; skipped or unverified checks limit coverage"

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            inventory_path = REPORTS_DIR / "canvas_inventory.json"
            inventory_path.write_text(json.dumps({"course_url":self.course_url,
                "status":"BLOCKED" if self.status=="BLOCKED" else self.inventory_status,
                "generated_utc":datetime.now(timezone.utc).isoformat(),
                "scope":"Observed module items only; items outside Modules not inventoried; completeness unverified",
                "inventory":self.inventory},indent=2),encoding="utf-8")
            (REPORTS_DIR / "canvas_qc_results.json").write_text(json.dumps({"status":self.status,
                "pages":self.scanned_pages,"skipped_items":self.skipped_items},indent=2),encoding="utf-8")
            # Generate HTML Report
            print("\n[5/5] Generating Local HTML QC Report...")
            report_path = generate_html_report(
                course_url=self.course_url,
                scanned_results=self.scanned_pages,
                skipped_items=self.skipped_items,
                output_dir=REPORTS_DIR,
                scan_status=self.status,
                status_reason=self.status_reason
            )
            print(f"[*] Report successfully created: {report_path}")
            print(f"[*] Latest bookmark shortcut: {REPORTS_DIR / 'latest_report.html'}")

            return self.scanned_pages, self.skipped_items, report_path

        finally:
            self.close()

    def close(self):
        """Clean up browser resources safely."""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
