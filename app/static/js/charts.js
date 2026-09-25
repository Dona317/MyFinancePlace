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
    textMuted: get("--clr-text-muted"),
    border:    get("--clr-border"),
    card:      get("--clr-bg-card") || "#FFFFFF",
    chart: [
      get("--chart-1"), get("--chart-2"), get("--chart-3"),
      get("--chart-4"), get("--chart-5"), get("--chart-6"),
      get("--chart-7"), get("--chart-8"),
    ],
  });
  Chart.defaults.color = Theme.textMuted;
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
function makeLineChart(canvasId, labels, datasets) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;
  return registerChart(buildLineChart(ctx, labels, datasets), () => buildLineChart(ctx, labels, datasets));
}

function buildLineChart(ctx, labels, datasets) {
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: datasets.map((ds, i) => ({
        label: ds.label,
        data:  ds.data,
        borderColor:     themeColor(ds.color, Theme.chart[i % Theme.chart.length]),
        backgroundColor: hexAlpha(themeColor(ds.color, Theme.chart[i % Theme.chart.length]), ds.fillAlpha ?? 0.08),
        tension: 0.4,
        fill: ds.fill !== undefined ? ds.fill : true,   // also "-1": fill down to the previous dataset (a band)
        pointRadius: ds.pointRadius ?? 4,
        pointHoverRadius: 6,
        borderWidth: ds.borderWidth ?? 2,
        borderDash: ds.dash || [],                       // e.g. [6, 4] for forecast values
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { filter: item => !datasets[item.datasetIndex].noLegend } } },
      scales: {
        x: { grid: { color: Theme.border }, ticks: { color: Theme.textMuted } },
        y: { grid: { color: Theme.border }, ticks: { color: Theme.textMuted } },
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
  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: datasets.map((ds, i) => ({
        label: ds.label,
        data:  ds.data,
        backgroundColor: (ds.colors || Theme.chart.map(c => hexAlpha(c, 0.85)))[i % Theme.chart.length],
        borderRadius: 4,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: datasets.length > 1 } },
      scales: {
        x: { grid: { display: false }, stacked: opts.stacked || false },
        y: { grid: { color: Theme.border }, stacked: opts.stacked || false },
      },
    },
  });
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
      datasets: [{ data, backgroundColor: Theme.chart, borderWidth: 2, borderColor: Theme.card, hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: opts.pie ? 0 : "65%",
      plugins: { legend: { position: opts.legendPosition || "right" } },
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
