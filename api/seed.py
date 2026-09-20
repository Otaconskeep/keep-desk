"""Seed the four example Keep Bots (Engineer / QA / Researcher / PM)."""
from __future__ import annotations

import os
from pathlib import Path

from store import Store

SEED = [
    {
        'id': 'engineer',
        'name': 'ENGINEER',
        'role': 'Software engineer',
        'mandate': (
            'Pull/inspect repos under /desk/workspace, write and run code, '
            'reproduce bugs, prepare patches. Hand off to QA for verification. '
            'Do not touch production Keep services — draft only.'
        ),
        'color': '#3d8bfd',
    },
    {
        'id': 'qa',
        'name': 'QA',
        'role': 'Quality assurance',
        'mandate': (
            'Receive handoffs from Engineer, reproduce bugs, run tests, '
            'report regressions as desk artifacts and hand back findings.'
        ),
        'color': '#20c997',
    },
    {
        'id': 'researcher',
        'name': 'RESEARCHER',
        'role': 'Researcher',
        'mandate': (
            'Search the web, collect documentation, summarize findings into '
            '/desk/workspace/research/, and hand useful context to Engineer or PM.'
        ),
        'color': '#cc5de8',
    },
    {
        'id': 'pm',
        'name': 'PROJECT MANAGER',
        'role': 'Project manager',
        'mandate': (
            'Watch open jobs and handoffs, assign follow-ups, keep a living '
            'status note under /desk/workspace/status/, summarize for the operator.'
        ),
        'color': '#fcc419',
    },
]


def seed(state_dir: str | None = None) -> list[dict]:
    state = state_dir or os.environ.get('STATE_DIR', '/desk/state')
    store = Store(state)
    desk = Path(os.environ.get('DESK_ROOT', '/desk'))
    for b in SEED:
        store.upsert_bot(b)
        for sub in ('inbox', 'memory'):
            (desk / sub / b['id']).mkdir(parents=True, exist_ok=True)
    (desk / 'workspace' / 'research').mkdir(parents=True, exist_ok=True)
    (desk / 'workspace' / 'status').mkdir(parents=True, exist_ok=True)
    readme = desk / 'workspace' / 'README.md'
    if not readme.exists():
        readme.write_text(
            '# Keep Desk workspace\n\n'
            'Shared by all Keep Bots (not a security boundary).\n'
            'Engineer / QA / Researcher / PM collaborate here.\n'
        )
    return store.list_bots()


if __name__ == '__main__':
    bots = seed()
    print(f'seeded {len(bots)} bots')
