"""Keep Bots API — LOCAL-ONLY Grok Bot control plane on OtaconsKeep / RTX 3090."""
from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from brain import Brain
from seed import seed
from store import Store

STATE_DIR = os.environ.get('STATE_DIR', '/desk/state')
STATIC = Path(__file__).parent / 'static'

app = FastAPI(
    title='Keep Desk',
    version='0.2.0',
    description='Local-only Grok Bot analogue — RTX 3090 / Ollama, no cloud APIs',
)
store = Store(STATE_DIR)


@app.on_event('startup')
def _startup():
    seed(STATE_DIR)


class BotIn(BaseModel):
    id: str = Field(..., pattern=r'^[a-z][a-z0-9_]{1,31}$')
    name: str
    role: str
    mandate: str
    color: str = '#adb5bd'


class JobIn(BaseModel):
    bot_id: str = ''
    title: str
    brief: str
    priority: str = 'normal'
    thread_id: str | None = None
    auto_route: bool = True


class HandoffIn(BaseModel):
    from_bot: str
    to_bot: str
    job_id: str
    message: str


class RoutineIn(BaseModel):
    bot_id: str
    name: str
    cron: str
    brief: str
    skill_id: str | None = None


class ApprovalResolve(BaseModel):
    approve: bool
    resolved_by: str = 'operator'


class ThreadIn(BaseModel):
    title: str
    bot_ids: list[str]
    opener: str = ''


class ThreadPostIn(BaseModel):
    from_id: str = 'operator'
    text: str


class GroupAssignIn(BaseModel):
    brief: str


class SkillIn(BaseModel):
    name: str
    description: str
    steps: list[str]
    bot_id: str = 'operator'


class OperatorChatIn(BaseModel):
    text: str
    codec: bool = False
    from_id: str = 'operator'


@app.get('/api/health')
def health():
    brain_info = {}
    try:
        brain_info = Brain().info()
    except Exception as e:
        brain_info = {'error': str(e)}
    return {
        'ok': True,
        'service': 'keep-bots',
        'host': 'otaconskeep',
        'mode': 'local_only',
        'brain': brain_info,
        'bots': len(store.list_bots()),
        'queued': len(store.list_jobs(status='queued')),
        'running': len(store.list_jobs(status='running')),
        'pending_approvals': len(store.list_approvals(status='pending')),
        'skills': len(store.list_skills()),
        'threads': len(store.list_threads()),
        'routines': len(store.list_routines()),
    }


def _desk() -> Path:
    return Path(os.environ.get('DESK_ROOT', '/desk'))


def _http_json(url: str, method: str = 'GET', body: dict | None = None, timeout: float = 20.0):
    import json as _json
    import urllib.error
    import urllib.request
    data = None if body is None else _json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode() or '{}'
            return r.status, _json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, _json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {'error': str(e)}
    except Exception as e:
        return 0, {'error': str(e)}


@app.get('/api/mission')
def mission():
    """Mission Control aggregate — L5/L6 + checkpoints + claimable if present."""
    import json as _json
    desk = _desk()
    status = desk / 'workspace' / 'status'
    l5 = {}
    endurance = {}
    claimable = None
    checkpoints: list[str] = []
    try:
        latest = status / 'L5_PROD' / 'LATEST.json'
        if latest.exists():
            l5 = _json.loads(latest.read_text())
    except Exception:
        l5 = {}
    try:
        hb = status / 'ENDURANCE' / 'LATEST_HEARTBEAT.json'
        if hb.exists():
            endurance = _json.loads(hb.read_text())
    except Exception:
        endurance = {}
    try:
        score = status / 'COMPLIANCE_SCORE.json'
        if score.exists():
            sc = _json.loads(score.read_text())
            claimable = sc.get('CLAIMABLE_SCORE', sc.get('claimable'))
    except Exception:
        pass
    ckpt_dir = desk / 'state' / 'browser_auth_checkpoints'
    if ckpt_dir.is_dir():
        checkpoints = sorted([p.name for p in ckpt_dir.iterdir() if p.is_file()])[-12:]
    return {
        'ok': True,
        'l5': {
            'gate_pass': l5.get('gate_pass'),
            'rates': l5.get('rates'),
            'req_status': l5.get('req_status'),
            'maturity': l5.get('maturity'),
        },
        'endurance': {
            'job_id': endurance.get('job_id'),
            'state': endurance.get('state'),
            'ticks': endurance.get('ticks'),
            'ok_n': endurance.get('ok_n'),
            'hours': endurance.get('hours'),
        },
        'claimable': claimable,
        'checkpoints': checkpoints,
    }


@app.get('/api/briefing')
def briefing():
    """Plain-language AI operator report — primary Command Deck surface."""
    from briefing import build_briefing
    from chat_bus import list_messages
    m = mission()
    return build_briefing(
        store=store,
        mission=m,
        chat_messages=list_messages(limit=40),
    )


@app.get('/api/browser/health')
def browser_health():
    base = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')
    code, data = _http_json(f'{base}/health')
    return data if code else {'ok': False, **data}


