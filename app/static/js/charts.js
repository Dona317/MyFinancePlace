/**
 * charts.js — Chart.js configuration helpers
 * Reads color values from CSS variables so charts always match the theme.
 */

// Colors of the current theme; re-read when the user switches between light and dark mode
const Theme = {};

function readTheme() {
  const style = getComputedStyle(document.documentElement);
  const get = (v) => style.getPropertyValue(v).trim();
  Object.assign(Theme, {
    primary:   get("--clr-primary"),
    positive:  get("--clr-positive"),
    negative:  get("--clr-negative"),
    neutral:   get("--clr-neutral"),
    warning:   get("--clr-warning"),
    purple:    get("--chart-5"),
    textMuted: get("--clr-text-muted"),
    border:    get("--clr-border"),
    card:      get("--clr-bg-card") || "#FFFFFF",
    chart: [
      get("--chart-1"), get("--chart-2"), get("--chart-3"),
      get("--chart-4"), get("--chart-5"), get("--chart-6"),
      get("--chart-7"), get("--chart-8"),
    ],
    // income and expenses never share colours (Impostazioni → Visualizzazione); "income" / "expense" as a series
    // colour is the first of each
    incomes:  [1, 2, 3, 4, 5, 6, 7, 8].map(i => get(`--inc-${i}`)),
    expenses: [1, 2, 3, 4, 5, 6, 7, 8].map(i => get(`--exp-${i}`)),
  });
  Theme.income = Theme.incomes[0] || Theme.positive;
  Theme.expense = Theme.expenses[0] || Theme.negative;
  Chart.defaults.color = Theme.textMuted;
}

// The colours of a chart: the income or the expense palette (opts.palette), else the general one
function paletteOf(opts) {
  const colours = opts?.palette === "income" ? Theme.incomes : opts?.palette === "expense" ? Theme.expenses : null;
  return colours && colours.every(Boolean) ? colours : Theme.chart;
}

// A dataset color can be a token name ("positive", "negative", …) so it follows the theme
function themeColor(color, fallback) {
  return (typeof color === "string" && typeof Theme[color] === "string" && Theme[color]) || color || fallback;
}

// Global Chart.js defaults
readTheme();
Chart.defaults.font.family   = getComputedStyle(document.documentElement).getPropertyValue("--font-body").trim();
Chart.defaults.font.size     = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 16;
Chart.defaults.plugins.tooltip.backgroundColor = "#1A2540";
Chart.defaults.plugins.tooltip.titleColor = "#FFFFFF";
Chart.defaults.plugins.tooltip.bodyColor  = "#C6D4EE";
Chart.defaults.plugins.tooltip.borderColor = "#243570";
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding    = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;

/* Legends in HTML: the canvas legend cuts entries off when there are many. A pie has its legend on its right, in
   columns that scroll sideways; a line or bar chart has it above, one row that scrolls sideways. The chart keeps all
   the rest of its box. Each entry shows or hides its series (or slice), one button selects or deselects them all.
   A chart can use a list of its page instead (opts.legendList: one <li> per slice, its .category-legend-dot becomes
   the switch); that list moves beside the pie the same way. */
const isPie = (chart) => ["pie", "doughnut"].includes(chart.config.type);

/* A slice's share of the slices shown, «35,9%»: hiding some (an exceptional expense) makes the rest the new 100%.
   A hidden slice has no share. */
function sliceShare(chart, index) {
  if (!chart.getDataVisibility(index)) return "–";
  const data = chart.data.datasets[0].data;
  const total = data.reduce((sum, v, i) => sum + (chart.getDataVisibility(i) ? Math.abs(Number(v) || 0) : 0), 0);
  const share = total ? Math.abs(Number(data[index]) || 0) / total * 100 : 0;
  return `${share.toLocaleString(document.documentElement.dataset.locale || "it-IT", { maximumFractionDigits: 1 })}%`;
}

function legendSwitch(chart) {
  const pie = isPie(chart);
  return {
    shown: (i) => pie ? chart.getDataVisibility(i) : chart.isDatasetVisible(i),
    set: (i, on) => {
      if (pie) { if (chart.getDataVisibility(i) !== on) chart.toggleDataVisibility(i); }
      else chart.setDatasetVisibility(i, on);
    },
  };
}

