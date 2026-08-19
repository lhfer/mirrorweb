import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, rm, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ROLE_SPECS,
  createPrivateReviewServer,
} from "../../scripts/v4/lib/private-review-server.mjs";
import {
  COMPARE_VERDICTS,
  FRAME_REJECT_REASONS,
  MIN_BAND_WIDTH,
  MAX_TOTAL_INWARD,
  ReviewerStateError,
  boundariesAreOrdered,
  boundariesFromWidths,
  computeTargetAnnotationHash,
  emptyReviewerState,
  localComparisonAllowed,
  maxReachableStep,
  roleProgressState,
  validateReviewerState,
} from "../../scripts/v4/lib/reviewer-state.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const ANNOTATIONS = path.join(ROOT, "qa-v4/reference/frozen-visual/annotations.private.json");
const SOURCE_VIDEO_SHA256 = "b6e79250c75e0357e489de87b63ffd4a5097a573eb7baced35e5de8b050c2435";
const BINDING = {
  frozenManifestSha256: "1".repeat(64),
  reviewBundleSha256: "2".repeat(64),
  reviewAssetSetSha256: "3".repeat(64),
  localRuntimeSourceSetSha256: "4".repeat(64),
};
const CONTEXT = {
  roleSpecs: ROLE_SPECS,
  roleIds: ROLE_SPECS.map((spec) => spec.id),
  sourceVideoSha256: SOURCE_VIDEO_SHA256,
  evidenceBinding: BINDING,
};
const QUAD = [[0.34, 0.68], [0.74, 0.677], [0.737, 0.952], [0.346, 0.904]];
const WIDTHS = { sidewall: 0.012, strongRim: 0.053, shoulder: 0.08 };

function seed() {
  return structuredClone(emptyReviewerState(CONTEXT));
}

function acceptedRole(state, roleId = "bright", overrides = {}) {
  const role = state.roles[roleId];
  role.frame = { status: "ACCEPTED", candidateId: "f192", rejectionReasons: [], note: "" };
  role.quad = { status: "ACCEPTED", quadNormalized: structuredClone(QUAD) };
  role.zones = { status: "ACCEPTED", widths: { ...WIDTHS } };
  role.step = 4;
  Object.assign(role, overrides);
  return role;
}

function lockRole(state, roleId = "bright") {
  const spec = ROLE_SPECS.find((entry) => entry.id === roleId);
  const role = acceptedRole(state, roleId);
  role.lock = {
    status: "LOCKED",
    targetAnnotationSha256: computeTargetAnnotationHash(roleId, spec, role, state),
    lockedAt: "2026-08-19T09:00:00.000Z",
    unlockCount: 0,
    unlockReason: "",
  };
  role.step = 5;
  return role;
}

test("reviewer drafts start empty, and frame / quad / zones / local match stay four separate states", () => {
  const state = validateReviewerState(seed(), CONTEXT);
  assert.equal(state.referenceClass, "frozen-visual-human-reviewer");
  assert.equal(state.private, true);
  assert.equal(state.tutorialAcknowledged, false);
  for (const spec of ROLE_SPECS) {
    const role = state.roles[spec.id];
    assert.equal(role.frame.status, "PENDING");
    assert.equal(role.quad.status, "PENDING");
    assert.equal(role.zones.status, "PENDING");
    assert.equal(role.lock.status, "UNLOCKED");
    assert.deepEqual(role.compare.verdicts, []);
    assert.equal(roleProgressState(role), "PENDING_FRAME");
    assert.equal(maxReachableStep(role), 1);
  }

  // Accepting the frame advances nothing else.
  const partial = seed();
  partial.roles.bright.frame = { status: "ACCEPTED", candidateId: "f192", rejectionReasons: [], note: "" };
  partial.roles.bright.step = 2;
  const afterFrame = validateReviewerState(partial, CONTEXT);
  assert.equal(roleProgressState(afterFrame.roles.bright), "PENDING_QUAD");
  assert.equal(afterFrame.roles.bright.quad.status, "PENDING");
  assert.equal(maxReachableStep(afterFrame.roles.bright), 2);

  // A rejected frame carries its reasons and cannot hold an accepted quad.
  const rejected = seed();
  rejected.roles.dark.frame = {
    status: "REJECTED",
    candidateId: null,
    rejectionReasons: ["motion-blur", "cursor-occlusion"],
    note: "",
  };
  const afterReject = validateReviewerState(rejected, CONTEXT);
  assert.equal(roleProgressState(afterReject.roles.dark), "REJECTED");
  assert.ok(FRAME_REJECT_REASONS.includes(afterReject.roles.dark.frame.rejectionReasons[0]));

  const impossible = seed();
  impossible.roles.dark.quad = { status: "ACCEPTED", quadNormalized: structuredClone(QUAD) };
  assert.throws(() => validateReviewerState(impossible, CONTEXT), /requires an accepted target frame/);
});

