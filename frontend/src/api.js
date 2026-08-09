const TOKEN_KEY = 'nivor_chat_token';
const SESSION_KEY = 'nivor_chat_session_id';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

async function request(path, options = {}) {
  const token = getToken();
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response had no JSON body
    }
    throw new Error(detail);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  signup: (email, password) =>
    request('/api/auth/signup', { method: 'POST', body: JSON.stringify({ email, password }) }),
  login: (email, password) =>
    request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: () => request('/api/auth/me'),
  usage: () => request('/api/usage'),
  chat: (sessionId, message) =>
    request('/api/chat', { method: 'POST', body: JSON.stringify({ session_id: sessionId, message }) }),
  conversation: (sessionId) => request(`/api/conversations/${sessionId}`),
  billingCheckout: () => request('/api/billing/checkout', { method: 'POST' }),
  billingPortal: () => request('/api/billing/portal'),
};
