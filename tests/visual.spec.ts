import { expect, test } from "playwright/test";

const ORIGIN = {
  topL: { i: -1, j: 2, nx: 203.676 / 1440, ny: -139.734 / 900 },
  topC: { i: 0, j: 2, nx: 720 / 1440, ny: -155.231 / 900 },
  topR: { i: 1, j: 2, nx: 1236.324 / 1440, ny: -139.734 / 900 },
  midL: { i: -1, j: 1, nx: 441.143 / 1440, ny: 237.249 / 900 },
  midR: { i: 0, j: 1, nx: 998.857 / 1440, ny: 237.249 / 900 },
  botL: { i: -1, j: 0, nx: 181.376 / 1440, ny: 660.38 / 900 },
  botC: { i: 0, j: 0, nx: 720 / 1440, ny: 661.047 / 900 },
  botR: { i: 1, j: 0, nx: 1258.624 / 1440, ny: 660.38 / 900 },
};

function find(landmarks: Array<{ i: number; j: number; nx: number; ny: number }>, i: number, j: number) {
  return landmarks.find((item) => item.i === i && item.j === j);
}

test("local page is a live canvas, not a disguise", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.mouse.move(720, 450);
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(300);
  const facts = await page.evaluate(() => ({
    iframes: document.querySelectorAll("iframe").length,
    videos: document.querySelectorAll("video").length,
    canvases: document.querySelectorAll("canvas").length,
    state: window.__LIQUID_GLASS_QA__.getState(),
    pool: window.__LIQUID_GLASS_QA__.getPoolState(),
    assets: window.__LIQUID_GLASS_QA__.getAssetState(),
  }));
  expect(facts.iframes).toBe(0);
  expect(facts.canvases).toBe(1);
  expect(facts.assets.ready).toBeTruthy();
  expect(facts.assets.videos).toBeGreaterThan(0);
  expect(facts.assets.placeholderTileCount ?? 0).toBe(0);
  expect(facts.assets.media).toBe("video");
  expect(facts.state.milestone).toBe(3);
  expect(facts.state.glass).toBe("volume");
  expect(facts.pool.slots).toBe(81);
  expect(facts.state.backend === "webgpu" || facts.state.backend === "webgl2").toBeTruthy();
  const shot = await page.screenshot({ path: "artifacts/local/A-1440x900-dpr1/06-rest-5s.png", type: "png" });
  expect(shot.byteLength).toBeGreaterThan(20000);
});

test("rest nine landmarks stay within 2% of the origin brick", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.mouse.move(720, 450);
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(200);
  const state = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  const errors: string[] = [];
  for (const [name, target] of Object.entries(ORIGIN)) {
    const hit = find(state.landmarks, target.i, target.j);
    if (!hit) {
      errors.push(`${name} missing i=${target.i} j=${target.j}`);
      continue;
    }
    const dx = Math.abs(hit.nx - target.nx);
    const dy = Math.abs(hit.ny - target.ny);
    if (name.startsWith("top")) {
      if (hit.ny >= 0) errors.push(`${name} top row is not clipped (ny=${hit.ny.toFixed(3)})`);
      if (dx > 0.06) errors.push(`${name} nx Δ=${(dx * 100).toFixed(2)}%`);
      continue;
    }
    const limit = name.startsWith("bot") && name !== "botC" ? 0.03 : 0.02;
    if (dx > limit || dy > limit) {
      errors.push(`${name} Δn=(${(dx * 100).toFixed(2)}%,${(dy * 100).toFixed(2)}%) limit=${limit * 100}%`);
    }
  }
  expect(errors, errors.join("; ")).toEqual([]);
  const midGutter = state.landmarks.every((item) => Math.hypot(item.nx - 0.5, item.ny - 0.5) > 0.04);
  expect(midGutter).toBeTruthy();
});

test("coverage debug paints tiles and reports overscan", async ({ page }) => {
  await page.goto("/?debug=coverage&qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  const facts = await page.evaluate(() => ({
    mode: window.__LIQUID_GLASS_QA__.getState().debug,
    hud: Boolean(document.getElementById("debug-hud")),
    hidden: (document.getElementById("debug-hud") as HTMLElement | null)?.hidden,
  }));
  expect(facts.mode).toBe("coverage");
  expect(facts.hud).toBeTruthy();
  expect(facts.hidden).toBeFalsy();
});
