"""Background job worker — local RTX 3090 brain, routines, shared desk computer."""
from __future__ import annotations

import json
import logging
import os
import re
import time
import traceback

from brain import Brain
from routines import fire_due
from store import Store
from tools import TOOL_SCHEMAS, ToolRunner

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('keep-bots-worker')

MAX_STEPS = int(os.environ.get('KEEP_BOTS_MAX_STEPS', '16'))
BROWSE_MAX_STEPS = int(os.environ.get('KEEP_BOTS_BROWSE_MAX_STEPS', '28'))
POLL_SEC = float(os.environ.get('KEEP_BOTS_POLL_SEC', '2'))
APPROVALS = os.environ.get('APPROVALS_REQUIRED', 'true').lower() == 'true'
ROUTINES_DISABLED = os.environ.get('ROUTINES_DISABLED', '0') == '1'

SYSTEM_TEMPLATE = """You are {name}, a Keep Desk Bot on OtaconsKeep.
You are a LOCAL-ONLY agent running on an RTX 3090 (Ollama). No cloud APIs.

Role: {role}
Mandate: {mandate}

Shared computer (/desk): filesystem, shell (git/python/pytest), persistent browser, memory, skills.
You are NOT a chatbot. Do real work with tools, then finish(summary=...).

Rules:
- Prefer artifacts under workspace/ and memory/{bot_id}/.
- News / wiki / generic "look up": web_research is OK; still browser_navigate when LIVE must move.
- SHOPPING / Amazon / Newegg / product shortlists: browser_navigate FIRST to a real search or product URL.
  Do NOT finish a shopping stage on web_research alone — LIVE must show real product pages.
  Prefer /dp/ or concrete listing pages over /s?k= search SERPs when picking.
- Use browser_content / browser_click_text after navigate. Amazon is an SPA — wait and re-read content.
- http_fetch is for simple static GETs only — it returns text_excerpt; never pipe it into shell stdin.
- shell has NO stdin from other tools. Never use sys.stdin.read().
- Do not wander to shopping sites unless the brief asks.
- Use handoff / group_post to coordinate with other Bots.
- Save reusable workflows with skill_save.
- Never claim production Keep/REX/media/HA changes — those stay REX-gated.
- If a tool returns pending_approval, stop.
- When you have enough findings, desk_write them, then finish(summary=...).
- Never desk_write an empty or placeholder shortlist. If the page is a bot wall, say so and retry navigate.
- Job start/finish auto-notify the operator via Keep Desk chat + Codec. Use operator_chat / codec_transmit for mid-job updates.
"""

BROWSE_ADDENDUM = """
THIS IS A MULTI-PART RESEARCH / WEB JOB.
Follow the brief in order. Do not stop after the first finding.

Typical tools:
- room_list + group_post to talk in Keep Desk rooms
- browser_navigate + browser_content FIRST for Amazon/Newegg/shopping (LIVE must move off NO SIGNAL)
- web_research only as a supplement after at least one real navigate — never as the only evidence
- youtube_transcript(url=...) after you find a YouTube video
- desk_write for each deliverable (proposal, shopping pick, final report) with REAL URLs + prices
- operator_chat for mid-job human updates
- finish only when EVERY part of the brief is done

Write the final report in plain human language — like briefing a friend, not a system log.
No jargon stacks, no "as an AI", no bullet telemetry dumps.

Shopping (Amazon etc.) is ALLOWED when the brief asks for it.
Forbidden: shell+stdin parsing; repeating the same failing tool; finishing early;
empty shortlists; inventing prices without opening a page; leaving LIVE on NO SIGNAL all job.
Watch mode: browser_navigate updates workspace/screenshots/live.png — use it.
"""


def _bot_system(bot: dict) -> str:
    return SYSTEM_TEMPLATE.format(
        name=bot.get('name') or bot['id'],
        role=bot.get('role') or 'worker',
        mandate=bot.get('mandate') or 'Complete assigned jobs.',
        bot_id=bot['id'],
    )


