#!/usr/bin/env python3
"""Deprecated wrapper — use gate_a_human_seed.py (human VNC; bot never sees secrets)."""
from __future__ import annotations

import os
import runpy
import sys

print('Redirecting to gate_a_human_seed.py (preferred human session path).')
print('Password JSON seeding is opt-in only via L5_ALLOW_PASSWORD_SEED=1 on l5_prod_gate.')
sys.argv[0] = '/opt/otacon/keep-bots/api/gate_a_human_seed.py'
runpy.run_path('/opt/otacon/keep-bots/api/gate_a_human_seed.py', run_name='__main__')
