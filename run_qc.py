#!/usr/bin/env python3
"""
Canvas LMS Quality Control (QC) Runner
Inspects course modules and content pages for:
  - Rendered image loading failures (with issue screenshots)
  - Authenticated link checking (distinguishing broken vs auth/timeout links)
  - Video and embed discovery (marked NOT TESTED)
  - Non-destructive read-only operation
  - Local HTML report generation
"""

import sys
import os
import argparse
import webbrowser
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from qc_core.config import (
    DEFAULT_COURSE_URL,
    DEFAULT_MODULES_URL,
    AUTH_STATE_FILE,
    REPORTS_DIR
)
from qc_core.scanner import LMSScanner


def print_banner():
    banner = r"""
========================================================================
     __    __  ______     ____   ______
    / /   /  |/  / __/    / __ \ / ____/
   / /   / /|_/ /\ \     / / / // /
  / /___/ /  / /___/ /   / /_/ // /___
 /_____/_/  /_//___/     \___\_\\____/

 Canvas LMS Quality Control & Content Assurance Tool
 Target: Canvas Course 350 (OLE Bristol)
 Mode: Read-Only (Non-destructive inspection)
========================================================================
    """
    print(banner)


def main():
    parser = argparse.ArgumentParser(
        description="Canvas LMS Automated Quality Control (QC) Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Run automated test on local sample pages (1 working img, 1 broken img):
  python run_qc.py --local-sample

  # 2. Run standard live QC on Canvas Course 350:
  python run_qc.py

  # 3. Quick spot check (scan only first 3 pages):
  python run_qc.py --max-pages 3

  # 4. Clear saved session cookies and log in fresh:
  python run_qc.py --reset-auth
        """
    )

    parser.add_argument(
        "--course-url",
        default=DEFAULT_COURSE_URL,
        help=f"Canvas Course URL to inspect (default: {DEFAULT_COURSE_URL})"
    )
    parser.add_argument(
        "--local-sample",
        action="store_true",
        help="Run against local mock sample pages (verify broken/working images before live scan)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (default: visible browser for manual SSO/MFA login)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional maximum number of content pages to inspect"
    )
    parser.add_argument(
        "--reset-auth",
        action="store_true",
        help="Remove saved session state (.auth/storage_state.json) before running"
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not automatically open the generated HTML report in your browser"
    )

    parser.add_argument("--browser", choices=["chrome", "msedge", "chromium"],
                        default="chrome", help="Browser to launch (default: installed Chrome)")
    args = parser.parse_args()

    print_banner()

    # If --reset-auth requested, delete local session state
    if args.reset_auth and AUTH_STATE_FILE.exists():
        try:
            AUTH_STATE_FILE.unlink()
            print(f"[*] Cleared previous session: {AUTH_STATE_FILE}\n")
        except Exception as e:
            print(f"[!] Warning clearing session: {e}\n")

    # If --local-sample requested, delegate to local test suite
    if args.local_sample:
        from test_qc import run_local_test
        success = run_local_test()
        latest_report = REPORTS_DIR / "latest_report.html"
        if success and latest_report.exists() and not args.no_open:
            print(f"[*] Opening test report in your browser: {latest_report.resolve().as_uri()}")
            webbrowser.open(latest_report.resolve().as_uri())
        sys.exit(0 if success else 1)

    # Live Canvas Scan
    print(f"Target Course: {args.course_url}")
    print(f"Modules View : {args.course_url.rstrip('/')}/modules")
    print("Security Note: antigravity & this tool NEVER ask for your password in chat or terminal.")
    print(f"Browser Mode : headless={args.headless}; browser={args.browser}\n")

    scanner = LMSScanner(
        course_url=args.course_url,
        headless=args.headless,
        auth_file=AUTH_STATE_FILE,
        browser_channel=args.browser
    )

    try:
        scanned_pages, skipped_items, report_path = scanner.run_qc(max_pages=args.max_pages)

        # Print summary in console
        total_pages = len(scanned_pages)
        total_skipped = len(skipped_items)
        failed_pages = sum(1 for p in scanned_pages if p.get("overall_status") == "FAIL")
        passed_pages = sum(1 for p in scanned_pages if p.get("overall_status") == "PASS")
        warn_pages = sum(1 for p in scanned_pages if p.get("overall_status") == "NOT TESTED")

        total_broken_imgs = sum(
            sum(1 for img in p.get("images", []) if img["status"] == "FAIL")
            for p in scanned_pages
        )
        total_broken_links = sum(
            sum(1 for lk in p.get("links", []) if lk["status"] == "FAIL")
            for p in scanned_pages
        )
        total_embeds = sum(len(p.get("embeds", [])) for p in scanned_pages)

        print("\n" + "=" * 70)
        print(" LMS QC SCAN SUMMARY")
        print("=" * 70)
        print(f" Total Content Pages Scanned : {total_pages}")
        print(f" Total Module Items Skipped  : {total_skipped}")
        print(f" Clean Content Pages (PASS)  : {passed_pages}")
        print(f" Pages with Issues (FAIL)    : {failed_pages}")
        print(f" Broken Images Found         : {total_broken_imgs}")
        print(f" Confirmed Broken Links      : {total_broken_links}")
        print(f" Videos / Embeds (NOT TESTED): {total_embeds}")
        print("-" * 70)
        print(f" HTML QC Report: {report_path}")
        print(f" Latest Shortcut: {REPORTS_DIR / 'latest_report.html'}")
        print("=" * 70 + "\n")

        # Automatically open HTML report in browser
        if not args.no_open and report_path.exists():
            report_uri = report_path.resolve().as_uri()
            print(f"[*] Opening QC report in your default browser: {report_uri}")
            try:
                webbrowser.open(report_uri)
            except Exception:
                pass

        return 0 if scanner.status == "PASS" else (1 if scanner.status == "FAIL" else 2)

    except KeyboardInterrupt:
        print("\n[!] Scan interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\n[!] Unexpected error during QC scan: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
