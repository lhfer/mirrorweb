#!/usr/bin/env node
/**
 * True mobile touch gate.
 *
 * The previous harness drove "mobile" sessions with page.mouse, which produces
 * pointerType "mouse" and proves nothing about the touch path. This dispatches
 * real touch events through CDP Input.dispatchTouchEvent and asserts the
 * behaviour that only a touch path can produce.
 */
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const port = Number(process.argv.find((a) => a.startsWith("--port="))?.slice(7) ?? 5322);
const out = process.argv.find((a) => a.startsWith("--out="))?.slice(6);
if (!out) throw new Error("--out is required");

function startPreview() {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("preview did not start")), 30_000);
    const onData = (c) => { if (String(c).includes("Local:")) { clearTimeout(timer); resolve(child); } };
    child.stdout.on("data", onData); child.stderr.on("data", onData); child.once("error", reject);
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function touchDrag(cdp, from, steps) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: from.x, y: from.y, id: 1 }] });
  for (const p of steps) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: p.x, y: p.y, id: 1 }] });
    await sleep(28);
  }
  const last = steps.at(-1) ?? from;
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  return last;
}

let preview, browser;
const report = { generator: "stage-h-touch-gate", orientations: {}, checks: {} };
try {
  preview = await startPreview();
  browser = await chromium.launch({ channel: "chrome", headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

  for (const [name, viewport] of [["portrait", { width: 390, height: 844 }], ["landscape", { width: 844, height: 390 }]]) {
    // deviceScaleFactor 3 exercises the product's own mobile DPR clamp.
    const context = await browser.newContext({ viewport, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    const cdp = await context.newCDPSession(page);
    await page.goto(`http://127.0.0.1:${port}/?optics=v4&qa=1`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__ILG_QA__?.getState()?.ready === true, undefined, { timeout: 90_000 });

    // Record the pointerType the app actually receives, harness-side only.
    await page.evaluate(() => {
      window.__STAGE_H_POINTERS__ = [];
      window.__STAGE_H_EVENTS__ = { pointerdown: 0, pointermove: 0, pointerup: 0, pointercancel: 0, lostpointercapture: 0, touchstart: 0, touchmove: 0, touchend: 0 };
      window.__STAGE_H_MOVE_TS__ = [];
      for (const type of ["pointerdown", "pointermove", "pointerup", "pointercancel", "lostpointercapture"]) {
        window.addEventListener(type, (e) => {
          window.__STAGE_H_EVENTS__[type] += 1;
          window.__STAGE_H_POINTERS__.push(e.pointerType);
          if (type === "pointermove") window.__STAGE_H_MOVE_TS__.push(Math.round(performance.now()));
        }, true);
      }
      for (const type of ["touchstart", "touchmove", "touchend"]) {
        window.addEventListener(type, () => { window.__STAGE_H_EVENTS__[type] += 1; }, true);
      }
    });
    await page.evaluate(() => window.__ILG_QA__.reset());
    await sleep(1200);

    const before = await page.evaluate(() => window.__ILG_QA__.getState());
    const dprState = await page.evaluate(() => ({
      browserDpr: window.devicePixelRatio,
      rendererDpr: window.__ILG_V4_GRID_QA__.getV4State().sceneColor.dpr,
      canvas: (() => { const c = document.querySelector("canvas"); return c ? [c.width, c.height] : null; })(),
    }));

    // A page-side rAF recorder, so nothing crosses the process boundary while
    // the touch path is being dispatched. Polling getState() from Node during
    // the drag runs JS on the page's main thread and swallows pointermove.
    await page.evaluate(() => {
      window.__STAGE_H_TRACE__ = [];
      const tick = () => {
        const s = window.__ILG_QA__.getState();
        window.__STAGE_H_TRACE__.push([performance.now(), s.scrollX, s.scrollY, s.velocityX, s.velocityY, s.dragging]);
        window.__STAGE_H_RAF__ = requestAnimationFrame(tick);
      };
      window.__STAGE_H_RAF__ = requestAnimationFrame(tick);
    });

    const start = { x: Math.round(viewport.width * 0.8), y: Math.round(viewport.height * 0.75) };
    const steps = [];
    for (let k = 1; k <= 16; k += 1) steps.push({ x: start.x - k * 15, y: start.y - k * 17 });
    await touchDrag(cdp, start, steps);
    await sleep(2400);
    await page.evaluate(() => cancelAnimationFrame(window.__STAGE_H_RAF__));

    const trace = await page.evaluate(() => window.__STAGE_H_TRACE__);
    const pointerTypes = await page.evaluate(() => Array.from(new Set(window.__STAGE_H_POINTERS__)));
    const eventCounts = await page.evaluate(() => window.__STAGE_H_EVENTS__);
    const moveTimestamps = await page.evaluate(() => window.__STAGE_H_MOVE_TS__);
    const pageScroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));

    const dragSamples = trace.filter((t) => t[5]);
    const lastDragIdx = trace.map((t) => t[5]).lastIndexOf(true);
    const first = trace[0];
    const atRelease = lastDragIdx >= 0 ? trace[lastDragIdx] : trace[0];
    const shortlyAfter = trace[Math.min(trace.length - 1, lastDragIdx + 8)] ?? trace.at(-1);
    const settled = trace.at(-1);

    // The grid is damped, so its offset lags the finger and keeps moving after
    // release. "Did touch move the grid" is therefore the total displacement
    // from before the gesture to fully settled, not the displacement measured
    // while the finger was still down.
    const totalMoved = Math.hypot(settled[1] - first[1], settled[2] - first[2]);
    const moved = Math.hypot(atRelease[1] - first[1], atRelease[2] - first[2]);
    const releaseSpeed = Math.hypot(atRelease[3], atRelease[4]);
    const coastDistance = Math.hypot(shortlyAfter[1] - atRelease[1], shortlyAfter[2] - atRelease[2]);
    const draggingSeen = trace.map((t) => t[5]);

    report.orientations[name] = {
      viewport: [viewport.width, viewport.height],
      pointerTypes,
      eventCounts,
      moveSpanMs: moveTimestamps.length > 1 ? moveTimestamps.at(-1) - moveTimestamps[0] : 0,
      browserDpr: dprState.browserDpr,
      rendererDpr: dprState.rendererDpr,
      canvasPixels: dprState.canvas,
      gridOffsetTotalPx: Number(totalMoved.toFixed(2)),
      gridOffsetDuringDragPx: Number(moved.toFixed(2)),
      releaseSpeed: Number(releaseSpeed.toFixed(2)),
      coastDistancePx: Number(coastDistance.toFixed(2)),
      settledSpeed: Number(Math.hypot(settled[3], settled[4]).toFixed(2)),
      draggingSamples: draggingSeen.filter(Boolean).length,
      traceSamples: trace.length,
      pageScroll,
    };
    await context.close();
  }

  const o = report.orientations;
  const both = ["portrait", "landscape"];
  report.checks = {
    POINTER_TYPE_IS_TOUCH: both.every((k) => o[k].pointerTypes.length > 0 && o[k].pointerTypes.every((t) => t === "touch")),
    // The pointer stream must survive the whole gesture. Before the fix a
    // 16-step drag produced pointermove 1, pointerup 0, pointercancel 1.
    POINTER_STREAM_SURVIVES: both.every((k) => o[k].eventCounts.pointermove > 10),
    POINTER_UP_DELIVERED: both.every((k) => o[k].eventCounts.pointerup === 1),
    NO_POINTER_CANCEL: both.every((k) => o[k].eventCounts.pointercancel === 0),
    TOUCH_DRAG_MOVES_GRID: both.every((k) => o[k].gridOffsetTotalPx > 150),
    RELEASE_PRODUCES_INERTIA: both.every((k) => o[k].coastDistancePx > 1 && o[k].releaseSpeed > 0),
    INERTIA_SETTLES: both.every((k) => o[k].settledSpeed < o[k].releaseSpeed),
    NO_PAGE_SCROLL: both.every((k) => o[k].pageScroll.x === 0 && o[k].pageScroll.y === 0),
    POINTER_CAPTURE_HELD: both.every((k) => o[k].draggingSamples > 0),
    BOTH_ORIENTATIONS_RUN: both.every((k) => Boolean(o[k])),
    MOBILE_DPR_CLAMPED_TO_1_5: both.every((k) => o[k].browserDpr === 3 && o[k].rendererDpr === 1.5),
    CANVAS_SIZED_FOR_VIEWPORT: both.every((k) => {
      const [w, h] = o[k].viewport; const c = o[k].canvasPixels;
      return c && Math.abs(c[0] - w * o[k].rendererDpr) <= 2 && Math.abs(c[1] - h * o[k].rendererDpr) <= 2;
    }),
  };
  report.status = Object.values(report.checks).every(Boolean) ? "PASS" : "FAIL";
  report.failed = Object.entries(report.checks).filter(([, v]) => !v).map(([k]) => k);
  await mkdir(path.dirname(out), { recursive: true });
  await writeFile(out, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ status: report.status, failed: report.failed, checks: report.checks }, null, 2));
} finally { await browser?.close(); preview?.kill("SIGTERM"); }
