#!/usr/bin/env python3
"""CI-6: Teach-by-demonstration black-box test (C-10).

1) Simulate human demo on Intake Desk Beta (type name=Bob, code=1234, submit)
2) Generalize → Skill (Bob/1234 become inputs, NOT literals)
3) Replay with name=Alice, code=7777 in fresh session
4) Verify confirmation uses Alice/7777 and Skill does not hardcode Bob
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

from teach_by_demo import (  # noqa: E402
    RecordingComputer, generalize_recording, publish_skill, replay_skill,
)

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
OUT = DESK / 'workspace' / 'status' / 'CI6_TEACH_BY_DEMO'
MATRIX = Path('/opt/otacon/keep-bots/api/compliance_matrix.json')
FIXTURE = os.environ.get('FIXTURE_BROWSER_BASE', 'http://host.docker.internal:5767')


def human_demo() -> Path:
    rc = RecordingComputer(meta={
        'name': 'intake_form_submit',
        'description': 'Fill intake form and read confirmation',
        'validation': ['contains:CONFIRMATION'],
        'expected_outputs': ['confirmation_text'],
    })
    rc.navigate(f'{FIXTURE}/webapp_b/index.html')
    rc.wait(0.3)
    rc.type('#name', 'Bob')
    rc.type('#code', '1234')
    rc.click('#submit')
    rc.wait(0.3)
    rc.screenshot('demo_intake.png')
    return rc.finish()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    demo_path = human_demo()
    rec = json.loads(demo_path.read_text())
    skill = generalize_recording(rec)

    # Must have generalized Bob and 1234
    examples = skill.get('must_not_hardcode_examples') or []
    gen_ok = 'Bob' in examples and '1234' in examples
    steps_blob = json.dumps(skill.get('steps'))
    no_literal_bob = '"Bob"' not in steps_blob and "'Bob'" not in steps_blob
    # placeholders present
    has_placeholders = '{{' in steps_blob and '}}' in steps_blob

    published = publish_skill(skill)
    replay = replay_skill(skill, {'name': 'Alice', 'code': '7777'})
    text = replay.get('final_text') or ''
    replay_ok = replay.get('ok') and 'CONFIRMATION: BETA-OK-Alice-7777' in text
    no_bob_in_result = 'Bob' not in text and '1234' not in text

    report = {
        'suite': 'L2-CI6-teach-by-demo',
        'demo_path': str(demo_path),
        'skill_id': published['skill_id'],
        'skill_path': published['path'],
        'generalized_ok': gen_ok and has_placeholders and no_literal_bob,
        'inputs': list(skill.get('required_inputs') or []),
        'input_schema': skill.get('input_schema'),
        'replay_ok': bool(replay_ok),
        'no_bob_leak': no_bob_in_result,
        'replay_text_snip': text[:300],
        'ok': bool(gen_ok and has_placeholders and no_literal_bob and replay_ok and no_bob_in_result),
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    path = OUT / f'report_{int(time.time())}.json'
    path.write_text(json.dumps(report, indent=2))
    (OUT / 'LATEST.json').write_text(json.dumps(report, indent=2))

    # Update C-10 (+ E-01/E-08 partial chain)
    data = json.loads(MATRIX.read_text())
    now = report['ts']
    for r in data['requirements']:
        if r['id'] not in {'C-10', 'E-08', 'E-01'}:
            continue
        r['runs'] = int(r.get('runs') or 0) + 1
        if report['ok']:
            r['passes'] = int(r.get('passes') or 0) + 1
            if r['id'] == 'C-10':
                r['status'] = 'PASS'
            elif r['id'] == 'E-08':
                # demo→skill→replay is part of the loop; scheduling still separate
                r['status'] = 'PARTIAL'
            elif r['id'] == 'E-01':
                r['status'] = 'PASS'
            r['regression'] = 'green' if r['status'] == 'PASS' else 'amber'
        else:
            if r['id'] == 'C-10':
                r['status'] = 'FAIL'
            r['regression'] = 'red'
        r['last_run'] = now
        r['reliability'] = round(r['passes'] / r['runs'], 3) if r['runs'] else None
        ev = list(r.get('evidence') or [])
        ev.append(str(path))
        r['evidence'] = ev[-10:]
    MATRIX.write_text(json.dumps(data, indent=2) + '\n')

    print(json.dumps({k: report[k] for k in (
        'ok', 'generalized_ok', 'replay_ok', 'no_bob_leak', 'inputs', 'skill_id'
    )}, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
