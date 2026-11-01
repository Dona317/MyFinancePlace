/**
 * main.js — UI interactions for MyFinancePlace
 */

/* ── Preferences kept in this browser (private mode may refuse them) ──── */
const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } },
};

/* Windows over the page (.modal-overlay): open one by id, close it by id */
function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add("open");
  document.documentElement.classList.add("no-scroll");  // the page behind stays still (it scrolls on <html>)
  setTimeout(() => el.querySelector("input, select, textarea, button")?.focus(), 60);
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove("open");
  if (!document.querySelector(".modal-overlay.open")) document.documentElement.classList.remove("no-scroll");
}
window.openModal = openModal;
window.closeModal = closeModal;

/* Fill a translated message: fmt("%(count)s rows", {count: 3}) → "3 rows" */
function fmt(message, values) {
  return String(message).replace(/%\((\w+)\)s/g, (all, key) => (key in values ? values[key] : all));
}

/* A comma-separated tags field shown as chips; the suggestions come from data-suggestions (JSON list) */
function initTagInput(input, text) {
  const pool = JSON.parse(input.dataset.suggestions || "[]");
  const same = (a, b) => a.toLocaleLowerCase() === b.toLocaleLowerCase();
  let tags = input.value.split(",").map(t => t.trim()).filter(Boolean);
  const wrap = document.createElement("div");
  wrap.className = "tag-picker form-control";
  const typing = document.createElement("input");
  typing.type = "text";
  typing.className = "tag-picker-input";
  typing.placeholder = input.placeholder;
  typing.autocomplete = "off";
  const list = document.createElement("datalist");
  list.id = (input.id || input.name) + "-pool";
  typing.setAttribute("list", list.id);
  if (input.id) { typing.id = input.id; input.id = input.id + "-value"; }  // the <label for> now points to the text box
  input.type = "hidden";
  input.after(wrap, list);

  // the tags the chosen category suggests (data-category-tags: {category: [tags]}), one click each (F32)
  const byCategory = JSON.parse(input.dataset.categoryTags || "null");
  const hints = Object.assign(document.createElement("div"), { className: "tag-suggest", hidden: true });
  list.after(hints);
  const paint = () => {
    if (!byCategory) return;
    const select = input.form?.querySelector('select[name="category"]');
    const names = (byCategory[select?.value] || []).filter(t => !tags.some(x => same(x, t)));
    hints.replaceChildren(...names.map(t => {
      const chip = Object.assign(document.createElement("button"), { type: "button", className: "tag-suggest-chip", textContent: "+ " + t });
      chip.addEventListener("click", () => add(t));
      return chip;
    }));
    hints.hidden = !names.length;
  };
  if (byCategory) input.form?.addEventListener("change", e => { if (e.target.name === "category") paint(); });

  const render = () => {
    wrap.querySelectorAll(".tag-chip").forEach(chip => chip.remove());
    tags.forEach((tag, i) => {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.textContent = tag;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.innerHTML = '<i class="bi bi-x"></i>';
      remove.setAttribute("aria-label", (text.remove_tag || "Togli") + " " + tag);
      remove.addEventListener("click", () => { tags.splice(i, 1); render(); typing.focus(); });
      chip.appendChild(remove);
      wrap.insertBefore(chip, typing);
    });
    input.value = tags.join(", ");
    list.replaceChildren(...pool.filter(p => !tags.some(t => same(t, p))).map(p => Object.assign(document.createElement("option"), { value: p })));
    paint();
  };
  const add = (value) => {
    value.split(",").map(v => v.trim()).filter(Boolean).forEach(tag => {
      if (!tags.some(t => same(t, tag))) tags.push(pool.find(p => same(p, tag)) || tag);
    });
    typing.value = "";
    render();
  };
  typing.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(typing.value);
    } else if (e.key === "Backspace" && !typing.value && tags.length) {
      tags.pop();
      render();
    }
  });
  // a suggestion picked from the list arrives as the whole value: take it at once
  typing.addEventListener("input", () => { if (pool.some(p => same(p, typing.value.trim()))) add(typing.value); });
  typing.addEventListener("blur", () => { if (typing.value.trim()) add(typing.value); });
  wrap.addEventListener("click", e => { if (e.target === wrap) typing.focus(); });
  wrap.appendChild(typing);
  render();
}

/* ── Light / dark mode ─────────────────────────────────────────────────── */
// The user's choice is remembered; until they choose, the app follows the operating system.
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme, remember) {
  document.documentElement.setAttribute("data-theme", theme);
  // One button: the sun in light mode, the moon in dark mode; the label says what a click does
  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    const text = window.MFP_TEXT || {};
    const label = theme === "dark" ? (text.to_light || "Passa alla modalità chiara") : (text.to_dark || "Passa alla modalità scura");
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
  }
  if (remember) store.set("mfp-theme", theme);
  document.dispatchEvent(new CustomEvent("mfp:themechange", { detail: { theme } }));
}

