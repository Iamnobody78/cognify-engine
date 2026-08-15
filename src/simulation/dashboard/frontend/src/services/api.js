// 治理中心 API 客户端 (S67 spec §5 契约 + ARCH-ROUND 2 RBAC)
// 认证: JWT Bearer token 存 localStorage, 所有治理请求自动携带
const BASE = '/api/governance';
const TOKEN_KEY = 'gov_token';
const USER_KEY = 'gov_user';

function authHeaders(extra = {}) {
  const t = localStorage.getItem(TOKEN_KEY);
  return t ? { ...extra, Authorization: `Bearer ${t}` } : extra;
}

async function get(path) {
  const r = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

async function post(path, body) {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export const governanceApi = {
  agents: () => get('/agents'),
  agentAudit: (agentId, limit = 50) => get(`/agents/${agentId}/audit?limit=${limit}`),
  policies: () => get('/policies'),
  protocol: (name) => get(`/policies/${name}`),
  audit: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return get(`/audit?${q}`);
  },
  auditOne: (id) => get(`/audit/${id}`),
  vceLatest: () => get('/vce/latest'),
  vceHistory: (limit = 20) => get(`/vce/history?limit=${limit}`),
  vceScan: () => post('/vce/scan'),
  evaluate: (payload) => post('/evaluate', payload),
  // S69 策略编辑器
  protocolSource: (name) => get(`/policies/${name}/source`),
  policyValidate: (payload) => post('/policies/validate', payload),
  policyDeploy: (payload) => post('/policies/deploy', payload),
};

// ── RBAC 认证层 (ARCH-ROUND 2 / GAP-3.1) ─────────────────────
export const authApi = {
  login: async (username, password) => {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    const data = await r.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    return data.user;
  },
  me: async () => {
    const r = await fetch('/api/auth/me', { headers: authHeaders() });
    if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
    const user = await r.json();
    localStorage.setItem(USER_KEY, JSON.stringify(user));
    return user;
  },
  logout: () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  getToken: () => localStorage.getItem(TOKEN_KEY),
  getUser: () => {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); }
    catch { return null; }
  },
  isAdmin: () => authApi.getUser()?.role === 'admin',
  isAuditorOrHigher: () => ['auditor', 'admin'].includes(authApi.getUser()?.role),
};
