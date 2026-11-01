/**
 * blocks.js — pages the user arranges (Modifica): the dashboard, the reminders.
 * Blocks are moved (drag or arrows), one to three thirds wide, of a chosen height, switched off; a second grid of cards
 * is one or two columns wide. Every change is saved with a POST of {<grid key>: [{id, span, height?, visible}]};
 * {"reset": true} goes back to the default. The controls are in the top bar (partials/blocks.html).
 * A block switched off (the eye) stays in place, greyed, while editing — the eye brings it back — and is hidden
 * once done; data-off keeps the choice, the hidden attribute only what is shown.
 */
function initBlockEditor({ grids, saveUrl }) {
  grids = grids.filter(g => g.el);
  if (!grids.length) return;
  const byElement = new Map(grids.map(g => [g.el, g]));
  const $ = (id) => document.getElementById(id);
  const editButton = $("layout-edit"), hiddenWrap = $("layout-hidden-wrap"), hiddenButton = $("layout-hidden-btn");
  const hiddenList = $("layout-hidden");
  const editOnly = ["layout-title", "layout-reset", "layout-done"].map($);
  const editOff = ["layout-edit", "layout-manage"].map($);
  const widgets = () => grids.flatMap(g => [...g.el.querySelectorAll(":scope > .fc-widget")]);
  const gridOf = (w) => byElement.get(w.parentElement);
  const SPAN_LABELS = { 3: { 1: "⅓", 2: "⅔", 3: "1/1" }, 2: { 1: "×1", 2: "×2" } };
  const HEIGHT_LABELS = { 0: "Auto", 1: "M", 2: "L", 3: "XL" };
  let editing = false, dragged = null, saveTimer = null;
  const isOff = (w) => w.dataset.off === "1";
  widgets().forEach(w => { w.dataset.off = w.hidden ? "1" : "0"; });
  const setOff = (w, off) => {
    w.dataset.off = off ? "1" : "0";
    w.hidden = off && !editing;
    const eye = w.querySelector('[data-act="hide"]');
    if (eye) {
      eye.querySelector("i").className = off ? "bi bi-eye" : "bi bi-eye-slash";
      eye.title = off ? (window.MFP_TEXT?.show || "Mostra") : (window.MFP_TEXT?.hide || "Nascondi");
    }
  };

  const paint = () => widgets().forEach(w => {
    const span = w.querySelector(".span-label"), height = w.querySelector(".height-label");
    if (span) span.textContent = SPAN_LABELS[gridOf(w).spans][w.dataset.span] || "";
    if (height) height.textContent = HEIGHT_LABELS[w.dataset.height] || HEIGHT_LABELS[0];
  });
  // resize, then draw: a chart busy with an animation keeps a resize for its next drawing
  const redrawCharts = (widget) => requestAnimationFrame(() => (widget ? [widget] : widgets()).forEach(w =>
    w.querySelectorAll("canvas").forEach(c => { const chart = window.Chart?.getChart(c); chart?.resize(); chart?.update("none"); })));

  function save() {
    renderHidden();
    paint();
    clearTimeout(saveTimer);
    const body = Object.fromEntries(grids.map(g => [g.key, [...g.el.querySelectorAll(":scope > .fc-widget")].map(w => ({
      id: w.dataset.widget, span: +w.dataset.span, ...(g.heights ? { height: +w.dataset.height || 0 } : {}), visible: !isOff(w),
    }))]));
    saveTimer = setTimeout(() => fetch(saveUrl, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }), 250);
  }
  function renderHidden() {
    const hidden = widgets().filter(isOff);
    hiddenWrap.hidden = !editing || !hidden.length;
    $("layout-hidden-count").textContent = hidden.length;
    if (!hidden.length) hiddenList.hidden = true;
    hiddenList.replaceChildren(...hidden.map(w => {
      const chip = Object.assign(document.createElement("button"), { type: "button", className: "layout-chip" });
      chip.innerHTML = '<i class="bi bi-plus-lg"></i> ';
      chip.append(w.dataset.title);
      chip.addEventListener("click", () => { setOff(w, false); redrawCharts(w); save(); });
      return chip;
    }));
  }
  function setEditing(on) {
    editing = on;
    document.body.classList.toggle("fc-editing", on);
    editOnly.forEach(el => { if (el) el.hidden = !on; });
    editOff.forEach(el => { if (el) el.hidden = on; });
    hiddenList.hidden = true;
    editButton?.setAttribute("aria-pressed", String(on));
    widgets().forEach(w => { w.draggable = on; setOff(w, isOff(w)); });  // greyed while editing, hidden after
    renderHidden();
    if (on) { paint(); redrawCharts(); }  // the charts of blocks that were hidden take their size
  }
  // the hidden blocks: a small menu under «Nascosti», each one shown again with a click
  hiddenButton?.addEventListener("click", e => {
    e.stopPropagation();
    hiddenList.hidden = !hiddenList.hidden;
    hiddenButton.setAttribute("aria-expanded", String(!hiddenList.hidden));
  });
  document.addEventListener("click", e => { if (!hiddenWrap.contains(e.target)) hiddenList.hidden = true; });
  editButton?.addEventListener("click", () => setEditing(!editing));
  $("layout-done")?.addEventListener("click", () => setEditing(false));
  $("layout-reset")?.addEventListener("click", async () => {
    await fetch(saveUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"reset": true}' });
    location.reload();
  });

  grids.forEach(g => {
    g.el.addEventListener("click", e => {
      const button = e.target.closest(".fc-widget-tools [data-act]");
      if (!button) return;
      const w = button.closest(".fc-widget");
      const act = button.dataset.act;
      if (act === "prev") w.previousElementSibling?.before(w);  // in Modifica every block is in view, switched off too
      if (act === "next") w.nextElementSibling?.after(w);
      if (act === "span") { w.dataset.span = String(w.dataset.span % g.spans + 1); redrawCharts(w); }
      if (act === "height") { w.dataset.height = String(((+w.dataset.height || 0) + 1) % 4); redrawCharts(); }  // the row follows
      if (act === "hide") setOff(w, !isOff(w));  // the eye: off (greyed) or back on
      save();
    });
    // a block moves among the blocks of its own grid
    g.el.addEventListener("dragstart", e => {
      const w = e.target.closest?.(".fc-widget");
      if (!editing || !w) return;
      dragged = w;
      w.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", w.dataset.widget);
    });
    g.el.addEventListener("dragover", e => {
      if (!dragged) return;
      e.preventDefault();
      const target = e.target.closest(".fc-widget");
      if (!target || target === dragged || target.parentElement !== dragged.parentElement) return;
      const r = target.getBoundingClientRect();
      const before = target.dataset.span === "3" ? e.clientY < r.top + r.height / 2 : e.clientX < r.left + r.width / 2;
      const reference = before ? target : target.nextElementSibling;
      if (reference !== dragged && dragged.nextElementSibling !== reference) g.el.insertBefore(dragged, reference);
    });
    g.el.addEventListener("drop", e => { if (dragged) e.preventDefault(); });
    g.el.addEventListener("dragend", () => {
      if (!dragged) return;
      dragged.classList.remove("dragging");
      dragged = null;
      redrawCharts();
      save();
    });
  });
}
window.initBlockEditor = initBlockEditor;
