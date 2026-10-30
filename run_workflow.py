"""Run both LMS scanners and produce a conservative comparison report."""
import argparse
import json
import sys
from pathlib import Path
from qc_core.bb_scanner import BlackboardScanner, DEFAULT_URL
from qc_core.scanner import LMSScanner
from qc_core.comparison import compare, write_comparison
from qc_core.config import DEFAULT_COURSE_URL, REPORTS_DIR


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',choices=['msedge','chrome','chromium'],default='msedge')
    parser.add_argument('--blackboard-url',default=DEFAULT_URL)
    parser.add_argument('--canvas-url',default=DEFAULT_COURSE_URL)
    parser.add_argument('--compare-only',action='store_true',help='Compare saved JSON inventories; no browser or login')
    args=parser.parse_args()
    if not args.compare_only:
        bb=BlackboardScanner(args.blackboard_url,browser_channel=args.browser)
        bb.run_inventory()
        print(f'Blackboard: {bb.status} - {bb.status_reason}')
        if bb.status=='BLOCKED':
            print('STOP: Blackboard access must be resolved before comparison.'); return 2
        canvas=LMSScanner(args.canvas_url,browser_channel=args.browser)
        canvas.run_qc()
        print(f'Canvas QC: {canvas.status}')
    try:
        source=json.loads((REPORTS_DIR/'blackboard_inventory.json').read_text(encoding='utf-8'))
        target=json.loads((REPORTS_DIR/'canvas_inventory.json').read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        print(f'Inventories unavailable: {exc}'); return 2
    if source.get('course_url','').rstrip('/')!=args.blackboard_url.rstrip('/') or target.get('course_url','').rstrip('/')!=args.canvas_url.rstrip('/'):
        print('STOP: Saved inventories belong to different courses.'); return 2
    result=compare(source,target)
    report=write_comparison(result,REPORTS_DIR)
    print(f'Comparison: {result["status"]}\nReport: {report}')
    print('Title matches do not certify content equivalence. Review timestamps for saved inventories.')
    return 2

if __name__=='__main__':
    try: sys.exit(main())
    except KeyboardInterrupt: print('Cancelled; no LMS edits performed.'); sys.exit(130)
    except Exception as exc: print(f'Run could not complete: {type(exc).__name__}: {exc}'); sys.exit(2)
