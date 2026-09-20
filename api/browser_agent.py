"""Generic browser agent loop — site is incidental.

observe → understand page state → identify goal-relevant control → act →
observe result → verify → replan if necessary

NO if-site adapters. Task goals are declarative (URLs, contains, keywords).
"""
from __future__ import annotations

import re
import time
from typing import Any

from computer_use import Computer


def _goal_met(obs: dict, goal: dict) -> bool:
    text = (obs.get('text') or '') + ' ' + (obs.get('title') or '')
    url = obs.get('url') or ''
    for needle in goal.get('verify_contains') or []:
        if needle not in text and needle not in url:
            return False
    for needle in goal.get('verify_url_contains') or []:
        if needle not in url:
            return False
    for needle in goal.get('verify_not_contains') or []:
        if needle in text:
            return False
    return True


def _pick_control(controls: list[dict], keywords: list[str]) -> dict | None:
    kws = [k.lower() for k in keywords if k]
    if not kws:
        return None
    scored = []
    for c in controls or []:
        if c.get('disabled'):
            continue
        blob = ' '.join([
            c.get('text') or '', c.get('name') or '', c.get('id') or '',
            c.get('href') or '', c.get('type') or '',
        ]).lower()
        score = sum(1 for k in kws if k in blob)
        if score:
            scored.append((score, c))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], len(x[1].get('text') or '')))
    return scored[0][1]