/* "-€ 1.234,56" like the money filter on the server: sign, symbol, number in the format chosen in Settings
   (on <html>), unless the caller says otherwise */
function formatMoney(value, currency, locale) {
  locale = locale || document.documentElement.dataset.locale || "it-IT";
  currency = currency || document.documentElement.dataset.currency || "EUR";
  const symbol = new Intl.NumberFormat(locale, { style: "currency", currency }).formatToParts(0)
    .find(part => part.type === "currency").value;
  // grouping always: Italian would leave 4-digit amounts without the thousands point (1870,18), unlike the server
  const number = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always" })
    .format(Math.abs(value));
  return (value < 0 ? "-" : "") + symbol + " " + number;
}
window.formatMoney = formatMoney;

/* A typed amount as a number, read like the server does (parsing.parse_amount): "1.234,56", "1,234.56", "12,5",
   "€ 12" and a sign; 0 when it is not a number */
function parseAmount(text) {
  let raw = String(text ?? '').replace(/[€\s]/g, '');
  if (raw.includes(',') && raw.includes('.')) {
    raw = raw.lastIndexOf(',') > raw.lastIndexOf('.') ? raw.replace(/\./g, '').replace(',', '.') : raw.replace(/,/g, '');
  } else {
    raw = raw.replace(',', '.');
  }
  const value = Number(raw);
  return isFinite(value) && raw !== '' ? value : 0;
}
window.parseAmount = parseAmount;

/* A dashed box files can be dropped on: they go into the file input, as if chosen with it ("change" fires);
   only the first file when the input takes one */
function initDropZone(zone, input) {
  if (!zone || !input) return;
  ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('over'); }));
  zone.addEventListener('dragleave', e => { if (!zone.contains(e.relatedTarget)) zone.classList.remove('over'); });
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('over');
    const files = [...e.dataTransfer.files].slice(0, input.multiple ? undefined : 1);
    if (!files.length) return;
    const transfer = new DataTransfer();
    files.forEach(file => transfer.items.add(file));
    input.files = transfer.files;
    input.dispatchEvent(new Event('change'));
  });
}
window.initDropZone = initDropZone;

/* Interface texts in the chosen language (set by base.html), Italian when missing */
const TEXT = Object.assign({
  expand_menu: "Espandi il menu", shrink_menu: "Riduci il menu", confirm: "Sei sicuro?",
}, window.MFP_TEXT || {});

/* Theme switch: show the theme applied in <head>, change it on click, follow the system until the user chooses */
function initTheme() {
  applyTheme(currentTheme(), false);
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
  });
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", e => {
    if (!store.get("mfp-theme")) applyTheme(e.matches ? "dark" : "light", false);
  });
}

/* The ☰ button in the sidebar: on desktop it switches the menu between icons + names and icons only
   (remembered), so the menu never disappears; on phones and tablets the sidebar is hidden, the ☰ in the
   topbar slides it in and the one in the sidebar, the overlay or ESC closes it */
function initSidebar() {
  const toggleBtn = document.getElementById("sidebar-toggle");
  const openBtn   = document.getElementById("sidebar-open");
  const sidebar   = document.getElementById("sidebar");
  const overlay   = document.getElementById("sidebar-overlay");
  const phone = window.matchMedia("(max-width: 992px)");
  const closeSidebar = () => {
    sidebar?.classList.remove("open");
    overlay?.classList.remove("active");
  };
  if (openBtn && sidebar) {
    openBtn.addEventListener("click", () => {
      sidebar.classList.add("open");
      overlay?.classList.add("active");
    });
  }
  // Icons only: more room for tables; each icon gets its name as a tooltip
  const applyMini = (mini) => {
    document.documentElement.classList.toggle("sidebar-mini", mini);
    document.querySelectorAll(".sidebar .nav-item").forEach(item => {
      const label = item.querySelector(".nav-label");
      if (mini && label) item.title = label.textContent.trim();
      else item.removeAttribute("title");
    });
    if (!toggleBtn) return;
    const label = mini ? TEXT.expand_menu : TEXT.shrink_menu;
    toggleBtn.setAttribute("aria-label", label);
    toggleBtn.setAttribute("aria-expanded", String(!mini));
    toggleBtn.title = label;
  };
  applyMini(document.documentElement.classList.contains("sidebar-mini"));
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      if (phone.matches) {
        closeSidebar();
        return;
      }
      const mini = !document.documentElement.classList.contains("sidebar-mini");
      applyMini(mini);
      store.set("mfp-sidebar-mini", mini ? "1" : "0");
    });
  }
  overlay?.addEventListener("click", closeSidebar);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeSidebar(); });
}

