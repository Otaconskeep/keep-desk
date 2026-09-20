"""Desk tools — shared computer for Keep Bots (LOCAL Grok Bot parity)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DESK_ROOT = Path(os.environ.get('DESK_ROOT', '/desk')).resolve()
BROWSER_URL = os.environ.get('BROWSER_URL', 'http://keep-desk-browser:5766').rstrip('/')

_FORBIDDEN_PREFIXES = (
    '/etc', '/usr', '/bin', '/sbin', '/boot', '/root', '/home',
    '/opt/otacon', '/var/run', '/proc', '/sys',
)

_DESTRUCTIVE_SHELL = re.compile(
    r'\b(rm\s+-rf\s+/|mkfs|dd\s+if=|shutdown|reboot|passwd|userdel|'
    r'docker\s+(rm|rmi|system)|curl\s+[^\n]*\|\s*(ba)?sh)\b',
    re.I,
)

TOOL_SCHEMAS = [
    {'type': 'function', 'function': {
        'name': 'desk_list',
        'description': 'List files under a path inside the shared desk.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string'},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'desk_read',
        'description': 'Read a text file from the shared desk (max 64KB).',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string'},
        }, 'required': ['path']},
    }},
    {'type': 'function', 'function': {
        'name': 'desk_write',
        'description': 'Write a text file into the shared desk.',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string'}, 'content': {'type': 'string'},
        }, 'required': ['path', 'content']},
    }},
    {'type': 'function', 'function': {
        'name': 'desk_delete',
        'description': 'Delete a desk file (requires approval).',
        'parameters': {'type': 'object', 'properties': {
            'path': {'type': 'string'},
        }, 'required': ['path']},
    }},
    {'type': 'function', 'function': {
        'name': 'shell',
        'description': (
            'Run a shell command in /desk/workspace (git, python, pytest). '
            'Shell has NO stdin from other tools — never use sys.stdin.read() to parse '
            'http_fetch/browser output. Write files with desk_write then read them, or use browser_content.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'command': {'type': 'string'},
            'timeout_sec': {'type': 'integer', 'default': 90},
        }, 'required': ['command']},
    }},
    {'type': 'function', 'function': {
        'name': 'http_fetch',
        'description': (
            'HTTP GET a URL (no JS). Returns status + text_excerpt. '
            'For Google/news/interactive pages use web_research or browser_navigate instead.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string'},
            'max_bytes': {'type': 'integer', 'default': 20000},
        }, 'required': ['url']},
    }},
    {'type': 'function', 'function': {
        'name': 'web_research',
        'description': (
            'PRIMARY tool for browse/news/search jobs. Opens the shared browser, navigates to '
            'query (DuckDuckGo) or url, dismisses overlays, returns visible text + live screenshot path. '
            'Then desk_write findings and finish.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Search query, e.g. newest Metal Gear Solid news'},
            'url': {'type': 'string', 'description': 'Optional direct URL instead of search'},
            'max_chars': {'type': 'integer', 'default': 10000},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_navigate',
        'description': 'Open a URL in the shared persistent browser computer.',
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string'},
        }, 'required': ['url']},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_content',
        'description': 'Read visible text from the current browser page.',
        'parameters': {'type': 'object', 'properties': {
            'max_chars': {'type': 'integer', 'default': 12000},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_click',
        'description': 'Click a CSS selector in the shared browser.',
        'parameters': {'type': 'object', 'properties': {
            'selector': {'type': 'string'},
        }, 'required': ['selector']},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_click_text',
        'description': 'Click the first element matching visible text (generic, not site-specific).',
        'parameters': {'type': 'object', 'properties': {
            'text': {'type': 'string'},
        }, 'required': ['text']},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_type',
        'description': 'Type into a CSS selector in the shared browser.',
        'parameters': {'type': 'object', 'properties': {
            'selector': {'type': 'string'}, 'text': {'type': 'string'},
        }, 'required': ['selector', 'text']},
    }},
    {'type': 'function', 'function': {
        'name': 'browser_screenshot',
        'description': 'Screenshot current page into workspace/screenshots/ (also refreshes live.png).',
        'parameters': {'type': 'object', 'properties': {
            'name': {'type': 'string', 'default': 'shot.png'},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'handoff',
        'description': 'Hand work to another Keep Bot.',
        'parameters': {'type': 'object', 'properties': {
            'to_bot': {'type': 'string'},
            'message': {'type': 'string'},
            'spawn_job_title': {'type': 'string'},
        }, 'required': ['to_bot', 'message']},
    }},
    {'type': 'function', 'function': {
        'name': 'group_post',
        'description': 'Post a message into a group thread all bots share.',
        'parameters': {'type': 'object', 'properties': {
            'thread_id': {'type': 'string'},
            'text': {'type': 'string'},
        }, 'required': ['thread_id', 'text']},
    }},
    {'type': 'function', 'function': {
        'name': 'memory_write',
        'description': 'Persist a note under /desk/memory/<bot_id>/.',
        'parameters': {'type': 'object', 'properties': {
            'filename': {'type': 'string'}, 'content': {'type': 'string'},
        }, 'required': ['filename', 'content']},
    }},
    {'type': 'function', 'function': {
        'name': 'memory_read',
        'description': 'Read a memory file for this bot.',
        'parameters': {'type': 'object', 'properties': {
            'filename': {'type': 'string'},
        }, 'required': ['filename']},
    }},
    {'type': 'function', 'function': {
        'name': 'skill_save',
        'description': 'Save a reusable workflow skill from this job.',
        'parameters': {'type': 'object', 'properties': {
            'name': {'type': 'string'},
            'description': {'type': 'string'},
            'steps': {'type': 'array', 'items': {'type': 'string'}},
        }, 'required': ['name', 'description', 'steps']},
    }},
    {'type': 'function', 'function': {
        'name': 'skill_list',
        'description': 'List saved skills.',
        'parameters': {'type': 'object', 'properties': {}},
    }},
    {'type': 'function', 'function': {
        'name': 'skill_load',
        'description': 'Load a skill by id and return its steps.',
        'parameters': {'type': 'object', 'properties': {
            'skill_id': {'type': 'string'},
        }, 'required': ['skill_id']},
    }},
    {'type': 'function', 'function': {
        'name': 'operator_chat',
        'description': (
            'Post a message to the Keep Desk operator chat (:5765 Codec link). '
            'Use for mid-job status. Job start/finish are auto-posted; still call this '
            'for important findings the operator should see live.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'text': {'type': 'string'},
            'codec': {
                'type': 'boolean',
                'description': 'Also bridge to Otacon Codec (/codec/chat). Default false.',
                'default': False,
            },
        }, 'required': ['text']},
    }},
    {'type': 'function', 'function': {
        'name': 'codec_transmit',
        'description': (
            'Transmit to the operator via Otacon Codec AND Keep Desk chat. '
            'Use for critical updates that should surface in Codec.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'text': {'type': 'string'},
        }, 'required': ['text']},
    }},
    {'type': 'function', 'function': {
        'name': 'youtube_transcript',
        'description': (
            'Fetch a YouTube video transcript/captions by URL or video id. '
            'Use after finding an AI news video. Returns plain text transcript excerpt.'
        ),
        'parameters': {'type': 'object', 'properties': {
            'url': {'type': 'string', 'description': 'YouTube watch URL or youtu.be link'},
            'video_id': {'type': 'string', 'description': '11-char video id if known'},
            'max_chars': {'type': 'integer', 'default': 12000},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'room_list',
        'description': 'List Keep Desk group rooms/threads the bots can talk in.',
        'parameters': {'type': 'object', 'properties': {}},
    }},
    {'type': 'function', 'function': {
        'name': 'finish',
        'description': 'Mark the job complete.',
        'parameters': {'type': 'object', 'properties': {
            'summary': {'type': 'string'},
        }, 'required': ['summary']},
    }},
]


def _safe_desk_path(rel: str) -> Path:
    rel = (rel or '').strip()
    # Models often pass /desk/... or desk/... — normalize to desk-relative
    if rel.startswith('/desk/'):
        rel = rel[len('/desk/'):]
    elif rel == '/desk':
        rel = ''
    elif rel.startswith('desk/'):
        rel = rel[len('desk/'):]
    elif rel == 'desk':
        rel = ''
    rel = rel.lstrip('/')
    if not rel:
        rel = 'workspace'
    candidate = (DESK_ROOT / rel).resolve()
    if not str(candidate).startswith(str(DESK_ROOT)):
        raise ValueError('path escapes desk root')
    return candidate


def _browser_json(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f'{BROWSER_URL}{path}',
        data=data,
        headers={'Content-Type': 'application/json'} if body is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {'error': f'browser: {e}'}


class ToolRunner:
    def __init__(self, store, bot_id: str, job_id: str, *, approvals_required: bool = True):
        self.store = store
        self.bot_id = bot_id
        self.job_id = job_id
        self.approvals_required = approvals_required
        self.finished = False
        self.finish_summary = None
        self.needs_approval = False

    def run(self, name: str, args: dict) -> dict[str, Any]:
        handlers = {
            'desk_list': lambda: self._desk_list(args.get('path') or 'workspace'),
            'desk_read': lambda: self._desk_read(args['path']),
            'desk_write': lambda: self._desk_write(
                args.get('path') or '',
                args.get('content') or args.get('text') or args.get('body') or '',
            ),
            'desk_delete': lambda: self._desk_delete(args['path']),
            'shell': lambda: self._shell(args['command'], int(args.get('timeout_sec') or 90)),
            'http_fetch': lambda: self._http_fetch(args['url'], int(args.get('max_bytes') or 20000)),
            'web_research': lambda: self._web_research(args),
            'browser_navigate': lambda: _browser_json('POST', '/navigate', {'url': args['url']}),
            'browser_content': lambda: _browser_json(
                'GET', f"/content?max_chars={int(args.get('max_chars') or 12000)}"),
            'browser_click': lambda: _browser_json('POST', '/click', {'selector': args['selector']}),
            'browser_click_text': lambda: _browser_json('POST', '/click_text', {'text': args['text']}),
            'browser_type': lambda: _browser_json(
                'POST', '/type', {'selector': args['selector'], 'text': args['text']}),
            'browser_screenshot': lambda: _browser_json(
                'POST', '/screenshot', {'name': args.get('name') or 'shot.png'}),
            'handoff': lambda: self._handoff(args),
            'group_post': lambda: self._group_post(args.get('thread_id') or '', args.get('text') or ''),
            'memory_write': lambda: self._memory_write(args['filename'], args.get('content') or ''),
            'memory_read': lambda: self._memory_read(args['filename']),
            'skill_save': lambda: self._skill_save(args),
            'skill_list': lambda: {'skills': [
                {'id': s['id'], 'name': s['name'], 'description': s.get('description')}
                for s in self.store.list_skills()
            ]},
            'skill_load': lambda: self._skill_load(args['skill_id']),
            'operator_chat': lambda: self._operator_chat(
                args.get('text') or '', bool(args.get('codec'))),
            'codec_transmit': lambda: self._operator_chat(
                args.get('text') or '', codec=True, kind='codec_tx'),
            'youtube_transcript': lambda: self._youtube_transcript(args),
            'room_list': lambda: self._room_list(),
            'finish': lambda: self._finish(args.get('summary') or ''),
        }
        fn = handlers.get(name)
        if not fn:
            return {'error': f'unknown tool {name}'}
        try:
            return fn()
        except KeyError as e:
            return {'error': f'missing arg {e}'}
        except Exception as e:
            return {'error': str(e)}

    def _room_list(self) -> dict:
        rooms = []
        for t in self.store.list_threads()[:30]:
            rooms.append({
                'thread_id': t.get('id'),
                'title': t.get('title'),
                'bot_ids': t.get('bot_ids') or [],
                'messages': len(t.get('messages') or []),
            })
        return {'ok': True, 'rooms': rooms, 'hint': 'Use group_post(thread_id=..., text=...) to talk in a room.'}

    def _youtube_transcript(self, args: dict) -> dict:
        """Pull captions from a YouTube watch page / timedtext tracks."""
        from urllib.parse import parse_qs, urlparse

        url = (args.get('url') or '').strip()
        vid = (args.get('video_id') or '').strip()
        max_chars = int(args.get('max_chars') or 12000)
        if not vid and url:
            u = urlparse(url)
            if 'youtu.be' in (u.netloc or ''):
                vid = (u.path or '/').lstrip('/').split('/')[0]
            else:
                vid = (parse_qs(u.query).get('v') or [''])[0]
            if not vid and '/shorts/' in (u.path or ''):
                vid = (u.path or '').split('/shorts/')[-1].split('/')[0]
        if not vid or len(vid) < 8:
            return {'error': 'need a YouTube url or video_id'}

        watch = f'https://www.youtube.com/watch?v={vid}'
        title = ''
        text = ''

        # Preferred: youtube-transcript-api (handles signed timedtext)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            fetched = YouTubeTranscriptApi().fetch(vid)
            bits = []
            for snip in fetched:
                bits.append(getattr(snip, 'text', None) or (snip.get('text') if isinstance(snip, dict) else '') or '')
            text = ' '.join(bits)
            text = re.sub(r'\s+', ' ', text).strip()
        except Exception as e:
            yt_api_err = str(e)
        else:
            yt_api_err = None

        headers = {
            'User-Agent': (
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            req = urllib.request.Request(watch, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            mtitle = re.search(r'<title>([^<]+)</title>', html)
            if mtitle:
                title = mtitle.group(1).replace(' - YouTube', '').strip()
        except Exception:
            html = ''

        if not text:
            # Fall back to captionTracks brace-match (often empty from datacenter IPs)
            tracks = []
            idx = html.find('"captionTracks":') if html else -1
            if idx >= 0:
                start = html.find('[', idx)
                depth = 0
                end = None
                for j, ch in enumerate(html[start:], start):
                    if ch == '[':
                        depth += 1
                    elif ch == ']':
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            break
                if end:
                    try:
                        tracks = json.loads(html[start:end])
                    except Exception:
                        tracks = []
            if tracks:
                track = tracks[0]
                base_url = track.get('baseUrl') or ''
                try:
                    req = urllib.request.Request(
                        base_url + ('&fmt=json3' if 'fmt=' not in base_url else ''),
                        headers=headers,
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        payload = resp.read().decode('utf-8', errors='replace')
                    if payload.lstrip().startswith('{'):
                        data = json.loads(payload)
                        bits = []
                        for ev in data.get('events') or []:
                            for seg in ev.get('segs') or []:
                                bits.append(seg.get('utf8') or '')
                        text = re.sub(r'\s+', ' ', ' '.join(bits)).strip()
                except Exception as e:
                    yt_api_err = yt_api_err or str(e)

        _browser_json('POST', '/navigate', {'url': watch})
        if not text:
            return {
                'ok': False,
                'video_id': vid,
                'title': title,
                'url': watch,
                'error': yt_api_err or 'no captions available',
                'hint': 'Try another video, or summarize from the video description via browser_content.',
            }
        return {
            'ok': True,
            'video_id': vid,
            'title': title or vid,
            'url': watch,
            'chars': len(text),
            'transcript': text[:max_chars],
        }

    def _operator_chat(self, text: str, codec: bool = False, kind: str = 'chat') -> dict:
        from chat_bus import post_message
        if not (text or '').strip():
            return {'error': 'empty text'}
        msg = post_message(
            from_id=f'bot:{self.bot_id}',
            text=text.strip(),
            kind='codec_tx' if codec else kind,
            job_id=self.job_id,
            bot_id=self.bot_id,
            codec=codec,
        )
        return {
            'ok': True,
            'msg_id': msg.get('id'),
            'codec': msg.get('codec'),
            'kind': msg.get('kind'),
        }

    def _finish(self, summary: str) -> dict:
        self.finished = True
        self.finish_summary = summary.strip() or 'done'
        return {'ok': True, 'summary': self.finish_summary}

    def _desk_list(self, path: str) -> dict:
        p = _safe_desk_path(path)
        if not p.exists():
            return {'error': 'not found', 'path': str(p.relative_to(DESK_ROOT))}
        if p.is_file():
            return {'type': 'file', 'path': str(p.relative_to(DESK_ROOT)), 'size': p.stat().st_size}
        entries = []
        for child in sorted(p.iterdir())[:200]:
            entries.append({
                'name': child.name,
                'type': 'dir' if child.is_dir() else 'file',
                'size': child.stat().st_size if child.is_file() else None,
            })
        return {'path': str(p.relative_to(DESK_ROOT)), 'entries': entries}

    def _desk_read(self, path: str) -> dict:
        p = _safe_desk_path(path)
        if not p.is_file():
            return {'error': 'not a file'}
        data = p.read_bytes()[:65536]
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            return {'error': 'binary file', 'size': p.stat().st_size}
        return {'path': str(p.relative_to(DESK_ROOT)), 'content': text}

    def _desk_write(self, path: str, content: str) -> dict:
        if not path:
            return {'error': 'missing path'}
        if not (content or '').strip():
            return {
                'error': 'empty content — pass content= (or text=) with the findings to write',
                'hint': 'desk_write(path="workspace/research/topic.md", content="...")',
            }
        p = _safe_desk_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {'ok': True, 'path': str(p.relative_to(DESK_ROOT)), 'bytes': len(content.encode())}

    def _desk_delete(self, path: str) -> dict:
        if self.approvals_required:
            ap = self.store.create_approval(
                job_id=self.job_id, bot_id=self.bot_id,
                action='desk_delete', detail=path, risk='high',
            )
            self.needs_approval = True
            return {'pending_approval': ap['id'], 'action': 'desk_delete', 'path': path}
        p = _safe_desk_path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            p.rmdir()
        return {'ok': True, 'deleted': path}

    def _shell(self, command: str, timeout_sec: int) -> dict:
        cmd = command or ''
        if 'sys.stdin.read' in cmd or 'stdin.read()' in cmd:
            return {
                'error': (
                    'shell has empty stdin — previous tool output is NOT piped here. '
                    'Use browser_content / web_research / desk_read instead of parsing via stdin.'
                ),
                'hint': 'Call web_research(query=...) for browse/news jobs.',
            }
        if _DESTRUCTIVE_SHELL.search(cmd):
            if self.approvals_required:
                ap = self.store.create_approval(
                    job_id=self.job_id, bot_id=self.bot_id,
                    action='shell_destructive', detail=command, risk='critical',
                )
                self.needs_approval = True
                return {'pending_approval': ap['id'], 'action': 'shell_destructive'}
            return {'error': 'destructive shell blocked'}
        cwd = DESK_ROOT / 'workspace'
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                ['bash', '-lc', command],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=max(5, min(timeout_sec, 300)),
                env={
                    **os.environ,
                    'HOME': str(DESK_ROOT / 'home'),
                    'DESK_ROOT': str(DESK_ROOT),
                    'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                },
            )
            return {
                'exit_code': proc.returncode,
                'stdout': (proc.stdout or '')[-12000:],
                'stderr': (proc.stderr or '')[-4000:],
            }
        except subprocess.TimeoutExpired:
            return {'error': 'timeout'}
        except Exception as e:
            return {'error': str(e)}

    def _html_to_text(self, html: str, max_chars: int = 8000) -> str:
        text = re.sub(r'(?is)<(script|style).*?>.*?</\1>', ' ', html)
        text = re.sub(r'(?is)<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]

    def _http_fetch(self, url: str, max_bytes: int) -> dict:
        if not url.startswith(('http://', 'https://')):
            return {'error': 'only http(s) allowed'}
        # Steer away from shopping rabbit holes on research jobs
        host = ''
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ''
        except Exception:
            host = ''
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                ),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read(max_bytes)
                raw = body.decode('utf-8', errors='replace')
                ct = resp.headers.get('Content-Type', '')
                out = {
                    'status': resp.status,
                    'content_type': ct,
                    'host': host,
                    'bytes': len(body),
                    'text_excerpt': self._html_to_text(raw) if 'html' in ct.lower() or raw.lstrip().startswith('<') else raw[:8000],
                    'note': 'For interactive pages prefer web_research. Do not pipe this into shell stdin.',
                }
                return out
        except Exception as e:
            return {'error': str(e)}

    def _web_research(self, args: dict) -> dict:
        """Search via local SearXNG JSON, open a top result in the shared browser for watch mode."""
        from urllib.parse import quote_plus, urlencode
        query = (args.get('query') or '').strip()
        url = (args.get('url') or '').strip()
        max_chars = int(args.get('max_chars') or 10000)
        if not url and not query:
            return {'error': 'provide query or url'}

        results = []
        searx_err = None
        searx = os.environ.get('SEARX_URL', 'http://192.168.50.219:8180').rstrip('/')
        if query and not url:
            # Structured search first (reliable); browser opens a result for the operator to watch
            qurl = f'{searx}/search?{urlencode({"q": query, "format": "json", "language": "en-US"})}'
            try:
                req = urllib.request.Request(
                    qurl,
                    headers={'User-Agent': 'Mozilla/5.0 (compatible; KeepDesk/1.0)'},
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode('utf-8', errors='replace'))
                for r in (data.get('results') or [])[:8]:
                    results.append({
                        'title': (r.get('title') or '')[:160],
                        'url': r.get('url') or '',
                        'snippet': (r.get('content') or '')[:280],
                        'engine': r.get('engine'),
                    })
                # Prefer titles matching query tokens (avoid "Metal - Wikipedia" for MGS queries)
                tokens = [t.lower() for t in re.findall(r'[a-zA-Z0-9]{3,}', query)]
                def _score(item: dict) -> int:
                    blob = f"{item.get('title','')} {item.get('url','')}".lower()
                    return sum(1 for t in tokens if t in blob)
                results.sort(key=_score, reverse=True)
                results = [r for r in results if _score(r) >= max(1, min(2, len(tokens)//2))] or results[:8]
            except Exception as e:
                results = []
                searx_err = str(e)
            if results:
                url = results[0]['url']

        if not url and query:
            url = f'https://en.wikipedia.org/w/index.php?search={quote_plus(query)}'

        nav = _browser_json('POST', '/navigate', {'url': url})
        if nav.get('error') or nav.get('ok') is False:
            return {
                'ok': False,
                'error': nav.get('error') or 'navigate failed',
                'results': results,
                'searx_error': searx_err if query else None,
            }
        _browser_json('POST', '/dismiss_overlays', {})
        content = _browser_json('GET', f'/content?max_chars={max_chars}')
        shot = _browser_json('POST', '/screenshot', {'name': 'live_research.png'})
        text = (content.get('text') or content.get('content') or '')[:max_chars]
        return {
            'ok': True,
            'url': nav.get('url') or url,
            'title': nav.get('title') or content.get('title'),
            'query': query or None,
            'results': results,
            'result_count': len(results),
            'text': text,
            'screenshot': shot.get('path') or 'workspace/screenshots/live.png',
            'chars': len(text),
            'next': (
                'Use results[] headlines/snippets. Optionally browser_navigate to results[1].url. '
                'desk_write workspace/research/<topic>.md then finish(summary=...).'
            ),
        }
    def _handoff(self, args: dict) -> dict:
        to_bot = (args.get('to_bot') or '').strip()
        if not self.store.get_bot(to_bot):
            return {'error': f'unknown bot {to_bot}'}
        msg = args.get('message') or ''
        ho = self.store.create_handoff(
            from_bot=self.bot_id, to_bot=to_bot, job_id=self.job_id, message=msg,
        )
        inbox = DESK_ROOT / 'inbox' / to_bot
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / f"{ho['id']}.json").write_text(json.dumps(ho, indent=2))
        title = args.get('spawn_job_title') or f'Handoff from {self.bot_id}'
        parent = self.store.get_job(self.job_id) or {}
        child = self.store.create_job(
            bot_id=to_bot, title=title, brief=msg,
            created_by=f'handoff:{self.bot_id}',
            thread_id=parent.get('thread_id'),
        )
        return {'ok': True, 'handoff_id': ho['id'], 'child_job_id': child['id']}

    def _group_post(self, thread_id: str, text: str) -> dict:
        t = self.store.post_thread(thread_id, from_id=self.bot_id, text=text)
        if not t:
            return {'error': 'thread not found'}
        return {'ok': True, 'messages': len(t.get('messages') or [])}

    def _memory_write(self, filename: str, content: str) -> dict:
        safe = re.sub(r'[^a-zA-Z0-9._-]+', '_', filename.strip()) or 'note.md'
        mem = DESK_ROOT / 'memory' / self.bot_id
        mem.mkdir(parents=True, exist_ok=True)
        path = mem / safe
        path.write_text(content)
        return {'ok': True, 'path': str(path.relative_to(DESK_ROOT))}

    def _memory_read(self, filename: str) -> dict:
        safe = re.sub(r'[^a-zA-Z0-9._-]+', '_', filename.strip()) or 'note.md'
        path = DESK_ROOT / 'memory' / self.bot_id / safe
        if not path.is_file():
            return {'error': 'not found'}
        return {'path': str(path.relative_to(DESK_ROOT)), 'content': path.read_text()[:65536]}

    def _skill_save(self, args: dict) -> dict:
        steps = args.get('steps') or []
        if isinstance(steps, str):
            steps = [steps]
        skill = self.store.save_skill(
            name=args.get('name') or 'unnamed',
            description=args.get('description') or '',
            steps=list(steps),
            bot_id=self.bot_id,
            source_job_id=self.job_id,
        )
        return {'ok': True, 'skill_id': skill['id'], 'path': f"skills/{skill['id']}/SKILL.md"}

    def _skill_load(self, skill_id: str) -> dict:
        s = self.store.get_skill(skill_id)
        if not s:
            return {'error': 'skill not found'}
        self.store.bump_skill_use(skill_id)
        return s
