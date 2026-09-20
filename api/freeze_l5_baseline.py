#!/usr/bin/env python3
"""Freeze BROW-L5 PROD BASELINE — only when L5_PROD/LATEST.json gate_pass is true.

Records immutable evidence hashes + versions. Do not rewrite after freeze.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

DESK = Path('/mnt/data/keep-desk')
OUT = DESK / 'workspace' / 'status' / 'L5_PROD'
LATEST = OUT / 'LATEST.json'
BASELINE_DIR = OUT / 'BASELINES'
MATRIX = Path('/opt/otacon/keep-bots/api/compliance_matrix.json')
REGISTRY = Path('/opt/otacon/keep-bots/config/live_services.json')
SCORER = Path('/opt/otacon/keep-bots/api/compliance_score.py')
GATE = Path('/opt/otacon/keep-bots/api/l5_prod_gate.py')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    if not LATEST.exists():
        print('No L5_PROD/LATEST.json — run l5_prod_gate.py first')
        return 2
    report = json.loads(LATEST.read_text())
    if not report.get('gate_pass'):
        print('gate_pass is false — refuse to freeze baseline')
        print(json.dumps(report.get('rates') or {}, indent=2))
        return 1

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    try:
        commit = subprocess.check_output(
            ['git', '-C', '/opt/otacon/keep-bots', 'rev-parse', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        commit = 'unknown'

    rates = report.get('rates') or {}
    baseline = {
        'name': 'BROW-L5 PROD BASELINE',
        'title': 'Generalized Browser Agent — Production SaaS Worker',
        'frozen_at': ts,
        'gate_pass': True,
        'services_tested': rates.get('authed_services_n') or report.get('services_n'),
        'authed_services': rates.get('authed_services'),
        'authenticated_tasks': rates.get('authenticated_tasks_executed'),
        'authenticated_success_rate': rates.get('authenticated_task_success_rate'),
        'discovery_success_rate': rates.get('discovery_success_rate'),
        'auth_boundary_accuracy': rates.get('auth_boundary_accuracy'),
        'recovery_rate': rates.get('recovery_rate'),
        'false_completion': rates.get('false_completion'),
        'unauthorized_actions': report.get('unauthorized_actions'),
        'credential_leakage': report.get('credential_leakage'),
        'human_intervention_rate': rates.get('human_intervention_rate'),
        'unexpected_human_rescue': report.get('unexpected_human_rescue'),
        'versions': {
            'keep_bots_git': commit,
            'live_services_sha256': sha256(REGISTRY),
            'l5_prod_gate_sha256': sha256(GATE),
            'compliance_matrix_sha256': sha256(MATRIX),
            'compliance_score_sha256': sha256(SCORER),
            'evidence_report_sha256': sha256(LATEST),
        },
        'evidence_report': str(LATEST),
        'doctrine': (
            'Do not rewrite this baseline. L6 is an endurance program on top of this freeze.'
        ),
    }
    path = BASELINE_DIR / f'BROW_L5_PROD_BASELINE_{ts}.json'
    path.write_text(json.dumps(baseline, indent=2) + '\n')
    (BASELINE_DIR / 'LATEST.json').write_text(json.dumps(baseline, indent=2) + '\n')

    # Stamp matrix
    data = json.loads(MATRIX.read_text())
    data['browser_l5_prod_baseline'] = {
        'path': str(path),
        'frozen_at': ts,
        'authenticated_tasks': baseline['authenticated_tasks'],
        'success_rate': baseline['authenticated_success_rate'],
    }
    data['browser_maturity'] = {
        **(data.get('browser_maturity') or {}),
        'BROW-L5': 'PASS',
        'baseline': str(path),
        'label': 'Generalized Browser Agent — Production SaaS Worker',
    }
    MATRIX.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'frozen': True, 'path': str(path), **{k: baseline[k] for k in (
        'authenticated_tasks', 'authenticated_success_rate', 'services_tested',
    )}}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
