#!/usr/bin/env python3
"""
Web QA Automation Dashboard Server for LMS (Canvas & Blackboard Ultra).
Provides a local web interface to trigger, monitor, inspect errors, and view HTML reports
without touching or modifying the underlying qc_core automation logic.
"""

import sys
import os
import json
import time
import socket
import threading
import traceback
import builtins
import webbrowser
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from qc_core.config import (
    DEFAULT_COURSE_URL,
    DEFAULT_MODULES_URL,
    REPORTS_DIR,
    SCREENSHOTS_DIR,
    AUTH_STATE_FILE
)
from qc_core.scanner import LMSScanner
from qc_core.bb_scanner import BlackboardScanner, DEFAULT_URL as DEFAULT_BB_URL
from qc_core.comparison import compare, write_comparison


class ScanStateManager:
    """Thread-safe manager for LMS scan execution, logs, and error states."""

    def __init__(self):
        self.lock = threading.RLock()
        self.state = "IDLE"  # IDLE, RUNNING, WAITING_FOR_LOGIN, DONE, ERROR
        self.mode = None     # canvas, blackboard, workflow, mock_canvas
        self.current_task = ""
        self.login_prompt = ""
        self.login_lms = ""
        self.logs = []
        self.start_time = None
        self.end_time = None
        self.last_error = None
        self.login_event = threading.Event()
        self.cancel_event = threading.Event()
        self.current_scanner = None
        self.worker_thread = None

    def reset_for_run(self, mode):
        with self.lock:
            self.state = "RUNNING"
            self.mode = mode
            self.current_task = "Initializing scanner..."
            self.login_prompt = ""
            self.login_lms = ""
            self.logs = []
            self.start_time = time.time()
            self.end_time = None
            self.last_error = None
            self.login_event.clear()
            self.cancel_event.clear()
            self.current_scanner = None

    def add_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {message}"
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 1500:
                self.logs.pop(0)
        # Also print to terminal for development transparency
        try:
            sys.__stdout__.write(entry + "\n")
            sys.__stdout__.flush()
        except Exception:
            pass

    def request_login_confirmation(self, prompt, lms_name):
        with self.lock:
            self.state = "WAITING_FOR_LOGIN"
            self.login_prompt = prompt
            self.login_lms = lms_name
            self.current_task = f"Awaiting university SSO/MFA login in {lms_name} browser window..."
        self.add_log(f"*** AWAITING USER LOGIN ({lms_name}) ***: {prompt}")

    def confirm_login(self):
        with self.lock:
            if self.state == "WAITING_FOR_LOGIN":
                self.state = "RUNNING"
                self.current_task = "Login confirmed. Resuming automation..."
                self.add_log("[*] Login confirmation received from Web Dashboard. Continuing...")
                self.login_event.set()
                return True
            return False

    def cancel_scan(self):
        with self.lock:
            if self.state in ("RUNNING", "WAITING_FOR_LOGIN"):
                self.add_log("[!] Scan cancellation requested by user.")
                self.cancel_event.set()
                self.login_event.set()  # Unblock if waiting
                if self.current_scanner and hasattr(self.current_scanner, "close"):
                    try:
                        self.current_scanner.close()
                    except Exception:
                        pass
                self.state = "ERROR"
                self.current_task = "Scan cancelled by user."
                self.end_time = time.time()
                return True
            return False

    def mark_completed(self, success=True, error_msg=None):
        with self.lock:
            self.end_time = time.time()
            if success:
                self.state = "DONE"
                self.current_task = "Scan completed successfully."
            else:
                self.state = "ERROR"
                self.last_error = error_msg
                self.current_task = f"Failed: {error_msg}"
        if success:
            self.add_log("[✓] All checks finished. Reports generated.")
        else:
            self.add_log(f"[!] Scan halted with error: {error_msg}")

    def get_snapshot(self):
        with self.lock:
            return {
                "state": self.state,
                "mode": self.mode,
                "current_task": self.current_task,
                "login_prompt": self.login_prompt,
                "login_lms": self.login_lms,
                "logs": list(self.logs),
                "start_time": self.start_time,
                "end_time": self.end_time,
                "duration_seconds": round((self.end_time or time.time()) - (self.start_time or time.time()), 1) if self.start_time else 0,
                "last_error": self.last_error
            }


state_mgr = ScanStateManager()


class StdoutInterceptor:
    """Redirects stdout writes into state_mgr.logs without breaking standard terminal."""
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, text):
        if text:
            # Strip trailing newlines and handle line by line
            lines = text.splitlines()
            for line in lines:
                clean = line.strip()
                if clean:
                    state_mgr.add_log(clean)
            self.original_stdout.write(text)
            self.original_stdout.flush()

    def flush(self):
        self.original_stdout.flush()


