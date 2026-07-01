import React, { useMemo, useState } from "react";

function formatSessionTime(value) {
  const date = new Date(value || Date.now());
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Sidebar({
  sessions,
  activeId,
  isOpen,
  onNewChat,
  onSelectSession,
  onRenameChat,
  onDeleteChat,
  onClose,
}) {
  const [historyQuery, setHistoryQuery] = useState("");

  const filteredSessions = useMemo(() => {
    const query = historyQuery.trim().toLowerCase();
    return [...sessions]
      .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
      .filter((session) => {
        if (!query) return true;
        const content = [
          session.title,
          ...(session.messages || []).map((message) => message.content),
        ].join(" ").toLowerCase();
        return content.includes(query);
      });
  }, [historyQuery, sessions]);

  return (
    <aside className={`sidebar ${isOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-header">
        <div>
          <div className="eyebrow">Chat History</div>
          <strong>Student Record Agent</strong>
        </div>
        <button className="icon-button mobile-only" onClick={onClose} aria-label="Close sidebar">
          x
        </button>
      </div>

      <button className="new-chat-button" onClick={onNewChat}>
        <span>+</span>
        New Chat
      </button>

      <div className="history-search">
        <input
          value={historyQuery}
          onChange={(event) => setHistoryQuery(event.target.value)}
          placeholder="Search history"
          aria-label="Search chat history"
        />
      </div>

      <div className="session-list">
        {filteredSessions.map((session) => (
          <div
            key={session.id}
            className={`session-item ${session.id === activeId ? "active" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => onSelectSession(session.id)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelectSession(session.id);
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
            <span className="session-actions" onClick={(event) => event.stopPropagation()}>
              <button onClick={() => onRenameChat(session.id)} aria-label="Rename chat">Rename</button>
              <button onClick={() => onDeleteChat(session.id)} aria-label="Delete chat">Delete</button>
            </span>
          </div>
        ))}
        {!filteredSessions.length && (
          <div className="history-empty">
            No chats match your search.
          </div>
        )}
      </div>
    </aside>
  );
}