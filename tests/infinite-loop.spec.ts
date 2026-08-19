import { expect, test } from "playwright/test";

test("wrapping keeps a filled field after a large offset jump", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  const before = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getPoolState());
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.setOffset(4000, -2800);
    window.__LIQUID_GLASS_QA__.setVelocity(0, 0);
  });
  await page.waitForTimeout(200);
  const after = await page.evaluate(() => ({
    state: window.__LIQUID_GLASS_QA__.getState(),
    pool: window.__LIQUID_GLASS_QA__.getPoolState(),
  }));
  const visible = after.state.landmarks.filter((item) => item.nx >= -0.2 && item.nx <= 1.2 && item.ny >= -0.2 && item.ny <= 1.2);
  expect(visible.length).toBeGreaterThanOrEqual(6);
  expect(after.pool.slots).toBe(before.slots);
  expect(after.pool.created).toBe(before.created);
  expect(after.pool.destroyed).toBe(before.destroyed);
});
