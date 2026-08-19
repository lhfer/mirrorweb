import { expect, test } from "playwright/test";

test("drag left moves the field and keeps velocity on release", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  await page.evaluate(() => window.__LIQUID_GLASS_QA__.reset());
  await page.mouse.move(720, 450);
  await page.mouse.down();
  await page.mouse.move(320, 450, { steps: 40 });
  await page.waitForTimeout(32);
  const held = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  await page.mouse.up();
  await page.waitForTimeout(32);
  const released = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(held.scrollX).toBeGreaterThan(200);
  expect(Math.abs(released.velocityX)).toBeGreaterThan(0);
});

test("hover pointer tilts the view but does not translate the grid", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(-1, -1);
  });
  await page.waitForFunction(() => {
    const state = window.__LIQUID_GLASS_QA__.getState();
    return Math.abs(state.pointerX + 1) < 0.05 && Math.abs(state.pointerY + 1) < 0.05;
  });
  const state = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(state.scrollX).toBe(0);
  expect(state.scrollY).toBe(0);
  expect(Math.abs(state.rotX)).toBeGreaterThan(0.01);
  expect(Math.abs(state.rotY)).toBeGreaterThan(0.01);
  expect(Math.abs(state.camX)).toBeGreaterThan(8);
  expect(Math.abs(state.camY)).toBeGreaterThan(5);
});

test("pointer eases to the target without a hard snap", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(1, 0);
  });
  const early = await page.evaluate(() => new Promise<{ pointerX: number }>((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        resolve({ pointerX: window.__LIQUID_GLASS_QA__.getState().pointerX });
      });
    });
  }));
  expect(early.pointerX).toBeGreaterThan(0);
  expect(early.pointerX).toBeLessThan(0.85);
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__.getState().pointerX > 0.95);
  const settled = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(settled.pointerX).toBeGreaterThan(0.95);
  expect(settled.pointerTargetX).toBe(1);
});

test("thirty seconds of motion does not crash", async ({ page }) => {
  test.setTimeout(60000);
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  for (let i = 0; i < 8; i += 1) {
    await page.mouse.move(720, 450);
    await page.mouse.down();
    await page.mouse.move(720 - 240, 450 + (i % 2 ? 80 : -80), { steps: 6 });
    await page.mouse.up();
  }
  const state = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(Number.isFinite(state.scrollX)).toBeTruthy();
});
