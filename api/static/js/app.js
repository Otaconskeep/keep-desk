/** OtaconsKeep Command Deck — briefing-first AI operator UI */
(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const api = window.KeepAPI;

  const state = {
    page: 'briefing',
    bots: [],
    jobs: [],
    approvals: [],
    handoffs: [],
    health: null,
    mission: null,
    briefing: null,
    browser: null,
    selectedBot: null,
    selectedJob: null,
    memory: null,
    chat: [],
  };

  const ICONS = {
    briefing: `<svg viewBox="0 0 24 24"><path d="M4 5h16v14H4z"/><path d="M8 9h8M8 12h8M8 15h5"/></svg>`,
    workspace: `<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`,
    browser: `<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 8h18"/></svg>`,
    work: `<svg viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg>`,
    intel: `<svg viewBox="0 0 24 24"><path d="M4 7a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V7z"/><path d="M8 11h8M8 15h5"/></svg>`,
  };

  function statusPill(s) {
    const v = (s || 'idle').toLowerCase().replace(/\s+/g, '_');
    const map = {
      running: 'pill-run',
      queued: 'pill-queued',
      done: 'pill-live',
      completed: 'pill-live',
      pending_approval: 'pill-warn',
      waiting: 'pill-queued',
      failed: 'pill-bad',
      rejected: 'pill-bad',
      live: 'pill-live',
      idle: 'pill-idle',
    };
    return `<span class="pill ${map[v] || 'pill-idle'}">${v.replace(/_/g, ' ')}</span>`;
  }

  function initials(name) {
    return (name || '?').split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  }

  function ago(ts) {
    if (!ts) return '';
    const t = typeof ts === 'number' ? ts * (ts < 1e12 ? 1000 : 1) : Date.parse(ts);
    if (!t) return '';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h`;
  }


  let _audioCtx = null;
  function playUiSound(kind = 'click') {
    try {
      _audioCtx = _audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const ctx = _audioCtx;
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.connect(g);
      g.connect(ctx.destination);
      const now = ctx.currentTime;
      if (kind === 'ok') {
        o.frequency.setValueAtTime(660, now);
        o.frequency.exponentialRampToValueAtTime(880, now + 0.06);
      } else if (kind === 'warn') {
        o.frequency.setValueAtTime(420, now);
      } else {
        o.frequency.setValueAtTime(520, now);
        o.frequency.exponentialRampToValueAtTime(280, now + 0.05);
      }
      g.gain.setValueAtTime(0.0001, now);
      g.gain.exponentialRampToValueAtTime(0.045, now + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.08);
      o.type = 'triangle';
      o.start(now);
      o.stop(now + 0.09);
    } catch (_) {}
  }

  function escapeHtml(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function setPage(id) {
    state.page = id;
    document.body.dataset.page = id;
    $$('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.page === id));
    $$('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${id}`));
    const labels = {
      briefing: ['Home', 'Mission'],
      workspace: ['Chat', 'Talk to the fleet'],
      browser: ['Live', 'Browser worker'],
      work: ['Work', 'Batches & jobs'],
      intel: ['Intel', 'Memory'],
    };
    const [title, meta] = labels[id] || ['Keep Desk', ''];
    $('#page-title').textContent = title;
    $('#page-meta').textContent = meta;
    if (id === 'browser') startViewportWatch();
    else stopViewportWatch();
    render();
  }

  async function refresh() {
    try {
      const [health, bots, jobs, approvals, handoffs, mission, memory, chat, briefing] =
        await Promise.all([
          api.health(),
          api.bots(),
          api.jobs(),
          api.approvals('pending'),
          api.handoffs(),
          api.mission().catch(() => null),
          api.memory().catch(() => null),
          api.chat(120).catch(() => ({ messages: [] })),
          api.briefing().catch(() => null),
        ]);
      state.health = health;
      state.bots = bots.bots || [];
      state.jobs = jobs.jobs || [];
      state.approvals = approvals.approvals || [];
      state.handoffs = handoffs.handoffs || [];
      state.mission = mission;
      state.memory = memory;
      state.chat = chat.messages || [];
      state.briefing = briefing;
      if (!state.selectedBot && state.bots[0]) state.selectedBot = state.bots[0].id;

      try {
        const [bh, obs] = await Promise.all([
          api.browserHealth().catch(() => null),
          api.browserObserve().catch(() => null),
        ]);
        state.browser = { health: bh, observe: obs };
      } catch (_) {}

      const attn = (health.pending_approvals || 0) + (health.running || 0);
      $('#live-status').textContent =
        attn > 0
          ? `${health.running || 0} live · ${health.pending_approvals || 0} need you`
          : 'desk idle · ready';
      $('#sys-dot').className = 'sys-dot' + (health.ok ? '' : ' deg');
      fillAskBot();
      render();
    } catch (e) {
      console.error(e);
      $('#live-status').textContent = 'link degraded';
      $('#sys-dot').className = 'sys-dot deg';
    }
  }

  function fillAskBot() {
    const sel = $('#ask-bot');
    if (!sel) return;
    const prev = sel.value || state.selectedBot;
    sel.innerHTML =
      `<option value="">Desk / Codec</option>` +
      state.bots
        .map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`)
        .join('');
    if (prev) sel.value = prev;
  }

  function renderContext() {
    const el = $('#context-body');
    if (!el) return;
    const approvals = state.approvals;
    const running = state.jobs.filter((j) => j.status === 'running').slice(0, 4);
    const meaning = state.briefing?.meaning || [];
    // Old failures live here / Workstreams — never on the main briefing once superseded
    const pastFails = state.jobs
      .filter((j) => j.status === 'failed')
      .slice(0, 4);
    const mode = state.briefing?.mode || '';
    el.innerHTML = `
      <div class="context-section">
        <h3>Needs you</h3>
        ${
          approvals.length
            ? approvals
                .map(
                  (a) => `
          <div style="margin-bottom:0.85rem;padding-bottom:0.85rem;border-bottom:1px solid var(--line)">
            <div class="mono">${escapeHtml(a.bot_id)} · ${escapeHtml(a.action || 'action')}</div>
            <div style="font-size:0.85rem;margin:0.35rem 0;color:var(--text-soft)">${escapeHtml((a.detail || '').slice(0, 140))}</div>
            <div style="display:flex;gap:0.4rem">
              <button class="btn btn-ok btn-sm" data-approve="${a.id}">Approve</button>
              <button class="btn btn-bad btn-sm" data-reject="${a.id}">Reject</button>
            </div>
          </div>`
                )
                .join('')
            : `<div class="empty">Nothing waiting on you</div>`
        }
      </div>
      <div class="context-section">
        <h3>Live work</h3>
        ${
          running.length
            ? running
                .map(
                  (j) => `
          <div class="list-row" data-goto-work="${j.id}">
            <div style="min-width:0">
              <div class="truncate">${escapeHtml(j.title)}</div>
              <div class="mono">${escapeHtml(j.bot_id)} · ${ago(j.updated_at)}</div>
            </div>
          </div>`
                )
                .join('')
            : `<div class="empty">Idle</div>`
        }
      </div>
      <div class="context-section">
        <h3>Meaning</h3>
        ${
          mode
            ? `<div class="mono" style="color:var(--ice);margin-bottom:0.5rem">mode · ${escapeHtml(mode)}</div>`
            : ''
        }
        ${
          meaning.length
            ? meaning
                .map(
                  (m) => `
          <div style="margin-bottom:0.75rem">
            <div class="mono" style="color:var(--signal)">${escapeHtml(m.label)}</div>
            <div style="font-size:0.85rem;color:var(--text-soft);margin-top:0.2rem">${escapeHtml(m.meaning)}</div>
          </div>`
                )
                .join('')
            : `<div class="empty">—</div>`
        }
      </div>
      <div class="context-section">
        <h3>Timeline · failures</h3>
        <p style="font-size:0.75rem;color:var(--muted);margin:0 0 0.6rem">Evidence only — does not override a completed mission on home.</p>
        ${
          pastFails.length
            ? pastFails
                .map(
                  (j) => `
          <div class="list-row" data-goto-work="${j.id}">
            <div style="min-width:0">
              <div class="truncate">${escapeHtml(j.title)}</div>
              <div class="mono">${escapeHtml(j.bot_id || '')} · ${ago(j.finished_at || j.updated_at)}</div>
            </div>
          </div>`
                )
                .join('')
            : `<div class="empty">No recent failures</div>`
        }
      </div>`;

    el.querySelectorAll('[data-approve]').forEach((b) => {
      b.onclick = async () => {
        await api.resolveApproval(b.dataset.approve, true);
        refresh();
      };
    });
    el.querySelectorAll('[data-reject]').forEach((b) => {
      b.onclick = async () => {
        await api.resolveApproval(b.dataset.reject, false);
        refresh();
      };
    });
    el.querySelectorAll('[data-goto-work]').forEach((b) => {
      b.onclick = () => {
        state.selectedJob = b.dataset.gotoWork;
        setPage('work');
      };
    });
  }

  function shotUrl(path) {
    const p = path || 'workspace/screenshots/live.png';
    return `/api/desk/file?path=${encodeURIComponent(p)}&t=${Date.now()}`;
  }

  function liveViewportUrl() {
    return `/api/browser/viewport.png?t=${Date.now()}`;
  }

  function extractUrls(text) {
    const re = /https?:\/\/[^\s<>"')\]]+/g;
    return [...new Set((text || '').match(re) || [])].slice(0, 3);
  }

  function linkCard(url, blurb) {
    let host = url;
    try {
      host = new URL(url).hostname.replace(/^www\./, '');
    } catch (_) {}
    return `
      <a class="link-card bevel bevel-ice" href="${escapeHtml(url)}" target="_blank" rel="noopener">
        <div class="link-card-shot">
          <img src="${liveViewportUrl()}" alt="" loading="lazy" onerror="this.style.opacity=.3" />
          <span class="shot-badge">live view</span>
        </div>
        <div class="link-card-body">
          <div class="lc-title">${escapeHtml(host)}</div>
          <div class="lc-url">${escapeHtml(url)}</div>
          ${blurb ? `<div class="lc-blurb">${escapeHtml(blurb)}</div>` : ''}
        </div>
      </a>`;
  }

  function formatMessageBody(text) {
    const raw = text || '';
    const urls = extractUrls(raw);
    let body = escapeHtml(raw);
    // soften raw URLs in text (cards carry the link)
    urls.forEach((u) => {
      body = body.split(escapeHtml(u)).join(`<span class="mono" style="color:var(--ice)">↗ link</span>`);
    });
    const cards = urls.map((u) => linkCard(u, '')).join('');
    return `<div class="msg-text">${body}</div>${cards}`;
  }

  function openDetailPopup(title, sub, html) {
    $('#detail-popup-title').textContent = title || 'Detail';
    $('#detail-popup-sub').textContent = sub || '';
    $('#detail-popup-body').innerHTML = html || '';
    $('#detail-popup').classList.add('open');
    $('#detail-popup').setAttribute('aria-hidden', 'false');
  }

  function closeDetailPopup() {
    $('#detail-popup')?.classList.remove('open');
    $('#detail-popup')?.setAttribute('aria-hidden', 'true');
  }

  function missionOwnsBrowser() {
    const b = state.briefing;
    if (!b) return false;
    if (b.mode === 'active') return true;
    const r = b.rationale;
    if (!r || r.hollow) return false;
    const sites = (r.sections || []).find((s) => s.id === 'sites');
    if (sites && (sites.urls || []).length) return true;
    if ((r.artifacts || []).length) return false;
    return false;
  }

  function isDeadLiveUrl(url) {
    const u = String(url || '').toLowerCase();
    if (!u || u === 'viewport' || u === '—' || u === '-') return true;
    return /example\.com|nosignal|about:blank|data:text\/html/.test(u);
  }

  function refreshHomeMonitor() {
    const img = $('#home-mon-img');
    const ws = $('#ws-live-shot');
    const wrap = $('#hx-live');
    const obs = state.browser?.observe || {};
    const url = obs.url || '';
    const dead = isDeadLiveUrl(url) && state.briefing?.mode !== 'active';
    const src = liveViewportUrl();
    if (ws) ws.src = src;
    if (img) {
      if (dead) {
        img.removeAttribute('src');
        img.style.opacity = '0.12';
      } else {
        img.src = src;
        img.style.opacity = '0.9';
      }
    }
    wrap?.classList.toggle('is-nosignal', !!dead);
    if ($('#home-mon-url')) {
      $('#home-mon-url').textContent = dead
        ? 'NO SIGNAL'
        : String(url || 'viewport').replace(/^https?:\/\//, '').slice(0, 28);
    }
    if ($('#home-mon-cap')) {
      $('#home-mon-cap').textContent = dead
        ? 'Parked · awaiting machine work'
        : obs.title
          ? String(obs.title).slice(0, 42)
          : 'Live feed';
    }
  }

  function renderBriefing() {
    const b = state.briefing;
    if (!b) {
      if ($('#home-lede')) $('#home-lede').textContent = 'Waiting for briefing…';
      return;
    }
    const p = b.progress || {};
    const batch = p.batch || {};
    const dod = b.definition_of_done || p.definition_of_done || [];
    const r = b.mode === 'active' ? null : b.rationale;

    document.body.dataset.page = 'briefing';

    const headline = (b.headline || 'Standing by').replace(/^Done —\s*/i, 'Done · ');
    if ($('#home-headline')) $('#home-headline').textContent = headline;
    if ($('#brief-headline')) $('#brief-headline').textContent = headline;
    if ($('#brief-speaker-label')) {
      $('#brief-speaker-label').textContent =
        b.mode === 'active' ? 'In progress' : b.mode === 'completed' ? 'Mission report' : 'Briefing';
    }

    const lede = _humanText(
      b.mode === 'active' || b.mode === 'blocker'
        ? b.objective
        : p.winner_line || r?.one_liner || b.objective || ''
    );
    if ($('#home-lede')) $('#home-lede').textContent = lede.slice(0, 180) || 'Ready when you are.';

    // Compact pills
    const strip = $('#home-status-strip');
    if (strip) {
      const runN = b.counts?.running ?? (b.mode === 'active' ? 1 : 0);
      const eta = p.eta_label || '—';
      const batchLab =
        batch.total > 1 ? `${batch.current || 0}/${batch.total}` : runN ? '1' : '—';
      strip.innerHTML = `
        <span class="hx-pill ${runN ? 'is-live' : ''}"><span>Run</span><b>${runN}</b></span>
        <span class="hx-pill"><span>ETA</span><b>${escapeHtml(String(eta))}</b></span>
        <span class="hx-pill ${p.pipeline_complete || b.mode === 'completed' ? 'is-done' : ''}"><span>Batch</span><b>${escapeHtml(String(batchLab))}</b></span>
        <span class="hx-pill"><span>Conf</span><b>${escapeHtml((b.confidence_level || '—').slice(0, 6))}</b></span>`;
    }

    // Traffic-light attention
    const attn = $('#hx-attn');
    const level = p.attention_level || (b.mode === 'failure' ? 'red' : b.mode === 'active' ? 'yellow' : 'green');
    if (attn) {
      attn.dataset.level = level;
      const lab =
        level === 'red' ? 'Blocked' : level === 'yellow' ? 'Working' : 'Clear';
      if ($('#hx-attn-lab')) $('#hx-attn-lab').textContent = lab;
      attn.title =
        level === 'red'
          ? 'Needs attention'
          : level === 'yellow'
            ? 'Mission in progress'
            : 'All clear';
    }

    // Done when — human checklist
    const doneN = dod.filter((d) => d.done).length;
    const allDone = dod.length > 0 && doneN === dod.length;
    $('#dod-card')?.classList.toggle('is-incomplete', !allDone);
    if ($('#dod-state')) {
      $('#dod-state').textContent = dod.length ? (allDone ? 'All set' : `${doneN} of ${dod.length}`) : '—';
    }
    if ($('#dod-list')) {
      $('#dod-list').innerHTML = dod.length
        ? dod
            .map(
              (d) => `
        <li class="${d.done ? 'is-done' : ''}">
          <span class="tick">${d.done ? '✓' : ''}</span>
          <span>
            <span class="lab">${escapeHtml(_humanText(d.label))}</span>
            ${d.detail ? `<span class="det">${escapeHtml(_humanText(d.detail))}</span>` : ''}
          </span>
        </li>`
            )
            .join('')
        : `<li><span class="tick"></span><span class="det">No checklist yet</span></li>`;
    }

    // Body kept empty on purpose — home stays clean
    if ($('#briefing-body')) $('#briefing-body').innerHTML = '';

    const retryId =
      b.latest_completed?.id ||
      b.rationale?.job_id ||
      (['done', 'failed'].includes(b.latest_job?.status) ? b.latest_job?.id : '') ||
      '';
    const canRetry =
      !!retryId &&
      b.mode !== 'active' &&
      (r?.hollow || b.mode === 'failure' || b.mode === 'completed');

    $('#briefing-actions').innerHTML = `
      ${
        b.mode === 'active'
          ? `<button class="btn btn-ember" type="button" data-action="go-browser" data-sfx="click">Watch</button>`
          : ''
      }
      ${
        canRetry
          ? `<button class="btn btn-ember" type="button" data-action="retry-job" data-job-id="${escapeHtml(retryId)}" data-sfx="click">Retry</button>`
          : ''
      }
      <button class="btn btn-ghost" type="button" data-action="open-rationale" data-sfx="click">Why</button>
      <button class="btn btn-ghost" type="button" data-action="ask-bot" data-sfx="click">Ask</button>`;

    refreshHomeMonitor();
  }

  function _humanText(s) {
    return String(s || '')
      .replace(/[*_#>`]+/g, '')
      .replace(/\s+/g, ' ')
      .replace(/^(Winner product|Recommended|Stage \d+.*?):\s*/i, '')
      .trim();
  }

  function renderMd(src) {
    const raw = String(src || '');
    if (!raw.trim()) return '';
    const lines = raw.replace(/\r\n/g, '\n').split('\n');
    const out = [];
    let i = 0;
    let inList = false;
    const closeList = () => {
      if (inList) {
        out.push('</ul>');
        inList = false;
      }
    };
    const inline = (t) => {
      let s = escapeHtml(t);
      s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      s = s.replace(/\*([^*]+)\*/g, '<em>$1</em>');
      s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
      return s;
    };
    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();
      // GFM table
      if (
        trimmed.includes('|') &&
        i + 1 < lines.length &&
        /^\s*\|?[\s:-]+\|/.test(lines[i + 1])
      ) {
        closeList();
        const headers = trimmed.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].includes('|')) {
          const cells = lines[i]
            .trim()
            .replace(/^\|/, '')
            .replace(/\|$/, '')
            .split('|')
            .map((c) => c.trim());
          if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells);
          i += 1;
        }
        out.push('<div class="study-table-wrap"><table class="study-table"><thead><tr>');
        headers.forEach((h) => out.push(`<th>${inline(h)}</th>`));
        out.push('</tr></thead><tbody>');
        rows.forEach((row) => {
          out.push('<tr>');
          headers.forEach((_, idx) => out.push(`<td>${inline(row[idx] || '')}</td>`));
          out.push('</tr>');
        });
        out.push('</tbody></table></div>');
        continue;
      }
      if (/^###\s+/.test(trimmed)) {
        closeList();
        out.push(`<h4 class="md-h">${inline(trimmed.replace(/^###\s+/, ''))}</h4>`);
        i += 1;
        continue;
      }
      if (/^##\s+/.test(trimmed)) {
        closeList();
        out.push(`<h3 class="md-h">${inline(trimmed.replace(/^##\s+/, ''))}</h3>`);
        i += 1;
        continue;
      }
      if (/^#\s+/.test(trimmed)) {
        closeList();
        out.push(`<h3 class="md-h">${inline(trimmed.replace(/^#\s+/, ''))}</h3>`);
        i += 1;
        continue;
      }
      if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
        if (!inList) {
          out.push('<ul class="md-list">');
          inList = true;
        }
        out.push(`<li>${inline(trimmed.replace(/^([-*]|\d+\.)\s+/, ''))}</li>`);
        i += 1;
        continue;
      }
      if (!trimmed) {
        closeList();
        i += 1;
        continue;
      }
      closeList();
      out.push(`<p class="md-p">${inline(trimmed)}</p>`);
      i += 1;
    }
    closeList();
    return out.join('');
  }

  function renderStudyMatrix(study) {
    if (!study) return '';
    const matrix = study.matrix;
    let table = '';
    if (matrix && matrix.headers && matrix.rows) {
      table = `<div class="study-table-wrap"><table class="study-table"><thead><tr>${matrix.headers
        .map((h) => `<th>${escapeHtml(h)}</th>`)
        .join('')}</tr></thead><tbody>${matrix.rows
        .map(
          (row) =>
            `<tr>${matrix.headers
              .map((_, i) => `<td>${escapeHtml(String(row[i] || '').replace(/\*\*/g, ''))}</td>`)
              .join('')}</tr>`
        )
        .join('')}</tbody></table></div>`;
    }
    const bars =
      study.options && study.options.length
        ? `<div class="study-bars">${study.options
            .map((o) => {
              const vals = Object.values(o.scores || {});
              // crude bar from presence of High/Medium/Low or $ amount
              let score = 40;
              const blob = vals.join(' ').toLowerCase();
              if (/\bhigh\b/.test(blob)) score += 30;
              if (/\bmedium\b/.test(blob)) score += 15;
              if (/\blow\b/.test(blob)) score += 5;
              if (study.winner && o.name.toLowerCase().includes(String(study.winner).toLowerCase().slice(0, 12)))
                score = Math.max(score, 85);
              return `<div class="study-bar-row">
                <span class="study-bar-lab">${escapeHtml(o.name)}</span>
                <span class="study-bar-track"><span class="study-bar-fill" style="width:${Math.min(100, score)}%"></span></span>
              </div>`;
            })
            .join('')}</div>`
        : '';
    const crit =
      (study.criteria || []).length
        ? `<div class="study-crit">${study.criteria
            .map((c) => `<span class="hx-pill"><b>${escapeHtml(c)}</b></span>`)
            .join('')}</div>`
        : '';
    const caveats = (study.caveats || [])
      .map((c) => `<div class="study-caveat">${escapeHtml(c)}</div>`)
      .join('');
    return `
      <div class="study-dossier">
        ${
          study.winner
            ? `<div class="study-winner"><span>Winner</span><b>${escapeHtml(study.winner)}</b></div>`
            : ''
        }
        ${crit}
        ${table}
        ${bars}
        ${
          study.why
            ? `<div class="study-why"><span>Why</span>${escapeHtml(study.why)}</div>`
            : ''
        }
        ${
          study.what_would_change
            ? `<div class="study-sens"><span>What would change the answer</span>${escapeHtml(
                study.what_would_change
              )}</div>`
            : ''
        }
        ${caveats}
        ${
          study.confidence
            ? `<div class="rat-meta">Confidence · ${escapeHtml(study.confidence)}</div>`
            : ''
        }
      </div>`;
  }

  function rationalePopupHtml(r) {
    if (!r) return '<p class="quiet-copy">No rationale available.</p>';
    const sections = r.sections || [];
    return `
      <div class="rationale dossier">
        ${sections
          .map((s) => {
            const why = s.why
              ? `<div class="rat-why"><span>Why</span>${escapeHtml(s.why)}</div>`
              : '';
            const meta = s.meta
              ? `<div class="rat-meta">${escapeHtml(s.meta)}</div>`
              : '';
            const link = s.url
              ? `<a class="rat-link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.url)}</a>`
              : '';
            const items = (s.items || []).length
              ? `<ul class="rat-list">${s.items.map((i) => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`
              : '';
            const urls = (s.urls || []).length
              ? `<ul class="rat-list rat-urls">${s.urls
                  .map(
                    (u) =>
                      `<li><a href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a></li>`
                  )
                  .join('')}</ul>`
              : '';
            const opts = (s.options || []).length
              ? `<ul class="rat-list rat-urls">${s.options
                  .map(
                    (o) =>
                      `<li><strong>${escapeHtml(o.roaster || '')}</strong> — ${escapeHtml(
                        o.product || ''
                      )}${
                        o.url
                          ? ` · <a href="${escapeHtml(o.url)}" target="_blank" rel="noopener">open</a>`
                          : ''
                      }</li>`
                  )
                  .join('')}</ul>`
              : '';
            const cand =
              s.candidates != null
                ? `<div class="rat-stat">${escapeHtml(String(s.candidates))} weighed</div>`
                : '';
            let bodyHtml = '';
            if (s.study) bodyHtml = renderStudyMatrix(s.study);
            else if (s.format === 'markdown' || s.id === 'trade' || s.id === 'shortlist' || s.id === 'picks' || s.id === 'cart')
              bodyHtml = `<div class="md-body">${renderMd(s.body || '')}</div>`;
            else if (s.body) bodyHtml = `<div class="rat-body">${escapeHtml(s.body)}</div>`;
            return `
          <section class="rat-section bevel ${s.id === 'trade' ? 'is-dossier' : ''}">
            <header>
              <h3>${escapeHtml(s.title || '')}</h3>
              ${cand}
            </header>
            ${bodyHtml}
            ${why}${meta}${link}${items}${urls}${opts}
          </section>`;
          })
          .join('')}
      </div>`;
  }

  function openDodPopup() {
    const b = state.briefing || {};
    const dod = b.definition_of_done || b.progress?.definition_of_done || [];
    const doneN = dod.filter((d) => d.done).length;
    const html = dod.length
      ? `<ul class="dod-list">${dod
          .map(
            (d) => `
        <li class="${d.done ? 'is-done' : ''}">
          <span class="tick">${d.done ? '✓' : ''}</span>
          <span>
            ${escapeHtml(d.label || '')}
            ${d.detail ? `<span class="dod-detail">${escapeHtml(String(d.detail).slice(0, 200))}</span>` : ''}
          </span>
        </li>`
          )
          .join('')}</ul>`
      : `<p class="quiet-copy">No definition of done yet.</p>`;
    openDetailPopup(
      'Definition of done',
      dod.length ? `${doneN}/${dod.length} met` : '',
      html
    );
  }

  function openBatchPopup() {
    const p = state.briefing?.progress || {};
    const batch = p.batch || {};
    const stages = batch.stages || [];
    const html = stages.length
      ? `<div class="rationale">${stages
          .map(
            (s) => `
        <section class="rat-section bevel">
          <header>
            <h3>${escapeHtml(s.label || '')}</h3>
            <div class="rat-stat">${escapeHtml(s.status || '')}</div>
          </header>
          ${s.summary ? `<div class="rat-body">${escapeHtml(s.summary)}</div>` : ''}
        </section>`
          )
          .join('')}</div>`
      : `<p class="quiet-copy">No batch pipeline on the current mission.</p>`;
    openDetailPopup(
      'Batch progress',
      batch.total > 1 ? `${batch.current}/${batch.total} · ${batch.label || ''}` : p.status_label || '',
      html
    );
  }

  function openRationalePopup() {
    const r = state.briefing?.rationale;
    const jobId = r?.job_id || state.briefing?.latest_job?.id || '';
    const retry =
      jobId && state.briefing?.mode !== 'active'
        ? `<button class="btn btn-ember" type="button" data-action="retry-job" data-job-id="${escapeHtml(jobId)}" style="margin-right:0.5rem">Retry</button>`
        : '';
    openDetailPopup(
      'Why this result',
      r?.duration_label ? `Took ${r.duration_label}` : r?.title || '',
      `${rationalePopupHtml(r)}<div style="margin-top:1.25rem;display:flex;gap:0.5rem;flex-wrap:wrap">${retry}</div>`
    );
  }

  async function retryJob(jobId) {
    const id = jobId || state.briefing?.latest_job?.id || state.briefing?.rationale?.job_id;
    if (!id) return;
    const btn = document.querySelector(`[data-action="retry-job"][data-job-id="${id}"]`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Retrying…';
    }
    try {
      const res = await api.retryJob(id);
      closeDetailPopup();
      setPage('work');
      await refresh();
      const newId = res?.job?.id;
      if (newId) {
        state.selectedJob = newId;
        renderWorkDetail();
      }
    } catch (err) {
      openDetailPopup('Retry failed', id, `<p class="quiet-copy">${escapeHtml(String(err.message || err))}</p>`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Retry';
      }
    }
  }

  function msgClass(m) {
    const from = (m.from || '').toLowerCase();
    if (from === 'operator' || from.startsWith('e2e')) return 'from-operator';
    if (from.startsWith('codec')) return 'from-codec';
    if (from === 'system') return 'from-system';
    return 'from-bot';
  }

  function renderWorkspace() {
    const stream = $('#ws-stream');
    if (!stream) return;
    const msgs = state.chat || [];
    const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 100;

    if (!msgs.length) {
      stream.innerHTML = `<div class="empty">No reports yet. Ask below, or assign work — STARTED / FINISHED land here automatically.</div>`;
    } else {
      stream.innerHTML = msgs
        .map((m) => {
          const who = m.from || '?';
          const kind = m.kind || 'chat';
          return `
        <div class="msg bevel ${msgClass(m)} kind-${escapeHtml(kind)}">
          <div class="msg-avatar">${initials(who.replace(/^bot:/, '').replace(/^codec:/, ''))}</div>
          <div class="msg-bubble">
            <div class="msg-meta">
              <strong>${escapeHtml(who)}</strong>
              <span class="pill pill-idle">${escapeHtml(kind)}</span>
              ${m.job_id ? `<span class="chip">${escapeHtml(m.job_id)}</span>` : ''}
              <span>${ago(m.ts)}</span>
            </div>
            ${formatMessageBody(m.text || '')}
          </div>
        </div>`;
        })
        .join('');
      if (atBottom) stream.scrollTop = stream.scrollHeight;
    }

    const active = state.jobs.find((j) => j.status === 'running') || state.briefing?.active_job;
    $('#ws-task-body').innerHTML = active
      ? `
        <div style="display:flex;gap:0.5rem;margin-bottom:0.5rem">${statusPill(active.status)}
          <span class="mono">${escapeHtml(active.bot_id)}</span></div>
        <div style="font-weight:600;color:var(--text)">${escapeHtml(active.title)}</div>
        <div class="quiet-copy" style="margin-top:0.4rem">${escapeHtml((active.brief || '').slice(0, 200))}</div>
        ${
          active.result_summary
            ? `<button class="detail-toggle" type="button" data-action="popup-task-result">Show result detail</button>`
            : ''
        }`
      : `<div class="quiet-copy">No live task. Use the command bar to ask or start work.</div>`;

    const busy = new Set(state.jobs.filter((j) => j.status === 'running').map((j) => j.bot_id));
    $('#ws-fleet-body').innerHTML = state.bots
      .map(
        (b) => `
      <div class="list-row">
        <div class="avatar ${busy.has(b.id) ? 'live' : ''}" style="background:${b.color || 'var(--ice)'}">${initials(b.name)}</div>
        <div style="min-width:0">
          <div class="truncate">${escapeHtml(b.name)}</div>
          <div class="mono">${busy.has(b.id) ? 'running' : 'idle'} · ${escapeHtml(b.role || '')}</div>
        </div>
      </div>`
      )
      .join('') || `<div class="empty">No agents</div>`;

    refreshHomeMonitor();
  }

  async function captureBrowser() {
    try {
      await api.browserShot();
      const obs = await api.browserObserve().catch(() => null);
      if (obs) state.browser = { ...(state.browser || {}), observe: obs };
      renderBrowser();
    } catch (e) {
      renderBrowser();
    }
  }

  function renderBrowser() {
    const obs = state.browser?.observe || {};
    const health = state.browser?.health || {};
    const url = obs.url || health.url || '—';
    const title = obs.title || '—';
    const text = (obs.text || '').slice(0, 500);
    const authish = /log in|login|sign in|password/i.test((obs.text || '') + (obs.title || ''));
    const active = state.jobs.find((j) => j.status === 'running');

    $('#bw-url').textContent = url;
    $('#bw-title').textContent = title;
    $('#bw-objective').textContent = active
      ? `${active.bot_id}: ${active.title}`
      : state.briefing?.objective || 'No active browse objective';
    $('#bw-auth').className = 'auth-line' + (authish ? '' : ' clear');
    $('#bw-auth').textContent = authish
      ? 'Auth boundary — human takeover preferred. Do not give the bot secrets.'
      : 'Session clear · open or authenticated surface';

    const img = $('#bw-img');
    const ph = $('#bw-placeholder');
    img.onload = () => {
      img.style.display = 'block';
      ph.style.display = 'none';
    };
    img.onerror = () => {
      img.style.display = 'none';
      ph.style.display = 'grid';
    };
    img.src = `/api/browser/viewport.png?t=${Date.now()}`;

    $('#bw-strip').innerHTML = `
      <span>tabs ${health.tabs ?? obs.tabs ?? '—'}</span>
      <span>stream 2s</span>
      <span>${health.ok ? 'browser healthy' : 'checking…'}</span>
      <span>${authish ? 'auth risk' : 'session ok'}</span>
    `;

    const ckpts = state.mission?.checkpoints || [];
    $('#bw-checkpoints').innerHTML = ckpts.length
      ? ckpts
          .slice(0, 8)
          .map((c) => `<div class="chip" style="display:block;margin-bottom:0.35rem">${escapeHtml(c)}</div>`)
          .join('')
      : `<div class="mono">No checkpoints on desk</div>`;

    $('#bw-trace').textContent = text || 'Viewport streams while this page is open.';
  }

  let viewportTimer = null;
  function startViewportWatch() {
    stopViewportWatch();
    viewportTimer = setInterval(() => {
      if (state.page === 'browser') {
        api
          .browserObserve()
          .then((obs) => {
            state.browser = { ...(state.browser || {}), observe: obs };
            renderBrowser();
          })
          .catch(() => renderBrowser());
      }
    }, 2000);
  }
  function stopViewportWatch() {
    if (viewportTimer) {
      clearInterval(viewportTimer);
      viewportTimer = null;
    }
  }

  function renderWork() {
    const sel = $('#task-bot');
    const prev = sel.value || state.selectedBot;
    sel.innerHTML = state.bots
      .map((b) => `<option value="${b.id}">${escapeHtml(b.name)} — ${escapeHtml(b.role)}</option>`)
      .join('');
    if (prev) sel.value = prev;

    const jobs = state.jobs.slice(0, 40);
    $('#task-list').innerHTML = jobs.length
      ? jobs
          .map(
            (j) => `
      <div class="task-card ${state.selectedJob === j.id ? 'active' : ''}" data-job="${j.id}">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:0.5rem">
          ${statusPill(j.status)}
          <span class="mono">${escapeHtml(j.bot_id)}</span>
        </div>
        <h3>${escapeHtml(j.title)}</h3>
        ${
          j.stage_label
            ? `<div class="chip" style="margin:0.35rem 0">batch ${escapeHtml(j.stage_label)}</div>`
            : ''
        }
        <div class="quiet-copy">${escapeHtml((j.brief || '').slice(0, 140))}</div>
      </div>`
          )
          .join('')
      : `<div class="empty">No workstreams yet</div>`;

    $('#task-list').querySelectorAll('[data-job]').forEach((el) => {
      el.onclick = () => {
        state.selectedJob = el.dataset.job;
        renderWorkDetail();
        $$('.task-card', $('#task-list')).forEach((c) =>
          c.classList.toggle('active', c.dataset.job === state.selectedJob)
        );
      };
    });
    renderWorkDetail();
  }

  function renderWorkDetail() {
    const j = state.jobs.find((x) => x.id === state.selectedJob) || state.jobs[0];
    const box = $('#task-detail');
    if (!j) {
      box.innerHTML = `<div class="quiet-copy">Select a workstream</div>`;
      return;
    }
    state.selectedJob = j.id;
    const log = (j.log || []).map((x) => x.line || JSON.stringify(x)).join('\n');
    box.innerHTML = `
      <h2 style="margin-bottom:0.5rem">Detail</h2>
      <div style="font-size:1.1rem;font-weight:500;margin-bottom:0.5rem">${escapeHtml(j.title)}</div>
      <div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.75rem">
        ${statusPill(j.status)}
        <span class="chip">${escapeHtml(j.bot_id)}</span>
      </div>
      <div class="quiet-copy" style="margin-bottom:1rem">${escapeHtml(j.brief || '')}</div>
      ${
        j.status === 'done' || j.status === 'failed'
          ? `<div style="margin-bottom:1rem"><button class="btn btn-ember" type="button" data-action="retry-job" data-job-id="${escapeHtml(j.id)}">Retry</button></div>`
          : ''
      }
      ${
        j.result_summary
          ? `<div style="margin-bottom:1rem"><div class="mono" style="margin-bottom:0.35rem">RESULT</div><div>${escapeHtml(j.result_summary)}</div></div>`
          : ''
      }
      <div class="mono" style="margin-bottom:0.35rem">TRACE</div>
      <div class="trace">${escapeHtml(log || 'No log yet')}</div>
    `;
  }

  function renderIntel() {
    const mem = state.memory || {};
    $('#mem-cards').innerHTML = `
      <div class="intel-card">
        <div class="icon">◈</div>
        <h3>Agent memory</h3>
        <p class="quiet-copy">${mem.bot_dirs ?? 0} roots under /desk/memory</p>
      </div>
      <div class="intel-card">
        <div class="icon">◉</div>
        <h3>Evidence</h3>
        <p class="quiet-copy">${mem.evidence_n ?? 0} status artifacts</p>
      </div>
      <div class="intel-card">
        <div class="icon">◎</div>
        <h3>Skills</h3>
        <p class="quiet-copy">${state.health?.skills ?? 0} skills · ${state.health?.routines ?? 0} routines</p>
      </div>`;
    const rows = mem.evidence || [];
    $('#mem-evidence').innerHTML = rows.length
      ? rows
          .map(
            (e) => `
      <div class="evidence-row">
        <span class="mono">${escapeHtml(e.kind || 'artifact')}</span>
        <span>${escapeHtml(e.name)}</span>
        <span class="mono">${escapeHtml(e.mtime || '')}</span>
      </div>`
          )
          .join('')
      : `<div class="empty" style="padding:1rem">No evidence indexed</div>`;
  }

  function render() {
    renderContext();
    if (state.page === 'briefing') renderBriefing();
    if (state.page === 'workspace') renderWorkspace();
    if (state.page === 'browser') renderBrowser();
    if (state.page === 'work') renderWork();
    if (state.page === 'intel') renderIntel();
  }

  async function handleAsk(bridge) {
    const input = $('#ask-input');
    const text = (input?.value || '').trim();
    if (!text) return;

    // Natural language work order → auto-routed job (no fleet picker)
    const wantsWork =
      /\b(browse|search|research|look up|find|check|run|test|write|fix|validate|monitor|compare|trade study|shortlist|shop|buy|cart)\b/i.test(
        text
      ) && text.length > 24;

    if (wantsWork) {
      await api.createJob({
        bot_id: '',
        auto_route: true,
        title: text.slice(0, 80),
        brief: text,
      });
      input.value = '';
      setPage('workspace');
      await refresh();
      return;
    }

    if (bridge) await api.postCodec(text);
    else await api.postChat(text, false);
    input.value = '';
    setPage('workspace');
    await refresh();
  }

  function openApprovalsSheet() {
    const sheet = $('#approvals-sheet');
    const body = $('#approvals-sheet-body');
    if (!sheet || !body) return;
    const approvals = state.approvals || [];
    body.innerHTML = approvals.length
      ? approvals
          .map(
            (a) => `
        <div style="margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--line)">
          <div class="mono">${escapeHtml(a.bot_id)} · ${escapeHtml(a.action || 'action')}</div>
          <div style="margin:0.4rem 0;color:var(--text-soft);font-size:0.9rem">${escapeHtml((a.detail || '').slice(0, 240))}</div>
          <div style="display:flex;gap:0.4rem">
            <button class="btn btn-ok btn-sm" type="button" data-approve="${a.id}">Approve</button>
            <button class="btn btn-bad btn-sm" type="button" data-reject="${a.id}">Reject</button>
          </div>
        </div>`
          )
          .join('')
      : `<div class="empty">Nothing waiting on you right now.</div>`;
    body.querySelectorAll('[data-approve]').forEach((b) => {
      b.onclick = async () => {
        await api.resolveApproval(b.dataset.approve, true);
        await refresh();
        openApprovalsSheet();
      };
    });
    body.querySelectorAll('[data-reject]').forEach((b) => {
      b.onclick = async () => {
        await api.resolveApproval(b.dataset.reject, false);
        await refresh();
        openApprovalsSheet();
      };
    });
    sheet.classList.add('open');
    sheet.setAttribute('aria-hidden', 'false');
  }

  function closeApprovalsSheet() {
    const sheet = $('#approvals-sheet');
    if (!sheet) return;
    sheet.classList.remove('open');
    sheet.setAttribute('aria-hidden', 'true');
  }

  function focusAsk(placeholder) {
    const input = $('#ask-input');
    if (!input) return;
    if (placeholder) input.placeholder = placeholder;
    input.focus();
    input.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }


  function loadBootBriefing() {
    try {
      const el = document.getElementById('keep-boot');
      if (!el) return false;
      const raw = (el.textContent || '').trim();
      if (!raw || raw === 'null') return false;
      const boot = JSON.parse(raw);
      if (!boot || !boot.ok) return false;
      state.briefing = boot;
      renderBriefing();
      return true;
    } catch (_) {
      return false;
    }
  }

  function bootSting() {
    try {
      playUiSound('ok');
      setTimeout(() => playUiSound('click'), 90);
      setTimeout(() => playUiSound('ok'), 180);
    } catch (_) {}
  }

  function wire() {
    $$('.nav-btn').forEach((b) => {
      b.innerHTML = `${ICONS[b.dataset.page] || ''}<span class="tip">${b.dataset.tip}</span>`;
      b.onclick = () => setPage(b.dataset.page);
    });
    $('.brand').onclick = () => setPage('briefing');

    // Durable action routing — survives briefing re-renders
    document.addEventListener('click', (e) => {
      const t = e.target.closest('[data-action]');
      if (!t) return;
      const act = t.dataset.action;
      if (t.dataset.sfx) playUiSound(t.dataset.sfx);
      else playUiSound('click');
      if (act === 'ask-bot') {
        setPage('workspace');
        setTimeout(() => focusAsk('Ask your bot what to do next…'), 50);
      } else if (act === 'go-browser') {
        setPage('browser');
      } else if (act === 'go-work') {
        setPage('work');
      } else if (act === 'open-approvals') {
        openApprovalsSheet();
      } else if (act === 'toggle-brief-detail') {
        const panel = $('#brief-detail-panel');
        const btn = $('#brief-detail-toggle');
        panel?.classList.toggle('open');
        btn?.classList.toggle('open');
        if (btn) btn.textContent = panel?.classList.contains('open') ? 'Hide status' : 'More status';
      } else if (act === 'open-rationale') {
        openRationalePopup();
      } else if (act === 'open-dod') {
        openDodPopup();
      } else if (act === 'open-batch') {
        openBatchPopup();
      } else if (act === 'open-full-brief') {
        openRationalePopup();
      } else if (act === 'retry-job') {
        retryJob(t.dataset.jobId);
      } else if (act === 'popup-task-result') {
        const active = state.jobs.find((j) => j.status === 'running') || state.briefing?.active_job;
        openDetailPopup(
          active?.title || 'Result',
          active?.bot_id || '',
          `<div class="quiet-copy" style="white-space:pre-wrap;color:var(--text)">${escapeHtml(active?.result_summary || '')}</div>`
        );
      }
    });

    $('#approvals-sheet-close')?.addEventListener('click', closeApprovalsSheet);
    $('#approvals-sheet')?.addEventListener('click', (e) => {
      if (e.target === $('#approvals-sheet')) closeApprovalsSheet();
    });
    $('#detail-popup-close')?.addEventListener('click', closeDetailPopup);
    $('#detail-popup')?.addEventListener('click', (e) => {
      if (e.target === $('#detail-popup')) closeDetailPopup();
    });

    $('#assign-btn').onclick = async () => {
      await api.createJob({
        bot_id: '',
        auto_route: true,
        title: $('#task-title').value.trim() || 'Untitled',
        brief: $('#task-brief').value.trim() || '(no brief)',
      });
      $('#task-title').value = '';
      $('#task-brief').value = '';
      setPage('work');
      refresh();
    };

    $('#shot-btn').onclick = () => captureBrowser();
    $('#refresh-btn').onclick = () => refresh();

    $('#ask-send-btn').onclick = () => handleAsk(true);
    $('#ask-desk-btn').onclick = () => handleAsk(false);
    $('#ask-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleAsk(true);
      }
    });
  }

  wire();
  const hadBoot = loadBootBriefing();
  setPage('briefing');
  if (hadBoot) bootSting();
  refresh();
  setInterval(refresh, 6000);
  setInterval(refreshHomeMonitor, 2500);
})();