def _is_shopping_job(job: dict) -> bool:
    blob = f"{job.get('title') or ''} {job.get('brief') or ''} {job.get('parent_brief') or ''}".lower()
    stage = (job.get('stage_id') or '').lower()
    if stage in ('shortlist', 'picks', 'study', 'cart'):
        return True
    keys = (
        'amazon', 'newegg', 'ebay', 'cart', 'checkout', 'trade study', 'shortlist',
        'homelab', 'mini pc', 'optiplex', 'thinkcentre', 'elitedesk', 'shoes',
        'roaster', 'coffee', 'under $', 'under $', 'listing', 'product page',
        'buy ', 'shop', 'sku',
    )
    return any(k in blob for k in keys)


def _is_browse_job(job: dict) -> bool:
    blob = f"{job.get('title') or ''} {job.get('brief') or ''}".lower()
    keys = (
        'browse', 'google', 'news', 'search the web', 'look for', 'look up',
        'website', 'http://', 'https://', 'duckduckgo', 'wikipedia', 'find news',
        'metal gear', 'web research', 'online', 'youtube', 'amazon', 'transcript',
        'proposal', 'shoes', 'price', 'room', 'homelab', 'newegg',
        # shopping / local research (coffee, cart, find X, etc.)
        'find ', 'find the', 'roaster', 'coffee', 'cart', 'shop', 'buy ',
        'order', 'store', 'tucson', 'beans', 'trade study',
    )
    return any(k in blob for k in keys) or _is_shopping_job(job)


def _is_multipart_job(job: dict) -> bool:
    # Pipeline stages are already one batch — do not keep nudging "continue next part"
    if job.get('pipeline_id') and job.get('stage_index') is not None:
        return False
    brief = (job.get('brief') or '').lower()
    markers = (
        'then ', 'also ', 'after that', 'after you', 'amazon', 'proposal', 'transcript',
        '1)', '2)', '3)', 'step ', 'finally', 'and then', 'then after', 'shoes',
        'cart', 'trade study', 'one from each',
    )
    return sum(1 for m in markers if m in brief) >= 2 or 'amazon' in brief or 'cart' in brief


def _notify_operator(*, bot_id: str, job_id: str, text: str, kind: str, codec: bool) -> None:
    try:
        from chat_bus import post_message
        post_message(
            from_id=f'bot:{bot_id}',
            text=text,
            kind=kind,
            job_id=job_id,
            bot_id=bot_id,
            codec=codec,
        )
    except Exception as e:
        log.warning('operator notify failed: %s', e)


def _artifact_is_hollow(text: str) -> bool:
    """True if a shortlist/picks write is empty, placeholder, or search-SERP-only junk."""
    body = (text or '').strip()
    if len(body) < 80:
        return True
    low = body.lower()
    if any(p in low for p in ('todo', 'tbd', 'placeholder', 'no results', 'could not find', '(empty)')):
        if low.count('http') < 2:
            return True
    urls = re.findall(r'https?://[^\s\)\]\>\"\']+', body)
    if not urls:
        return True
    # Search SERPs alone are weak evidence for picks/study
    productish = [
        u for u in urls
        if any(x in u.lower() for x in ('/dp/', '/gp/product', '/p/', 'item=', 'product/', '/itm/'))
    ]
    search_only = urls and not productish and all(
        any(x in u.lower() for x in ('/s?', '/s/', 'search?', 'pl?d=', 'k=')) for u in urls
    )
    if search_only and 'winner' not in low and 'criteria' not in low:
        # shortlist may use search URLs; picks/recommendation should not be SERP-only
        return False  # allow shortlist SERPs; stricter check applied by stage
    return False


def _picks_need_concrete_urls(text: str) -> bool:
    """Picks/study should prefer concrete listing pages over /s?k= SERPs."""
    urls = re.findall(r'https?://[^\s\)\]\>\"\']+', text or '')
    if not urls:
        return True
    concrete = [
        u for u in urls
        if any(x in u.lower() for x in ('/dp/', '/gp/product', '/p/', 'item=', '/itm/'))
    ]
    return len(concrete) == 0


