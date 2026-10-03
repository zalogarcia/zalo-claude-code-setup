#!/usr/bin/env node
// Tests for diagram.mjs, page-check.mjs and render.mjs.
// Run: node ~/.claude/skills/digest/scripts/visual.test.mjs   (about 20 s: it renders in Chrome)
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { validate, buildHtml } from "./diagram.mjs";
import { staticChecks } from "./page-check.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const EX = join(HERE, "../templates/examples");
const TMP = mkdtempSync(join(tmpdir(), "digest-visual-test-"));
let passed = 0, failed = 0;
const check = (name, cond, detail = "") => {
  if (cond) passed++;
  else { failed++; console.log(`FAIL ${name} ${detail}`); }
};
const run = (args) => spawnSync(process.execPath, args, { encoding: "utf8", timeout: 120000 });
const flow = (rows, extra = {}) => ({ template: "flow", title: "T", rows, ...extra });

// validate()
check("v01 good flow", validate(flow([[{ id: "a", label: "A" }], [{ id: "b", label: "B" }]])).length === 0);
check("v02 missing title", validate({ template: "flow", rows: [[{ id: "a" }]] }).some((e) => /title/.test(e)));
check("v03 unknown template", validate({ template: "pie", title: "T" }).some((e) => /template/.test(e)));
check("v04 em dash refused", validate(flow([[{ id: "a", label: "A — B" }]])).some((e) => /dash/.test(e)));
check("v05 en dash refused", validate(flow([[{ id: "a", label: "1–4" }]])).some((e) => /dash/.test(e)));
check("v06 duplicate id", validate(flow([[{ id: "a" }], [{ id: "a" }]])).some((e) => /duplicate/.test(e)));
check("v07 edge to unknown node", validate(flow([[{ id: "a" }]], { edges: [{ from: "a", to: "zz" }] })).some((e) => /unknown node zz/.test(e)));
check("v08 five lanes refused", validate({ template: "sequence", title: "T", lanes: [1, 2, 3, 4, 5].map((i) => ({ id: `l${i}` })), messages: [{ from: "l1", to: "l2" }] }).some((e) => /at most 4/.test(e)));
check("v09 message to unknown lane", validate({ template: "sequence", title: "T", lanes: [{ id: "a" }, { id: "b" }], messages: [{ from: "a", to: "c" }] }).some((e) => /unknown lane c/.test(e)));
check("v10 compare needs items", validate({ template: "compare", title: "T", before: {}, after: { items: [] } }).some((e) => /before.items/.test(e)));

// buildHtml() escapes spec text and turns backticks into code
const html = buildHtml(flow([[{ id: "a", label: "<img src=x onerror=alert(1)>", detail: "id `aaaa1111`" }]]));
check("b01 label escaped", html.includes("&lt;img src=x onerror=alert(1)&gt;") && !html.includes("<img src=x"));
check("b02 backticks become code", html.includes("<code>aaaa1111</code>"));
check("b03 edge JSON cannot close the script", !buildHtml(flow([[{ id: "a" }], [{ id: "b" }]], { edges: [{ from: "a", to: "b", label: "</script><b>x" }] })).includes("</script><b>x"));

// diagram.mjs renders the four examples clean
for (const t of ["flow", "sequence", "compare", "map"]) {
  const out = join(TMP, `${t}.png`);
  const r = run([join(HERE, "diagram.mjs"), join(EX, `${t}.json`), out]);
  check(`d-${t} renders clean`, r.status === 0 && existsSync(out) && /clean/.test(r.stdout), `${r.status} ${r.stdout}${r.stderr}`);
}
// a spec whose labelled edge must run down the side fails with a warning (exit 1)
const crowded = flow([[{ id: "a", label: "A" }, { id: "x", label: "X" }], [{ id: "m", label: "Middle box spans the row" }], [{ id: "b", label: "B" }, { id: "y", label: "Y" }]], {
  edges: [{ from: "a", to: "b", label: "skips a row" }],
});
writeFileSync(join(TMP, "crowded.json"), JSON.stringify(crowded));
let r = run([join(HERE, "diagram.mjs"), join(TMP, "crowded.json"), join(TMP, "crowded.png")]);
check("d-crowded warns and exits 1", r.status === 1 && /layout warning/.test(r.stderr), `${r.status} ${r.stderr}`);
// a dash in the spec is a spec error (exit 2), nothing is rendered
writeFileSync(join(TMP, "dash.json"), JSON.stringify(flow([[{ id: "a", label: "A — B" }]])));
r = run([join(HERE, "diagram.mjs"), join(TMP, "dash.json"), join(TMP, "dash.png")]);
check("d-dash exits 2", r.status === 2 && !existsSync(join(TMP, "dash.png")), `${r.status}`);
// the intermediate html never overwrites a page with the same base name
writeFileSync(join(TMP, "same.html"), "<p>page</p>");
r = run([join(HERE, "diagram.mjs"), join(EX, "compare.json"), join(TMP, "same.png")]);
check("d-no page clobber", r.status === 0 && existsSync(join(TMP, "same.diagram.html")) && spawnSync("cat", [join(TMP, "same.html")], { encoding: "utf8" }).stdout === "<p>page</p>");

