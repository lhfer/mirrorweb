/**
 * The Sprint 2 input scenarios, in one file, imported by BOTH the card
 * trajectory recorder (§五) and the screen recorder (§四).
 *
 * Same reason as M2's shared sequence module: the recordings a reviewer
 * watches must be of the SAME gestures the geometry instrument measured, or
 * the review is of one thing and the verdict is about another.
 *
 * Every gesture is real browser input -- `page.mouse` on fine-pointer
 * contexts, CDP `Input.dispatchTouchEvent` on touch contexts. Nothing here
 * calls a QA hook to move a page; `setOffset` exists on our side and is
 * deliberately never used, because a trajectory produced by writing the
 * offset would prove nothing about the gesture layer under test.
 */
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function touchDrag(cdp, from, dx, dy, steps, gap) {
  const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
  await cdp.send("Input.dispatchTouchEvent",
    { type: "touchStart", touchPoints: pt(from[0], from[1]) });
  for (let i = 1; i <= steps; i += 1) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove",
      touchPoints: pt(from[0] + (dx * i) / steps, from[1] + (dy * i) / steps) });
    if (gap > 0) await sleep(gap);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function mouseDrag(page, from, dx, dy, steps, gap) {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from[0] + (dx * i) / steps, from[1] + (dy * i) / steps);
    if (gap > 0) await sleep(gap);
  }
  await page.mouse.up();
}

/**
 * `rest` records the page holding still with the pointer parked -- the
 * baseline every gutter and stagger comparison is measured against.
 * `orientation-change` resizes the viewport mid-record, which is the one
 * scenario where the two pages must re-derive their whole layout live.
 */
export const SCENARIOS = [
  {
    key: "rest", vp: "1440x900", touch: false, recordMs: 3000, tailMs: 0,
    what: "still page, pointer parked at centre",
    async run() { await sleep(2600); },
  },
  {
    key: "desktop-slow-drag", vp: "1440x900", touch: false, recordMs: 6500, tailMs: 2600,
    what: "one slow 420 px leftward drag with a slight rise, released",
    async run(page) { await mouseDrag(page, [1000, 470], -420, -60, 30, 24); },
  },
  {
    key: "desktop-fast-flick", vp: "1440x900", touch: false, recordMs: 6500, tailMs: 3400,
    what: "short hard flick -- the dolly window",
    async run(page) { await mouseDrag(page, [1020, 460], -430, 0, 7, 8); },
  },
  {
    key: "desktop-pointer-sweep", vp: "1440x900", touch: false, recordMs: 5500, tailMs: 1500,
    what: "pointer crosses the page with no button down -- pose only, no scroll",
    async run(page) {
      await page.mouse.move(120, 200);
      for (let i = 1; i <= 40; i += 1) {
        await page.mouse.move(120 + i * 30, 200 + Math.round(Math.sin(i / 5) * 160));
        await sleep(26);
      }
    },
  },
  {
    key: "mobile-touch-drag", vp: "390x844", touch: true, recordMs: 5500, tailMs: 2400,
    what: "single 240 px touch drag and release",
    async run(page, cdp) { await touchDrag(cdp, [320, 560], -240, -70, 26, 26); },
  },
  {
    key: "mobile-long-drag-wrap", vp: "390x844", touch: true, recordMs: 9000, tailMs: 2400,
    what: "long touch drag across several cells -- forces occupant rotation",
    async run(page, cdp) { await touchDrag(cdp, [350, 520], -1180, 40, 70, 22); },
  },
  {
    key: "orientation-change", vp: "390x844", touch: true, resizeTo: "844x390",
    recordMs: 7000, tailMs: 2000,
    what: "drag, then a live portrait -> landscape resize, then drag again",
    async run(page, cdp) {
      await touchDrag(cdp, [320, 560], -200, 0, 20, 24);
      await sleep(700);
      await page.setViewportSize({ width: 844, height: 390 });
      await sleep(1800);
      await touchDrag(cdp, [700, 200], -260, 0, 22, 24);
    },
  },
];

export const RECORDED_SCENARIOS = SCENARIOS.filter((s) => s.key !== "rest");
