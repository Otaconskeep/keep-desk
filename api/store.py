"""JSON file store for Keep Bots (bots, jobs, handoffs, routines, approvals)."""
from __future__ import annotations

import fcntl
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _atomic_write(path: Path, data: Any) -> None:
    """Process-safe atomic write (api + worker share state on disk)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + '.lock')
    tmp = path.with_suffix(path.suffix + f'.tmp.{os.getpid()}')
    payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    with open(lock_path, 'a+', encoding='utf-8') as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            tmp.write_text(payload)
            os.replace(tmp, path)
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass


class Store:
    def __init__(self, state_dir: str):
        self.root = Path(state_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.bots_path = self.root / 'bots.json'
        self.jobs_path = self.root / 'jobs.json'
        self.handoffs_path = self.root / 'handoffs.json'
        self.routines_path = self.root / 'routines.json'
        self.approvals_path = self.root / 'approvals.json'
        self.skills_path = self.root / 'skills.json'
        self.threads_path = self.root / 'threads.json'
        self._ensure()

    def _ensure(self) -> None:
        for path, default in (
            (self.bots_path, {'bots': []}),
            (self.jobs_path, {'jobs': []}),
            (self.handoffs_path, {'handoffs': []}),
            (self.routines_path, {'routines': []}),
            (self.approvals_path, {'approvals': []}),
            (self.skills_path, {'skills': []}),
            (self.threads_path, {'threads': []}),
        ):
            if not path.exists():
                _atomic_write(path, default)

    def _load(self, path: Path) -> dict:
        with _LOCK:
            return json.loads(path.read_text())

    def _save(self, path: Path, data: dict) -> None:
        with _LOCK:
            _atomic_write(path, data)

    # ── bots ──────────────────────────────────────────────────────────
    def list_bots(self) -> list[dict]:
        return list(self._load(self.bots_path).get('bots') or [])

    def get_bot(self, bot_id: str) -> dict | None:
        for b in self.list_bots():
            if b.get('id') == bot_id:
                return b
        return None

    def upsert_bot(self, bot: dict) -> dict:
        data = self._load(self.bots_path)
        bots = data.setdefault('bots', [])
        for i, b in enumerate(bots):
            if b.get('id') == bot['id']:
                bots[i] = {**b, **bot, 'updated_at': _now()}
                self._save(self.bots_path, data)
                return bots[i]
        bot = {**bot, 'created_at': _now(), 'updated_at': _now()}
        bots.append(bot)
        self._save(self.bots_path, data)
        return bot

    def bot_routine_count(self, bot_id: str) -> int:
        return sum(1 for r in self.list_routines() if r.get('bot_id') == bot_id and r.get('enabled', True))

    # ── jobs ──────────────────────────────────────────────────────────
    def list_jobs(self, *, bot_id: str | None = None, status: str | None = None) -> list[dict]:
        jobs = list(self._load(self.jobs_path).get('jobs') or [])
        if bot_id:
            jobs = [j for j in jobs if j.get('bot_id') == bot_id]
        if status:
            jobs = [j for j in jobs if j.get('status') == status]
        return jobs

    def get_job(self, job_id: str) -> dict | None:
        for j in self.list_jobs():
            if j.get('id') == job_id:
                return j
        return None

    def create_job(self, *, bot_id: str, title: str, brief: str,
                   priority: str = 'normal', created_by: str = 'operator',
                   thread_id: str | None = None) -> dict:
        job = {
            'id': f'job_{uuid.uuid4().hex[:10]}',
            'bot_id': bot_id,
            'title': title.strip(),
            'brief': brief.strip(),
            'status': 'queued',
            'priority': priority,
            'created_by': created_by,
            'thread_id': thread_id or f'thread_{uuid.uuid4().hex[:8]}',
            'created_at': _now(),
            'updated_at': _now(),
            'started_at': None,
            'finished_at': None,
            'result_summary': None,
            'log': [],
            'pending_approval_id': None,
            'tool_trace': [],
        }
        data = self._load(self.jobs_path)
        data.setdefault('jobs', []).insert(0, job)
        self._save(self.jobs_path, data)
        return job

    def patch_job(self, job_id: str, fields: dict) -> dict | None:
        data = self._load(self.jobs_path)
        for i, j in enumerate(data.get('jobs') or []):
            if j.get('id') == job_id:
                j.update(fields)
                j['updated_at'] = _now()
                data['jobs'][i] = j
                self._save(self.jobs_path, data)
                return j
        return None

    def append_job_log(self, job_id: str, line: str) -> None:
        job = self.get_job(job_id)
        if not job:
            return
        log = list(job.get('log') or [])
        log.append({'at': _now(), 'line': line})
        self.patch_job(job_id, {'log': log[-200:]})

    def claim_next_job(self) -> dict | None:
        """Atomically claim oldest queued job (skip waiting pipeline stages / approvals)."""
        with _LOCK:
            data = json.loads(self.jobs_path.read_text())
            jobs = data.get('jobs') or []
            # process oldest first among queued (never claim pipeline 'waiting')
            candidates = [
                j for j in jobs
                if j.get('status') == 'queued'
            ]
            candidates.sort(key=lambda j: j.get('created_at') or '')
            if not candidates:
                return None
            job = candidates[0]
            for i, j in enumerate(jobs):
                if j.get('id') == job['id']:
                    jobs[i]['status'] = 'running'
                    jobs[i]['started_at'] = _now()
                    jobs[i]['updated_at'] = _now()
                    job = jobs[i]
                    break
            _atomic_write(self.jobs_path, data)
            return job

    # ── handoffs ──────────────────────────────────────────────────────
    def list_handoffs(self, *, to_bot: str | None = None) -> list[dict]:
        items = list(self._load(self.handoffs_path).get('handoffs') or [])
        if to_bot:
            items = [h for h in items if h.get('to_bot') == to_bot]
        return items

    def create_handoff(self, *, from_bot: str, to_bot: str, job_id: str,
                       message: str, context: dict | None = None) -> dict:
        item = {
            'id': f'ho_{uuid.uuid4().hex[:10]}',
            'from_bot': from_bot,
            'to_bot': to_bot,
            'job_id': job_id,
            'message': message.strip(),
            'context': context or {},
            'status': 'pending',
            'created_at': _now(),
        }
        data = self._load(self.handoffs_path)
        data.setdefault('handoffs', []).insert(0, item)
        self._save(self.handoffs_path, data)
        return item

    # ── routines ──────────────────────────────────────────────────────
    def list_routines(self) -> list[dict]:
        return list(self._load(self.routines_path).get('routines') or [])

    def create_routine(self, *, bot_id: str, name: str, cron: str,
                       brief: str, skill_id: str | None = None) -> dict:
        if self.bot_routine_count(bot_id) >= 50:
            raise ValueError('bot already owns 50 routines (Grok Bot parity cap)')
        item = {
            'id': f'rt_{uuid.uuid4().hex[:10]}',
            'bot_id': bot_id,
            'name': name.strip(),
            'cron': cron.strip(),
            'brief': brief.strip(),
            'skill_id': skill_id,
            'enabled': True,
            'created_at': _now(),
            'last_run_at': None,
        }
        data = self._load(self.routines_path)
        data.setdefault('routines', []).append(item)
        self._save(self.routines_path, data)
        return item

    # ── approvals ─────────────────────────────────────────────────────
    def list_approvals(self, *, status: str | None = None) -> list[dict]:
        items = list(self._load(self.approvals_path).get('approvals') or [])
        if status:
            items = [a for a in items if a.get('status') == status]
        return items

    def create_approval(self, *, job_id: str, bot_id: str, action: str,
                        detail: str, risk: str = 'high') -> dict:
        item = {
            'id': f'ap_{uuid.uuid4().hex[:10]}',
            'job_id': job_id,
            'bot_id': bot_id,
            'action': action,
            'detail': detail,
            'risk': risk,
            'status': 'pending',
            'created_at': _now(),
            'resolved_at': None,
            'resolved_by': None,
        }
        data = self._load(self.approvals_path)
        data.setdefault('approvals', []).insert(0, item)
        self._save(self.approvals_path, data)
        self.patch_job(job_id, {
            'status': 'pending_approval',
            'pending_approval_id': item['id'],
        })
        return item

    def resolve_approval(self, approval_id: str, *, approve: bool,
                         resolved_by: str = 'operator') -> dict | None:
        data = self._load(self.approvals_path)
        item = None
        for i, a in enumerate(data.get('approvals') or []):
            if a.get('id') == approval_id:
                a['status'] = 'approved' if approve else 'rejected'
                a['resolved_at'] = _now()
                a['resolved_by'] = resolved_by
                data['approvals'][i] = a
                item = a
                break
        if not item:
            return None
        self._save(self.approvals_path, data)
        job_id = item['job_id']
        if approve:
            self.patch_job(job_id, {
                'status': 'queued',
                'pending_approval_id': None,
            })
            self.append_job_log(job_id, f'approval {approval_id} granted — re-queued')
        else:
            self.patch_job(job_id, {
                'status': 'rejected',
                'finished_at': _now(),
                'result_summary': f'Rejected at approval {approval_id}',
                'pending_approval_id': None,
            })
        return item

    # ── skills ────────────────────────────────────────────────────────
    def list_skills(self) -> list[dict]:
        return list(self._load(self.skills_path).get('skills') or [])

    def get_skill(self, skill_id: str) -> dict | None:
        for s in self.list_skills():
            if s.get('id') == skill_id:
                return s
        return None

    def save_skill(self, *, name: str, description: str, steps: list,
                   bot_id: str, source_job_id: str | None = None) -> dict:
        item = {
            'id': f'skill_{uuid.uuid4().hex[:10]}',
            'name': name.strip(),
            'description': description.strip(),
            'steps': steps,
            'created_by': bot_id,
            'source_job_id': source_job_id,
            'created_at': _now(),
            'use_count': 0,
        }
        data = self._load(self.skills_path)
        data.setdefault('skills', []).insert(0, item)
        self._save(self.skills_path, data)
        desk = Path(os.environ.get('DESK_ROOT', '/desk'))
        skill_dir = desk / 'skills' / item['id']
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / 'SKILL.md').write_text(
            f"# {item['name']}\n\n{item['description']}\n\n"
            f"## Steps\n\n" + '\n'.join(f"- {s}" for s in steps) + '\n'
        )
        return item

    def bump_skill_use(self, skill_id: str) -> None:
        data = self._load(self.skills_path)
        for i, s in enumerate(data.get('skills') or []):
            if s.get('id') == skill_id:
                s['use_count'] = int(s.get('use_count') or 0) + 1
                data['skills'][i] = s
                self._save(self.skills_path, data)
                return

    # ── group threads ─────────────────────────────────────────────────
    def list_threads(self) -> list[dict]:
        return list(self._load(self.threads_path).get('threads') or [])

    def get_thread(self, thread_id: str) -> dict | None:
        for t in self.list_threads():
            if t.get('id') == thread_id:
                return t
        return None

    def create_thread(self, *, title: str, bot_ids: list[str],
                      opener: str = '') -> dict:
        item = {
            'id': f'gthread_{uuid.uuid4().hex[:10]}',
            'title': title.strip(),
            'bot_ids': list(bot_ids),
            'messages': [],
            'created_at': _now(),
            'updated_at': _now(),
            'status': 'open',
        }
        if opener:
            item['messages'].append({
                'at': _now(), 'from': 'operator', 'text': opener.strip(),
            })
        data = self._load(self.threads_path)
        data.setdefault('threads', []).insert(0, item)
        self._save(self.threads_path, data)
        return item

    def post_thread(self, thread_id: str, *, from_id: str, text: str) -> dict | None:
        data = self._load(self.threads_path)
        for i, t in enumerate(data.get('threads') or []):
            if t.get('id') == thread_id:
                t.setdefault('messages', []).append({
                    'at': _now(), 'from': from_id, 'text': text.strip(),
                })
                t['messages'] = t['messages'][-200:]
                t['updated_at'] = _now()
                data['threads'][i] = t
                self._save(self.threads_path, data)
                return t
        return None

    def spawn_group_jobs(self, thread_id: str, brief: str) -> list[dict]:
        t = self.get_thread(thread_id)
        if not t:
            return []
        jobs = []
        for bot_id in t.get('bot_ids') or []:
            jobs.append(self.create_job(
                bot_id=bot_id,
                title=f"Group: {t.get('title')}",
                brief=(
                    f"GROUP THREAD {thread_id}\n"
                    f"Participants: {', '.join(t.get('bot_ids') or [])}\n"
                    f"Operator brief: {brief}\n"
                    f"Recent messages:\n" +
                    '\n'.join(
                        f"- {m.get('from')}: {m.get('text')}"
                        for m in (t.get('messages') or [])[-8:]
                    ) +
                    "\nCoordinate via group_post tool. Do your role, then finish."
                ),
                created_by=f'group:{thread_id}',
                thread_id=thread_id,
            ))
        return jobs