/* Collapsible sections of the menu, remembered in this browser */
function initNavSections() {
  const saveCollapsed = () => {
    const closed = [...document.querySelectorAll(".nav-section.collapsed")].map(s => s.dataset.section);
    store.set("mfp-nav-collapsed", JSON.stringify(closed));
  };
  document.querySelectorAll(".nav-section-title").forEach(title => {
    title.addEventListener("click", () => {
      const section = title.closest(".nav-section");
      const collapsed = section.classList.toggle("collapsed");
      title.setAttribute("aria-expanded", String(!collapsed));
      saveCollapsed();
    });
  });
}

/* Chiedi ai tuoi dati: the round button opens the panel on the right; the questions and answers of this browser tab
   are kept while moving between pages (sessionStorage), «new conversation» clears them */
function initAskPanel() {
  const panel = document.getElementById("ask-panel"), bubble = document.getElementById("ask-bubble");
  if (!panel || !bubble) return;
  const list = document.getElementById("ask-messages"), form = document.getElementById("ask-form");
  const input = document.getElementById("ask-input"), examples = document.getElementById("ask-examples");
  const KEY = "mfp-ask-chat";
  let chat = [], status = null;
  try { chat = JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) { chat = []; }
  const keep = () => { try { sessionStorage.setItem(KEY, JSON.stringify(chat.slice(-40))); } catch (e) { /* private mode */ } };
  const bubbleOf = (m) => {
    const el = Object.assign(document.createElement("div"), { className: `ask-msg ask-${m.from}` });
    el.appendChild(Object.assign(document.createElement("div"), { className: "ask-text", textContent: m.text }));
    if (m.links?.length) {
      const links = Object.assign(document.createElement("div"), { className: "ask-links" });
      m.links.forEach(([label, url]) => links.appendChild(Object.assign(document.createElement("a"), { href: url, className: "btn btn-ghost btn-sm", textContent: label + " →" })));
      el.appendChild(links);
    }
    if (m.from === "bot" && !m.error) el.appendChild(Object.assign(document.createElement("div"), { className: "ask-check", textContent: TEXT.ask_check || "" }));
    return el;
  };
  const render = () => {
    list.replaceChildren(...chat.map(bubbleOf));
    examples.hidden = chat.length > 0 || !status?.available;
    list.scrollTop = list.scrollHeight;
  };
  const open = async (on) => {
    panel.hidden = !on;
    bubble.setAttribute("aria-expanded", String(on));
    document.body.classList.toggle("ask-open", on);
    if (!on) return;
    if (!status) {
      try { status = await fetch(panel.dataset.status).then(r => r.json()); } catch (e) { status = { available: false, examples: [] }; }
      document.getElementById("ask-note").textContent = !status.available ? TEXT.ask_none : (status.cloud ? TEXT.ask_cloud : TEXT.ask_local);
      form.hidden = !status.available;
      examples.replaceChildren(...(status.examples || []).map(q => {
        const b = Object.assign(document.createElement("button"), { type: "button", className: "ask-example", textContent: q });
        b.addEventListener("click", () => { input.value = q; form.requestSubmit(); });
        return b;
      }));
    }
    render();
    input.focus();
  };
  bubble.addEventListener("click", () => open(panel.hidden));
  document.getElementById("ask-close").addEventListener("click", () => open(false));
  document.getElementById("ask-clear").addEventListener("click", () => { chat = []; keep(); render(); input.focus(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden) open(false); });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    chat.push({ from: "me", text: question });
    const waiting = { from: "bot", text: TEXT.ask_wait || "…", error: true };
    chat.push(waiting);
    render();
    try {
      const res = await fetch(panel.dataset.ask, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
      const data = await res.json();
      chat[chat.indexOf(waiting)] = res.ok ? { from: "bot", text: data.text, links: data.links } : { from: "bot", text: data.error || TEXT.ask_error, error: true };
    } catch (err) {
      chat[chat.indexOf(waiting)] = { from: "bot", text: TEXT.ask_error, error: true };
    }
    keep();
    render();
  });
  if (new URLSearchParams(location.search).get("ask") === "1") open(true);
}

/* Tables whose columns are resized by dragging the edge between two titles (th[data-col]), like a spreadsheet:
   the table fills its card and its right edge stays; th[data-fixed] (Azioni) is never wider than it is; the widths
   are remembered in this browser, per table */
