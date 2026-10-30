import tempfile
import unittest
from pathlib import Path
from qc_core.comparison import compare,write_comparison
from qc_core.checks import is_auth_or_login_url,check_images
from qc_core.reporter import generate_html_report
from playwright.sync_api import sync_playwright

class QAUnitTests(unittest.TestCase):
    def test_title_match_is_not_course_pass(self):
        s={'status':'COLLECTED','inventory':[{'title':'Lesson 1'}]}
        r=compare(s,s); self.assertEqual(r['rows'][0]['status'],'MATCHED_TITLE'); self.assertNotEqual(r['status'],'PASS')
    def test_duplicate_title_requires_review(self):
        s={'status':'COLLECTED','inventory':[{'title':'Lesson'}]}
        r=compare(s,dict(s,inventory=[{'title':'Lesson'},{'title':'Lesson'}]))
        self.assertEqual(r['rows'][0]['status'],'NEEDS REVIEW')
    def test_incomplete_target_never_confirms_missing(self):
        r=compare({'status':'COLLECTED','inventory':[{'title':'Lesson'}]}, {'status':'OBSERVED','inventory':[]})
        self.assertEqual(r['status'],'INCOMPLETE'); self.assertEqual(r['rows'][0]['status'],'NOT TESTED')
    def test_blocked_inventory(self):
        self.assertEqual(compare({'status':'BLOCKED'}, {'status':'COLLECTED'})['status'],'BLOCKED')
    def test_report_escapes_content(self):
        s={'status':'COLLECTED','inventory':[{'title':'<script>alert(1)</script>'}]}
        with tempfile.TemporaryDirectory() as d:
            report=write_comparison(compare(s,s),d)
            self.assertNotIn('<script>',report.read_text(encoding='utf-8'))
    def test_auth_url_not_arbitrary_substring(self):
        self.assertFalse(is_auth_or_login_url('https://example.org/authors/lesson'))
        self.assertTrue(is_auth_or_login_url('https://example.org/login'))
    def test_report_preserves_not_tested(self):
        row={'title':'Lesson','overall_status':'NOT TESTED','error':'navigation timeout','images':[],'links':[],'embeds':[]}
        with tempfile.TemporaryDirectory() as d:
            generate_html_report('https://example.org',[row],[],Path(d))
        self.assertEqual(row['overall_status'],'NOT TESTED')
    def test_loading_image_not_pass(self):
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                page.set_content('<main><img id="pending" src="data:image/png;base64,bad"></main>')
                page.evaluate('''() => {const img=document.getElementById('pending');Object.defineProperty(img,'complete',{get:()=>false});Object.defineProperty(img,'naturalWidth',{get:()=>0});}''')
                with tempfile.TemporaryDirectory() as d:
                    results=check_images(page,'pending',Path(d))
                self.assertEqual(results[0]['status'],'NOT TESTED')
            finally: browser.close()

if __name__=='__main__': unittest.main(verbosity=2)
