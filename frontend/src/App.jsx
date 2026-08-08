import React, { useEffect, useRef, useState } from 'react';

const SESSION_KEY = 'ai_chatbot_engine_session_id';

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    fetch(`/api/conversations/${sessionId}`)
      .then((res) => res.json())
      .then((history) => setMessages(history.map((m) => ({ role: m.role, content: m.content }))))
      .catch(() => {});
  }, [sessionId]);

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
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: userMsg.content }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Something went wrong. Please try again.' }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 640, margin: '40px auto', fontFamily: 'system-ui', padding: '0 16px' }}>
      <h1>AI Chatbot Engine</h1>
      <p style={{ color: '#666' }}>RAG demo — ask about how this template works.</p>
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
