#!/usr/bin/env node
/**
 * F2 resize sessions with runtime assertions.
 *
 * Two sessions, because a rest-only sweep hides the interesting failures:
 *   A  offset (0, 0)
 *   B  offset (260, 180)
 * The offset is NOT reset between steps -- resetting it every frame is exactly
 * what would mask a catalog-window or recycling fault.
 *
 * At every step the page's own pool, asset and media state is recorded, and the
 * invariants that must hold across a resize are asserted: no new meshes, no
 * destroyed meshes, stable video and texture counts, no reload, no console
 * error, no card overlap, no large void.
 */
import { spawnSync } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "qa-v5/f2/session"), fps: 18, query: "" };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--origin=")) opts.origin = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
}

const HOLDS = ["1920x1080", "1440x900", "1366x768", "1100x720", "844x390", "390x844"];
function sweepSteps() {
  const s = [];
  for (let w = 1920; w >= 1024; w -= 40) s.push([w, Math.round(w * 0.5625 / 0.9)]);
  for (let w = 1024; w >= 844; w -= 30) s.push([w, Math.max(390, Math.round(w * 0.55))]);
  s.push([844, 390]);
  // through the orientation corner, 1 px either side of square
  for (const [w, h] of [[800, 425], [760, 470], [720, 520], [680, 565], [640, 600],
                        [618, 617], [617, 617], [617, 618], [600, 640], [565, 680],
                        [520, 720], [470, 760], [425, 800], [390, 844]]) s.push([w, h]);
  return s;
}

function quadOverlap(quads, vw, vh) {
  const on = quads.map(q => q.quad.map(([x, y]) => [x * vw, y * vh]))
    .filter(p => Math.max(...p.map(q => q[0])) > -40 && Math.min(...p.map(q => q[0])) < vw + 40
              && Math.max(...p.map(q => q[1])) > -40 && Math.min(...p.map(q => q[1])) < vh + 40);
  const sep = (a, b) => {
    let best = -Infinity;
    for (const poly of [a, b]) for (let k = 0; k < poly.length; k++) {
      const [x0, y0] = poly[k], [x1, y1] = poly[(k + 1) % poly.length];
      let nx = -(y1 - y0), ny = x1 - x0;
      const L = Math.hypot(nx, ny); if (L < 1e-9) continue;
      nx /= L; ny /= L;
      const pa = a.map(p => p[0] * nx + p[1] * ny), pb = b.map(p => p[0] * nx + p[1] * ny);
      best = Math.max(best, Math.max(Math.min(...pb) - Math.max(...pa), Math.min(...pa) - Math.max(...pb)));
    }
    return best;
  };
  let worst = Infinity, count = 0;
  for (let i = 0; i < on.length; i++) for (let j = i + 1; j < on.length; j++) {
    const d = sep(on[i], on[j]); worst = Math.min(worst, d); if (d <= 0) count++;
  }
  return { cards: on.length, minSeparationPx: Number.isFinite(worst) ? +worst.toFixed(2) : null, overlaps: count };
}