function initResizableColumns() {
  document.querySelectorAll("table[id]").forEach(table => {
    const heads = [...table.querySelectorAll("thead th")];
    const cols = heads.filter(th => th.dataset.col);               // the columns that take part (Azioni too)
    if (cols.length < 2) return;
    const others = heads.filter(th => !cols.includes(th));          // the box of the selection
    const locked = (th) => th.hasAttribute("data-fixed");           // Azioni: never wider than it is
    const key = `mfp-cols-${table.id}`;
    let saved = {};
    try { saved = JSON.parse(store.get(key) || "{}"); } catch (e) { saved = {}; }
    const defaults = Object.fromEntries(cols.map(th => [th.dataset.col, parseFloat(th.style.width) || 120]));
    const width = (th) => parseFloat(th.style.width);
    // the smallest a column can be: its title; Azioni neither grows nor shrinks
    const minOf = (th) => locked(th) ? defaults[th.dataset.col] : Math.ceil(th.querySelector(".col-title")?.scrollWidth || 40) + 32;
    const maxOf = (th) => locked(th) ? defaults[th.dataset.col] : Infinity;
    // the table fills its card: the columns share the room the box leaves, in the proportions last chosen
    const layout = () => {
      const room = table.parentElement.clientWidth - others.reduce((sum, th) => sum + (parseFloat(th.style.width) || 0), 0);
      const fixed = cols.filter(locked), free = cols.filter(th => !locked(th));
      fixed.forEach(th => { th.style.width = Math.min(saved[th.dataset.col] || defaults[th.dataset.col], defaults[th.dataset.col]) + "px"; });
      const left = room - fixed.reduce((sum, th) => sum + width(th), 0);
      const weights = free.map(th => saved[th.dataset.col] || defaults[th.dataset.col]);
      const total = weights.reduce((a, b) => a + b, 0);
      free.forEach((th, i) => { th.style.width = Math.max(minOf(th), left * weights[i] / total) + "px"; });
      table.style.width = table.parentElement.clientWidth + "px";
    };
    const save = () => {
      saved = Object.fromEntries(cols.map(th => [th.dataset.col, Math.round(width(th))]));
      store.set(key, JSON.stringify(saved));
    };
    // an edge between column k and k+1: to the right, k grows and the columns after it give way one after the other,
    // each down to its title; to the left the same the other way. The total never changes: the right edge stays.
    // The edge before Azioni (which never changes) widens or narrows the column before it against the ones on its left.
    const drag = (k, d, start) => {
      const w = start.slice(), mins = cols.map(minOf), maxs = cols.map(maxOf);
      if (locked(cols[k + 1])) {
        if (d > 0) {
          let left = Math.min(d, w.slice(0, k).reduce((sum, x, j) => sum + x - mins[j], 0));
          w[k] += left;
          for (let j = k - 1; j >= 0 && left > 0; j--) { const give = Math.min(left, w[j] - mins[j]); w[j] -= give; left -= give; }
        } else if (d < 0 && k > 0) {
          const give = Math.min(-d, w[k] - mins[k]);
          w[k] -= give;
          w[k - 1] += give;
        }
        cols.forEach((th, i) => { th.style.width = w[i] + "px"; });
        return;
      }
      if (d > 0) {
        let left = Math.min(d, maxs[k] - w[k], w.slice(k + 1).reduce((sum, x, j) => sum + x - mins[k + 1 + j], 0));
        w[k] += Math.max(left, 0);
        for (let j = k + 1; j < w.length && left > 0; j++) { const give = Math.min(left, w[j] - mins[j]); w[j] -= give; left -= give; }
      } else if (d < 0) {
        let left = Math.min(-d, maxs[k + 1] - w[k + 1], w.slice(0, k + 1).reduce((sum, x, j) => sum + x - mins[j], 0));
        w[k + 1] += Math.max(left, 0);
        for (let j = k; j >= 0 && left > 0; j--) { const give = Math.min(left, w[j] - mins[j]); w[j] -= give; left -= give; }
      }
      cols.forEach((th, i) => { th.style.width = w[i] + "px"; });
    };
    cols.slice(0, -1).forEach((th, k) => {
      const grip = Object.assign(document.createElement("span"), { className: "col-resizer", title: TEXT.resize || "" });
      grip.setAttribute("aria-hidden", "true");
      th.appendChild(grip);
      grip.addEventListener("click", e => e.stopPropagation());
      grip.addEventListener("pointerdown", e => {
        e.preventDefault();
        e.stopPropagation();
        const startX = e.clientX, start = cols.map(width);
        try { grip.setPointerCapture(e.pointerId); } catch (err) { /* a pointer the browser does not track */ }
        const move = ev => drag(k, ev.clientX - startX, start);
        const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); save(); };
        grip.addEventListener("pointermove", move);
        grip.addEventListener("pointerup", up);
      });
    });
    layout();
    window.addEventListener("resize", layout);
  });
}

/* Flash messages marked data-autohide fade out after a few seconds */
function initFlash() {
  document.querySelectorAll(".alert[data-autohide]").forEach(el => {
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 4000);
  });
}

/* Amounts written by the server as data-amount, shown in the chosen currency and number format */
function initAmounts() {
  document.querySelectorAll("[data-amount]").forEach(el => {
    const raw = parseFloat(el.dataset.amount);
    el.textContent = formatMoney(raw, el.dataset.currency, el.dataset.locale);
    if (raw > 0) el.classList.add("positive");
    else if (raw < 0) el.classList.add("negative");
  });
}

/* A question with OK / Annulla drawn by the app, instead of the browser's box («127.0.0.1 says…», which the desktop
   app's window shows raw). Resolves to true for OK; ESC, Annulla or a click outside are false. */
