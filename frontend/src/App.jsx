import React, { useEffect, useMemo, useRef, useState } from "react";

const TOKEN_KEY = "bizai_token";
const EMAIL_KEY = "bizai_email";
const SESSION_KEY = "bizai_session";
const SUGGESTIONS = [
  "Summarize this policy",
  "Draft a client update",
  "Make a quick SWOT",
  "Create an onboarding checklist",
];

function readPath() {
  return window.location.pathname === "/chat" ? "/chat" : "/auth";
}

function cls(...parts) {
  return parts.filter(Boolean).join(" ");
}

function formatElapsed(seconds) {
  if (seconds == null || Number.isNaN(seconds)) {
    return "";
  }
  return `${seconds.toFixed(1)}s`;
}

function formatSessionTime(value) {
  if (!value) {
    return "";
  }
  const normalizedValue =
    typeof value === "string" && !value.endsWith("Z") && value.includes(" ")
      ? `${value.replace(" ", "T")}Z`
      : value;
  const date = new Date(normalizedValue);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);
  if (diffMinutes < 1) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }
  return date.toLocaleDateString();
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed");
  }
  return data;
}

function navigate(path) {
  if (window.location.pathname !== path) {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }
}

function App() {
  const [path, setPath] = useState(readPath());
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || "");
  const [email, setEmail] = useState(localStorage.getItem(EMAIL_KEY) || "");
  const [sessionId, setSessionId] = useState(localStorage.getItem(SESSION_KEY) || "");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthToken = params.get("oauth_token");
    const oauthEmail = params.get("oauth_email");
    if (oauthToken && oauthEmail) {
      setToken(oauthToken);
      setEmail(oauthEmail);
      setSessionId("");
      window.history.replaceState({}, "", "/auth");
      navigate("/chat");
    }
  }, []);

  useEffect(() => {
    const onPopState = () => setPath(readPath());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(EMAIL_KEY, email);
    localStorage.setItem(SESSION_KEY, sessionId);
  }, [token, email, sessionId]);

  useEffect(() => {
    if (!token && path === "/chat") {
      navigate("/auth");
    }
    if (token && path === "/auth") {
      navigate("/chat");
    }
  }, [path, token]);

  function handleAuth(nextToken, nextEmail) {
    setToken(nextToken);
    setEmail(nextEmail);
    setSessionId("");
    navigate("/chat");
  }

  function handleLogout() {
    setToken("");
    setEmail("");
    setSessionId("");
    navigate("/auth");
  }

  return path === "/chat" ? (
    <ChatScreen
      email={email}
      onLogout={handleLogout}
      sessionId={sessionId}
      setSessionId={setSessionId}
      token={token}
    />
  ) : (
    <AuthScreen onAuth={handleAuth} />
  );
}

