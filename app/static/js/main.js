/**
 * main.js — UI interactions for MyFinancePlace
 */

/* ── Mobile sidebar toggle ────────────────────────────────────────────── */
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

/* ── Dark / Light mode toggle ──────────────────────────────────────────── */
function applyTheme(dark) {
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  document.getElementById("theme-icon-dark").style.display  = dark ? "none"   : "";
  document.getElementById("theme-icon-light").style.display = dark ? ""       : "none";
  localStorage.setItem("mfp-theme", dark ? "dark" : "light");
}

document.addEventListener("DOMContentLoaded", () => {

  // Sync toggle icon with the theme already applied in <head>
  const isDark = document.documentElement.getAttribute("data-theme") === "dark";
  applyTheme(isDark);

  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const currentlyDark = document.documentElement.getAttribute("data-theme") === "dark";
    applyTheme(!currentlyDark);
  });

  // Close modal when clicking the overlay background
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  // Close modal on ESC key
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay.open").forEach(m => closeModal(m.id));
    }
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
      try { localStorage.setItem("mfp-sidebar-hidden", hidden ? "1" : "0"); } catch (e) { /* private mode */ }
    });
  }
  overlay && overlay.addEventListener("click", closeSidebar);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeSidebar(); });

  // Collapsible sections, remembered in this browser
  const saveCollapsed = () => {
    const closed = [...document.querySelectorAll(".nav-section.collapsed")].map(s => s.dataset.section);
    try { localStorage.setItem("mfp-nav-collapsed", JSON.stringify(closed)); } catch (e) { /* private mode */ }
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
    try { localStorage.setItem("mfp-sidebar-mini", mini ? "1" : "0"); } catch (e) { /* private mode */ }
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

  /* ── Nav active state from URL ───────────────────────────────────────── */
  const path = window.location.pathname;
  document.querySelectorAll(".nav-item[href]").forEach(link => {
    if (path.startsWith(link.getAttribute("href")) && link.getAttribute("href") !== "/") {
      link.classList.add("active");
    } else if (link.getAttribute("href") === "/dashboard" && path === "/") {
      link.classList.add("active");
    }
  });
});

/* ── Number formatting helper ──────────────────────────────────────────── */
function formatCurrency(value, currency = "EUR", locale = "it-IT") {
  return new Intl.NumberFormat(locale, {
    style: "currency", currency,
    minimumFractionDigits: 2,
  }).format(value);
}

function formatPercent(value, decimals = 1) {
  return (value >= 0 ? "+" : "") + value.toFixed(decimals) + "%";
}
