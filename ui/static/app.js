const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const clearBtn = document.getElementById("clearBtn");
const pipBtn = document.getElementById("pipBtn");
const coderSelect = document.getElementById("coderSelect");
const usageEl = document.getElementById("usage");
const toolsBtn = document.getElementById("toolsBtn");
const toolsPanel = document.getElementById("toolsPanel");
const toolsPanelList = document.getElementById("toolsPanelList");

let sending = false;

const PIP_SUPPORTED = "documentPictureInPicture" in window;
let pipWindow = null;
let pipBodyEl = null;
let pipStatusEl = null;
let pipInputEl = null;

if (!PIP_SUPPORTED) {
  pipBtn.style.display = "none";
}

async function openPip() {
  if (!PIP_SUPPORTED || pipWindow) return;

  try {
    pipWindow = await documentPictureInPicture.requestWindow({ width: 340, height: 260 });
  } catch (e) {
    pipWindow = null;
    return; // browser refused (no active gesture / not supported here) — fail quietly
  }

  const pipDoc = pipWindow.document;
  pipDoc.title = "Lapis";

  const style = pipDoc.createElement("style");
  style.textContent = `
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; background: #0a0e1a; color: #f5f7fa;
      font-family: "Merriweather", Georgia, serif; }
    .pip-wrap { display: flex; flex-direction: column; height: 100vh; font-size: 13px; }
    .pip-header { display: flex; align-items: center; gap: 6px; padding: 8px 10px;
      border-bottom: 1px solid #1f2c44; font-family: "Playfair Display", Georgia, serif;
      font-style: italic; font-weight: 600; flex-shrink: 0; }
    .pip-dot { width: 6px; height: 6px; border-radius: 50%; background: #7ea6e0; }
    .pip-status { margin-left: auto; color: #6b7a94; font-weight: 400; font-style: normal; font-size: 11px; }
    .pip-body { flex: 1; overflow-y: auto; padding: 10px; line-height: 1.6; }
    .pip-body p { margin: 0 0 8px; }
    .pip-body p:last-child { margin-bottom: 0; }
    .pip-body strong { color: #7ea6e0; }
    .pip-body em { color: #a9b4c4; }
    .pip-body ul, .pip-body ol { margin: 0 0 8px; padding-left: 18px; }
    .pip-body li { margin: 2px 0; }
    .pip-body code { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px;
      background: #16213a; border: 1px solid #1f2c44; padding: 1px 4px; border-radius: 3px; }
    .pip-body pre { background: #121a2b; border: 1px solid #1f2c44; border-radius: 6px;
      padding: 8px 10px; overflow-x: auto; margin: 0 0 8px; }
    .pip-body pre code { background: none; border: none; padding: 0; font-size: 11.5px; }
    .pip-body h1, .pip-body h2, .pip-body h3 { font-family: "Playfair Display", Georgia, serif;
      font-size: 13.5px; color: #f5f7fa; margin: 10px 0 4px; }
    .pip-body blockquote { margin: 0 0 8px; padding: 0 10px; border-left: 2px solid #2f5fa8; color: #a9b4c4; }
    .pip-body a { color: #7ea6e0; border-bottom: 1px solid #2f5fa8; text-decoration: none; }
    .pip-composer { border-top: 1px solid #1f2c44; padding: 8px; flex-shrink: 0; }
    .pip-composer input { width: 100%; background: #121a2b; border: 1px solid #1f2c44;
      color: #f5f7fa; padding: 8px 10px; border-radius: 8px; font-size: 13px; outline: none; font-family: "Merriweather", Georgia, serif; }
    .pip-composer input:focus { border-color: #7ea6e0; }
  `;
  pipDoc.head.appendChild(style);

  const wrap = pipDoc.createElement("div");
  wrap.className = "pip-wrap";
  wrap.innerHTML = `
    <div class="pip-header">
      <span class="pip-dot"></span>
      <span>Lapis</span>
      <span class="pip-status" id="pipStatus">idle</span>
    </div>
    <div class="pip-body" id="pipBody"></div>
    <form class="pip-composer" id="pipComposer">
      <input type="text" id="pipInput" placeholder="Reply…" autocomplete="off">
    </form>
  `;
  pipDoc.body.appendChild(wrap);

  pipBodyEl = pipDoc.getElementById("pipBody");
  pipStatusEl = pipDoc.getElementById("pipStatus");
  pipInputEl = pipDoc.getElementById("pipInput");

  pipDoc.getElementById("pipComposer").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = pipInputEl.value.trim();
    if (!text || sending) return;
    pipInputEl.value = "";
    sendMessage(text);
  });

  pipWindow.addEventListener("pagehide", () => {
    pipWindow = null;
    pipBodyEl = null;
    pipStatusEl = null;
    pipInputEl = null;
  }, { once: true });

  syncPipStatus();
}

