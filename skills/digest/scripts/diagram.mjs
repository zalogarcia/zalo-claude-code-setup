#!/usr/bin/env node
// diagram.mjs: render an exact boxes-and-arrows diagram from a JSON spec to a phone-readable PNG.
// Every word is typeset by the browser from the spec, so the text is exact (no AI image text).
//
// Usage:
//   node diagram.mjs <spec.json> <out.png> [--html out.html] [--width 1080] [--scale 1]
//   (the HTML it renders from is kept as <out>.diagram.html unless --html names a path)
//
// Templates (spec.template): flow | sequence | compare | map. Spec shapes: ../templates/README.md
// The page lays out with CSS, then a small script draws the arrows from the real box positions
// and reports overlaps. Overlaps and em or en dashes in the spec fail the run.
// Exit codes: 0 rendered and clean, 1 rendered with layout warnings or failed, 2 bad spec or usage.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { renderToPng } from "./render.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const TEMPLATES = ["flow", "sequence", "compare", "map"];
const TONES = ["blue", "green", "yellow", "red", "grey", "purple"];

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
// Backticks in spec text become <code>: ids and file names read as exact names.
const md = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");
const tone = (t, d = "blue") => (TONES.includes(t) ? t : d);

export function validate(spec) {
  const errs = [];
  if (!spec || typeof spec !== "object") return ["spec is not a JSON object"];
  if (!TEMPLATES.includes(spec.template)) errs.push(`template must be one of ${TEMPLATES.join(", ")}`);
  if (!spec.title) errs.push("title is required");
  if ("width" in spec && !(typeof spec.width === "number" && Number.isFinite(spec.width) && spec.width >= 320 && spec.width <= 4000)) {
    errs.push("width must be a number from 320 to 4000 (pixels)");
  }
  const walk = (v, path) => {
    if (typeof v === "string" && /[\u2012-\u2015]/.test(v)) errs.push(`${path}: em or en dash (Zalo's rule): use a comma, colon or 'to'`);
    else if (Array.isArray(v)) v.forEach((x, i) => walk(x, `${path}[${i}]`));
    else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) walk(x, `${path}.${k}`);
  };
  walk(spec, "spec");
  const ids = new Set();
  const addId = (id, where) => {
    if (!id) errs.push(`${where}: id is required`);
    else if (ids.has(id)) errs.push(`${where}: duplicate id ${id}`);
    else ids.add(id);
  };
  if (spec.template === "flow") {
    if (!Array.isArray(spec.rows) || !spec.rows.length) errs.push("flow: rows must be a non-empty array of arrays of nodes");
    else spec.rows.forEach((row, r) => (Array.isArray(row) ? row : [row]).forEach((n, i) => addId(n?.id, `rows[${r}][${i}]`)));
  }
  if (spec.template === "map") {
    if (!Array.isArray(spec.zones) || !spec.zones.length) errs.push("map: zones must be a non-empty array");
    else spec.zones.forEach((z, zi) => (z.nodes || []).forEach((n, i) => addId(n?.id, `zones[${zi}].nodes[${i}]`)));
  }
  if (spec.template === "sequence") {
    if (!Array.isArray(spec.lanes) || spec.lanes.length < 2) errs.push("sequence: lanes needs 2 or more entries");
    else spec.lanes.forEach((l, i) => addId(l?.id, `lanes[${i}]`));
    if (spec.lanes?.length > 4) errs.push("sequence: at most 4 lanes fit a phone width");
    (spec.messages || []).forEach((m, i) => {
      for (const k of ["from", "to"]) if (!ids.has(m[k])) errs.push(`messages[${i}].${k}: unknown lane ${m[k]}`);
    });
    if (!spec.messages?.length) errs.push("sequence: messages must be a non-empty array");
  }
  if (spec.template === "compare") {
    for (const side of ["before", "after"]) if (!spec[side] || !Array.isArray(spec[side].items)) errs.push(`compare: ${side}.items is required`);
  }
  if (["flow", "map"].includes(spec.template)) {
    (spec.edges || []).forEach((e, i) => {
      for (const k of ["from", "to"]) if (!ids.has(e[k])) errs.push(`edges[${i}].${k}: unknown node ${e[k]}`);
    });
  }
  return errs;
}

