"""Auto-route work orders to a Keep Bot — operator should not pick ENGINEER by hand."""
from __future__ import annotations

import re


def route_bot(text: str, *, bots: list[dict] | None = None) -> str:
    """Pick a bot id from free-text intent. Falls back to researcher then engineer."""
    t = (text or '').lower()
    available = {b.get('id') for b in (bots or []) if b.get('id')}

    def pick(*candidates: str) -> str | None:
        for c in candidates:
            if not available or c in available:
                return c
        return None

    # Explicit @mention / name wins
    for bid, names in (
        ('engineer', ('engineer', 'eng', 'coder')),
        ('researcher', ('researcher', 'research', 'scout')),
        ('qa', ('qa', 'tester', 'quality')),
        ('pm', ('pm', 'project manager', 'manager')),
    ):
        if re.search(rf'\b({"|".join(names)})\b', t):
            hit = pick(bid)
            if hit:
                return hit

    researchish = any(
        k in t
        for k in (
            'research', 'find', 'look up', 'search', 'browse', 'shop', 'buy',
            'roaster', 'coffee', 'compare', 'trade study', 'shortlist', 'cart',
            'web', 'news', 'summarize', 'scoop',
        )
    )
    codeish = any(
        k in t
        for k in (
            'code', 'patch', 'debug', 'repo', 'python', 'fix', 'implement',
            'script', 'test suite', 'compile', 'lint',
        )
    )
    qaish = any(k in t for k in ('verify', 'regression', 'reproduce bug', 'qa '))
    pmish = any(k in t for k in ('status', 'handoff', 'plan sprint', 'roadmap', 'prioritize'))

    if researchish and not codeish:
        return pick('researcher', 'engineer') or 'researcher'
    if qaish:
        return pick('qa', 'engineer') or 'qa'
    if pmish and not researchish:
        return pick('pm', 'engineer') or 'pm'
    if codeish:
        return pick('engineer', 'researcher') or 'engineer'
    return pick('researcher', 'engineer', 'pm', 'qa') or 'researcher'


def criteria_lock(parent_brief: str) -> dict:
    """Extract or invent (with disclosure) trade-study criteria from the parent brief.

    Returns weights where cost defaults to 0 unless the operator prized budget/cost.
    """
    text = parent_brief or ''
    low = text.lower()
    prizes_cost = any(
        k in low
        for k in (
            'cheap', 'budget', 'lowest price', 'cost matters', 'prize cost',
            'price matters', 'affordable', 'under $', 'cheapest',
        )
    )
    # Named criteria hints
    criteria = []
    if any(k in low for k in ('taste', 'flavor', 'cup', 'acidity', 'origin')):
        criteria.append(('taste_origin', 0.35))
    if any(k in low for k in ('quality', 'specialty', 'single-origin', 'single origin', 'geisha')):
        criteria.append(('quality_signal', 0.35))
    if any(k in low for k in ('reputation', 'roaster', 'local', 'tucson')):
        criteria.append(('roaster_reputation', 0.2))
    if any(k in low for k in ('everyday', 'daily', 'staple')):
        criteria.append(('everyday_fit', 0.1))

    if not criteria:
        # Quality-first defaults when operator didn't specify
        criteria = [
            ('taste_origin', 0.35),
            ('quality_signal', 0.35),
            ('roaster_reputation', 0.2),
            ('everyday_fit', 0.1),
        ]
        invented = True
    else:
        invented = False

    cost_w = 0.25 if prizes_cost else 0.0
    if cost_w > 0:
        # renormalize lightly
        total = sum(w for _, w in criteria) + cost_w
        criteria = [(n, round(w / total, 3)) for n, w in criteria]
        criteria.append(('cost', round(cost_w / total, 3)))
    else:
        criteria.append(('cost', 0.0))

    return {
        'criteria': [{'id': n, 'weight': w} for n, w in criteria],
        'cost_is_decision_variable': prizes_cost,
        'invented_defaults': invented,
        'note': (
            'Operator prized cost/budget — cost is a scored variable.'
            if prizes_cost
            else 'Cost weight = 0 (not a decision variable unless operator says so).'
        ),
    }


def criteria_brief_block(parent_brief: str) -> str:
    lock = criteria_lock(parent_brief)
    lines = [
        'CRITERIA LOCK (mandatory — do not invent a different framework):',
        lock['note'],
    ]
    for c in lock['criteria']:
        lines.append(f"- {c['id']}: weight={c['weight']}")
    if lock['invented_defaults']:
        lines.append(
            'Defaults used because parent brief did not name variables. '
            'If continuity/taste conflict appears, stop and ask via codec/approval — do not silently invent.'
        )
    lines.append(
        'Deliverable must include: criteria list, comparison table, score matrix '
        '(criteria × options), winner under these weights, and “what would change the answer”.'
    )
    return '\n'.join(lines)
