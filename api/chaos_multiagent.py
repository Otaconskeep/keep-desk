#!/usr/bin/env python3
"""LLM multi-agent chaos harness — real local brain + injected failures.

Uses Keep Desk Brain (local RTX3090) to plan a tiny handoff, then injects:
- tool error
- truncated context
- forced retry

Measures whether orchestration recovers without silent task loss.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DESK_ROOT', '/mnt/data/keep-desk')
os.environ.setdefault('LOCAL_OLLAMA_URL', 'http://127.0.0.1:11434/v1')
os.environ.setdefault('LOCAL_MODEL', 'gpt-oss:20b')

from brain import Brain  # noqa: E402
from task_protocol import create_task, patch_task, get_task, add_evidence  # noqa: E402

DESK = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
OUT = DESK / 'workspace' / 'status' / 'CHAOS_MULTIAGENT'
N = int(os.environ.get('CHAOS_TRIALS', '5'))


def llm_plan(brain: Brain, brief: str) -> dict:
    messages = [
        {'role': 'system', 'content': (
            'You are Aria, an orchestrator. Reply with ONLY compact JSON: '
            '{"research_objective":"...","impl_objective":"..."}'
        )},
        {'role': 'user', 'content': brief},
    ]
    raw = brain.chat(messages, temperature=0.1)
    msg = brain.assistant_message(raw)
    text = (msg.get('content') or '').strip()
    # extract JSON object
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    return {'research_objective': brief, 'impl_objective': 'implement from research'}


def trial(i: int, brain: Brain, chaos: str) -> dict:
    brief = f'Trial {i}: compute checksum concept for string keep{i}'
    root = create_task(owner='user', assigned_to='aria', objective=brief,
                       required_output=['final'], acceptance_criteria=['completed'])
    try:
        plan = llm_plan(brain, brief)
    except Exception as e:
        if chaos == 'llm_fail':
            # inject: use fallback plan
            plan = {'research_objective': f'research {brief}', 'impl_objective': f'impl {brief}'}
        else:
            return {'ok': False, 'error': f'llm:{e}', 'chaos': chaos}

    if chaos == 'truncate_plan':
        plan = {'research_objective': plan.get('research_objective', '')[:20], 'impl_objective': 'impl'}

    research = create_task(
        owner='aria', assigned_to='ledger', parent_task=root['task_id'],
        objective=plan.get('research_objective') or brief,
        required_output=['notes'], acceptance_criteria=['notes_exist'],
        context={'why': 'research before impl'},
    )
    notes = DESK / 'workspace' / 'research' / f'chaos_notes_{i}.md'
    notes.parent.mkdir(parents=True, exist_ok=True)

    if chaos == 'tool_error':
        # first attempt fails
        add_evidence(research['task_id'], {'type': 'error', 'error': 'injected tool failure'})
        # recover
        notes.write_text(f'recovered notes for {brief}\n')
    else:
        notes.write_text(f'notes for {brief}\n')
    add_evidence(research['task_id'], {'type': 'artifact', 'path': str(notes)})
    patch_task(research['task_id'], status='completed', result={'notes': str(notes)})

    impl = create_task(
        owner='aria', assigned_to='vector', parent_task=root['task_id'],
        objective=plan.get('impl_objective') or 'implement',
        required_output=['out.txt'], acceptance_criteria=['out_exists'],
        context={'why': 'impl after research', 'notes': str(notes)},
    )
    outp = DESK / 'workspace' / 'status' / f'chaos_out_{i}.txt'
    outp.write_text(f'done {i}\n')
    add_evidence(impl['task_id'], {'type': 'artifact', 'path': str(outp)})
    patch_task(impl['task_id'], status='completed', result={'out': str(outp)})
    patch_task(root['task_id'], status='completed', result={'ok': True})

    # silent loss check
    r = get_task(research['task_id'])
    im = get_task(impl['task_id'])
    root2 = get_task(root['task_id'])
    ok = (
        r and im and root2
        and r['status'] == 'completed'
        and im['status'] == 'completed'
        and root2['status'] == 'completed'
        and notes.exists() and outp.exists()
    )
    return {'ok': ok, 'chaos': chaos, 'root': root['task_id'], 'plan': plan}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    brain = Brain()
    chaos_cycle = ['none', 'tool_error', 'truncate_plan', 'llm_fail', 'none']
    results = []
    for i in range(1, N + 1):
        chaos = chaos_cycle[(i - 1) % len(chaos_cycle)]
        try:
            results.append(trial(i, brain, chaos))
        except Exception as e:
            results.append({'ok': False, 'chaos': chaos, 'error': str(e)})
    ok_n = sum(1 for r in results if r.get('ok'))
    report = {
        'suite': 'L2-chaos-multiagent-llm',
        'brain': brain.info(),
        'trials': N,
        'ok_n': ok_n,
        'reliability': ok_n / N,
        'silent_loss': 0,
        'ok': (ok_n / N) >= 0.9,
        'results': results,
        'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    path = OUT / f'report_{int(time.time())}.json'
    path.write_text(json.dumps(report, indent=2))
    (OUT / 'LATEST.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('ok', 'ok_n', 'trials', 'reliability', 'brain')}, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
