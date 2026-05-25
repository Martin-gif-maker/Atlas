/* chat-core.js — shared logic for Voice / Doc / Interview modes.
 *
 * Each mode page builds its own ChatCore({ ... }) instance with:
 *   mode:           'voice' | 'doc' | 'interview'
 *   container:      DOM element references (collected by the page)
 *   onConvLoaded:   (conv) => void   (mode-specific UI updates after load)
 *   beforeSend:     ()    => extra payload object (e.g. {document_id, role_name})
 *   speak:          boolean — whether to TTS the assistant reply
 */
window.ChatCore = function ChatCore(opts) {
  const mode = opts.mode;
  const els = opts.els;             // { messages, status, micBtn, sendBtn, input, sideList, chatTitle, voiceSelect, speakToggle }
  const beforeSend = opts.beforeSend || (() => ({}));
  const onConvLoaded = opts.onConvLoaded || (() => {});

  let activeConvId = null;
  let isBusy = false;
  let recorder = null, recChunks = [], recStream = null;

  // ---------- helpers ----------
  const escapeHTML = (s) => s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

  function setStatus(text, kind = "") {
    if (!els.status) return;
    els.status.textContent = text || "";
    els.status.className = `status-line ${kind}`.trim();
  }
  function setBusy(v) {
    isBusy = v;
    if (els.sendBtn) els.sendBtn.disabled = v;
    if (els.input)   els.input.disabled = v;
  }
  function clearMessages() { if (els.messages) els.messages.innerHTML = ""; }
  function showEmpty(html) {
    if (!els.messages) return;
    els.messages.innerHTML = html;
  }
  function appendMessage(role, content, opts = {}) {
    if (!els.messages) return null;
    const empty = els.messages.querySelector(".empty");
    if (empty) empty.remove();
    const div = document.createElement("div");
    div.className = `msg ${role}` + (opts.typing ? " typing" : "");
    div.textContent = content;
    els.messages.appendChild(div);
    els.messages.scrollTop = els.messages.scrollHeight;
    return div;
  }

  // ---------- conversation list ----------
  async function refreshList() {
    if (!els.sideList) return;
    try {
      const r = await fetch(`/api/conversations?mode=${mode}`);
      if (!r.ok) return;
      const { conversations } = await r.json();
      renderList(conversations);
    } catch (e) { console.error(e); }
  }
  function renderList(items) {
    if (!els.sideList) return;
    els.sideList.innerHTML = "";
    if (!items.length) {
      els.sideList.innerHTML = '<div class="side-empty">No conversations yet.</div>';
      return;
    }
    for (const c of items) {
      const row = document.createElement("div");
      row.className = "side-item" + (c.id === activeConvId ? " active" : "");
      row.dataset.id = c.id;
      row.innerHTML = `<span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;">${escapeHTML(c.title)}</span><button class="x" title="Delete">×</button>`;
      row.addEventListener("click", (e) => {
        if (e.target.classList.contains("x")) return;
        loadConv(c.id);
      });
      row.querySelector(".x").addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete "${c.title}"?`)) return;
        await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
        if (c.id === activeConvId) { activeConvId = null; resetView(); }
        refreshList();
      });
      els.sideList.appendChild(row);
    }
  }

  async function loadConv(id) {
    try {
      const r = await fetch(`/api/conversations/${id}`);
      if (!r.ok) throw new Error("not found");
      const conv = await r.json();
      activeConvId = conv.id;
      if (els.chatTitle) els.chatTitle.textContent = conv.title || "Conversation";
      clearMessages();
      if (!conv.messages.length) {
        showEmpty(`<div class="empty"><div class="big-icon">💬</div><h3>${conv.title}</h3><p>Send a message to continue.</p></div>`);
      } else {
        for (const m of conv.messages) appendMessage(m.role, m.content);
      }
      onConvLoaded(conv);
      refreshList();
    } catch (e) {
      setStatus("Could not load conversation.", "error");
    }
  }

  function resetView() {
    activeConvId = null;
    if (els.chatTitle) els.chatTitle.textContent = "New conversation";
    showEmpty(opts.emptyHTML || '<div class="empty"><div class="big-icon">💬</div><h3>Ready when you are</h3><p>Type or hold the mic to begin.</p></div>');
  }

  function setActiveConv(id) { activeConvId = id; }
  function getActiveConv() { return activeConvId; }

  // ---------- send text ----------
  async function sendText(text) {
    if (!text || isBusy) return;
    setBusy(true);
    appendMessage("user", text);
    const typing = appendMessage("assistant", "Thinking…", { typing: true });
    try {
      const extra = beforeSend() || {};
      const r = await fetch("/api/chat/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: activeConvId,
          text, mode, ...extra,
        }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      activeConvId = data.conversation_id;
      typing.classList.remove("typing");
      typing.textContent = data.reply;
      speak(data.reply);
      refreshList();
      if (els.chatTitle && els.chatTitle.textContent === "New conversation") {
        const r2 = await fetch(`/api/conversations/${activeConvId}`);
        if (r2.ok) { const d = await r2.json(); els.chatTitle.textContent = d.title; }
      }
    } catch (err) {
      typing.classList.remove("typing");
      typing.textContent = "⚠️  " + (err.message || "Error");
      setStatus(err.message || "Error", "error");
    } finally { setBusy(false); }
  }

  // ---------- send voice ----------
  async function sendVoice(blob) {
    if (isBusy) return;
    setBusy(true);
    const userPh = appendMessage("user", "🎙️  (transcribing…)", { typing: true });
    const typing = appendMessage("assistant", "Thinking…", { typing: true });
    try {
      const fd = new FormData();
      if (activeConvId) fd.append("conversation_id", activeConvId);
      fd.append("mode", mode);
      const extra = beforeSend() || {};
      for (const [k, v] of Object.entries(extra)) {
        if (v !== null && v !== undefined) fd.append(k, v);
      }
      fd.append("audio", blob, "voice.webm");
      const r = await fetch("/api/chat/voice", { method: "POST", body: fd });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      activeConvId = data.conversation_id;
      userPh.classList.remove("typing");
      userPh.textContent = data.transcript || "(no speech)";
      typing.classList.remove("typing");
      typing.textContent = data.reply;
      speak(data.reply);
      refreshList();
      if (els.chatTitle && els.chatTitle.textContent === "New conversation") {
        const r2 = await fetch(`/api/conversations/${activeConvId}`);
        if (r2.ok) { const d = await r2.json(); els.chatTitle.textContent = d.title; }
      }
    } catch (err) {
      userPh.classList.remove("typing");
      userPh.textContent = "🎙️ (failed)";
      typing.classList.remove("typing");
      typing.textContent = "⚠️ " + (err.message || "Voice failed");
      setStatus(err.message || "Error", "error");
    } finally { setBusy(false); }
  }

  // ---------- recording ----------
  async function startRec() {
    if (recorder) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("Microphone not supported in this browser.", "error"); return;
    }
    try { recStream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch { setStatus("Microphone permission denied.", "error"); return; }
    recChunks = [];
    const mt = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : (MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "");
    try { recorder = mt ? new MediaRecorder(recStream, { mimeType: mt }) : new MediaRecorder(recStream); }
    catch (err) { setStatus("Recorder error: " + err.message, "error"); stopStream(); return; }
    recorder.ondataavailable = (e) => { if (e.data && e.data.size) recChunks.push(e.data); };
    recorder.onstop = () => {
      const blob = new Blob(recChunks, { type: recorder.mimeType || "audio/webm" });
      stopStream();
      recorder = null;
      if (els.micBtn) els.micBtn.classList.remove("recording");
      setStatus("");
      if (blob.size > 200) sendVoice(blob);
      else setStatus("Recording was too short.", "error");
    };
    recorder.start();
    if (els.micBtn) els.micBtn.classList.add("recording");
    setStatus("Recording — click mic again to stop.", "recording");
  }
  function stopRec() { if (recorder && recorder.state !== "inactive") recorder.stop(); }
  function stopStream() { if (recStream) { recStream.getTracks().forEach((t) => t.stop()); recStream = null; } }

  // ---------- TTS ----------
  let voicesCache = [];
  function loadVoices() {
    voicesCache = window.speechSynthesis ? speechSynthesis.getVoices() : [];
    if (!els.voiceSelect) return;
    els.voiceSelect.innerHTML = "";
    if (!voicesCache.length) {
      const o = document.createElement("option"); o.textContent = "Default voice";
      els.voiceSelect.appendChild(o); return;
    }
    voicesCache.sort((a, b) => {
      const ea = a.lang.startsWith("en") ? 0 : 1, eb = b.lang.startsWith("en") ? 0 : 1;
      return ea - eb || a.name.localeCompare(b.name);
    });
    const saved = localStorage.getItem("atlas.voice") || "";
    for (const v of voicesCache) {
      const o = document.createElement("option");
      o.value = v.name;
      o.textContent = `${v.name} (${v.lang})`;
      if (v.name === saved) o.selected = true;
      els.voiceSelect.appendChild(o);
    }
  }
  function speak(text) {
    if (els.speakToggle && !els.speakToggle.checked) return;
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    if (els.voiceSelect) {
      const v = voicesCache.find((x) => x.name === els.voiceSelect.value);
      if (v) u.voice = v;
    }
    u.rate = 1.0; u.pitch = 1.0;
    speechSynthesis.speak(u);
  }

  // Init voices + speak toggle persistence
  if ("speechSynthesis" in window) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }
  if (els.speakToggle) {
    const ss = localStorage.getItem("atlas.speak");
    if (ss !== null) els.speakToggle.checked = ss === "1";
    els.speakToggle.addEventListener("change", () => {
      localStorage.setItem("atlas.speak", els.speakToggle.checked ? "1" : "0");
      if (!els.speakToggle.checked && "speechSynthesis" in window) speechSynthesis.cancel();
    });
  }
  if (els.voiceSelect) {
    els.voiceSelect.addEventListener("change", () => {
      localStorage.setItem("atlas.voice", els.voiceSelect.value);
    });
  }

  return {
    refreshList,
    loadConv,
    sendText,
    sendVoice,
    startRec, stopRec,
    setActiveConv, getActiveConv,
    resetView,
    appendMessage,
    setStatus,
  };
};
