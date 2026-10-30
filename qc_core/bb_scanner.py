"""Read-only Blackboard Ultra outline inventory. No content or media QC implied."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = 'https://www.ole.bris.ac.uk/ultra/courses/_268444_1/outline'
TOGGLES = 'button[id^="learning-module-title-"], button[id^="folder-title-"]'

# Observed on the actual Bristol Ultra outline, not Canvas selectors.
COLLECT = r'''() => {
 const nodes = Array.from(document.querySelectorAll('.itemContainer'));
 const own = (row, selector) => Array.from(row.querySelectorAll(selector)).filter(e => e.closest('.itemContainer') === row);
 const key = row => {
   const t = own(row, 'button[id^="folder-title-"],button[id^="learning-module-title-"]')[0];
   const m = own(row, '[id^="content-item-overflow-menu-button-"]')[0];
   const a = own(row, 'h3 a[href]')[0];
   const raw = (t || m || a)?.id || a?.getAttribute('href') || '';
   return raw.match(/_\d+_\d+/)?.[0] || raw || null;
 };
 return nodes.map((row, index) => {
   const toggle = own(row, 'button[id^="folder-title-"],button[id^="learning-module-title-"]')[0];
   const heading = own(row, 'h3')[0];
   const menu = own(row, '[id^="content-item-overflow-menu-button-"]')[0];
   const link = own(row, 'h3 a[href]')[0];
   const label = (menu?.getAttribute('aria-label') || '').replace(/^More options for /,'');
   const title = (heading?.textContent || toggle?.textContent || label || '').trim() || null;
   const spans = own(row,'span').map(e => e.textContent.trim());
   const visibility = spans.includes('Hidden from students') ? 'HIDDEN' : spans.includes('Visible to students') ? 'VISIBLE' : 'UNKNOWN';
   let parent = row.parentElement?.closest('.itemContainer');
   // Some Ultra child containers are siblings of the parent item.
   if (!parent) {
     const region = row.parentElement?.closest('[id^="learning-module-contents-"],[id^="folder-contents-"]');
     if(region) parent = nodes.find(r => own(r,'button[aria-controls]').some(b => b.getAttribute('aria-controls') === region.id));
   }
   const icon = own(row,'svg[aria-label]')[0]?.getAttribute('aria-label');
   const controls = toggle?.getAttribute('aria-controls');
   const panel = controls ? document.getElementById(controls) : null;
   const links = own(row,'a[href]').filter(a => !a.closest('[role="menu"]')).map(a => ({title:a.textContent.trim(), url:a.href}));
   return {id:key(row), title, type:toggle ? (toggle.id.startsWith('folder-')?'Folder':'Learning Module') : (icon || 'Content'),
     parent_id:parent?key(parent):null, position:index, url:link?.href || null, links, visibility,
     toggle_id:toggle?.id || null, expanded:toggle?toggle.getAttribute('aria-expanded') === 'true':null,
     panel_found:toggle?Boolean(panel):null};
 });
}'''

class BlackboardScanner:
    def __init__(self, course_url=DEFAULT_URL, headless=False, auth_file=None,
                 browser_channel='msedge', output_dir=None, timeout_ms=15000):
        self.course_url = course_url.rstrip('/')
        self.headless = headless
        self.auth_file = Path(auth_file) if auth_file else ROOT / '.auth/bb_auth.json'
        self.output_dir = Path(output_dir) if output_dir else ROOT / 'reports'
        self.browser_channel = browser_channel
        self.timeout_ms = timeout_ms
        self.status = 'INCOMPLETE'
        self.status_reason = 'Not run'
        self.inventory = []
        self.issues = []
        self.playwright = self.browser = self.context = self.page = None

    def access_problem(self, response=None):
        current, expected = urlparse(self.page.url), urlparse(self.course_url)
        if current.netloc != expected.netloc:
            return 'Redirected outside course host'
        if re.search(r'/(login|signin|sso|auth|saml|unauthorized|access_denied)(/|$)', current.path, re.I):
            return 'Authentication page reached'
        if response and response.status in (401,403):
            return f'Access denied: HTTP {response.status}'
        if self.page.locator('input[type="password"]').count():
            return 'Login form reached'
        body = self.page.locator('body').inner_text().lower()
        if any(x in body for x in ('access denied','you do not have permission to access','you are unauthorized')):
            return 'Access denied page reached'
        return None

    def start_browser(self):
        self.playwright = sync_playwright().start()
        options = {'headless':self.headless}
        if self.browser_channel != 'chromium':
            options['channel'] = self.browser_channel
        print(f'Launching {self.browser_channel}; visible={not self.headless}', flush=True)
        self.browser = self.playwright.chromium.launch(**options)
        kwargs = {'viewport':{'width':1400,'height':950}}
        if self.auth_file.exists():
            kwargs['storage_state'] = str(self.auth_file)
        self.context = self.browser.new_context(**kwargs)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        if not self.headless:
            self.page.bring_to_front()

    def _expand_all(self):
        attempted = set()
        for _ in range(300):
            reason = self.access_problem()
            if reason:
                self.status = 'BLOCKED'; self.issues.append(reason); return
            pending = []
            for button in self.page.locator(TOGGLES).all():
                bid = button.get_attribute('id')
                if button.get_attribute('aria-expanded') != 'true' and bid not in attempted:
                    pending.append((bid,button))
            if pending:
                bid, button = pending[0]; attempted.add(bid)
                try:
                    button.click(timeout=self.timeout_ms)
                    self.page.wait_for_function('(id) => document.getElementById(id)?.getAttribute("aria-expanded") === "true"',arg=bid)
                    panel = button.get_attribute('aria-controls')
                    if panel:
                        self.page.locator('[id="'+panel+'"]').wait_for(state='attached')
                    self.page.wait_for_timeout(350)
                except Exception as exc:
                    self.issues.append(f'Could not expand {bid}: {type(exc).__name__}')
                continue
            more = self.page.get_by_role('button',name=re.compile(r'^(Load more|Load more content|Load more content items)$',re.I))
            available = [b for b in more.all() if b.is_visible() and b.is_enabled()]
            if available:
                try:
                    available[0].click(); self.page.wait_for_timeout(500)
                except Exception as exc:
                    self.issues.append(f'Additional content load failed: {type(exc).__name__}'); return
                continue
            # Wait for asynchronous children to mount, then verify stable item count.
            before = self.page.locator('.itemContainer').count()
            self.page.wait_for_timeout(700)
            if before != self.page.locator('.itemContainer').count():
                continue
            return
        self.issues.append('Expansion/loading limit reached')

    def _collect_items(self):
        return self.page.evaluate(COLLECT)

    def inspect_outline(self, response=None):
        reason = self.access_problem(response)
        if reason:
            self.status='BLOCKED'; self.status_reason=reason; return
        if response and response.status >= 400:
            self.status_reason=f'Outline HTTP {response.status}'; return
        if urlparse(self.page.url).path.rstrip('/') != urlparse(self.course_url).path.rstrip('/'):
            self.status_reason='Exact course outline not reached'; return
        try:
            self.page.locator('#course-content-outline-header-text').wait_for(state='attached')
        except Exception:
            self.status_reason='Course Content outline marker not found'; return
        self._expand_all()
        if self.status == 'BLOCKED':
            self.status_reason='Access lost during inventory'; return
        self.inventory=self._collect_items()
        if not self.inventory:
            self.issues.append('No content items discovered')
        ids=[x['id'] for x in self.inventory]
        if len(ids)!=len(set(ids)):
            self.issues.append('Duplicate or ambiguous item IDs')
        for item in self.inventory:
            if not item['id'] or not item['title']:
                self.issues.append(f'Unidentified item at position {item["position"]}')
            if item['visibility']=='UNKNOWN':
                self.issues.append(f'Unknown visibility: {item["title"]}')
            if item['toggle_id'] and (not item['expanded'] or not item['panel_found']):
                self.issues.append(f'Unverified folder/module contents: {item["title"]}')
        if not self.page.get_by_role('button',name='No more content items to load',exact=True).count():
            self.issues.append('End-of-content marker not observed; loading coverage unverified')
        self.status='INCOMPLETE' if self.issues else 'COLLECTED'
        self.status_reason=f'{len(self.inventory)} outline items recorded; content/media equivalence NOT TESTED'

    def save_report(self):
        self.output_dir.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path=self.output_dir / f'blackboard_inventory_{stamp}.json'
        data={'course_url':self.course_url,'status':self.status,'reason':self.status_reason,
              'generated_utc':datetime.now(timezone.utc).isoformat(),'issues':self.issues,
              'scope':'Outline inventory only; not migration completeness or media QC',
              'inventory':self.inventory}
        text=json.dumps(data,indent=2,ensure_ascii=False)
        path.write_text(text,encoding='utf-8')
        (self.output_dir/'blackboard_inventory.json').write_text(text,encoding='utf-8')
        return path

    def run_inventory(self):
        self.inventory=[]; self.issues=[]; self.status='INCOMPLETE'
        try:
            self.start_browser()
            response=self.page.goto(self.course_url,wait_until='domcontentloaded',timeout=35000)
            if not self.headless:
                print('Log in INSIDE this Edge window. Open the course outline. Never share your password.')
                answer=input('Type SCAN here after the outline is visible: ')
                if answer.strip()!='SCAN':
                    self.status_reason='Explicit SCAN confirmation not received'
                    return self.inventory,self.save_report()
                response=None
            self.inspect_outline(response)
            if not self.headless and self.status != 'BLOCKED' and self.page.locator('#course-content-outline-header-text').count():
                self.auth_file.parent.mkdir(parents=True,exist_ok=True)
                self.context.storage_state(path=str(self.auth_file))
            return self.inventory,self.save_report()
        except Exception as exc:
            self.status='INCOMPLETE'; self.status_reason=f'{type(exc).__name__}: {exc}'
            return self.inventory,self.save_report()
        finally:
            self.close()

    def close(self):
        for obj,method in ((self.context,'close'),(self.browser,'close'),(self.playwright,'stop')):
            if obj:
                try: getattr(obj,method)()
                except Exception: pass


def main():
    parser=argparse.ArgumentParser(description='Read-only Blackboard Ultra outline inventory')
    parser.add_argument('action',nargs='?',choices=['run_inventory'],default='run_inventory')
    parser.add_argument('--course-url',default=DEFAULT_URL)
    parser.add_argument('--browser',choices=['msedge','chrome','chromium'],default='msedge')
    parser.add_argument('--headless',action='store_true')
    args=parser.parse_args()
    scanner=BlackboardScanner(args.course_url,headless=args.headless,browser_channel=args.browser)
    items,path=scanner.run_inventory()
    print(f'Status: {scanner.status}\nReason: {scanner.status_reason}\nItems: {len(items)}\nReport: {path}')
    return 0 if scanner.status=='COLLECTED' else 2

if __name__=='__main__':
    raise SystemExit(main())
