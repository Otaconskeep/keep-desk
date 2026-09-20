"""Local-only brain — RTX 3090 Ollama via host GPU router.

HARD RULE: never call xAI / Anthropic / OpenAI / Groq cloud APIs.
Keep Desk must run entirely on OtaconsKeep local silicon.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

# Explicit denylist — fail closed if misconfigured
_CLOUD_HOST_RE = re.compile(
    r'(api\.x\.ai|api\.openai\.com|api\.anthropic\.com|api\.groq\.com|'
    r'openrouter\.ai|generativelanguage\.googleapis\.com|'
    r'claude\.ai|openai\.azure\.com|bedrock|together\.xyz)',
    re.I,
)

_LOCAL_HOST_OK = {
    'localhost', '127.0.0.1', 'host.docker.internal',
    '0.0.0.0', '::1',
}


def _is_local_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    host = (u.hostname or '').lower()
    if _CLOUD_HOST_RE.search(host):
        return False
    if host in _LOCAL_HOST_OK:
        return True
    # RFC1918 / docker bridge / Keep LAN
    if host.startswith(('10.', '192.168.', '172.')):
        return True
    return False


class Brain:
    def __init__(self):
        # Prefer direct local Ollama/gpu-router — NOT Omniroute (may have cloud providers)
        self.base = os.environ.get(
            'LOCAL_OLLAMA_URL',
            os.environ.get('OMNIROUTE_BASE_URL', 'http://host.docker.internal:11434/v1'),
        ).rstrip('/')
        # Strip trailing /v1 duplication safety
        if self.base.endswith('/v1/v1'):
            self.base = self.base[:-3]
        self.model = os.environ.get('LOCAL_MODEL', os.environ.get('OMNIROUTE_MODEL', 'gpt-oss:20b'))
        # Strip omniroute provider prefix if present
        if '/' in self.model and not self.model.startswith('gpt'):
            # e.g. ollama-local/gpt-oss:20b → gpt-oss:20b
            self.model = self.model.split('/', 1)[-1]
        self.key = os.environ.get('LOCAL_OLLAMA_KEY', 'local')
        self._assert_local()

    def _assert_local(self) -> None:
        if not _is_local_url(self.base):
            raise RuntimeError(
                f'Refused non-local brain URL: {self.base}. '
                'Keep Desk is LOCAL-ONLY (RTX 3090 / Ollama).'
            )
        if _CLOUD_HOST_RE.search(self.base):
            raise RuntimeError(f'Cloud API blocked: {self.base}')

    def chat(self, messages: list[dict], *, temperature: float = 0.2,
             tools: list[dict] | None = None) -> dict[str, Any]:
        self._assert_local()
        body: dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'stream': False,
        }
        if tools:
            body['tools'] = tools
            body['tool_choice'] = 'auto'
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f'{self.base}/chat/completions',
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.key}',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors='replace')[:800]
            raise RuntimeError(f'local brain HTTP {e.code}: {err}') from e
        except Exception as e:
            raise RuntimeError(f'local brain error: {e}') from e

    def assistant_message(self, raw: dict) -> dict:
        choices = raw.get('choices') or []
        if not choices:
            return {'role': 'assistant', 'content': ''}
        return choices[0].get('message') or {'role': 'assistant', 'content': ''}

    def info(self) -> dict:
        return {
            'mode': 'local_only',
            'base': self.base,
            'model': self.model,
            'cloud_blocked': True,
        }
