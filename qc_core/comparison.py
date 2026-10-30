"""Conservative inventory comparison. Title matches never prove content identity."""
import html
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def normalize(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',value or '')).strip().casefold()


def compare(source, target):
    rows=[]
    blocked=source.get('status')=='BLOCKED' or target.get('status')=='BLOCKED'
    trusted_source=source.get('status')=='COLLECTED'
    # OBSERVED is deliberately not proof that every target item was collected.
    trusted_target=target.get('status')=='COLLECTED'
    candidates=defaultdict(list)
    for item in target.get('inventory',[]):
        candidates[normalize(item.get('title'))].append(item)
    source_counts=defaultdict(int)
    for item in source.get('inventory',[]): source_counts[normalize(item.get('title'))]+=1
    for item in source.get('inventory',[]):
        title=normalize(item.get('title'))
        found=candidates.get(title,[]) if title else []
        if blocked:
            state,reason='NOT TESTED','One LMS inventory was blocked'
        elif len(found)==1 and source_counts[title]==1:
            state,reason='MATCHED_TITLE','Unique exact normalized title; content, type, hierarchy and visibility equivalence not verified'
        elif found:
            state,reason='NEEDS REVIEW','Duplicate or ambiguous title; manual mapping needed'
        else:
            state='POSSIBLY MISSING' if trusted_source and trusted_target else 'NOT TESTED'
            reason='No title match; missing content is not confirmed when inventory coverage is unverified'
        rows.append({'source':item,'candidates':found,'status':state,'reason':reason})
    status='BLOCKED' if blocked else 'INCOMPLETE' if not trusted_source or not trusted_target or not rows else 'NEEDS REVIEW'
    return {'status':status,'generated_utc':datetime.now(timezone.utc).isoformat(),
            'source_url':source.get('course_url'),'target_url':target.get('course_url'),
            'limitations':['Title comparison only; no guarantee of migration completeness.',
                           'Canvas Modules inventory excludes content outside Modules.',
                           'No media playback, academic accuracy, student-access or AI visual certification.',
                           'No automatic edits or fixes are performed.'], 'rows':rows}


def write_comparison(result, output_dir):
    output_dir=Path(output_dir); output_dir.mkdir(parents=True,exist_ok=True)
    path=output_dir/'comparison_report.html'
    escape=lambda s:html.escape(str(s or ''))
    body=''.join('<tr><td>'+escape(x['source'].get('title'))+'</td><td>'+escape(x['status'])+'</td><td>'+
                 escape(', '.join(c.get('module_name','') for c in x['candidates']))+'</td><td>'+escape(x['reason'])+'</td></tr>' for x in result['rows'])
    page='<!doctype html><meta charset="utf-8"><title>LMS inventory comparison</title><style>body{font:16px system-ui;margin:32px}td,th{padding:12px;border:1px solid #aaa;text-align:left}table{border-collapse:collapse}</style>'
    page+='<h1>Comparison: '+escape(result['status'])+'</h1><p>'+escape(result['source_url'])+' → '+escape(result['target_url'])+'</p>'
    page+='<ul>'+''.join('<li>'+escape(x)+'</li>' for x in result['limitations'])+'</ul>'
    page+='<table><tr><th>Blackboard item</th><th>Result</th><th>Canvas module</th><th>Reason</th></tr>'+body+'</table>'
    path.write_text(page,encoding='utf-8')
    (output_dir/'comparison_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return path
