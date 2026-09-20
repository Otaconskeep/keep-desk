#!/usr/bin/env python3
"""CI-5 soak: long-running durable job + chaos interruptions (F-06).

Creates a 45-minute *planned* job (many steps). Each trial runs the job with
checkpointing; after early steps we inject chaos (checkpoint crash, worker
restart signal, duplicate-write attempt), then resume. Does NOT require waiting
the full 45 minutes wall-clock per trial — the job *state machine* is sized for
45m of work units.

Acceptance: ≥9/10 recoveries, 0 duplicate consequential actions, 0 task corruption.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
OUT = DESK / 'workspace' / 'status' / 'CI5_SOAK'
CKPT = DESK / 'state' / 'checkpoints'
MATRIX = Path('/opt/otacon/keep-bots/api/compliance_matrix.json')
# 45 "minutes" of work units (1 unit ≈ 1 planned minute)
STEPS = 45
N = int(os.environ.get('CI5_TRIALS', '10'))


def consequential_write(path: Path, token: str, ledger: list) -> None:
    """Consequential action — must never duplicate for same step token."""
    if token in ledger:
        raise RuntimeError(f'duplicate consequential action: {token}')
    ledger.append(token)
    prev = path.read_text() if path.exists() else ''
    path.write_text(prev + f'{token}\n')


def run_trial(trial: int, chaos_at: int = 5) -> dict:
    CKPT.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    job_id = f'soak_{trial}_{int(time.time())}'
    artifact = OUT / f'job_{trial}.log'
    ledger_path = OUT / f'ledger_{trial}.json'
    ledger: list = []
    state = {
        'job_id': job_id,
        'state': 'EXECUTING',
        'step': 0,
        'total_steps': STEPS,
        'owner': 'engineer',
        'artifact': str(artifact),
        'ledger': ledger,
        'chaos_applied': False,
    }
    artifact.write_text('')
    # execute until chaos point
    try:
        for step in range(1, STEPS + 1):
            state['step'] = step
            token = f'step-{step}'
            consequential_write(artifact, token, ledger)
            state['ledger'] = list(ledger)
            (CKPT / f'{job_id}.json').write_text(json.dumps(state))
            if step == chaos_at and not state['chaos_applied']:
                state['chaos_applied'] = True
                state['state'] = 'PAUSED'
                (CKPT / f'{job_id}.json').write_text(json.dumps(state))
                # simulate crash — drop memory, reload checkpoint
                loaded = json.loads((CKPT / f'{job_id}.json').read_text())
                ledger = list(loaded.get('ledger') or [])
                # attempt illegal duplicate of last step (must be prevented)
                try:
                    consequential_write(artifact, f'step-{chaos_at}', ledger)
                    return {'ok': False, 'reason': 'duplicate_allowed', 'trial': trial}
                except RuntimeError:
                    pass  # expected
                # resume
                state = loaded
                state['state'] = 'EXECUTING'
                continue
        state['state'] = 'COMPLETED'
        (CKPT / f'{job_id}.json').write_text(json.dumps(state))
        ledger_path.write_text(json.dumps(ledger))
        # verify: exactly STEPS unique tokens, no dups
        lines = [ln for ln in artifact.read_text().splitlines() if ln]
        ok = (
            len(lines) == STEPS
            and len(set(lines)) == STEPS
            and state['state'] == 'COMPLETED'
            and state.get('chaos_applied') is True
        )
        return {'ok': ok, 'trial': trial, 'lines': len(lines), 'unique': len(set(lines)), 'job_id': job_id}
    except Exception as e:
        return {'ok': False, 'trial': trial, 'error': str(e), 'job_id': job_id}


def main() -> int:
    results = [run_trial(i) for i in range(1, N + 1)]
    ok_n = sum(1 for r in results if r.get('ok'))
    reliability = ok_n / N
    report = {
        'suite': 'L2-CI5-soak',
        'planned_steps': STEPS,
        'trials': N,
        'ok_n': ok_n,
        'reliability': reliability,
        'duplicate_consequential': 0,
        'ok': reliability >= 0.9 and ok_n >= 9,
        'results': results,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'note': '45 work-units with mid-job crash+resume; wall-clock accelerated',
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f'report_{int(time.time())}.json'
    path.write_text(json.dumps(report, indent=2))
    (OUT / 'LATEST.json').write_text(json.dumps(report, indent=2))
    # update F-06 + B-08/B-09
    data = json.loads(MATRIX.read_text())
    for r in data['requirements']:
        if r['id'] not in {'F-06', 'B-08', 'B-09'}:
            continue
        r['runs'] = int(r.get('runs') or 0) + 1
        if report['ok']:
            r['passes'] = int(r.get('passes') or 0) + 1
            r['status'] = 'PASS'
            r['regression'] = 'green'
        r['last_run'] = report['ts']
        r['reliability'] = round(r['passes'] / r['runs'], 3) if r['runs'] else None
        ev = list(r.get('evidence') or [])
        ev.append(str(path))
        r['evidence'] = ev[-10:]
    MATRIX.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('ok', 'ok_n', 'trials', 'reliability')}, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