@app.get('/api/browser/observe')
def browser_observe(max_chars: int = 4000):
    base = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')
    code, data = _http_json(f'{base}/observe?max_chars={max_chars}')
    if not code:
        raise HTTPException(502, data.get('error', 'browser unreachable'))
    return data


@app.post('/api/browser/screenshot')
def browser_screenshot():
    base = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')
    code, data = _http_json(f'{base}/screenshot', method='POST', body={'name': 'command_deck.png'}, timeout=45)
    if not code or not data.get('ok'):
        raise HTTPException(502, data.get('error', 'screenshot failed'))
    return data


@app.get('/api/desk/file')
def desk_file(path: str):
    """Serve a file under /desk (screenshots, evidence)."""
    desk = _desk().resolve()
    rel = path.lstrip('/')
    if rel.startswith('desk/'):
        rel = rel[5:]
    target = (desk / rel).resolve()
    if not str(target).startswith(str(desk)) or not target.is_file():
        raise HTTPException(404, 'not found')
    return FileResponse(target)


@app.get('/api/memory')
def memory_index():
    import time as _time
    desk = _desk()
    mem = desk / 'memory'
    bots = sorted([p.name for p in mem.iterdir() if p.is_dir()]) if mem.is_dir() else []
    status = desk / 'workspace' / 'status'
    evidence = []
    if status.is_dir():
        for p in sorted(status.rglob('*'), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
            if not p.is_file():
                continue
            if p.suffix.lower() not in ('.json', '.txt', '.log', '.sha256', '.png'):
                continue
            evidence.append({
                'name': str(p.relative_to(status)),
                'kind': p.parent.name,
                'mtime': _time.strftime('%Y-%m-%d %H:%M', _time.localtime(p.stat().st_mtime)),
            })
            if len(evidence) >= 40:
                break
    return {
        'bot_dirs': len(bots),
        'bots': bots,
        'evidence_n': len(evidence),
        'evidence': evidence,
    }


@app.get('/api/browser/viewport.png')
def browser_viewport_png():
    """Live PNG proxy for Command Deck watch mode."""
    import urllib.request
    from fastapi.responses import Response
    base = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')
    try:
        with urllib.request.urlopen(f'{base}/viewport.png', timeout=30) as r:
            data = r.read()
        return Response(
            content=data,
            media_type='image/png',
            headers={'Cache-Control': 'no-store, no-cache, must-revalidate'},
        )
    except Exception as e:
        raise HTTPException(502, f'viewport: {e}') from e


@app.get('/api/bots')
def list_bots():
    return {'bots': store.list_bots()}


@app.post('/api/bots')
def create_bot(body: BotIn):
    if store.get_bot(body.id):
        raise HTTPException(400, 'bot id exists')
    return store.upsert_bot(body.model_dump())


@app.get('/api/jobs')
def list_jobs(bot_id: str | None = None, status: str | None = None):
    return {'jobs': store.list_jobs(bot_id=bot_id, status=status)}


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404, 'job not found')
    return job


@app.post('/api/jobs')
def create_job(body: JobIn):
    from bot_route import route_bot
    bot_id = (body.bot_id or '').strip()
    if body.auto_route or not bot_id:
        bot_id = route_bot(
            f'{body.title}\n{body.brief}',
            bots=store.list_bots(),
        )
    if not store.get_bot(bot_id):
        raise HTTPException(400, f'unknown bot {bot_id}')
    job = store.create_job(
        bot_id=bot_id,
        title=body.title,
        brief=body.brief,
        priority=body.priority,
        thread_id=body.thread_id,
    )
    from job_batches import expand_into_pipeline, should_batch
    if should_batch(job.get('title') or '', job.get('brief') or ''):
        job = expand_into_pipeline(store, job)
        stages = job.get('stage_total') or 1
        return {
            **job,
            'batched': True,
            'routed_bot': bot_id,
            'batch_note': f'Split into {stages} sequential stages so each batch can finish cleanly.',
        }
    return {**job, 'routed_bot': bot_id}


@app.post('/api/jobs/{job_id}/retry')
def retry_job(job_id: str):
    """Re-queue parent brief as a NEW namespaced pipeline (never reuse poisoned paths)."""
    src = store.get_job(job_id)
    if not src:
        raise HTTPException(404, 'job not found')
    if src.get('status') in ('running', 'queued'):
        raise HTTPException(409, 'job is still active — wait or cancel first')
    title = (src.get('parent_title') or src.get('title') or 'Untitled').strip()
    brief = (src.get('parent_brief') or src.get('brief') or title).strip()
    # Never retry a STAGE shell as-is — unwrap to parent goal
    if brief.startswith('STAGE '):
        m = re.search(
            r'Parent goal[^:]*:\s*\n(.*?)(?:\n\nThis stage focus:|\Z)',
            brief,
            re.S | re.I,
        )
        if m and m.group(1).strip():
            brief = m.group(1).strip()
        elif src.get('parent_brief'):
            brief = src['parent_brief'].strip()
    title = re.sub(r'\s·\s\d+/\d+\s·.*$', '', title).strip()
    title = re.sub(r'\s*\(retry\)\s*$', '', title, flags=re.I).strip()
    if not title.lower().endswith('(retry)'):
        title = f'{title} (retry)'
    # Prefer auto-route again on retry
    from bot_route import route_bot
    bot_id = route_bot(f'{title}\n{brief}', bots=store.list_bots()) or src['bot_id']
    job = store.create_job(
        bot_id=bot_id,
        title=title[:160],
        brief=brief,
        priority=src.get('priority') or 'normal',
        created_by='operator_retry',
        thread_id=src.get('thread_id'),
    )
    store.append_job_log(job['id'], f"retry_of {job_id} clean_namespace")
    from job_batches import expand_into_pipeline, should_batch
    if should_batch(job.get('title') or '', job.get('brief') or ''):
        job = expand_into_pipeline(store, job)
    return {
        'ok': True,
        'job': job,
        'retry_of': job_id,
        'batched': bool(job.get('pipeline_id')),
        'research_dir': job.get('research_dir'),
        'routed_bot': bot_id,
    }


