/** Keep Desk API client */
const api = {
  async req(path, opts = {}) {
    const r = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      ...opts,
    });
    if (!r.ok) {
      const t = await r.text();
      throw new Error(t || r.statusText);
    }
    const ct = r.headers.get('content-type') || '';
    if (ct.includes('application/json')) return r.json();
    return r;
  },
  health: () => api.req('/api/health'),
  bots: () => api.req('/api/bots'),
  jobs: (q = '') => api.req('/api/jobs' + (q ? `?${q}` : '')),
  job: (id) => api.req(`/api/jobs/${id}`),
  createJob: (body) => api.req('/api/jobs', { method: 'POST', body: JSON.stringify(body) }),
  retryJob: (id) => api.req(`/api/jobs/${id}/retry`, { method: 'POST', body: '{}' }),
  approvals: (status = 'pending') => api.req(`/api/approvals?status=${status}`),
  resolveApproval: (id, approve) =>
    api.req(`/api/approvals/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ approve, resolved_by: 'operator' }),
    }),
  handoffs: () => api.req('/api/handoffs'),
  skills: () => api.req('/api/skills'),
  threads: () => api.req('/api/threads'),
  routines: () => api.req('/api/routines'),
  mission: () => api.req('/api/mission'),
  briefing: () => api.req('/api/briefing'),
  browserHealth: () => api.req('/api/browser/health'),
  browserObserve: () => api.req('/api/browser/observe'),
  browserShot: () => api.req('/api/browser/screenshot', { method: 'POST', body: '{}' }),
  memory: () => api.req('/api/memory'),
  chat: (limit = 80) => api.req(`/api/chat?limit=${limit}`),
  postChat: (text, codec = false) =>
    api.req('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ text, codec, from_id: 'operator' }),
    }),
  postCodec: (text) =>
    api.req('/api/chat/codec', {
      method: 'POST',
      body: JSON.stringify({ text, from_id: 'operator' }),
    }),
};

window.KeepAPI = api;
