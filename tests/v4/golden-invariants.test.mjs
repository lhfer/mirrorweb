import assert from "node:assert/strict";
import { mkdir, readFile, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { assetIdentitySha256, lockInvariantBlockers } from "../../scripts/v4/lib/golden.mjs";

const repoRoot = resolve(import.meta.dirname, "../..");
const calibration = JSON.parse(await readFile(resolve(repoRoot, "config/calibration.v4.json"), "utf8"));

function video(role, path, sha256) {
  return {
    role,
    path,
    sha256,
    bytes: 100,
    video: {
      codec: "h264",
      width: 100,
      height: 100,
      frameRate: { numerator: 30, denominator: 1 },
      frameCount: 30,
      durationSeconds: 1,
      pixelFormat: "yuv420p",
      colorRange: "tv",
      colorSpace: "bt709",
      colorTransfer: "bt709",
      colorPrimaries: "bt709",
      hasAudio: false,
    },
  };
}

function baseLock() {
  return {
    schemaVersion: 1,
    referenceSet: calibration.golden.referenceSet,
    private: true,
    assets: {
      targetVideo: video("frozen-target", "target.mp4", "a".repeat(64)),
      currentVideo: video("frozen-current-baseline", "current.mp4", "b".repeat(64)),
      referenceScreenshots: [{
        role: "target-annotated-roi",
        path: "target-annotated.png",
        sha256: "c".repeat(64),
        bytes: 100,
        width: 100,
        height: 100,
        comparisonUse: "annotation-only",
      }],
    },
    capture: {
      currentSourceCommit: calibration.baseline.sourceCommit,
      browser: { name: "Chrome", version: "1", channel: "stable" },
      gpu: { api: "webgpu", vendor: "vendor", architecture: "arch", description: "gpu" },
      viewport: { width: 100, height: 100 },
      dpr: 1,
    },
    inputScript: {
      path: calibration.golden.inputScript,
      sha256: "d".repeat(64),
    },
  };
}

function calibratedFor(lock) {
  return {
    ...calibration,
    golden: {
      ...calibration.golden,
      assetIdentitySha256: assetIdentitySha256(lock),
    },
  };
}

function codes(lock, calibrated = calibratedFor(lock)) {
  return lockInvariantBlockers(lock, calibrated).map((item) => item.code);
}

test("annotation-only screenshots can never make Golden READY", () => {
  const lock = baseLock();
  assert.deepEqual(codes(lock), ["CLEAN_PIXEL_GOLDEN_MISSING"]);
});

test("target and current cannot be the same frozen asset", () => {
  const lock = baseLock();
  lock.assets.currentVideo.path = lock.assets.targetVideo.path;
  lock.assets.currentVideo.sha256 = lock.assets.targetVideo.sha256;
  assert.ok(codes(lock).includes("TARGET_CURRENT_IDENTICAL"));
});

test("input script cannot escape or differ from the calibrated path", () => {
  const lock = baseLock();
  lock.inputScript.path = "../outside.json";
  assert.ok(codes(lock).includes("INPUT_SCRIPT_PATH_INVALID"));
});

test("changing a frozen asset invalidates the version-controlled identity anchor", () => {
  const lock = baseLock();
  const anchoredCalibration = calibratedFor(lock);
  lock.assets.targetVideo.sha256 = "e".repeat(64);
  assert.ok(codes(lock, anchoredCalibration).includes("GOLDEN_ASSET_IDENTITY_MISMATCH"));
});

test("an in-repository Golden directory must be ignored and untracked", async () => {
  const unsafe = resolve(repoRoot, "qa-v4/unsafe-golden-test");
  await mkdir(unsafe, { recursive: true });
  try {
    const result = spawnSync(process.execPath, [resolve(repoRoot, "scripts/v4/golden-manifest.mjs"), "--verify"], {
      cwd: repoRoot,
      env: { ...process.env, ILG_GOLDEN_DIR: unsafe },
      encoding: "utf8",
    });
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.deepEqual(report.blockers.map((item) => item.code), ["ILG_GOLDEN_DIR_NOT_PRIVATE"]);
  } finally {
    await rm(unsafe, { recursive: true, force: true });
  }
});