test("an illegal optical boundary order cannot be represented or persisted", () => {
  // Widths are the stored representation, so any accepted triple derives an
  // ordered cumulative boundary set by construction.
  for (const widths of [
    { sidewall: MIN_BAND_WIDTH, strongRim: MIN_BAND_WIDTH, shoulder: MIN_BAND_WIDTH },
    { sidewall: 0.012, strongRim: 0.053, shoulder: 0.08 },
    { sidewall: 0.2, strongRim: 0.2, shoulder: 0.05 },
    { sidewall: MAX_TOTAL_INWARD - 2 * MIN_BAND_WIDTH, strongRim: MIN_BAND_WIDTH, shoulder: MIN_BAND_WIDTH },
  ]) {
    const bounds = boundariesFromWidths(widths);
    assert.ok(boundariesAreOrdered(bounds), `${JSON.stringify(widths)} produced ${JSON.stringify(bounds)}`);
    assert.ok(bounds.sidewallToStrongLensRim > 0);
  }

  // A zero-width band, the exact failure the reviewer hit as "Shoulder = 0%",
  // is rejected instead of being stored and reported back as an error.
  for (const widths of [
    { sidewall: 0, strongRim: 0.05, shoulder: 0.08 },
    { sidewall: 0.012, strongRim: 0.053, shoulder: 0 },
    { sidewall: 0.012, strongRim: -0.01, shoulder: 0.08 },
    { sidewall: 0.3, strongRim: 0.3, shoulder: 0.3 },
  ]) {
    const state = seed();
    acceptedRole(state, "bright", { zones: { status: "ACCEPTED", widths }, step: 3 });
    assert.throws(() => validateReviewerState(state, CONTEXT), ReviewerStateError, JSON.stringify(widths));
  }

  // Cumulative boundaries can never be written directly.
  const cumulative = seed();
  acceptedRole(cumulative, "bright", {
    zones: { status: "ACCEPTED", widths: { sidewallToStrongLensRim: 0.1, strongRim: 0.2, shoulder: 0.3 } },
    step: 3,
  });
  assert.throws(() => validateReviewerState(cumulative, CONTEXT), /unexpected property|missing property/);
});

test("the local comparison stays unreachable until the target annotation is locked", () => {
  const state = seed();
  const role = acceptedRole(state, "bright");
  assert.equal(localComparisonAllowed(role), false);
  assert.equal(maxReachableStep(role), 4);

  role.step = 5;
  assert.throws(() => validateReviewerState(state, CONTEXT), /not reachable yet|requires a locked target annotation/);

  const verdictWithoutLock = seed();
  const unlocked = acceptedRole(verdictWithoutLock, "bright");
  unlocked.compare = { verdicts: ["local-looks-close"], note: "" };
  assert.throws(() => validateReviewerState(verdictWithoutLock, CONTEXT), /requires a locked target annotation/);

  const locked = seed();
  const lockedRole = lockRole(locked, "bright");
  lockedRole.compare = { verdicts: [COMPARE_VERDICTS[1]], note: "local rim reads wider" };
  const validated = validateReviewerState(locked, CONTEXT);
  assert.equal(localComparisonAllowed(validated.roles.bright), true);
  assert.equal(maxReachableStep(validated.roles.bright), 5);
  assert.deepEqual(validated.roles.bright.compare.verdicts, ["local-too-wide"]);

  // A local verdict never changes the locked target annotation.
  assert.equal(validated.roles.bright.lock.status, "LOCKED");
  assert.deepEqual(validated.roles.bright.quad.quadNormalized, QUAD);
  assert.deepEqual(validated.roles.bright.zones.widths, WIDTHS);
});