def run_scan_worker(params):
    """Executes the selected scan in a background thread."""
    mode = params.get("mode", "canvas")
    state_mgr.reset_for_run(mode)

    # Patch builtins.input so manual logins can be confirmed directly from Web UI
    original_input = builtins.input
    original_stdout = sys.stdout

    def intercepted_input(prompt=""):
        lms_label = "Blackboard Ultra" if "SCAN" in prompt or "Blackboard" in prompt else "Canvas LMS"
        state_mgr.request_login_confirmation(prompt, lms_label)
        while not state_mgr.login_event.is_set():
            if state_mgr.cancel_event.is_set():
                raise KeyboardInterrupt("Cancelled from Web Dashboard")
            time.sleep(0.3)
        state_mgr.login_event.clear()
        return "SCAN"

    try:
        builtins.input = intercepted_input
        sys.stdout = StdoutInterceptor(original_stdout)

        browser = params.get("browser", "msedge")
        headless = bool(params.get("headless", False))
        max_pages = params.get("max_pages")
        if max_pages:
            try:
                max_pages = int(max_pages)
            except Exception:
                max_pages = None

        if mode == "canvas":
            canvas_url = params.get("canvas_url", DEFAULT_COURSE_URL).strip() or DEFAULT_COURSE_URL
            state_mgr.add_log(f"Starting Canvas Quality Control Scanner for: {canvas_url}")
            scanner = LMSScanner(
                course_url=canvas_url,
                headless=headless,
                browser_channel=browser
            )
            state_mgr.current_scanner = scanner
            scanned_pages, skipped_items, report_path = scanner.run_qc(max_pages=max_pages)
            state_mgr.mark_completed(success=(scanner.status != "BLOCKED"), error_msg=scanner.status_reason if scanner.status == "BLOCKED" else None)

        elif mode == "blackboard":
            bb_url = params.get("blackboard_url", DEFAULT_BB_URL).strip() or DEFAULT_BB_URL
            state_mgr.add_log(f"Starting Blackboard Outline Inventory Scanner for: {bb_url}")
            scanner = BlackboardScanner(
                course_url=bb_url,
                headless=headless,
                browser_channel=browser
            )
            state_mgr.current_scanner = scanner
            items, path = scanner.run_inventory()
            state_mgr.mark_completed(success=(scanner.status != "BLOCKED"), error_msg=scanner.status_reason if scanner.status == "BLOCKED" else None)

        elif mode == "workflow":
            bb_url = params.get("blackboard_url", DEFAULT_BB_URL).strip() or DEFAULT_BB_URL
            canvas_url = params.get("canvas_url", DEFAULT_COURSE_URL).strip() or DEFAULT_COURSE_URL
            state_mgr.add_log("=== Step 1/3: Running Blackboard Outline Inventory ===")
            bb = BlackboardScanner(bb_url, headless=headless, browser_channel=browser)
            state_mgr.current_scanner = bb
            bb.run_inventory()

            if bb.status == "BLOCKED":
                state_mgr.mark_completed(success=False, error_msg=f"Blackboard scan BLOCKED: {bb.status_reason}")
                return

            if state_mgr.cancel_event.is_set():
                state_mgr.mark_completed(success=False, error_msg="Cancelled by user.")
                return

            state_mgr.add_log("=== Step 2/3: Running Canvas Quality Control Scan ===")
            canvas = LMSScanner(canvas_url, headless=headless, browser_channel=browser)
            state_mgr.current_scanner = canvas
            canvas.run_qc(max_pages=max_pages)

            state_mgr.add_log("=== Step 3/3: Comparing Blackboard & Canvas Outline Inventories ===")
            source = json.loads((REPORTS_DIR / "blackboard_inventory.json").read_text(encoding="utf-8"))
            target = json.loads((REPORTS_DIR / "canvas_inventory.json").read_text(encoding="utf-8"))
            result = compare(source, target)
            comp_report = write_comparison(result, REPORTS_DIR)
            state_mgr.add_log(f"Comparison Status: {result.get('status')} | Report: {comp_report}")
            state_mgr.mark_completed(success=True)

        elif mode == "mock_canvas":
            import subprocess
            state_mgr.add_log("Starting Local Mock QC Verification Scan (Isolated Process)...")
            cmd = [sys.executable, str(PROJECT_ROOT / "run_qc.py"), "--local-sample", "--no-open"]
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            output, _ = proc.communicate(timeout=60)
            for line in output.splitlines():
                clean = line.strip()
                if clean:
                    state_mgr.add_log(clean)
            state_mgr.mark_completed(success=(proc.returncode == 0))

        else:
            state_mgr.mark_completed(success=False, error_msg=f"Unknown scan mode: {mode}")

    except KeyboardInterrupt:
        state_mgr.mark_completed(success=False, error_msg="Scan cancelled by user.")
    except Exception as exc:
        traceback_str = traceback.format_exc()
        state_mgr.add_log(f"Exception during scan: {type(exc).__name__}: {exc}\n{traceback_str}")
        state_mgr.mark_completed(success=False, error_msg=f"{type(exc).__name__}: {exc}")
    finally:
        builtins.input = original_input
        sys.stdout = original_stdout