function legendAllButton(chart, indexes) {
  const text = window.MFP_TEXT || {};
  const button = Object.assign(document.createElement("button"), { type: "button", className: "chart-legend-all" });
  const { shown, set } = legendSwitch(chart);
  const all = indexes.every(shown);
  button.textContent = all ? (text.deselect_all || "Deseleziona tutto") : (text.select_all || "Seleziona tutto");
  button.addEventListener("click", () => { indexes.forEach(i => set(i, !all)); chart.update(); });
  return button;
}

/* The box of the chart (the element with its height, holding only the canvas) becomes: the canvas in its own
   wrapper, the legend beside it (a pie) or above it. Done before the chart measures itself. */
function legendLayout(chart, options) {
  const canvas = chart.canvas;
  if (canvas.$legend) return canvas.$legend;  // a chart drawn again (theme change): the layout is there
  const box = canvas.parentElement;
  const legend = Object.assign(document.createElement("div"), { className: "chart-legend" });
  canvas.$legend = legend;
  if (box.children.length !== 1 || box.classList.contains("card-body")) {
    canvas.after(legend);  // no box of its own: the legend goes under it
    return legend;
  }
  const wrap = Object.assign(document.createElement("div"), { className: "chart-canvas" });
  box.classList.add("chart-with-legend", isPie(chart) ? "legend-side" : "legend-top");
  canvas.before(wrap);
  wrap.appendChild(canvas);
  if (isPie(chart)) box.append(legend); else box.prepend(legend);
  if (options.list) legend.appendChild(options.list);  // the page's list of categories, beside the pie
  return legend;
}

const htmlLegend = {
  id: "htmlLegend",
  beforeInit(chart, _args, options) {
    if (options.display || options.list) legendLayout(chart, options);
  },
  afterUpdate(chart, _args, options) {
    if (options.list) return pageLegend(chart, options.list);
    if (!options.display) return;
    const legend = chart.canvas.$legend;
    const pie = isPie(chart);
    const items = chart.options.plugins.legend.labels.generateLabels(chart)
      .filter(item => !options.filter || options.filter(item));
    const index = (item) => pie ? item.index : item.datasetIndex;
    const { shown, set } = legendSwitch(chart);
    const list = Object.assign(document.createElement("ul"), { className: "chart-legend-list" });
    items.forEach(item => {
      const i = index(item);
      const button = Object.assign(document.createElement("button"), { type: "button", className: "chart-legend-item" });
      button.setAttribute("aria-pressed", String(shown(i)));
      const dot = Object.assign(document.createElement("span"), { className: "chart-legend-dot" });
      // a line shows the colour of its stroke (its fill is almost transparent), a bar or a slice its fill
      const line = !pie && (chart.data.datasets[i].type || chart.config.type) === "line";
      dot.style.background = line ? item.strokeStyle : item.fillStyle;
      if (pie) {  // a slice: its name and share, its amount in euro under them
        const text = Object.assign(document.createElement("span"), { className: "chart-legend-text" });
        const name = Object.assign(document.createElement("span"), { textContent: item.text + " " });
        name.appendChild(Object.assign(document.createElement("small"), { textContent: sliceShare(chart, i) }));
        const amount = Object.assign(document.createElement("span"), { className: "chart-legend-amount",
          textContent: formatMoney(chart.data.datasets[0].data[i]) });
        text.append(name, amount);
        button.append(dot, text);
      } else {
        button.append(dot, document.createTextNode(item.text));
      }
      button.addEventListener("click", () => { set(i, !shown(i)); chart.update(); });
      const li = document.createElement("li");
      li.appendChild(button);
      list.appendChild(li);
    });
    const scroll = legend.querySelector(".chart-legend-list")?.scrollLeft || 0;
    legend.replaceChildren(...(items.length > 2 ? [legendAllButton(chart, items.map(index))] : []), list);
    list.scrollLeft = scroll;  // a click does not jump back to the start of a long list
  },
};

