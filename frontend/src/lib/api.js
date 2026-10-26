const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:4000/api';
const TOKEN_KEY = 'bc_token';

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(status, message, details) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function request(path, { method = 'GET', body, raw = false } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    tokenStore.clear();
    window.dispatchEvent(new Event('bc:unauthorized'));
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.error ?? res.statusText, data.details);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

const qs = (params) => {
  const clean = Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== false);
  return clean.length ? `?${new URLSearchParams(clean)}` : '';
};

export const api = {
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => request('/auth/me'),
  leads: (filters) => request(`/leads${qs(filters)}`),
  stats: () => request('/leads/stats'),
  updateLead: (id, patch) => request(`/leads/${id}`, { method: 'PATCH', body: patch }),
  deleteLead: (id) => request(`/leads/${id}`, { method: 'DELETE' }),
  users: () => request('/users'),
  suppress: (value, reason) => request('/suppression', { method: 'POST', body: { value, reason } }),

  async exportCsv(filters) {
    const { page: _p, pageSize: _ps, ...rest } = filters;
    const res = await request(`/leads/export${qs(rest)}`, { raw: true });
    const blob = await res.blob();
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? 'leads.csv';
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    a.click();
    URL.revokeObjectURL(url);
  },
};