test("a locked target annotation is bound to the hash of its own geometry", () => {
  const state = seed();
  lockRole(state, "bright");
  const validated = validateReviewerState(state, CONTEXT);
  const stored = validated.roles.bright.lock.targetAnnotationSha256;
  assert.match(stored, /^[0-9a-f]{64}$/);

  // Recomputing from the persisted state reproduces the same identity.
  const reloaded = validateReviewerState(structuredClone(validated), CONTEXT);
  assert.equal(reloaded.roles.bright.lock.targetAnnotationSha256, stored);

  // Editing the geometry without re-locking is refused.
  const tampered = structuredClone(validated);
  tampered.roles.bright.zones.widths.shoulder = 0.09;
  assert.throws(() => validateReviewerState(tampered, CONTEXT), /hash does not match/);

  // Unlocking requires a concrete reason.
  const unlocked = structuredClone(validated);
  unlocked.roles.bright.lock = {
    status: "UNLOCKED",
    targetAnnotationSha256: null,
    lockedAt: null,
    unlockCount: 1,
    unlockReason: "typo",
  };
  unlocked.roles.bright.step = 3;
  unlocked.roles.bright.compare = { verdicts: [], note: "" };
  assert.throws(() => validateReviewerState(unlocked, CONTEXT), /concrete reason/);
  unlocked.roles.bright.lock.unlockReason = "corner drifted onto the halo";
  const reopened = validateReviewerState(unlocked, CONTEXT);
  assert.equal(reopened.roles.bright.lock.status, "UNLOCKED");
  assert.deepEqual(reopened.roles.bright.zones.widths, WIDTHS, "drafts survive an unlock");
});

test("rebinding the review evidence clears human decisions but keeps the drafted geometry", () => {
  const state = seed();
  lockRole(state, "bright");
  const locked = validateReviewerState(state, CONTEXT);
  assert.equal(locked.roles.bright.lock.status, "LOCKED");

  const drifted = validateReviewerState(structuredClone(locked), {
    ...CONTEXT,
    evidenceBinding: { ...BINDING, reviewAssetSetSha256: "5".repeat(64) },
  });
  assert.equal(drifted.roles.bright.lock.status, "UNLOCKED");
  assert.equal(drifted.roles.bright.quad.status, "PENDING");
  assert.equal(drifted.roles.bright.zones.status, "PENDING");
  assert.equal(drifted.roles.bright.step, 1);
  assert.deepEqual(drifted.roles.bright.quad.quadNormalized, QUAD);
  assert.deepEqual(drifted.roles.bright.zones.widths, WIDTHS);
});

test("Reviewer Mode is the default entry and the Advanced Inspector is preserved", async () => {
  const [html, entry, app, main, server, zoneModel] = await Promise.all([
    readFile(path.join(ROOT, "phase-1b-review.html"), "utf8"),
    readFile(path.join(ROOT, "src/review-phase1b/entry.ts"), "utf8"),
    readFile(path.join(ROOT, "src/review-phase1b/reviewer/app.ts"), "utf8"),
    readFile(path.join(ROOT, "src/review-phase1b/main.ts"), "utf8"),
    readFile(path.join(ROOT, "scripts/v4/lib/private-review-server.mjs"), "utf8"),
    readFile(path.join(ROOT, "src/review-phase1b/zone-model.ts"), "utf8"),
  ]);
  assert.match(html, /<div id="reviewer-root"><\/div>/);
  assert.match(html, /<template id="advanced-inspector">/);
  assert.match(entry, /mode.*===.*"advanced"/);
  assert.match(entry, /\.\/reviewer\/app/);
  for (const label of ["Frozen target", "Local candidate", "Approve role", "Reject role"]) {
    assert.ok(html.includes(label), `Advanced Inspector markup lost ${label}`);
  }
  // The reviewer surface never talks to the annotation contract endpoint.
  assert.ok(!app.includes("/annotations"), "Reviewer Mode must not reference the annotation endpoint");
  assert.match(app, /reviewer\/state|ReviewerStore/);
  // The Advanced Inspector now edits boundaries through the same width model.
  assert.match(main, /withBoundaryAt/);
  assert.match(main, /setZoneBoundary/);
  assert.ok(!main.includes("function setZoneValue"), "the unordered zone setter is gone");
  assert.match(zoneModel, /MIN_BAND_WIDTH/);
  assert.match(server, /reviewer\/state/);
  assert.match(server, /assertReviewerStatePath/);
});