function pageLegend(chart, list) {
  const { shown } = legendSwitch(chart);
  const rows = [...list.children];
  list.$chart = chart;  // the chart drawn now: a theme change draws a new one on the same list
  rows.forEach((li, i) => {
    li.classList.toggle("off", !shown(i));
    const share = li.querySelector(".category-legend-share");
    if (share) share.textContent = sliceShare(chart, i);  // of the slices shown
    const dot = li.querySelector(".category-legend-dot");
    if (dot && !dot.dataset.switch) {
      dot.dataset.switch = "1";
      dot.setAttribute("role", "button");
      dot.tabIndex = 0;
      dot.title = (window.MFP_TEXT || {}).show_hide || "Mostra o nascondi";
      const flip = () => {
        const { shown, set } = legendSwitch(list.$chart);
        set(i, !shown(i));
        list.$chart.update();
      };
      dot.addEventListener("click", flip);
      dot.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flip(); } });
    }
  });
  list.classList.add("chart-legend-scroll");
  if (list.previousElementSibling?.classList.contains("chart-legend-all")) list.previousElementSibling.remove();
  if (rows.length > 2) list.before(legendAllButton(chart, rows.map((_, i) => i)));
}

Chart.register(htmlLegend);

// Every chart built by the helpers below, so it can be redrawn in the new theme's colors
const themedCharts = [];

function registerChart(chart, rebuild) {
  if (chart) themedCharts.push({ chart, rebuild });
  return chart;
}

document.addEventListener("mfp:themechange", () => {
  readTheme();
  themedCharts.forEach(entry => {
    entry.chart.destroy();
    entry.chart = entry.rebuild();
  });
});

/* ── Factory helpers ────────────────────────────────────────────────────── */

/**
 * Create a line chart (e.g., monthly cash flow trend).
 * @param {string} canvasId
 * @param {string[]} labels
 * @param {Array<{label, data, color?}>} datasets
 */
function makeLineChart(canvasId, labels, datasets, opts = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return registerChart(buildLineChart(ctx, labels, datasets, opts), () => buildLineChart(ctx, labels, datasets, opts));
}

