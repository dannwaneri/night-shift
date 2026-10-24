// Records the demo with headless Edge (DevTools screencast): the real-log replay, the notes page, the search replay.
// Writes demo/out/frames/*.jpg, frames.json, marks.json. Usage: node demo/record.mjs
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = new URL("..", import.meta.url).pathname.replace(/^\/(\w:)/, "$1");
const OUT = join(ROOT, "demo", "out"), port = 9339;
const page = (p) => pathToFileURL(join(ROOT, p)).href;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
try { await fetch(`http://127.0.0.1:${port}/json/version`); console.error(`Port ${port} busy.`); process.exit(1); } catch {}
rmSync(join(OUT, "frames"), { recursive: true, force: true }); mkdirSync(join(OUT, "frames"), { recursive: true });
const profile = mkdtempSync(join(tmpdir(), "edge-night-demo-"));
const edge = spawn("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", ["--headless=new", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "--disable-sync", "--no-first-run", "--disable-extensions", "--allow-file-access-from-files",
  "--window-size=1280,760", "about:blank"], { stdio: "ignore" });
let t; for (let i = 0; i < 80 && !t; i++) { await sleep(500); try { t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.type === "page"); } catch {} }
const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 0; const pend = new Map(); const frames = [];
const send = (method, params = {}) => new Promise((r) => { const n = ++id; pend.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id) { pend.get(m.id)?.(m); pend.delete(m.id); return; }
  if (m.method === "Page.screencastFrame") {
    const f = join(OUT, "frames", `${String(frames.length).padStart(5, "0")}.jpg`);
    writeFileSync(f, Buffer.from(m.params.data, "base64")); frames.push({ f, t: m.params.metadata.timestamp });
    send("Page.screencastFrameAck", { sessionId: m.params.sessionId });
  }
});
const ev = async (x) => (await send("Runtime.evaluate", { expression: x, awaitPromise: true, returnByValue: true })).result?.result?.value;
const waitFor = async (x, ms) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await ev(x)) return true; await sleep(300); } return false; };
await send("Page.enable"); await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 720, deviceScaleFactor: 1.5, mobile: false });
await send("Page.navigate", { url: "about:blank" }); await sleep(500);

const marks = {}; const t0 = Date.now() / 1000; const mark = (k) => { marks[k] = Date.now() / 1000 - t0; console.log("mark", k, marks[k].toFixed(1)); };
await send("Page.startScreencast", { format: "jpeg", quality: 88, everyNthFrame: 1 });
mark("start");
await send("Page.navigate", { url: page("demo/replay.html") + "#run" }); mark("run");
await waitFor("window.__done === true", 120e3); await sleep(2500);
await send("Page.navigate", { url: page("out/video_notes.html") }); await sleep(1500); mark("notes");
await sleep(3500);
const screenCard = `[...document.querySelectorAll("article")].find(a => /read from the screen/.test(a.textContent) && a.querySelector("img") && /OpenWA/.test(a.textContent)) || [...document.querySelectorAll("article")].find(a => a.querySelector("img"))`;
await ev(`(${screenCard})?.scrollIntoView({ behavior: "smooth", block: "center" })`); await sleep(1500); mark("screen"); await sleep(6000);
const fixCard = `[...document.querySelectorAll("article")].find(a => /Olamar/.test(a.textContent))`;
await ev(`(${fixCard})?.scrollIntoView({ behavior: "smooth", block: "center" })`); await sleep(1500); mark("fix"); await sleep(6000);
await send("Page.navigate", { url: page("demo/replay.html") + "#search" }); mark("search");
await waitFor("window.__done === true", 60e3); await sleep(5000);
mark("end"); await sleep(800);
await send("Page.stopScreencast"); await sleep(600);
writeFileSync(join(OUT, "frames.json"), JSON.stringify(frames.map((f) => ({ f: f.f, t: f.t - t0 }))));
writeFileSync(join(OUT, "marks.json"), JSON.stringify(marks, null, 1));
console.log("frames:", frames.length);
await send("Browser.close").catch(() => {}); ws.close(); edge.kill(); await sleep(1500); try { rmSync(profile, { recursive: true, force: true }); } catch {}
