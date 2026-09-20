"""Split long multipart briefs into sequential pipeline stages.

Each stage is its own job with a focused brief and finish criteria, so the
local brain can complete a batch cleanly instead of stalling mid-mission.

Artifacts are ALWAYS namespaced under:
  workspace/research/<pipeline_id>/…
so a soda mission never reads leftover coffee pipeline_*.md files.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any


def research_dir(pipeline_id: str) -> str:
    pid = (pipeline_id or 'scratch').strip() or 'scratch'
    return f'workspace/research/{pid}'


def _is_simple_browse_write(low: str) -> bool:
    """Single browse + write a named file — must NOT become image/soda pipelines.

    Catches demos like: browse Wikipedia Arizona, write yt_demo_arizona.md summary.
    'YouTube demo' / 'summary' alone are NOT enough to imply image shortlist.
    """
    has_browse = any(k in low for k in ('browse ', 'open http', 'go to http', 'wikipedia', 'wiki/'))
    has_write = any(k in low for k in ('desk_write', 'write workspace/', 'write file', '.md with'))
    imageish = any(
        k in low
        for k in (
            'image', 'images', 'photo', 'photos', 'picture', 'pictures',
            'soda', 'pexels', 'unsplash', 'shortlist', 'google images',
            'find three', '3 images', 'three images',
        )
    )
    return has_browse and has_write and not imageish


def _is_image_media_mission(low: str) -> bool:
    """True only for explicit image/soda/media shortlist missions.

    Do NOT treat 'youtube' or 'summary' alone as image missions — that misfires
    on wiki summary demos and forces soda/image stages + fake store dossiers.
    """
    if _is_simple_browse_write(low):
        return False
    strong = any(
        k in low
        for k in (
            'image', 'images', 'photo', 'photos', 'picture', 'pictures',
            'soda', 'cola', 'pexels', 'unsplash', 'screenshot', 'google find',
            'google images', 'image shortlist', 'find three', '3 images',
            'three images', 'shortlist',
        )
    )
    # YouTube/synopsis only count when paired with product/media hunt language
    yt_media = any(k in low for k in ('youtube', 'synopsis')) and any(
        k in low
        for k in ('soda', 'product', 'image', 'photo', 'pick', 'winner', 'store', 'buy')
    )
    if not (strong or yt_media):
        return False
    return not any(
        k in low
        for k in ('roaster', 'coffee beans', 'add to cart', 'checkout')
    )


def _is_shopping_mission(low: str) -> bool:
    return any(
        k in low
        for k in (
            'roaster', 'roasters', 'coffee', 'beans', 'bag of', 'shoes',
            'amazon', 'newegg', 'ebay', 'cart', 'checkout', 'trade study', 'tucson',
            'homelab', 'mini pc', 'optiplex', 'under $', 'listing',
        )
    )


def _topic_keywords(text: str) -> list[str]:
    stop = {
        'stage', 'batched', 'complete', 'parent', 'goal', 'context', 'finish',
        'workspace', 'research', 'pipeline', 'write', 'then', 'with', 'from',
        'this', 'that', 'only', 'after', 'want', 'find', 'best', 'cart',
        'three', 'images', 'pick', 'the', 'and', 'for', 'you', 'your',
    }
    words = re.findall(r'[a-z][a-z0-9]{3,}', (text or '').lower())
    out = []
    for w in words:
        if w in stop or w in out:
            continue
        out.append(w)
        if len(out) >= 14:
            break
    return out


def artifact_matches_parent(path: Path, parent_brief: str, *, min_hits: int = 1) -> tuple[bool, str]:
    """True if file content shares topic keywords with the parent goal."""
    if not path.is_file():
        return False, f'missing artifact {path}'
    try:
        body = path.read_text(errors='replace').lower()
    except Exception as e:
        return False, str(e)
    keys = _topic_keywords(parent_brief)
    if not keys:
        return True, 'no keywords'
    hits = [k for k in keys if k in body]
    # Strong foreign shopping residue vs media brief
    parent_l = (parent_brief or '').lower()
    if _is_image_media_mission(parent_l):
        foreign = ('yellow brick', 'kenya', 'nyeri', 'presta coffee', 'exo roast', 'coffee roaster')
        if any(f in body for f in foreign) and not any(k in body for k in ('soda', 'cola', 'image', 'photo', 'youtube')):
            return False, 'artifact looks like prior coffee mission'
    if len(hits) < min_hits:
        return False, f'topic mismatch (hits={hits[:5]} need {min_hits} of {keys[:8]})'
    return True, f'ok hits={hits[:6]}'


def plan_stages(*, title: str, brief: str, pipeline_id: str | None = None) -> list[dict[str, str]]:
    """Return 1..N stage specs. Single-item list means no split.

    When pipeline_id is None, paths use the token {RESEARCH} for later rewrite.
    """
    full = f"{title or ''}\n{brief or ''}".strip()
    low = full.lower()
    parent = (brief or title or '').strip()
    rd = research_dir(pipeline_id) if pipeline_id else '{RESEARCH}'

    raw: list[dict[str, str]] = []

    # —— Simple browse → write file: NEVER split on "then" into image/soda steps ——
    if _is_simple_browse_write(low):
        return [{
            'id': 'main',
            'label': 'Main',
            'brief': (
                f'{parent}\n\n'
                'Operator note: use browser_navigate + browser_content so LIVE updates. '
                'Do NOT invent image shortlists, soda picks, product dossiers, or store carts. '
                'Write the requested file, then finish.'
            ),
        }]

    # —— Media / image → pick → YouTube → local store (NOT cart) ——
    if _is_image_media_mission(low):
        wants_yt = any(k in low for k in ('youtube', 'video', 'synopsis', 'summary'))
        wants_store = any(
            k in low
            for k in (
                'store', 'shop', 'buy', 'where to', 'ogden', 'walmart', 'harmons',
                "smith's", 'smiths', 'grocery', 'which store',
            )
        )
        raw.append({
            'id': 'images',
            'label': 'Image shortlist',
            'focus': (
                f'Go to Google (or Pexels/Unsplash) and find THREE distinct soda/image candidates '
                f'the parent goal asks for. '
                f'desk_write {rd}/images.md with for EACH: title, direct image or page URL, '
                f'one-line why it fits. '
                f'Do NOT open carts or coffee sites. '
                f'NEVER read workspace/research/pipeline_*.md (legacy global files — forbidden). '
                f'Then finish.'
            ),
        })
        raw.append({
            'id': 'pick',
            'label': 'Pick winner',
            'focus': (
                f'Read ONLY {rd}/images.md (ignore any other research files). '
                f'Pick ONE winner with stated criteria (taste/look/brand — not price unless asked). '
                f'desk_write {rd}/pick.md with winner name, URL, criteria, and why losers lost. '
                f'NEVER read workspace/research/pipeline_*.md. '
                f'Then finish. No YouTube/store yet.'
            ),
        })
        # Always close image missions with YT/synopsis/store dossier (never a cart stage)
        raw.append({
            'id': 'dossier',
            'label': 'YT + store',
            'focus': (
                f'Read ONLY {rd}/pick.md. '
                f'Find a real YouTube video about the winning soda/product; write a short synopsis. '
                f'If the parent goal names a city (e.g. Ogden, UT), recommend which local store '
                f'to buy it (Smith’s / Harmons / Walmart / etc.) with address or Maps link. '
                f'desk_write {rd}/dossier.md with: winner, YT URL + synopsis, store rec, why buy. '
                f'Do NOT add anything to an online cart. Do NOT write ai_news_*.md. '
                f'NEVER read workspace/research/pipeline_*.md. Then finish.'
            ),
        })
        return _finalize_stages(raw, parent, title)

    # —— Shopping / coffee / trade-study (namespaced; cart only if asked) ——
    wants_shortlist = any(
        k in low
        for k in (
            'find', 'best', 'roaster', 'roasters', 'look for', 'look up',
            'search', 'top ',
        )
    )
    wants_picks = any(
        k in low
        for k in (
            'bag', 'bags', 'bean', 'beans', 'one from each', 'product',
            'shoes', 'pair', 'item from each',
        )
    )
    wants_study = any(
        k in low
        for k in (
            'trade study', 'compare', 'which one', 'should get', 'recommend',
            'pick the', 'decide',
        )
    )
    wants_cart = any(
        k in low
        for k in ('cart', 'add to cart', 'add it to the cart', 'checkout')
    )
    # "buy" alone is not enough for cart when it's "which store to buy"
    if 'which store' in low or 'where to buy' in low or 'ogden' in low:
        wants_cart = False

    if wants_shortlist and (wants_picks or wants_study or wants_cart) and _is_shopping_mission(low):
        raw.append({
            'id': 'shortlist',
            'label': 'Shortlist',
            'focus': (
                f'browser_navigate to Amazon/Newegg search for what the parent goal asks '
                f'(LIVE must leave NO SIGNAL — do NOT use web_research-only). '
                f'browser_content / click listings. Name the top matches (at least 3, prefer 5). '
                f'desk_write {rd}/shortlist.md with: name, one-line why, https URL, ballpark $ for each. '
                f'NEVER write an empty shortlist. NEVER read workspace/research/pipeline_*.md. '
                f'Then finish. Do NOT pick SKUs or use a cart yet.'
            ),
        })
        if wants_picks:
            raw.append({
                'id': 'picks',
                'label': 'Pick products',
                'focus': (
                    f'Read ONLY {rd}/shortlist.md. '
                    f'browser_navigate into ONE concrete product/listing page per shortlisted option '
                    f'(prefer /dp/ or product pages — not only /s?k= search SERPs). '
                    f'desk_write {rd}/picks.md with name, concrete URL, ballpark price if visible. '
                    f'Then finish. No trade study or cart yet.'
                ),
            })
        if wants_study:
            from bot_route import criteria_brief_block
            lock = criteria_brief_block(parent)
            raw.append({
                'id': 'study',
                'label': 'Trade study',
                'focus': (
                    f'Read ONLY {rd}/picks.md (and shortlist). '
                    f'browser_navigate to the leading candidate’s listing so LIVE shows a real product page. '
                    f'Do a real trade study — not a cart note.\n\n'
                    f'{lock}\n\n'
                    f'desk_write {rd}/recommendation.md with ALL of: '
                    f'(1) criteria + weights, (2) comparison table, (3) score matrix, '
                    f'(4) ONE winner, (5) what would change the answer, (6) confidence. '
                    f'NEVER read workspace/research/pipeline_*.md. '
                    f'Then finish. Do NOT add to cart yet.'
                ),
            })
        if wants_cart:
            raw.append({
                'id': 'cart',
                'label': 'Cart',
                'focus': (
                    f'Read ONLY {rd}/recommendation.md. '
                    f'If that file mentions a different product category than the parent goal '
                    f'(e.g. coffee when parent asked soda), STOP and finish with failure — do not cart. '
                    f'Otherwise open the winner’s product URL and add to cart if possible. '
                    f'desk_write {rd}/cart.md with what you did and the URL. Then finish.'
                ),
            })

    if len(raw) <= 1:
        parts = [
            p.strip()
            for p in re.split(
                r'\b(?:then after you|then after|after that|and then|then|finally)\b',
                parent,
                flags=re.I,
            )
            if p and len(p.strip()) > 12
        ]
        if len(parts) >= 2:
            raw = []
            for i, part in enumerate(parts[:4], start=1):
                raw.append({
                    'id': f'step{i}',
                    'label': f'Step {i}',
                    'focus': (
                        f'Do ONLY this slice of the parent goal:\n{part}\n\n'
                        f'desk_write {rd}/step{i}.md with the result, '
                        f'then finish. NEVER read workspace/research/pipeline_*.md. '
                        f'Do not jump ahead to later slices.'
                    ),
                })

    if not raw:
        return [{
            'id': 'main',
            'label': 'Main',
            'brief': parent or title or '(no brief)',
        }]

    return _finalize_stages(raw, parent, title)


def _finalize_stages(raw: list[dict[str, str]], parent: str, title: str | None) -> list[dict[str, str]]:
    total = len(raw)
    return [
        {
            'id': s['id'],
            'label': f'{i}/{total} · {s["label"]}',
            'brief': _stage_brief(parent, n=i, total=total, focus=s['focus']),
        }
        for i, s in enumerate(raw, start=1)
    ]


def _stage_brief(parent: str, *, n: int, total: int, focus: str) -> str:
    return (
        f'STAGE {n} of {total} — BATCHED JOB (complete ONLY this stage, then finish).\n\n'
        f'Parent goal (for context — do not complete the whole thing now):\n{parent}\n\n'
        f'This stage focus:\n{focus}\n\n'
        'Rules: stay on this stage; desk_write ONLY under this mission’s research folder; '
        'call finish when THIS stage is done. Later stages are separate jobs. '
        'If prior-stage files contradict the parent goal, stop and finish with an error note — '
        'do not invent a cart from leftover missions.'
    )


def _rewrite_research_token(text: str, pipeline_id: str) -> str:
    return (text or '').replace('{RESEARCH}', research_dir(pipeline_id))


def should_batch(title: str, brief: str) -> bool:
    stages = plan_stages(title=title, brief=brief)
    return len(stages) >= 2


def expand_into_pipeline(store, job: dict) -> dict[str, Any]:
    """Turn a multipart job into stage-0 + waiting follow-ons."""
    if not job or job.get('pipeline_id') or job.get('stage_index') is not None:
        return job
    if (job.get('brief') or '').startswith('STAGE '):
        return job

    title = job.get('title') or 'Untitled'
    brief = job.get('brief') or title
    # First pass without id to decide count; second pass with real id for paths
    draft = plan_stages(title=title, brief=brief)
    if len(draft) < 2:
        return job

    pipeline_id = f"pipe_{uuid.uuid4().hex[:10]}"
    stages = plan_stages(title=title, brief=brief, pipeline_id=pipeline_id)
    parent_brief = brief
    parent_title = title

    # Create namespaced research dir + mission stamp
    try:
        import os
        desk = Path(os.environ.get('DESK_ROOT', '/desk'))
        rdir = desk / research_dir(pipeline_id)
        rdir.mkdir(parents=True, exist_ok=True)
        stamp = (
            f'# Mission {pipeline_id}\n\n'
            f'Title: {parent_title}\n\n'
            f'Brief:\n{parent_brief}\n\n'
            f'Keywords: {", ".join(_topic_keywords(parent_brief))}\n'
        )
        (rdir / 'MISSION.md').write_text(stamp, encoding='utf-8')
    except Exception:
        pass

    first = store.patch_job(job['id'], {
        'pipeline_id': pipeline_id,
        'stage_index': 0,
        'stage_total': len(stages),
        'stage_id': stages[0]['id'],
        'stage_label': stages[0]['label'],
        'title': f"{parent_title[:70]} · {stages[0]['label']}"[:160],
        'brief': _rewrite_research_token(stages[0]['brief'], pipeline_id),
        'parent_brief': parent_brief,
        'parent_title': parent_title,
        'research_dir': research_dir(pipeline_id),
        'pipeline_stages': [
            {
                'index': i,
                'id': s['id'],
                'label': s['label'],
                'job_id': job['id'] if i == 0 else None,
                'status': 'queued' if i == 0 else 'waiting',
            }
            for i, s in enumerate(stages)
        ],
    }) or job

    prev_id = job['id']
    for i, stage in enumerate(stages[1:], start=1):
        child = store.create_job(
            bot_id=job['bot_id'],
            title=f"{parent_title[:70]} · {stage['label']}"[:160],
            brief=_rewrite_research_token(stage['brief'], pipeline_id),
            priority=job.get('priority') or 'normal',
            created_by='pipeline',
            thread_id=job.get('thread_id'),
        )
        store.patch_job(child['id'], {
            'status': 'waiting',
            'pipeline_id': pipeline_id,
            'stage_index': i,
            'stage_total': len(stages),
            'stage_id': stage['id'],
            'stage_label': stage['label'],
            'parent_brief': parent_brief,
            'parent_title': parent_title,
            'research_dir': research_dir(pipeline_id),
            'depends_on_job': prev_id,
            'pipeline_root_job': job['id'],
        })
        root = store.get_job(job['id']) or {}
        plist = list(root.get('pipeline_stages') or [])
        if i < len(plist):
            plist[i]['job_id'] = child['id']
            store.patch_job(job['id'], {'pipeline_stages': plist})
        prev_id = child['id']
        store.append_job_log(child['id'], f"pipeline {pipeline_id} stage {i + 1}/{len(stages)} waiting")

    store.append_job_log(
        job['id'],
        f"batched into pipeline {pipeline_id}: {len(stages)} stages @ {research_dir(pipeline_id)}",
    )
    return store.get_job(job['id']) or first


def advance_pipeline(store, finished_job: dict, *, summary: str) -> dict | None:
    """Queue the next waiting stage after a successful stage finish."""
    pipeline_id = finished_job.get('pipeline_id')
    if not pipeline_id:
        return None
    idx = finished_job.get('stage_index')
    if idx is None:
        return None

    # Refuse to unlock next stage if this finish was off-brief / hollow
    if finished_job.get('off_brief') or finished_job.get('hollow'):
        return None
    try:
        from briefing import _off_brief_mismatch
        if _off_brief_mismatch(finished_job):
            return None
    except Exception:
        pass

    root_id = finished_job.get('pipeline_root_job') or (
        finished_job['id'] if finished_job.get('stage_index') == 0 else None
    )
    if root_id:
        root = store.get_job(root_id) or {}
        plist = list(root.get('pipeline_stages') or [])
        for s in plist:
            if s.get('job_id') == finished_job['id'] or s.get('index') == idx:
                s['status'] = 'done'
                s['summary'] = (summary or '')[:300]
        store.patch_job(root_id, {'pipeline_stages': plist})

    nxt = None
    for j in store.list_jobs():
        if j.get('pipeline_id') != pipeline_id:
            continue
        if j.get('stage_index') == (idx or 0) + 1 and j.get('status') == 'waiting':
            nxt = j
            break
    if not nxt:
        return None

    # Topic gate: namespaced prior artifacts must match parent goal
    parent = finished_job.get('parent_brief') or finished_job.get('brief') or ''
    try:
        import os
        desk = Path(os.environ.get('DESK_ROOT', '/desk'))
        rdir = desk / research_dir(pipeline_id)
        # Prefer newest mission file that exists
        for name in ('pick.md', 'images.md', 'recommendation.md', 'picks.md', 'shortlist.md', 'dossier.md'):
            p = rdir / name
            if p.is_file():
                ok, why = artifact_matches_parent(p, parent)
                if not ok:
                    store.append_job_log(
                        nxt['id'],
                        f'pipeline_blocked: prior artifact off-topic ({why})',
                    )
                    store.patch_job(nxt['id'], {
                        'status': 'cancelled',
                        'result_summary': f'Blocked — prior stage artifact off-topic: {why}',
                    })
                    return None
                break
    except Exception:
        pass

    prior = (summary or '').strip()[:800]
    brief = nxt.get('brief') or ''
    if prior and 'PRIOR STAGE RESULT' not in brief:
        brief = (
            f"{brief}\n\nPRIOR STAGE RESULT (use this — do not redo stage "
            f"{(idx or 0) + 1}):\n{prior}\n"
            f"\nUse ONLY files under {research_dir(pipeline_id)}/. "
            f"Ignore workspace/research/pipeline_*.md forever.\n"
        )
    store.patch_job(nxt['id'], {
        'status': 'queued',
        'brief': brief,
        'prior_stage_summary': prior,
    })
    store.append_job_log(
        nxt['id'],
        f"unlocked after {finished_job.get('id')} — queued stage {(idx or 0) + 2}",
    )
    if root_id:
        root = store.get_job(root_id) or {}
        plist = list(root.get('pipeline_stages') or [])
        for s in plist:
            if s.get('job_id') == nxt['id']:
                s['status'] = 'queued'
        store.patch_job(root_id, {'pipeline_stages': plist})
    return store.get_job(nxt['id'])
