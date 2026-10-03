#!/usr/bin/env node
// render.mjs: screenshot a local HTML or SVG file to PNG with the Chrome already on this Mac.
// Zero dependencies: it drives Chrome over the DevTools protocol with Node's built-in WebSocket.
//
// Usage:
//   node render.mjs <in.html|in.svg> <out.png> [--width 1080] [--scale 1]
//                   [--height N]         fixed viewport height (a phone screen); default: full page
//                   [--mobile]           emulate a touch phone (use with --width 390 --scale 3)
//                   [--fail-on-js-error] exit 1 when the page throws or logs a console error
//                   [--timeout-ms N]     give up after N ms (default 75000); Chrome and its profile are always removed
//
// The page may set `window.__digestReady = true` when its own layout script is done
// (diagram.mjs does, after it draws the arrows); render waits up to 8 s for it.
// Chrome: $CHROME_PATH, else Google Chrome.app, else the newest Playwright headless shell.
// Exit codes: 0 rendered, 1 page error (with --fail-on-js-error) or render failure, 2 bad usage.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const MAX_PX = 16000; // Chrome cannot capture a surface much taller than 16384 device px

export function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  if (existsSync(mac)) return mac;
  const cache = join(homedir(), "Library/Caches/ms-playwright");
  if (existsSync(cache)) {
    const shells = readdirSync(cache).filter((d) => d.startsWith("chromium_headless_shell-")).sort().reverse();
    for (const d of shells) {
      for (const sub of ["chrome-mac-arm64/headless_shell", "chrome-mac/headless_shell", "chrome-headless-shell-mac-arm64/chrome-headless-shell"]) {
        const p = join(cache, d, sub);
        if (existsSync(p)) return p;
      }
    }
  }
  return null;
}

// Every Chrome this module starts is tracked, so a timeout, a crash or process.exit still kills
// its whole process tree and removes its temp profile (QA 2026-10-02: 61 leaked profiles).
const LIVE = new Set();
function killTree(proc) {
  try { process.kill(-proc.pid, "SIGKILL"); } catch { try { proc.kill("SIGKILL"); } catch {} }
}
function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}
function groupAlive(pid) {
  try { process.kill(-pid, 0); return true; } catch (e) { return e.code === "EPERM"; }
}
// A dying Chrome can still land a file in its profile, and rmSync's retries do not re-scan,
// so remove in a few fresh passes (QA round 2: 1 leak in 17 signals during startup).
function removeProfile(profile) {
  for (let i = 0; i < 4 && existsSync(profile); i++) {
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 50 }); } catch {}
    if (existsSync(profile)) sleepSync(150);
  }
}
process.on("exit", () => {
  for (const e of LIVE) {
    killTree(e.proc);
    const t0 = Date.now();
    // Inside this hook node cannot reap Chrome, so its zombie keeps the group "alive":
    // wait briefly for the helpers, then let removeProfile's passes do the rest.
    while (groupAlive(e.proc.pid) && Date.now() - t0 < 300) sleepSync(25);
    removeProfile(e.profile);
  }
});
// A signal skips "exit" hooks by default; route it through process.exit so the cleanup runs.
for (const [sig, code] of [["SIGTERM", 143], ["SIGINT", 130], ["SIGHUP", 129]]) {
  process.on(sig, () => process.exit(code));
}

function launch(chrome) {
  const profile = mkdtempSync(join(tmpdir(), "digest-render-"));
  const proc = spawn(chrome, [
    "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--disable-extensions",
    "--hide-scrollbars", "--disable-gpu", "--allow-file-access-from-files", "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"], detached: true }); // own process group: one kill ends the tree
  const ws = new Promise((res, rej) => {
    let buf = "";
    const t = setTimeout(() => rej(new Error("Chrome did not print a DevTools URL in 20 s")), 20000);
    proc.stderr.on("data", (d) => {
      buf += d.toString();
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(t); res(m[1]); }
    });
    proc.on("exit", (code) => { clearTimeout(t); rej(new Error(`Chrome exited early (code ${code})`)); });
  });
  const entry = { proc, profile, ws, client: null };
  LIVE.add(entry);
  return entry;
}

