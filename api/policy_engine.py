"""Policy engine — enforcement OUTSIDE the LLM.

LEVEL 0 read-only → AUTO_ALLOW
LEVEL 1 reversible local → ALLOW_WITH_AUDIT
LEVEL 2 external communication → REQUIRE_APPROVAL
LEVEL 3 production modification → REQUIRE_APPROVAL
LEVEL 4 destructive/financial/credential → DENY or REQUIRE_APPROVAL
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

DESK = Path(os.environ.get('DESK_ROOT', '/desk'))
AUDIT = DESK / 'state' / 'policy_audit.jsonl'
PENDING = DESK / 'state' / 'policy_pending.json'

LEVEL = {
    'read': 0,
    'desk_read': 0,
    'desk_list': 0,
    'observe': 0,
    'browser_content': 0,
    'memory_read': 0,
    'desk_write': 1,
    'shell_safe': 1,
    'browser_navigate': 1,
    'browser_click': 1,
    'browser_type': 1,
    'http_fetch': 1,
    'download': 1,
    'external_post': 2,
    'email_send': 2,
    'production_write': 3,
    'deploy': 3,
    'desk_delete': 4,
    'shell_destructive': 4,
    'credential_access': 4,
}

DESTRUCTIVE_RE = re.compile(
    r'\b(rm\s+-rf|mkfs|dd\s+if=|shutdown|reboot|drop\s+table|production)\b', re.I
)


def classify(action: str, detail: str = '') -> int:
    if action in LEVEL:
        return LEVEL[action]
    if DESTRUCTIVE_RE.search(detail or '') or DESTRUCTIVE_RE.search(action or ''):
        return 4
    if 'production' in (detail or '').lower():
        return 3
    return 1


def decide(action: str, detail: str = '') -> dict:
    level = classify(action, detail)
    if level <= 0:
        decision = 'AUTO_ALLOW'
    elif level == 1:
        decision = 'ALLOW_WITH_AUDIT'
    elif level in (2, 3):
        decision = 'REQUIRE_APPROVAL'
    else:
        decision = 'REQUIRE_APPROVAL'  # level 4 still approval (or DENY via deny list)
        if re.search(r'\b(mkfs|drop\s+table)\b', detail or '', re.I):
            decision = 'DENY'
    rec = {
        'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'action': action,
        'detail': detail[:500],
        'level': level,
        'decision': decision,
    }
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open('a') as f:
        f.write(json.dumps(rec) + '\n')
    if decision == 'REQUIRE_APPROVAL':
        pending = {'pending': []}
        if PENDING.exists():
            pending = json.loads(PENDING.read_text())
        pending['pending'].append({**rec, 'id': f'pol_{int(datetime.now().timestamp())}_{len(pending["pending"])}'})
        PENDING.write_text(json.dumps(pending, indent=2))
        rec['approval_id'] = pending['pending'][-1]['id']
    return rec


def resolve(approval_id: str, *, approve: bool) -> dict:
    if not PENDING.exists():
        return {'error': 'no pending'}
    data = json.loads(PENDING.read_text())
    item = None
    rest = []
    for p in data.get('pending') or []:
        if p.get('id') == approval_id:
            item = p
        else:
            rest.append(p)
    if not item:
        return {'error': 'not found'}
    data['pending'] = rest
    PENDING.write_text(json.dumps(data, indent=2))
    outcome = {
        'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'approval_id': approval_id,
        'approved': approve,
        'action': item.get('action'),
        'executed': bool(approve),
        'detail': item.get('detail'),
    }
    with AUDIT.open('a') as f:
        f.write(json.dumps({'type': 'resolve', **outcome}) + '\n')
    return outcome
