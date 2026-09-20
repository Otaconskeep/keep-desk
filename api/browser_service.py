"""Keep Desk browser computer — general-purpose work environment (not site adapters)."""
from __future__ import annotations

import base64
import os
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DESK = Path(os.environ.get('DESK_ROOT', '/desk')).resolve()
PROFILE = DESK / 'browser-profile'
SHOTS = DESK / 'workspace' / 'screenshots'
DL = DESK / 'workspace' / 'downloads'
PROFILE.mkdir(parents=True, exist_ok=True)
SHOTS.mkdir(parents=True, exist_ok=True)
DL.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='Keep Desk Browser')
_lock = threading.Lock()
_cmd_q: queue.Queue = queue.Queue()
_owner_started = False


def _owner_loop():
    """Single thread owns Playwright sync API (avoids greenlet cross-thread crashes)."""
    while True:
        item = _cmd_q.get()
        if item is None:
            break
        fn, fut = item
        try:
            fut.set_result(fn())
        except BaseException as e:
            fut.set_exception(e)


def pw(fn, timeout: float = 120):
    global _owner_started
    import concurrent.futures
    if not _owner_started:
        with _lock:
            if not _owner_started:
                threading.Thread(target=_owner_loop, name='playwright-owner', daemon=True).start()
                _owner_started = True
    fut = concurrent.futures.Future()
    _cmd_q.put((fn, fut))
    return fut.result(timeout=timeout)

_pw = None
_browser = None
_context = None
_pages: list = []
_active = 0

# Generic overlay dismiss candidates (NOT site-specific workflows)
_DISMISS_TEXTS = (
    'Accept', 'Accept all', 'Accept All', 'I agree', 'Agree', 'OK', 'Got it',
    'Close', 'Dismiss', 'Allow all', 'Accept cookies', 'Accept Cookies',
)


