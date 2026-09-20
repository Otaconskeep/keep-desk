"""Teach-by-demonstration — the Grok Bot link OtaconsKeep was missing.

Pipeline:
  Record user/computer actions
       ↓
  Capture: action, target, screen state, timing, entered values
       ↓
  Generalize variable data (don't hardcode "Bob")
       ↓
  Infer inputs / constants / decisions / validation
       ↓
  Generate Skill draft
       ↓
  Replay in sandbox with new inputs
       ↓
  Review + publish Skill

This is NOT a dumb macro recorder.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from computer_use import Computer, DESK

DEMO_DIR = DESK / 'workspace' / 'demos'
SKILL_DIR = DESK / 'skills'
DEMO_DIR.mkdir(parents=True, exist_ok=True)

# Heuristic: typed values that look like variables
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_NUMERIC = re.compile(r'^\d{2,}$')
_TOKENISH = re.compile(r'^[A-Z0-9_-]{4,}$')


@dataclass
class DemoEvent:
    action: str
    args: dict
    t: float
    url: str | None = None
    title: str | None = None
    text_snippet: str | None = None


@dataclass
class DemoRecording:
    demo_id: str
    events: list[DemoEvent] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)

    def add(self, action: str, args: dict, obs: dict | None = None) -> None:
        self.events.append(DemoEvent(
            action=action,
            args=deepcopy(args),
            t=time.time() - self.started_at,
            url=(obs or {}).get('url'),
            title=(obs or {}).get('title'),
            text_snippet=((obs or {}).get('text') or '')[:240] or None,
        ))

    def save(self) -> Path:
        path = DEMO_DIR / f'{self.demo_id}.json'
        path.write_text(json.dumps({
            'demo_id': self.demo_id,
            'started_at': self.started_at,
            'meta': self.meta,
            'events': [asdict(e) for e in self.events],
        }, indent=2) + '\n')
        return path


class RecordingComputer:
    """Wraps Computer and records every action for teach-by-demo."""

    def __init__(self, demo_id: str | None = None, meta: dict | None = None):
        self.demo_id = demo_id or f'demo_{uuid.uuid4().hex[:10]}'
        self.rec = DemoRecording(demo_id=self.demo_id, meta=meta or {})
        self.cu = Computer(session_id=f'rec_{self.demo_id}')

    def _obs(self) -> dict:
        try:
            return self.cu.observe(max_chars=2000)
        except Exception:
            return {}

    def navigate(self, url: str) -> dict:
        r = self.cu.navigate(url)
        self.rec.add('navigate', {'url': url}, self._obs())
        return r

    def click(self, selector: str) -> dict:
        r = self.cu.click(selector)
        self.rec.add('click', {'selector': selector}, self._obs())
        return r

    def type(self, selector: str, text: str) -> dict:
        r = self.cu.type(selector, text)
        self.rec.add('type', {'selector': selector, 'text': text}, self._obs())
        return r

    def wait(self, seconds: float = 0.4) -> dict:
        r = self.cu.wait(seconds)
        self.rec.add('wait', {'seconds': seconds})
        return r

    def screenshot(self, name: str = 'demo.png') -> dict:
        r = self.cu.screenshot(name)
        self.rec.add('screenshot', {'name': name})
        return r

    def finish(self) -> Path:
        return self.rec.save()


def _is_variable_value(text: str) -> bool:
    if not text or len(text) > 80:
        return False
    if text.lower() in {'submit', 'ok', 'search', 'login', 'next'}:
        return False
    if _EMAIL.match(text) or _NUMERIC.match(text):
        return True
    # Proper-ish names / free text inputs
    if text[:1].isupper() and ' ' not in text and len(text) >= 2:
        return True
    if _TOKENISH.match(text) and not text.startswith('http'):
        return True
    return True  # default: treat typed text as variable (safer for generalization)


def generalize_recording(rec: dict | DemoRecording) -> dict:
    """Infer Skill draft: constants stay; typed values become inputs."""
    if isinstance(rec, DemoRecording):
        events = [asdict(e) for e in rec.events]
        demo_id = rec.demo_id
        meta = rec.meta
    else:
        events = list(rec.get('events') or [])
        demo_id = rec.get('demo_id') or 'demo'
        meta = rec.get('meta') or {}

    inputs: dict[str, Any] = {}
    steps: list[dict] = []
    input_i = 0

    for ev in events:
        action = ev['action']
        args = deepcopy(ev.get('args') or {})
        if action == 'type' and 'text' in args and _is_variable_value(str(args['text'])):
            input_i += 1
            # Prefer semantic names from selector
            sel = str(args.get('selector') or '')
            if 'name' in sel.lower():
                key = 'name'
            elif 'code' in sel.lower() or 'code' in sel:
                key = 'code'
            elif 'email' in sel.lower():
                key = 'email'
            elif 'customer' in sel.lower():
                key = 'customer_name'
            else:
                key = f'input_{input_i}'
            # uniquify
            base = key
            n = 2
            while key in inputs:
                key = f'{base}_{n}'
                n += 1
            inputs[key] = {
                'example': args['text'],
                'from_selector': sel,
            }
            args['text'] = f'{{{{{key}}}}}'
        steps.append({
            'action': action,
            'args': args,
            't': ev.get('t'),
        })

    skill = {
        'name': meta.get('name') or f'skill_from_{demo_id}',
        'description': meta.get('description') or f'Auto-generated from demonstration {demo_id}',
        'source_demo': demo_id,
        'applicability': meta.get('applicability') or ['browser_workflow'],
        'required_inputs': list(inputs.keys()),
        'input_schema': inputs,
        'prerequisites': [],
        'steps': steps,
        'decision_rules': [],
        'tool_permissions': ['browser_navigate', 'browser_click', 'browser_type', 'observe'],
        'expected_outputs': meta.get('expected_outputs') or ['page_contains_marker'],
        'validation': meta.get('validation') or [],
        'approval_boundaries': ['no_production_write', 'no_destructive_shell'],
        'failure_behavior': 'stop_and_report',
        'version': 1,
        'generalized': True,
        # Prove we did NOT freeze the demo literal forever
        'must_not_hardcode_examples': [v['example'] for v in inputs.values()],
    }
    return skill


def render_steps(skill: dict, inputs: dict) -> list[dict]:
    """Substitute {{input}} placeholders with provided values."""
    out = []
    for step in skill.get('steps') or []:
        args = deepcopy(step.get('args') or {})
        for k, v in list(args.items()):
            if isinstance(v, str):
                for ik, iv in inputs.items():
                    v = v.replace('{{' + ik + '}}', str(iv))
                args[k] = v
        out.append({'action': step['action'], 'args': args})
    return out


def replay_skill(skill: dict, inputs: dict, *, session_id: str | None = None) -> dict:
    """Execute generalized Skill with NEW inputs (sandbox replay)."""
    cu = Computer(session_id=session_id or f'replay_{uuid.uuid4().hex[:8]}')
    steps = render_steps(skill, inputs)
    # Guard: examples from demo must not appear if inputs differ
    for ex in skill.get('must_not_hardcode_examples') or []:
        if ex and ex not in inputs.values():
            blob = json.dumps(steps)
            # placeholder form is ok; literal example in navigated typed args is not
            for st in steps:
                if st['action'] == 'type' and st['args'].get('text') == ex:
                    return {'ok': False, 'error': f'hardcoded demo value leaked: {ex}'}

    log = []
    for st in steps:
        action = st['action']
        args = st['args']
        fn = getattr(cu, action, None)
        if not fn:
            log.append({'action': action, 'error': 'unknown action'})
            continue
        try:
            result = fn(**args)
            log.append({'action': action, 'args': args, 'ok': True, 'result': result})
        except TypeError:
            # wait(seconds=...) etc.
            result = fn(*args.values()) if args else fn()
            log.append({'action': action, 'args': args, 'ok': True, 'result': result})
        except Exception as e:
            log.append({'action': action, 'args': args, 'ok': False, 'error': str(e)})
            return {'ok': False, 'log': log, 'error': str(e), 'trace': str(cu.trace_path)}

    obs = cu.observe()
    return {
        'ok': True,
        'log': log,
        'final_url': obs.get('url'),
        'final_title': obs.get('title'),
        'final_text': (obs.get('text') or '')[:2000],
        'trace': str(cu.trace_path),
    }


def publish_skill(skill: dict, store=None) -> dict:
    skill_id = f"skill_{uuid.uuid4().hex[:10]}"
    d = SKILL_DIR / skill_id
    d.mkdir(parents=True, exist_ok=True)
    (d / 'skill.json').write_text(json.dumps(skill, indent=2) + '\n')
    (d / 'SKILL.md').write_text(
        f"# {skill['name']}\n\n{skill.get('description')}\n\n"
        f"## Inputs\n" + '\n'.join(f"- `{k}`: example `{v.get('example')}`" for k, v in (skill.get('input_schema') or {}).items()) +
        f"\n\n## Steps\n" + '\n'.join(f"- {s['action']} {s['args']}" for s in skill.get('steps') or []) + '\n'
    )
    published = {'skill_id': skill_id, 'path': str(d), 'skill': skill}
    if store is not None:
        store.save_skill(
            name=skill['name'],
            description=json.dumps({'teach_by_demo': True, 'schema': skill}),
            steps=[json.dumps(s) for s in skill.get('steps') or []],
            bot_id='teacher',
        )
    return published