async function shutdown(entry) {
  try { await Promise.race([entry.client?.send("Browser.close"), new Promise((r) => setTimeout(r, 1500))]); } catch {}
  entry.client?.close();
  const exited = new Promise((r) => {
    if (entry.proc.exitCode !== null || entry.proc.signalCode) return r();
    entry.proc.once("exit", r);
    setTimeout(r, 3000);
  });
  killTree(entry.proc);
  await exited; // Chrome writes to its profile until it is gone; remove it only after that
  for (const t0 = Date.now(); groupAlive(entry.proc.pid) && Date.now() - t0 < 3000; ) {
    await new Promise((r) => setTimeout(r, 25));
  }
  removeProfile(entry.profile);
  LIVE.delete(entry);
}

function cdp(url) {
  const sock = new WebSocket(url);
  let next = 1;
  const pending = new Map();
  const listeners = [];
  sock.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(`${msg.error.message} ${msg.error.data || ""}`)) : res(msg.result);
    } else if (msg.method) {
      for (const l of listeners) l(msg);
    }
  };
  const open = new Promise((res, rej) => { sock.onopen = res; sock.onerror = () => rej(new Error("DevTools socket error")); });
  // If Chrome dies, fail every pending call now instead of waiting for the render timeout.
  let onClosed;
  const closed = new Promise((_, rej) => { onClosed = rej; });
  closed.catch(() => {});
  sock.onclose = () => {
    const err = new Error("DevTools connection closed (Chrome exited)");
    for (const { rej } of pending.values()) rej(err);
    pending.clear();
    onClosed(err);
  };
  return {
    open,
    closed,
    send(method, params = {}, sessionId) {
      if (sock.readyState > 1) return Promise.reject(new Error("DevTools connection closed (Chrome exited)"));
      const id = next++;
      const body = { id, method, params };
      if (sessionId) body.sessionId = sessionId;
      sock.send(JSON.stringify(body));
      return new Promise((res, rej) => pending.set(id, { res, rej }));
    },
    on(fn) { listeners.push(fn); },
    close() { try { sock.close(); } catch {} },
  };
}

export async function renderToPng(input, out, opts = {}) {
  const chrome = findChrome();
  if (!chrome) throw new Error("no Chrome found: set CHROME_PATH");
  const entry = launch(chrome);
  const ms = opts.timeoutMs || 75000;
  let timer;
  try {
    return await Promise.race([
      doRender(entry, input, out, opts),
      new Promise((_, rej) => { timer = setTimeout(() => rej(new Error(`render timed out after ${ms / 1000} s (a page script may hang)`)), ms); }),
    ]);
  } finally {
    clearTimeout(timer);
    await shutdown(entry);
  }
}