function closePip() {
  if (pipWindow) pipWindow.close();
}

function togglePip() {
  if (pipWindow) closePip();
  else openPip();
}

function syncPipStatus(text) {
  if (!pipStatusEl) return;
  pipStatusEl.textContent = text !== undefined ? text : (sending ? "thinking…" : "idle");
}

function syncPipBody(rawText) {
  if (!pipBodyEl) return;
  const html = marked.parse(rawText);
  pipBodyEl.innerHTML = DOMPurify.sanitize(html);
  pipBodyEl.scrollTop = pipBodyEl.scrollHeight;
}

pipBtn.addEventListener("click", togglePip);

document.addEventListener("visibilitychange", () => {
  if (!PIP_SUPPORTED) return;
  if (document.hidden && !pipWindow) {
    openPip();
  } else if (!document.hidden && pipWindow) {
    closePip();
  }
});

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function addUserMessage(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.textContent = text;
  chat.appendChild(el);
  scrollToBottom();
}

marked.setOptions({ breaks: true, gfm: true });

// Raw markdown source per in-flight assistant message, keyed by element.
const rawBuffers = new WeakMap();

// How many raw characters have already been "committed" — parsed into
// real markdown HTML — for a given message element. Everything past this
// point is still live/uncommitted and shown as plain fading-in text.
const committedLens = new WeakMap();

// Re-rendering the ENTIRE message from scratch on every single token (the
// old approach) replaces the whole DOM tree each time, which browsers
// can't animate — text just pops in instantly, hence the "choppy" look.
//
// Instead, each message is split into two regions:
//   .md-committed — fully parsed markdown HTML, only re-rendered at safe
//                   boundaries (a blank line), so already-shown text is
//                   left alone and doesn't flicker.
//   .md-live      — the current in-progress line/paragraph, shown as
//                   plain text. Each token gets its own brand-new <span>
//                   with a CSS fade-in — since these are genuinely new
//                   nodes (not replacements), the browser actually
//                   animates them, which is what gives the Gemini-style
//                   reveal.
//
// A commit is deliberately withheld while inside an unclosed ``` fence,
// so a code block never gets parsed half-finished and rendered broken —
// it waits for the closing fence (or the end of the message).
const MAX_LIVE_CHARS = 400; // safety flush for long fence-free stretches with no blank line

function startAssistantMessage() {
  const el = document.createElement("div");
  el.className = "msg assistant";
  const content = document.createElement("span");
  content.className = "md-content";
  const committed = document.createElement("span");
  committed.className = "md-committed";
  const live = document.createElement("span");
  live.className = "md-live";
  content.appendChild(committed);
  content.appendChild(live);
  const cursor = document.createElement("span");
  cursor.className = "cursor";
  el.appendChild(content);
  el.appendChild(cursor);
  chat.appendChild(el);
  rawBuffers.set(el, "");
  committedLens.set(el, 0);
  scrollToBottom();
  return el;
}

function renderCommitted(el, committedRaw) {
  const committedEl = el.querySelector(".md-committed");
  const html = marked.parse(committedRaw);
  committedEl.innerHTML = DOMPurify.sanitize(html);
}

