import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from qc_core.bb_scanner import BlackboardScanner

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path=='/login-case':
            self.send_response(302); self.send_header('Location','/login'); self.end_headers(); return
        self.send_response(403 if self.path=='/denied' else 200); self.end_headers()
        if self.path=='/login': body='<input type="password">'
        elif self.path=='/empty': body='<h2 id="course-content-outline-header-text">Course Content</h2>'
        elif self.path=='/wrong': body='<h1>Unrelated portal page</h1>'
        elif self.path=='/denied': body='Access denied'
        else:
            body='''<h2 id="course-content-outline-header-text">Course Content</h2>
<div class="itemContainer"><h3><button id="folder-title-_1_1" aria-expanded="false" aria-controls="folder-contents-_1_1" onclick="this.setAttribute('aria-expanded','true');document.getElementById(this.getAttribute('aria-controls')).hidden=false">Parent</button></h3><span>Hidden from students</span>
<div id="folder-contents-_1_1" hidden><div class="itemContainer"><h3><button id="folder-title-_2_1" aria-expanded="false" aria-controls="folder-contents-_2_1" onclick="this.setAttribute('aria-expanded','true');document.getElementById(this.getAttribute('aria-controls')).hidden=false">Nested</button></h3><span>Visible to students</span>
<div id="folder-contents-_2_1" hidden><div class="itemContainer"><h3><a id="document-_3_1" href="/document/_3_1">Lesson</a></h3><span>Visible to students</span></div></div></div></div></div><button disabled>No more content items to load</button>'''
        self.wfile.write(('<html><body>'+body+'</body></html>').encode())

class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def scan(self,path):
        with tempfile.TemporaryDirectory() as tmp:
            scanner=BlackboardScanner(f'http://127.0.0.1:{self.server.server_port}{path}',headless=True,
                browser_channel='chromium',auth_file=Path(tmp)/'isolated.json',output_dir=Path(tmp),timeout_ms=1000)
            items,report=scanner.run_inventory()
            self.assertTrue(report.exists())
            import json
            self.assertEqual(json.loads(report.read_text(encoding='utf-8'))['status'],scanner.status)
            return scanner,items
    def test_login_redirect(self):
        s,items=self.scan('/login-case'); self.assertEqual(s.status,'BLOCKED'); self.assertEqual(items,[])
    def test_access_denied(self):
        s,items=self.scan('/denied'); self.assertEqual(s.status,'BLOCKED'); self.assertEqual(items,[])
    def test_empty(self):
        s,items=self.scan('/empty'); self.assertEqual(s.status,'INCOMPLETE'); self.assertEqual(items,[])
    def test_unrecognized_page(self):
        s,items=self.scan('/wrong'); self.assertEqual(s.status,'INCOMPLETE'); self.assertEqual(items,[])
    def test_nested_inventory(self):
        s,items=self.scan('/nested'); self.assertEqual(s.status,'COLLECTED',s.issues)
        self.assertEqual(len(items),3)
        by_id={x['id']:x for x in items}
        self.assertEqual(by_id['_2_1']['parent_id'],'_1_1')
        self.assertEqual(by_id['_3_1']['parent_id'],'_2_1')
        self.assertEqual(by_id['_1_1']['visibility'],'HIDDEN')
        self.assertTrue(by_id['_1_1']['expanded'])
        self.assertTrue(by_id['_2_1']['expanded'])
        self.assertTrue(by_id['_3_1']['url'].endswith('/document/_3_1'))

if __name__=='__main__': unittest.main(verbosity=2)