// page-check static checks
const base = '<meta name="viewport" content="width=device-width, initial-scale=1">';
check("p01 clean page passes", staticChecks(base + "<p>hi</p>").length === 0);
check("p02 external script", staticChecks(base + '<script src="https://cdn.x/y.js"></script>').length === 1);
check("p03 external stylesheet", staticChecks(base + '<link rel="stylesheet" href="https://fonts.x/css">').length === 1);
check("p04 protocol-relative src", staticChecks(base + '<img src="//cdn.x/a.png">').length === 1);
check("p05 css url()", staticChecks(base + "<style>body{background:url(https://x/y.png)}</style>").length === 1);
check("p06 @import", staticChecks(base + '<style>@import "https://x/y.css";</style>').length === 1);
check("p07 plain link allowed", staticChecks(base + '<a href="https://blackumbrella.app/trial">trial</a>').length === 0);
check("p08 em dash in text", staticChecks(base + "<p>a — b</p>").some((f) => /dash/.test(f)));
check("p09 dash inside a script is fine", staticChecks(base + "<script>const s='—'</script>").length === 0);
check("p10 missing viewport", staticChecks("<p>hi</p>").some((f) => /viewport/.test(f)));
check("p11 network call", staticChecks(base + "<script>fetch('/x')</script>").some((f) => /network/.test(f)));
check("p12 iframe", staticChecks(base + '<iframe src="a.html"></iframe>').some((f) => /iframe/.test(f)));

// page-check CLI: the example page passes, a page with a dead toggle fails
r = run([join(HERE, "page-check.mjs"), join(EX, "page.html"), join(TMP, "page.png")]);
check("c01 example page passes", r.status === 0 && /PASS/.test(r.stdout) && existsSync(join(TMP, "page.png")), `${r.status} ${r.stdout}${r.stderr}`);
writeFileSync(join(TMP, "dead.html"), base + '<button aria-expanded="false">More</button><p>text</p>');
r = run([join(HERE, "page-check.mjs"), join(TMP, "dead.html"), join(TMP, "dead.png")]);
check("c02 dead toggle fails", r.status === 1 && /did not open on tap/.test(r.stderr), `${r.status} ${r.stderr}`);
writeFileSync(join(TMP, "err.html"), base + "<script>throw new Error('boom')</script>");
r = run([join(HERE, "page-check.mjs"), join(TMP, "err.html"), join(TMP, "err.png")]);
check("c03 page error fails", r.status === 1 && /boom/.test(r.stderr), `${r.status} ${r.stderr}`);
r = run([join(HERE, "page-check.mjs")]);
check("c04 no args exits 2", r.status === 2);

// render.mjs: phone mode size and bad usage
r = run([join(HERE, "render.mjs"), join(EX, "page.html"), join(TMP, "phone.png"), "--width", "390", "--scale", "3", "--height", "844", "--mobile"]);
check("r01 phone shot is 1170x2532", r.status === 0 && /1170x2532/.test(r.stdout), `${r.status} ${r.stdout}${r.stderr}`);
r = run([join(HERE, "render.mjs"), join(EX, "page.html")]);
check("r02 missing out exits 2", r.status === 2);
r = run([join(HERE, "render.mjs"), join(EX, "page.html"), join(TMP, "x.png"), "--width", "0"]);
check("r03 bad width exits 2", r.status === 2);

