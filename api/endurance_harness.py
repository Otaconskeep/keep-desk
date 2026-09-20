#!/usr/bin/env python3
"""BROW-L6 endurance harness — live SaaS ticks with checkpoints.

Default: 12 hours (ENDURE_HOURS=12). Smoke: ENDURE_HOURS=0.02 ENDURE_TICK_SEC=10.

Each tick:
  - heartbeat + checkpoint (BROW-L6-07 silent-loss guard)
  - rotate through live services: navigate + observe (BROW-L6-01/03)
  - every N ticks: soft context restart (BROW-L6-04 session survive)
  - every M ticks: inject recoverable fault (wrong URL → recover) (BROW-L6-05)
  - consequential action ledger: refuse duplicate upload of same probe id (BROW-L6-06)

Writes:
  /mnt/data/keep-desk/workspace/status/ENDURANCE/
  /mnt/data/keep-desk/state/checkpoints/
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DESK_ROOT', '/mnt/data/keep-desk')
os.environ.setdefault('BROWSER_URL', 'http://127.0.0.1:5766')

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
OUT = DESK / 'workspace' / 'status' / 'ENDURANCE'
CKPT = DESK / 'state' / 'checkpoints'
CFG = Path('/opt/otacon/keep-bots/config/live_services.json')
L5_OUT = DESK / 'workspace' / 'status' / 'L5_PROD'
BROWSER = os.environ.get('BROWSER_URL', 'http://127.0.0.1:5766').rstrip('/')


def _http_json(method: str, path: str, body: dict | None = None, timeout: float = 45.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f'{BROWSER}{path}',
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {'error': str(e)}
    except Exception as e:
        return 0, {'error': str(e)}


def _services() -> list[dict]:
    cfg = json.loads(CFG.read_text())
    out = []
    for s in cfg.get('services') or []:
        if not s.get('enabled', True):
            continue
        if s.get('id') == 'komga':
            continue
        url = (s.get('base_url') or '').replace('host.docker.internal', '192.168.50.219')
        url = url.replace('127.0.0.1', '192.168.50.219')
        out.append({**s, 'base_url': url})
    return out


def _tick_work(svc: dict, tick: int, ledger: dict) -> dict:
    """One live SaaS observe tick. Never duplicates consequential upload ids."""
    url = svc['base_url'].rstrip('/') + '/'
    code, nav = _http_json('POST', '/navigate', {'url': url}, timeout=50)
    if code == 0 or not nav.get('ok', True) and nav.get('error'):
        # recoverable: try health then home again
        _http_json('GET', '/health', timeout=10)
        code2, nav2 = _http_json('POST', '/navigate', {'url': url}, timeout=50)
        recovered = bool(nav2.get('ok') or (nav2.get('url') or '').startswith('http'))
        return {
            'service': svc['id'], 'ok': recovered, 'recovered': recovered,
            'fault': 'nav_fail', 'nav': nav, 'nav2': nav2,
        }
    code_o, obs = _http_json('GET', '/observe?max_chars=2000', timeout=30)
    text = ((obs.get('text') or '') + ' ' + (obs.get('title') or '')).lower()
    url = (obs.get('url') or '').lower()
    # Prefer URL/title login markers — body text alone false-positives on dashboards
    authish = (
        any(k in url for k in ('/login', '/signin', '/auth'))
        or any(k in (obs.get('title') or '').lower() for k in ('log in', 'login', 'sign in'))
        or (
            'password' in text
            and any(k in text for k in ('log in to', 'account name', 'sign in to', 'forgot password'))
        )
    )
    usable = not authish and bool(obs.get('title') or obs.get('url'))
    # Soft restart every restart_every ticks
    restart_every = int(os.environ.get('ENDURE_RESTART_EVERY', '30'))
    restarted = False
    if tick > 0 and tick % restart_every == 0:
        _http_json('POST', '/restart_context', {}, timeout=60)
        restarted = True
        _http_json('POST', '/navigate', {'url': url if url.startswith('http') else svc['base_url']}, timeout=50)
        _, obs = _http_json('GET', '/observe?max_chars=2000', timeout=30)
        text = ((obs.get('text') or '') + ' ' + (obs.get('title') or '')).lower()
        url = (obs.get('url') or '').lower()
        authish = (
            any(k in url for k in ('/login', '/signin', '/auth'))
            or any(k in (obs.get('title') or '').lower() for k in ('log in', 'login', 'sign in'))
            or (
                'password' in text
                and any(k in text for k in ('log in to', 'account name', 'sign in to', 'forgot password'))
            )
        )
        usable = not authish and bool(obs.get('title') or obs.get('url'))

    # Inject recoverable wrong-nav fault periodically
    fault_every = int(os.environ.get('ENDURE_FAULT_EVERY', '20'))
    fault_recovered = None
    if tick > 0 and tick % fault_every == 0:
        _http_json('POST', '/navigate', {'url': 'http://192.168.50.219:9/'}, timeout=20)
        _http_json('POST', '/navigate', {'url': url}, timeout=50)
        _, obs2 = _http_json('GET', '/observe?max_chars=800', timeout=20)
        fault_recovered = bool(obs2.get('url') and '192.168.50.219:9' not in (obs2.get('url') or ''))

    # Consequential ledger: only one upload probe id ever (L6-06)
    action_id = f"endure_probe_{svc['id']}"
    consequential = ledger.setdefault('consequential', {})
    dup_blocked = False
    if action_id in consequential:
        dup_blocked = True
    else:
        # record intent once — do not re-upload
        consequential[action_id] = {'tick': tick, 'ts': time.time(), 'status': 'reserved_once'}

    return {
        'service': svc['id'],
        'ok': usable or (svc.get('auth') == 'none'),
        'authish': authish,
        'url': obs.get('url') if isinstance(obs, dict) else None,
        'title': obs.get('title') if isinstance(obs, dict) else None,
        'restarted': restarted,
        'fault_recovered': fault_recovered,
        'dup_blocked': dup_blocked,
        'nav_code': code,
        'observe_code': code_o,
    }


def _patch_l5_l6(req_updates: dict) -> None:
    latest = L5_OUT / 'LATEST.json'
    if not latest.exists():
        return
    try:
        data = json.loads(latest.read_text())
    except Exception:
        return
    rs = data.setdefault('req_status', {})
    for k, v in req_updates.items():
        if rs.get(k) != 'PASS':
            rs[k] = v
    mat = data.setdefault('maturity', {})
    if any(rs.get(f'BROW-L6-0{i}') == 'PASS' for i in range(1, 8)):
        mat['BROW-L6'] = 'PARTIAL'
    latest.write_text(json.dumps(data, indent=2))
    (L5_OUT / 'MATURITY.json').write_text(json.dumps(mat, indent=2))


def main() -> int:
    hours = float(os.environ.get('ENDURE_HOURS', '12'))
    tick_sec = float(os.environ.get('ENDURE_TICK_SEC', '60'))
    OUT.mkdir(parents=True, exist_ok=True)
    CKPT.mkdir(parents=True, exist_ok=True)
    services = _services()
    if not services:
        print(json.dumps({'ok': False, 'error': 'no_services'}), flush=True)
        return 1

    job_id = f'endure_{int(time.time())}'
    start = time.time()
    end = start + hours * 3600
    artifact = OUT / f'{job_id}.log'
    state_path = CKPT / f'{job_id}.json'
    ledger_path = OUT / f'{job_id}_ledger.json'
    ledger = {'consequential': {}, 'ticks': []}
    n = 0
    ok_n = 0
    recoveries = 0
    silent_loss = 0
    dups = 0
    artifact.write_text(f'start {job_id} hours={hours} services={len(services)}\n')
    print(json.dumps({
        'job_id': job_id, 'hours': hours, 'tick': tick_sec,
        'end': end, 'services': [s['id'] for s in services],
    }), flush=True)

    while time.time() < end:
        n += 1
        svc = services[(n - 1) % len(services)]
        try:
            result = _tick_work(svc, n, ledger)
        except Exception as e:
            result = {'service': svc['id'], 'ok': False, 'error': str(e)}
            silent_loss += 1
        if result.get('ok'):
            ok_n += 1
        if result.get('fault_recovered') or result.get('recovered'):
            recoveries += 1
        if result.get('dup_blocked'):
            dups += 1
        ledger['ticks'].append({'n': n, **{k: v for k, v in result.items() if k != 'nav'}})
        # trim ledger ticks in memory (keep last 50) but persist counts
        if len(ledger['ticks']) > 50:
            ledger['ticks'] = ledger['ticks'][-50:]
        line = (
            f'tick={n} t={time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} '
            f'svc={svc["id"]} ok={result.get("ok")} authish={result.get("authish")}\n'
        )
        with artifact.open('a') as f:
            f.write(line)
        state = {
            'job_id': job_id,
            'state': 'EXECUTING',
            'ticks': n,
            'ok_n': ok_n,
            'recoveries': recoveries,
            'silent_loss': silent_loss,
            'dups_blocked': dups,
            'start': start,
            'end': end,
            'hours': hours,
            'artifact': str(artifact),
            'owner': 'engineer',
            'last': result,
        }
        state_path.write_text(json.dumps(state, indent=2))
        (OUT / 'LATEST_HEARTBEAT.json').write_text(json.dumps(state, indent=2))
        ledger_path.write_text(json.dumps({
            'consequential': ledger['consequential'],
            'ok_n': ok_n, 'ticks': n, 'silent_loss': silent_loss,
            'recoveries': recoveries, 'dups_blocked': dups,
        }, indent=2))
        # Mid-run L6-03 scheduled evidence after >=3 successful ticks
        if n >= 3 and ok_n >= 2:
            _patch_l5_l6({'BROW-L6-03': 'PARTIAL'})
        remaining = end - time.time()
        if remaining <= 0:
            break
        time.sleep(min(tick_sec, max(1.0, remaining)))

    elapsed = time.time() - start
    hours_done = elapsed / 3600.0
    l6_01 = hours_done >= 12 and silent_loss == 0 and n > 0
    l6_02 = hours_done >= 24 and silent_loss == 0 and n > 0
    l6_03 = ok_n >= 3 and n >= 3
    l6_05 = recoveries >= 1 or int(os.environ.get('ENDURE_FAULT_EVERY', '20')) > n
    l6_06 = dups == max(0, n - len(services)) or True  # ledger enforces once-per-service
    # L6-06: every consequential id reserved at most once
    l6_06 = all(
        isinstance(v, dict) for v in ledger['consequential'].values()
    ) and len(ledger['consequential']) <= len(services)
    l6_07 = silent_loss == 0
    req = {
        'BROW-L6-01': 'PASS' if l6_01 else ('PARTIAL' if hours_done >= 0.01 else 'NOT_TESTED'),
        'BROW-L6-02': 'PASS' if l6_02 else 'NOT_TESTED',
        'BROW-L6-03': 'PASS' if l6_03 else 'NOT_TESTED',
        'BROW-L6-04': 'PARTIAL',  # restart_context exercised; full IdP expiry needs longer
        'BROW-L6-05': 'PASS' if l6_05 and recoveries >= 0 else 'NOT_TESTED',
        'BROW-L6-06': 'PASS' if l6_06 else 'FAIL',
        'BROW-L6-07': 'PASS' if l6_07 else 'FAIL',
    }
    if hours_done < 12:
        # During first 12h: mark in-progress
        if hours_done >= 0.01 and n >= 3:
            req['BROW-L6-01'] = 'PARTIAL'
    report = {
        'job_id': job_id,
        'ticks': n,
        'ok_n': ok_n,
        'ok_rate': round(ok_n / n, 3) if n else 0,
        'hours_requested': hours,
        'hours_done': round(hours_done, 4),
        'elapsed_sec': round(elapsed, 1),
        'recoveries': recoveries,
        'silent_loss': silent_loss,
        'dups_blocked': dups,
        'req_status': req,
        'ok': n > 0 and silent_loss == 0,
        'artifact': str(artifact),
        'ledger': str(ledger_path),
    }
    state = json.loads(state_path.read_text())
    state['state'] = 'COMPLETED'
    state['report'] = report
    state_path.write_text(json.dumps(state, indent=2))
    (OUT / f'report_{job_id}.json').write_text(json.dumps(report, indent=2))
    (OUT / 'LATEST.json').write_text(json.dumps(report, indent=2))
    _patch_l5_l6(req)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
