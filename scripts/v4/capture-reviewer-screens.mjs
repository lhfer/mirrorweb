#!/usr/bin/env node

/**
 * Reviewer Mode acceptance run.
 *
 * Drives the guided five-step flow in a real browser and produces both the
 * screenshots and the machine-checkable evidence for the Phase 1B acceptance
 * criteria:
 *
 *   - the target card fills at least 65% of the step 2 review stage, for all
 *     seven roles;
 *   - the local candidate is never requested while the reviewer is in the
 *     target annotation stage (steps 0-4);
 *   - an illegal optical boundary ordering cannot be produced by dragging;
 *   - drafts autosave and a reload restores the same role, step and geometry.
 *
 * It runs against a throwaway reviewer draft file and never touches
 * qa-v4/reference/frozen-visual/annotations.private.json, whose hash is
 * verified before and after the run.
 */

import { createHash } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

import { startPrivateReviewServer } from "./lib/private-review-server.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ANNOTATIONS = path.join(REPO_ROOT, "qa-v4/reference/frozen-visual/annotations.private.json");
const DEFAULT_OUTPUT = path.join(REPO_ROOT, "qa-v4/review/phase-1b/reviewer-screens");
const DEFAULT_STATE = path.join(REPO_ROOT, "qa-v4/review/phase-1b/reviewer-state.screenshot-demo.private.json");
const ROLE_IDS = ["bright", "dark", "highTexture", "lowTexture", "front", "leftTilt", "rightTilt"];
const MIN_COVERAGE = 0.65;

const options = {
  port: 5284,
  output: DEFAULT_OUTPUT,
  statePath: DEFAULT_STATE,
  keepState: false,
};
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--port=")) options.port = Number(argument.slice("--port=".length));
  else if (argument.startsWith("--out=")) options.output = path.resolve(REPO_ROOT, argument.slice("--out=".length));
  else if (argument.startsWith("--state=")) options.statePath = path.resolve(REPO_ROOT, argument.slice("--state=".length));
  else if (argument === "--keep-state") options.keepState = true;
  else throw new Error(`Unknown argument: ${argument}`);
}

const failures = [];
const checks = [];

function check(id, passed, detail) {
  checks.push({ id, status: passed ? "PASSED" : "FAILED", detail });
  if (!passed) failures.push(`${id}: ${JSON.stringify(detail)}`);
  console.log(`${passed ? "PASS" : "FAIL"} ${id} ${detail === undefined ? "" : JSON.stringify(detail)}`);
}

async function sha256File(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

function repositoryPath(file) {
  return path.relative(REPO_ROOT, file).split(path.sep).join("/");
}

const annotationsBefore = await sha256File(ANNOTATIONS);
await rm(options.statePath, { force: true });
await mkdir(options.output, { recursive: true });

const instance = await startPrivateReviewServer({
  port: options.port,
  reviewerStatePath: options.statePath,
});
const origin = instance.runtime.origin;
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1680, height: 1050 }, deviceScaleFactor: 1 });

const requests = [];
const consoleErrors = [];
page.on("request", (request) => requests.push(request.url()));
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));

const screenshots = [];
async function shot(name) {
  const file = path.join(options.output, name);
  await page.screenshot({ path: file });
  screenshots.push(repositoryPath(file));
  return file;
}

function localRequestsSince(index) {
  return requests.slice(index).filter((url) => /\/__phase1b_review__\/asset\/[A-Za-z]+\/local-/.test(url));
}

async function waitForSaved() {
  await page.waitForFunction(
    () => document.querySelector("#rv-save")?.getAttribute("data-status") === "SAVED",
    undefined,
    { timeout: 15000 },
  );
}

async function reviewerState() {
  const response = await fetch(`${origin}/__phase1b_review__/reviewer/state`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`state HTTP ${response.status}`);
  return response.json();
}

async function stepOf(roleId) {
  const { state } = await reviewerState();
  return state.roles[roleId].step;
}