def _browse_ready(trace: list, job: dict | None = None) -> tuple[bool, str]:
    tools = [t.get('tool') for t in (trace or [])]
    shopping = _is_shopping_job(job or {})
    stage = ((job or {}).get('stage_id') or '').lower()

    if shopping:
        if 'browser_navigate' not in tools:
            return False, (
                'Shopping jobs require browser_navigate to a real Amazon/Newegg/product URL '
                'before finish (LIVE must leave NO SIGNAL). web_research alone is not enough.'
            )
    else:
        if 'web_research' not in tools and 'browser_navigate' not in tools:
            return False, 'Browse jobs require web_research or browser_navigate before finish.'

    wrote = False
    wrote_body = ''
    wrote_path = ''
    for t in (trace or []):
        if t.get('tool') != 'desk_write':
            continue
        res = t.get('result') or {}
        args = t.get('args') or {}
        if res.get('ok') and int(res.get('bytes') or 0) > 20:
            path = str(res.get('path') or args.get('path') or '')
            wrote = True
            wrote_path = path
            content = args.get('content')
            if isinstance(content, str):
                wrote_body = content
            else:
                try:
                    from tools import DESK_ROOT
                    p = DESK_ROOT / path
                    if p.is_file():
                        wrote_body = p.read_text(errors='replace')
                except Exception:
                    pass
            if 'research' in path or path.endswith('.md'):
                break
    if not wrote:
        return False, 'Browse jobs require a successful desk_write of findings (path under workspace/research/*.md) before finish.'

    if shopping and _artifact_is_hollow(wrote_body):
        return False, (
            f'Hollow artifact blocked ({wrote_path or "desk_write"}). '
            'Write a real shortlist/picks with names, https URLs, and prices — not empty/placeholder text.'
        )
    if stage in ('picks',) and _picks_need_concrete_urls(wrote_body):
        # Allow SERP URLs only if LIVE navigate happened and prices are present
        if not ('$' in wrote_body and 'browser_navigate' in tools and len(wrote_body) > 200):
            return False, (
                'Picks need concrete product URLs (/dp/, /p/, item=) or at least '
                'browser_navigate + ballpark $ prices — not a hollow search-SERP dump.'
            )
    return True, 'ok'


def _deliverable_matches_brief(job: dict, write_result: dict | None = None) -> tuple[bool, str]:
    """Block finish when the written summary/path is clearly a different mission."""
    try:
        from briefing import _off_brief_mismatch
    except Exception:
        _off_brief_mismatch = None  # type: ignore
    arts: dict[str, str] = {}
    summary = (job.get('result_summary') or '')
    for t in (job.get('tool_trace') or []):
        if t.get('tool') != 'desk_write':
            continue
        path = (t.get('args') or {}).get('path') or (t.get('result') or {}).get('path')
        if not path:
            continue
        try:
            from tools import DESK_ROOT
            p = DESK_ROOT / str(path)
            if p.is_file():
                arts[str(path)] = p.read_text(errors='replace')[:4000]
        except Exception:
            pass
    if write_result and write_result.get('path'):
        try:
            from tools import DESK_ROOT
            p = DESK_ROOT / str(write_result['path'])
            if p.is_file():
                arts[str(write_result['path'])] = p.read_text(errors='replace')[:4000]
                summary = arts[str(write_result['path'])][:600] or summary
        except Exception:
            pass
    probe = dict(job)
    if summary and not probe.get('result_summary'):
        probe['result_summary'] = summary
    if _off_brief_mismatch and _off_brief_mismatch(probe, arts):
        return False, (
            'Deliverable is OFF-BRIEF (looks like coffee/cart/AI-news residue). '
            'desk_write findings that match THIS brief (soda images / pick), then finish.'
        )
    brief = f"{job.get('parent_brief') or ''} {job.get('brief') or ''} {job.get('title') or ''}".lower()
    for path in arts:
        pl = path.lower()
        if 'ai_news' in pl and not any(k in brief for k in ('news', 'youtube', 'transcript', 'ai ')):
            return False, f'{path} is not a valid deliverable for this brief.'
        if 'pipeline_cart' in pl and not any(k in brief for k in ('cart', 'buy', 'checkout', 'purchase')):
            if any(k in brief for k in ('soda', 'image', 'photo', 'picture')):
                return False, 'Cart artifact is wrong for an image-pick brief.'
    return True, 'ok'


