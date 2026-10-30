import sys
import os
import time
import socket
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from qc_core.scanner import LMSScanner
from qc_core.config import REPORTS_DIR, SCREENSHOTS_DIR


class MockLMSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        directory = str(PROJECT_ROOT / "test_samples")
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        # Simulate SSO / Login endpoint
        if self.path.startswith("/login"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>University Single Sign-On (SSO) Portal</h1></body></html>")
            return
        # Fall back to serving test_samples static files
        super().do_GET()

    def log_message(self, format, *args):
        # Suppress verbose HTTP server logging in test output
        pass


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def run_local_test() -> bool:
    print("\n" + "=" * 70)
    print(" LMS QC TEST RUNNER - LOCAL SAMPLE PAGES VERIFICATION (REQ 13)")
    print("=" * 70)

    port = find_free_port()
    server = HTTPServer(("127.0.0.1", port), MockLMSHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    test_base_url = f"http://127.0.0.1:{port}"
    mock_modules_url = f"{test_base_url}/index.html"
    print(f"[*] Started local mock LMS server at: {mock_modules_url}")


    scanner = LMSScanner(course_url=mock_modules_url, headless=True,
                         auth_file=PROJECT_ROOT / ".auth" / "local_test_unused.json")

    try:
        scanned_pages, skipped_items, report_path = scanner.run_qc()

        print("\n" + "-" * 70)
        print(" VERIFYING QC CHECK RESULTS AGAINST LOCAL TEST SAMPLES")
        print("-" * 70)

        # 1. Verify Scanned and Skipped counts
        print(f"[*] Scanned pages: {len(scanned_pages)} | Skipped items: {len(skipped_items)}")
        assert len(scanned_pages) >= 2, f"Expected at least 2 scannable pages, found {len(scanned_pages)}"
        assert len(skipped_items) >= 2, f"Expected at least 2 skipped items, found {len(skipped_items)}"

        # 2. Inspect Lesson 1 (Diagnostics Page)
        page1 = next((p for p in scanned_pages if "Lesson 1" in p["title"]), None)
        assert page1 is not None, "Lesson 1 page was not found in scanned results!"

        images = page1["images"]
        links = page1["links"]
        embeds = page1["embeds"]

        # Image assertions: 1 working image, 1 broken image
        good_imgs = [img for img in images if img["status"] == "PASS"]
        bad_imgs = [img for img in images if img["status"] == "FAIL"]
        print(f"[*] Images detected on Lesson 1: {len(images)} (Working: {len(good_imgs)}, Broken: {len(bad_imgs)})")

        assert len(good_imgs) >= 1, "Working image was not marked as PASS!"
        assert len(bad_imgs) >= 1, "Broken image was not detected as FAIL!"
        assert bad_imgs[0]["screenshot"] is not None, "Screenshot was not recorded for broken image!"

        screenshot_full_path = REPORTS_DIR / bad_imgs[0]["screenshot"]
        assert screenshot_full_path.exists(), f"Screenshot file missing at: {screenshot_full_path}"
        print(f"  [PASS] Broken image correctly failed and screenshot saved: {bad_imgs[0]['screenshot']}")

        # Link assertions:
        working_links = [l for l in links if l["status"] == "PASS"]
        broken_links = [l for l in links if l["status"] == "FAIL"]
        auth_links = [l for l in links if l.get("category") == "AUTH_REQUIRED"]

        print(f"[*] Links detected on Lesson 1: {len(links)} (Working: {len(working_links)}, Broken: {len(broken_links)}, Auth/SSO: {len(auth_links)})")
        assert len(working_links) >= 1, "Working link was not detected as PASS!"
        assert len(broken_links) >= 1, "Broken 404 link was not detected as FAIL!"
        assert len(auth_links) >= 1, "SSO / Login link was incorrectly classified! Must be NOT TESTED / AUTH_REQUIRED."
        assert all(l["status"] != "FAIL" for l in auth_links), "Auth/Login link was classified as broken FAIL (Violates Req 6)!"
        print("  [PASS] Confirmed broken 404 link failed; SSO/login link was preserved as NOT TESTED (Req 6 compliant).")

        # Embed assertions:
        print(f"[*] Embeds / Videos detected on Lesson 1: {len(embeds)}")
        assert len(embeds) >= 2, f"Expected 2 embeds (video + iframe), found {len(embeds)}"
        assert all(emb["status"] == "NOT TESTED" for emb in embeds), "Embed was not marked as NOT TESTED (Violates Req 7)!"
        print("  [PASS] All detected videos and iframes recorded and marked NOT TESTED (Req 7 compliant).")

        # 3. Inspect Lesson 2 (Clean Page)
        page2 = next((p for p in scanned_pages if "Lesson 2" in p["title"]), None)
        assert page2 is not None, "Lesson 2 page was not found in scanned results!"
        assert page2["overall_status"] == "PASS", f"Lesson 2 expected PASS, got {page2['overall_status']}"
        print("  [PASS] Clean content page passed all quality checks.")

        # 4. Report assertion
        assert report_path.exists(), f"Report was not generated at {report_path}"
        report_text = report_path.read_text(encoding="utf-8")
        assert "PASS" in report_text
        assert "FAIL" in report_text
        assert "NOT TESTED" in report_text
        assert "SKIPPED" in report_text
        assert "screenshots/" in report_text
        print(f"  [PASS] HTML QC Report verified and populated ({report_path.stat().st_size} bytes).")

        print("\n" + "=" * 70)
        print(" ALL PRE-SCAN LOCAL VERIFICATION TESTS PASSED SUCCESSFULLY! (100%)")
        print("=" * 70 + "\n")
        return True

    except Exception as e:
        print(f"\n[FAIL] Test assertion failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    success = run_local_test()
    sys.exit(0 if success else 1)