test("reviewer autosave round-trips over HTTP and never writes the annotation contract", async (t) => {
  const distPage = path.join(ROOT, "dist/phase-1b-review.html");
  const statePath = path.join(ROOT, `qa-v4/review/phase-1b/reviewer-state.node-test-${process.pid}.private.json`);
  let instance;
  try {
    await stat(distPage);
    instance = await createPrivateReviewServer({ port: 5289, reviewerStatePath: statePath });
  } catch (error) {
    t.skip(`private review bundle unavailable (${error.message}); run npm run build and the Phase 1B bundle first`);
    return;
  }
  const origin = await instance.listen();
  const annotationsBefore = createHash("sha256").update(await readFile(ANNOTATIONS)).digest("hex");
  try {
    const initial = await (await fetch(`${origin}/__phase1b_review__/reviewer/state`)).json();
    assert.equal(initial.state.roles.bright.step, 1);
    assert.ok(initial.roles[0].candidates.length >= 0);

    const draft = structuredClone(initial.state);
    draft.tutorialAcknowledged = true;
    draft.activeRoleId = "dark";
    const role = draft.roles.dark;
    role.frame = { status: "ACCEPTED", candidateId: initial.roles[1].candidates[0]?.id ?? null, rejectionReasons: [], note: "" };
    role.quad = { status: "ACCEPTED", quadNormalized: structuredClone(QUAD) };
    role.zones = { status: "ACCEPTED", widths: { ...WIDTHS } };
    role.step = 4;
    if (role.frame.candidateId === null) role.frame.status = "PENDING";

    const saved = await fetch(`${origin}/__phase1b_review__/reviewer/state`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Origin: origin,
        "X-Phase1B-CSRF": initial.csrfToken,
        "If-Match": initial.etag,
      },
      body: JSON.stringify(draft),
    });
    assert.equal(saved.status, role.frame.status === "ACCEPTED" ? 200 : 400);
    if (role.frame.status !== "ACCEPTED") return;

    const reloaded = await (await fetch(`${origin}/__phase1b_review__/reviewer/state`)).json();
    assert.equal(reloaded.state.activeRoleId, "dark");
    assert.equal(reloaded.state.tutorialAcknowledged, true);
    assert.equal(reloaded.state.roles.dark.step, 4);
    assert.deepEqual(reloaded.state.roles.dark.zones.widths, WIDTHS);
    assert.equal(reloaded.summary.lockedCount, 0);

    // A stale ETag is refused instead of clobbering a newer draft.
    const stale = await fetch(`${origin}/__phase1b_review__/reviewer/state`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Origin: origin,
        "X-Phase1B-CSRF": initial.csrfToken,
        "If-Match": initial.etag,
      },
      body: JSON.stringify(draft),
    });
    assert.equal(stale.status, 412);

    // An illegal boundary order is refused over the wire as well.
    const illegal = structuredClone(reloaded.state);
    illegal.roles.dark.zones.widths = { sidewall: 0.2, strongRim: 0, shoulder: 0.1 };
    const rejected = await fetch(`${origin}/__phase1b_review__/reviewer/state`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Origin: origin,
        "X-Phase1B-CSRF": initial.csrfToken,
        "If-Match": reloaded.etag,
      },
      body: JSON.stringify(illegal),
    });
    assert.equal(rejected.status, 400);

    const annotationsAfter = createHash("sha256").update(await readFile(ANNOTATIONS)).digest("hex");
    assert.equal(annotationsAfter, annotationsBefore, "Reviewer Mode wrote the private annotation contract");
  } finally {
    await instance.close();
    await rm(statePath, { force: true });
  }
});