def _summary_from_artifact(write_result: dict) -> str:
    """Build a short finish summary from the just-written research file."""
    try:
        from tools import DESK_ROOT
        rel = (write_result or {}).get('path') or ''
        p = DESK_ROOT / rel
        if not p.is_file():
            return ''
        text = p.read_text(errors='replace').strip()
        # first ~3 non-empty lines / 600 chars
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:6]
        body = '\n'.join(lines)[:600]
        return body or text[:600]
    except Exception:
        return ''


def _close_job(store: Store, job: dict, bot: dict, *, status: str, summary: str, codec: bool) -> None:
    # Chat line first (fast), then status — avoids validator race with Codec latency
    verb = 'FINISHED' if status == 'done' else 'FAILED'
    stage_bit = ''
    if job.get('pipeline_id') and job.get('stage_label'):
        stage_bit = f" · stage {job.get('stage_label')}"

    # Last-chance: never celebrate / advance off-brief "done"
    if status == 'done':
        try:
            from briefing import _off_brief_mismatch
            if _off_brief_mismatch(dict(job, result_summary=summary)):
                status = 'failed'
                verb = 'FAILED'
                summary = f'HARD FAILURE — off-brief finish blocked. {summary or ""}'[:2000]
                store.patch_job(job['id'], {'hollow': True, 'off_brief': True})
        except Exception:
            pass

    _notify_operator(
        bot_id=bot['id'],
        job_id=job['id'],
        text=(
            f'{verb} job {job["id"]}{stage_bit}: {job.get("title")}\n'
            f'Summary: {(summary or "")[:1200]}'
        ),
        kind='result' if status == 'done' else 'status',
        codec=codec,
    )
    patch = {
        'status': status,
        'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'result_summary': (summary or '')[:2000],
    }
    if status == 'failed' and 'off-brief' in (summary or '').lower():
        patch['hollow'] = True
        patch['off_brief'] = True
    store.patch_job(job['id'], patch)
    store.append_job_log(job['id'], f'{status}: {summary}')
    _park_browser_after_job(job)

    if status == 'done' and job.get('pipeline_id'):
        try:
            from job_batches import advance_pipeline
            fresh = store.get_job(job['id']) or job
            nxt = advance_pipeline(store, fresh, summary=summary or '')
            if nxt:
                _notify_operator(
                    bot_id=bot['id'],
                    job_id=nxt['id'],
                    text=(
                        f'PIPELINE queued next batch: {nxt.get("stage_label") or nxt.get("title")}\n'
                        f'Job {nxt["id"]} (stage {(nxt.get("stage_index") or 0) + 1}/'
                        f'{nxt.get("stage_total") or "?"})'
                    ),
                    kind='status',
                    codec=True,
                )
            else:
                _notify_operator(
                    bot_id=bot['id'],
                    job_id=job['id'],
                    text=(
                        f'PIPELINE complete — all {job.get("stage_total") or "?"} stages finished '
                        f'for “{job.get("parent_title") or job.get("title")}”.'
                    ),
                    kind='result',
                    codec=True,
                )
        except Exception as e:
            log.warning('pipeline advance failed: %s', e)

    if status == 'failed' and (patch.get('off_brief') or 'off-brief' in (summary or '').lower()):
        if not job.get('auto_retried'):
            try:
                _auto_retry_clean(store, job, bot)
            except Exception as e:
                log.warning('auto retry failed: %s', e)