def _ensure():
    global _pw, _browser, _context, _pages, _active
    if _pages:
        # Drop dead pages
        alive = []
        for p in _pages:
            try:
                _ = p.url
                alive.append(p)
            except Exception:
                pass
        _pages = alive
        if _pages:
            _active = min(_active, len(_pages) - 1)
            return
    from playwright.sync_api import sync_playwright
    if _pw is None:
        _pw = sync_playwright().start()
    if _browser is None or not _browser.is_connected():
        headless = os.environ.get('BROWSER_HEADLESS', '1') != '0'
        _browser = _pw.chromium.launch(
            headless=headless,
            args=['--disable-blink-features=AutomationControlled'],
        )
    _context = _browser.new_context(
        storage_state=str(PROFILE / 'state.json') if (PROFILE / 'state.json').exists() else None,
        viewport={'width': 1280, 'height': 800},
        accept_downloads=True,
        # Realistic UA — bot UA gets blocked/captcha'd on Google etc.
        user_agent=(
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
        locale='en-US',
    )
    page = _context.new_page()
    _pages = [page]
    _active = 0


def _page():
    _ensure()
    return _pages[_active]


def _persist():
    try:
        _context.storage_state(path=str(PROFILE / 'state.json'))
    except Exception:
        pass


def _live_shot(page=None) -> dict:
    """Refresh workspace/screenshots/live.png for Command Deck watch mode."""
    try:
        p = page or _page()
        live = SHOTS / 'live.png'
        p.screenshot(path=str(live), full_page=False)
        return {'ok': True, 'path': 'workspace/screenshots/live.png', 'bytes': live.stat().st_size}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


class NavIn(BaseModel):
    url: str


class SelIn(BaseModel):
    selector: str


class TypeIn(BaseModel):
    selector: str
    text: str
    clear: bool = True


class ShotIn(BaseModel):
    name: str = 'shot.png'


class UploadIn(BaseModel):
    selector: str
    path: str


class ScrollIn(BaseModel):
    dy: int = 400


class WaitIn(BaseModel):
    selector: str | None = None
    text: str | None = None
    timeout_ms: int = 15000


class TabIn(BaseModel):
    index: int | None = None
    url: str | None = None


@app.get('/health')
def health():
    return {
        'ok': True,
        'service': 'keep-desk-browser',
        'profile': str(PROFILE),
        'tabs': len(_pages),
        'active': _active,
        'state_file': (PROFILE / 'state.json').exists(),
        'live_shot': (SHOTS / 'live.png').exists(),
    }


@app.get('/viewport.png')
def viewport_png():
    """Raw PNG of current page — Command Deck live watch."""
    from fastapi.responses import Response
    def _op():
        try:
            p = _page()
            data = p.screenshot(type='png', full_page=False)
            (SHOTS / 'live.png').write_bytes(data)
            return Response(
                content=data,
                media_type='image/png',
                headers={'Cache-Control': 'no-store, no-cache, must-revalidate'},
            )
        except Exception as e:
            raise HTTPException(500, str(e)) from e


    return pw(_op)
NOSIGNAL_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>NO SIGNAL</title>
<style>
html,body{margin:0;height:100%;background:#05070c;overflow:hidden;font-family:monospace}
canvas{width:100%;height:100%;display:block;image-rendering:pixelated}
.badge{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);
letter-spacing:.35em;color:rgba(94,200,255,.85);text-shadow:0 0 12px rgba(94,200,255,.5);
border:1px solid rgba(94,200,255,.35);padding:.75rem 1.25rem;background:rgba(0,0,0,.55)}
</style></head><body>
<canvas id="c"></canvas><div class="badge">NO SIGNAL</div>
<script>
const c=document.getElementById('c'),ctx=c.getContext('2d');
function resize(){c.width=Math.min(640,innerWidth);c.height=Math.min(400,innerHeight)}
resize();addEventListener('resize',resize);
(function snow(){const w=c.width,h=c.height,img=ctx.createImageData(w,h),d=img.data;
for(let i=0;i<d.length;i+=4){const v=(Math.random()*60)|0;d[i]=d[i+1]=d[i+2]=v;d[i+3]=255}
ctx.putImageData(img,0,0);requestAnimationFrame(snow)})();
</script></body></html>"""


@app.post('/park')
def park_nosignal():
    """Park viewport on local NO SIGNAL snow — no network, never leave example.com as LIVE."""
    def _op():
        try:
            p = _page()
            p.set_content(NOSIGNAL_HTML, wait_until='domcontentloaded')
            _persist()
            shot = _live_shot(p)
            return {'ok': True, 'url': 'about:blank#nosignal', 'title': 'NO SIGNAL', 'live': shot}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    return pw(_op)


@app.post('/navigate')
def navigate(body: NavIn):
    if not body.url.startswith(('http://', 'https://')):
        raise HTTPException(400, 'http(s) only')
    def _op():
        try:
            p = _page()
            p.goto(body.url, wait_until='domcontentloaded', timeout=60000)
            try:
                p.wait_for_load_state('networkidle', timeout=8000)
            except Exception:
                pass
            _persist()
            shot = _live_shot(p)
            return {'ok': True, 'url': p.url, 'title': p.title(), 'live': shot}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


    return pw(_op)
@app.post('/click')
def click(body: SelIn):
    def _op():
        try:
            p = _page()
            p.click(body.selector, timeout=15000)
            _persist()
            return {'ok': True, 'url': p.url}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


    return pw(_op)
@app.post('/type')
def type_text(body: TypeIn):
    def _op():
        try:
            p = _page()
            if body.clear:
                p.fill(body.selector, body.text, timeout=15000)
            else:
                p.type(body.selector, body.text, timeout=15000)
            _persist()
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


    return pw(_op)
@app.get('/content')
def content(max_chars: int = 20000):
    def _op():
        p = _page()
        try:
            text = p.inner_text('body')
        except Exception:
            text = ''
        html = p.content()
        return {
            'url': p.url,
            'title': p.title(),
            'text': text[:max_chars],
            'html_len': len(html),
            'tab': _active,
            'tabs': len(_pages),
        }


    return pw(_op)
@app.get('/observe')
def observe(max_chars: int = 12000, max_controls: int = 80):
    """Page state for the agent loop — controls are generic, not site-coded."""
    def _op():
        p = _page()
        try:
            text = p.inner_text('body')
        except Exception:
            text = ''
        controls = p.evaluate(
            """(maxN) => {
              const out = [];
              const nodes = document.querySelectorAll(
                'a[href], button, input, select, textarea, [role="button"], [role="link"], [role="tab"]'
              );
              for (const el of nodes) {
                if (out.length >= maxN) break;
                const r = el.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) continue;
                const style = window.getComputedStyle(el);
                if (style.visibility === 'hidden' || style.display === 'none') continue;
                let sel = el.id ? ('#' + CSS.escape(el.id)) : null;
                if (!sel && el.name) sel = el.tagName.toLowerCase() + '[name="' + el.name + '"]';
                if (!sel) {
                  const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40);
                  if (t) sel = 'text=' + t;
                }
                out.push({
                  tag: el.tagName.toLowerCase(),
                  type: el.getAttribute('type') || '',
                  role: el.getAttribute('role') || '',
                  name: el.getAttribute('name') || '',
                  id: el.id || '',
                  href: el.getAttribute('href') || '',
                  text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                  disabled: !!el.disabled,
                  selector: sel,
                });
              }
              return out;
            }""",
            max_controls,
        )
        return {
            'url': p.url,
            'title': p.title(),
            'text': (text or '')[:max_chars],
            'controls': controls,
            'tab': _active,
            'tabs': len(_pages),
        }


    return pw(_op)
@app.post('/screenshot')
def screenshot(body: ShotIn):
    safe = ''.join(c for c in body.name if c.isalnum() or c in '._-') or 'shot.png'
    if not safe.endswith(('.png', '.jpg', '.jpeg')):
        safe += '.png'
    path = SHOTS / safe
    def _op():
        _page().screenshot(path=str(path), full_page=False)
        data = path.read_bytes()
        _live_shot()
        return {
            'ok': True,
            'path': f'workspace/screenshots/{safe}',
            'bytes': len(data),
            # Full image via /viewport.png or /api/desk/file — do NOT truncate preview for UI
            'preview_b64': base64.b64encode(data).decode() if len(data) < 400_000 else None,
        }


    return pw(_op)
@app.get('/url')
def current_url():
    def _op():
        p = _page()
        return {'url': p.url, 'title': p.title(), 'tab': _active, 'tabs': len(_pages)}


    return pw(_op)
@app.post('/upload')
def upload(body: UploadIn):
    path = Path(body.path)
    if not path.is_file():
        raise HTTPException(400, f'file not found: {body.path}')
    try:
        path.resolve().relative_to(DESK.resolve())
    except Exception as e:
        raise HTTPException(400, 'upload path must be under /desk') from e
    def _op():
        _page().set_input_files(body.selector, str(path))
        _persist()
        return {'ok': True, 'path': str(path)}


    return pw(_op)
@app.post('/scroll')
def scroll(body: ScrollIn):
    def _op():
        _page().mouse.wheel(0, body.dy)
        return {'ok': True, 'dy': body.dy}


    return pw(_op)
@app.post('/wait_for')
def wait_for(body: WaitIn):
    def _op():
        p = _page()
        try:
            if body.selector:
                p.wait_for_selector(body.selector, timeout=body.timeout_ms)
            if body.text:
                p.get_by_text(body.text).first.wait_for(timeout=body.timeout_ms)
            return {'ok': True, 'url': p.url}
        except Exception as e:
            return {'ok': False, 'error': str(e)}


    return pw(_op)
@app.post('/dismiss_overlays')
def dismiss_overlays():
    """Best-effort generic cookie/modal dismiss — no site adapters."""
    def _op():
        p = _page()
        dismissed = []
        for label in _DISMISS_TEXTS:
            try:
                loc = p.get_by_role('button', name=label)
                if loc.count() > 0:
                    loc.first.click(timeout=2000)
                    dismissed.append(label)
            except Exception:
                pass
            try:
                loc = p.get_by_text(label, exact=True)
                if loc.count() > 0:
                    loc.first.click(timeout=2000)
                    dismissed.append(label)
            except Exception:
                pass
        _persist()
        return {'ok': True, 'dismissed': list(dict.fromkeys(dismissed))}


    return pw(_op)
@app.post('/tab/new')
def tab_new(body: TabIn):
    def _op():
        _ensure()
        page = _context.new_page()
        _pages.append(page)
        global _active
        _active = len(_pages) - 1
        if body.url:
            page.goto(body.url, wait_until='domcontentloaded', timeout=60000)
        _persist()
        return {'ok': True, 'tab': _active, 'tabs': len(_pages), 'url': page.url}


    return pw(_op)
@app.post('/tab/switch')
def tab_switch(body: TabIn):
    def _op():
        if body.index is None or body.index < 0 or body.index >= len(_pages):
            raise HTTPException(400, 'bad tab index')
        global _active
        _active = body.index
        p = _page()
        return {'ok': True, 'tab': _active, 'url': p.url, 'title': p.title()}


    return pw(_op)
@app.get('/tabs')
def tabs():
    def _op():
        _ensure()
        info = []
        for i, p in enumerate(_pages):
            try:
                info.append({'index': i, 'url': p.url, 'title': p.title(), 'active': i == _active})
            except Exception:
                info.append({'index': i, 'url': '?', 'title': '?', 'active': i == _active})
        return {'tabs': info, 'active': _active}


    return pw(_op)
@app.post('/restart_context')
def restart_context():
    """Survive browser restart using persisted storage_state (BROW-12).

    Soft-restarts the Playwright context (not the Sync API driver) so we stay
    compatible with uvicorn's asyncio loop.
    """
    global _context, _pages, _active
    def _op():
        try:
            if _context:
                _persist()
                try:
                    _context.close()
                except Exception:
                    pass
        except Exception:
            pass
        _context = None
        _pages = []
        _active = 0
        _ensure()
        return {
            'ok': True,
            'restored_state': (PROFILE / 'state.json').exists(),
            'url': _page().url,
            'mode': 'soft_context_restart',
        }


    return pw(_op)
class TextIn(BaseModel):
    text: str


@app.post('/click_text')
def click_text(body: TextIn):
    """Click by visible text — still generic, not site-coded."""
    def _op():
        try:
            p = _page()
            p.get_by_text(body.text, exact=False).first.click(timeout=15000)
            _persist()
            return {'ok': True, 'url': p.url}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
    return pw(_op)