function nodeHtml(n, num) {
  const kind = n.kind ? ` kind-${esc(n.kind)}` : "";
  const parts = [`<div class="node tone-${tone(n.tone, n.kind === "gap" ? "red" : "blue")}${kind}" data-id="${esc(n.id)}">`];
  parts.push(`<div class="head">${num ? `<span class="num">${num}</span>` : ""}<span class="label">${md(n.label)}</span></div>`);
  if (n.sub) parts.push(`<div class="sub">${md(n.sub)}</div>`);
  if (n.detail) parts.push(`<div class="detail">${md(n.detail)}</div>`);
  if (n.chips?.length) parts.push(chipsHtml(n.chips));
  if (n.branches?.length) {
    parts.push(`<div class="branches">`);
    for (const b of n.branches) parts.push(`<div class="branch tone-${tone(b.tone, "grey")}"><div class="when">${md(b.when)}</div>${b.then?.length ? chipsHtml(b.then) : ""}${b.note ? `<div class="bnote">${md(b.note)}</div>` : ""}</div>`);
    parts.push(`</div>`);
  }
  if (n.items?.length) parts.push(`<ul class="items">${n.items.map((i) => `<li>${md(i)}</li>`).join("")}</ul>`);
  parts.push(`</div>`);
  return parts.join("");
}

// Each arrow is bound to the chip after it, so a wrapped line starts with the arrow.
const chipsHtml = (chips) => `<div class="chips">${chips.map((c, i) => (i ? `<span class="link"><span class="sep">&rarr;</span><span class="chip">${md(c)}</span></span>` : `<span class="chip">${md(c)}</span>`)).join("")}</div>`;

function bodyFlow(spec) {
  let k = 0;
  const numbered = spec.numbered !== false;
  const rows = spec.rows.map((row) => (Array.isArray(row) ? row : [row]));
  const html = rows.map((row) => `<div class="row">${row.map((n) => nodeHtml(n, numbered && n.kind !== "note" ? ++k : 0)).join("")}</div>`).join("");
  let edges = spec.edges;
  if (!edges) {
    edges = [];
    for (let r = 1; r < rows.length; r++) for (const a of rows[r - 1]) for (const b of rows[r]) edges.push({ from: a.id, to: b.id });
  }
  return { html: `<div class="flow">${html}</div>`, edges };
}

function bodyMap(spec) {
  const html = spec.zones.map((z) => `<section class="zone tone-${tone(z.tone, "grey")}"><div class="zhead"><div class="zlabel">${md(z.label)}</div>${z.sub ? `<div class="zsub">${md(z.sub)}</div>` : ""}</div><div class="row">${(z.nodes || []).map((n) => nodeHtml(n, 0)).join("")}</div></section>`).join("");
  return { html: `<div class="map">${html}</div>`, edges: spec.edges || [] };
}

function bodySequence(spec) {
  const L = spec.lanes.length;
  const lanes = spec.lanes.map((l) => `<div class="lane tone-${tone(l.tone)}" data-id="${esc(l.id)}"><div class="label">${md(l.label)}</div>${l.sub ? `<div class="sub">${md(l.sub)}</div>` : ""}</div>`).join("");
  const idx = Object.fromEntries(spec.lanes.map((l, i) => [l.id, i]));
  const msgs = spec.messages.map((m, i) => {
    const a = idx[m.from], b = idx[m.to];
    const lo = Math.min(a, b), hi = Math.max(a, b);
    const self = a === b;
    const span = self ? `${a + 1} / ${a + 2}` : `${lo + 1} / ${hi + 2}`;
    return `<div class="msg${self ? " self" : ""} tone-${tone(m.tone, "grey")}${m.dashed ? " dashed" : ""}" style="grid-column:${span};grid-row:${i + 1}" data-from="${a}" data-to="${b}">
      <div class="mlabel"><span class="num">${i + 1}</span>${md(m.label)}</div>${m.detail ? `<div class="mdetail">${md(m.detail)}</div>` : ""}</div>`;
  }).join("");
  return { html: `<div class="seq" style="--lanes:${L}"><div class="lanes">${lanes}</div><div class="msgs">${msgs}</div></div>`, edges: [] };
}