// QA round 1 regressions
const twoByTwo = flow([[{ id: "a", label: "A" }, { id: "b", label: "B" }], [{ id: "c", label: "C" }, { id: "d", label: "D" }]]);
writeFileSync(join(TMP, "2x2.json"), JSON.stringify(twoByTwo));
r = run([join(HERE, "diagram.mjs"), join(TMP, "2x2.json"), join(TMP, "2x2.png")]);
check("q01 2x2 default edges render clean", r.status === 0, `${r.status} ${r.stderr}`);
writeFileSync(join(TMP, "w.json"), JSON.stringify({ ...flow([[{ id: "a", label: "A" }]]), width: '1080px" onload="alert(1)' }));
r = run([join(HERE, "diagram.mjs"), join(TMP, "w.json"), join(TMP, "w.png")]);
check("q02 string width is a spec error", r.status === 2 && /width must be a number/.test(r.stderr), `${r.status} ${r.stderr}`);
writeFileSync(join(TMP, "dopen.html"), base + "<details open><summary>A</summary>a</details><details><summary>B</summary>b</details>");
r = run([join(HERE, "page-check.mjs"), join(TMP, "dopen.html"), join(TMP, "dopen.png")]);
check("q03 details open passes", r.status === 0 && /2 of 2 sections/.test(r.stdout), `${r.status} ${r.stdout}${r.stderr}`);
const bypasses = [
  '<script type="module">import c from "https://esm.sh/canvas-confetti"</script>',
  '<script>import("https://x.y/z.js")</script>',
  '<svg><image href="https://x.y/a.png"/></svg>',
  '<video poster="https://x.y/p.png"></video>',
  '<form action="https://x.y/post"></form>',
  '<meta http-equiv="refresh" content="0;url=https://x.y">',
  "<script>new EventSource('/s')</script>",
  "<script>new Image().src = 'https://x.y/t.gif'</script>",
];
bypasses.forEach((b, i) => check(`q04.${i} bypass caught`, staticChecks(base + b).length >= 1, b));
check("q05a reversed viewport attrs ok", staticChecks('<meta content="width=device-width, initial-scale=1" name="viewport"><p>x</p>').length === 0);
check("q05b unquoted viewport ok", staticChecks("<meta name=viewport content=width=device-width><p>x</p>").length === 0);
writeFileSync(join(TMP, "net.html"), base + "<p>x</p><script>var i=document.createElement('img'); i.src=['http:','','127.0.0.1:9','x.png'].join('/'); document.body.appendChild(i);</script>");
r = run([join(HERE, "page-check.mjs"), join(TMP, "net.html"), join(TMP, "net.png")]);
check("q06 runtime network request caught", r.status === 1 && /made a network request: http:\/\/127\.0\.0\.1:9/.test(r.stderr), `${r.status} ${r.stderr}`);
writeFileSync(join(TMP, "busy.html"), base + "<p>x</p><script>while(true){}</script>");
const profilesBefore = spawnSync("sh", ["-c", "ls -d \"$TMPDIR\"digest-render-* 2>/dev/null | wc -l"], { encoding: "utf8" }).stdout.trim();
r = run([join(HERE, "render.mjs"), join(TMP, "busy.html"), join(TMP, "busy.png"), "--timeout-ms", "4000"]);
const live = spawnSync("sh", ["-c", "pgrep -f digest-render- | wc -l"], { encoding: "utf8" }).stdout.trim();
const profilesAfter = spawnSync("sh", ["-c", "ls -d \"$TMPDIR\"digest-render-* 2>/dev/null | wc -l"], { encoding: "utf8" }).stdout.trim();
check("q07 hung page times out and leaves nothing", r.status === 1 && /timed out/.test(r.stderr) && live === "0" && profilesAfter === profilesBefore, `${r.status} live=${live} profiles ${profilesBefore}->${profilesAfter}`);

// QA round 2 regressions
writeFileSync(join(TMP, "sib.png"), "x");
writeFileSync(join(TMP, "rel.html"), base + '<link rel="stylesheet" href="kit.css"><img src="sib.png"><script src="kit.js"></script>');
check("q08 sibling-file references fail statically", staticChecks(base + '<img src="sib.png"><link rel="stylesheet" href="kit.css"><script src="kit.js"></script>').filter((f) => /points at a file outside the page/.test(f)).length === 3);
r = run([join(HERE, "page-check.mjs"), join(TMP, "rel.html"), join(TMP, "rel.png")]);
check("q09 sibling-file page fails the gate", r.status === 1 && /points at a file outside the page: sib\.png/.test(r.stderr), `${r.status} ${r.stderr}`);
check("q10 fetch( in prose passes", staticChecks(base + "<p>The worker calls <code>fetch(url)</code> once.</p>").length === 0);
check("q11 fetch( in a script fails", staticChecks(base + "<script>fetch('/x')</script>").length === 1);
check("q12 poster after a data src is caught", staticChecks(base + '<video src="data:video/mp4;base64,AA" poster="http://127.0.0.1:9/p.png"></video>').length === 1);
check("q13 css url to a sibling fails", staticChecks(base + "<style>body{background:url(bg.png)}</style>").length === 1);
check("q14 svg url(#id) is fine", staticChecks(base + '<svg><rect fill="url(#g)"/></svg><style>.a{fill:url(#g)}</style>').length === 0);

// QA round 3 regressions
const px = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";
check("q15 srcset of data URIs passes", staticChecks(base + `<img src="data:image/png;base64,${px}" srcset="data:image/png;base64,${px} 1x, data:image/png;base64,${px} 2x">`).length === 0);
check("q16 new URL(location.href) in a script passes", staticChecks(base + "<script>var u = new URL(location.href); var o = URL.createObjectURL(new Blob([]));</script>").length === 0);
check("q17 url( in prose or a code sample passes", staticChecks(base + "<p>Set <code>background: url(hero.png)</code> in the CSS.</p>").length === 0);
check("q18 url( in a style attribute to a sibling fails", staticChecks(base + '<div style="background:url(hero.png)">x</div>').length === 1);

check("q19 a commented-out img is ignored", staticChecks(base + '<!-- <img src="old.png"> --><p>x</p>').length === 0);

rmSync(TMP, { recursive: true, force: true });
console.log(`${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
