/**
 * main.js — UI interactions for MyFinancePlace
 */

/* ── Preferences kept in this browser (private mode may refuse them) ──── */
const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } },
};

/* ── Modal helpers ─────────────────────────────────────────────────────── */
function openModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.add("open");
  document.body.style.overflow = "hidden";
  // Focus first input for accessibility
  setTimeout(() => { const f = el.querySelector("input, select, textarea"); if (f) f.focus(); }, 80);
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove("open");
  document.body.style.overflow = "";
}

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

document.addEventListener("DOMContentLoaded", () => {

  // Theme switch: show the theme applied in <head>, change it on click
  applyTheme(currentTheme(), false);
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    applyTheme(currentTheme() === "dark" ? "light" : "dark", true);
  });
  // Follow the operating system while the user has not chosen
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", e => {
    if (!store.get("mfp-theme")) applyTheme(e.matches ? "dark" : "light", false);
  });

  // Close modal when clicking the overlay background
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  // Interface texts in the chosen language (set by base.html), Italian when missing
  const text = Object.assign({
    expand_menu: "Espandi il menu", shrink_menu: "Riduci il menu", confirm: "Sei sicuro?",
  }, window.MFP_TEXT || {});

  /* ── Sidebar ─────────────────────────────────────────────────────────── */
  const toggleBtn = document.getElementById("sidebar-toggle");
  const sidebar   = document.getElementById("sidebar");
  const overlay   = document.getElementById("sidebar-overlay");

  // The ☰ button: on desktop it switches the menu between icons + names and icons only (remembered),
  // so the menu never disappears; on phones and tablets it slides the sidebar in, the overlay or ESC closes it
  const phone = window.matchMedia("(max-width: 992px)");
  const closeSidebar = () => {
    sidebar && sidebar.classList.remove("open");
    overlay && overlay.classList.remove("active");
  };
  // Icons only: more room for tables; each icon gets its name as a tooltip
  const applyMini = (mini) => {
    document.documentElement.classList.toggle("sidebar-mini", mini);
    document.querySelectorAll(".sidebar .nav-item").forEach(item => {
      const label = item.querySelector(".nav-label");
      if (mini && label) item.title = label.textContent.trim();
      else item.removeAttribute("title");
    });
    if (!toggleBtn) return;
    const label = mini ? text.expand_menu : text.shrink_menu;
    toggleBtn.setAttribute("aria-label", label);
    toggleBtn.setAttribute("aria-expanded", String(!mini));
    toggleBtn.title = label;
  };
  applyMini(document.documentElement.classList.contains("sidebar-mini"));
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      if (phone.matches) {
        sidebar.classList.toggle("open");
        overlay && overlay.classList.toggle("active", sidebar.classList.contains("open"));
        return;
      }
      const mini = !document.documentElement.classList.contains("sidebar-mini");
      applyMini(mini);
      store.set("mfp-sidebar-mini", mini ? "1" : "0");
    });
  }
  overlay && overlay.addEventListener("click", closeSidebar);

  // ESC closes the open modal and the phone sidebar
  document.addEventListener("keydown", e => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".modal-overlay.open").forEach(m => closeModal(m.id));
    closeSidebar();
  });

  // Collapsible sections, remembered in this browser
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

  /* ── Tags: chips picked from the tags already used, or new ones (Enter or comma) ── */
  document.querySelectorAll("input[data-tag-input]").forEach(input => initTagInput(input, text));

  /* ── Auto-dismiss flash alerts ──────────────────────────────────────── */
  document.querySelectorAll(".alert[data-autohide]").forEach(el => {
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 4000);
  });

  /* ── Amount formatter (tabular display) ─────────────────────────────── */
  document.querySelectorAll("[data-amount]").forEach(el => {
    const raw    = parseFloat(el.dataset.amount);
    // number format and currency chosen in Settings (on <html>), unless the element says otherwise
    const locale = el.dataset.locale || document.documentElement.dataset.locale || "it-IT";
    const currency = el.dataset.currency || document.documentElement.dataset.currency || "EUR";
    el.textContent = new Intl.NumberFormat(locale, {
      style: "currency", currency,
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    }).format(raw);
    if (raw > 0) el.classList.add("positive");
    else if (raw < 0) el.classList.add("negative");
  });

  /* ── Confirm-before-delete ───────────────────────────────────────────── */
  document.querySelectorAll("form[data-confirm]").forEach(form => {
    form.addEventListener("submit", (e) => {
      if (!confirm(form.dataset.confirm || text.confirm)) {
        e.preventDefault();
      }
    });
  });

  /* ── Active menu item for pages the server does not mark (e.g. /transactions/duplicates) ── */
  if (!document.querySelector(".sidebar .nav-item.active")) {
    const path = window.location.pathname === "/" ? "/dashboard" : window.location.pathname;
    const best = [...document.querySelectorAll(".sidebar .nav-item[href]")]
      .filter(link => path.startsWith(link.getAttribute("href")))
      .sort((a, b) => b.getAttribute("href").length - a.getAttribute("href").length)[0];
    best?.classList.add("active");
  }
});