async function runSession(browser, name, offset, framesDir) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const consoleErrors = [], pageErrors = [], requests = [];
  page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", e => pageErrors.push(String(e.message)));
  page.on("request", r => { if (/\.mp4(\?|$)/.test(r.url())) requests.push(r.url()); });

  await page.goto(`${opts.origin}/?optics=v4&qa=1${opts.query ? "&" + opts.query : ""}`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
  await page.waitForTimeout(2500);
  await page.evaluate(() => window.__ILG_QA__.setQuality("high"));
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
  await page.evaluate(o => window.__ILG_QA__.setOffset(o[0], o[1]), offset);
  await page.waitForTimeout(400);
  const videoLoadsAtStart = requests.length;

  const steps = [];
  for (const [i, [w, h]] of sweepSteps().entries()) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(150);
    // deliberately NOT re-setting the offset: the point is that it survives
    const st = await page.evaluate(() => {
      const q = window.__ILG_QA__;
      const s = q.getState(), v = q.getV4State(), pool = q.getPoolState(), asset = q.getAssetState();
      const near = s.landmarks
        .map(l => ({ i: l.i, j: l.j, d: Math.hypot(l.nx - 0.5, l.ny - 0.5) }))
        .sort((a, b) => a.d - b.d).slice(0, 3).map(l => `${l.i},${l.j}`);
      return {
        compositionScale: v.compositionScale, viewZoom: v.viewZoom, viewport: v.viewport,
        scrollX: s.scrollX, scrollY: s.scrollY, quality: s.quality,
        centreCells: near, pool, asset,
        media: q.getMediaState(), quads: q.getCardQuads(),
      };
    });
    const ov = quadOverlap(st.quads, w, h);
    delete st.quads;
    const file = path.join(framesDir, `${name}-${String(i).padStart(3, "0")}.png`);
    await page.screenshot({ path: file });
    steps.push({ index: i, viewport: [w, h], hold: HOLDS.includes(`${w}x${h}`), file: path.basename(file),
                 ...st, overlap: ov,
                 consoleErrorsSoFar: consoleErrors.length, pageErrorsSoFar: pageErrors.length,
                 videoRequestsSoFar: requests.length });
  }
  await ctx.close();
  return { name, offset, steps, consoleErrors, pageErrors, videoRequests: requests.length, videoLoadsAtStart };
}

function assertSession(s) {
  const f = s.steps[0], out = [];
  const add = (id, ok, detail) => out.push({ assertion: id, pass: !!ok, detail });
  add("noNewMeshesAfterFirstBuild", s.steps.every(x => x.pool.created === f.pool.created),
      `created ${f.pool.created} -> ${s.steps.at(-1).pool.created}`);
  add("noMeshesDestroyed", s.steps.every(x => x.pool.destroyed === f.pool.destroyed),
      `destroyed ${f.pool.destroyed} -> ${s.steps.at(-1).pool.destroyed}`);
  add("poolSlotsStable", s.steps.every(x => x.pool.slots === f.pool.slots), `slots ${f.pool.slots}`);
  add("videoCountStable", s.steps.every(x => x.pool.videos === f.pool.videos), `videos ${f.pool.videos}`);
  add("textureCountStable", s.steps.every(x => x.pool.textures === f.pool.textures), `textures ${f.pool.textures}`);
  add("materialsStable", s.steps.every(x => x.pool.materials === f.pool.materials), `materials ${f.pool.materials}`);
  add("geometriesStable", s.steps.every(x => x.pool.geometries === f.pool.geometries), `geometries ${f.pool.geometries}`);
  add("noVideoReload", s.videoRequests === s.videoLoadsAtStart,
      `${s.videoLoadsAtStart} at start, ${s.videoRequests} total`);
  add("assetsStayReady", s.steps.every(x => x.asset.ready === true), "asset.ready true at every step");
  add("qualityPinnedHigh", s.steps.every(x => x.quality === "high"), "adaptive quality must not drift");
  add("offsetPreserved", s.steps.every(x => Math.abs(x.scrollX - s.offset[0]) < 0.5
                                         && Math.abs(x.scrollY - s.offset[1]) < 0.5),
      `offset held at ${s.offset.join(",")} across every resize step`);
  add("mediaStaysFrozen", s.steps.every(x => (x.media || []).every(m => m.paused !== false)),
      "every clip paused at the frozen frame");
  add("noCardOverlap", s.steps.every(x => x.overlap.overlaps === 0),
      `min separation ${Math.min(...s.steps.map(x => x.overlap.minSeparationPx ?? Infinity)).toFixed(2)} px`);
  add("noConsoleErrors", s.consoleErrors.length === 0, s.consoleErrors.slice(0, 3).join(" | ") || "none");
  add("noPageErrors", s.pageErrors.length === 0, s.pageErrors.slice(0, 3).join(" | ") || "none");
  return out;
}

