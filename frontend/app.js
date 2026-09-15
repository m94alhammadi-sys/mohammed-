/* مجلس القرار — منطق الواجهة: قائمة الدردشات، البث الحي، عرض الرسائل. */
(() => {
  "use strict";

  const WAR_ROOM = "war_room";

  const state = {
    chats: [],
    active: WAR_ROOM,
    typing: new Map(),   // agentId -> نص الحالة
    unread: new Map(),   // chatId -> عدد
    sending: false,
  };

  const el = {
    app: document.getElementById("app"),
    chatList: document.getElementById("chatList"),
    messages: document.getElementById("messages"),
    composer: document.getElementById("composer"),
    input: document.getElementById("input"),
    sendBtn: document.getElementById("sendBtn"),
    depth: document.getElementById("depth"),
    headName: document.getElementById("headName"),
    headSub: document.getElementById("headSub"),
    headAvatar: document.getElementById("headAvatar"),
    typingBar: document.getElementById("typingBar"),
    wsDot: document.getElementById("wsDot"),
    wsText: document.getElementById("wsText"),
    modeBadge: document.getElementById("modeBadge"),
    search: document.getElementById("chatSearch"),
    backBtn: document.getElementById("backBtn"),
    clearBtn: document.getElementById("clearBtn"),
  };

  const STATUS_TEXT = {
    working: "يبحث الآن…",
    typing: "يكتب…",
    synthesizing: "يركّب القرار…",
    reported: null,
    done: null,
    idle: null,
    timeout: null,
  };

  // ---------------------------------------------------------- أدوات

  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

  /** تنسيق خفيف بنمط الواتساب: *عريض* وروابط قابلة للنقر. */
  function renderText(raw) {
    let html = escapeHtml(raw);
    html = html.replace(/\*([^*\n]+)\*/g, "<b>$1</b>");
    html = html.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    return html;
  }

  const timeOf = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ""
      : d.toLocaleTimeString("ar", { hour: "2-digit", minute: "2-digit" });
  };

  const chatById = (id) => state.chats.find((c) => c.id === id);

  /** معاينة سطر واحد: بلا علامات تنسيق وبلا أسطر جديدة. */
  const snippetOf = (text) =>
    (text || "").replace(/\*/g, "").replace(/\s+/g, " ").trim().slice(0, 80);

  const agentName = (author) => {
    if (author === "user") return "أنا";
    const chat = chatById(author);
    return chat ? chat.name : author;
  };

  async function api(path, options) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.status === 204 ? null : res.json();
  }

  // ---------------------------------------------------------- الشريط

  function renderChatList() {
    const query = (el.search.value || "").trim().toLowerCase();
    el.chatList.replaceChildren();

    state.chats
      .filter((c) => !query || c.name.toLowerCase().includes(query)
                  || (c.tagline || "").toLowerCase().includes(query))
      .forEach((chat) => {
        const unread = state.unread.get(chat.id) || 0;
        const button = document.createElement("button");
        button.className = "chat-item" + (chat.id === state.active ? " active" : "");
        button.type = "button";
        button.innerHTML = `
          <span class="avatar" style="background:${escapeHtml(chat.color)}">${escapeHtml(chat.avatar)}</span>
          <span class="meta">
            <span class="row">
              <span class="name">${escapeHtml(chat.name)}</span>
              <span class="time">${escapeHtml(timeOf(chat.last_ts))}</span>
            </span>
            <span class="snippet">${escapeHtml(snippetOf(chat.last_message) || chat.tagline || "")}</span>
          </span>
          ${unread ? `<span class="unread">${unread}</span>` : ""}`;
        button.addEventListener("click", () => openChat(chat.id));
        el.chatList.appendChild(button);
      });
  }

  // ---------------------------------------------------------- الرسائل

  function bubbleFor(message) {
    if (message.kind === "system") {
      const node = document.createElement("div");
      node.className = "system";
      node.textContent = message.text;
      return node;
    }

    const outgoing = message.author === "user";
    const node = document.createElement("div");
    node.className = `bubble ${outgoing ? "out" : "in"} ${message.kind}`;

    const isGroup = (chatById(state.active) || {}).is_group;
    const who = (!outgoing && isGroup)
      ? `<span class="who" style="color:${escapeHtml((chatById(message.author) || {}).color || "#075E54")}">${escapeHtml(agentName(message.author))}</span>`
      : "";

    node.innerHTML = `${who}<span class="body">${renderText(message.text)}</span>
      <span class="time">${escapeHtml(timeOf(message.ts))}</span>`;

    const chips = chipsFor(message);
    if (chips) node.appendChild(chips);
    return node;
  }

  function chipsFor(message) {
    const meta = message.meta || {};
    const items = [];

    if (typeof meta.confidence === "number") {
      const pct = Math.round(meta.confidence * 100);
      items.push([`ثقة ${pct}%`, pct >= 60 ? "good" : pct < 35 ? "warn" : ""]);
    }
    if (typeof meta.risk === "number") {
      const pct = Math.round(meta.risk * 100);
      items.push([`مخاطرة ${pct}%`, pct >= 60 ? "warn" : ""]);
    }
    if (typeof meta.evidence === "number") items.push([`${meta.evidence} مصدر`, ""]);
    if (meta.degraded) items.push(["وضع منقطع", "warn"]);
    if (meta.urgency >= 0.7) items.push([`إلحاح ${Math.round(meta.urgency * 100)}%`, "warn"]);
    if (!items.length) return null;

    const wrap = document.createElement("span");
    wrap.className = "chips";
    items.forEach(([label, tone]) => {
      const chip = document.createElement("span");
      chip.className = `chip ${tone}`.trim();
      chip.textContent = label;
      wrap.appendChild(chip);
    });
    return wrap;
  }

  function appendMessage(message, { scroll = true } = {}) {
    const placeholder = el.messages.querySelector(".empty");
    if (placeholder) placeholder.remove();
    el.messages.appendChild(bubbleFor(message));
    if (scroll) el.messages.scrollTop = el.messages.scrollHeight;
  }

  function renderEmptyState(chat) {
    const isGroup = chat && chat.is_group;
    el.messages.innerHTML = `
      <div class="empty">
        <h2>${escapeHtml(chat ? chat.name : "")}</h2>
        <p>${escapeHtml(chat ? chat.tagline : "")}</p>
        ${isGroup ? `
          <p>اكتب موضوعاً ليتولّاه المجلس كاملاً: يبحث كل وكيل في اختصاصه،
             ثم يركّب الوكيل التنسيقي القرار التنفيذي.</p>
          <ul>
            <li>«أثر قرار الفائدة القادم على الذهب»</li>
            <li>«التوتر في مضيق هرمز وأسعار النفط»</li>
            <li>«تدفقات المؤسسات على أسهم أشباه الموصلات»</li>
          </ul>` : `
          <p>دردشة مباشرة مع هذا الوكيل في حدود اختصاصه وحده.</p>`}
      </div>`;
  }

  async function openChat(chatId) {
    state.active = chatId;
    state.unread.set(chatId, 0);
    el.app.classList.add("show-chat");

    const chat = chatById(chatId);
    if (chat) {
      el.headName.textContent = chat.name;
      el.headAvatar.textContent = chat.avatar;
      el.headAvatar.style.background = chat.color;
      el.headSub.textContent = chat.is_group
        ? (chat.members || []).join("، ")
        : chat.tagline;
    }
    el.depth.hidden = !(chat && chat.is_group);
    renderChatList();

    const history = await api(`/api/chats/${chatId}/messages`);
    el.messages.replaceChildren();
    if (!history.length) renderEmptyState(chat);
    else history.forEach((m) => appendMessage(m, { scroll: false }));
    el.messages.scrollTop = el.messages.scrollHeight;
    renderTyping();
  }

  // ---------------------------------------------------------- الحالة

  function renderTyping() {
    const entries = [...state.typing.entries()];
    if (!entries.length) {
      el.typingBar.hidden = true;
      el.headSub.classList.remove("active");
      return;
    }
    el.typingBar.hidden = false;
    el.typingBar.replaceChildren();
    entries.forEach(([agent, label]) => {
      const pill = document.createElement("span");
      pill.className = "typing-pill";
      pill.innerHTML = `<i></i><span>${escapeHtml(agentName(agent))} ${escapeHtml(label)}</span>`;
      el.typingBar.appendChild(pill);
    });
    el.headSub.classList.add("active");
  }

  function onStatus(data) {
    const label = STATUS_TEXT[data.state];
    if (label) state.typing.set(data.agent, label);
    else state.typing.delete(data.agent);
    renderTyping();
  }

  function onMessage(message) {
    const chat = chatById(message.chat_id);
    if (chat) {
      chat.last_message = snippetOf(message.text);
      chat.last_ts = message.ts;
    }
    if (message.chat_id === state.active) {
      appendMessage(message);
    } else if (message.author !== "user") {
      state.unread.set(message.chat_id, (state.unread.get(message.chat_id) || 0) + 1);
    }
    renderChatList();
  }

  // ---------------------------------------------------------- الاتصال

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/ws`);

    socket.addEventListener("open", () => {
      el.wsDot.className = "dot on";
      el.wsText.textContent = "متصل";
    });

    socket.addEventListener("message", (event) => {
      const { event: kind, data } = JSON.parse(event.data);
      if (kind === "message") onMessage(data);
      else if (kind === "status") onStatus(data);
      else if (kind === "ready") setMode(data.llm_enabled);
    });

    socket.addEventListener("close", () => {
      el.wsDot.className = "dot off";
      el.wsText.textContent = "انقطع الاتصال — إعادة المحاولة…";
      setTimeout(connect, 2500);
    });

    socket.addEventListener("error", () => socket.close());
  }

  function setMode(live) {
    el.modeBadge.textContent = live ? "متصل بالنموذج" : "وضع عرض بلا نموذج";
    el.modeBadge.className = `badge ${live ? "live" : "offline"}`;
  }

  // ---------------------------------------------------------- الإرسال

  async function send(text) {
    if (state.sending) return;
    state.sending = true;
    el.sendBtn.disabled = true;
    try {
      if (state.active === WAR_ROOM) {
        await api("/api/cycle", {
          method: "POST",
          body: JSON.stringify({
            topic: text, chat_id: WAR_ROOM, depth: el.depth.value,
          }),
        });
      } else {
        await api("/api/chat", {
          method: "POST",
          body: JSON.stringify({ chat_id: state.active, text }),
        });
      }
    } catch (error) {
      onMessage({
        id: `err_${Date.now()}`, chat_id: state.active, author: "system",
        text: `تعذّر الإرسال: ${error.message}`, ts: new Date().toISOString(),
        kind: "system", meta: {},
      });
    } finally {
      state.sending = false;
      el.sendBtn.disabled = false;
    }
  }

  // ---------------------------------------------------------- التهيئة

  el.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = el.input.value.trim();
    if (!text) return;
    el.input.value = "";
    send(text);
  });

  el.search.addEventListener("input", renderChatList);
  el.backBtn.addEventListener("click", () => el.app.classList.remove("show-chat"));
  el.clearBtn.addEventListener("click", async () => {
    if (!confirm("مسح كل رسائل هذه المحادثة؟")) return;
    await api(`/api/chats/${state.active}/messages`, { method: "DELETE" });
    openChat(state.active);
  });

  (async function init() {
    try {
      const health = await api("/api/health");
      setMode(health.llm_enabled);
    } catch { setMode(false); }

    state.chats = await api("/api/chats");
    renderChatList();
    await openChat(WAR_ROOM);
    if (window.innerWidth <= 820) el.app.classList.remove("show-chat");
    connect();
  })();
})();