def get_errors_summary():
    """Extracts exact categorized errors from the generated report JSONs."""
    summary = {
        "canvas": {
            "has_data": False,
            "status": "NONE",
            "total_pages": 0,
            "broken_images": [],
            "broken_links": [],
            "auth_links": [],
            "embeds": [],
            "skipped_items": []
        },
        "blackboard": {
            "has_data": False,
            "status": "NONE",
            "reason": "",
            "items_count": 0,
            "issues": []
        },
        "comparison": {
            "has_data": False,
            "status": "NONE",
            "matched_count": 0,
            "source_only": [],
            "target_only": [],
            "duplicate_titles": []
        }
    }

    # 1. Parse Canvas QC Results
    canvas_json_path = REPORTS_DIR / "canvas_qc_results.json"
    if canvas_json_path.exists():
        try:
            cdata = json.loads(canvas_json_path.read_text(encoding="utf-8"))
            pages = cdata.get("pages", [])
            summary["canvas"]["has_data"] = True
            summary["canvas"]["status"] = cdata.get("status", "UNKNOWN")
            summary["canvas"]["total_pages"] = len(pages)

            for page in pages:
                page_title = page.get("title", "Untitled Page")
                page_url = page.get("url", "")

                for img in page.get("images", []):
                    if img.get("status") == "FAIL":
                        summary["canvas"]["broken_images"].append({
                            "page_title": page_title,
                            "page_url": page_url,
                            "src": img.get("src", ""),
                            "alt": img.get("alt", "(no alt text)"),
                            "reason": img.get("reason", "Render error"),
                            "screenshot": f"/reports/{img.get('screenshot')}" if img.get("screenshot") else None
                        })

                for link in page.get("links", []):
                    if link.get("status") == "FAIL":
                        summary["canvas"]["broken_links"].append({
                            "page_title": page_title,
                            "page_url": page_url,
                            "href": link.get("href", ""),
                            "text": link.get("text", "(no link text)"),
                            "reason": link.get("reason", "HTTP check failed"),
                            "category": link.get("category", "BROKEN_LINK")
                        })
                    elif link.get("category") == "AUTH_REQUIRED":
                        summary["canvas"]["auth_links"].append({
                            "page_title": page_title,
                            "href": link.get("href", ""),
                            "text": link.get("text", ""),
                            "reason": link.get("reason", "")
                        })

                for emb in page.get("embeds", []):
                    summary["canvas"]["embeds"].append({
                        "page_title": page_title,
                        "src": emb.get("src", ""),
                        "type": emb.get("type", "embed"),
                        "reason": emb.get("reason", "Playback NOT TESTED")
                    })

            summary["canvas"]["skipped_items"] = cdata.get("skipped_items", [])
        except Exception as e:
            summary["canvas"]["parse_error"] = str(e)

    # 2. Parse Blackboard Inventory
    bb_json_path = REPORTS_DIR / "blackboard_inventory.json"
    if bb_json_path.exists():
        try:
            bdata = json.loads(bb_json_path.read_text(encoding="utf-8"))
            summary["blackboard"]["has_data"] = True
            summary["blackboard"]["status"] = bdata.get("status", "UNKNOWN")
            summary["blackboard"]["reason"] = bdata.get("reason", "")
            summary["blackboard"]["items_count"] = len(bdata.get("inventory", []))
            summary["blackboard"]["issues"] = bdata.get("issues", [])
        except Exception as e:
            summary["blackboard"]["parse_error"] = str(e)

    # 3. Parse Comparison Report
    comp_json_path = REPORTS_DIR / "comparison_report.json"
    if comp_json_path.exists():
        try:
            cmpdata = json.loads(comp_json_path.read_text(encoding="utf-8"))
            summary["comparison"]["has_data"] = True
            summary["comparison"]["status"] = cmpdata.get("status", "UNKNOWN")
            summary["comparison"]["matched_count"] = len(cmpdata.get("matched", []))
            summary["comparison"]["source_only"] = cmpdata.get("source_only", [])
            summary["comparison"]["target_only"] = cmpdata.get("target_only", [])
            summary["comparison"]["duplicate_titles"] = cmpdata.get("duplicate_titles", [])
        except Exception as e:
            summary["comparison"]["parse_error"] = str(e)

    return summary