const framesDir = path.join(opts.out, "frames");
await rm(opts.out, { recursive: true, force: true }).catch(() => {});
await mkdir(framesDir, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const sessions = [];
for (const [name, offset] of [["rest", [0, 0]], ["nonzero-offset", [260, 180]]]) {
  const s = await runSession(browser, name, offset, framesDir);
  s.assertions = assertSession(s);
  sessions.push(s);
  console.log(`${name}: ${s.assertions.filter(a => a.pass).length}/${s.assertions.length} assertions pass`);
}
await browser.close();

const payload = {
  note: "Offset is preserved across every resize step; it is never reset between steps.",
  sessions: sessions.map(s => ({
    name: s.name, offset: s.offset, steps: s.steps.length,
    assertions: s.assertions,
    verdict: s.assertions.every(a => a.pass) ? "PASS" : "FAIL",
    consoleErrors: s.consoleErrors, pageErrors: s.pageErrors,
    trace: s.steps,
  })),
  verdict: sessions.every(s => s.assertions.every(a => a.pass)) ? "PASS" : "FAIL",
};
await writeFile(path.join(opts.out, "runtime-assertions.json"), JSON.stringify(payload, null, 2));

for (const s of sessions) {
  const dir = path.join(opts.out, s.name);
  await mkdir(dir, { recursive: true });
  const py = `
import json,sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
out=Path(sys.argv[1]); frames=Path(sys.argv[2]); name=sys.argv[3]
trace=json.loads((out/"runtime-assertions.json").read_text())
sess=[s for s in trace["sessions"] if s["name"]==name][0]
try: font=ImageFont.truetype("/System/Library/Fonts/Menlo.ttc",28)
except OSError: font=ImageFont.load_default()
CW,CH=1920,1180
comp=out/name/"composited"; comp.mkdir(parents=True,exist_ok=True)
n=0
for st in sess["trace"]:
    src=Image.open(frames/st["file"]).convert("RGB")
    k=min((CW-80)/src.width,(CH-160)/src.height,1.0)
    view=src.resize((int(src.width*k),int(src.height*k)),Image.LANCZOS)
    c=Image.new("RGB",(CW,CH),(14,14,18)); c.paste(view,((CW-view.width)//2,120+(CH-160-view.height)//2))
    d=ImageDraw.Draw(c)
    d.text((40,26),f'{st["viewport"][0]}x{st["viewport"][1]}   S={st["compositionScale"]:.4f}   offset=({st["scrollX"]:.0f},{st["scrollY"]:.0f})   centre cells {",".join(st["centreCells"])}',fill=(240,240,250),font=font)
    d.text((40,64),f'pool slots={st["pool"]["slots"]} created={st["pool"]["created"]} destroyed={st["pool"]["destroyed"]} videos={st["pool"]["videos"]} textures={st["pool"]["textures"]}   minSep={st["overlap"]["minSeparationPx"]}px',fill=(130,150,180),font=font)
    reps = 14 if st["hold"] else 2
    for _ in range(reps):
        c.save(comp/f"f{n:05d}.png"); n+=1
print(n)
`;
  const r = spawnSync("python3", ["-c", py, opts.out, framesDir, s.name], { encoding: "utf8" });
  if (r.status !== 0) { console.error(r.stderr); process.exit(1); }
  const mp4 = path.join(opts.out, s.name, `resize-session-${s.name}.mp4`);
  const enc = spawnSync("ffmpeg", ["-y", "-framerate", String(opts.fps), "-i",
    path.join(opts.out, s.name, "composited", "f%05d.png"), "-c:v", "libx264",
    "-pix_fmt", "yuv420p", "-crf", "20", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4],
    { encoding: "utf8" });
  if (enc.status !== 0) { console.error(enc.stderr?.slice(-1500)); process.exit(1); }
  await rm(path.join(opts.out, s.name, "composited"), { recursive: true, force: true });
  console.log(`video -> ${mp4}`);
}
await rm(framesDir, { recursive: true, force: true });
console.log(`verdict ${payload.verdict}`);
