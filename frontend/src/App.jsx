import React, { useEffect, useRef, useState } from 'react';
import { api, clearToken, getSessionId, getToken, setToken } from './api.js';

function AuthPanel({ onAuthed, onClose }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const { access_token } = mode === 'login'
        ? await api.login(email, password)
        : await api.signup(email, password);
      setToken(access_token);
      onAuthed();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>{mode === 'login' ? 'Log in' : 'Create an account'}</strong>
        <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
      </div>
      <p style={{ color: '#666', fontSize: 13, margin: '4px 0 12px' }}>
        Sign in to save your usage across devices and unlock Pro.
      </p>
      <form onSubmit={submit}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{ display: 'block', width: '100%', padding: 8, marginBottom: 8 }}
        />
        <input
          type="password"
          placeholder="Password (8+ characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={8}
          required
          style={{ display: 'block', width: '100%', padding: 8, marginBottom: 8 }}
        />
        {error && <p style={{ color: 'crimson', fontSize: 13 }}>{error}</p>}
        <button type="submit" disabled={busy} style={{ width: '100%', padding: 8 }}>
          {busy ? 'Working…' : mode === 'login' ? 'Log in' : 'Sign up'}
        </button>
      </form>
      <button
        type="button"
        onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
        style={{ width: '100%', padding: 8, marginTop: 8, background: 'none', border: 'none', color: '#06c', cursor: 'pointer' }}
      >
        {mode === 'login' ? "Need an account? Sign up" : 'Have an account? Log in'}
      </button>
    </div>
  );
}

function AccountBar({ user, usageInfo, onLogout, onUpgrade, upgradeBusy }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: '1px solid #ddd', borderRadius: 8, padding: '8px 16px', marginBottom: 16, fontSize: 14 }}>
      <div>
        <strong>{user.email}</strong>{' '}
        <span style={{ color: '#666' }}>
          · {user.plan === 'pro' ? 'Pro plan' : 'Free plan'}
          {usageInfo ? ` · ${usageInfo.used_this_month}/${usageInfo.limit} messages this month` : ''}
        </span>
      </div>
      <div>
        {user.plan !== 'pro' && (
          <button onClick={onUpgrade} disabled={upgradeBusy} style={{ marginRight: 8 }}>
            {upgradeBusy ? '…' : 'Upgrade to Pro — $9/mo'}
          </button>
        )}
        <button onClick={onLogout}>Log out</button>
      </div>
    </div>
  );
}

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [user, setUser] = useState(null);
  const [usageInfo, setUsageInfo] = useState(null);
  const [showAuth, setShowAuth] = useState(false);
  const [upgradeBusy, setUpgradeBusy] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [billingNotice, setBillingNotice] = useState(null);
  const bottomRef = useRef(null);

  const refreshAccount = async () => {
    if (!getToken()) {
      setUser(null);
      setUsageInfo(null);
      return;
    }
    try {
      const [me, usage] = await Promise.all([api.me(), api.usage()]);
      setUser(me);
      setUsageInfo(usage);
    } catch {
      clearToken();
      setUser(null);
      setUsageInfo(null);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const billing = params.get('billing');
    if (billing === 'success') setBillingNotice('Subscription active — welcome to Pro!');
    if (billing === 'cancel') setBillingNotice('Checkout cancelled — you’re still on the Free plan.');
    if (billing) window.history.replaceState({}, '', window.location.pathname);

    refreshAccount();
    api.conversation(sessionId)
      .then((history) => setMessages(history.map((m) => ({ role: m.role, content: m.content }))))
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async (e) => {
    e.preventDefault();
    if (!input.trim() || busy) return;
    const userMsg = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setBusy(true);
    try {
      const data = await api.chat(sessionId, userMsg.content);
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
      if (data.usage_this_month != null) {
        setUsageInfo({ plan: user?.plan ?? 'free', used_this_month: data.usage_this_month, limit: data.usage_limit });
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }]);
    } finally {
      setBusy(false);
    }
  };

  const handleUpgrade = async () => {
    setUpgradeBusy(true);
    try {
      const { checkout_url } = await api.billingCheckout();
      window.location.href = checkout_url;
    } catch (err) {
      setBillingNotice(`Couldn't start checkout: ${err.message}`);
      setUpgradeBusy(false);
    }
  };

  const logout = () => {
    clearToken();
    setUser(null);
    setUsageInfo(null);
  };

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', fontFamily: 'system-ui', padding: '0 16px' }}>
      <h1>Nivor Chat Assistant</h1>
      <p style={{ color: '#666' }}>RAG-powered chat — try it free, sign in to save your usage and unlock Pro.</p>

      {billingNotice && (
        <div style={{ background: '#eef', border: '1px solid #ccd', borderRadius: 8, padding: 10, marginBottom: 16, fontSize: 14 }}>
          {billingNotice}
        </div>
      )}

      {user ? (
        <AccountBar user={user} usageInfo={usageInfo} onLogout={logout} onUpgrade={handleUpgrade} upgradeBusy={upgradeBusy} />
      ) : showAuth ? (
        <AuthPanel onAuthed={() => { setShowAuth(false); refreshAccount(); }} onClose={() => setShowAuth(false)} />
      ) : (
        <div style={{ marginBottom: 16 }}>
          <button onClick={() => setShowAuth(true)}>Sign in / Sign up</button>
        </div>
      )}

      <div style={{ border: '1px solid #ccc', borderRadius: 8, height: 420, overflowY: 'auto', padding: 12, marginBottom: 12 }}>
        {messages.length === 0 && <p style={{ color: '#888' }}>Say hello, or ask "what is RAG?"</p>}
        {messages.map((m, i) => (
          <div key={i} style={{ margin: '8px 0', textAlign: m.role === 'user' ? 'right' : 'left' }}>
            <span
              style={{
                display: 'inline-block',
                padding: '8px 12px',
                borderRadius: 12,
                background: m.role === 'user' ? '#06c' : '#eee',
                color: m.role === 'user' ? '#fff' : '#111',
                maxWidth: '80%',
              }}
            >
              {m.content}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={send} style={{ display: 'flex', gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message…"
          style={{ flex: 1, padding: 8 }}
        />
        <button type="submit" disabled={busy}>{busy ? '…' : 'Send'}</button>
      </form>
    </div>
  );
}
