"""Structured multi-agent task protocol (not chat-only handoffs)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

DESK = Path(os.environ.get('DESK_ROOT', '/desk'))
TASKS = DESK / 'state' / 'tasks.json'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _load() -> dict:
    TASKS.parent.mkdir(parents=True, exist_ok=True)
    if not TASKS.exists():
        TASKS.write_text(json.dumps({'tasks': []}, indent=2))
    return json.loads(TASKS.read_text())


def _save(data: dict) -> None:
    tmp = TASKS.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(TASKS)


def create_task(*, owner: str, assigned_to: str, objective: str,
                required_output: list | None = None,
                acceptance_criteria: list | None = None,
                constraints: list | None = None,
                parent_task: str | None = None,
                context: dict | None = None) -> dict:
    t = {
        'task_id': f'T-{uuid.uuid4().hex[:8]}',
        'parent_task': parent_task,
        'owner': owner,
        'assigned_to': assigned_to,
        'objective': objective,
        'constraints': constraints or [],
        'required_output': required_output or [],
        'acceptance_criteria': acceptance_criteria or [],
        'status': 'assigned',
        'context': context or {},
        'evidence': [],
        'handoff_to': None,
        'created_at': _now(),
        'updated_at': _now(),
        'result': None,
        'rejection_reason': None,
    }
    data = _load()
    data['tasks'].insert(0, t)
    _save(data)
    return t


def patch_task(task_id: str, **fields) -> dict | None:
    data = _load()
    for i, t in enumerate(data['tasks']):
        if t['task_id'] == task_id:
            t.update(fields)
            t['updated_at'] = _now()
            data['tasks'][i] = t
            _save(data)
            return t
    return None


def add_evidence(task_id: str, item: dict) -> None:
    t = get_task(task_id)
    if not t:
        return
    ev = list(t.get('evidence') or [])
    ev.append({**item, 'at': _now()})
    patch_task(task_id, evidence=ev)


def get_task(task_id: str) -> dict | None:
    for t in _load()['tasks']:
        if t['task_id'] == task_id:
            return t
    return None


def list_tasks() -> list[dict]:
    return list(_load().get('tasks') or [])