def _auto_retry_clean(store: Store, job: dict, bot: dict) -> None:
    """Queue a fresh parent-brief job in a new research namespace after off-brief failure."""
    title = (job.get('parent_title') or job.get('title') or 'Untitled').strip()
    brief = (job.get('parent_brief') or '').strip()
    if not brief:
        return
    title = re.sub(r'\s·\s\d+/\d+\s·.*$', '', title).strip()
    title = re.sub(r'\s*\(retry\)\s*$', '', title, flags=re.I).strip()
    title = f'{title} (auto-retry)'[:160]
    store.patch_job(job['id'], {'auto_retried': True})
    from bot_route import route_bot
    from job_batches import expand_into_pipeline, should_batch
    bot_id = route_bot(f'{title}\n{brief}', bots=store.list_bots()) or bot['id']
    nxt = store.create_job(
        bot_id=bot_id,
        title=title,
        brief=brief,
        priority=job.get('priority') or 'normal',
        created_by='auto_retry_off_brief',
        thread_id=job.get('thread_id'),
    )
    if should_batch(title, brief):
        nxt = expand_into_pipeline(store, nxt) or nxt
    store.append_job_log(nxt['id'], f"auto_retry_of {job['id']} clean_namespace")
    _notify_operator(
        bot_id=bot_id,
        job_id=nxt['id'],
        text=(
            f'AUTO-RETRY queued after off-brief failure of {job["id"]}.\n'
            f'Fresh research dir: {nxt.get("research_dir") or "(single job)"}\n'
            f'Job {nxt["id"]}'
        ),
        kind='status',
        codec=True,
    )



def _park_browser_after_job(job: dict) -> None:
    """Park on NO SIGNAL snow — never leave example.com / prior shopping tabs as 'LIVE'."""
    tools = {t.get('tool') for t in (job.get('tool_trace') or [])}
    # Keep last real page for successful browse stages
    if tools & {'browser_navigate', 'web_research', 'browser_click_text', 'youtube_transcript'}:
        return
    try:
        from tools import _browser_json
        # Local set_content — no cross-service navigate (avoids hangs / example.com)
        _browser_json('POST', '/park', {})
    except Exception:
        pass


