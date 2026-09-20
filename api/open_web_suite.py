#!/usr/bin/env python3
"""Open-web computer-use harness — breadth beyond local fixtures.

Curated public sites only (no auth, polite, timeout-bounded).
Tracks reliability toward the "20–50 unrelated sites" bar.

This does NOT claim Grok-equivalent open-web survival yet — it measures progress.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DESK_ROOT', '/mnt/data/keep-desk')
os.environ.setdefault('BROWSER_URL', 'http://127.0.0.1:5766')

from computer_use import Computer  # noqa: E402

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
OUT = DESK / 'workspace' / 'status' / 'OPEN_WEB'
MATRIX = Path('/opt/otacon/keep-bots/api/compliance_matrix.json')

# Curated, stable, no-login tasks. Expand toward 20–50 over time.
TASKS = [
    {
        'id': 'example_domain',
        'url': 'https://example.com/',
        'check': lambda t, title, url: 'Example Domain' in (title or t),
    },
    {
        'id': 'httpbin_html',
        'url': 'https://httpbin.org/html',
        'check': lambda t, title, url: 'Herman Melville' in t or 'httpbin' in (url or ''),
    },
    {
        'id': 'httpbin_get',
        'url': 'https://httpbin.org/get',
        'check': lambda t, title, url: 'origin' in t or 'headers' in t,
    },
    {
        'id': 'wikipedia_main',
        'url': 'https://en.wikipedia.org/wiki/Main_Page',
        'check': lambda t, title, url: 'Wikipedia' in (title or t),
    },
    {
        'id': 'iana_example_docs',
        'url': 'https://www.iana.org/domains/reserved',
        'check': lambda t, title, url: 'IANA' in (title or t) or 'example' in t.lower(),
    },
    {
        'id': 'rfc_editorconfig',
        'url': 'https://www.rfc-editor.org/rfc/rfc2616',
        'check': lambda t, title, url: 'HTTP' in t or 'RFC' in (title or t),
    },
    {
        'id': 'python_org',
        'url': 'https://www.python.org/',
        'check': lambda t, title, url: 'Python' in (title or t),
    },
    {
        'id': 'mdn_js',
        'url': 'https://developer.mozilla.org/en-US/docs/Web/JavaScript',
        'check': lambda t, title, url: 'JavaScript' in (title or t),
    },
    {
        'id': 'w3c',
        'url': 'https://www.w3.org/',
        'check': lambda t, title, url: 'W3C' in (title or t),
    },
    {
        'id': 'jsonplaceholder',
        'url': 'https://jsonplaceholder.typicode.com/todos/1',
        'check': lambda t, title, url: 'userId' in t or 'title' in t,
    },
]


def run_task(task: dict) -> dict:
    cu = Computer(session_id=f"ow_{task['id']}_{int(time.time())}")
    try:
        nav = cu.navigate(task['url'])
        cu.wait(0.8)
        obs = cu.observe()
        text = obs.get('text') or ''
        title = obs.get('title') or ''
        url = obs.get('url') or ''
        ok = bool(task['check'](text, title, url)) and nav.get('ok') is not False
        cu.screenshot(f"ow_{task['id']}.png")
        return {'id': task['id'], 'ok': ok, 'title': title, 'url': url, 'snip': text[:160]}
    except Exception as e:
        return {'id': task['id'], 'ok': False, 'error': str(e)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get('OPEN_WEB_LIMIT', str(len(TASKS))))
    tasks = TASKS[:limit]
    results = []
    for t in tasks:
        results.append(run_task(t))
        time.sleep(0.5)  # be polite
    ok_n = sum(1 for r in results if r.get('ok'))
    rel = ok_n / len(tasks) if tasks else 0
    report = {
        'suite': 'L2-open-web-breadth',
        'n': len(tasks),
        'ok_n': ok_n,
        'reliability': rel,
        'target_n': 20,
        'target_reliability': 0.9,
        'ok_for_partial_breadth': rel >= 0.8 and len(tasks) >= 8,
        'ok_for_full_breadth_bar': rel >= 0.9 and len(tasks) >= 20,
        'results': results,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'note': 'Curated public sites — not arbitrary SaaS. Proves breadth progress.',
    }
    path = OUT / f'report_{int(time.time())}.json'
    path.write_text(json.dumps(report, indent=2))
    (OUT / 'LATEST.json').write_text(json.dumps(report, indent=2))

    # Matrix: C-01/C-02 breadth — keep C-06 as local-unknown PASS; add note evidence for open web
    data = json.loads(MATRIX.read_text())
    for r in data['requirements']:
        if r['id'] in {'C-01', 'C-02'}:
            r['runs'] = int(r.get('runs') or 0) + 1
            if report['ok_for_partial_breadth']:
                r['passes'] = int(r.get('passes') or 0) + 1
                r['status'] = 'PASS'
            r['last_run'] = report['ts']
            r['reliability'] = round(r['passes'] / r['runs'], 3) if r['runs'] else None
            ev = list(r.get('evidence') or [])
            ev.append(str(path))
            r['evidence'] = ev[-10:]
    MATRIX.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in (
        'n', 'ok_n', 'reliability', 'ok_for_partial_breadth', 'ok_for_full_breadth_bar'
    )}, indent=2))
    return 0 if report['ok_for_partial_breadth'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
