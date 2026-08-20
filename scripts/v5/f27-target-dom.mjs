#!/usr/bin/env node
/**
 * Read the Target's own layout state, in numbers, from its DOM.
 *
 * The Target renders its typography with a CSS3D layer. Every card therefore
 * carries its full world transform as a computed `matrix3d`, the scene root
 * carries the world-to-screen flip, and the container carries the CSS
 * `perspective` -- the focal length in pixels. All of it is readable with
 * getComputedStyle.
 *
 * That makes the responsive law, the grid pitch, the initial scroll and the
 * catalog-to-cell binding directly observable instead of inferred from a
 * regression on detected pixels. A pixel fit has an error bar; this does not.
 *
 * Read-only: it loads the public page, waits, reads computed style. It never
 * interacts, never posts, and it stores no Target pixels unless --shots is
 * given (and then only under artifacts/, which is git-ignored).
 *
 * Each load is COLD: a fresh browser context, so cache and storage are new.
 * That is what makes repeated loads a determinism test rather than a re-read of
 * one already-initialised page.
 *
 * Usage: f27-target-dom.mjs --out=<dir> --vps=WxH,... [--loads=N] [--shots]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

const opts = { out: path.join(REPO, "artifacts/f27/dom"), vps: ["1440x900"], loads: 1,
               shots: false, settle: 6000 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--loads=")) opts.loads = Number(a.slice(8));
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a === "--shots") opts.shots = true;
}

/**
 * Mobile emulation per viewport, reproduced from the F2 sweep so a phase
 * observed here is comparable with the phase observed there. Recorded in the
 * output either way, so a reader never has to guess which UA produced a number.
 */
const MOBILE = new Set(["667x375", "844x390", "390x844", "360x800", "414x896", "430x932",
                        "926x428", "390x700", "390x1000", "500x900", "320x900", "375x812",
                        "393x852", "428x926"]);

function readState() {
  const cards = [];
  for (const d of document.querySelectorAll("div")) {
    const cs = getComputedStyle(d);
    if (!cs.transform.startsWith("matrix3d")) continue;
    const m = cs.transform.slice(9, -1).split(",").map(Number);
    if (m.length !== 16) continue;
    const text = (d.innerText || "").replace(/\s+/g, " ").trim();
    const codes = text.match(/ILG[—-]\s?\d+/g) || [];
    // The scene ROOT is also a div with a matrix3d at some viewports, and it
    // contains every label, so it matched the card test and was read as a card
    // sitting off the lattice. A card carries exactly one code.
    if (codes.length > 1) continue;
    const code = text.match(/ILG[—-]\s?(\d+)/);
    const r = d.getBoundingClientRect();
    cards.push({
      code: code ? Number(code[1]) : null,
      text: text.slice(0, 90),
      // World translation. CSS3D puts the object's world position straight into
      // the matrix's translation column.
      tx: m[12], ty: m[13], tz: m[14],
      // Rotation basis, so yaw and pitch are read rather than fitted.
      basis: [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]],
      cssW: parseFloat(cs.width), cssH: parseFloat(cs.height),
      rect: [r.x, r.y, r.width, r.height],
    });
  }
  // Scene root and perspective container.
  let root = null, persp = null, rootT = null, origin = null;
  for (const d of document.querySelectorAll("div")) {
    const cs = getComputedStyle(d);
    if (cs.perspective !== "none" && persp === null) {
      persp = parseFloat(cs.perspective);
      origin = cs.perspectiveOrigin;
      const kid = d.querySelector(":scope > div");
      if (kid) { root = kid.className; rootT = getComputedStyle(kid).transform; }
    }
  }
  return {
    cards, perspectivePx: persp, perspectiveOrigin: origin, rootClass: root, rootTransform: rootT,
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio,
    userAgent: navigator.userAgent,
    maxTouchPoints: navigator.maxTouchPoints,
    footer: (document.querySelector("footer")?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 200),
  };
}

async function waitReady(page, timeoutMs = 90_000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const s = await page.evaluate(() => {
      const m = (document.body?.innerText || "").match(/(\d+)\s*%/);
      return { p: m ? Number(m[1]) : null, c: !!document.querySelector("canvas") };
    });
    if (s.c && (s.p === null || s.p >= 100)) return true;
    await page.waitForTimeout(120);
  }
  return false;
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

const report = { target: TARGET, capturedAt: new Date().toISOString(), loadsPerViewport: opts.loads,
                 settleMs: opts.settle, method: "computed CSS3D transforms, read-only", loads: [], errors: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = MOBILE.has(vp);
  for (let n = 0; n < opts.loads; n++) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
      isMobile: mobile, hasTouch: mobile });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message)));
    try {
      await page.goto(TARGET, { waitUntil: "load", timeout: 90_000 });
      const ready = await waitReady(page);
      await page.waitForTimeout(opts.settle);
      const a = await page.evaluate(readState);
      // Rest check: the grid must not still be settling, or "initial offset" is
      // whatever moment the screenshot happened to catch.
      await page.waitForTimeout(700);
      const b = await page.evaluate(readState);
      const moved = Math.max(0, ...a.cards.map((c, i) =>
        b.cards[i] ? Math.abs(c.tx - b.cards[i].tx) + Math.abs(c.ty - b.cards[i].ty) : 0));
      if (opts.shots) await page.screenshot({ path: path.join(opts.out, `${vp}-load${n}.png`) });
      report.loads.push({ id: vp, viewport: [w, h], load: n, mobile, ready,
        capturedAtUtc: new Date().toISOString(), atRestDeltaWorld: moved, ...b });
      const codes = b.cards.filter((c) => c.code !== null).map((c) => c.code).sort((x, y) => x - y);
      console.log(`${vp} load${n}  P=${b.perspectivePx}  cards=${b.cards.length}  codes=${codes.length}  rest=${moved.toFixed(3)}`);
    } catch (e) {
      report.errors.push(`${vp} load${n}: ${e.message}`);
      console.error(`FAILED ${vp} load${n}: ${e.message}`);
    }
    if (errors.length) report.errors.push(...errors.map((e) => `${vp} load${n}: ${e}`));
    await ctx.close();
  }
}

await writeFile(path.join(opts.out, "dom-state.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(`done -> ${opts.out}/dom-state.json  (${report.loads.length} loads, ${report.errors.length} errors)`);
