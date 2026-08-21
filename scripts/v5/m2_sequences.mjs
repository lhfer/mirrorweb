/**
 * The input sequences, in one file, imported by BOTH the trace recorder and the
 * screen recorder.
 *
 * Why a shared module rather than a copy in each: the recordings a reviewer
 * watches have to be of the SAME gestures the gate measured, or the review is
 * of one thing and the verdict is about another. Two copies of a gesture drift;
 * one import cannot.
 *
 * Every sequence here is real browser input dispatched through the automation
 * protocol. Two are marked as synthetic where they are dispatched, and only two:
 * wheel deltaMode 1 and 2, which no real device can produce through the
 * protocol, and lostpointercapture, which is the event a page receives when
 * something else claims the pointer. Both are recorded with `isTrusted: false`
 * in the trace, so a reader never has to take a comment's word for it.
 */

export const SEQUENCES = [
  "slow-horizontal-drag",
  "slow-vertical-drag",
  "diagonal-drag",
  "medium-drag",
  "fast-flick",
  "reverse-flick",
  "wheel-mouse-steps",
  "wheel-trackpad-small",
  "wheel-deltamode",
  "pointer-sweep",
  "touch-drag-release",
  "pointercancel",
  "lostpointercapture",
  "resize-during-motion",
  "long-drag-multi-wrap",
];

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Straight mouse drag, `steps` moves of `dx,dy` each spaced `gap` ms. */
export async function mouseDrag(page, from, dx, dy, steps, gap, release = true) {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from[0] + dx * i, from[1] + dy * i);
    if (gap > 0) await sleep(gap);
  }
  if (release) await page.mouse.up();
}

export async function touchDrag(cdp, from, dx, dy, steps, gap, end = "touchend") {
  const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(from[0], from[1]) });
  for (let i = 1; i <= steps; i += 1) {
    await cdp.send("Input.dispatchTouchEvent",
      { type: "touchMove", touchPoints: pt(from[0] + dx * i, from[1] + dy * i) });
    if (gap > 0) await sleep(gap);
  }
  if (end === "touchcancel") await cdp.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
  else await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

export async function runSequence(page, cdp, name, w, h) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const span = Math.min(w, h);
  switch (name) {
    case "slow-horizontal-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.02, 0, 30, 26);
      return { tailMs: 2600 };
    case "slow-vertical-drag":
      await mouseDrag(page, [cx, cy - span * 0.3], 0, span * 0.02, 30, 26);
      return { tailMs: 2600 };
    case "diagonal-drag":
      await mouseDrag(page, [cx - span * 0.22, cy - span * 0.22], span * 0.014, span * 0.014, 30, 26);
      return { tailMs: 2600 };
    case "medium-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.045, 0, 14, 16);
      return { tailMs: 2600 };
    case "fast-flick":
      await mouseDrag(page, [cx + span * 0.36, cy], -span * 0.09, 0, 8, 6);
      return { tailMs: 3400 };
    case "reverse-flick":
      // out, then hard back the other way without releasing in between
      await page.mouse.move(cx - span * 0.3, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx - span * 0.3 + span * 0.07 * i, cy); await sleep(8); }
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.26 - span * 0.075 * i, cy); await sleep(6); }
      await page.mouse.up();
      return { tailMs: 3400 };
    case "wheel-mouse-steps":
      await page.mouse.move(cx, cy);
      for (let i = 0; i < 8; i += 1) { await page.mouse.wheel(0, 120); await sleep(60); }
      for (let i = 0; i < 4; i += 1) { await page.mouse.wheel(120, 0); await sleep(60); }
      return { tailMs: 2200 };
    case "wheel-trackpad-small":
      await page.mouse.move(cx, cy);
      for (let i = 0; i < 40; i += 1) { await page.mouse.wheel(2.5, 6.5); await sleep(12); }
      return { tailMs: 2200 };
    case "wheel-deltamode": {
      // deltaMode 1 (lines) and 2 (pages) cannot be produced by a real device
      // through the automation API, so they are dispatched synthetically and
      // labelled as such. The claim under test is that NO wheel listener is
      // registered at all, and an untrusted WheelEvent still reaches a
      // listener if one exists -- so absence of response is evidence either
      // way, and deltaMode 0 is additionally covered by a real wheel above.
      await page.mouse.move(cx, cy);
      for (const mode of [0, 1, 2]) {
        for (let i = 0; i < 6; i += 1) {
          await page.evaluate(([m, x, y]) => {
            const scale = m === 0 ? 100 : m === 1 ? 3 : 1;
            window.dispatchEvent(new WheelEvent("wheel", {
              deltaX: scale, deltaY: scale, deltaMode: m,
              clientX: x, clientY: y, bubbles: true, cancelable: true,
            }));
          }, [mode, cx, cy]);
          await sleep(40);
        }
        await sleep(260);
      }
      return { tailMs: 2200 };
    }
    case "pointer-sweep": {
      const pad = 6;
      const stops = [[cx, cy], [pad, pad], [w - pad, pad], [w - pad, h - pad], [pad, h - pad], [cx, cy]];
      for (const [x, y] of stops) {
        await page.mouse.move(x, y, { steps: 14 });
        await sleep(520);
      }
      return { tailMs: 1400 };
    }
    case "touch-drag-release":
      await touchDrag(cdp, [cx + span * 0.3, cy + span * 0.16], -span * 0.06, -span * 0.03, 12, 10);
      return { tailMs: 3400 };
    case "pointercancel":
      await touchDrag(cdp, [cx, cy], -span * 0.05, 0, 10, 12, "touchcancel");
      return { tailMs: 2600 };
    case "lostpointercapture": {
      // Press, drag, then take the capture away: dispatch the event the page
      // would get if something else claimed the pointer mid-gesture.
      await page.mouse.move(cx + span * 0.28, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.28 - span * 0.05 * i, cy); await sleep(12); }
      await page.evaluate(() => {
        const e = new PointerEvent("lostpointercapture", { pointerId: 1, bubbles: true, cancelable: false });
        (document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2) || document.body).dispatchEvent(e);
      });
      await sleep(220);
      await page.mouse.up();
      return { tailMs: 2600 };
    }
    case "resize-during-motion": {
      await mouseDrag(page, [cx + span * 0.34, cy], -span * 0.085, 0, 8, 6);
      await sleep(120);
      await page.setViewportSize({ width: Math.round(w * 0.78), height: Math.round(h * 0.86) });
      await sleep(1200);
      await page.setViewportSize({ width: w, height: h });
      return { tailMs: 2600 };
    }
    case "long-drag-multi-wrap":
      await mouseDrag(page, [Math.round(w * 0.9), cy], -Math.round(w * 0.1), 0, 40, 14);
      return { tailMs: 3400 };
    default:
      throw new Error(`unknown sequence ${name}`);
  }
}