function mfpConfirm(message, options = {}) {
  return new Promise(resolve => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay open confirm-overlay";
    overlay.innerHTML = '<div class="modal modal-sm" role="alertdialog" aria-modal="true">'
      + '<div class="modal-body"><p class="confirm-text"></p></div>'
      + '<div class="modal-footer"><button type="button" class="btn btn-ghost" data-answer="no"></button>'
      + '<button type="button" class="btn" data-answer="yes"></button></div></div>';
    overlay.querySelector(".confirm-text").textContent = message;
    const yes = overlay.querySelector('[data-answer="yes"]');
    const no = overlay.querySelector('[data-answer="no"]');
    yes.textContent = options.ok || TEXT.ok || "OK";
    yes.classList.add(options.danger ? "btn-danger" : "btn-primary");
    no.textContent = TEXT.cancel || "Annulla";
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); done(false); } };
    const done = (answer) => {
      overlay.remove();
      document.removeEventListener("keydown", onKey, true);
      resolve(answer);
    };
    yes.addEventListener("click", () => done(true));
    no.addEventListener("click", () => done(false));
    overlay.addEventListener("click", e => { if (e.target === overlay) done(false); });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(overlay);
    yes.focus();
  });
}
window.mfpConfirm = mfpConfirm;

/* Forms marked data-confirm ask before they are sent (deletions): the first submit is held back, the answer sends it */
function initConfirm() {
  document.addEventListener("submit", e => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-confirm")) return;
    if (form.dataset.confirmed === "1") { delete form.dataset.confirmed; return; }
    e.preventDefault();
    e.stopImmediatePropagation();  // the form's own handlers run once, on the confirmed submit
    const submitter = e.submitter && e.submitter.form === form ? e.submitter : undefined;
    mfpConfirm(form.dataset.confirm || TEXT.confirm, { danger: true }).then(ok => {
      if (!ok) return;
      form.dataset.confirmed = "1";
      form.requestSubmit(submitter);
    });
  }, true);
}

/* The user's menu in the sidebar footer (account, sign out): opens above the name, closes on a click elsewhere or ESC */
function initUserMenu() {
  const button = document.getElementById("user-menu-btn");
  const menu = document.getElementById("user-menu");
  if (!button || !menu) return;
  const set = (open) => { menu.hidden = !open; button.setAttribute("aria-expanded", String(open)); };
  button.addEventListener("click", e => { e.stopPropagation(); set(menu.hidden); });
  document.addEventListener("click", e => { if (!menu.hidden && !menu.contains(e.target)) set(false); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") set(false); });
}

/* Buttons with data-copy put that text on the clipboard (a whole IBAN shown as its last digits) */
function initCopy() {
  document.addEventListener("click", e => {
    const button = e.target.closest("[data-copy]");
    if (!button) return;
    const done = () => {
      button.classList.add("copied");
      setTimeout(() => button.classList.remove("copied"), 1200);
    };
    const value = button.dataset.copy;
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(value).then(done, () => fallbackCopy(value) && done());
    } else if (fallbackCopy(value)) done();
  });
}

function fallbackCopy(value) {
  const area = Object.assign(document.createElement("textarea"), { value });
  area.style.position = "fixed"; area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch (e) { /* not allowed */ }
  area.remove();
  return ok;
}

/* Links with data-popup open their page in a window over this one (the transaction form): a click outside or ESC
   closes it; when the page inside saves or deletes, it tells this one, which reloads. Inside such a window
   (html.embedded) the buttons with data-close-embed close it. */
function initPopups() {
  if (document.documentElement.classList.contains("embedded")) {
    document.addEventListener("click", e => {
      if (e.target.closest("[data-close-embed]")) window.parent.postMessage({ mfp: "popup-close" }, window.location.origin);
      if (e.target.closest("[data-popup-back]")) window.parent.postMessage({ mfp: "popup-back" }, window.location.origin);
    });
    return;
  }
  let overlay = null;
  const close = () => { overlay?.remove(); overlay = null; document.documentElement.classList.remove("no-scroll"); };
  document.addEventListener("click", e => {
    const link = e.target.closest("a[data-popup]");
    if (!link || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    overlay = document.createElement("div");
    overlay.className = "modal-overlay open popup-overlay";
    const box = document.createElement("div");
    box.className = "modal popup-box";
    const frame = Object.assign(document.createElement("iframe"), { src: link.dataset.popup, title: link.title || "" });
    frame.className = "popup-frame";
    box.appendChild(frame);
    overlay.appendChild(box);
    overlay.addEventListener("click", ev => { if (ev.target === overlay) close(); });
    document.body.appendChild(overlay);
    document.documentElement.classList.add("no-scroll");
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && overlay) close(); });
  window.addEventListener("message", e => {
    if (e.origin !== window.location.origin || !e.data || !overlay) return;
    if (e.data.mfp === "popup-close") close();
    if (e.data.mfp === "popup-back") { close(); openModal("add-chooser"); }  // back to the choice of the round +
    if (e.data.mfp === "tx-done") {
      close();
      // the register shows the change: reload it, the note comes after; elsewhere the note at once
      if (document.getElementById("tx-table") || location.pathname.startsWith("/transactions")) {
        try { sessionStorage.setItem("mfp-toast", e.data.message || ""); } catch (err) { /* private mode */ }
        window.location.reload();
      } else {
        showToast(e.data.message);
      }
    }
  });
  try {
    const pending = sessionStorage.getItem("mfp-toast");
    if (pending !== null) { sessionStorage.removeItem("mfp-toast"); showToast(pending); }
  } catch (err) { /* private mode */ }
}

/* A note at the bottom of the page for a few seconds: what was done, and the way to the transactions */
function showToast(message) {
  document.querySelector(".toast")?.remove();
  const toast = Object.assign(document.createElement("div"), { className: "toast", role: "status" });
  toast.appendChild(Object.assign(document.createElement("span"), { textContent: message || TEXT.saved || "Fatto." }));
  if (!location.pathname.startsWith("/transactions")) {
    toast.appendChild(Object.assign(document.createElement("a"), { href: "/transactions/", className: "toast-link", textContent: TEXT.to_list || "Vai alla lista transazioni" }));
  }
  const close = Object.assign(document.createElement("button"), { type: "button", className: "toast-close", innerHTML: '<i class="bi bi-x"></i>' });
  close.setAttribute("aria-label", TEXT.cancel || "Chiudi");
  close.addEventListener("click", () => toast.remove());
  toast.appendChild(close);
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 7000);
}

