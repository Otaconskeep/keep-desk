#!/usr/bin/env python3
"""Gate A — Human session seeding (preferred path).

Bot never sees passwords/MFA codes.

Flow:
  open login URL in headed Chromium (Xvfb + x11vnc)
  ↓
  human connects over VNC and authenticates
  ↓
  human signals done
  ↓
  export Playwright storage_state into Keep Desk browser profile
  ↓
  restart keep-desk-browser so Computer API inherits session

Default Gate A services: nextcloud, portainer, files, qbittorrent, openwebui, romm

Usage:
  python3 /opt/otacon/keep-bots/api/gate_a_human_seed.py
  # VNC → 192.168.50.219:5901 (no password; bind LAN only)
  # After logging into each tab/site:
  touch /mnt/data/keep-desk/workspace/status/L5_PROD/HUMAN_DONE

Env:
  GATE_A_SERVICES=nextcloud,portainer,files,qbittorrent
  VNC_PORT=5901
  GATE_A_WAIT_SEC=1800
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
CFG = Path('/opt/otacon/keep-bots/config/live_services.json')
OUT = DESK / 'workspace' / 'status' / 'L5_PROD'
PROFILE_PW = DESK / 'browser-profile'
CHROMIUM_DIR = DESK / 'browser-chromium-human'
DONE = OUT / 'HUMAN_DONE'
STATUS = OUT / 'GATE_A_SEED.json'
VNC_PORT = int(os.environ.get('VNC_PORT', '5901'))
WAIT_SEC = int(os.environ.get('GATE_A_WAIT_SEC', '1800'))
DISPLAY_NUM = os.environ.get('GATE_A_DISPLAY', '99')
FB_W = int(os.environ.get('GATE_A_WIDTH', '1920'))
FB_H = int(os.environ.get('GATE_A_HEIGHT', '1080'))

GATE_A_DEFAULT = ['nextcloud', 'portainer', 'files', 'qbittorrent', 'openwebui', 'romm']


def _lan_url(url: str) -> str:
    return url.replace('host.docker.internal', '192.168.50.219').replace('127.0.0.1', '192.168.50.219')


def _pkill(patterns: list[str]) -> None:
    for p in patterns:
        subprocess.call(['pkill', '-f', p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_display() -> None:
    _pkill([f'Xvfb :{DISPLAY_NUM}', f'x11vnc.*{VNC_PORT}', 'chromium.*browser-chromium-human'])
    time.sleep(0.5)
    CHROMIUM_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        ['Xvfb', f':{DISPLAY_NUM}', '-screen', '0', f'{FB_W}x{FB_H}x24', '-ac', '+extension', 'RANDR'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.8)
    # Listen on all interfaces so LAN operator can connect; no VNC password
    # (session is short-lived seed — operator should firewall if paranoid)
    subprocess.Popen(
        [
            'x11vnc', '-display', f':{DISPLAY_NUM}', '-forever', '-shared',
            '-rfbport', str(VNC_PORT), '-nopw', '-listen', '0.0.0.0',
            # NEVER enable -ncache here: it multiplies RFB height (e.g. 1920x12960)
            # and noVNC scaleViewport shrinks the real desktop to a postage stamp.
            '-xkb',
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    # Browser-friendly noVNC (Firefox cannot open raw :5901 RFB)
    novnc_port = int(os.environ.get('NOVNC_PORT', '6080'))
    webroot = '/usr/share/novnc'
    if Path(webroot).is_dir() and Path('/usr/bin/websockify').exists():
        subprocess.call(['pkill', '-f', f'websockify.*{novnc_port}'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        subprocess.Popen(
            ['websockify', f'--web={webroot}', f'0.0.0.0:{novnc_port}', f'localhost:{VNC_PORT}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.4)


def open_chromium(urls: list[str]) -> subprocess.Popen:
    env = os.environ.copy()
    env['DISPLAY'] = f':{DISPLAY_NUM}'
    args = [
        'chromium',
        f'--user-data-dir={CHROMIUM_DIR}',
        '--no-first-run',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-session-crashed-bubble',
        '--disable-infobars',
        '--start-maximized',
        f'--window-size={FB_W},{FB_H}',
        '--window-position=0,0',
        '--force-device-scale-factor=1',
        '--remote-debugging-port=9222',
        '--restore-last-session',
    ] + urls
    return subprocess.Popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def export_storage_state() -> dict:
    """Pull cookies from human Chromium profile into Playwright storage_state.

    Prefer SQLite cookie export (no Playwright pip needed). CDP/persistent
    Playwright paths remain as optional fallbacks.
    """
    PROFILE_PW.mkdir(parents=True, exist_ok=True)
    # 1) Direct Chromium Cookies → storage_state (reliable on this host)
    try:
        from export_chromium_state import export_cookies
        cookies = export_cookies(CHROMIUM_DIR)
        state_path = PROFILE_PW / 'state.json'
        state_path.write_text(json.dumps({'cookies': cookies, 'origins': []}, indent=2))
        domains = sorted({c['domain'] for c in cookies})
        return {
            'ok': True,
            'path': str(state_path),
            'method': 'chromium_cookies_sqlite',
            'cookie_count': len(cookies),
            'domains': domains,
        }
    except Exception as e:
        cookie_err = str(e)

    state_path = PROFILE_PW / 'state.json'
    script = r'''
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
state_path = Path("/desk/browser-profile/state.json")
state_path.parent.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    try:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = browser.contexts[0]
        ctx.storage_state(path=str(state_path))
        browser.close()
        print(json.dumps({"ok": True, "path": str(state_path), "method": "cdp"}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "method": "cdp"}))
        sys.exit(1)
'''
    r = subprocess.run(
        [
            'docker', 'run', '--rm', '--network', 'host',
            '-v', f'{DESK}:/desk',
            'mcr.microsoft.com/playwright/python:v1.49.1-jammy',
            'bash', '-lc', 'pip install -q playwright==1.49.1 && python -c ' + repr(script),
        ],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode == 0 and r.stdout.strip():
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            pass
    return {
        'ok': False,
        'cookie_err': cookie_err,
        'cdp_stderr': (r.stderr or '')[-400:],
        'cdp_out': (r.stdout or '')[-400:],
    }


def verify_sessions(services: list[dict]) -> list[dict]:
    """Restart Keep Desk browser and verify auth walls cleared."""
    subprocess.call(['docker', 'restart', 'keep-desk-browser'], stdout=subprocess.DEVNULL)
    time.sleep(5)
    sys.path.insert(0, '/opt/otacon/keep-bots/api')
    os.environ.setdefault('BROWSER_URL', 'http://127.0.0.1:5766')
    from computer_use import Computer
    from l5_prod_gate import _authish

    out = []
    for s in services:
        cu = Computer(session_id=f'verify_{s["id"]}')
        nav = cu.navigate(s['base_url'])
        cu.wait(1.2)
        obs = cu.observe()
        authed = not _authish(obs) and 'chrome-error' not in (obs.get('url') or '')
        out.append({
            'id': s['id'],
            'ok': authed,
            'title': obs.get('title'),
            'url': obs.get('url'),
            'nav_ok': nav.get('ok') is not False,
        })
        print(f"  verify {s['id']}: {'AUTHED' if authed else 'STILL_AUTH_WALL'} title={obs.get('title')!r}")
    return out


def main() -> int:
    if DONE.exists():
        DONE.unlink()

    cfg = json.loads(CFG.read_text())
    want = [x.strip() for x in os.environ.get('GATE_A_SERVICES', ','.join(GATE_A_DEFAULT)).split(',') if x.strip()]
    by_id = {s['id']: s for s in cfg['services']}
    services = []
    for wid in want:
        if wid not in by_id:
            print(f'skip unknown service {wid}')
            continue
        s = dict(by_id[wid])
        s['base_url'] = _lan_url(s['base_url'])
        s['enabled'] = True
        services.append(s)

    if not services:
        print('No Gate A services selected')
        return 2

    urls = [s['base_url'] for s in services]
    print('=== Gate A — Human session seed ===')
    print('Services:', [s['id'] for s in services])
    print(f'Browser (noVNC): http://192.168.50.219:{os.environ.get("NOVNC_PORT", "6080")}/vnc.html'
          f'?host=192.168.50.219&port={os.environ.get("NOVNC_PORT", "6080")}&autoconnect=1&resize=scale')
    print(f'Raw VNC client: 192.168.50.219:{VNC_PORT}  (not HTTP — do not open in Firefox)')
    print('Log into each site in the Chromium window. Bot will NOT see credentials.')
    print(f'When done:  touch {DONE}')
    print(f'Waiting up to {WAIT_SEC}s …')

    start_display()
    proc = open_chromium(urls)
    t0 = time.time()
    while time.time() - t0 < WAIT_SEC:
        if DONE.exists():
            print('HUMAN_DONE detected')
            break
        time.sleep(2)
        if proc.poll() is not None:
            print('Chromium exited early — relaunching')
            proc = open_chromium(urls)
    else:
        print('Timeout waiting for HUMAN_DONE')
        STATUS.write_text(json.dumps({
            'ok': False, 'reason': 'timeout', 'services': [s['id'] for s in services],
        }, indent=2))
        _pkill([f'Xvfb :{DISPLAY_NUM}', f'x11vnc.*{VNC_PORT}', 'chromium.*browser-chromium-human'])
        return 1

    print('Exporting storage_state …')
    try:
        export = export_storage_state()
    except Exception as e:
        export = {'ok': False, 'error': str(e)}
        print('Export failed:', e)
        STATUS.write_text(json.dumps({'ok': False, 'export': export}, indent=2))
        _pkill([f'Xvfb :{DISPLAY_NUM}', f'x11vnc.*{VNC_PORT}', 'chromium.*browser-chromium-human'])
        return 1

    print('Export:', {k: export[k] for k in export if k != 'note'})
    _pkill([f'Xvfb :{DISPLAY_NUM}', f'x11vnc.*{VNC_PORT}', 'chromium.*browser-chromium-human'])

    print('Verifying via Keep Desk browser Computer API …')
    verified = verify_sessions(services)
    ok_n = sum(1 for v in verified if v.get('ok'))
    report = {
        'gate': 'A',
        'ok': ok_n >= max(4, len(services) // 2),  # at least 4 or half
        'ok_n': ok_n,
        'n': len(services),
        'export': export,
        'verified': verified,
        'credential_path': 'human_only_never_in_bot',
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    STATUS.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('ok', 'ok_n', 'n')}, indent=2))
    print('Wrote', STATUS)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
