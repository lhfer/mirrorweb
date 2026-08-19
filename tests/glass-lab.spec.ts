import { expect, test } from "playwright/test";

test("glass lab is a live single-card page", async ({ page }) => {
  await page.goto("/glass-lab?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  const facts = await page.evaluate(() => ({
    state: window.__LIQUID_GLASS_QA__.getState(),
    canvases: document.querySelectorAll("canvas").length,
    iframes: document.querySelectorAll("iframe").length,
    panel: Boolean(document.getElementById("lab-panel")),
    sliders: document.querySelectorAll("#lab-panel input[type=range]").length,
    backgrounds: [...document.querySelectorAll<HTMLButtonElement>("#lab-panel [data-bg]")].map((item) => item.dataset.bg),
  }));
  expect(facts.iframes).toBe(0);
  expect(facts.canvases).toBe(1);
  expect(facts.panel).toBeTruthy();
  expect(facts.sliders).toBeGreaterThanOrEqual(6);
  expect(facts.backgrounds).toEqual(["checker", "h-lines", "v-lines", "color", "video", "white", "black", "gradient"]);
  expect(facts.state.milestone).toBe(3);
  expect(facts.state.lab).toBeTruthy();
  expect(facts.state.glass).toBe("volume");
});

test("lab pointer tilts the lens without translating a grid", async ({ page }) => {
  await page.goto("/glass-lab?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  await page.evaluate(() => window.__LIQUID_GLASS_QA__.setPointer(-1, -1));
  await page.waitForFunction(() => Math.abs(window.__LIQUID_GLASS_QA__.getState().rotX) > 0.01);
  const state = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(state.scrollX ?? 0).toBe(0);
  expect(Math.abs(state.rotY)).toBeGreaterThan(0.01);
});

test("debug=normals is a glass debug mode", async ({ page }) => {
  await page.goto("/glass-lab?debug=normals&qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
  const state = await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState());
  expect(state.debug).toBe("normals");
});