/* The round +: a small window to choose a single transaction (a pop-up over the page) or a file to import */
function initAddChooser() {
  const bubble = document.getElementById("add-bubble");
  if (!bubble || !document.getElementById("add-chooser")) return;
  bubble.addEventListener("click", e => { e.preventDefault(); openModal("add-chooser"); });
  document.querySelectorAll("#add-chooser [data-popup]").forEach(a => a.addEventListener("click", () => closeModal("add-chooser")));
}

/* Tooltips: everything clickable says what it does when the pointer rests on it (a native tooltip, no info icons):
   its aria-label, or its text when the text is cut or is only an icon */
function initTooltips() {
  const describe = (el) => {
    if (el.title || el.closest(".kpi-window-menu") || el.matches(".info-tip")) return;
    const label = el.getAttribute("aria-label") || (el.textContent || "").replace(/\s+/g, " ").trim();
    if (label && label.length <= 120) el.title = label;
  };
  document.addEventListener("pointerover", e => {
    const el = e.target.closest?.("a[href], button, [role=button], select, summary, label.toggle-switch");
    if (el) describe(el);
  });
}

/* The «i» of an explanation: its note card opens on hover or focus, and stays open with a click (touch screens) */
function initInfoTips() {
  const card = Object.assign(document.createElement("div"), { className: "info-card", hidden: true });
  card.setAttribute("role", "tooltip");
  document.body.appendChild(card);
  let pinned = null;
  const show = (tip) => {
    card.textContent = tip.dataset.tip;
    card.hidden = false;
    const r = tip.getBoundingClientRect(), w = card.offsetWidth, h = card.offsetHeight;
    const left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    const top = r.bottom + 8 + h > window.innerHeight ? r.top - h - 8 : r.bottom + 8;
    card.style.left = left + "px";
    card.style.top = top + "px";
  };
  const hide = () => { if (!pinned) card.hidden = true; };
  document.addEventListener("mouseover", e => { const tip = e.target.closest?.(".info-tip"); if (tip) show(tip); });
  document.addEventListener("mouseout", e => { if (e.target.closest?.(".info-tip")) hide(); });
  document.addEventListener("focusin", e => { if (e.target.matches?.(".info-tip")) show(e.target); });
  document.addEventListener("focusout", e => { if (e.target.matches?.(".info-tip")) hide(); });
  document.addEventListener("click", e => {
    const tip = e.target.closest?.(".info-tip");
    pinned?.classList.remove("on");
    if (tip && tip !== pinned) { e.preventDefault(); e.stopPropagation(); pinned = tip; tip.classList.add("on"); show(tip); }
    else { pinned = null; card.hidden = true; }
  }, true);
  window.addEventListener("scroll", () => { if (!card.hidden) { pinned = null; card.hidden = true; } }, true);
}

/* Lists you can search: every drop-down with more than a few choices gets a text box over it; typing filters the
   choices (groups kept), arrows and Enter pick one, and the real <select> underneath is what the form sends.
   data-no-search keeps a plain drop-down. */