function buildLineChart(ctx, labels, datasets, opts = {}) {
  // opts.percent: values are percentages (axis and tooltip with %)
  const percent = (v) => (v === null || v === undefined) ? "—" : `${Number(v).toLocaleString(document.documentElement.dataset.locale || "it-IT", { maximumFractionDigits: 1 })}%`;
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: datasets.map((ds, i) => ({
        label: ds.label,
        data:  ds.data,
        borderColor:     themeColor(ds.color, paletteOf(opts)[i % 8]),
        backgroundColor: hexAlpha(themeColor(ds.color, paletteOf(opts)[i % 8]), ds.fillAlpha ?? 0.08),
        tension: 0.4,
        fill: ds.fill !== undefined ? ds.fill : true,   // also "-1": fill down to the previous dataset (a band)
        pointRadius: ds.pointRadius ?? 4,
        pointHoverRadius: 6,
        borderWidth: ds.borderWidth ?? 2,
        borderDash: ds.dash || [],                       // e.g. [6, 4] for forecast values
        hidden: ds.hidden || false,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      onClick: clickHandler(opts),
      onHover: (event, elements) => { if (opts.onClickIndex) event.native.target.style.cursor = elements.length ? "pointer" : ""; },
      plugins: {
        legend: { display: false },
        htmlLegend: { display: opts.legend !== false, filter: item => !datasets[item.datasetIndex].noLegend },
        ...(opts.percent ? { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${percent(c.raw)}` } } } : {}),
      },
      spanGaps: false,
      scales: {
        x: { grid: { color: Theme.border }, ticks: { color: Theme.textMuted } },
        y: { grid: { color: Theme.border }, ticks: { color: Theme.textMuted, ...(opts.percent ? { callback: percent } : {}) } },
      },
    },
  });
}

/**
 * Create a bar chart (e.g., expenses by category).
 */
function makeBarChart(canvasId, labels, datasets, opts = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return registerChart(buildBarChart(ctx, labels, datasets, opts), () => buildBarChart(ctx, labels, datasets, opts));
}

function buildBarChart(ctx, labels, datasets, opts) {
  const valueAxis = opts.horizontal ? "x" : "y", labelAxis = opts.horizontal ? "y" : "x";
  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: datasets.map((ds, i) => ({
        type: ds.type,                                   // "line" mixes a line into the bars (e.g. the net)
        label: ds.label,
        data:  ds.data,
        // `colors`: one color per bar (theme tokens like "positive"); `palette`: the chart palette bar by bar;
        // `color`: one theme color for the dataset; otherwise one palette color per dataset
        backgroundColor: ds.colors ? ds.colors.map(c => themeColor(c, Theme.primary))
                       : ds.palette ? ds.data.map((_, j) => paletteOf(opts)[j % 8])
                       : ds.color ? hexAlpha(themeColor(ds.color, Theme.primary), ds.type === "line" ? 0.2 : 0.85)
                       : hexAlpha(paletteOf(opts)[i % 8], 0.85),
        borderColor: ds.color ? themeColor(ds.color, Theme.primary) : undefined,
        yAxisID: ds.axis === "right" ? "y1" : undefined,   // e.g. running totals next to monthly bars
        borderDash: ds.dash || [],
        borderWidth: ds.type === "line" ? 2 : 0,
        tension: 0.3,
        borderRadius: 4,
        hidden: ds.hidden || false,                      // drawn only after a click on its legend entry
        stack: ds.stack,                                 // bars with the same stack pile up (opts.stacked)
        order: ds.order ?? (ds.type === "line" ? 0 : 1), // lines over the bars
        pointRadius: ds.type === "line" ? (ds.pointRadius ?? 3) : undefined,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: labelAxis,
      onClick: clickHandler(opts),
      plugins: { legend: { display: false }, htmlLegend: { display: opts.legend ?? datasets.length > 1 } },
      scales: {
        [labelAxis]: { grid: { display: false }, stacked: opts.stacked || false },
        [valueAxis]: { grid: { color: Theme.border }, stacked: opts.stacked || false },
        ...(datasets.some(ds => ds.axis === "right")
          ? { y1: { position: "right", grid: { display: false }, ticks: { color: Theme.textMuted } } } : {}),
      },
    },
  });
}

/** `opts.onClickIndex(i)`: called with the index of the clicked bar or slice */
function clickHandler(opts) {
  if (!opts.onClickIndex) return undefined;
  // the nearest bar, slice or point (and its series): on a line chart the one under the pointer, not the first series
  return (event, elements, chart) => {
    const near = chart.getElementsAtEventForMode(event.native || event, "nearest", { intersect: false }, false);
    const hit = near[0] || elements[0];
    if (hit) opts.onClickIndex(hit.index, hit.datasetIndex);
  };
}

/**
 * Create a doughnut / pie chart (e.g., portfolio allocation).
 */
function makeDoughnutChart(canvasId, labels, data, opts = {}) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return registerChart(buildDoughnutChart(ctx, labels, data, opts), () => buildDoughnutChart(ctx, labels, data, opts));
}

function buildDoughnutChart(ctx, labels, data, opts) {
  return new Chart(ctx, {
    type: opts.pie ? "pie" : "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: paletteOf(opts), borderWidth: 2, borderColor: Theme.card, hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: opts.pie ? 0 : "65%",
      onClick: clickHandler(opts),
      plugins: {
        legend: { display: false },
        htmlLegend: { display: opts.legend !== false, list: opts.legendList },
        // a slice: its name and share, its amount in euro on the next line
        tooltip: { callbacks: { label: c => [`${c.label}: ${sliceShare(c.chart, c.dataIndex)}`, formatMoney(c.raw)] } },
      },
    },
  });
}

/** Convert hex color to rgba with alpha */
function hexAlpha(hex, alpha) {
  if (!/^#?[0-9a-f]{3}([0-9a-f]{3})?$/i.test(hex || "")) return hex;  // not a hex color: use as is
  hex = hex.replace("#", "");
  if (hex.length === 3) hex = hex.split("").map(c => c + c).join("");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
