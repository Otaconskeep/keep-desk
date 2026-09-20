#!/usr/bin/env python3
"""Gate D — L5-04 live login/MFA takeover + resume.

Distinct from session_persist (inherit). Forces logout → auth wall → human
re-seed (VNC / Gate A chromium) → HUMAN_DONE → browser restart_context → resume.

Usage:
  # Terminal 1 — start VNC seed UI for the target service:
  GATE_A_SERVICES=nextcloud python3 /opt/otacon/keep-bots/api/gate_a_human_seed.py

  # Terminal 2 — run takeover (waits for human):
  L5_HUMAN_AVAILABLE=1 L5_HUMAN_WAIT_SEC=1800 \\
    L5_ONLY_CLASSES=mfa_takeover L5_ONLY_IDS=takeover_nextcloud L5_MERGE_PREV=1 \\
    python3 /opt/otacon/keep-bots/api/l5_prod_gate.py

  # After re-login in noVNC http://192.168.50.219:6080/vnc.html :
  #   (Gate A export happens on HUMAN_DONE)
  touch /mnt/data/keep-desk/workspace/status/L5_PROD/HUMAN_DONE

Or run this orchestrator (starts takeover wait; you still do VNC login):
  python3 /opt/otacon/keep-bots/api/gate_d_takeover.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVICE = os.environ.get('GATE_D_SERVICE', 'nextcloud')
ROOT = Path('/opt/otacon/keep-bots')


def main() -> int:
    env = os.environ.copy()
    env['L5_HUMAN_AVAILABLE'] = '1'
    env.setdefault('L5_HUMAN_WAIT_SEC', '1800')
    env['L5_ONLY_CLASSES'] = 'mfa_takeover'
    env['L5_ONLY_IDS'] = f'takeover_{SERVICE}'
    env['L5_MERGE_PREV'] = '1'
    print(
        f'Gate D: takeover_{SERVICE}\n'
        f'1) In another terminal: GATE_A_SERVICES={SERVICE} '
        f'python3 {ROOT}/api/gate_a_human_seed.py\n'
        f'2) noVNC http://192.168.50.219:6080/vnc.html — re-login after bot logout\n'
        f'3) touch /mnt/data/keep-desk/workspace/status/L5_PROD/HUMAN_DONE\n',
        flush=True,
    )
    return subprocess.call(
        [sys.executable, str(ROOT / 'api' / 'l5_prod_gate.py')],
        env=env,
    )


if __name__ == '__main__':
    raise SystemExit(main())
