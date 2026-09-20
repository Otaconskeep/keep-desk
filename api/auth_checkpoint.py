"""Auth checkpoint protocol for browser agent (BROW-L5).

Rules:
  - Detect LOGIN_REQUIRED / SESSION_EXPIRED / MFA_REQUIRED markers
  - Never invent credentials or MFA codes
  - Never claim task completion while auth/MFA pending
  - Persist checkpoint so work can resume after human takeover
  - Human simulator (tests only) can complete MFA with known fixture code
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk')).resolve()
CKPT_DIR = DESK / 'state' / 'browser_auth_checkpoints'
PENDING = DESK / 'state' / 'browser_auth_pending.json'
AUDIT = DESK / 'state' / 'browser_auth_audit.jsonl'
CKPT_DIR.mkdir(parents=True, exist_ok=True)
PENDING.parent.mkdir(parents=True, exist_ok=True)

MARKERS = {
    'login': ('LOGIN_REQUIRED_MARKER', 'SESSION_EXPIRED_MARKER', 'please sign in'),
    'mfa': ('MFA_REQUIRED_MARKER', 'Multi-factor', 'human takeover required'),
    'expired': ('SESSION_EXPIRED_MARKER',),
}


def _audit(event: dict) -> None:
    event = {'ts': time.time(), **event}
    with AUDIT.open('a') as f:
        f.write(json.dumps(event) + '\n')


def detect_auth_boundary(obs: dict) -> str | None:
    """Return 'mfa' | 'login' | 'expired' | None from page observation."""
    text = ((obs.get('text') or '') + ' ' + (obs.get('title') or '')).lower()
    url = (obs.get('url') or '').lower()
    for m in MARKERS['mfa']:
        if m.lower() in text:
            return 'mfa'
    for m in MARKERS['expired']:
        if m.lower() in text:
            return 'expired'
    for m in MARKERS['login']:
        if m.lower() in text:
            return 'login'
    if '#/login' in url or '/login' in url:
        # only if we also see a sign-in affordance
        if 'sign in' in text or 'password' in text or 'login' in text:
            return 'login'
    if '#/mfa' in url:
        return 'mfa'
    return None


def load_pending() -> dict:
    if PENDING.exists():
        try:
            return json.loads(PENDING.read_text())
        except Exception:
            pass
    return {'pending': []}


def save_pending(data: dict) -> None:
    PENDING.write_text(json.dumps(data, indent=2))


def request_human_auth(
    *,
    kind: str,
    task_id: str,
    checkpoint: dict,
    reason: str,
) -> dict:
    """Pause for human. Does NOT complete the task."""
    req = {
        'id': f'bauth_{uuid.uuid4().hex[:10]}',
        'kind': kind,  # login | mfa | expired
        'task_id': task_id,
        'reason': reason,
        'status': 'waiting_human',
        'created_at': time.time(),
        'checkpoint_path': None,
        'credentials_present': False,  # invariant: we never store secrets here
    }
    path = CKPT_DIR / f"{task_id}_{req['id']}.json"
    payload = {
        'task_id': task_id,
        'auth_request_id': req['id'],
        'kind': kind,
        'checkpoint': checkpoint,
        'created_at': time.time(),
    }
    path.write_text(json.dumps(payload, indent=2))
    req['checkpoint_path'] = str(path)

    data = load_pending()
    data.setdefault('pending', []).append(req)
    save_pending(data)
    _audit({'event': 'human_auth_requested', **{k: req[k] for k in (
        'id', 'kind', 'task_id', 'reason', 'status')}})
    return req


def resolve_human_auth(auth_id: str, *, completed: bool, note: str = '') -> dict:
    data = load_pending()
    found = None
    for p in data.get('pending') or []:
        if p.get('id') == auth_id:
            found = p
            p['status'] = 'completed' if completed else 'cancelled'
            p['resolved_at'] = time.time()
            p['note'] = note
            break
    save_pending(data)
    _audit({'event': 'human_auth_resolved', 'id': auth_id, 'completed': completed, 'note': note})
    return found or {'id': auth_id, 'error': 'not_found'}


def claim_completion_allowed(obs: dict, goal_ok: bool) -> tuple[bool, str]:
    """False completion ban: never claim done while auth pending or goal unmet."""
    boundary = detect_auth_boundary(obs)
    if boundary:
        return False, f'auth_boundary_active:{boundary}'
    if not goal_ok:
        return False, 'goal_unmet'
    return True, 'ok'


def human_simulator_complete_mfa(cu, code: str = '246810') -> dict:
    """TEST-ONLY: act as human after bot paused. Never used for real SaaS."""
    from computer_use import Computer  # noqa: F401
    r1 = cu.type('#mfa', code)
    r2 = cu.click('#btn-mfa')
    cu.wait(0.4)
    _audit({'event': 'human_simulator_mfa', 'ok': True})
    return {'ok': True, 'type': r1, 'click': r2}


def human_simulator_login(cu, user: str = 'agent', password: str = 'local-only') -> dict:
    """TEST-ONLY fixture login as human takeover stand-in."""
    cu.type('#user', user)
    cu.type('#pass', password)
    cu.click('#btn-login')
    cu.wait(0.4)
    _audit({'event': 'human_simulator_login', 'user': user, 'password_logged': False})
    return {'ok': True}
