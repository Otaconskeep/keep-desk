"""Generalized computer-use API — agents must use this, not site-specific scripts.

Actions: observe, click, type, scroll, navigate, download, upload, wait, extract, verify,
screenshot, dismiss_overlays, wait_for, tab_*, click_text, restart_context
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

DESK = Path(os.environ.get('DESK_ROOT', '/desk')).resolve()
BROWSER = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')
TRACE_DIR = DESK / 'workspace' / 'computer_use_traces'
DL_DIR = DESK / 'workspace' / 'downloads'
TRACE_DIR.mkdir(parents=True, exist_ok=True)
DL_DIR.mkdir(parents=True, exist_ok=True)


def _http(method: str, path: str, body: dict | None = None, timeout: int = 90) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f'{BROWSER}{path}', data=data, method=method,
        headers={'Content-Type': 'application/json'} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class Computer:
    """Session-scoped computer-use handle with action trace."""

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f'cu_{int(time.time())}'
        self.trace: list[dict] = []
        self.trace_path = TRACE_DIR / f'{self.session_id}.jsonl'
        self.recovery_count = 0
        self.wrong_page_events = 0
        self.human_interventions = 0

    def _log(self, action: str, args: dict, result: Any) -> dict:
        entry = {
            'ts': time.time(),
            'action': action,
            'args': args,
            'ok': not (isinstance(result, dict) and result.get('error')),
            'result_summary': (
                {k: result[k] for k in list(result)[:8]} if isinstance(result, dict) else str(result)[:200]
            ),
        }
        self.trace.append(entry)
        with self.trace_path.open('a') as f:
            f.write(json.dumps(entry) + '\n')
        return result if isinstance(result, dict) else {'value': result}

    def navigate(self, url: str) -> dict:
        return self._log('navigate', {'url': url}, _http('POST', '/navigate', {'url': url}))

    def observe(self, max_chars: int = 12000) -> dict:
        return self._log('observe', {}, _http('GET', f'/content?max_chars={max_chars}'))

    def click(self, selector: str) -> dict:
        return self._log('click', {'selector': selector}, _http('POST', '/click', {'selector': selector}))

    def type(self, selector: str, text: str) -> dict:
        return self._log('type', {'selector': selector, 'text': text},
                         _http('POST', '/type', {'selector': selector, 'text': text}))

    def screenshot(self, name: str = 'shot.png') -> dict:
        return self._log('screenshot', {'name': name}, _http('POST', '/screenshot', {'name': name}))

    def wait(self, seconds: float = 1.0) -> dict:
        time.sleep(seconds)
        return self._log('wait', {'seconds': seconds}, {'ok': True})

    def extract(self, marker_start: str | None = None, marker_end: str | None = None) -> dict:
        obs = self.observe()
        text = obs.get('text') or ''
        if marker_start and marker_start in text:
            text = text.split(marker_start, 1)[1]
        if marker_end and marker_end in text:
            text = text.split(marker_end, 1)[0]
        return self._log('extract', {'marker_start': marker_start}, {'text': text.strip()[:8000]})

    def download(self, url: str, filename: str | None = None) -> dict:
        """Download via HTTP into desk downloads/ (browser computer adjunct)."""
        name = filename or url.rstrip('/').split('/')[-1] or 'download.bin'
        safe = ''.join(c for c in name if c.isalnum() or c in '._-') or 'download.bin'
        dest = DL_DIR / safe
        urllib.request.urlretrieve(url, dest)
        h = hashlib.sha256(dest.read_bytes()).hexdigest()
        return self._log('download', {'url': url}, {
            'ok': True, 'path': f'workspace/downloads/{safe}',
            'sha256': h, 'bytes': dest.stat().st_size,
        })

    def upload_file_field(self, selector: str, path: str) -> dict:
        """Set an <input type=file> via Playwright set_input_files through browser API."""
        # Browser container mounts desk at /desk — always send container path
        rel = path.lstrip('/')
        if rel.startswith('desk/'):
            rel = rel[5:]
        if Path(path).is_absolute() and str(Path(path).resolve()).startswith(str(DESK)):
            rel = str(Path(path).resolve().relative_to(DESK))
        container_path = f'/desk/{rel}'
        try:
            r = _http('POST', '/upload', {'selector': selector, 'path': container_path})
        except Exception as e:
            r = {'error': str(e)}
        return self._log('upload', {'selector': selector, 'path': path}, r)

    def verify(self, predicate: str, value: str | None = None) -> dict:
        """predicate: contains | title_is | url_contains"""
        obs = self.observe()
        ok = False
        if predicate == 'contains':
            ok = (value or '') in (obs.get('text') or '')
        elif predicate == 'title_is':
            ok = (obs.get('title') or '') == (value or '')
        elif predicate == 'url_contains':
            ok = (value or '') in (obs.get('url') or '')
        return self._log('verify', {'predicate': predicate, 'value': value}, {'ok': ok, 'obs_title': obs.get('title')})

    def scroll(self, dy: int = 400) -> dict:
        try:
            r = _http('POST', '/scroll', {'dy': dy})
        except Exception as e:
            r = {'error': str(e), 'note': 'scroll endpoint optional'}
        return self._log('scroll', {'dy': dy}, r)

    def observe_controls(self, max_chars: int = 12000) -> dict:
        try:
            r = _http('GET', f'/observe?max_chars={max_chars}')
        except Exception as e:
            base = self.observe(max_chars)
            r = {**base, 'controls': [], 'error': str(e)}
        return self._log('observe_controls', {}, r)

    def dismiss_overlays(self) -> dict:
        try:
            r = _http('POST', '/dismiss_overlays', {})
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('dismiss_overlays', {}, r)

    def wait_for(self, selector: str | None = None, text: str | None = None, timeout_ms: int = 15000) -> dict:
        try:
            r = _http('POST', '/wait_for', {
                'selector': selector, 'text': text, 'timeout_ms': timeout_ms,
            })
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('wait_for', {'selector': selector, 'text': text}, r)

    def click_text(self, text: str) -> dict:
        try:
            r = _http('POST', '/click_text', {'text': text})
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('click_text', {'text': text}, r)

    def tab_new(self, url: str | None = None) -> dict:
        try:
            r = _http('POST', '/tab/new', {'url': url})
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('tab_new', {'url': url}, r)

    def tab_switch(self, index: int) -> dict:
        try:
            r = _http('POST', '/tab/switch', {'index': index})
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('tab_switch', {'index': index}, r)

    def tabs(self) -> dict:
        try:
            r = _http('GET', '/tabs')
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('tabs', {}, r)

    def restart_context(self) -> dict:
        try:
            r = _http('POST', '/restart_context', {})
        except Exception as e:
            r = {'ok': False, 'error': str(e)}
        return self._log('restart_context', {}, r)

    def metrics(self) -> dict:
        return {
            'actions': len(self.trace),
            'recovery_count': self.recovery_count,
            'wrong_page_events': self.wrong_page_events,
            'human_interventions': self.human_interventions,
            'timeouts': sum(1 for t in self.trace if 'timeout' in str(t.get('result_summary', '')).lower()),
            'failures': sum(1 for t in self.trace if not t.get('ok')),
        }