const COMBO_MIN = 7;
function initCombos(root = document) {
  root.querySelectorAll("select:not([multiple]):not([data-no-search]):not([data-combo])").forEach(select => {
    if (select.options.length < COMBO_MIN || select.closest("template")) return;
    select.dataset.combo = "1";
    const box = document.createElement("div");
    box.className = "combo";
    const input = Object.assign(document.createElement("input"), { type: "text", className: select.className.replace("form-select", "form-control") + " combo-input", autocomplete: "off" });
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    if (select.id) { input.id = select.id; select.id = select.id + "-select"; }  // a <label for> now points to the box
    if (select.getAttribute("aria-label")) input.setAttribute("aria-label", select.getAttribute("aria-label"));
    const list = document.createElement("ul");
    list.className = "combo-list";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    select.before(box);
    box.append(input, list, select);
    select.classList.add("combo-select");
    select.tabIndex = -1;
    let active = -1, items = [];
    const label = () => select.selectedOptions[0]?.textContent.trim() || "";
    const showValue = () => { input.value = label(); input.placeholder = label() || ""; input.disabled = select.disabled; };
    const render = (filter) => {
      const words = (filter || "").toLocaleLowerCase().split(/\s+/).filter(Boolean);
      list.replaceChildren();
      items = [];
      let group = null;
      [...select.options].forEach(option => {
        const text = option.textContent.trim();
        const parent = option.parentElement.tagName === "OPTGROUP" ? option.parentElement.label : "";
        const haystack = (text + " " + parent).toLocaleLowerCase();
        if (option.hidden || (words.length && !words.every(w => haystack.includes(w)))) return;
        if (parent && parent !== group) {
          group = parent;
          list.appendChild(Object.assign(document.createElement("li"), { className: "combo-group", textContent: parent }));
        }
        const li = Object.assign(document.createElement("li"), { className: "combo-option", textContent: text });
        li.setAttribute("role", "option");
        if (option.disabled) li.classList.add("disabled");
        if (option.selected) li.classList.add("selected");
        li.addEventListener("mousedown", e => { e.preventDefault(); if (!option.disabled) choose(option); });
        list.appendChild(li);
        items.push({ li, option });
      });
      if (!items.length) list.appendChild(Object.assign(document.createElement("li"), { className: "combo-empty", textContent: TEXT.no_match || "Nessun risultato" }));
      active = items.findIndex(i => i.option.selected);
      paint();
    };
    const paint = () => items.forEach((item, i) => {
      item.li.classList.toggle("active", i === active);
      if (i === active) item.li.scrollIntoView({ block: "nearest" });
    });
    const open = () => { if (select.disabled) return; list.hidden = false; input.setAttribute("aria-expanded", "true"); input.value = ""; render(""); };
    const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); showValue(); };
    const choose = (option) => {
      const changed = select.value !== option.value;
      select.value = option.value;
      close();
      if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
    };
    input.addEventListener("focus", open);
    input.addEventListener("click", () => { if (list.hidden) open(); });
    input.addEventListener("input", () => render(input.value));
    input.addEventListener("blur", close);
    input.addEventListener("keydown", e => {
      if (list.hidden && (e.key === "ArrowDown" || e.key === "Enter")) { open(); e.preventDefault(); return; }
      if (e.key === "ArrowDown") { active = Math.min(active + 1, items.length - 1); paint(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); paint(); e.preventDefault(); }
      else if (e.key === "Enter") { if (items[active]) { choose(items[active].option); } e.preventDefault(); }
      else if (e.key === "Escape") { close(); input.blur(); }
    });
    // the page may change the choices or the value (a preview, a form filled by script): follow it
    new MutationObserver(() => { if (list.hidden) showValue(); else render(input.value); }).observe(select, { childList: true, subtree: true, attributes: true });
    select.addEventListener("change", () => { if (list.hidden) showValue(); });
    showValue();
  });
}
window.initCombos = initCombos;

/* Amount boxes take numbers only: digits, one decimal comma or point, a sign in front; letters are refused as typed
   and taken out of what is pasted */
function initNumberOnly() {
  const numeric = (el) => el.matches?.('input[inputmode="decimal"], input[inputmode="numeric"], input[type="number"]');
  document.addEventListener("keydown", e => {
    if (!numeric(e.target) || e.ctrlKey || e.metaKey || e.altKey || e.key.length !== 1) return;
    if (!/[0-9.,+\-−]/.test(e.key) || (e.target.inputMode === "numeric" && !/[0-9]/.test(e.key))) e.preventDefault();
  });
  document.addEventListener("input", e => {
    if (!numeric(e.target) || e.target.type === "number") return;
    const clean = e.target.value.replace(e.target.inputMode === "numeric" ? /[^0-9]/g : /[^0-9.,+\-−\s]/g, "");
    if (clean !== e.target.value) e.target.value = clean;
  });
}

/* A date that must be given starts on today (the calendar still opens, and it can be typed over) */
function initToday() {
  const today = new Date();
  const iso = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  document.querySelectorAll('input[type="date"][required]:not([data-no-today])').forEach(el => { if (!el.value) el.value = iso; });
}