def run_job(store: Store, brain: Brain, job: dict) -> None:
    # Late-bind batching if a multipart job slipped through unstaged
    try:
        from job_batches import expand_into_pipeline, should_batch
        if (
            not job.get('pipeline_id')
            and should_batch(job.get('title') or '', job.get('brief') or '')
        ):
            job = expand_into_pipeline(store, job) or job
            # Follow-on stages are 'waiting'; this job is stage 0 and already running
            job = store.get_job(job['id']) or job
    except Exception as e:
        log.warning('batch expand failed: %s', e)

    bot = store.get_bot(job['bot_id'])
    if not bot:
        store.patch_job(job['id'], {
            'status': 'failed',
            'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'result_summary': f"unknown bot {job['bot_id']}",
        })
        return

    browse = _is_browse_job(job)
    multipart = _is_multipart_job(job)
    # Image shortlist stages get more steps — browsing burns clicks fast
    max_steps = BROWSE_MAX_STEPS if browse else MAX_STEPS
    if (job.get('stage_id') or '') in ('images', 'shortlist') or 'image' in (job.get('stage_label') or '').lower():
        max_steps = max(max_steps, 36)

    rdir = job.get('research_dir') or ''
    if rdir:
        system = _bot_system(bot) + (
            f"\n\nMISSION RESEARCH DIR (mandatory): {rdir}/\n"
            f"desk_write ONLY under that folder. "
            f"NEVER read or write workspace/research/pipeline_*.md or ai_news_*.md "
            f"unless this brief explicitly asks for AI news.\n"
        ) + (BROWSE_ADDENDUM if browse else '')
    else:
        system = _bot_system(bot) + (BROWSE_ADDENDUM if browse else '')
    if multipart:
        max_steps = max(max_steps, 40)
    # Batched stages: keep focused, but image shortlist needs headroom for clicks
    if job.get('pipeline_id') is not None:
        cap = 36 if (job.get('stage_id') or '') in ('images', 'shortlist') else 22
        max_steps = min(max(max_steps, 18), cap)
        multipart = False
    store.append_job_log(
        job['id'],
        f"claimed local-brain={brain.model} browse={browse} multipart={multipart} max_steps={max_steps}",
    )
    _notify_operator(
        bot_id=bot['id'],
        job_id=job['id'],
        text=(
            f'STARTED job {job["id"]}: {job.get("title")}\n'
            f'Brief: {(job.get("brief") or "")[:500]}\n'
            f'Mode: {"shopping/browser_navigate" if _is_shopping_job(job) else ("browse/web_research" if browse else "desk")} · watching on :5765'
            + (f'\nResearch dir: {rdir}' if rdir else '')
        ),
        kind='status',
        codec=True,
    )
    runner = ToolRunner(store, bot['id'], job['id'], approvals_required=APPROVALS)
    # keep `system` from research_dir injection above — do not rebuild bare
    user = (
        f"Job title: {job.get('title')}\n"
        f"Brief:\n{job.get('brief')}\n\n"
        f"Use tools. When done, call finish. Stay on-brief — do exactly what was asked."
    )
    if rdir:
        user += (
            f"\n\nWrite artifacts ONLY under {rdir}/. "
            f"Ignore leftover files in workspace/research/pipeline_*.md from other missions."
        )
    if browse:
        if _is_shopping_job(job):
            user += (
                "\n\nSHOPPING MODE — Start NOW with browser_navigate to a real Amazon or Newegg "
                "search/product URL from the brief (e.g. https://www.amazon.com/s?k=...). "
                "LIVE must leave NO SIGNAL. Then browser_content / click into listings. "
                "web_research is optional supplement ONLY after at least one navigate. "
                "desk_write a NON-EMPTY shortlist/picks with https URLs and $ prices before finish. "
                "Prefer /dp/ product pages for picks. Do not use shell."
            )
        else:
            user += (
                "\n\nStart with web_research OR browser_navigate using a concise query/URL from the brief. "
                "If the brief names a URL, browser_navigate there so LIVE updates. "
                "Do not use shell. desk_write findings before finish."
            )
    # Early write nudge for image/shopping shortlist — don't burn all steps clicking
    if (job.get('stage_id') or '') in ('images', 'shortlist'):
        user += (
            "\n\nBy step ~10 you MUST desk_write the shortlist/images file for this stage "
            "with real https links — even if imperfect — then finish. "
            "Do not click forever. Do not write an empty file."
        )
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': user},
    ]

    recent_sigs: list[str] = []
    used_tools: set[str] = set()

    for step in range(max_steps):
        fresh = store.get_job(job['id'])
        if fresh and fresh.get('status') == 'pending_approval':
            store.append_job_log(job['id'], 'paused — pending approval')
            _notify_operator(
                bot_id=bot['id'], job_id=job['id'],
                text=f'PAUSED job {job["id"]} — pending approval',
                kind='status', codec=False,
            )
            return

        try:
            raw = None
            last_err = None
            for attempt in range(3):
                try:
                    raw = brain.chat(messages, tools=TOOL_SCHEMAS)
                    break
                except Exception as e:
                    last_err = e
                    store.append_job_log(job['id'], f'brain retry {attempt+1}/3: {e}')
                    time.sleep(2 + attempt * 2)
            if raw is None:
                raise last_err or RuntimeError('brain failed')
            msg = brain.assistant_message(raw)
        except Exception as e:
            store.append_job_log(job['id'], f'brain error: {e}')
            _close_job(store, job, bot, status='failed', summary=str(e)[:500], codec=True)
            return

        messages.append(msg)
        tool_calls = msg.get('tool_calls') or []
        content = (msg.get('content') or '').strip()
        if content:
            store.append_job_log(job['id'], f'assistant: {content[:400]}')

        if not tool_calls:
            if step < max_steps - 1 and not content:
                messages.append({'role': 'user', 'content': 'Use a tool or call finish.'})
                continue
            if browse:
                ok, reason = _browse_ready(list((store.get_job(job['id']) or {}).get('tool_trace') or []), job)
                # Model often narrates "Job complete" / finish(...) without a tool call
                doneish = bool(re.search(
                    r'\b(job complete|done|finished|finish\s*\()', content or '', re.I))
                if ok and (doneish or step >= max_steps - 3):
                    summary = content or 'browse research complete'
                    # strip accidental tool-call prose
                    summary = re.sub(r'finish\s*\(\s*summary\s*=\s*["\']?', '', summary, flags=re.I)
                    summary = summary.strip(' "\')') or 'browse research complete'
                    _close_job(store, job, bot, status='done', summary=summary[:2000], codec=True)
                    return
                if not ok and step < max_steps - 1:
                    messages.append({
                        'role': 'user',
                        'content': (
                            f'{reason} Then call the finish tool with summary=... '
                            '(actual tool call, not prose).'
                        ),
                    })
                    continue
                if ok:
                    messages.append({
                        'role': 'user',
                        'content': 'Requirements met. Call the finish tool now with a short summary.',
                    })
                    continue
            summary = content or 'completed without tool calls'
            _close_job(store, job, bot, status='done', summary=summary, codec=True)
            return

        for tc in tool_calls:
            fn = (tc.get('function') or {})
            name = fn.get('name') or ''
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except json.JSONDecodeError:
                args = {}
            sig = f"{name}:{json.dumps(args, sort_keys=True)[:220]}"
            recent_sigs.append(sig)
            store.append_job_log(job['id'], f'tool {name}({json.dumps(args)[:300]})')

            # Gate finish on browse requirements + on-brief deliverable
            if name == 'finish' and browse:
                ok, reason = _browse_ready(list((store.get_job(job['id']) or {}).get('tool_trace') or []), job)
                if ok:
                    ok2, reason2 = _deliverable_matches_brief(store.get_job(job['id']) or job)
                    if not ok2:
                        ok, reason = ok2, reason2
                if not ok:
                    store.append_job_log(job['id'], f'finish_blocked: {reason}')
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': tc.get('id') or name,
                        'content': json.dumps({'error': reason, 'finish_blocked': True}),
                    })
                    messages.append({'role': 'user', 'content': reason + ' Then call finish again.'})
                    runner.finished = False
                    continue

            result = runner.run(name, args)
            used_tools.add(name)
            trace = list((store.get_job(job['id']) or {}).get('tool_trace') or [])
            trace.append({'tool': name, 'args': args, 'result': _clip_result(result)})
            store.patch_job(job['id'], {'tool_trace': trace[-100:]})
            messages.append({
                'role': 'tool',
                'tool_call_id': tc.get('id') or name,
                'content': json.dumps(result)[:12000],
            })
            if runner.needs_approval:
                store.append_job_log(job['id'], 'stopped for approval')
                return
            if runner.finished:
                # Last-chance off-brief reject (model called finish via tool runner)
                if browse:
                    ok_b, reason_b = _deliverable_matches_brief(
                        store.get_job(job['id']) or job,
                    )
                    if not ok_b:
                        store.append_job_log(job['id'], f'finish_blocked: {reason_b}')
                        runner.finished = False
                        messages.append({
                            'role': 'user',
                            'content': reason_b + ' Fix the deliverable, then finish.',
                        })
                        continue
                _close_job(
                    store, job, bot,
                    status='done',
                    summary=runner.finish_summary or 'done',
                    codec=True,
                )
                return

            # After a successful research write: auto-finish ONLY for simple on-brief jobs.
            if browse and name == 'desk_write' and isinstance(result, dict) and result.get('ok'):
                ok, _reason = _browse_ready(
                    list((store.get_job(job['id']) or {}).get('tool_trace') or []),
                    job,
                )
                on_brief, brief_reason = _deliverable_matches_brief(
                    store.get_job(job['id']) or job, result,
                )
                multipart = _is_multipart_job(job)
                if ok and on_brief and not multipart:
                    summary = _summary_from_artifact(result) or (
                        f'Research saved to {result.get("path")} '
                        f'({result.get("bytes")} bytes).'
                    )
                    store.append_job_log(
                        job['id'],
                        f'auto_finish after successful desk_write ({result.get("path")})',
                    )
                    _close_job(store, job, bot, status='done', summary=summary, codec=True)
                    return
                if not on_brief:
                    messages.append({
                        'role': 'user',
                        'content': brief_reason,
                    })
                elif multipart and ok:
                    messages.append({
                        'role': 'user',
                        'content': (
                            f'Saved {result.get("path")}. Multi-part job — continue the NEXT '
                            'requirement in the brief (do not finish yet). Post a short '
                            'operator_chat update, then keep going.'
                        ),
                    })
                elif not ok:
                    messages.append({
                        'role': 'user',
                        'content': (
                            f'Wrote {result.get("path")} but requirements incomplete. {_reason} '
                            'Then continue or finish when the whole brief is done.'
                        ),
                    })

            # After a good transcript — ONLY nudge AI-news/Amazon when the brief asked for it
            if name == 'youtube_transcript' and isinstance(result, dict) and result.get('ok'):
                blob = f"{job.get('brief') or ''} {job.get('title') or ''}".lower()
                if any(k in blob for k in ('news', 'youtube', 'transcript', 'amazon', 'shoe')):
                    messages.append({
                        'role': 'user',
                        'content': (
                            'Transcript is in hand. Do NOT fetch more videos. '
                            'desk_write the transcript findings the brief asked for, '
                            'then continue the NEXT requirement in the brief.'
                        ),
                    })
                else:
                    messages.append({
                        'role': 'user',
                        'content': (
                            'You pulled a YouTube transcript but this brief is NOT a news/Amazon job. '
                            'Ignore unrelated videos. Return to the brief deliverable and desk_write that.'
                        ),
                    })
            # If we keep researching without writing, break the loop
            if browse and 'desk_write' not in used_tools and len(used_tools) >= 6:
                if name in ('web_research', 'youtube_transcript', 'browser_navigate'):
                    messages.append({
                        'role': 'user',
                        'content': (
                            'STOP researching. You already have enough. '
                            'desk_write your findings now, then continue the next brief step.'
                        ),
                    })

            if len(recent_sigs) >= 3 and len(set(recent_sigs[-3:])) == 1:
                store.append_job_log(job['id'], 'loop_break: identical tool repeated')
                messages.append({
                    'role': 'user',
                    'content': (
                        'STOP repeating that tool. Use a different approach: '
                        + (
                            'browser_navigate to a product URL, browser_content, desk_write, then finish. '
                            if _is_shopping_job(job) else
                            'web_research or browser_navigate, desk_write findings, then finish. '
                        )
                        + 'Do not use shell with stdin.'
                    ),
                })
                recent_sigs.clear()

    _close_job(
        store, job, bot,
        status='failed',
        summary=f'hit max steps ({max_steps}) without finish',
        codec=True,
    )


