#!/usr/bin/env python3
"""Export Chromium user-data-dir cookies → Playwright storage_state.json.

Does not require Playwright. Prefer this after human Gate A login.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

CHROMIUM_DIR = Path('/mnt/data/keep-desk/browser-chromium-human')
OUT = Path('/mnt/data/keep-desk/browser-profile/state.json')

# Chromium stores expires_utc as microseconds since 1601-01-01 UTC
CHROME_EPOCH_OFFSET = 11644473600  # seconds between 1601 and 1970


def chrome_expires_to_unix(expires_utc: int) -> float:
    if not expires_utc or expires_utc <= 0:
        return -1
    try:
        return expires_utc / 1_000_000 - CHROME_EPOCH_OFFSET
    except Exception:
        return -1


def export_cookies(profile: Path) -> list[dict]:
    cookies_db = profile / 'Default' / 'Cookies'
    if not cookies_db.exists():
        # newer chrome path
        alt = profile / 'Default' / 'Network' / 'Cookies'
        cookies_db = alt if alt.exists() else cookies_db
    if not cookies_db.exists():
        raise FileNotFoundError(f'no cookies db under {profile}')

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / 'Cookies'
        shutil.copy2(cookies_db, tmp)
        # journal optional
        for suf in ('-journal', '-wal', '-shm'):
            j = Path(str(cookies_db) + suf)
            if j.exists():
                shutil.copy2(j, Path(td) / ('Cookies' + suf))
        con = sqlite3.connect(tmp)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            'SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite '
            'FROM cookies'
        ).fetchall()
        con.close()

    out = []
    for r in rows:
        # samesite: 0=-1 unspecified, 1=no_restriction/None, 2=lax, 3=strict (varies by version)
        ss = r['samesite']
        if ss == 0:
            same = 'Lax'
        elif ss == 1:
            same = 'None'
        elif ss == 2:
            same = 'Lax'
        elif ss == 3:
            same = 'Strict'
        else:
            same = 'Lax'
        host = r['host_key'] or ''
        # Playwright wants domain without leading dot sometimes ok with dot
        out.append({
            'name': r['name'],
            'value': r['value'] or '',
            'domain': host,
            'path': r['path'] or '/',
            'expires': chrome_expires_to_unix(r['expires_utc']),
            'httpOnly': bool(r['is_httponly']),
            'secure': bool(r['is_secure']),
            'sameSite': same,
        })
    return out


def main() -> int:
    cookies = export_cookies(CHROMIUM_DIR)
    # Filter empty values? keep all — session cookies matter
    state = {'cookies': cookies, 'origins': []}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(state, indent=2))
    # summarize domains (no values)
    domains = sorted({c['domain'] for c in cookies})
    report = {
        'ok': True,
        'method': 'chromium_cookies_sqlite',
        'path': str(OUT),
        'cookie_count': len(cookies),
        'domains': domains,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    Path('/mnt/data/keep-desk/workspace/status/L5_PROD/GATE_A_EXPORT.json').write_text(
        json.dumps(report, indent=2) + '\n'
    )
    print(json.dumps(report, indent=2))
    return 0 if cookies else 1


if __name__ == '__main__':
    raise SystemExit(main())
