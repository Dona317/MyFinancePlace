/**
 * charts.js — Chart.js configuration helpers
 * Reads color values from CSS variables so charts always match the theme.
 */

const Theme = (() => {
  const style = getComputedStyle(document.documentElement);
  const get = (v) => style.getPropertyValue(v).trim();
  return {
    primary:   get("--clr-primary"),
    positive:  get("--clr-positive"),
    negative:  get("--clr-negative"),
    neutral:   get("--clr-neutral"),
    warning:   get("--clr-warning"),
    textMuted: get("--clr-text-muted"),
    border:    get("--clr-border"),
    chart: [
      get("--chart-1"), get("--chart-2"), get("--chart-3"),
      get("--chart-4"), get("--chart-5"), get("--chart-6"),
      get("--chart-7"), get("--chart-8"),
    ],
  };
})();

// Global Chart.js defaults
Chart.defaults.font.family   = getComputedStyle(document.documentElement).getPropertyValue("--font-body").trim();
Chart.defaults.font.size     = 12;
Chart.defaults.color         = Theme.textMuted;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 16;
Chart.defaults.plugins.tooltip.backgroundColor = "#1A2540";
Chart.defaults.plugins.tooltip.titleColor = "#FFFFFF";
Chart.defaults.plugins.tooltip.bodyColor  = "#C6D4EE";
Chart.defaults.plugins.tooltip.borderColor = "#243570";
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding    = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;

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
  return new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: datasets.map((ds, i) => ({
        label: ds.label,
        data:  ds.data,
        borderColor:     ds.color || Theme.chart[i % Theme.chart.length],
        backgroundColor: hexAlpha(ds.color || Theme.chart[i % Theme.chart.length], 0.08),
        tension: 0.4,
        fill: ds.fill !== undefined ? ds.fill : true,
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
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
  return new Chart(ctx, {
    type: opts.pie ? "pie" : "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: Theme.chart, borderWidth: 2, borderColor: "#fff", hoverOffset: 6 }],
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
  hex = hex.replace("#", "");
  if (hex.length === 3) hex = hex.split("").map(c => c + c).join("");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
