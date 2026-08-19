import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { access, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const REVIEW_ROOT = path.join(REPO_ROOT, "qa-v4/review");

async function source(relativePath) {
  return readFile(path.join(REPO_ROOT, relativePath), "utf8");
}

async function sha256(file) {
  return createHash("sha256").update(await readFile(file)).digest("hex");
}

test("Phase 1B capture is clean-source and dist-preview bound", async () => {
  const capture = await source("scripts/v4/capture-optics-lab.mjs");
  assert.match(capture, /optics-lab-capture-phase1b-v2/);
  assert.match(capture, /DEFAULT_URL\s*=\s*["']http:\/\/127\.0\.0\.1:5280\/glass-lab-v4\?qa=1["']/);
  assert.doesNotMatch(capture, /glass-lab-v4\/\?qa=1/);
  for (const contract of [
    "headTree",
    "dirtyRepository",
    "dirtyWithinRuntimeScope",
    "sourceIdentityStart",
    "sourceIdentityEnd",
    "sourceIdentityCheck",
    "distTreeSha256",
    "development-resource",
    "external-origin",
    "non-2xx-response",
    "served-resource-dist-hash-mismatch",
  ]) {
    assert.ok(capture.includes(contract), `missing identity contract ${contract}`);
  }
  assert.match(capture, /setShellMode/);
  assert.match(capture, /setPose/);
  assert.match(capture, /\["additive",\s*"energy-controlled",\s*"off"\]/);
  assert.match(capture, /debug:\s*"optical-zones"/);
  assert.match(capture, /for \(const shellMode of \["additive", "energy-controlled"\]\)/);
  assert.match(capture, /for \(const view of \["reflection", "beauty"\]\)/);
  assert.ok(capture.includes("`phase1b-shell-${shellMode}-pointer-${pointer.id}`"));
  assert.ok(capture.includes("`phase1b-shell-${shellMode}-beauty-pointer-${pointer.id}`"));
  assert.match(capture, /role:\s*"phase1b-reflection-shell-ab-pointer"/);
  assert.match(capture, /family:\s*"reflection-shell-ab-pointer"/);
  assert.match(capture, /experimentVariant:\s*specification\.experimentVariant/);
  assert.match(capture, /for \(const pose of \["front", "left", "right"\]\)/);
  assert.match(capture, /id:\s*`phase1b-pose-\$\{pose\}`/);
  assert.match(capture, /id:\s*`phase1b-optical-zones-\$\{pose\}`/);
  assert.match(capture, /family:\s*"optical-zones-pose"/);
  assert.match(capture, /id:\s*`phase1b-sidewall-\$\{pose\}-\$\{pattern\}`/);
  assert.match(capture, /role:\s*"phase1b-sidewall-lines"/);
  assert.match(capture, /family:\s*"sidewall-content-compression"/);
  for (const reviewName of [
    "v3-v4-split-checker.png",
    "v4-checker.png",
    "v4-horizontal-lines.png",
    "v4-vertical-lines.png",
    "v4-white.png",
    "v4-black.png",
    "v4-high-frequency.png",
    "v4-low-frequency.png",
    "v4-reflection-left.png",
    "v4-reflection-center.png",
    "v4-reflection-right.png",
    "v4-edge-mask.png",
    "v4-refraction-offset.png",
    "v4-dispersion.png",
  ]) {
    assert.ok(capture.includes(reviewName), `capture matrix is missing ${reviewName}`);
  }
  assert.match(capture, /shellMode:\s*"energy-controlled"[\s\S]{0,120}pose:\s*"front"[\s\S]{0,120}pointer:\s*\[0,\s*0\]/);
});

test("private review output is ignored and the generator fails closed elsewhere", async () => {
  const ignore = await source(".gitignore");
  const packageJson = JSON.parse(await source("package.json"));
  const generator = await source("scripts/v4/build-phase1b-review.py");
  assert.match(ignore, /^qa-v4\/review\/$/m);
  assert.match(packageJson.scripts["v4:preview:phase1b"], /vite preview[\s\S]*--port 5281/);
  assert.match(packageJson.scripts["v4:capture:phase1b"], /127\.0\.0\.1:5281\/glass-lab-v4\?qa=1/);
  assert.equal(packageJson.scripts["v4:review:phase1b"], "python3 scripts/v4/build-phase1b-review.py");
  assert.match(generator, /check-ignore/);
  assert.match(generator, /ls-files/);
  assert.match(generator, /Refusing tracked review files/);
  assert.match(generator, /absolutePathsStored/);
  assert.match(generator, /privatePixelsCommitted/);

  const sentinel = path.join("qa-v4/results", `.phase1b-unignored-${process.pid}`);
  const ignored = spawnSync("git", ["check-ignore", "-q", "--no-index", `${sentinel}/.privacy-sentinel`], {
    cwd: REPO_ROOT,
  });
  assert.notEqual(ignored.status, 0, "test sentinel unexpectedly became ignored");
  const blocked = spawnSync("python3", [
    "scripts/v4/build-phase1b-review.py",
    "--input",
    "qa-v4/results/optics-lab-foundation.json",
    "--output-dir",
    sentinel,
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(blocked.status, 2, blocked.stderr);
  assert.match(blocked.stdout, /not ignored|must remain inside qa-v4\/review/i);
});

test("review generator emits fourteen sanitized PNGs, contact sheet, MP4, and relative manifest", async (t) => {
  const prerequisites = spawnSync("python3", ["-c", "import PIL"], { cwd: REPO_ROOT });
  const ffmpeg = spawnSync("ffmpeg", ["-version"], { cwd: REPO_ROOT });
  const ffprobe = spawnSync("ffprobe", ["-version"], { cwd: REPO_ROOT });
  if (prerequisites.status !== 0 || ffmpeg.status !== 0 || ffprobe.status !== 0) {
    t.skip("Pillow, ffmpeg, and ffprobe are required for the integration test");
    return;
  }

  await mkdir(REVIEW_ROOT, { recursive: true });
  const temporaryRoot = await mkdtemp(path.join(REVIEW_ROOT, ".phase1b-test-"));
  t.after(async () => {
    await rm(temporaryRoot, { recursive: true, force: true });
  });
  const sourcePng = path.join(temporaryRoot, "source.png");
  const image = spawnSync("python3", [
    "-c",
    "from PIL import Image; Image.new('RGB',(32,24),(31,127,223)).save(__import__('sys').argv[1], format='PNG')",
    sourcePng,
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(image.status, 0, image.stderr);

  const sourceVideo = path.join(temporaryRoot, "source.webm");
  const video = spawnSync("ffmpeg", [
    "-hide_banner", "-loglevel", "error", "-y",
    "-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=0.3",
    "-an", "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", sourceVideo,
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(video.status, 0, video.stderr);

  const captureIds = [
    ["split-checker", "v3-v4-split-checker.png"],
    ["v4-checker", "v4-checker.png"],
    ["v4-horizontal-lines", "v4-horizontal-lines.png"],
    ["v4-vertical-lines", "v4-vertical-lines.png"],
    ["v4-white", "v4-white.png"],
    ["v4-black", "v4-black.png"],
    ["v4-high-frequency-photo", "v4-high-frequency.png"],
    ["v4-low-frequency-flat", "v4-low-frequency.png"],
    ["phase1b-reflection-left", "v4-reflection-left.png"],
    ["phase1b-reflection-center", "v4-reflection-center.png"],
    ["phase1b-reflection-right", "v4-reflection-right.png"],
    ["edge-mask-black", "v4-edge-mask.png"],
    ["refraction-offset-checker", "v4-refraction-offset.png"],
    ["dispersion-checker", "v4-dispersion.png"],
  ];
  const sourcePngSha = await sha256(sourcePng);
  const relativeSourcePng = path.relative(REPO_ROOT, sourcePng).split(path.sep).join("/");
  const relativeSourceVideo = path.relative(REPO_ROOT, sourceVideo).split(path.sep).join("/");
  const manifest = {
    status: "CAPTURED",
    sourceIdentity: {
      head: "a".repeat(40), headTree: "b".repeat(40), branch: "test",
      dirtyRepository: false, dirtyWithinRuntimeScope: false, runtimeSourceSetSha256: "c".repeat(64),
    },
    sourceIdentityEnd: {
      head: "a".repeat(40), headTree: "b".repeat(40),
      dirtyRepository: false, dirtyWithinRuntimeScope: false, runtimeSourceSetSha256: "c".repeat(64),
    },
    sourceIdentityCheck: { passed: true, sameIdentity: true, cleanAtStart: true, cleanAtEnd: true },
    previewIdentity: { passed: true, expectedOrigin: "http://127.0.0.1:5281", violations: [] },
    captures: captureIds.map(([id, reviewName]) => ({
      id,
      role: "test",
      reviewName,
      file: relativeSourcePng,
      sha256: sourcePngSha,
      shellMode: "energy-controlled",
      pose: "front",
      pointer: id.endsWith("-left") ? [-0.85, 0] : id.endsWith("-right") ? [0.85, 0] : [0, 0],
    })),
    sessionVideo: {
      role: "test-session", file: relativeSourceVideo, sha256: await sha256(sourceVideo),
    },
  };
  const captureManifest = path.join(temporaryRoot, "capture.local.json");
  await writeFile(captureManifest, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  const outputDir = path.join(temporaryRoot, "bundle");
  const generated = spawnSync("python3", [
    "scripts/v4/build-phase1b-review.py",
    "--input", captureManifest,
    "--output-dir", outputDir,
  ], { cwd: REPO_ROOT, encoding: "utf8", maxBuffer: 4 * 1024 * 1024 });
  assert.equal(generated.status, 0, `${generated.stdout}\n${generated.stderr}`);
  assert.equal(JSON.parse(generated.stdout).pngCount, 14);

  for (const [, outputName] of captureIds) await access(path.join(outputDir, outputName));
  await access(path.join(outputDir, "phase-1b-contact-sheet.jpg"));
  await access(path.join(outputDir, "phase-1b-session.mp4"));
  const localManifestPath = path.join(outputDir, "review-manifest.local.json");
  const localManifestSource = await readFile(localManifestPath, "utf8");
  const localManifest = JSON.parse(localManifestSource);
  assert.equal(localManifest.pngCount, 14);
  assert.equal(localManifest.privacy.absolutePathsStored, false);
  assert.equal(localManifest.privacy.privatePixelsCommitted, false);
  assert.match(localManifest.bundleSha256, /^[a-f0-9]{64}$/);
  assert.ok(!localManifestSource.includes(REPO_ROOT), "local manifest leaked an absolute repository path");
  assert.equal(localManifest.contactSheet.layout.columns, 4);
  assert.equal(localManifest.contactSheet.layout.rows, 4);
  assert.equal(localManifest.sessionVideo.codec, "h264");
  assert.equal(localManifest.sessionVideo.pixelFormat, "yuv420p");
});