function bodyCompare(spec) {
  const b = spec.before, a = spec.after;
  const n = Math.max(b.items.length, a.items.length);
  const labels = spec.rowLabels || [];
  let rows = "";
  for (let i = 0; i < n; i++) {
    if (labels[i]) rows += `<div class="rlabel">${md(labels[i])}</div>`;
    rows += `<div class="cell before">${b.items[i] != null ? md(b.items[i]) : ""}</div><div class="cell after">${a.items[i] != null ? md(a.items[i]) : ""}</div>`;
  }
  return {
    html: `<div class="compare"><div class="chead before tone-${tone(b.tone, "red")}"><div class="label">${md(b.title || "Before")}</div>${b.sub ? `<div class="sub">${md(b.sub)}</div>` : ""}</div><div class="chead after tone-${tone(a.tone, "green")}"><div class="label">${md(a.title || "After")}</div>${a.sub ? `<div class="sub">${md(a.sub)}</div>` : ""}</div>${rows}</div>${spec.verdict ? `<div class="verdict">${md(spec.verdict)}</div>` : ""}`,
    edges: [],
  };
}

export function buildHtml(spec, width = 1080) {
  width = Number(width) || 1080;
  const body = { flow: bodyFlow, map: bodyMap, sequence: bodySequence, compare: bodyCompare }[spec.template](spec);
  const css = readFileSync(join(HERE, "../templates/diagram.css"), "utf8");
  const js = readFileSync(join(HERE, "../templates/diagram.js"), "utf8");
  const theme = spec.theme === "light" ? "light" : "dark";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=${width}">
<title>${esc(spec.title)}</title><style>${css}</style></head>
<body class="theme-${theme} t-${spec.template}" style="--w:${width}px">
<main id="canvas">
<header><h1>${md(spec.title)}</h1>${spec.subtitle ? `<p class="subtitle">${md(spec.subtitle)}</p>` : ""}</header>
${body.html}
${spec.legend?.length ? `<div class="legend">${spec.legend.map((l) => `<span class="key tone-${tone(l.tone, "grey")}${l.dashed ? " dashed" : ""}"><i></i>${md(l.label)}</span>`).join("")}</div>` : ""}
${spec.footer ? `<footer>${md(spec.footer)}</footer>` : ""}
<svg id="wires" aria-hidden="true"></svg><div id="labels"></div>
</main>
<script>window.__digestReady = false; window.EDGES = ${JSON.stringify(body.edges).replace(/</g, "\\u003c")};</script>
<script>${js}</script>
</body></html>`;
}

function parseArgs(argv) {
  const pos = [];
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--html") o.html = argv[++i];
    else if (a === "--width") o.width = Number(argv[++i]);
    else if (a === "--scale") o.scale = Number(argv[++i]);
    else if (a.startsWith("--")) throw new Error(`unknown flag ${a}`);
    else pos.push(a);
  }
  if (pos.length !== 2) throw new Error("need <spec.json> <out.png>");
  return { spec: pos[0], out: pos[1], o };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  let args, spec;
  try {
    args = parseArgs(process.argv.slice(2));
    spec = JSON.parse(readFileSync(args.spec, "utf8"));
  } catch (e) {
    console.error(`diagram: ${e.message}\nusage: node diagram.mjs <spec.json> <out.png> [--html out.html] [--width 1080] [--scale 1]`);
    process.exit(2);
  }
  const errs = validate(spec);
  if (errs.length) {
    for (const e of errs) console.error(`diagram: spec error: ${e}`);
    process.exit(2);
  }
  const width = args.o.width || spec.width || 1080;
  const html = buildHtml(spec, width);
  // <name>.diagram.html, so it never overwrites a page (rung 3) that shares the base name.
  const htmlPath = args.o.html || args.out.replace(/\.png$/i, "") + ".diagram.html";
  writeFileSync(htmlPath, html);
  try {
    const r = await renderToPng(htmlPath, args.out, { width, scale: args.o.scale || 1, collect: "JSON.stringify(window.__digestWarnings || [])" });
    const warns = JSON.parse(r.collected || "[]");
    for (const e of r.jsErrors) console.error(`diagram: page error: ${e}`);
    for (const w of warns) console.error(`diagram: layout warning: ${w}`);
    console.log(`diagram: ${r.out} ${r.width}x${r.height} (${spec.template}), html ${htmlPath}${warns.length || r.jsErrors.length ? `, ${warns.length} warnings, ${r.jsErrors.length} page errors` : ", clean"}`);
    process.exit(warns.length || r.jsErrors.length ? 1 : 0);
  } catch (e) {
    console.error(`diagram: render failed: ${e.message}`);
    process.exit(1);
  }
}