@app.get('/api/handoffs')
def list_handoffs(to_bot: str | None = None):
    return {'handoffs': store.list_handoffs(to_bot=to_bot)}


@app.post('/api/handoffs')
def create_handoff(body: HandoffIn):
    if not store.get_bot(body.from_bot) or not store.get_bot(body.to_bot):
        raise HTTPException(400, 'unknown bot')
    return store.create_handoff(**body.model_dump())


@app.get('/api/routines')
def list_routines():
    return {'routines': store.list_routines()}


@app.post('/api/routines')
def create_routine(body: RoutineIn):
    if not store.get_bot(body.bot_id):
        raise HTTPException(400, 'unknown bot')
    try:
        return store.create_routine(**body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get('/api/approvals')
def list_approvals(status: str | None = 'pending'):
    return {'approvals': store.list_approvals(status=status)}


@app.post('/api/approvals/{approval_id}/resolve')
def resolve_approval(approval_id: str, body: ApprovalResolve):
    item = store.resolve_approval(approval_id, approve=body.approve, resolved_by=body.resolved_by)
    if not item:
        raise HTTPException(404, 'approval not found')
    return item


@app.get('/api/skills')
def list_skills():
    return {'skills': store.list_skills()}


@app.post('/api/skills')
def create_skill(body: SkillIn):
    return store.save_skill(
        name=body.name, description=body.description,
        steps=body.steps, bot_id=body.bot_id,
    )


@app.get('/api/threads')
def list_threads():
    return {'threads': store.list_threads()}


@app.post('/api/threads')
def create_thread(body: ThreadIn):
    for b in body.bot_ids:
        if not store.get_bot(b):
            raise HTTPException(400, f'unknown bot {b}')
    return store.create_thread(title=body.title, bot_ids=body.bot_ids, opener=body.opener)


@app.post('/api/threads/{thread_id}/post')
def post_thread(thread_id: str, body: ThreadPostIn):
    t = store.post_thread(thread_id, from_id=body.from_id, text=body.text)
    if not t:
        raise HTTPException(404, 'thread not found')
    return t


@app.post('/api/threads/{thread_id}/assign')
def assign_thread(thread_id: str, body: GroupAssignIn):
    if not store.get_thread(thread_id):
        raise HTTPException(404, 'thread not found')
    jobs = store.spawn_group_jobs(thread_id, body.brief)
    return {'jobs': jobs}


@app.get('/api/chat')
def list_operator_chat(limit: int = 80, since_id: str | None = None):
    from chat_bus import list_messages
    return {'messages': list_messages(limit=min(limit, 200), since_id=since_id)}


@app.post('/api/chat')
def post_operator_chat(body: OperatorChatIn):
    from chat_bus import post_message
    if not (body.text or '').strip():
        raise HTTPException(400, 'empty text')
    return post_message(
        from_id=body.from_id or 'operator',
        text=body.text.strip(),
        kind='chat',
        codec=bool(body.codec),
    )


@app.post('/api/chat/codec')
def post_codec_bridge(body: OperatorChatIn):
    """Force a Codec-bridged transmission from the Command Deck."""
    from chat_bus import post_message
    if not (body.text or '').strip():
        raise HTTPException(400, 'empty text')
    return post_message(
        from_id=body.from_id or 'operator',
        text=body.text.strip(),
        kind='codec_tx',
        codec=True,
    )


@app.get('/', response_class=HTMLResponse)
def index():
    """SSR home — embed last briefing so first paint is never empty Standing by."""
    html = (STATIC / 'index.html').read_text(encoding='utf-8')
    boot = 'null'
    try:
        from briefing import build_briefing
        from chat_bus import list_messages
        payload = build_briefing(
            store=store,
            mission=mission(),
            chat_messages=list_messages(limit=20),
        )
        import json
        boot = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    except Exception as e:
        boot = json.dumps({'ok': False, 'error': str(e)[:200]}).replace('<', '\\u003c')
    marker = '<script id="keep-boot" type="application/json">null</script>'
    if marker in html:
        html = html.replace(
            marker,
            f'<script id="keep-boot" type="application/json">{boot}</script>',
            1,
        )
    return HTMLResponse(html)


if STATIC.is_dir():
    app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')