def get_available_reports():
    """Lists HTML and JSON report files available in reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for f in sorted(REPORTS_DIR.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True):
        files.append({
            "name": f.name,
            "url": f"/reports/{f.name}",
            "size_bytes": f.stat().st_size,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
            "is_latest": f.name in ("latest_report.html", "comparison_report.html")
        })
    return files


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    """Handles REST API calls and serves UI and report static assets."""

    def __init__(self, *args, **kwargs):
        # Default directory for static files is PROJECT_ROOT / 'web_ui'
        super().__init__(*args, directory=str(PROJECT_ROOT / "web_ui"), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. API: Current Status Snapshot
        if path == "/api/status":
            self.send_json_response(state_mgr.get_snapshot())
            return

        # 2. API: Categorized Exact Errors
        if path == "/api/errors":
            self.send_json_response(get_errors_summary())
            return

        # 3. API: Available Reports List
        if path == "/api/reports":
            self.send_json_response(get_available_reports())
            return

        # 4. Static Reports & Screenshots Serving
        if path.startswith("/reports/"):
            relative_path = path[len("/reports/"):]
            file_path = (REPORTS_DIR / relative_path).resolve()
            # Ensure path does not escape REPORTS_DIR
            if file_path.is_file() and str(file_path).startswith(str(REPORTS_DIR.resolve())):
                self.serve_file(file_path)
                return
            else:
                self.send_error(404, "Report file not found")
                return

        # Default fallback to serve web_ui assets (index.html, etc.)
        if path == "/" or not path:
            index_path = PROJECT_ROOT / "web_ui" / "index.html"
            if index_path.exists():
                self.serve_file(index_path, content_type="text/html; charset=utf-8")
                return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            params = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            params = {}

        # 1. API: Start Scan
        if path == "/api/scan":
            snapshot = state_mgr.get_snapshot()
            if snapshot["state"] in ("RUNNING", "WAITING_FOR_LOGIN"):
                self.send_json_response({"error": "A scan is already in progress."}, status=409)
                return

            worker = threading.Thread(target=run_scan_worker, args=(params,), daemon=True)
            state_mgr.worker_thread = worker
            worker.start()

            self.send_json_response({"message": "Scan initiated", "mode": params.get("mode")})
            return

        # 2. API: Confirm Login
        if path == "/api/confirm_login":
            confirmed = state_mgr.confirm_login()
            self.send_json_response({"success": confirmed})
            return

        # 3. API: Cancel Scan
        if path == "/api/cancel":
            cancelled = state_mgr.cancel_scan()
            self.send_json_response({"success": cancelled})
            return

        self.send_error(404, "API endpoint not found")

    def send_json_response(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def serve_file(self, file_path, content_type=None):
        try:
            data = file_path.read_bytes()
            if not content_type:
                suffix = file_path.suffix.lower()
                if suffix == ".html": content_type = "text/html; charset=utf-8"
                elif suffix == ".json": content_type = "application/json; charset=utf-8"
                elif suffix == ".png": content_type = "image/png"
                elif suffix == ".jpg" or suffix == ".jpeg": content_type = "image/jpeg"
                elif suffix == ".css": content_type = "text/css; charset=utf-8"
                elif suffix == ".js": content_type = "application/javascript; charset=utf-8"
                else: content_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def log_message(self, format, *args):
        # Keep server log clean; only log errors
        if args and str(args[1]) not in ("200", "304"):
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))


def find_available_port(starting_port=8080, max_attempts=20):
    for port in range(starting_port, starting_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return starting_port


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LMS QA Automation Web Dashboard Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    args = parser.parse_args()

    port = find_available_port(args.port)
    server_address = ("127.0.0.1", port)
    httpd = DashboardServer(server_address, DashboardRequestHandler)

    url = f"http://127.0.0.1:{port}"
    print("=" * 75)
    print("   LMS QA AUTOMATION - WEB CONTROL DASHBOARD")
    print(f"   Server active at: {url}")
    print("   Open this URL in your browser to run scans and view error reports.")
    print("=" * 75)

    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.0), webbrowser.open(url)), daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Web Dashboard Server...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
