"""Cron-lite routine scheduler for Keep Desk (max 50 routines/bot)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

log = logging.getLogger('keep-bots-routines')

# Supported: "every_N_minutes", "hourly", "daily_HH:MM" (UTC)
_EVERY = re.compile(r'^every_(\d+)_minutes$')
_DAILY = re.compile(r'^daily_(\d{2}):(\d{2})$')


def due(routine: dict, now: datetime | None = None) -> bool:
    if not routine.get('enabled', True):
        return False
    now = now or datetime.now(timezone.utc)
    cron = (routine.get('cron') or '').strip()
    last = routine.get('last_run_at')
    last_dt = None
    if last:
        try:
            last_dt = datetime.fromisoformat(last.replace('Z', '+00:00'))
        except Exception:
            last_dt = None

    m = _EVERY.match(cron)
    if m:
        mins = max(1, int(m.group(1)))
        if last_dt is None:
            return True
        return (now - last_dt).total_seconds() >= mins * 60

    if cron == 'hourly':
        if last_dt is None:
            return True
        return (now - last_dt).total_seconds() >= 3600

    m = _DAILY.match(cron)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if now.hour != hh or now.minute != mm:
            return False
        if last_dt and last_dt.date() == now.date():
            return False
        return True

    return False


def fire_due(store) -> list[dict]:
    fired = []
    for r in store.list_routines():
        if not due(r):
            continue
        job = store.create_job(
            bot_id=r['bot_id'],
            title=f"Routine: {r['name']}",
            brief=r.get('brief') or r['name'],
            created_by=f"routine:{r['id']}",
        )
        # stamp last_run
        data_routines = store._load(store.routines_path)
        for i, item in enumerate(data_routines.get('routines') or []):
            if item.get('id') == r['id']:
                item['last_run_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
                data_routines['routines'][i] = item
                break
        store._save(store.routines_path, data_routines)
        if r.get('skill_id'):
            store.append_job_log(job['id'], f"routine skill hint: {r['skill_id']}")
        fired.append({'routine_id': r['id'], 'job_id': job['id']})
        log.info('fired routine %s → %s', r['id'], job['id'])
    return fired
