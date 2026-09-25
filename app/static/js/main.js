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

/* ── Light / dark mode ─────────────────────────────────────────────────── */
// The user's choice is remembered; until they choose, the app follows the operating system.
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function applyTheme(theme, remember) {
  document.documentElement.setAttribute("data-theme", theme);
  document.querySelectorAll("[data-theme-choice]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme));
  });
  if (remember) store.set("mfp-theme", theme);
  document.dispatchEvent(new CustomEvent("mfp:themechange", { detail: { theme } }));
}

document.addEventListener("DOMContentLoaded", () => {

  // Theme switch: show the theme applied in <head>, change it on click
  applyTheme(currentTheme(), false);
  document.querySelectorAll("[data-theme-choice]").forEach(button => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeChoice, true));
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

  /* ── Sidebar ─────────────────────────────────────────────────────────── */
  const toggleBtn = document.getElementById("sidebar-toggle");
  const sidebar   = document.getElementById("sidebar");
  const overlay   = document.getElementById("sidebar-overlay");

  // The ☰ button: on desktop it hides / shows the whole left column (remembered);
  // on phones and tablets it slides the sidebar in, and the dark overlay or ESC closes it
  const phone = window.matchMedia("(max-width: 992px)");
  const closeSidebar = () => {
    sidebar && sidebar.classList.remove("open");
    overlay && overlay.classList.remove("active");
  };
  const applyHidden = (hidden) => {
    document.documentElement.classList.toggle("sidebar-hidden", hidden);
    if (!toggleBtn) return;
    const label = hidden ? "Mostra il menu" : "Nascondi il menu";
    toggleBtn.setAttribute("aria-label", label);
    toggleBtn.setAttribute("aria-expanded", String(!hidden));
    toggleBtn.title = label;
  };
  applyHidden(document.documentElement.classList.contains("sidebar-hidden"));
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", () => {
      if (phone.matches) {
        sidebar.classList.toggle("open");
        overlay && overlay.classList.toggle("active", sidebar.classList.contains("open"));
        return;
      }
      const hidden = !document.documentElement.classList.contains("sidebar-hidden");
      applyHidden(hidden);
      store.set("mfp-sidebar-hidden", hidden ? "1" : "0");
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

  // Icons-only sidebar (desktop): more room for tables; each icon gets its name as a tooltip
  const miniToggle = document.getElementById("sidebar-mini-toggle");
  const applyMini = (mini) => {
    document.documentElement.classList.toggle("sidebar-mini", mini);
    document.querySelectorAll(".sidebar .nav-item").forEach(item => {
      const label = item.querySelector(".nav-label");
      if (mini && label) item.title = label.textContent.trim();
      else item.removeAttribute("title");
    });
    if (miniToggle) {
      miniToggle.setAttribute("aria-label", mini ? "Espandi il menu" : "Riduci il menu");
      miniToggle.title = mini ? "Espandi il menu" : "";
    }
  };
  applyMini(document.documentElement.classList.contains("sidebar-mini"));
  miniToggle && miniToggle.addEventListener("click", () => {
    const mini = !document.documentElement.classList.contains("sidebar-mini");
    applyMini(mini);
    store.set("mfp-sidebar-mini", mini ? "1" : "0");
  });

  /* ── Auto-dismiss flash alerts ──────────────────────────────────────── */
  document.querySelectorAll(".alert[data-autohide]").forEach(el => {
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 4000);
  });

  /* ── Amount formatter (tabular display) ─────────────────────────────── */
  document.querySelectorAll("[data-amount]").forEach(el => {
    const raw    = parseFloat(el.dataset.amount);
    const locale = el.dataset.locale  || "it-IT";
    const currency = el.dataset.currency || "EUR";
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
      if (!confirm(form.dataset.confirm || "Are you sure?")) {
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
