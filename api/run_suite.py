#!/usr/bin/env python3
"""Run L0 / L1 / L2 Keep Desk suites and refresh compliance score."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

API = Path(__file__).parent


def run(cmd: list[str]) -> int:
    print('+', ' '.join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(API))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', choices=['L0', 'L1', 'L2', 'all'], default='L0')
    args = ap.parse_args()
    rc = 0
    py = sys.executable
    if args.level in ('L0', 'all'):
        rc |= run([py, str(API / 'validate.py')])
    if args.level in ('L1', 'all'):
        rc |= run([py, str(API / 'ci2_delegation_test.py')])
        rc |= run([py, str(API / 'ci345_tests.py')])
    if args.level in ('L2', 'all'):
        rc |= run([py, str(API / 'ci1_computer_use_test.py')])
        rc |= run([py, str(API / 'ci6_teach_by_demo_test.py')])
        if args.level == 'L2':
            rc |= run([py, str(API / 'ci2_delegation_test.py')])
            rc |= run([py, str(API / 'ci345_tests.py')])
            rc |= run([py, str(API / 'ci5_soak_test.py')])
            rc |= run([py, str(API / 'open_web_suite.py')])
            rc |= run([py, str(API / 'brow_benchmark.py')])
            rc |= run([py, str(API / 'saas_gate.py')])
            # L5-prod is opt-in (needs operator sessions); set L5_PROD=1 to include
            if __import__('os').environ.get('L5_PROD') == '1':
                rc |= run([py, str(API / 'l5_prod_gate.py')])
    rc_score = run([py, str(API / 'compliance_score.py')])
    # score may exit 1 when CRITICAL_GATE fail — still print
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
