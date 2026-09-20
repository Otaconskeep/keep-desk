#!/usr/bin/env python3
"""Serve CI-1 unknown webapps. Agents must discover UI — no site-specific bot code."""
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import os

ROOT = Path(os.environ.get('FIXTURE_ROOT', '/opt/otacon/keep-bots/fixtures')).resolve()
PORT = int(os.environ.get('FIXTURE_PORT', '5767'))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)
    def log_message(self, fmt, *args):
        pass

if __name__ == '__main__':
    print(f'fixture server {ROOT} :{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
