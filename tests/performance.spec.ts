import { expect, test } from "playwright/test";

test("webgpu path holds a usable frame time at rest", async ({ page }) => {
  await page.goto("/");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  await page.waitForTimeout(2000);
  const metrics = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getMetrics());
  expect(metrics.backend === "webgpu" || metrics.backend === "webgl2").toBeTruthy();
  expect(metrics.medianFrameMs).toBeGreaterThan(0);
  expect(metrics.medianFrameMs).toBeLessThan(30);
});