def _clip_result(result: dict) -> dict:
    if not isinstance(result, dict):
        return {'value': str(result)[:500]}
    out = {}
    for k, v in result.items():
        if isinstance(v, str) and len(v) > 1500:
            out[k] = v[:1500] + '…'
        else:
            out[k] = v
    return out


def _idle_park_if_placeholder() -> None:
    """If LIVE is stuck on example.com / blank, park to NO SIGNAL snow."""
    try:
        from tools import _browser_json
        obs = _browser_json('GET', '/observe') or {}
        url = str(obs.get('url') or '').lower()
        if 'example.com' in url or url in ('about:blank', 'about:blank/', ''):
            _browser_json('POST', '/park', {})
    except Exception:
        pass


def main() -> None:
    state = os.environ.get('STATE_DIR', '/desk/state')
    store = Store(state)
    brain = Brain()
    log.info('Keep Bots worker LOCAL-ONLY %s', brain.info())
    _idle_park_if_placeholder()
    ticks = 0
    while True:
        try:
            ticks += 1
            if not ROUTINES_DISABLED and ticks % 15 == 1:
                fired = fire_due(store)
                if fired:
                    log.info('routines fired: %s', fired)
            # Periodically reclaim placeholder LIVE when idle
            if ticks % 30 == 0:
                try:
                    running = store.list_jobs(status='running')
                    if not running:
                        _idle_park_if_placeholder()
                except Exception:
                    pass
            job = store.claim_next_job()
            if not job:
                time.sleep(POLL_SEC)
                continue
            log.info('running %s for %s', job['id'], job['bot_id'])
            run_job(store, brain, job)
        except Exception:
            log.error('worker loop error:\n%s', traceback.format_exc())
            time.sleep(5)


if __name__ == '__main__':
    main()