function AuthScreen({ onAuth }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function authenticate(path, label) {
    if (!email.trim() || !password) {
      setStatus("Enter your work email and password.");
      setError(true);
      return;
    }
    setBusy(true);
    setStatus(label);
    setError(false);
    try {
      const data = await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      onAuth(data.access_token || "", data.email || email.trim());
    } catch (err) {
      setStatus(err.message || String(err));
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  async function signInWithGoogle() {
    setBusy(true);
    setError(false);
    try {
      const data = await request("/api/auth/google/start");
      window.location.href = data.auth_url;
    } catch (err) {
      setStatus(err.message || String(err));
      setError(true);
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-hero">
        <div className="eyebrow">BizAI</div>
        <h1>Business AI for faster work.</h1>
        <p>Chat, search docs, and draft work in one place.</p>
        <div className="auth-grid">
          <div className="auth-stat">
            <strong>Docs</strong>
            <span>Upload internal files.</span>
          </div>
          <div className="auth-stat">
            <strong>Drafts</strong>
            <span>Get emails and summaries fast.</span>
          </div>
          <div className="auth-stat">
            <strong>Memory</strong>
            <span>Keep each chat separate.</span>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="panel-card">
          <div className="panel-badge">Sign in</div>
          <h2>Welcome back</h2>
          <p className="panel-copy">Use your email to sign in or create an account.</p>

          <label className="field">
            <span>Email</span>
            <input
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              type="email"
              placeholder="you@company.com"
              autoComplete="email"
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              placeholder="Minimum 8 characters"
              autoComplete="current-password"
            />
          </label>

          <button className="button button-ghost oauth-button" type="button" disabled={busy} onClick={signInWithGoogle}>
            Continue with Google
          </button>

          <div className="action-row">
            <button
              className="button button-secondary"
              type="button"
              disabled={busy}
              onClick={() => authenticate("/api/auth/signup", "Creating your workspace access...")}
            >
              Create account
            </button>
            <button
              className="button button-primary"
              type="button"
              disabled={busy}
              onClick={() => authenticate("/api/auth/signin", "Signing you in...")}
            >
              Sign in
            </button>
          </div>

          <div className={cls("status-line", error && "error")}>{status || "Email and password sign-in is active."}</div>
        </div>
      </section>
    </main>
  );
}

function ChatScreen({ email, onLogout, sessionId, setSessionId, token }) {
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [message, setMessage] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [emailAttachment, setEmailAttachment] = useState(null);
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [status, setStatus] = useState("Workspace ready.");
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [file, setFile] = useState(null);
  const [pendingSeconds, setPendingSeconds] = useState(0);
  const [copiedMessageKey, setCopiedMessageKey] = useState("");
  const logRef = useRef(null);

  const authHeaders = useMemo(() => ({ Authorization: `Bearer ${token}` }), [token]);

  useEffect(() => {
    if (!token) {
      return;
    }
    request("/api/auth/me", { headers: authHeaders }).catch(() => {
      onLogout();
    });
  }, [authHeaders, onLogout, token]);

  useEffect(() => {
    if (!token) {
      return;
    }
    loadSessions();
  }, [token]);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    if (!loading) {
      setPendingSeconds(0);
      return undefined;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setPendingSeconds((Date.now() - startedAt) / 1000);
    }, 100);
    return () => window.clearInterval(timer);
  }, [loading]);

  const latestAssistantMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === "assistant") {
        return messages[index].text || "";
      }
    }
    return "";
  }, [messages]);

  const currentSessionLabel = useMemo(() => {
    if (!sessionId) {
      return "";
    }
    const currentSession = sessions.find((session) => {
      const id = typeof session === "string" ? session : session.id;
      return id === sessionId;
    });
    if (!currentSession) {
      return "Current chat";
    }
    const label = typeof currentSession === "string" ? currentSession : currentSession.name;
    return label || "Current chat";
  }, [sessionId, sessions]);

  function setStatusState(text, isError = false) {
    setStatus(text);
    setError(isError);
  }

  async function loadSessions() {
    try {
      const data = await request("/api/chat/sessions", { headers: authHeaders });
      setSessions(Array.isArray(data.sessions) ? data.sessions : []);
    } catch (err) {
      setStatusState(err.message || String(err), true);
    }
  }

  async function openSession(id, label) {
    setBusy(true);
    try {
      const data = await request(`/api/chat/${id}/messages`, { headers: authHeaders });
      const loadedMessages = Array.isArray(data.messages)
        ? data.messages.map((item) => ({
            role: item.role,
            text: item.content,
          }))
        : [];
      setSessionId(id);
      setMessages(loadedMessages);
      setStatusState(`Opened chat: ${label}.`);
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function newChat() {
    setBusy(true);
    try {
      const data = await request("/api/chat/new", { method: "POST", headers: authHeaders });
      setSessionId(data.session_id || "");
      setMessages([{ role: "assistant", text: "Fresh workspace opened. Upload knowledge or ask a question to get started." }]);
      setStatusState("New chat started.");
      await loadSessions();
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function clearChat() {
    if (!sessionId) {
      setStatusState("Start a chat before clearing memory.", true);
      return;
    }
    setBusy(true);
    try {
      await request(`/api/chat/${sessionId}/clear`, { method: "POST", headers: authHeaders });
      setMessages([{ role: "assistant", text: "This chat memory has been cleared." }]);
      setStatusState("Chat memory cleared.");
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function deleteCurrentSession() {
    if (!sessionId) {
      setStatusState("There is no active chat to delete.", true);
      return;
    }
    setBusy(true);
    try {
      await request(`/api/chat/${sessionId}`, { method: "DELETE", headers: authHeaders });
      setSessionId("");
      setMessages([]);
      setStatusState("Chat deleted.");
      await loadSessions();
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function deleteSessionById(id) {
    setBusy(true);
    try {
      await request(`/api/chat/${id}`, { method: "DELETE", headers: authHeaders });
      if (id === sessionId) {
        setSessionId("");
        setMessages([]);
      }
      setStatusState("Chat deleted.");
      await loadSessions();
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function uploadKnowledge() {
    if (!file) {
      setStatusState("Choose a file before uploading.", true);
      return;
    }
    setBusy(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (sessionId) {
        formData.append("session_id", sessionId);
      }
      const data = await request("/api/knowledge/upload", { method: "POST", headers: authHeaders, body: formData });
      setStatusState(`Uploaded ${data.filename}. Added ${data.chunks_added} chunks across ${data.documents_total} documents.`);
      setFile(null);
      await loadSessions();
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function wipeKnowledge() {
    setBusy(true);
    try {
      await request("/api/knowledge", { method: "DELETE", headers: authHeaders });
      setStatusState("Knowledge base deleted.");
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event, presetText) {
    if (event) {
      event.preventDefault();
    }
    const content = (presetText ?? message).trim();
    if (!content || loading) {
      return;
    }

    setMessages((current) => [...current, { role: "user", text: content }]);
    setMessage("");
    setLoading(true);
    const startedAt = performance.now();
    setError(false);

    try {
      const payload = { message: content, enable_web_search: webSearch };
      if (sessionId) {
        payload.session_id = sessionId;
      }
      const data = await request("/api/chat", {
        method: "POST",
        headers: { ...authHeaders, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSessionId(data.session_id || "");
      const elapsedSeconds = (performance.now() - startedAt) / 1000;
      setMessages((current) => [
        ...current,
        { role: "assistant", text: data.reply || "", elapsedSeconds },
      ]);
      setStatusState("Reply generated.");
      await loadSessions();
    } catch (err) {
      const detail = err.message || String(err);
      const elapsedSeconds = (performance.now() - startedAt) / 1000;
      setMessages((current) => [
        ...current,
        { role: "assistant", text: `Error: ${detail}`, elapsedSeconds },
      ]);
      setStatusState(detail, true);
    } finally {
      setLoading(false);
    }
  }

  function handleComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(event);
    }
  }

  function useLatestReplyForEmail() {
    if (!latestAssistantMessage) {
      setStatusState("Generate a reply before using it as an email draft.", true);
      return;
    }
    setEmailBody(latestAssistantMessage);
    if (!emailSubject.trim()) {
      setEmailSubject("BizAI draft");
    }
    setStatusState("Loaded the latest assistant reply into the email draft.");
  }

  async function sendEmail() {
    if (!emailTo.trim() || !emailSubject.trim() || !emailBody.trim()) {
      setStatusState("Complete the email recipient, subject, and body before sending.", true);
      return;
    }
    setBusy(true);
    try {
      let data;
      if (emailAttachment) {
        const formData = new FormData();
        formData.append("to", emailTo.trim());
        formData.append("subject", emailSubject.trim());
        formData.append("body", emailBody.trim());
        formData.append("attachment", emailAttachment);
        data = await request("/api/email/send-with-attachment", {
          method: "POST",
          headers: authHeaders,
          body: formData,
        });
      } else {
        data = await request("/api/email/send", {
          method: "POST",
          headers: { ...authHeaders, "Content-Type": "application/json" },
          body: JSON.stringify({
            to: emailTo.trim(),
            subject: emailSubject.trim(),
            body: emailBody.trim(),
          }),
        });
      }
      setStatusState(data.detail || `Email sent to ${emailTo.trim()}.`);
      setEmailModalOpen(false);
    } catch (err) {
      setStatusState(err.message || String(err), true);
    } finally {
      setBusy(false);
    }
  }

  function draftEmailFromMessage(text) {
    setEmailBody(text || "");
    if (!emailSubject.trim()) {
      setEmailSubject("BizAI draft");
    }
    setEmailModalOpen(true);
    setStatusState("Loaded this reply into the email draft.");
  }

  async function copyMessage(text, key) {
    try {
      await navigator.clipboard.writeText(text || "");
      setCopiedMessageKey(key);
      window.setTimeout(() => {
        setCopiedMessageKey((current) => (current === key ? "" : current));
      }, 1800);
    } catch (err) {
      setStatusState("Could not copy response.", true);
    }
  }

  return (
    <main className="workspace-shell">
      <section className="workspace-sidebar">
        <div className="sidebar-brand">
          <div className="eyebrow">Workspace</div>
          <h1>Your BizAI workspace.</h1>
          <p>Docs, memory, and chat in one view.</p>
        </div>

        <div className="sidebar-scrollable-content">
        <div className="sidebar-card">
          <div className="section-label">Account</div>
          <div className="account-chip">
            <div className="account-avatar">{(email || "B").slice(0, 1).toUpperCase()}</div>
            <div className="account-details">
              <strong>{email || "Signed in"}</strong>
              <span>Active session</span>
            </div>
          </div>
        </div>

        <div className="sidebar-card">
          <div className="section-label">Knowledge base</div>
          <label className="upload-box">
            <input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <strong>{file ? file.name : "Choose a document"}</strong>
            <span>.txt, .md, .pdf up to 20MB</span>
          </label>
          <div className="stack-row">
            <button className="button button-primary" type="button" disabled={busy} onClick={uploadKnowledge}>Upload file</button>
            <button className="button button-secondary" type="button" disabled={busy} onClick={wipeKnowledge}>Clear docs</button>
          </div>
          <div className="muted-note">Removes uploaded knowledge-base files and their searchable chunks.</div>
        </div>

        <div className="sidebar-card">
          <div className="section-label">Session controls</div>
          <div className="stack-row">
            <button className="button button-primary" type="button" disabled={busy} onClick={newChat}>New chat</button>
            <button className="button button-secondary" type="button" disabled={busy} onClick={clearChat}>Clear memory</button>
          </div>
          <button className="button button-ghost" type="button" disabled={busy} onClick={deleteCurrentSession}>Delete active chat</button>
          <label className="toggle-row">
            <input type="checkbox" checked={webSearch} onChange={(event) => setWebSearch(event.target.checked)} />
            <span>Use web search</span>
          </label>
        </div>

        <div className="sidebar-card">
          <div className="section-label">Send email</div>
          <label className="field compact-field">
            <span>To</span>
            <input
              value={emailTo}
              onChange={(event) => setEmailTo(event.target.value)}
              type="email"
              placeholder="client@company.com"
              autoComplete="email"
            />
          </label>
          <label className="field compact-field">
            <span>Subject</span>
            <input
              value={emailSubject}
              onChange={(event) => setEmailSubject(event.target.value)}
              type="text"
              placeholder="Quarterly update"
            />
          </label>
          <label className="field compact-field">
            <span>Body</span>
            <textarea
              className="email-textarea email-textarea-compact"
              value={emailBody}
              onChange={(event) => setEmailBody(event.target.value)}
              placeholder="Use the latest assistant reply or write your own email..."
            />
          </label>
          <label className="upload-box email-attachment-box">
            <input type="file" onChange={(event) => setEmailAttachment(event.target.files?.[0] || null)} />
            <strong>{emailAttachment ? emailAttachment.name : "Attach a file"}</strong>
            <span>{emailAttachment ? "Attachment ready to send" : "Optional email attachment"}</span>
          </label>
          <div className="stack-row">
            <button className="button button-secondary" type="button" disabled={busy} onClick={useLatestReplyForEmail}>
              Use latest reply
            </button>
            <button className="button button-secondary" type="button" disabled={busy} onClick={() => setEmailModalOpen(true)}>
              Open large
            </button>
            <button className="button button-primary" type="button" disabled={busy} onClick={sendEmail}>
              Send email
            </button>
          </div>
        </div>

        <div className="sidebar-card">
          <div className="section-label">Recent threads</div>
          <div className="session-list">
            {sessions.length ? (
              sessions.map((session) => {
                const id = typeof session === "string" ? session : session.id;
                const label = typeof session === "string" ? session : session.name;
                const preview = typeof session === "string" ? "" : session.preview;
                const updatedAt = typeof session === "string" ? "" : session.updated_at;
                return (
                  <div key={id} className={cls("session-pill", id === sessionId && "active")}>
                    <button
                      type="button"
                      className="session-pill-main"
                      onClick={() => openSession(id, label)}
                    >
                      <span className="session-pill-title">{label}</span>
                      {preview ? <span className="session-pill-preview">{preview}</span> : null}
                      {updatedAt ? <span className="session-pill-time">{formatSessionTime(updatedAt)}</span> : null}
                    </button>
                    <button
                      type="button"
                      className="session-delete"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        deleteSessionById(id);
                      }}
                      aria-label={`Delete ${label}`}
                      title="Delete chat"
                    >
                      Delete
                    </button>
                  </div>
                );
              })
            ) : (
              <div className="muted-note">No saved threads yet. Start a chat to create one.</div>
            )}
          </div>
        </div>
        </div>
        <div className="sidebar-footer">
          <button className="button button-ghost" type="button" onClick={onLogout}>Log out</button>
        </div>
      </section>

      <section className="workspace-main">
        <header className="workspace-header">
          <div>
            <div className="eyebrow">Chat</div>
            <h2>Ask, search, and draft.</h2>
          </div>
          <div className={cls("status-pill", error && "error")}>{status}</div>
        </header>

        <div className="suggestion-row">
          {SUGGESTIONS.map((item) => (
            <button key={item} type="button" className="suggestion-chip" onClick={(event) => sendMessage(event, item)}>
              {item}
            </button>
          ))}
        </div>

        <section className="log-panel" ref={logRef}>
          {messages.length === 0 && !loading ? (
            <div className="empty-state">
              <h3>Start a chat.</h3>
              <p>Ask a question or upload a file to begin.</p>
            </div>
          ) : null}

          {messages.map((item, index) => (
            <article key={`${item.role}-${index}`} className={cls("message-row", item.role)}>
              <div className="message-meta">{item.role === "user" ? "You" : "BizAI"}</div>
              <div className="message-bubble">{item.text}</div>
              {item.role === "assistant" ? (
                <div className="message-footer">
                  <span className="message-time">{formatElapsed(item.elapsedSeconds)}</span>
                  <button
                    type="button"
                    className="message-action"
                    onClick={() => copyMessage(item.text, `${item.role}-${index}`)}
                  >
                    {copiedMessageKey === `${item.role}-${index}` ? "Copied" : "Copy"}
                  </button>
                  <button
                    type="button"
                    className="message-action"
                    onClick={() => draftEmailFromMessage(item.text)}
                  >
                    Send email
                  </button>
                </div>
              ) : null}
            </article>
          ))}

          {loading ? (
            <article className="message-row assistant loading">
              <div className="message-meta">BizAI</div>
              <div className="message-bubble">Thinking through your request...</div>
              <div className="message-footer">
                <span className="message-time">{formatElapsed(pendingSeconds)}</span>
              </div>
            </article>
          ) : null}
        </section>

        <form className="composer" onSubmit={sendMessage}>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            disabled={loading}
            placeholder="Ask a question, draft something, or search your docs..."
          />
          <div className="composer-row">
            <button className="button button-primary" type="submit" disabled={loading}>Send message</button>
          </div>
        </form>
      </section>
      {emailModalOpen ? (
        <div className="modal-backdrop" onClick={() => setEmailModalOpen(false)}>
          <section className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <div className="section-label">Email composer</div>
                <h3>Send email</h3>
              </div>
              <button className="button button-ghost modal-close" type="button" onClick={() => setEmailModalOpen(false)}>
                Close
              </button>
            </div>
            <div className="modal-body">
              <label className="field">
                <span>To</span>
                <input
                  value={emailTo}
                  onChange={(event) => setEmailTo(event.target.value)}
                  type="email"
                  placeholder="client@company.com"
                  autoComplete="email"
                />
              </label>
              <label className="field">
                <span>Subject</span>
                <input
                  value={emailSubject}
                  onChange={(event) => setEmailSubject(event.target.value)}
                  type="text"
                  placeholder="Quarterly update"
                />
              </label>
              <label className="field">
                <span>Body</span>
                <textarea
                  className="email-textarea email-textarea-modal"
                  value={emailBody}
                  onChange={(event) => setEmailBody(event.target.value)}
                  placeholder="Write the email body here..."
                />
              </label>
              <label className="upload-box email-attachment-box">
                <input type="file" onChange={(event) => setEmailAttachment(event.target.files?.[0] || null)} />
                <strong>{emailAttachment ? emailAttachment.name : "Attach a file"}</strong>
                <span>{emailAttachment ? "Attachment ready to send" : "Optional email attachment"}</span>
              </label>
            </div>
            <div className="modal-actions">
              <button className="button button-secondary" type="button" disabled={busy} onClick={useLatestReplyForEmail}>
                Use latest reply
              </button>
              <button className="button button-primary" type="button" disabled={busy} onClick={sendEmail}>
                Send email
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