def run_goal(cu: Computer, task: dict, max_actions: int = 40) -> dict:
    """Execute one declarative browser task via the generalized loop."""
    goal = task.get('goal') or {}
    start = task.get('start_url')
    steps_log: list[dict] = []
    t0 = time.time()

    # Optional injected wrong navigation (recovery test)
    wrong = task.get('inject_wrong_nav')
    if wrong:
        cu.navigate(wrong)
        cu.wrong_page_events += 1
        steps_log.append({'step': 'inject_wrong_nav', 'url': wrong})

    if start:
        nav = cu.navigate(start)
        steps_log.append({'step': 'navigate', 'url': start, 'ok': nav.get('ok')})
        if nav.get('ok') is False:
            return _fail(cu, task, steps_log, t0, 'navigate_failed', nav)

    # Generic overlay dismiss
    if task.get('dismiss_overlays', True):
        d = cu.dismiss_overlays()
        steps_log.append({'step': 'dismiss_overlays', 'dismissed': d.get('dismissed')})

    # Multi-tab preamble
    for tab in task.get('open_tabs') or []:
        cu.tab_new(tab.get('url'))
        steps_log.append({'step': 'tab_new', 'url': tab.get('url')})

    if task.get('open_tabs'):
        cu.tab_switch(0)

    # Explicit procedural steps still expressed as generic actions (not site ifs)
    for action in task.get('actions') or []:
        kind = action.get('op')
        if kind == 'click_text':
            r = cu.click_text(action['text'])
        elif kind == 'click':
            r = cu.click(action['selector'])
        elif kind == 'type':
            r = cu.type(action['selector'], action['text'])
        elif kind == 'scroll':
            r = cu.scroll(action.get('dy', 400))
        elif kind == 'wait':
            r = cu.wait(action.get('seconds', 1.0))
        elif kind == 'wait_for':
            r = cu.wait_for(selector=action.get('selector'), text=action.get('text'),
                            timeout_ms=action.get('timeout_ms', 15000))
        elif kind == 'download':
            r = cu.download(action['url'], action.get('filename'))
        elif kind == 'upload':
            r = cu.upload_file_field(action['selector'], action['path'])
        elif kind == 'navigate':
            r = cu.navigate(action['url'])
        elif kind == 'tab_new':
            r = cu.tab_new(action.get('url'))
        elif kind == 'tab_switch':
            r = cu.tab_switch(int(action['index']))
        elif kind == 'restart_context':
            r = cu.restart_context()
        elif kind == 'screenshot':
            r = cu.screenshot(action.get('name', 'brow.png'))
        elif kind == 'human_auth_pause':
            # Boundary: do not automate credentials for real auth
            cu.human_interventions += 1
            r = {'ok': True, 'paused': True, 'note': 'human auth boundary honored'}
        else:
            r = {'ok': False, 'error': f'unknown op {kind}'}
        steps_log.append({'step': kind, 'ok': r.get('ok') if isinstance(r, dict) else True})
        if isinstance(r, dict) and r.get('ok') is False and action.get('required', True):
            # Try recovery: re-observe + dismiss + re-nav start
            cu.recovery_count += 1
            cu.dismiss_overlays()
            if start:
                cu.navigate(start)
            steps_log.append({'step': 'recover_after_fail', 'from': kind})

    # Keyword-driven explore loop until goal met or budget exhausted
    keywords = list(goal.get('control_keywords') or [])
    type_into = goal.get('type_into')  # {keywords: [], text: ''}
    budget = int(task.get('max_actions') or max_actions)
    used = 0
    last_obs: dict[str, Any] = {}

    while used < budget:
        last_obs = cu.observe_controls()
        if _goal_met(last_obs, goal):
            break

        # Recovery if wrong page injected earlier and we're still off-goal
        if wrong and start and (wrong.split('/')[2] if '://' in wrong else '') in (last_obs.get('url') or ''):
            cu.recovery_count += 1
            cu.navigate(start)
            used += 1
            continue

        acted = False
        controls = last_obs.get('controls') or []

        if type_into and type_into.get('text'):
            ctrl = _pick_control(controls, type_into.get('keywords') or ['input', 'search', 'q'])
            if ctrl and ctrl.get('selector') and ctrl.get('tag') in {'input', 'textarea'}:
                cu.type(ctrl['selector'], type_into['text'])
                acted = True
                used += 1
                # try submit
                btn = _pick_control(controls, ['search', 'submit', 'go', 'find'])
                if btn and btn.get('selector'):
                    try:
                        cu.click(btn['selector'])
                        used += 1
                    except Exception:
                        pass
                type_into = None  # once
                continue

        if keywords:
            ctrl = _pick_control(controls, keywords)
            if ctrl:
                sel = ctrl.get('selector')
                if sel and not sel.startswith('text='):
                    r = cu.click(sel)
                    acted = True
                elif ctrl.get('text'):
                    r = cu.click_text(ctrl['text'][:40])
                    acted = True
                used += 1
                if acted:
                    # drop matched keyword soft
                    keywords = keywords[1:] if len(keywords) > 1 else keywords
                    continue

        # scroll to reveal more
        cu.scroll(500)
        used += 1
        if used >= 3 and not keywords and not type_into:
            break

        if not acted and used > 5:
            break

    last_obs = cu.observe_controls()
    ok = _goal_met(last_obs, goal)

    # Extra verifies
    for v in task.get('post_verify') or []:
        if v.get('file_exists'):
            from pathlib import Path
            import os
            desk = Path(os.environ.get('DESK_ROOT', '/mnt/data/keep-desk'))
            ok = ok and (desk / v['file_exists']).is_file()
        if v.get('contains'):
            ok = ok and v['contains'] in ((last_obs.get('text') or '') + (last_obs.get('title') or ''))

    m = cu.metrics()
    return {
        'id': task.get('id'),
        'category': task.get('category'),
        'brow': task.get('brow') or [],
        'ok': ok,
        'url': last_obs.get('url'),
        'title': last_obs.get('title'),
        'snip': (last_obs.get('text') or '')[:180],
        'steps': steps_log,
        'metrics': m,
        'elapsed_s': round(time.time() - t0, 2),
        'site_adapters': 0,  # architectural invariant
    }


def _fail(cu, task, steps, t0, reason, detail=None):
    return {
        'id': task.get('id'),
        'category': task.get('category'),
        'brow': task.get('brow') or [],
        'ok': False,
        'error': reason,
        'detail': detail,
        'steps': steps,
        'metrics': cu.metrics(),
        'elapsed_s': round(time.time() - t0, 2),
        'site_adapters': 0,
    }
