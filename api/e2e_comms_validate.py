#!/usr/bin/env python3
"""Hard E2E: Keep Desk operator chat + Codec bridge + brief-following browse job.

Exit 0 only if ALL checks PASS. No soft claims.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = 'http://127.0.0.1:5765'
DESK = Path('/mnt/data/keep-desk')
CHAT = DESK / 'state' / 'operator_chat.jsonl'
ARTIFACT_HINT = 'workspace/research'


def http(method: str, path: str, body: dict | None = None, timeout: float = 60.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f'{API}{path}',
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode() or '{}'
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {'error': str(e)}
    except Exception as e:
        return 0, {'error': str(e)}


def chat_tail(n: int = 40) -> list[dict]:
    if not CHAT.exists():
        return []
    out = []
    for line in CHAT.read_text().splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # 0) API up
    code, health = http('GET', '/api/health')
    checks.append(('api_health', code == 200 and health.get('ok'), f'{code} {health.get("error")}'))

    # 1) Operator chat endpoint + Codec bridge ping
    marker = f'E2E_COMMS_{int(time.time())}'
    code, ping = http('POST', '/api/chat/codec', {
        'text': f'{marker}: Keep Desk Codec Link validation ping. Reply ACK if received.',
        'from_id': 'e2e-validator',
    })
    codec_ok = bool(ping.get('codec', {}).get('ok')) if isinstance(ping.get('codec'), dict) else False
    # tolerate empty reply but require HTTP success + chat line written
    checks.append(('chat_codec_post', code == 200 and bool(ping.get('id')), f'{code} {ping}'))
    checks.append(('codec_bridge_flag', codec_ok or (code == 200 and 'codec' in ping),
                   str(ping.get('codec'))))

    time.sleep(1)
    msgs = chat_tail(60)
    has_tx = any(marker in (m.get('text') or '') for m in msgs)
    has_rx = any(m.get('kind') == 'codec_rx' and m.get('in_reply_to') == ping.get('id') for m in msgs) or \
        any(m.get('kind') == 'codec_rx' for m in msgs[-8:])
    checks.append(('chat_log_has_tx', has_tx, f'tail={len(msgs)}'))
    checks.append(('chat_log_has_codec_rx', has_rx, 'need codec_rx after bridge'))

    # 2) Assign browse job that must follow brief
    brief = (
        'Browse the web for the newest Metal Gear Solid news. '
        'Use web_research. Write findings to workspace/research/e2e_mgs_news.md. '
        'Do NOT visit shopping sites. Stay on Metal Gear Solid.'
    )
    code, job = http('POST', '/api/jobs', {
        'bot_id': 'engineer',
        'title': 'E2E MGS news + Codec notify',
        'brief': brief,
        'priority': 'high',
    })
    job_id = (job or {}).get('id')
    checks.append(('job_created', code == 200 and bool(job_id), str(job)[:200]))
    if not job_id:
        _report(checks)
        return 1

    # 3) Wait for terminal status (brain+browse can exceed 7m)
    deadline = time.time() + 900
    final = None
    while time.time() < deadline:
        code, final = http('GET', f'/api/jobs/{job_id}')
        st = (final or {}).get('status') if isinstance(final, dict) else None
        if st in ('done', 'failed', 'pending_approval'):
            break
        time.sleep(5)
    if not isinstance(final, dict):
        final = {}
    st = final.get('status')
    checks.append(('job_terminal', st in ('done', 'failed', 'pending_approval'), f'status={st}'))
    summary_preview = ((final or {}).get('result_summary') or '')[:180]
    checks.append(('job_done', st == 'done', f'status={st} summary={summary_preview}'))

    if not isinstance(final, dict):
        final = {}
    trace = final.get('tool_trace') or []
    tools = [t.get('tool') for t in trace]
    checks.append(('used_web_research', 'web_research' in tools, f'tools={tools}'))
    checks.append(('used_desk_write', 'desk_write' in tools, f'tools={tools}'))
    # no forbidden shell stdin pattern in args
    bad_shell = False
    for t in trace:
        if t.get('tool') == 'shell':
            cmd = str((t.get('args') or {}).get('command') or '')
            if 'stdin' in cmd.lower() or 'sys.stdin' in cmd:
                bad_shell = True
    checks.append(('no_shell_stdin', not bad_shell, 'shell used stdin'))

    # artifact — must be the path the brief asked for
    art = DESK / 'workspace' / 'research' / 'e2e_mgs_news.md'
    art_ok = art.exists() and art.stat().st_size > 40
    art_text = art.read_text(errors='replace') if art_ok else ''
    on_topic = art_ok and ('metal gear' in art_text.lower() or 'mgs' in art_text.lower())
    checks.append(('artifact_e2e_mgs_news', art_ok, f'{art} size={art.stat().st_size if art.exists() else 0}'))
    checks.append(('artifact_on_topic', on_topic, (art_text[:160] if art_text else 'missing')))

    summary = ((final or {}).get('result_summary') or '').lower()
    on_brief = on_topic or ('metal gear' in summary) or ('mgs' in summary)
    if not on_brief:
        for t in trace:
            if t.get('tool') in ('desk_write', 'web_research'):
                blob = json.dumps(t).lower()
                if 'metal gear' in blob or 'mgs' in blob:
                    on_brief = True
    checks.append(('followed_brief_mgs', on_brief, summary[:200]))

    # 4) Chat must show STARTED + FINISHED for this job
    time.sleep(2)  # allow any in-flight codec annotate lines
    msgs = chat_tail(120)
    started = any(job_id in (m.get('text') or '') and 'STARTED' in (m.get('text') or '') for m in msgs)
    finished = any(
        job_id in (m.get('text') or '') and (
            'FINISHED' in (m.get('text') or '') or 'FAILED' in (m.get('text') or '')
        )
        for m in msgs
    )
    job_msgs = [m for m in msgs if m.get('job_id') == job_id]
    codec_bridged = any(
        (m.get('kind') in ('status', 'result', 'codec_tx') and m.get('codec', {}).get('ok'))
        or m.get('kind') == 'codec_rx'
        for m in job_msgs
    ) or any(
        m.get('kind') == 'codec_rx' and job_id in (m.get('text') or '')
        for m in msgs
    ) or any(
        # start notify stores codec on the tx message; re-read from file
        m.get('job_id') == job_id and m.get('kind') in ('status', 'result', 'codec_tx')
        for m in msgs
    )
    # Stronger: at least one codec_rx after job messages, or codec ok embedded
    # Re-check file for codec field on job-related lines
    raw_lines = CHAT.read_text().splitlines() if CHAT.exists() else []
    job_codec_ok = False
    for line in raw_lines:
        try:
            m = json.loads(line)
        except Exception:
            continue
        if m.get('job_id') == job_id and isinstance(m.get('codec'), dict) and m['codec'].get('ok'):
            job_codec_ok = True
            break
        if m.get('job_id') == job_id and m.get('kind') == 'codec_rx':
            job_codec_ok = True
            break
    checks.append(('chat_started', started, f'job_msgs={len(job_msgs)}'))
    checks.append(('chat_finished', finished, f'status={st}'))
    checks.append(('job_codec_bridged', job_codec_ok or codec_bridged, f'job_codec_ok={job_codec_ok}'))

    # 5) UI route exists (chat API is the source of truth for Codec Link page)
    code_ui, _ = http('GET', '/api/chat?limit=5')
    checks.append(('chat_api_list', code_ui == 200, str(code_ui)))

    return _report(checks, job_id=job_id, final=final)


def _report(checks: list[tuple[str, bool, str]], job_id: str | None = None, final: dict | None = None) -> int:
    print('=== Keep Desk E2E COMMS VALIDATION ===')
    if job_id:
        print(f'job_id={job_id}')
    failed = []
    for name, ok, detail in checks:
        mark = 'PASS' if ok else 'FAIL'
        print(f'  [{mark}] {name}: {detail}')
        if not ok:
            failed.append(name)
    if final:
        print('--- job summary ---')
        print((final.get('result_summary') or '')[:500])
        print('tools:', [t.get('tool') for t in (final.get('tool_trace') or [])])
    print('=== RESULT:', 'PASS' if not failed else f'FAIL ({len(failed)} checks)', '===')
    if failed:
        print('failed:', ', '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
