import { expect, test } from "playwright/test";

test("mobile viewport keeps a live canvas", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  const box = await page.locator("canvas").boundingBox();
  expect(box?.width).toBeGreaterThan(300);
  expect(box?.height).toBeGreaterThan(700);
});

test("landscape mobile resizes without losing the canvas", async ({ page }) => {
  await page.setViewportSize({ width: 844, height: 390 });
  await page.goto("/");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  const box = await page.locator("canvas").boundingBox();
  expect(box?.width).toBeGreaterThan(700);
});