try {
  await page.goto(`${origin}/`, { waitUntil: "networkidle" });
  await page.waitForSelector("#rv-tutorial-start", { timeout: 20000 });
  await page.waitForTimeout(600);
  await shot("00-tutorial.png");
  check("TUTORIAL_RENDERS", await page.locator(".rv-forbidden li").count() >= 6, {
    forbiddenExamples: await page.locator(".rv-forbidden li").count(),
    correctWrong: await page.locator(".rv-compare-figures .rv-figure-card").count(),
  });

  const targetStageStart = requests.length;
  await page.click("#rv-tutorial-start");
  await page.waitForSelector("#rv-accept-frame", { timeout: 20000 });
  await page.waitForTimeout(900);
  await shot("01-bright-step1-frame.png");
  check("STEP1_CANDIDATES", await page.locator(".rv-candidate").count() >= 3, {
    candidates: await page.locator(".rv-candidate").count(),
  });
  check("STEP1_REJECT_REASONS", await page.locator(".rv-reject .rv-chip-button").count() === 6, {
    reasons: await page.locator(".rv-reject .rv-chip-button").count(),
  });

  await page.click("#rv-accept-frame");
  await page.waitForSelector("#rv-accept-quad", { timeout: 30000 });
  await waitForSaved();
  await page.waitForTimeout(1200);
  await shot("02-bright-step2-quad.png");
  const brightCoverage = Number(await page.locator("#rv-coverage").getAttribute("data-fill"));
  check("STEP2_CARD_COVERAGE_BRIGHT", brightCoverage >= MIN_COVERAGE, { coverage: brightCoverage });
  check("STEP2_LOUPE_AND_ZOOM", await page.locator("[data-zoom]").count() === 3, {
    zoomLevels: await page.locator("[data-zoom]").count(),
    planePreview: await page.locator("#rv-quad-plane canvas").count(),
  });

  await page.click("#rv-accept-quad");
  await page.waitForSelector("#rv-accept-zones", { timeout: 30000 });
  await waitForSaved();
  await page.waitForTimeout(1200);
  await shot("03-bright-step3-zones.png");
  check("STEP3_BOUNDARIES_ON_CARD", await page.locator(".rv-zone-line").count() === 3, {
    boundaries: await page.locator(".rv-zone-line").count(),
    focusViews: await page.locator("[data-focus]").count(),
  });

  // Illegal ordering attempt: drag the innermost boundary far outside the card
  // and the outermost boundary far inside it.
  // Grab a point that really sits on the drawn boundary: the polygon points are
  // in stage pixels because the overlay viewBox matches the stage box exactly.
  const boundaryPoint = async (index) => page.evaluate((boundary) => {
    const node = document.querySelector(`[data-boundary="${boundary}"]`);
    const stage = document.querySelector("#rv-zone-stage");
    if (!node || !stage) return null;
    const points = (node.getAttribute("points") ?? "").split(" ").map((pair) => pair.split(",").map(Number));
    if (points.length !== 4) return null;
    const rect = stage.getBoundingClientRect();
    return {
      x: rect.left + (points[0][0] + points[1][0]) / 2,
      y: rect.top + (points[0][1] + points[1][1]) / 2,
      stageTop: rect.top,
      stageBottom: rect.top + rect.height,
      stageHeight: rect.height,
    };
  }, index);

  const before = (await reviewerState()).state.roles.bright.zones.widths;

  // 1. A legal drag must actually move the boundary.
  const shoulderLine = await boundaryPoint(1);
  await page.mouse.move(shoulderLine.x, shoulderLine.y);
  await page.mouse.down();
  await page.mouse.move(shoulderLine.x, shoulderLine.y + shoulderLine.stageHeight * 0.06, { steps: 14 });
  await page.mouse.up();
  await page.waitForTimeout(600);
  await waitForSaved();
  const moved = (await reviewerState()).state.roles.bright.zones.widths;
  check("BOUNDARY_DRAG_MOVES_BOUNDARY", moved.strongRim !== before.strongRim, { before, moved });

  // 2. Dragging the innermost boundary far outside the card, then the
  //    outermost boundary far inside it, must not produce an illegal order.
  const innerLine = await boundaryPoint(2);
  await page.mouse.move(innerLine.x, innerLine.y);
  await page.mouse.down();
  await page.mouse.move(innerLine.x, innerLine.stageTop - 80, { steps: 16 });
  await page.mouse.up();
  await page.waitForTimeout(500);
  const outerLine = await boundaryPoint(0);
  await page.mouse.move(outerLine.x, outerLine.y);
  await page.mouse.down();
  await page.mouse.move(outerLine.x, outerLine.stageTop + outerLine.stageHeight * 0.48, { steps: 16 });
  await page.mouse.up();
  await page.waitForTimeout(700);
  await waitForSaved();
  const after = (await reviewerState()).state.roles.bright.zones.widths;
  const bounds = {
    sidewall: after.sidewall,
    rim: after.sidewall + after.strongRim,
    shoulder: after.sidewall + after.strongRim + after.shoulder,
  };
  check(
    "ILLEGAL_BOUNDARY_ORDER_IMPOSSIBLE",
    after.sidewall > 0 && after.strongRim > 0 && after.shoulder > 0
      && bounds.sidewall < bounds.rim && bounds.rim < bounds.shoulder && bounds.shoulder < 0.5,
    { before, after, bounds },
  );

  // The boundary drags above were deliberate abuse; restore the provisional
  // starting zones so the remaining screenshots show a normal state.
  await page.click("#rv-reset-zones");
  await page.waitForSelector("#rv-accept-zones", { timeout: 30000 });
  await waitForSaved();
  await page.waitForTimeout(800);

  const localBeforeLock = localRequestsSince(targetStageStart);
  check("LOCAL_HIDDEN_IN_TARGET_STAGE", localBeforeLock.length === 0, {
    localAssetRequests: localBeforeLock.length,
    localPanels: await page.locator("#rv-compare-local").count(),
  });

  await page.click("#rv-accept-zones");
  await page.waitForSelector("#rv-lock", { timeout: 30000 });
  await waitForSaved();
  await page.waitForTimeout(900);
  await shot("04-bright-step4-lock.png");
  check("STEP4_SUMMARY", await page.locator(".rv-crop canvas").count() === 8, {
    crops: await page.locator(".rv-crop canvas").count(),
  });

  const localBeforeLockClick = localRequestsSince(targetStageStart);
  check("LOCAL_HIDDEN_THROUGH_STEP4", localBeforeLockClick.length === 0, {
    localAssetRequests: localBeforeLockClick.length,
  });

  await page.click("#rv-lock");
  await page.waitForSelector("#rv-compare-local", { timeout: 45000 });
  await waitForSaved();
  await page.waitForTimeout(1500);
  await shot("05-bright-step5-compare.png");
  const locked = (await reviewerState()).state.roles.bright.lock;
  check("TARGET_ANNOTATION_LOCK_HASH", /^[0-9a-f]{64}$/.test(locked.targetAnnotationSha256 ?? ""), {
    status: locked.status,
    hash: locked.targetAnnotationSha256,
  });
  check("LOCAL_VISIBLE_ONLY_AFTER_LOCK", localRequestsSince(targetStageStart).length > 0, {
    localAssetRequests: localRequestsSince(targetStageStart).length,
  });
  check("COMPARE_VERDICTS_INDEPENDENT", await page.locator("[data-verdict]").count() === 7, {
    verdicts: await page.locator("[data-verdict]").count(),
  });

  // Target, local and the overlay must address the same region at the same zoom.
  const viewsAll = await page.evaluate(() => ["rv-compare-target", "rv-compare-local", "rv-compare-overlay"]
    .map((id) => document.querySelector(`#${id} canvas`)?.dataset.view ?? null));
  await page.click('[data-compare-focus="tr"]');
  await page.waitForTimeout(900);
  const viewsCorner = await page.evaluate(() => ["rv-compare-target", "rv-compare-local", "rv-compare-overlay"]
    .map((id) => document.querySelector(`#${id} canvas`)?.dataset.view ?? null));
  check(
    "STEP5_ROI_SYNCED",
    viewsCorner.every((view) => view && view === viewsCorner[0]) && viewsCorner[0] !== viewsAll[0],
    { whole: viewsAll[0], topRightCorner: viewsCorner, regions: await page.locator("[data-compare-focus]").count() },
  );
  await page.click('[data-compare-focus="all"]');
  await page.waitForTimeout(900);

  // Autosave + reload restores the same role, the same step and the same geometry.
  const beforeReload = (await reviewerState()).state;
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForSelector("#rv-compare-local", { timeout: 45000 });
  const afterReload = (await reviewerState()).state;
  check("AUTOSAVE_RELOAD_RESTORES", JSON.stringify({
    role: beforeReload.activeRoleId,
    step: beforeReload.roles.bright.step,
    quad: beforeReload.roles.bright.quad,
    zones: beforeReload.roles.bright.zones,
    hash: beforeReload.roles.bright.lock.targetAnnotationSha256,
  }) === JSON.stringify({
    role: afterReload.activeRoleId,
    step: afterReload.roles.bright.step,
    quad: afterReload.roles.bright.quad,
    zones: afterReload.roles.bright.zones,
    hash: afterReload.roles.bright.lock.targetAnnotationSha256,
  }), {
    role: afterReload.activeRoleId,
    step: afterReload.roles.bright.step,
    hash: afterReload.roles.bright.lock.targetAnnotationSha256,
  });
  check("LOCK_HASH_RECOMPUTES", afterReload.roles.bright.lock.targetAnnotationSha256 === locked.targetAnnotationSha256, {
    stored: locked.targetAnnotationSha256,
    reloaded: afterReload.roles.bright.lock.targetAnnotationSha256,
  });

  // Step 2 coverage for every remaining role.
  const coverage = { bright: brightCoverage };
  for (const roleId of ROLE_IDS.filter((id) => id !== "bright")) {
    const index = ROLE_IDS.indexOf(roleId);
    await page.locator(".rv-role").nth(index).click();
    await page.waitForSelector("#rv-accept-frame", { timeout: 30000 });
    await page.click("#rv-accept-frame");
    await page.waitForSelector("#rv-coverage", { timeout: 45000 });
    await page.waitForTimeout(900);
    coverage[roleId] = Number(await page.locator("#rv-coverage").getAttribute("data-fill"));
    if (roleId === "leftTilt") await shot("06-left-tilt-step2-quad.png");
  }
  check(
    "STEP2_CARD_COVERAGE_ALL_ROLES",
    Object.values(coverage).every((value) => value >= MIN_COVERAGE),
    coverage,
  );

  check("NO_CONSOLE_ERRORS", consoleErrors.length === 0, consoleErrors.slice(0, 5));
  check("ROLE_STEP_PERSISTED", await stepOf("bright") === 5, { brightStep: await stepOf("bright") });
} catch (error) {
  check("RUN_COMPLETED", false, error instanceof Error ? error.message : String(error));
  await shot("99-failure.png").catch(() => {});
} finally {
  await browser.close();
  await instance.close();
}

const annotationsAfter = await sha256File(ANNOTATIONS);
check("ANNOTATIONS_PRIVATE_UNTOUCHED", annotationsBefore === annotationsAfter, {
  before: annotationsBefore,
  after: annotationsAfter,
});

if (!options.keepState) {
  // The demo draft exists only to reach step 5 for the screenshots.
  await rm(options.statePath, { force: true });
}

const result = {
  schemaVersion: 1,
  private: true,
  generator: "phase1b-reviewer-screens-v1",
  status: failures.length === 0 ? "PASS" : "FAIL",
  reviewerStatePath: repositoryPath(options.statePath),
  reviewerStateRemoved: !options.keepState,
  annotationsSha256: { before: annotationsBefore, after: annotationsAfter },
  minimumCoverage: MIN_COVERAGE,
  screenshots,
  checks,
};
const resultPath = path.join(options.output, "reviewer-acceptance.local.json");
await writeFile(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
console.log(`\n${result.status} · ${checks.filter((entry) => entry.status === "PASSED").length}/${checks.length} checks`);
console.log(`Result: ${repositoryPath(resultPath)}`);
process.exitCode = failures.length === 0 ? 0 : 1;
