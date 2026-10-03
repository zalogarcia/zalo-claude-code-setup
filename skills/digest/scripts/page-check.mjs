#!/usr/bin/env node
// page-check.mjs: gate a rung 3 HTML page before it goes to Zalo, then take its phone screenshot.
//
// Usage:
//   node page-check.mjs <page.html> [shot.png] [--full]
//
// Checks (each failure is printed; any failure means exit 1):
//   self-contained   no script, link, img, image, source, video, audio, object, use, form or
//                    input that points at a web address OR at a sibling file (data: and #ids only),
//                    no CSS url() or @import outside the page, and no <iframe> at all.
//                    Plain <a href> links are allowed: they are navigation.
//   phone viewport   a <meta name="viewport" content="width=device-width ..."> tag
//   no dashes        no em or en dash in the visible text (Zalo's rule)
//   size             under 2 MB (it travels as a Telegram document)
//   runs clean       renders in headless Chrome at 390 px, scale 3, touch on, with no page errors
//   taps work        every [aria-expanded] control and every <details> opens when tapped
//   no network       on load and on tap, the page requests nothing but itself and data: URLs
// The screenshot is the first phone screen (390x844 at 3x); --full captures the whole page.
// Exit codes: 0 pass, 1 a check failed, 2 bad usage or missing file.
import { readFileSync, statSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
import { renderToPng } from "./render.mjs";

export function staticChecks(html) {
  const fails = [];
  html = html.replace(/<!--[\s\S]*?-->/g, " "); // a commented-out tag is not part of the page
  // The page travels alone as a Telegram document, so anything it points at must be inside it:
  // a web address AND a sibling file both break (QA round 2: <img src="diagram.png"> passed).
  const LOCAL_OK = /^\s*(data:|blob:|#|about:blank\s*$)/i;
  const TAGS = /<(script|link|img|image|iframe|source|video|audio|embed|object|use|form|input|track)\b([^>]*)>/gi;
  const ATTR = /(?:^|\s)(src|href|xlink:href|data|srcset|imagesrcset|poster|action|formaction)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/gi;
  for (const t of html.matchAll(TAGS)) {
    const tag = t[1].toLowerCase();
    for (const a of t[2].matchAll(ATTR)) {
      const val = (a[3] ?? a[4] ?? a[5] ?? "").trim();
      if (!val) continue;
      // srcset candidates are separated by a comma AND whitespace; a data URI has a bare comma inside.
      const parts = /srcset$/i.test(a[1]) ? val.split(/,\s+/).map((v) => v.trim().split(/\s+/)[0]) : [val];
      for (const v of parts) {
        if (!v || LOCAL_OK.test(v)) continue;
        fails.push(/^(https?:)?\/\//i.test(v)
          ? `external ${tag} ${a[1]}: ${v}`
          : `${tag} ${a[1]} points at a file outside the page: ${v} (inline it with scripts/inline-assets.py, or as a data: URI)`);
      }
    }
  }
  if (/<iframe\b/i.test(html)) fails.push("iframe present: a digest page embeds nothing");
  // CSS is checked where CSS lives (style blocks and style attributes), so a script's
  // new URL(...) or a code sample that mentions url(x) is not mistaken for a stylesheet.
  const css = [...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)].map((m) => m[1])
    .concat([...html.matchAll(/\sstyle\s*=\s*("([^"]*)"|'([^']*)')/gi)].map((m) => m[2] ?? m[3]))
    .join("\n");
  for (const m of css.matchAll(/(?<![\w.-])url\(\s*['"]?(?!data:|#|['"]?\))([^'")]+)/g)) fails.push(`CSS url() points outside the page: ${m[1].trim()}`);
  for (const m of css.matchAll(/@import\s+(?:url\()?\s*['"]?([^'")\s;]+)/gi)) fails.push(`CSS @import: ${m[1]}`);
  // Network calls are looked for in script code only (script bodies and on* handlers), so a page
  // that shows `fetch(url)` in a code sample still passes; the runtime request log is the real proof.
  const code = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1])
    .concat([...html.matchAll(/\son[a-z]+\s*=\s*("([^"]*)"|'([^']*)')/gi)].map((m) => m[2] ?? m[3]))
    .join("\n");
  if (/\bfetch\s*\(|XMLHttpRequest|new\s+WebSocket|new\s+EventSource|navigator\.sendBeacon|\bimport\s*\(|\bimport\b[^;\n]*?\bfrom\s*["']|\.src\s*=\s*["'`]\s*(https?:)?\/\//.test(code)) {
    fails.push("network call or import in a script (fetch, XHR, WebSocket, EventSource, beacon, import, .src)");
  }
  if (/<meta\b[^>]*http-equiv\s*=\s*["']?refresh/i.test(html)) fails.push("meta refresh: a digest page never redirects");
  const metas = html.match(/<meta\b[^>]*>/gi) || [];
  const viewport = metas.some((m) => /\bname\s*=\s*["']?viewport\b/i.test(m) && /\bcontent\s*=\s*["']?[^>]*width\s*=\s*device-width/i.test(m));
  if (!viewport) fails.push("no phone viewport meta (width=device-width)");
  const visible = html
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&mdash;|&#8212;|&#x2014;/gi, "—")
    .replace(/&ndash;|&#8211;|&#x2013;/gi, "–");
  const dashes = (visible.match(/[‒-―]/g) || []).length;
  if (dashes) fails.push(`${dashes} em or en dashes in the visible text`);
  return fails;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const full = args.includes("--full");
  const pos = args.filter((a) => !a.startsWith("--"));
  const bad = args.filter((a) => a.startsWith("--") && a !== "--full");
  if (!pos.length || pos.length > 2 || bad.length) {
    console.error("usage: node page-check.mjs <page.html> [shot.png] [--full]");
    process.exit(2);
  }
  const [page, shot = page.replace(/\.html?$/i, "") + ".phone.png"] = pos;
  let html, size;
  try {
    html = readFileSync(page, "utf8");
    size = statSync(page).size;
  } catch (e) {
    console.error(`page-check: cannot read ${page}: ${e.message}`);
    process.exit(2);
  }
  const fails = staticChecks(html);
  if (size > 2 * 1024 * 1024) fails.push(`file is ${(size / 1048576).toFixed(1)} MB (limit 2 MB)`);
  let shotInfo = "no screenshot";
  try {
    const r = await renderToPng(page, shot, { width: 390, scale: 3, mobile: true, height: full ? undefined : 844 });
    for (const e of r.jsErrors) fails.push(`page error: ${e}`);
    shotInfo = `${shot} ${r.width}x${r.height}${r.clipped ? " (clipped)" : ""}`;
  } catch (e) {
    fails.push(`render failed: ${e.message}`);
  }
  // Tap test: every control that declares aria-expanded must open when tapped, and every
  // <details> must open. Runs in its own render so the screenshot shows the page as it loads.
  let tapInfo = "no tap controls";
  try {
    const tap = await renderToPng(page, shot.replace(/\.png$/i, "") + ".tap-test.png", {
      width: 390, scale: 1, mobile: true, height: 844, trackRequests: true,
      collect: `(() => {
        const ctl = Array.from(document.querySelectorAll('[aria-expanded]'));
        let ok = 0;
        for (const el of ctl) {
          if (el.getAttribute('aria-expanded') === 'true') el.click();
          el.click();
          if (el.getAttribute('aria-expanded') === 'true') ok++;
        }
        const det = Array.from(document.querySelectorAll('details'));
        let dok = 0;
        for (const d of det) {
          const sum = d.querySelector('summary');
          if (d.open) sum?.click();
          sum?.click();
          if (d.open) dok++;
        }
        return JSON.stringify({ ctl: ctl.length, ok, det: det.length, dok });
      })()`,
    });
    const t = JSON.parse(tap.collected || "{}");
    if (t.ok < t.ctl) fails.push(`${t.ctl - t.ok} of ${t.ctl} aria-expanded controls did not open on tap`);
    if (t.dok < t.det) fails.push(`${t.det - t.dok} of ${t.det} <details> sections did not open on tap`);
    for (const e of tap.jsErrors) fails.push(`page error during the tap test: ${e}`);
    // Runtime proof of self-containment: every request the page made, on load and on tap.
    const self = pathToFileURL(resolve(page)).href;
    const remote = (tap.requests || []).filter((u) => u.split("#")[0] !== self && !/^(data|blob|about):/i.test(u));
    for (const u of [...new Set(remote)]) fails.push(`the page made a network request: ${u}`);
    tapInfo = `${t.ok} of ${t.ctl} tap controls and ${t.dok} of ${t.det} sections open`;
    try { (await import("node:fs")).rmSync(shot.replace(/\.png$/i, "") + ".tap-test.png", { force: true }); } catch {}
  } catch (e) {
    fails.push(`tap test failed: ${e.message}`);
  }
  for (const f of fails) console.error(`page-check: FAIL ${f}`);
  console.log(`page-check: ${fails.length ? `${fails.length} failures` : "PASS"} ${page} (${(size / 1024).toFixed(0)} KB), ${tapInfo}, screenshot ${shotInfo}`);
  process.exit(fails.length ? 1 : 0);
}
