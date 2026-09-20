#!/usr/bin/env python3
"""Authoritative Grok Bot compliance scorer (Sprint 0).

Outputs:
  RAW_SCORE       — unweighted among rows that are not NOT_TESTED
  WEIGHTED_SCORE  — Σ(criticality_weight × status_credit) / Σ(criticality_weight)
  CRITICAL_GATE   — PASS iff all critical_gate_ids are PASS
  CLAIMABLE_SCORE — WEIGHTED_SCORE if CRITICAL_GATE else blocked

Doctrine: /opt/otacon/keep-bots/DOCTRINE.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MATRIX = Path(__file__).with_name('compliance_matrix.json')
CREDIT = {'PASS': 1.0, 'PARTIAL': 0.5, 'FAIL': 0.0, 'NOT_TESTED': 0.0}
CRIT_W = {'Mission Critical': 5, 'High': 3, 'Medium': 2, 'Low': 1}


def score(data: dict) -> dict:
    reqs = [r for r in data['requirements'] if not r.get('deferred') and r.get('scored') is not False]
    gate_ids = set((data.get('scoring') or {}).get('critical_gate_ids') or [
        'C-06', 'C-07', 'C-08', 'D-05', 'E-02', 'F-02', 'F-03', 'F-06',
    ])
    counts = Counter(r['status'] for r in data['requirements'])

    # RAW among tested
    tested = [r for r in reqs if r['status'] != 'NOT_TESTED']
    raw = (100.0 * sum(1 for r in tested if r['status'] == 'PASS') / len(tested)) if tested else 0.0

    earned = 0.0
    total = 0.0
    by_group: dict[str, dict] = {}
    mc_fail = []
    mc_untested = []

    for r in reqs:
        if r.get('deferred') or r.get('scored') is False:
            continue
        crit = r.get('criticality') or 'Medium'
        w = float(r.get('weight') or CRIT_W.get(crit, 2))
        total += w
        earned += CREDIT.get(r['status'], 0.0) * w
        g = r.get('group') or 'other'
        by_group.setdefault(g, {'earned': 0.0, 'total': 0.0, 'n': 0})
        by_group[g]['earned'] += CREDIT.get(r['status'], 0.0) * w
        by_group[g]['total'] += w
        by_group[g]['n'] += 1
        if crit == 'Mission Critical':
            if r['status'] == 'FAIL':
                mc_fail.append(r['id'])
            if r['status'] == 'NOT_TESTED':
                mc_untested.append(r['id'])

    weighted = 100.0 * earned / total if total else 0.0

    gate_rows = [r for r in reqs if r['id'] in gate_ids]
    gate_open = [r['id'] for r in gate_rows if r['status'] != 'PASS']
    critical_gate = 'PASS' if not gate_open else 'FAIL'

    claimable = round(weighted, 1) if critical_gate == 'PASS' else None
    release_85 = bool(
        critical_gate == 'PASS'
        and weighted >= 85.0
        and not mc_fail
        and not mc_untested
    )

    return {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'RAW_SCORE': round(raw, 1),
        'WEIGHTED_SCORE': round(weighted, 1),
        'CRITICAL_GATE': critical_gate,
        'CLAIMABLE_SCORE': claimable,
        'CLAIMABLE_BLOCKED_REASON': None if claimable is not None else f'critical not PASS: {gate_open}',
        'RELEASE_85_GATE': release_85,
        'earned': round(earned, 2),
        'total': round(total, 2),
        'counts': dict(counts),
        'requirement_count': len(reqs),
        'mission_critical_fail': mc_fail,
        'mission_critical_not_tested': mc_untested,
        'critical_gate_ids': sorted(gate_ids),
        'critical_gap_ids_not_pass': gate_open,
        'by_group': {
            g: {
                'pct': round(100 * v['earned'] / v['total'], 1) if v['total'] else 0,
                'n': v['n'],
            }
            for g, v in sorted(by_group.items())
        },
        'doctrine': 'IMPLEMENTED≠PASS; CLAIMABLE requires CRITICAL_GATE',
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    data = json.loads(MATRIX.read_text())
    out = score(data)
    for p in (
        Path('/mnt/data/keep-desk/workspace/status/COMPLIANCE_SCORE.json'),
        Path('/desk/workspace/status/COMPLIANCE_SCORE.json'),
    ):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, indent=2) + '\n')
        except Exception:
            pass
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print('Keep Desk Compliance Score (authoritative)')
        print(f"  RAW_SCORE:       {out['RAW_SCORE']}%")
        print(f"  WEIGHTED_SCORE:  {out['WEIGHTED_SCORE']}%  ({out['earned']}/{out['total']})")
        print(f"  CRITICAL_GATE:   {out['CRITICAL_GATE']}")
        print(f"  CLAIMABLE_SCORE: {out['CLAIMABLE_SCORE'] if out['CLAIMABLE_SCORE'] is not None else 'BLOCKED — ' + out['CLAIMABLE_BLOCKED_REASON']}")
        print(f"  RELEASE_85_GATE: {out['RELEASE_85_GATE']}")
        print(f"  Counts: {out['counts']}")
        print(f"  Critical gaps: {', '.join(out['critical_gap_ids_not_pass']) or '(none)'}")
        print(f"  MC FAIL: {out['mission_critical_fail'] or '(none)'}")
        print(f"  MC NOT_TESTED: {out['mission_critical_not_tested'] or '(none)'}")
        for g, v in out['by_group'].items():
            print(f"    {g:20s} {v['pct']:5.1f}%  n={v['n']}")
    return 0 if out['CRITICAL_GATE'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
