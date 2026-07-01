import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";
import MessageBubble from "../components/MessageBubble";

const starterPrompts = [
  "Find student 101 and summarize their record.",
  "Search for students named Priya.",
  "What is the average CGPA for CSE students?",
];

function nowId() {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeSession(title = "New chat") {
  return { id: nowId(), title, messages: [], updatedAt: Date.now() };
}

function sessionsKey() {
  return `sra.sessions.${localStorage.getItem("user_id") || "guest"}`;
}

function loadSessions() {
  try {
    const saved = JSON.parse(localStorage.getItem(sessionsKey()) || "[]");
    return Array.isArray(saved) && saved.length ? saved : [makeSession()];
  } catch {
    return [makeSession()];
  }
}

function normalizeSession(session) {
  return {
    id: session.id,
    title: session.title || "New chat",
    updatedAt: session.updated_at ? new Date(session.updated_at).getTime() : Date.now(),
    messages: Array.isArray(session.messages)
      ? session.messages.map((m, i) => ({
          id: m.id || `${session.id}-${i}`,
          role: m.role,
          content: m.content,
        }))
      : [],
  };
}

function messagesFromHistory(sessionId, history) {
  return history.map((m, i) => ({
    id: `${sessionId}-${i}-${m.role}`,
    role: m.role,
    content: m.content,
    animate: i === history.length - 1 && m.role === "assistant",
  }));
}

function compactTitle(text) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "New chat";
  return cleaned.length > 42 ? `${cleaned.slice(0, 42)}...` : cleaned;
}