function rebuildLiveTail(el, tailRaw) {
  const live = el.querySelector(".md-live");
  live.innerHTML = "";
  if (tailRaw) {
    const tok = document.createElement("span");
    tok.className = "tok-fade";
    tok.textContent = tailRaw;
    live.appendChild(tok);
  }
}

function maybeCommit(el) {
  const raw = rawBuffers.get(el) || "";
  const committedLen = committedLens.get(el) || 0;
  const uncommitted = raw.slice(committedLen);

  const fencesSoFar = (raw.match(/```/g) || []).length;
  if (fencesSoFar % 2 === 1) return; // inside an open code fence — wait for it to close

  const boundary = uncommitted.lastIndexOf("\n\n");
  const forceFlush = uncommitted.length > MAX_LIVE_CHARS;
  if (boundary === -1 && !forceFlush) return;

  const newCommittedLen = boundary === -1 ? raw.length : committedLen + boundary + 2;
  committedLens.set(el, newCommittedLen);
  renderCommitted(el, raw.slice(0, newCommittedLen));
  rebuildLiveTail(el, raw.slice(newCommittedLen));
}

function appendToken(el, text) {
  const updated = (rawBuffers.get(el) || "") + text;
  rawBuffers.set(el, updated);

  const live = el.querySelector(".md-live");
  const tok = document.createElement("span");
  tok.className = "tok-fade";
  tok.textContent = text;
  live.appendChild(tok);

  maybeCommit(el);
  scrollToBottom();
  syncPipBody(updated); // mirror the live text into the PiP window, if open
}

function finishAssistantMessage(el) {
  const raw = rawBuffers.get(el) || "";
  committedLens.set(el, raw.length);
  renderCommitted(el, raw); // final full parse — guarantees correct formatting once done
  rebuildLiveTail(el, "");

  const cursor = el.querySelector(".cursor");
  if (cursor) cursor.remove();
  if (!raw.trim()) el.remove();
  rawBuffers.delete(el);
  committedLens.delete(el);
  syncPipStatus("done");
}

function addToolChip(name, args) {
  const el = document.createElement("div");
  el.className = "tool-chip";
  const nameEl = document.createElement("span");
  nameEl.className = "name";
  nameEl.textContent = `⚙ ${name}`;
  const argsEl = document.createElement("span");
  argsEl.className = "args";
  argsEl.textContent = JSON.stringify(args);
  el.appendChild(nameEl);
  el.appendChild(argsEl);
  chat.appendChild(el);
  scrollToBottom();
  syncPipStatus(`⚙ ${name}`);
  syncPipBody(`Running ${name}…`);
}

function addToolResult(name, result) {
  const el = document.createElement("div");
  el.className = "tool-result";
  el.textContent = result;
  chat.appendChild(el);
  scrollToBottom();
  syncPipStatus("thinking…");
}

function addSystemNote(text) {
  const el = document.createElement("div");
  el.className = "system-note";
  el.textContent = text;
  chat.appendChild(el);
  scrollToBottom();
  syncPipStatus("⚠ " + text.slice(0, 30));
}

async function refreshState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    usageEl.textContent = `${data.total_in} in / ${data.total_out} out`;
    coderSelect.value = data.coder_backend;

    const openrouterOpt = coderSelect.querySelector('option[value="openrouter"]');
    const groqOpt = coderSelect.querySelector('option[value="groq"]');
    if (openrouterOpt) openrouterOpt.disabled = !data.openrouter_available;
    if (groqOpt) groqOpt.disabled = !data.groq_available;
  } catch (e) {
    // server not up yet — ignore, next refresh will retry
  }
}

// ---------------------------------------------------------------------
// Tool-category dropdown — lets the user pick which categories of tools
// (files, spotify, git, etc.) are exposed to the model this session.
// Logos are placeholders for now (see .tool-logo-placeholder in CSS);
// swap in real icons per category later without touching this logic.
// ---------------------------------------------------------------------

async function loadToolCategories() {
  try {
    const res = await fetch("/api/tool-categories");
    const data = await res.json();
    renderToolCategories(data.categories, data.active);
  } catch (e) {
    // server not up yet — ignore, next call will retry
  }
}

function renderToolCategories(categories, active) {
  const activeSet = new Set(active);
  toolsPanelList.innerHTML = "";

  categories.forEach((cat) => {
    const row = document.createElement("label");
    row.className = "tool-option";

    const logo = document.createElement("span");
    logo.className = "tool-logo-placeholder"; // TODO: replace with real icon per category

    const text = document.createElement("span");
    text.className = "tool-option-label";
    text.textContent = cat.label;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = cat.id;
    checkbox.checked = activeSet.has(cat.id);
    checkbox.addEventListener("change", onToolCategoryChange);

    row.appendChild(logo);
    row.appendChild(text);
    row.appendChild(checkbox);
    toolsPanelList.appendChild(row);
  });
}

async function onToolCategoryChange() {
  const checked = Array.from(
    toolsPanelList.querySelectorAll('input[type="checkbox"]:checked')
  ).map((cb) => cb.value);

  await fetch("/api/toggle-categories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ categories: checked }),
  });
}

toolsBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  toolsPanel.hidden = !toolsPanel.hidden;
});

// close the panel on an outside click, but not on clicks inside it
document.addEventListener("click", (e) => {
  if (!toolsPanel.hidden && !toolsPanel.contains(e.target) && e.target !== toolsBtn) {
    toolsPanel.hidden = true;
  }
});

function setSending(state) {
  sending = state;
  sendBtn.disabled = state;
  input.disabled = state;
  syncPipStatus();
}

async function sendMessage(text) {
  addUserMessage(text);
  setSending(true);

  let assistantEl = null;

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text }),
  });

  if (!res.ok || !res.body) {
    addSystemNote("Couldn't reach Lapis — is the server running?");
    setSending(false);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop(); // last chunk may be incomplete

    for (const raw of events) {
      if (!raw.trim()) continue;
      const lines = raw.split("\n");
      let eventName = "message";
      let dataStr = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataStr += line.slice(5).trim();
      }
      let data = {};
      try { data = JSON.parse(dataStr); } catch (e) { continue; }

      if (eventName === "token") {
        if (!assistantEl) assistantEl = startAssistantMessage();
        appendToken(assistantEl, data.text);
      } else if (eventName === "tool_call") {
        if (assistantEl) { finishAssistantMessage(assistantEl); assistantEl = null; }
        addToolChip(data.name, data.args);
      } else if (eventName === "tool_result") {
        addToolResult(data.name, data.result);
      } else if (eventName === "warning") {
        addSystemNote(data.message);
      } else if (eventName === "error") {
        addSystemNote(data.message);
      } else if (eventName === "done") {
        if (assistantEl) finishAssistantMessage(assistantEl);
        assistantEl = null;
      }
    }
  }

  setSending(false);
  refreshState();
  input.focus();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || sending) return;

  if (text.toLowerCase() === "clear") {
    input.value = "";
    input.style.height = "auto";
    runClear();
    return;
  }

  input.value = "";
  input.style.height = "auto";
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
});

async function runClear() {
  await fetch("/api/clear", { method: "POST" });
  chat.innerHTML = "";
  closePip();
  refreshState();
  loadToolCategories(); // categories reset to defaults server-side on clear
}

clearBtn.addEventListener("click", runClear);

coderSelect.addEventListener("change", async () => {
  const previous = coderSelect.dataset.previous || "local";
  const chosen = coderSelect.value;

  const res = await fetch("/api/toggle-coder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coder_backend: chosen }),
  });

  if (!res.ok) {
    coderSelect.value = previous;
    const data = await res.json();
    addSystemNote(data.error || "Couldn't switch coder backend.");
  } else {
    coderSelect.dataset.previous = chosen;
  }
});

refreshState();
loadToolCategories();