/* A round button with two arrows, bottom right: shown while a long page is scrolled and its end is far below;
   a click goes to the end of the page */
function initToBottom() {
  const button = Object.assign(document.createElement("button"), { type: "button", className: "to-bottom", hidden: true });
  button.innerHTML = '<i class="bi bi-chevron-double-down"></i>';
  button.setAttribute("aria-label", TEXT.to_bottom || "Vai in fondo");
  button.title = TEXT.to_bottom || "Vai in fondo";
  document.body.appendChild(button);
  // a long page: «to the bottom» while far from it, «back to the top» once at its end
  let up = false;
  const update = () => {
    const page = document.documentElement.scrollHeight, left = page - (window.scrollY + window.innerHeight);
    const long = page > window.innerHeight * 1.5;
    up = long && left < 120;
    button.hidden = !(long && (up || left > window.innerHeight));
    button.querySelector("i").className = up ? "bi bi-chevron-double-up" : "bi bi-chevron-double-down";
    const label = up ? (TEXT.to_top || "Torna su") : (TEXT.to_bottom || "Vai in fondo");
    button.title = label;
    button.setAttribute("aria-label", label);
  };
  button.addEventListener("click", () => window.scrollTo({ top: up ? 0 : document.documentElement.scrollHeight, behavior: "smooth" }));
  window.addEventListener("scroll", update, { passive: true });
  window.addEventListener("resize", update);
  update();
}

/* Areas that scroll sideways (tables, rows of tabs): two arrows appear on the edges while there is more to see;
   a click scrolls by most of the width, and the area can be focused and moved with the arrow keys */
function initScrollArrows() {
  const boxes = () => document.querySelectorAll(".table-wrapper, .settings-nav, .tabs, .tab-bar, .statement-tabs");
  const wire = (box) => {
    if (box.dataset.arrows) return;
    box.dataset.arrows = "1";
    const holder = document.createElement("div");
    holder.className = "scroll-arrows";
    box.parentNode.insertBefore(holder, box);
    holder.appendChild(box);
    const make = (dir) => {
      const btn = Object.assign(document.createElement("button"), { type: "button", className: `scroll-arrow scroll-arrow-${dir}`,
        title: dir === "left" ? (TEXT.scroll_left || "Scorri a sinistra") : (TEXT.scroll_right || "Scorri a destra") });
      btn.innerHTML = `<i class="bi bi-chevron-${dir}"></i>`;
      btn.addEventListener("click", () => box.scrollBy({ left: (dir === "left" ? -1 : 1) * box.clientWidth * 0.8, behavior: "smooth" }));
      holder.appendChild(btn);
      return btn;
    };
    const left = make("left"), right = make("right");
    const update = () => {
      const more = box.scrollWidth - box.clientWidth > 2;
      left.hidden = !more || box.scrollLeft <= 1;
      right.hidden = !more || box.scrollLeft + box.clientWidth >= box.scrollWidth - 1;
      if (more && !box.hasAttribute("tabindex")) box.tabIndex = 0;  // the arrow keys scroll it once focused
    };
    box.addEventListener("scroll", update, { passive: true });
    new ResizeObserver(update).observe(box);
    update();
  };
  boxes().forEach(wire);
}

/* The ← at the left of the title: back to the page seen before, when it was a page of the app */
function initBack() {
  const back = document.getElementById("nav-back");
  if (!back) return;
  let fromApp = false;
  try { fromApp = !!document.referrer && new URL(document.referrer).origin === window.location.origin; } catch (e) { /* no referrer */ }
  back.hidden = !(fromApp && window.history.length > 1);
  back.addEventListener("click", () => window.history.back());
}

/* Active menu item for pages the server does not mark (e.g. /transactions/duplicates): the longest matching link */
function initActiveNav() {
  if (document.querySelector(".sidebar .nav-item.active")) return;
  const path = window.location.pathname === "/" ? "/dashboard" : window.location.pathname;
  const best = [...document.querySelectorAll(".sidebar .nav-item[href]")]
    .filter(link => path.startsWith(link.getAttribute("href")))
    .sort((a, b) => b.getAttribute("href").length - a.getAttribute("href").length)[0];
  best?.classList.add("active");
}

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initSidebar();
  initNavSections();
  initAskPanel();
  initAddChooser();
  initResizableColumns();
  // Tags: chips picked from the tags already used, or new ones (Enter or comma)
  document.querySelectorAll("input[data-tag-input]").forEach(input => initTagInput(input, TEXT));
  initFlash();
  initAmounts();
  initConfirm();
  initUserMenu();
  initBack();
  initCopy();
  initPopups();
  initTooltips();
  initInfoTips();
  initCombos();
  initNumberOnly();
  initToday();
  initToBottom();
  initScrollArrows();
  initActiveNav();
});