function formatSessionTime(value) {
  const date = new Date(value || Date.now());
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function ChatPage() {
  const [sessions, setSessions] = useState(loadSessions);
  const [activeId, setActiveId] = useState(() => sessions[0]?.id);
  const [input, setInput] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const navigate = useNavigate();

  // Refs so async callbacks always read the latest values without stale closures
  const activeIdRef = useRef(activeId);
  const loadingRef = useRef(false);
  useEffect(() => { activeIdRef.current = activeId; }, [activeId]);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  const role = localStorage.getItem("role") || "User";
  const username = localStorage.getItem("username") || "Signed in";

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) || sessions[0],
    [activeId, sessions]
  );

  const filteredSessions = useMemo(() => {
    const query = historyQuery.trim().toLowerCase();
    return [...sessions]
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
      .filter((session) => {
        if (!query) return true;
        const content = [
          session.title,
          ...(session.messages || []).map((m) => m.content),
        ].join(" ").toLowerCase();
        return content.includes(query);
      });
  }, [historyQuery, sessions]);

  useEffect(() => {
    localStorage.setItem(sessionsKey(), JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    let cancelled = false;
    async function loadServerSessions() {
      try {
        const res = await api.get("/chat/sessions");
        if (cancelled || loadingRef.current) return; // don't overwrite while a message is in flight
        const serverSessions = (res.data.sessions || []).map(normalizeSession);
        if (serverSessions.length) {
          setSessions(serverSessions);
          setActiveId((current) =>
            serverSessions.some((s) => s.id === current) ? current : serverSessions[0].id
          );
        } else {
          const session = makeSession();
          setSessions([session]);
          setActiveId(session.id);
          api.post("/chat/sessions", { session_id: session.id, title: session.title }).catch(() => {});
        }
      } catch {
        // Keep local fallback if backend is unavailable
      }
    }
    loadServerSessions();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeSession?.messages, loading]);

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = "48px";
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
  }, [input]);

  // Always updates by captured session id — safe across async boundaries
  function updateSession(sessionId, updater) {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId ? { ...updater(s), updatedAt: Date.now() } : s
      )
    );
  }

  function startNewChat() {
    const session = makeSession();
    setSessions((prev) => [session, ...prev]);
    setActiveId(session.id);
    setSidebarOpen(false);
    setInput("");
    api.post("/chat/sessions", { session_id: session.id, title: session.title }).catch(() => {});
  }

  async function renameChat(sessionId) {
    const session = sessions.find((s) => s.id === sessionId);
    const nextTitle = window.prompt("Rename chat", session?.title || "New chat");
    if (!nextTitle?.trim()) return;
    const title = compactTitle(nextTitle);
    setSessions((prev) =>
      prev.map((s) => s.id === sessionId ? { ...s, title, updatedAt: Date.now() } : s)
    );
    try {
      await api.patch(`/chat/sessions/${sessionId}`, { title });
    } catch {
      // Local title remains
    }
  }

  async function deleteChat(sessionId) {
    if (!window.confirm("Delete this chat?")) return;
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== sessionId);
      if (!next.length) {
        const fresh = makeSession();
        setActiveId(fresh.id);
        return [fresh];
      }
      if (sessionId === activeId) setActiveId(next[0].id);
      return next;
    });
    try {
      await api.delete(`/chat/sessions/${sessionId}`);
    } catch {
      // Local removal still useful
    }
  }

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("user_id");
    localStorage.removeItem("username");
    navigate("/login", { replace: true });
  }

  async function sendMessage(promptText = input) {
    const query = promptText.trim();
    if (!query || loading || !activeSession) return;

    // Capture id and title NOW — before any await — so they can't go stale
    const sessionId = activeIdRef.current;
    const previousMessages = activeSession.messages;
    const title = previousMessages.length ? activeSession.title : compactTitle(query);
    const optimisticMessages = [
      ...previousMessages,
      { id: nowId(), role: "user", content: query },
    ];

    updateSession(sessionId, (s) => ({ ...s, title, messages: optimisticMessages }));
    loadingRef.current = true;
    setInput("");
    setLoading(true);

    try {
      const res = await api.post("/chat", { query, session_id: sessionId, title });
      const serverMessages = Array.isArray(res.data.history)
        ? messagesFromHistory(sessionId, res.data.history)
        : [
            ...optimisticMessages,
            {
              id: nowId(),
              role: "assistant",
              content: res.data.response || "I could not produce a response.",
              animate: true,
            },
          ];
      updateSession(sessionId, (s) => ({ ...s, title, messages: serverMessages }));
    } catch (err) {
      const message =
        err.response?.status === 401
          ? "Your session expired. Please sign in again."
          : "I could not reach the Student Record Agent. Check that FastAPI is running on port 8000.";
      updateSession(sessionId, (s) => ({
        ...s,
        messages: [...optimisticMessages, { id: nowId(), role: "assistant", content: message }],
      }));
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <main className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="sidebar-header">
          <div>
            <div className="eyebrow">Chat History</div>
            <strong>Student Record Agent</strong>
          </div>
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar">
            x
          </button>
        </div>

        <button className="new-chat-button" onClick={startNewChat}>
          <span>+</span>
          New Chat
        </button>

        <div className="history-search">
          <input
            value={historyQuery}
            onChange={(e) => setHistoryQuery(e.target.value)}
            placeholder="Search history"
            aria-label="Search chat history"
          />
        </div>

        <div className="session-list">
          {filteredSessions.map((session) => (
            <div
              key={session.id}
              className={`session-item ${session.id === activeSession?.id ? "active" : ""}`}
              role="button"
              tabIndex={0}
              onClick={() => { setActiveId(session.id); setSidebarOpen(false); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setActiveId(session.id);
                  setSidebarOpen(false);
                }
              }}
            >
              <span className="session-title">{session.title}</span>
              <span className="session-preview">
                {session.messages.at(-1)?.content || "No messages yet"}
              </span>
              <span className="session-meta">
                {session.messages.length} messages · {formatSessionTime(session.updatedAt)}
              </span>
              <span className="session-actions" onClick={(e) => e.stopPropagation()}>
                <button onClick={() => renameChat(session.id)} aria-label="Rename chat">Rename</button>
                <button onClick={() => deleteChat(session.id)} aria-label="Delete chat">Delete</button>
              </span>
            </div>
          ))}
          {!filteredSessions.length && (
            <div className="history-empty">No chats match your search.</div>
          )}
        </div>
      </aside>

      {sidebarOpen && <div className="scrim" onClick={() => setSidebarOpen(false)} />}

      <section className="chat-panel">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar">
            =
          </button>
          <div>
            <div className="eyebrow">{activeSession?.title || "New chat"}</div>
            <h1>Student records assistant</h1>
          </div>
          <div className="account-pill">
            <span>{role}</span>
            <small>{username}</small>
          </div>
          <button className="ghost-button" onClick={handleLogout}>Logout</button>
        </header>

        <div className="messages-area">
          {!activeSession?.messages.length && (
            <section className="empty-state">
              <div className="empty-card">
                <div className="brand-mark small">SRA</div>
                <h2>Ask about students, marks, subjects, and audit records.</h2>
                <p>
                  The chat keeps context per local session and sends your selected history to the FastAPI agent.
                </p>
                <div className="prompt-grid">
                  {starterPrompts.map((prompt) => (
                    <button key={prompt} onClick={() => sendMessage(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          )}

          {activeSession?.messages.map((message, index) => (
            <MessageBubble
              key={message.id || index}
              role={message.role}
              content={message.content}
              animate={message.animate}
            />
          ))}

          {loading && (
            <div className="typing-row">
              <span /><span /><span />
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <footer className="composer-wrap">
          <div className="composer">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask the agent..."
              disabled={loading}
              rows={1}
            />
            <button className="send-button" onClick={() => sendMessage()} disabled={loading || !input.trim()}>
              {loading ? "..." : "Send"}
            </button>
          </div>
        </footer>
      </section>
    </main>
  );
}