async function doRender(entry, input, out, opts) {
  const width = opts.width || 1080;
  const scale = opts.scale || 1;
  const jsErrors = [];
  const requests = [];
  const client = cdp(await entry.ws);
  entry.client = client;
  await client.open;
  const { targetId } = await client.send("Target.createTarget", { url: "about:blank" });
  const { sessionId: s } = await client.send("Target.attachToTarget", { targetId, flatten: true });
  client.on((m) => {
    if (m.sessionId !== s) return;
    if (m.method === "Runtime.exceptionThrown") jsErrors.push(m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || "exception");
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") jsErrors.push((m.params.args || []).map((a) => a.value ?? a.description ?? "").join(" "));
    if (m.method === "Network.requestWillBeSent") requests.push(m.params.request?.url || "");
  });
  await client.send("Page.enable", {}, s);
  await client.send("Runtime.enable", {}, s);
  if (opts.trackRequests) await client.send("Network.enable", {}, s);
  const viewH = opts.height || 900;
  await client.send("Emulation.setDeviceMetricsOverride", { width, height: viewH, deviceScaleFactor: scale, mobile: !!opts.mobile }, s);
  if (opts.mobile) await client.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 }, s);
  const loaded = new Promise((res) => client.on((m) => { if (m.sessionId === s && m.method === "Page.loadEventFired") res(); }));
  await client.send("Page.navigate", { url: pathToFileURL(resolve(input)).href }, s);
  await Promise.race([loaded, client.closed, new Promise((r) => setTimeout(r, 15000))]);
  await client.send("Runtime.evaluate", {
    expression: `(async () => { await document.fonts.ready; const t0 = Date.now();
      while (window.__digestReady === false && Date.now() - t0 < 8000) await new Promise(r => setTimeout(r, 50));
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return true; })()`,
    awaitPromise: true,
  }, s);
  let height = viewH;
  let clipped = false;
  if (!opts.height) {
    const r = await client.send("Runtime.evaluate", { expression: "Math.ceil(Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0))", returnByValue: true }, s);
    height = Math.max(1, r.result.value);
    if (height * scale > MAX_PX) { height = Math.floor(MAX_PX / scale); clipped = true; }
    await client.send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile: !!opts.mobile }, s);
    await client.send("Runtime.evaluate", { expression: "new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))", awaitPromise: true }, s);
  }
  let collected;
  if (opts.collect) {
    const c = await client.send("Runtime.evaluate", { expression: opts.collect, returnByValue: true, awaitPromise: true }, s);
    collected = c.result.value;
    if (opts.trackRequests) await new Promise((r) => setTimeout(r, 300)); // let requests the taps caused show up
  }
  const shot = await client.send("Page.captureScreenshot", { format: "png", fromSurface: true }, s);
  writeFileSync(out, Buffer.from(shot.data, "base64"));
  return { out, width: width * scale, height: height * scale, clipped, jsErrors, collected, requests };
}

function parseArgs(argv) {
  const pos = [];
  const o = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--width") o.width = Number(argv[++i]);
    else if (a === "--scale") o.scale = Number(argv[++i]);
    else if (a === "--height") o.height = Number(argv[++i]);
    else if (a === "--mobile") o.mobile = true;
    else if (a === "--fail-on-js-error") o.failOnJsError = true;
    else if (a === "--timeout-ms") o.timeoutMs = Number(argv[++i]);
    else if (a.startsWith("--")) throw new Error(`unknown flag ${a}`);
    else pos.push(a);
  }
  if (pos.length !== 2) throw new Error("need <in> <out.png>");
  for (const k of ["width", "scale", "height", "timeoutMs"]) if (k in o && !(o[k] > 0)) throw new Error(`--${k} must be a positive number`);
  return { input: pos[0], out: pos[1], o };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  let args;
  try { args = parseArgs(process.argv.slice(2)); } catch (e) {
    console.error(`render: ${e.message}\nusage: node render.mjs <in.html|svg> <out.png> [--width 1080] [--scale 1] [--height N] [--mobile] [--fail-on-js-error]`);
    process.exit(2);
  }
  if (!existsSync(args.input)) { console.error(`render: missing input ${args.input}`); process.exit(2); }
  // Last resort: process.exit runs the exit hook above, which kills Chrome and removes the profile.
  const lastResort = Math.max((args.o.timeoutMs || 75000) + 15000, 90000);
  const killer = setTimeout(() => { console.error(`render: timed out after ${lastResort / 1000} s`); process.exit(1); }, lastResort);
  try {
    const r = await renderToPng(args.input, args.out, args.o);
    clearTimeout(killer);
    for (const e of r.jsErrors) console.error(`render: page error: ${e}`);
    console.log(`render: ${r.out} ${r.width}x${r.height}${r.clipped ? " (clipped at the 16000 px limit)" : ""}${r.jsErrors.length ? `, ${r.jsErrors.length} page errors` : ""}`);
    process.exit(args.o.failOnJsError && r.jsErrors.length ? 1 : 0);
  } catch (e) {
    clearTimeout(killer);
    console.error(`render: failed: ${e.message}`);
    process.exit(1);
  }
}
