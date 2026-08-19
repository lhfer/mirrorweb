import { expect, test } from "playwright/test";

async function maxNearBlackRun(page: import("playwright").Page) {
  const png = await page.screenshot({ type: "png" });
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const canvas = document.createElement("canvas");
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return { maxRun: 999, start: -1 };
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let maxRun = 0;
    let run = 0;
    let start = -1;
    let runStart = 0;
    for (let y = 0; y < canvas.height; y += 1) {
      let dark = 0;
      const row = y * canvas.width * 4;
      for (let x = 0; x < canvas.width; x += 1) {
        const i = row + x * 4;
        if (Math.max(data[i], data[i + 1], data[i + 2]) < 16) dark += 1;
      }
      if (dark / canvas.width > 0.9) {
        if (run === 0) runStart = y;
        run += 1;
        if (run > maxRun) {
          maxRun = run;
          start = runStart;
        }
      } else {
        run = 0;
      }
    }
    return { maxRun, start, width: canvas.width, height: canvas.height };
  }, png.toString("base64"));
}

test("rest A has no full-width near-black valley", async ({ page }) => {
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.mouse.move(720, 450);
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(400);
  const band = await maxNearBlackRun(page);
  expect(band.maxRun, `near-black run ${band.maxRun}px starting at ${band.start}`).toBeLessThanOrEqual(4);
});

test("coverage A overlaps rows instead of opening a mid gutter", async ({ page }) => {
  await page.goto("/?debug=coverage&qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(300);
  const band = await maxNearBlackRun(page);
  expect(band.maxRun, `coverage near-black run ${band.maxRun}px starting at ${band.start}`).toBeLessThanOrEqual(4);
});

test("mobile rest does not open a full-width near-black valley", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/?qa=1");
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset();
    window.__LIQUID_GLASS_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(400);
  const band = await maxNearBlackRun(page);
  expect(band.maxRun, `mobile near-black run ${band.maxRun}px starting at ${band.start}`).toBeLessThanOrEqual(4);
});
