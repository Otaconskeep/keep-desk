"""Plain-language AI briefing + structured mission rationale for the Command Deck."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def build_briefing(
    *,
    store,
    mission: dict | None = None,
    chat_messages: list[dict] | None = None,
) -> dict[str, Any]:
    """Build the Command Deck home briefing.

    Precedence (never regress):
      1. Latest completed mission summary
      2. Active mission state (live override while running/queued)
      3. Unresolved blocker (approvals — only if no completed mission)
      4. Old failure history (timeline/evidence only once superseded)

    Invariant: after a successful mission finish, older failures and L5/diagnostic
    telemetry must never hijack headline, objective, next_step, or attention.
    A failure may drive home only when it is the latest finished outcome.
    """
    jobs = store.list_jobs()
    bots = store.list_bots()
    approvals = store.list_approvals(status='pending')
    running = [j for j in jobs if j.get('status') == 'running']
    queued = [j for j in jobs if j.get('status') == 'queued']
    recent_done = [j for j in jobs if j.get('status') == 'done']
    recent_failed = [j for j in jobs if j.get('status') == 'failed']
    mission = mission or {}
    l5 = mission.get('l5') or {}
    endure = mission.get('endurance') or {}

    completed = _latest_completed_mission(recent_done)
    newest_failure = _newest_failure(recent_failed)
    # Failure only drives home when it is the latest finished outcome (newer than any success)
    # EXCEPT hollow/off-brief poison finishes — those must not park home on "Incomplete"
    # forever when a real successful mission still exists. Surface them as Attention instead.
    failure_driver = None
    prior_hollow = None
    if newest_failure and (
        not completed or _job_time_key(newest_failure) > _job_time_key(completed)
    ):
        hollowish = bool(
            newest_failure.get('hollow')
            or newest_failure.get('off_brief')
            or _is_hollow_completion(newest_failure)
        )
        if hollowish and completed:
            prior_hollow = newest_failure
        else:
            failure_driver = newest_failure

    mode = select_briefing_mode(
        running=running,
        queued=queued,
        completed=completed,
        approvals=approvals,
        failure=failure_driver,
    )

    # Rationale for the CURRENT briefing driver only.
    # Never attach a prior hollow/completed debrief while a job is live — that
    # made home say "Marked done" during an active run.
    rationale = None
    previous_rationale = None
    if mode == 'completed' and completed:
        rationale = build_mission_rationale(store, completed)
        # Off-brief "done" is a hard failure for home — never celebrate coffee-on-soda
        if (rationale or {}).get('hollow'):
            mode = 'failure'
            failure_driver = completed
    elif mode == 'failure' and failure_driver:
        rationale = build_mission_rationale(store, failure_driver)
    elif mode == 'active' and completed:
        previous_rationale = build_mission_rationale(store, completed)
    elif mode in ('blocker', 'ready') and completed:
        previous_rationale = build_mission_rationale(store, completed)

    speaker = _primary_speaker(
        bots,
        running,
        completed or failure_driver,
    )

    if mode == 'active':
        job = running[0] if running else queued[0]
        phase = 'Running' if running else 'Queued'
        headline = f"{phase} — {(job.get('title') or 'work')[:90]}"
        objective = (
            f"{'Working on' if running else 'Queued'}: “{job.get('title')}” "
            f"({job.get('bot_id')})."
        )
        next_step = (
            'Open Browser Worker to watch, or Workspace for live updates.'
            if running
            else 'Wait for the worker to claim it, or open Workstreams.'
        )
        attention = _approval_lines(approvals) or (
            ['No immediate action — job is running.'] if running else ['No immediate action required.']
        )
        happened = [f"{phase}: “{job.get('title')}”."]
        if completed:
            happened.append(f"Previous result still available: “{completed.get('title')}”.")
        confidence = 'Medium — work in flight.'
        latest_job = job

    elif mode == 'completed':
        assert completed is not None
        rationale = rationale or build_mission_rationale(store, completed)
        hollow = bool((rationale or {}).get('hollow'))
        objective = (rationale or {}).get('one_liner') or f"Finished “{completed.get('title')}”."
        headline = (rationale or {}).get('headline') or (completed.get('title') or 'Mission complete')[:100]
        next_step = (rationale or {}).get('next_step') or 'Open Why this result for the full rationale.'
        attention = _approval_lines(approvals) or (
            ['Last finish did not deliver — re-run or ask the desk what failed.']
            if hollow
            else ['No immediate action required.']
        )
        if prior_hollow:
            attention = [
                f"Prior run off-brief (hard failure): “{(prior_hollow.get('title') or 'job')[:70]}” — Retry for a clean namespaced re-run.",
            ] + [a for a in attention if a != 'No immediate action required.']
            next_step = (
                f"Retry job {prior_hollow.get('id')} for the soda/image brief "
                f"(fresh research folder). Or ignore and continue from the last good mission."
            )
            previous_rationale = build_mission_rationale(store, prior_hollow)
        happened = (rationale or {}).get('happened_bullets') or [
            f"Completed “{completed.get('title')}”."
        ]
        confidence = (
            'Low — finished without delivering the brief.'
            if hollow
            else 'High — latest mission finished with artifacts.'
        )
        latest_job = completed

    elif mode == 'blocker':
        headline = f"{len(approvals)} approval{'s' if len(approvals) != 1 else ''} need you"
        objective = 'Something is blocked on your yes/no before the fleet continues.'
        next_step = 'Open Approvals and clear the pending items.'
        attention = _approval_lines(approvals)
        happened = []
        if completed:
            happened.append(f"Last mission still on file: “{completed.get('title')}”.")
        confidence = 'Medium — waiting on you.'
        latest_job = completed

    elif mode == 'failure':
        assert failure_driver is not None
        failure = failure_driver
        if rationale and rationale.get('hollow'):
            headline = (rationale.get('headline') or f"Failed — {(failure.get('title') or 'job')[:80]}")[:100]
            objective = rationale.get('one_liner') or 'Last finish did not match the brief.'
            next_step = rationale.get('next_step') or 'Re-run. Ignore foreign cart/coffee residue.'
            attention = [
                'Hard failure: deliverable does not match the brief.',
            ] + _approval_lines(approvals)
            happened = rationale.get('happened_bullets') or [
                f"Job {failure.get('id')} finished off-brief."
            ]
            confidence = 'Low — off-brief finish.'
        else:
            headline = f"Failed — {(failure.get('title') or 'job')[:80]}"
            objective = f"Last run failed: “{failure.get('title')}”."
            next_step = 'Open the failure detail, or re-run the workstream.'
            attention = [
                f"{(failure.get('result_summary') or 'unknown error')[:180]}"
            ] + _approval_lines(approvals)
            happened = [f"Job {failure.get('id')} failed."]
            if completed and completed.get('id') != failure.get('id'):
                happened.append(
                    f"Earlier success still on file: “{completed.get('title')}” (see timeline)."
                )
            confidence = 'Low — latest run did not finish cleanly.'
            if not rationale:
                rationale = build_mission_rationale(store, failure)
            # If rationale is hollow, upgrade framing even when status was already failed
            if rationale.get('hollow'):
                headline = (rationale.get('headline') or headline)[:100]
                objective = rationale.get('one_liner') or objective
                next_step = rationale.get('next_step') or next_step
                attention = [
                    'Hard failure: deliverable does not match the brief.',
                ] + _approval_lines(approvals)
                happened = rationale.get('happened_bullets') or happened
                confidence = 'Low — off-brief finish.'
        latest_job = failure

    else:  # ready — no completed mission, no live work, no blockers, no failure
        objective = 'Ready for your next order.'
        headline = 'Ready'
        next_step = 'Ask the fleet a question, or assign a new workstream.'
        attention = ['No immediate action required.']
        happened = _idle_happened(l5, endure)
        confidence = 'High — desk idle and ready.'
        latest_job = None

    meaning = _status_meaning(mode, running, queued, approvals, completed, failure_driver)
    progress = _build_progress(
        store,
        jobs=jobs,
        mode=mode,
        running=running,
        queued=queued,
        focus=latest_job,
        completed=completed,
    )
    if approvals and progress.get('attention_level') == 'green':
        progress['attention_level'] = 'yellow'
    # Prefer parent mission framing when a pipeline just finished
    if mode == 'completed' and progress.get('pipeline_complete'):
        parent = progress.get('parent_title') or headline
        headline = f"Done — {parent}"[:100]
        if progress.get('winner_line'):
            objective = _clean_human_line(progress['winner_line'], 160)
        if not prior_hollow:
            next_step = 'You’re clear — ask for the next mission, or open Why for the trail.'
        # Human happened, not tool telemetry
        happened = []
        for d in (progress.get('definition_of_done') or []):
            if d.get('done') and d.get('detail'):
                happened.append(f"{d.get('label')}: {d.get('detail')}")
            elif d.get('done'):
                happened.append(f"{d.get('label')} — done")
        if not happened:
            happened = ['Mission batches finished.']

    report_lines = [
        f"{speaker['name'].upper()} REPORT",
        '',
        f'Mode: {mode}',
        '',
        'Current objective:',
        objective,
        '',
        'Definition of done:',
        *[f"- [{'x' if d.get('done') else ' '}] {d.get('label')}" for d in (progress.get('definition_of_done') or [])],
        '',
        'What happened:',
        *[f'- {x}' for x in happened],
        '',
        'What needs your attention:',
        *[f'- {x}' for x in attention],
        '',
        f'Confidence:\n{confidence}',
        '',
        'Recommended next step:',
        next_step,
    ]

    return {
        'ok': True,
        'mode': mode,
        'precedence': list(BRIEFING_PRECEDENCE),
        'speaker': speaker,
        'headline': headline,
        'objective': objective,
        'happened': happened[:6],
        'attention': attention[:5],
        'confidence': confidence,
        'confidence_level': (confidence.split()[0] if confidence else 'Medium').rstrip('—'),
        'next_step': next_step,
        'meaning': meaning,
        'progress': progress,
        'definition_of_done': progress.get('definition_of_done') or [],
        'report_text': '\n'.join(report_lines),
        'active_job': running[0] if running else None,
        'latest_job': latest_job,
        'latest_completed': completed,
        'latest_failure': newest_failure,  # timeline/evidence — may be superseded
        'rationale': rationale,
        'previous_rationale': previous_rationale,
        'counts': {
            'running': len(running),
            'queued': len(queued),
            'waiting': len([j for j in jobs if j.get('status') == 'waiting']),
            'approvals': len(approvals),
            'failed_recent': len(recent_failed[:5]),
            'bots': len(bots),
        },
    }


def _build_progress(store, *, jobs, mode, running, queued, focus, completed) -> dict:
    """Running / ETA / batch + definition-of-done checklist for the home UI."""
    focus_job = (running[0] if running else None) or focus or completed
    pipeline_id = (focus_job or {}).get('pipeline_id')
    stages_meta = []
    parent_title = None
    parent_brief = None
    winner_line = None

    if pipeline_id:
        pipe_jobs = [j for j in jobs if j.get('pipeline_id') == pipeline_id]
        pipe_jobs.sort(key=lambda j: j.get('stage_index') if j.get('stage_index') is not None else 99)
        total = max((j.get('stage_total') or 0 for j in pipe_jobs), default=0) or len(pipe_jobs)
        for j in pipe_jobs:
            st = j.get('status') or 'waiting'
            done = st == 'done'
            stages_meta.append({
                'index': j.get('stage_index'),
                'id': j.get('stage_id'),
                'label': j.get('stage_label') or f"Stage {(j.get('stage_index') or 0) + 1}",
                'status': st,
                'done': done,
                'job_id': j.get('id'),
                'summary': _human_stage_detail(j) if done else '',
            })
            if j.get('parent_title'):
                parent_title = j.get('parent_title')
            if j.get('parent_brief'):
                parent_brief = j.get('parent_brief')
        # Prefer a human winner line from study/cart summaries
        for j in reversed(pipe_jobs):
            if j.get('status') != 'done':
                continue
            raw = (j.get('result_summary') or '').strip()
            if not raw:
                continue
            for line in raw.splitlines():
                line = line.strip().lstrip('#').strip()
                if not line or line.lower().startswith('action taken'):
                    continue
                if line.lower().startswith('stage '):
                    continue
                if 'winner' in line.lower() or 'recommend' in line.lower():
                    winner_line = re.sub(r'\*\*', '', line)[:200]
                    break
                if not winner_line and len(line) > 20:
                    winner_line = re.sub(r'\*\*', '', line)[:200]
            if winner_line:
                break
        current = focus_job or pipe_jobs[-1]
        cur_idx = (current.get('stage_index') if current else 0) or 0
        done_n = sum(1 for s in stages_meta if s['done'])
        pipeline_complete = done_n >= total and total > 0 and mode != 'active'
        batch = {
            'pipeline_id': pipeline_id,
            'current': cur_idx + 1,
            'total': total,
            'label': (current or {}).get('stage_label') or f'{cur_idx + 1}/{total}',
            'done_count': done_n,
            'stages': stages_meta,
        }
    else:
        total = 1
        cur_idx = 0
        done_n = 1 if mode == 'completed' else 0
        pipeline_complete = mode == 'completed'
        parent_title = (focus_job or {}).get('title')
        parent_brief = (focus_job or {}).get('brief')
        batch = {
            'pipeline_id': None,
            'current': 1 if focus_job else 0,
            'total': 1 if focus_job else 0,
            'label': '—',
            'done_count': done_n,
            'stages': [],
        }

    # Definition of done — human checklist labels, never raw markdown dumps
    dod = []
    if stages_meta:
        for s in stages_meta:
            dod.append({
                'id': s.get('id') or s.get('label'),
                'label': _human_stage_label(s),
                'done': bool(s.get('done')),
                'detail': s.get('summary') or (
                    'In progress' if s.get('status') == 'running' else (
                        'Waiting' if s.get('status') == 'waiting' else ''
                    )
                ),
            })
    elif parent_brief:
        parts = [
            p.strip()
            for p in re.split(
                r'\b(?:then after you|then after|after that|and then|then|finally)\b',
                parent_brief,
                flags=re.I,
            )
            if p and len(p.strip()) > 8
        ]
        if len(parts) >= 2:
            for i, p in enumerate(parts[:6], start=1):
                dod.append({
                    'id': f'p{i}',
                    'label': _clean_human_line(p, 72),
                    'done': mode == 'completed',
                    'detail': '',
                })
        else:
            dod.append({
                'id': 'goal',
                'label': _clean_human_line(parent_brief or parent_title or 'Complete the brief', 90),
                'done': mode == 'completed',
                'detail': '',
            })
    else:
        dod.append({
            'id': 'idle',
            'label': 'Assign a mission to set done criteria',
            'done': False,
            'detail': '',
        })

    # ETA from elapsed + remaining stages
    eta_label = '—'
    eta_sec = None
    running_job = running[0] if running else None
    if running_job and running_job.get('started_at'):
        try:
            started = datetime.fromisoformat(str(running_job['started_at']).replace('Z', '+00:00'))
            elapsed = max(1, int((datetime.now(started.tzinfo) - started).total_seconds()))
        except Exception:
            elapsed = 180
        # rough: 3–4 min per remaining stage including current
        remain_stages = max(1, (batch.get('total') or 1) - (batch.get('done_count') or 0))
        # blend elapsed pace: if we've been going, extrapolate
        per = max(120, min(420, elapsed if (batch.get('done_count') or 0) == 0 else 180))
        eta_sec = remain_stages * per - min(elapsed, per)
        eta_sec = max(30, eta_sec)
        eta_label = _fmt_duration(eta_sec)
    elif mode == 'completed':
        eta_label = '0'
        eta_sec = 0
    elif queued:
        eta_label = '~2m'
        eta_sec = 120

    all_done = all(d.get('done') for d in dod) if dod else False
    return {
        'running': bool(running),
        'queued': len(queued),
        'status_label': (
            'Running' if running else (
                'Queued' if queued else (
                    'Complete' if mode == 'completed' else mode.title()
                )
            )
        ),
        'batch': batch,
        'eta_label': eta_label,
        'eta_sec': eta_sec,
        'definition_of_done': dod,
        'definition_complete': all_done and mode == 'completed',
        'parent_title': parent_title,
        'parent_brief': parent_brief,
        'pipeline_complete': bool(pipeline_id and pipeline_complete),
        'winner_line': winner_line,
        'done_next': (
            'Mission complete — open Why this result, or assign the next order.'
            if pipeline_complete else None
        ),
        'attention_level': (
            'red' if mode == 'failure' else (
                'yellow' if mode in ('active', 'blocker') or (mode == 'completed' and not all_done) else
                'green'
            )
        ),
    }


def _clean_human_line(text: str, limit: int = 100) -> str:
    if not text:
        return ''
    t = re.sub(r'[*_#>`]+', '', text)
    t = re.sub(r'\s+', ' ', t).strip(' :-\t')
    t = re.sub(
        r'^(winner product|recommended|completed stage \d+[^.]*\.?\s*recommended|stage \d+.*?:)\s*',
        '',
        t,
        flags=re.I,
    )
    t = t.strip(' :-\t')
    return t[:limit]


def _human_stage_label(stage: dict) -> str:
    sid = (stage.get('id') or '').lower()
    lab = (stage.get('label') or '').lower()
    mapping = {
        'shortlist': 'Find the shortlist',
        'picks': 'Pick one product each',
        'study': 'Recommend a winner',
        'cart': 'Add winner to cart',
    }
    for k, v in mapping.items():
        if k in sid or k in lab:
            return v
    # strip "1/4 · "
    clean = re.sub(r'^\d+/\d+\s·\s*', '', stage.get('label') or 'Step')
    return clean


def _human_stage_detail(job: dict) -> str:
    """One plain sentence a human can skim — never markdown dumps."""
    raw = (job.get('result_summary') or '').strip()
    if not raw:
        return 'Done'
    sid = (job.get('stage_id') or '').lower()
    # Prefer bold names / winner lines
    bolds = re.findall(r'\*\*([^*]+)\*\*', raw)
    if 'cart' in sid or 'winner' in raw.lower():
        for b in bolds:
            if any(x in b.lower() for x in ('coffee', 'kenya', 'yellow', 'brick', 'presta', 'exo')):
                return f'In cart: {_clean_human_line(b, 80)}'
        for line in raw.splitlines():
            if 'winner' in line.lower():
                return 'In cart: ' + _clean_human_line(line, 80)
    if 'study' in sid or 'recommend' in raw.lower():
        m = re.search(r'[Rr]ecommended\s+(.+?)(?:\s+for\b|$)', raw)
        if m:
            return _clean_human_line(m.group(1), 90)
        for line in raw.splitlines():
            if 'recommend' in line.lower() or 'winner' in line.lower():
                return _clean_human_line(line, 90)
        if bolds:
            return f'Pick: {_clean_human_line(bolds[0], 70)}'
    if 'pick' in sid:
        names = [_clean_human_line(b, 40) for b in bolds[:3] if len(b) > 3]
        if names:
            return ' · '.join(names)
    if 'short' in sid:
        names = [_clean_human_line(b, 36) for b in bolds[:3] if len(b) > 3]
        if names:
            return ', '.join(names)
    # fallback: first non-heading sentence
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('**Action'):
            continue
        return _clean_human_line(line, 90)
    return 'Done'


BRIEFING_PRECEDENCE = (
    'completed',  # latest successful mission debrief
    'active',     # running / queued — live override while in flight
    'blocker',    # unresolved approvals (only if no completed mission)
    'failure',    # only when no newer completed mission exists
)


def select_briefing_mode(
    *,
    running: list,
    queued: list,
    completed: dict | None,
    approvals: list,
    failure: dict | None,
) -> str:
    """Home briefing driver.

    Product order: completed > active > blocker > old failure history.

    Rules:
      • Active takes the stage while work is running/queued.
      • ``failure`` is only passed in when it is newer than any completed mission
        (i.e. it is the latest finished outcome). Older failures are omitted by
        the caller so they cannot hijack home after a successful finish.
      • Otherwise completed owns home and beats blockers + diagnostics.
    """
    if running or queued:
        return 'active'
    if failure:
        return 'failure'
    if completed:
        return 'completed'
    if approvals:
        return 'blocker'
    return 'ready'



def build_mission_rationale(store, job: dict | None) -> dict[str, Any] | None:
    """Structured why/how card — scoped to THIS job's writes (and its pipeline siblings).

    Never reuse leftover research files from a prior mission. Artifacts count
    only if this job (or another stage in the same pipeline_id) wrote them via
    desk_write in tool_trace. Stops shoe/YouTube bleed while still showing the
    full shortlist → picks → trade study → cart story for batched missions.
    """
    if not job:
        return None
    import os
    desk = Path(os.environ.get('DESK_ROOT', '/desk'))

    pipeline_jobs = _pipeline_jobs(store, job)
    traces = []
    for pj in pipeline_jobs:
        traces.extend(pj.get('tool_trace') or [])
    tools = [t.get('tool') for t in traces if t.get('tool')]
    urls = _urls_from_trace(traces)
    yt = _youtube_from_trace(traces)
    duration_sec = sum(_duration_sec(pj) or 0 for pj in pipeline_jobs) or _duration_sec(job)
    duration_label = _fmt_duration(duration_sec)
    title = job.get('parent_title') or job.get('title') or 'Mission'
    brief = job.get('parent_brief') or job.get('brief') or ''
    written_paths: list[str] = []
    artifact_texts: dict[str, str] = {}
    for pj in pipeline_jobs:
        for rel in _paths_written_by_job(pj.get('tool_trace') or []):
            if rel not in written_paths:
                written_paths.append(rel)
            body, rel_key = _load_desk_artifact(desk, rel)
            if body and rel_key not in artifact_texts:
                artifact_texts[rel_key] = body

    sites = _site_hosts(urls)
    hollow = _is_hollow_completion(job, artifact_texts)
    one_liner = _one_liner_for_job(job, artifact_texts, hollow=hollow)
    headline = _headline_for_job(job, hollow=hollow)
    happened = _happened_for_job(job, tools, urls, yt, written_paths, duration_label, hollow=hollow)

    sections = [
        {
            'id': 'summary',
            'title': 'Bottom line',
            'body': one_liner,
        },
    ]

    if hollow:
        sections.append({
            'id': 'gap',
            'title': 'Hard failure — off-brief deliverable',
            'body': _hollow_explanation(job, artifact_texts),
            'why': 'Marked done, but the written result does not match the job brief.',
        })
        sections.append({
            'id': 'sites',
            'title': 'Sites checked (forensics)',
            'items': sites[:14] or ['(none)'],
            'urls': urls[:14],
        })
        sections.append({
            'id': 'time',
            'title': 'Time spent',
            'body': duration_label,
            'meta': f"Job {job.get('id')} · HOLLOW",
        })
        sections.append({
            'id': 'tools',
            'title': 'How it worked',
            'items': _dedupe_preserve(tools)[:28] or ['(no tools recorded)'],
        })
        return {
            'job_id': job.get('id'),
            'pipeline_id': job.get('pipeline_id'),
            'title': title,
            'status': 'failed',
            'headline': headline,
            'one_liner': one_liner,
            'next_step': 'Reject this result — re-run. Do not trust coffee/cart residue on this brief.',
            'happened_bullets': happened,
            'duration_sec': duration_sec,
            'duration_label': duration_label,
            'sections': sections,
            'artifacts': list(artifact_texts.keys()),
            'screenshot': 'workspace/screenshots/live.png',
            'hollow': True,
            'shoe_name': None,
            'yt_title': None,
            'yt_url': None,
            'shoe_url': None,
        }

    if yt or any('youtube' in (u or '') for u in urls):
        if any(k in brief.lower() for k in ('youtube', 'transcript', 'news', 'video')):
            sections.append({
                'id': 'youtube',
                'title': 'YouTube',
                'body': (yt or {}).get('title') or 'YouTube video',
                'why': 'Pulled during this job (see tool trace).',
                'url': (yt or {}).get('url') or next((u for u in urls if 'youtube.com' in u), None),
                'meta': f"Transcript chars: {(yt or {}).get('chars')}" if (yt or {}).get('chars') else None,
            })

    pipeline_sections = _pipeline_artifact_sections(artifact_texts)
    if pipeline_sections:
        sections.extend(pipeline_sections)
    else:
        pick_section = _pick_section_from_artifacts(artifact_texts, urls, brief)
        if pick_section:
            sections.append(pick_section)

    stage_meta = ''
    if job.get('pipeline_id') and len(pipeline_jobs) > 1:
        stage_meta = f"Pipeline {job.get('pipeline_id')} · {len(pipeline_jobs)} stages"
    sections.append({
        'id': 'sites',
        'title': 'Sites checked',
        'items': sites[:14] or ['(no sites visited in this mission’s tool trace)'],
        'urls': urls[:14],
    })
    sections.append({
        'id': 'time',
        'title': 'Time spent',
        'body': duration_label,
        'meta': stage_meta or f"Job {job.get('id')}",
    })
    sections.append({
        'id': 'tools',
        'title': 'How it worked',
        'items': _dedupe_preserve(tools)[:28] or ['(no tools recorded)'],
    })

    return {
        'job_id': job.get('id'),
        'pipeline_id': job.get('pipeline_id'),
        'title': title,
        'status': job.get('status'),
        'headline': headline,
        'one_liner': one_liner,
        'next_step': 'Open Why this result for the trade study, picks, and sites.',
        'happened_bullets': happened,
        'duration_sec': duration_sec,
        'duration_label': duration_label,
        'sections': sections,
        'artifacts': list(artifact_texts.keys()),
        'screenshot': 'workspace/screenshots/live.png',
        'hollow': False,
        'shoe_name': None,
        'yt_title': (yt or {}).get('title'),
        'yt_url': (yt or {}).get('url'),
        'shoe_url': None,
    }


def _is_hollow_completion(job: dict, artifact_texts: dict | None = None) -> bool:
    """Done on paper, but did not actually deliver THIS mission."""
    summary = (job.get('result_summary') or '').strip()
    low = summary.lower()
    if not summary:
        return True
    if any(x in low for x in ('"error"', 'not found', 'failed', 'stopped:', 'traceback', 'max steps')):
        return True
    tools = [t.get('tool') for t in (job.get('tool_trace') or []) if t.get('tool')]
    meaningful = [
        t for t in tools
        if t not in ('finish', 'desk_list', 'operator_chat', 'room_list', 'group_post')
    ]
    if not meaningful:
        return True
    if _off_brief_mismatch(job, artifact_texts):
        return True
    return False


def _brief_blob(job: dict) -> str:
    return ' '.join(
        str(job.get(k) or '')
        for k in ('parent_brief', 'parent_title', 'brief', 'title', 'stage_label')
    ).lower()


def _off_brief_mismatch(job: dict, artifact_texts: dict | None = None) -> bool:
    """True when deliverable is clearly a different mission (e.g. coffee cart on a soda brief)."""
    brief = _brief_blob(job)
    content = (job.get('result_summary') or '').lower()
    if artifact_texts:
        content += '\n' + '\n'.join(str(v).lower() for v in artifact_texts.values())

    def has(*keys: str) -> bool:
        return any(k in brief for k in keys)

    def body(*keys: str) -> bool:
        return any(k in content for k in keys)

    # Soda / image pick vs coffee shopping
    if has('soda', 'cola', 'soft drink') or (
        has('image', 'images', 'photo', 'photos', 'picture') and has('google', 'find')
    ):
        if body('yellow brick', 'kenya', 'nyeri', 'presta', 'exo roast', 'coffee roaster'):
            if not body('soda', 'cola', 'soft drink'):
                return True
        if body('ai_news', 'amazon shoe', 'sneaker') and not body('soda', 'image', 'photo', 'picture'):
            return True

    # Explicit coffee brief should not finish as shoes / ai news only
    if has('coffee', 'roaster', 'tucson') and not has('soda'):
        if body('soda') and not body('coffee', 'roaster', 'kenya', 'presta'):
            return True

    # Cart stage that never mentions brief nouns
    if 'cart' in (job.get('stage_id') or '') or 'cart' in (job.get('stage_label') or '').lower():
        # extract a few contentful tokens from parent/brief
        tokens = [
            w for w in re.findall(r'[a-z]{4,}', brief)
            if w not in {
                'stage', 'batched', 'complete', 'parent', 'goal', 'context', 'finish',
                'workspace', 'research', 'pipeline', 'write', 'then', 'with', 'from',
                'this', 'that', 'only', 'after', 'want', 'find', 'best', 'cart',
            }
        ][:12]
        if tokens and content and not any(t in content for t in tokens):
            # foreign shopping residue
            if body('coffee', 'kenya', 'yellow brick', 'shoe', 'sneaker'):
                return True
    return False


def _paths_written_by_job(trace: list) -> list[str]:
    out = []
    for t in trace:
        if t.get('tool') not in ('desk_write', 'write_file', 'save'):
            continue
        args = t.get('args') or {}
        res = t.get('result') or {}
        for blob in (args, res):
            p = blob.get('path')
            if isinstance(p, str) and p.strip():
                rel = p.strip()
                if rel not in out:
                    out.append(rel)
    return out


def _one_liner_for_job(job: dict, artifacts: dict, *, hollow: bool) -> str:
    summary = (job.get('result_summary') or '').strip()
    title = job.get('title') or 'mission'
    if hollow:
        return (
            f"Hard failure — off-brief deliverable for “{title[:70]}”. "
            f"Do not trust cart/coffee residue."
        )[:220]
    # Prefer first paragraph of a written report — recommendation/cart before shortlist
    prefer = sorted(
        artifacts.items(),
        key=lambda kv: (
            0 if 'recommend' in kv[0].lower() else
            1 if 'cart' in kv[0].lower() else
            2 if 'pick' in kv[0].lower() else 3
        ),
    )
    for path, body in prefer:
        if path.endswith('.md') and body.strip():
            lines = body.splitlines()
            for i, line in enumerate(lines):
                if re.search(r'^\s*#{0,3}\s*winner\b', line, re.I):
                    # next non-empty content line is the pick
                    for nxt in lines[i + 1 : i + 4]:
                        cleaned = re.sub(r'\*\*', '', nxt).strip()
                        cleaned = re.sub(r'^#+\s*', '', cleaned)
                        if len(cleaned) > 8:
                            return f"Winner · {cleaned}"[:220]
                    continue
                if re.search(r'\*\*why\?\*\*|^\s*why\?', line, re.I):
                    continue
                if re.search(r'winner\s*[·:\-–]', line, re.I) and len(line.strip()) > 12:
                    cleaned = re.sub(r'\*\*', '', line).strip()
                    cleaned = re.sub(r'^#+\s*', '', cleaned)
                    if len(cleaned) > 16:
                        return cleaned[:220]
            for para in [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]:
                low = para.lower()
                if low.startswith('hey') or low.startswith('hi '):
                    continue
                if low.startswith('# top') or low.startswith('## coffee product') or low.startswith('## trade'):
                    continue
                if low.startswith('## stage'):
                    continue
                line = para.split('\n')[0].replace('**', '').strip()
                if len(line) > 20:
                    return line[:220]
    if summary and not summary.startswith('{'):
        return summary.split('\n')[0][:220]
    return f"Finished “{title}”."[:220]


def _headline_for_job(job: dict, *, hollow: bool) -> str:
    title = (job.get('title') or 'Mission').strip()
    short = title if len(title) <= 72 else title[:69] + '…'
    if hollow:
        return f"Incomplete — {short}"[:100]
    return f"Done — {short}"[:100]


def _hollow_explanation(job: dict, artifact_texts: dict | None = None) -> str:
    tools = [t.get('tool') for t in (job.get('tool_trace') or []) if t.get('tool')]
    summary = (job.get('result_summary') or '').strip()
    bits = []
    if _off_brief_mismatch(job, artifact_texts):
        bits.append(
            'Deliverable is off-brief (e.g. coffee cart / AI-news residue on a soda/image mission).'
        )
    if tools:
        bits.append(f"Tools used: {', '.join(tools[:8])}.")
    else:
        bits.append('No tools recorded.')
    if summary:
        bits.append(f"Finish note: {summary[:180]}")
    arts = list((artifact_texts or {}).keys())
    if arts:
        bits.append(f"Wrote: {', '.join(arts[:4])}.")
    bits.append('Do not treat foreign shopping artifacts as this mission’s answer.')
    return ' '.join(bits)


def _happened_for_job(job, tools, urls, yt, written, duration_label, *, hollow) -> list[str]:
    out = []
    if hollow:
        out.append('Job finished without completing the brief.')
    if yt:
        out.append(f"YouTube: {(yt or {}).get('title') or (yt or {}).get('url')}.")
    if urls:
        hosts = _site_hosts(urls)
        out.append(f"Visited {len(hosts)} site(s): {', '.join(hosts[:5])}{'…' if len(hosts) > 5 else ''}.")
    if written:
        out.append(f"Wrote {len(written)} file(s).")
    if tools:
        out.append(f"Tools: {', '.join(tools[:8])}{'…' if len(tools) > 8 else ''}.")
    if duration_label and duration_label != '—':
        out.append(f"Took {duration_label}.")
    if not out:
        out.append(f"Finished “{job.get('title')}”.")
    return out


def _pipeline_jobs(store, job: dict) -> list[dict]:
    """This job plus same-pipeline siblings, ordered by stage_index."""
    pid = job.get('pipeline_id')
    if not pid:
        return [job]
    try:
        siblings = [j for j in store.list_jobs() if j.get('pipeline_id') == pid]
    except Exception:
        return [job]
    if not siblings:
        return [job]
    siblings.sort(key=lambda j: (j.get('stage_index') is None, j.get('stage_index') or 0, _job_time_key(j)))
    return siblings


def _load_desk_artifact(desk: Path, rel: str) -> tuple[str, str]:
    p = desk / rel if not rel.startswith('/') else Path(rel)
    try:
        if str(p).startswith(str(desk)):
            rel_key = str(p.relative_to(desk))
        else:
            rel_key = rel.lstrip('/')
            if rel_key.startswith('desk/'):
                rel_key = rel_key[5:]
            p = desk / rel_key
    except Exception:
        rel_key = rel
        p = desk / rel
    body = _read_md(p)
    return body or '', rel_key


def _dedupe_preserve(items: list) -> list:
    seen = set()
    out = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _pipeline_artifact_sections(artifacts: dict) -> list[dict]:
    """Ordered mission story from known pipeline filenames (namespaced or legacy)."""
    order = [
        ('images.md', 'images', 'Images shortlisted'),
        ('pipeline_shortlist.md', 'shortlist', 'Shortlist'),
        ('shortlist.md', 'shortlist', 'Shortlist'),
        ('pipeline_picks.md', 'picks', 'Picks'),
        ('picks.md', 'picks', 'Picks'),
        ('pick.md', 'pick', 'Winner pick'),
        ('pipeline_recommendation.md', 'trade', 'Trade study'),
        ('recommendation.md', 'trade', 'Trade study'),
        ('dossier.md', 'dossier', 'YT + store dossier'),
        ('pipeline_cart.md', 'cart', 'Cart action'),
        ('cart.md', 'cart', 'Cart action'),
    ]
    sections: list[dict] = []
    for fname, sid, title in order:
        path = next((p for p in artifacts if p.endswith(fname)), None)
        if not path:
            continue
        body = artifacts[path]
        clipped = body.strip()
        if len(clipped) > 4200:
            clipped = clipped[:4200].rstrip() + '\n…'
        sec: dict[str, Any] = {
            'id': sid,
            'title': title,
            'body': clipped,
            'meta': path,
            'url': _first_url(body),
            'format': 'markdown',
        }
        if sid == 'trade':
            study = _parse_trade_study(body)
            if study:
                sec['study'] = study
                sec['title'] = 'Decision dossier · trade study'
        if sid == 'picks':
            opts = _parse_pick_options(body)
            if opts:
                sec['options'] = opts
        sections.append(sec)
    return sections


def _parse_markdown_tables(text: str) -> list[dict]:
    """Return list of {headers, rows} for GFM-ish tables in text."""
    lines = text.splitlines()
    tables: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if '|' in line and i + 1 < len(lines) and re.match(r'^\s*\|?[\s:-]+\|', lines[i + 1]):
            headers = [c.strip() for c in line.strip('|').split('|')]
            i += 2
            rows = []
            while i < len(lines) and '|' in lines[i]:
                row = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if row and not all(re.match(r'^:?-+:?$', c) for c in row):
                    # pad/trim to header width
                    while len(row) < len(headers):
                        row.append('')
                    rows.append(row[: len(headers)])
                i += 1
            if headers and rows:
                tables.append({'headers': headers, 'rows': rows})
            continue
        i += 1
    return tables


def _parse_trade_study(body: str) -> dict | None:
    """Lift a decision dossier from stage-3 markdown (best-effort)."""
    if not body or len(body.strip()) < 40:
        return None
    tables = _parse_markdown_tables(body)
    winner = None
    m = re.search(
        r'(?:###?\s*Winner\s*\n+\s*\*?\*?([^\n*]+)\*?\*?)'
        r'|(?:\*\*Winner(?:\s*product)?\*\*\s*[:—-]?\s*([^\n]+))',
        body,
        re.I,
    )
    if m:
        winner = (m.group(1) or m.group(2) or '').strip().strip('.')

    # Criteria from table headers (skip identity cols)
    criteria: list[str] = []
    options: list[dict] = []
    matrix = None
    if tables:
        primary = tables[0]
        headers = primary['headers']
        skip = {'roaster', 'product', 'option', 'name', 'item', '#'}
        criteria = [h for h in headers[1:] if h.lower() not in skip]
        # If first cols are Roaster+Product, keep both as label
        for row in primary['rows']:
            if len(headers) >= 2 and headers[0].lower() in ('roaster', 'option') and headers[1].lower() == 'product':
                a = re.sub(r'\*\*', '', row[0])
                b = re.sub(r'\*\*', '', row[1])
                label = f'{a} — {b}'
                cells = row[2:]
                crit_headers = headers[2:]
            else:
                label = re.sub(r'\*\*', '', row[0])
                cells = row[1:]
                crit_headers = headers[1:]
            options.append({
                'name': label.strip(),
                'scores': {crit_headers[i]: cells[i] for i in range(min(len(crit_headers), len(cells)))},
            })
        matrix = {'headers': headers, 'rows': primary['rows']}

    # Sensitivity / what would change
    change = None
    for pat in (
        r'what would change[^\n]*\n+([\s\S]{0,400}?)(?:\n#{1,3}\s|\Z)',
        r'sensitivity[^\n]*\n+([\s\S]{0,400}?)(?:\n#{1,3}\s|\Z)',
    ):
        cm = re.search(pat, body, re.I)
        if cm:
            change = cm.group(1).strip()[:400]
            break

    why_bits = []
    wm = re.search(r'\*\*Why\?\*\*\s*([\s\S]{0,600}?)(?:\nI recommend|\n###|\Z)', body, re.I)
    if wm:
        why_bits.append(wm.group(1).strip()[:500])

    # Cost-weight disclosure if price dominated
    cost_heavy = bool(re.search(r'balanced price|price point|affordable|\$\d+', body, re.I)) and bool(
        re.search(r'winner', body, re.I)
    )

    if not options and not winner:
        return None

    return {
        'winner': winner,
        'criteria': criteria,
        'options': options,
        'matrix': matrix,
        'why': why_bits[0] if why_bits else None,
        'what_would_change': change,
        'caveats': (
            ['Study narrative weighted price/everyday-fit — re-run if cost weight should be 0.']
            if cost_heavy and not change
            else []
        ),
        'confidence': 'medium' if options else 'low',
    }


def _parse_pick_options(body: str) -> list[dict]:
    opts = []
    for m in re.finditer(
        r'\d+\.\s+\*\*([^*]+)\*\*\s*[—–-]\s*\*?([^*\n]+)\*?.*?(?:URL|url):\s*(\S+)',
        body,
        re.S,
    ):
        opts.append({
            'roaster': m.group(1).strip(),
            'product': m.group(2).strip(),
            'url': m.group(3).strip().rstrip(')'),
        })
    return opts


def _pick_section_from_artifacts(artifacts: dict, urls: list, brief: str) -> dict | None:
    """If this job wrote a pick/report, surface it — never invent shoes/coffee."""
    if not artifacts:
        return None
    # Prefer recommendation / trade over cart
    ranked = sorted(
        artifacts.items(),
        key=lambda kv: (
            0 if 'recommend' in kv[0].lower() or 'trade' in kv[0].lower() else
            1 if 'pick' in kv[0].lower() else
            2 if 'cart' in kv[0].lower() else 3
        ),
    )
    for path, body in ranked:
        name = path.rsplit('/', 1)[-1].lower()
        if not any(k in name for k in ('pick', 'recommend', 'report', 'trade', 'coffee', 'shoe', 'cart')):
            if not path.endswith('.md'):
                continue
        pick = _first_productish_bold(body) or _labeled_value(body, r"I.?d look at") or _labeled_value(body, r'Recommend')
        why = _section(body, 'Why this one') or _section(body, 'Why') or _section(body, 'Bottom line')
        if not pick and not why:
            continue
        return {
            'id': 'pick',
            'title': 'Recommendation',
            'body': pick or 'See written report',
            'why': (why[:420] if why else 'From this job’s written artifact.'),
            'url': _first_url(body) or (urls[0] if urls else None),
            'meta': path,
        }
    return None



def _job_time_key(j: dict) -> str:
    return j.get('finished_at') or j.get('updated_at') or j.get('created_at') or ''


def _is_routine(j: dict) -> bool:
    return (j.get('title') or '').lower().startswith('routine:')


def _latest_completed_mission(done: list) -> dict | None:
    """Newest successful operator mission (routines excluded)."""
    pool = [j for j in done if not _is_routine(j)]
    if not pool:
        pool = list(done)
    if not pool:
        return None
    pool.sort(key=_job_time_key, reverse=True)
    return pool[0]


def _newest_failure(failed: list) -> dict | None:
    pool = [j for j in failed if not _is_routine(j)]
    if not pool:
        pool = list(failed)
    if not pool:
        return None
    pool.sort(key=_job_time_key, reverse=True)
    return pool[0]


def _latest_failure_without_newer_success(done: list, failed: list) -> dict | None:
    """Newest failure only if nothing completed more recently.

    Old failures stay in jobs/timeline/evidence — they must not surface as the
    briefing driver once a newer mission has finished successfully.
    """
    failure = _newest_failure(failed)
    if not failure:
        return None
    completed = _latest_completed_mission(done)
    if completed and _job_time_key(completed) >= _job_time_key(failure):
        return None
    return failure


def _primary_speaker(bots, running, latest) -> dict:
    bid = None
    if running:
        bid = running[0].get('bot_id')
    elif latest:
        bid = latest.get('bot_id')
    bot = next((b for b in bots if b.get('id') == bid), None) if bid else None
    if not bot and bots:
        bot = bots[0]
    if bot:
        return {
            'id': bot['id'],
            'name': bot.get('name') or bot['id'],
            'role': bot.get('role') or 'operator',
            'color': bot.get('color') or '#5ec8ff',
        }
    return {'id': 'desk', 'name': 'Keep Desk', 'role': 'system', 'color': '#5ec8ff'}


def _approval_lines(approvals: list) -> list[str]:
    out = []
    for a in approvals[:3]:
        out.append(
            f"Approval: {a.get('bot_id')} wants to {a.get('action') or 'act'} "
            f"— {(a.get('detail') or '')[:80]}"
        )
    return out


def _idle_happened(l5, endure) -> list[str]:
    out = []
    if l5.get('gate_pass'):
        out.append('Browser maturity gate is clear in the background.')
    if endure.get('ticks'):
        out.append(f"Endurance heartbeat: {endure.get('state')} · {endure.get('ticks')} ticks.")
    if not out:
        out.append('No live mission right now.')
    return out


def _status_meaning(
    mode: str,
    running: list,
    queued: list,
    approvals: list,
    completed: dict | None,
    failure: dict | None,
) -> list[dict]:
    items = [{
        'label': 'Briefing mode',
        'meaning': {
            'completed': 'Showing latest completed mission — failures stay in the timeline.',
            'active': 'Live work is in flight — last completed result stays available under Why.',
            'blocker': 'Blocked on your approval.',
            'failure': 'Latest outcome was a failure (no newer successful mission).',
            'ready': 'Desk idle — ready for your next order.',
        }.get(mode, mode),
    }]
    if mode == 'active' and running:
        items.append({
            'label': 'Running',
            'meaning': f"{running[0].get('bot_id')} is on “{running[0].get('title')}”.",
        })
    elif mode == 'active' and queued:
        items.append({
            'label': 'Queued',
            'meaning': f"{len(queued)} job(s) waiting.",
        })
    elif mode == 'completed' and completed:
        items.append({
            'label': 'Last result',
            'meaning': f"Completed “{completed.get('title')}” — open Why this result for the rationale.",
        })
    elif mode == 'failure' and failure:
        items.append({
            'label': 'Latest failure',
            'meaning': f"“{failure.get('title')}” — review Workstreams or re-run.",
        })
    if approvals and mode != 'blocker':
        items.append({
            'label': 'Also waiting',
            'meaning': f"{len(approvals)} approval(s) — open Approvals when ready.",
        })
    elif approvals:
        items.append({
            'label': 'Blocked on you',
            'meaning': f"{len(approvals)} approval(s) need a yes/no.",
        })
    return items


def _urls_from_trace(trace: list) -> list[str]:
    urls = []
    for t in trace:
        args = t.get('args') or {}
        res = t.get('result') or {}
        for blob in (args, res):
            if not isinstance(blob, dict):
                continue
            for k in ('url', 'watch', 'href'):
                u = blob.get(k)
                if isinstance(u, str) and u.startswith('http'):
                    urls.append(u)
            for r in blob.get('results') or []:
                if isinstance(r, dict) and isinstance(r.get('url'), str):
                    urls.append(r['url'])
    # unique preserve order
    out = []
    for u in urls:
        if u not in out:
            out.append(u)
    return out


def _youtube_from_trace(trace: list) -> dict | None:
    for t in reversed(trace):
        if t.get('tool') != 'youtube_transcript':
            continue
        res = t.get('result') or {}
        if res.get('ok') or res.get('video_id') or res.get('url'):
            return {
                'title': res.get('title'),
                'url': res.get('url'),
                'video_id': res.get('video_id'),
                'chars': res.get('chars'),
            }
    return None


def _duration_sec(job: dict) -> int | None:
    a = job.get('started_at') or job.get('created_at')
    b = job.get('finished_at') or job.get('updated_at')
    if not a or not b:
        return None
    try:
        def parse(x):
            x = str(x).replace('Z', '+00:00')
            return datetime.fromisoformat(x)
        return max(0, int((parse(b) - parse(a)).total_seconds()))
    except Exception:
        return None


def _fmt_duration(sec: int | None) -> str:
    if sec is None:
        return '—'
    if sec < 60:
        return f'{sec}s'
    m, s = divmod(sec, 60)
    if m < 60:
        return f'{m}m {s}s'
    h, m = divmod(m, 60)
    return f'{h}h {m}m'


def _read_md(path: Path) -> str:
    try:
        if path.is_file():
            return path.read_text(errors='replace')
    except Exception:
        pass
    return ''


def _first_bold(md: str) -> str:
    m = re.search(r'\*\*([^*]+)\*\*', md or '')
    return m.group(1).strip() if m else ''


def _first_productish_bold(md: str) -> str:
    """Skip label-like bold spans (I'd look at:) and prefer product names."""
    for m in re.finditer(r'\*\*([^*]+)\*\*', md or ''):
        t = m.group(1).strip().rstrip(':')
        low = t.lower()
        if low in ("i'd look at", 'id look at', 'where to start', 'ballpark on the page right now', 'video', 'link'):
            continue
        if len(t) < 8:
            continue
        return t
    return ''


def _labeled_value(md: str, label_re: str) -> str:
    """Match **Label:** value or Label: value (colon may sit inside the bold span)."""
    if not md:
        return ''
    pat = rf'(?im)^(?:\*\*)?\s*{label_re}\s*:?\s*(?:\*\*)?\s*:?\s*(.+)$'
    m = re.search(pat, md)
    if not m:
        return ''
    val = m.group(1).strip()
    val = re.sub(r'^\*+\s*', '', val)
    val = re.sub(r'\*+$', '', val).strip()
    val = re.sub(r'\*\*([^*]+)\*\*', r'\1', val)
    return val.strip()


def _md_bold_after(md: str, before_re: str) -> str:
    m = re.search(rf'(?is){before_re}\s+\*\*([^*]+)\*\*', md or '')
    return m.group(1).strip() if m else ''


def _quoted_after(md: str, before_re: str) -> str:
    m = re.search(rf'(?is){before_re}\s+[“\"]([^”\"]+)[”\"]', md or '')
    return m.group(1).strip() if m else ''


def _line_after(md: str, prefix: str) -> str:
    for line in (md or '').splitlines():
        if prefix.lower() in line.lower():
            parts = re.split(r':\s*', line, maxsplit=1)
            return (parts[-1] if parts else line).replace('**', '').strip()
    return ''


def _all_urls(text: str) -> list[str]:
    found = re.findall(r'https?://[^\s\)\]\>\"\']+', text or '')
    out = []
    for u in found:
        u = u.rstrip('.,;')
        if u not in out:
            out.append(u)
    return out


def _first_url(text: str, must_contain: str | None = None) -> str:
    for u in _all_urls(text):
        if must_contain and must_contain not in u:
            continue
        return u
    return ''


def _site_hosts(urls: list[str]) -> list[str]:
    out = []
    for u in urls:
        try:
            host = re.sub(r'^www\.', '', re.split(r'/', u.split('://', 1)[-1])[0])
        except Exception:
            continue
        if host and host not in out:
            out.append(host)
    return out


def _section(md: str, heading: str) -> str:
    if not md:
        return ''
    lines = md.splitlines()
    capture = False
    buf = []
    for line in lines:
        if re.match(rf'(?i)^#+\s*{re.escape(heading)}\b', line):
            capture = True
            continue
        if capture and re.match(r'^#+\s+', line):
            break
        if capture:
            buf.append(line)
    return '\n'.join(buf).strip()
