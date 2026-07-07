const API = "";

let sessionId = localStorage.getItem("telesom_session") || null;
const messagesEl = document.getElementById("messages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const fileInput = document.getElementById("fileInput");
const urlInput = document.getElementById("urlInput");
const btnUrl = document.getElementById("btnUrl");
const btnClear = document.getElementById("btnClear");
const ingestStatus = document.getElementById("ingestStatus");
const chunkBadge = document.getElementById("chunkBadge");
const phoneInput = document.getElementById("phoneInput");

const history = [];

function getCustomerPhone() {
  const v = (phoneInput?.value || localStorage.getItem("telesom_phone") || "").trim();
  if (v && phoneInput) phoneInput.value = v;
  return v || null;
}

phoneInput?.addEventListener("change", () => {
  const v = phoneInput.value.trim();
  if (v) localStorage.setItem("telesom_phone", v);
});

if (phoneInput) {
  const saved = localStorage.getItem("telesom_phone");
  if (saved) phoneInput.value = saved;
}

function setStatus(text, isError = false) {
  ingestStatus.textContent = text;
  ingestStatus.classList.toggle("err", isError);
}

async function ensureSession() {
  await refreshKnowledgeCount();
  if (sessionId) {
    const r = await fetch(`${API}/api/session/status?session_id=${encodeURIComponent(sessionId)}`);
    if (r.ok) {
      const d = await r.json();
      sessionId = d.session_id;
      localStorage.setItem("telesom_session", sessionId);
      updateBadge(d.chunks);
      return;
    }
  }
  const r = await fetch(`${API}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_phone: getCustomerPhone() }),
  });
  const d = await r.json();
  sessionId = d.session_id;
  localStorage.setItem("telesom_session", sessionId);
  updateBadge(0);
}

function updateBadge(chunks) {
  const n = Number(chunks);
  chunkBadge.textContent = `Xog: ${Number.isFinite(n) ? n : 0} qaybood`;
}

async function refreshKnowledgeCount() {
  try {
    const r = await fetch(`${API}/api/knowledge/status`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    updateBadge(d.chunks);
    return d.chunks;
  } catch (e) {
    setStatus("Server ma xidhiidhin — hubi uvicorn wuu socdo.", true);
    return null;
  }
}

function appendBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = role === "user" ? "Adiga" : "Telesom AI";
  div.appendChild(meta);
  const body = document.createElement("div");
  body.textContent = text;
  div.appendChild(body);
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  await ensureSession();
  appendBubble("user", text);
  history.push({ role: "user", content: text });
  messageInput.value = "";

  const sendBtn = document.getElementById("btnSend");
  sendBtn.disabled = true;

  try {
    const r = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        messages: history,
        customer_phone: getCustomerPhone(),
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(data.detail || r.statusText || "Qalad");
    }
    sessionId = data.session_id;
    localStorage.setItem("telesom_session", sessionId);
    updateBadge(data.chunks_in_memory);
    const reply = data.reply || "";
    history.push({ role: "assistant", content: reply });
    appendBubble("assistant", reply);
  } catch (err) {
    appendBubble("assistant", `Qalad: ${err.message}`);
    history.pop();
  } finally {
    sendBtn.disabled = false;
  }
});

fileInput.addEventListener("change", async () => {
  const f = fileInput.files?.[0];
  if (!f) return;
  await ensureSession();
  setStatus("Waa la soo gelinayaa faylka…");
  const fd = new FormData();
  fd.append("file", f);
  fd.append("session_id", sessionId);
  try {
    const r = await fetch(`${API}/api/upload`, {
      method: "POST",
      body: fd,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
    updateBadge((await (await fetch(`${API}/api/session/status?session_id=${encodeURIComponent(sessionId)}`)).json()).chunks);
    setStatus(`Waxaa lagu daray ${data.chunks_added} qaybood — ${data.filename}`);
  } catch (e) {
    setStatus(e.message, true);
  }
  fileInput.value = "";
});

btnUrl.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus("Geli URL.", true);
    return;
  }
  await ensureSession();
  setStatus("Waa la soo gelinayaa bogga…");
  try {
    const r = await fetch(`${API}/api/ingest-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, url }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
    sessionId = data.session_id;
    localStorage.setItem("telesom_session", sessionId);
    const st = await fetch(`${API}/api/session/status?session_id=${encodeURIComponent(sessionId)}`).then((x) => x.json());
    updateBadge(st.chunks);
    setStatus(`URL waa la geliyey — ${data.chunks_added} qaybood`);
    urlInput.value = "";
  } catch (e) {
    setStatus(e.message, true);
  }
});

btnClear.addEventListener("click", async () => {
  await ensureSession();
  const r = await fetch(`${API}/api/session/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await r.json().catch(() => ({}));
  history.length = 0;
  messagesEl.innerHTML = "";
  if (r.ok) updateBadge(data.chunks);
  else await refreshKnowledgeCount();
  setStatus("Chat-ka waa la nadiifiyey — dukumeentiyada waa la hayaa.");
});

ensureSession().catch(() => refreshKnowledgeCount());
