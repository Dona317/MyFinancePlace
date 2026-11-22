/* The money flow (Sankey) drawn on the block's real size (22 Nov 2026, UI-33).

   The server writes the figures in a <script type="application/json"> inside the .sankey-box (services/sankey.py):
   the income categories, the expense ones, the middle. Here they are laid out on the box's width and height, and
   drawn again whenever the box changes size (Modifica, a narrower window, the side menu). The labels keep the size
   of the page's text; the width decides how much is shown:

   - medium (two columns): up to 7 a side, name and amount;
   - wide (three columns): up to 10 a side, name, amount and share of the total;
   - a low block shows as many as its height holds, the rest in «Altre»;
   - one column, or a phone: the flow runs top to bottom (income above, expenses below), a list with the figures
     under it. */
(function () {
  const SVG = "http://www.w3.org/2000/svg";
  const NODE = 12;            // thickness of a node
  const GAP = 10;             // between two nodes of a column
  const OTHER = "Altre";

  const el = (name, attrs = {}, text) => {
    const node = document.createElementNS(SVG, name);
    Object.entries(attrs).forEach(([k, v]) => v !== undefined && v !== null && node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const money = (value) => (window.formatMoney ? window.formatMoney(value) : value.toFixed(2));
  const colour = (node, index) => node.special ? "var(--clr-positive)" : `var(--chart-${index % 8 + 1})`;

  // the biggest `limit` categories of a side; the others (and an «Altre» already there) in one «Altre»; the special
  // line (savings) stays last
  function group(items, limit, other) {
    const plain = items.filter(i => !i.special && i.category !== null);
    const others = items.filter(i => !i.special && i.category === null);  // «Altre» from the server
    const special = items.filter(i => i.special);
    const kept = plain.slice(0, limit);
    const rest = plain.slice(limit).concat(others).reduce((sum, i) => sum + i.amount, 0);
    if (rest > 0) kept.push({ label: other || OTHER, amount: Math.round(rest * 100) / 100, category: null, special: false });
    return kept.concat(special);
  }

  // the scale (pixels per euro) that fits `items` in `room`, each at least `slot` tall (its label's lines)
  function fit(items, room, slot) {
    const total = items.reduce((s, i) => s + i.amount, 0) || 1;
    const free = room - GAP * (items.length - 1);
    let scale = free / total;
    for (let round = 0; round < 6; round++) {
      const small = items.filter(i => i.amount * scale < slot);
      const big = items.filter(i => i.amount * scale >= slot).reduce((s, i) => s + i.amount, 0);
      if (!big) break;
      scale = Math.max((free - small.length * slot) / big, 0.0001);
    }
    return scale;
  }

  function measure(svg, text, cls) {
    const probe = el("text", { class: cls, x: -9999, y: -9999 }, text);
    svg.appendChild(probe);
    const width = probe.getComputedTextLength();
    probe.remove();
    return width;
  }

  function link(box, node, kind, child) {
    if (!node.category || box.dataset.tx === undefined) return child;
    const url = new URL(box.dataset.tx, location.href);
    url.searchParams.set("category", node.category);
    url.searchParams.set("type", kind);
    url.searchParams.set("start", box.dataset.start);
    url.searchParams.set("end", box.dataset.end);
    const a = el("a", { href: url.pathname + url.search, class: "sankey-link" });
    a.appendChild(child);
    return a;
  }

  const band = (x0, y0, x1, y1, t) => {
    const m = (x0 + x1) / 2;
    return `M${x0},${y0} C${m},${y0} ${m},${y1} ${x1},${y1} L${x1},${y1 + t} C${m},${y1 + t} ${m},${y0 + t} ${x0},${y0 + t} Z`;
  };
  const bandDown = (x0, y0, x1, y1, t) => {  // the same, running top to bottom (phone)
    const m = (y0 + y1) / 2;
    return `M${x0},${y0} C${x0},${m} ${x1},${m} ${x1},${y1} L${x1 + t},${y1} C${x1 + t},${m} ${x0 + t},${m} ${x0 + t},${y0} Z`;
  };

  function draw(box) {
    const data = box._data;
    const width = Math.floor(box.clientWidth);
    if (!data || width < 50) return;
    const columns = width < 460 ? 1 : width < 820 ? 2 : 3;
    // a phone, or a block one column wide: top to bottom, the names in the list under it (side by side they would
    // be cut to a few letters)
    const down = columns === 1 || window.matchMedia("(max-width: 640px)").matches;
    const svg = el("svg", { class: "sankey", role: "img", "aria-label": box.dataset.label || "" });
    box.replaceChildren(svg);
    const legend = box.parentElement.querySelector(".sankey-legend");
    if (legend) legend.hidden = !down;
    if (down) return drawDown(box, svg, group(data.incomes, 4, data.other), group(data.expenses, 5, data.other), data, width);

    // the height: what the card's height leaves (a block made taller: Modifica → altezza), or one that suits the
    // width; worked out from the card's minimum, never from the drawing itself (it would grow at every redraw)
    const card = box.closest(".card"), body = box.parentElement;
    const tall = box.closest(".fc-widget[data-height]:not([data-height='0'])");
    const style = getComputedStyle(body);
    const given = card && tall ? (parseFloat(getComputedStyle(card).minHeight) || 0)
      - (card.querySelector(".card-header")?.offsetHeight || 0)
      - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - 2 : 0;
    const height = Math.round(given > 160 ? given : Math.min(Math.max(width * 0.62, 280), 560));
    const lineHeight = 17;
    const top = 26, bottom = 6, room = height - top - bottom;
    // as many categories as the height holds with their two lines (a low block: fewer, the rest in «Altre»)
    const fits = Math.max(Math.floor((room + GAP) / (2 * lineHeight + GAP)) - 1, 2);
    const limit = Math.min({ 2: 7, 3: 10 }[columns], fits);
    const left = group(data.incomes, limit, data.other), right = group(data.expenses, limit, data.other);
    const total = data.middle.amount || 1;
    const showAmount = true, showShare = columns === 3;
    const lines = 2;
    const slot = lines * lineHeight;
    const share = (n) => showShare ? ` · ${Math.round(n.amount / total * 100)}%` : "";
    const amountText = (n) => money(n.amount) + share(n);
    // room for the labels: the longest name or amount of each side (a narrow block cuts the names)
    const cap = width * 0.26;
    const sideRoom = (items) => Math.min(cap, Math.max(...items.map(n => Math.max(
      measure(svg, n.label, "sankey-label"), showAmount ? measure(svg, amountText(n), "sankey-amount") : 0))) + 12);
    const roomL = sideRoom(left), roomR = sideRoom(right);
    const scale = Math.min(fit(left, room, slot), fit(right, room, slot), room / total);
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    const xL = roomL, xR = width - roomR - NODE, xM = Math.round((xL + xR) / 2 - NODE / 2);
    const middleH = total * scale, middleY = top + (room - middleH) / 2;

    const column = (items, x) => {
      const tall = items.reduce((s, n) => s + Math.max(n.amount * scale, slot), 0) + GAP * (items.length - 1);
      let y = top + Math.max((room - tall) / 2, 0);
      return items.map((n, i) => {
        const h = Math.max(n.amount * scale, 1);
        const placed = { ...n, x, y, h, slotH: Math.max(h, slot), colour: colour(n, i) };
        y += placed.slotH + GAP;
        return placed;
      });
    };
    const nodesL = column(left, 0 + xL - NODE), nodesR = column(right, xR);
    nodesL.forEach(n => { n.x = xL - NODE; });

    const bands = el("g");
    let yIn = middleY, yOut = middleY;
    nodesL.forEach(n => {
      const t = n.amount * scale;
      const path = el("path", { d: band(n.x + NODE, n.y, xM, yIn, t), class: "sankey-band", style: `fill:${n.colour}` });
      path.appendChild(el("title", {}, `${n.label} → ${data.middle.label}: ${money(n.amount)}`));
      bands.appendChild(link(box, n, "income", path));
      yIn += t;
    });
    nodesR.forEach(n => {
      const t = n.amount * scale;
      const path = el("path", { d: band(xM + NODE, yOut, n.x, n.y, t), class: "sankey-band", style: `fill:${n.colour}` });
      path.appendChild(el("title", {}, `${data.middle.label} → ${n.label}: ${money(n.amount)}`));
      bands.appendChild(link(box, n, "expense", path));
      yOut += t;
    });
    svg.appendChild(bands);

    const cut = (text, cls, max) => {  // a name too long for its room ends with «…»
      if (measure(svg, text, cls) <= max) return text;
      let s = text;
      while (s.length > 2 && measure(svg, s + "…", cls) > max) s = s.slice(0, -1);
      return s + "…";
    };
    const label = (n, kind, right) => {
      const g = el("g");
      const rect = el("rect", { x: n.x, y: n.y, width: NODE, height: n.h, rx: 3, style: `fill:${n.colour}` });
      rect.appendChild(el("title", {}, `${n.label}: ${money(n.amount)}${share(n)}`));
      g.appendChild(rect);
      const x = right ? n.x + NODE + 8 : n.x - 8;
      const centre = n.y + n.h / 2;
      const text = el("text", { x, y: centre - (lines - 1) * lineHeight / 2, "text-anchor": right ? "start" : "end",
                                "dominant-baseline": "middle", class: "sankey-label" + (n.special ? " sankey-special" : "") });
      text.appendChild(el("tspan", {}, cut(n.label, "sankey-label", (right ? roomR : roomL) - 12)));
      if (showAmount) text.appendChild(el("tspan", { x, dy: lineHeight, class: "sankey-amount" }, amountText(n)));
      const title = el("title", {}, `${n.label}: ${money(n.amount)}${share(n)}`);
      text.appendChild(title);
      g.appendChild(text);
      svg.appendChild(link(box, n, kind, g));
    };
    nodesL.forEach(n => label(n, "income", false));
    nodesR.forEach(n => label(n, "expense", true));
    const mid = el("rect", { x: xM, y: middleY, width: NODE, height: Math.max(middleH, 1), rx: 3, style: "fill:var(--clr-primary)" });
    mid.appendChild(el("title", {}, `${data.middle.label}: ${money(data.middle.amount)}`));
    svg.appendChild(mid);
    const head = el("text", { x: xM + NODE / 2, y: middleY - 10, "text-anchor": "middle", class: "sankey-label" });
    head.appendChild(el("tspan", {}, data.middle.label));
    head.appendChild(el("tspan", { class: "sankey-amount", dx: 6 }, money(data.middle.amount)));
    svg.appendChild(head);
  }

  // a phone: income on top, the middle as a bar across, expenses at the bottom; the names in the list under it
  function drawDown(box, svg, top, bottom, data, width) {
    const total = data.middle.amount || 1;
    const height = 300, pad = 8, rowH = 14, midY = height / 2 - rowH / 2;
    const scaleFor = (items) => (width - 2 * pad - GAP * (items.length - 1)) / total;
    const scale = Math.min(scaleFor(top), scaleFor(bottom));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    const midW = total * scale, midX = (width - midW) / 2;
    const row = (items, y) => {
      const used = items.reduce((s, n) => s + n.amount * scale, 0) + GAP * (items.length - 1);
      let x = (width - used) / 2;
      return items.map((n, i) => { const p = { ...n, x, y, w: Math.max(n.amount * scale, 1), colour: colour(n, i) }; x += p.w + GAP; return p; });
    };
    const up = row(top, pad), down = row(bottom, height - pad - rowH);
    let xIn = midX, xOut = midX;
    up.forEach(n => {
      const t = n.amount * scale;
      svg.appendChild(link(box, n, "income", el("path", { d: bandDown(n.x, n.y + rowH, xIn, midY, t), class: "sankey-band", style: `fill:${n.colour}` })));
      xIn += t;
    });
    down.forEach(n => {
      const t = n.amount * scale;
      svg.appendChild(link(box, n, "expense", el("path", { d: bandDown(xOut, midY + rowH, n.x, n.y, t), class: "sankey-band", style: `fill:${n.colour}` })));
      xOut += t;
    });
    [...up.map(n => [n, "income"]), ...down.map(n => [n, "expense"])].forEach(([n, kind]) => {
      const rect = el("rect", { x: n.x, y: n.y, width: n.w, height: rowH, rx: 3, style: `fill:${n.colour}` });
      rect.appendChild(el("title", {}, `${n.label}: ${money(n.amount)}`));
      svg.appendChild(link(box, n, kind, rect));
    });
    svg.appendChild(el("rect", { x: midX, y: midY, width: Math.max(midW, 1), height: rowH, rx: 3, style: "fill:var(--clr-primary)" }));
    // the list: what each colour is, with its amount
    const legend = box.parentElement.querySelector(".sankey-legend");
    if (!legend) return;
    legend.replaceChildren();
    [[data.middle.label, null], ...up.map(n => [n, "income"]), ...down.map(n => [n, "expense"])].forEach(([n, kind]) => {
      const li = document.createElement("li");
      if (kind === null) {
        li.className = "sankey-legend-head";
        li.textContent = `${n} ${money(data.middle.amount)}`;
      } else {
        const dot = Object.assign(document.createElement("span"), { className: "sankey-dot" });
        dot.style.background = n.colour;
        li.append(dot, Object.assign(document.createElement("span"), { textContent: n.label, className: n.special ? "sankey-special-text" : "" }),
                  Object.assign(document.createElement("strong"), { textContent: money(n.amount) }));
        li.dataset.kind = kind;
      }
      legend.appendChild(li);
    });
  }

  function init(root = document) {
    root.querySelectorAll(".sankey-box").forEach(box => {
      if (box._observer) return;
      try { box._data = JSON.parse(box.querySelector("script[type='application/json']").textContent); } catch (e) { return; }
      let frame = 0;
      const redraw = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => draw(box)); };
      box._observer = new ResizeObserver(redraw);
      box._observer.observe(box);
      const card = box.closest(".card");
      if (card) box._observer.observe(card);  // a block made taller or shorter
      window.matchMedia("(max-width: 640px)").addEventListener("change", redraw);
      draw(box);
    });
  }
  window.initSankey = init;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => init());
  else init();
})();
