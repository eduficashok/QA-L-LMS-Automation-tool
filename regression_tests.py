import tempfile
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import qc_core.scanner as module
from qc_core.scanner import LMSScanner

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == '/courses/1/modules':
            self.send_response(302); self.send_header('Location', '/login'); self.end_headers(); return
        status = 403 if self.path == '/courses/3/modules' else 200
        self.send_response(status); self.end_headers()
        body = '<input type="password">' if self.path == '/login' else '<div id="context_modules"></div>'
        self.wfile.write(('<html><body>' + body + '</body></html>').encode())

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            module.REPORTS_DIR = Path(directory) / 'reports'
            for number, expected in [(1, 'BLOCKED'), (2, 'INCOMPLETE'), (3, 'BLOCKED')]:
                scanner = LMSScanner(f'http://127.0.0.1:{server.server_port}/courses/{number}', headless=True,
                                     auth_file=Path(directory) / 'no-session.json')
                scanned, skipped, report = scanner.run_qc()
                assert not scanned, scanned
                assert scanner.status == expected, scanner.status
                assert f'SCAN STATUS: {expected}' in report.read_text(encoding='utf-8')
                print(f'[PASS] course {number}: {expected}; zero content pages scanned; HTML status verified')
        print('ALL 3 REGRESSION TESTS PASSED')
    finally:
        server.shutdown(); server.server_close(); thread.join()
