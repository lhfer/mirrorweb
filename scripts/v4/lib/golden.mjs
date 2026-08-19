import { spawnSync } from "node:child_process";
import { access, mkdir, realpath, stat } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve, sep } from "node:path";
import { REPO_ROOT, blocker, execText, readJson, sha256File, sha256Value, writeJson } from "./common.mjs";

const READY = "READY";
const BLOCKED = "BLOCKED";

function parseRate(value) {
  const [numeratorText, denominatorText] = String(value ?? "0/1").split("/");
  const numerator = Number(numeratorText);
  const denominator = Number(denominatorText || 1);
  return { numerator, denominator, value: denominator ? numerator / denominator : 0 };
}

function runFfprobe(path) {
  const result = spawnSync("ffprobe", [
    "-v", "error",
    "-show_entries",
    "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames,pix_fmt,color_range,color_space,color_transfer,color_primaries",
    "-of", "json",
    path,
  ], { encoding: "utf8" });
  if (result.error || result.status !== 0) {
    const message = result.error?.message || result.stderr?.trim() || "ffprobe failed";
    throw new Error(message);
  }
  return JSON.parse(result.stdout);
}

function probeVideo(path) {
  const data = runFfprobe(path);
  const video = data.streams?.find((stream) => stream.codec_type === "video");
  if (!video) throw new Error("No video stream found");
  const frameRate = parseRate(video.avg_frame_rate || video.r_frame_rate);
  const durationSeconds = Number(data.format?.duration ?? 0);
  const encodedFrameCount = Number(video.nb_frames);
  return {
    codec: video.codec_name ?? null,
    width: Number(video.width ?? 0),
    height: Number(video.height ?? 0),
    frameRate: {
      numerator: frameRate.numerator,
      denominator: frameRate.denominator,
    },
    frameCount: Number.isFinite(encodedFrameCount) && encodedFrameCount > 0
      ? encodedFrameCount
      : Math.round(durationSeconds * frameRate.value),
    durationSeconds,
    pixelFormat: video.pix_fmt ?? null,
    colorRange: video.color_range ?? null,
    colorSpace: video.color_space ?? null,
    colorTransfer: video.color_transfer ?? null,
    colorPrimaries: video.color_primaries ?? null,
    hasAudio: Boolean(data.streams?.some((stream) => stream.codec_type === "audio")),
  };
}

function probeImage(path) {
  const data = runFfprobe(path);
  const image = data.streams?.find((stream) => stream.codec_type === "video");
  if (!image) throw new Error("No image stream found");
  return {
    codec: image.codec_name ?? null,
    width: Number(image.width ?? 0),
    height: Number(image.height ?? 0),
    pixelFormat: image.pix_fmt ?? null,
    colorSpace: image.color_space ?? null,
  };
}

function captureFromEnv(env) {
  const viewportMatch = env.ILG_CAPTURE_VIEWPORT?.match(/^(\d+)x(\d+)$/i);
  return {
    currentSourceCommit: env.ILG_CAPTURE_COMMIT ?? null,
    browser: {
      name: env.ILG_CAPTURE_BROWSER ?? null,
      version: env.ILG_CAPTURE_BROWSER_VERSION ?? null,
      channel: env.ILG_CAPTURE_BROWSER_CHANNEL ?? null,
    },
    gpu: {
      api: env.ILG_CAPTURE_GPU_API ?? null,
      vendor: env.ILG_CAPTURE_GPU_VENDOR ?? null,
      architecture: env.ILG_CAPTURE_GPU_ARCHITECTURE ?? null,
      description: env.ILG_CAPTURE_GPU_DESCRIPTION ?? null,
    },
    viewport: {
      width: viewportMatch ? Number(viewportMatch[1]) : null,
      height: viewportMatch ? Number(viewportMatch[2]) : null,
    },
    dpr: env.ILG_CAPTURE_DPR ? Number(env.ILG_CAPTURE_DPR) : null,
  };
}

function captureBlockers(capture) {
  const blockers = [];
  if (!/^[0-9a-f]{40}$/i.test(capture.currentSourceCommit ?? "")) {
    blockers.push(blocker("CAPTURE_COMMIT_UNVERIFIED", "The source commit used by the current baseline capture is required"));
  }
  if (!capture.browser?.name || !capture.browser?.version) {
    blockers.push(blocker("CAPTURE_BROWSER_UNVERIFIED", "Capture browser name and version are required"));
  }
  if (!capture.gpu?.api || !capture.gpu?.vendor || !capture.gpu?.architecture || !capture.gpu?.description) {
    blockers.push(blocker("CAPTURE_GPU_UNVERIFIED", "Capture GPU API, vendor, architecture, and description are required"));
  }
  if (!(capture.viewport?.width > 0) || !(capture.viewport?.height > 0)) {
    blockers.push(blocker("CAPTURE_VIEWPORT_UNVERIFIED", "Capture CSS viewport is required and cannot be inferred from encoded pixels"));
  }
  if (!(capture.dpr > 0)) {
    blockers.push(blocker("CAPTURE_DPR_UNVERIFIED", "Capture DPR is required and cannot be inferred from encoded pixels"));
  }
  return blockers;
}

async function goldenRootFromEnv(env) {
  if (!env.ILG_GOLDEN_DIR?.trim()) {
    return { blockers: [blocker("ILG_GOLDEN_DIR_UNSET", "ILG_GOLDEN_DIR is required")], root: null };
  }
  try {
    const root = await realpath(resolve(REPO_ROOT, env.ILG_GOLDEN_DIR));
    const info = await stat(root);
    if (!info.isDirectory()) {
      return { blockers: [blocker("ILG_GOLDEN_DIR_INVALID", "ILG_GOLDEN_DIR is not a directory")], root: null };
    }
    const repoRelative = relative(REPO_ROOT, root);
    const insideRepo = repoRelative === "" || (repoRelative !== ".." && !repoRelative.startsWith(`..${sep}`) && !isAbsolute(repoRelative));
    if (insideRepo) {
      const ignored = spawnSync("git", ["check-ignore", "-q", "--", repoRelative || "."], {
        cwd: REPO_ROOT,
        stdio: "ignore",
      }).status === 0;
      const tracked = execText("git", ["ls-files", "--", repoRelative || "."]);
      if (!ignored || tracked) {
        return {
          blockers: [blocker("ILG_GOLDEN_DIR_NOT_PRIVATE", "A Golden directory inside the repository must be ignored and contain no tracked files")],
          root: null,
        };
      }
    }
    return { blockers: [], root };
  } catch (error) {
    return {
      blockers: [blocker("ILG_GOLDEN_DIR_MISSING", "ILG_GOLDEN_DIR does not exist", error instanceof Error ? error.message : String(error))],
      root: null,
    };
  }
}

async function resolveGoldenAsset(root, relativePath) {
  if (!relativePath || isAbsolute(relativePath)) throw new Error("Golden asset paths must be relative");
  const path = await realpath(resolve(root, relativePath));
  if (path !== root && !path.startsWith(`${root}${sep}`)) throw new Error("Golden asset resolves outside ILG_GOLDEN_DIR");
  const info = await stat(path);
  if (!info.isFile()) throw new Error("Golden asset is not a regular file");
  return { path, info };
}

async function resolveRepositoryFile(relativePath) {
  if (!relativePath || isAbsolute(relativePath)) throw new Error("Repository file path must be relative");
  const path = await realpath(resolve(REPO_ROOT, relativePath));
  if (path !== REPO_ROOT && !path.startsWith(`${REPO_ROOT}${sep}`)) throw new Error("Repository file path escapes the repository");
  const info = await stat(path);
  if (!info.isFile()) throw new Error("Repository path is not a regular file");
  return path;
}

async function inspectVideo(root, role, relativePath, sourceAlias = undefined) {
  const { path, info } = await resolveGoldenAsset(root, relativePath);
  return {
    role,
    path: relative(root, path),
    ...(sourceAlias ? { sourceAlias } : {}),
    sha256: await sha256File(path),
    bytes: info.size,
    video: probeVideo(path),
  };
}

async function inspectScreenshot(root, role, relativePath, comparisonUse) {
  const { path, info } = await resolveGoldenAsset(root, relativePath);
  return {
    role,
    path: relative(root, path),
    sha256: await sha256File(path),
    bytes: info.size,
    ...probeImage(path),
    comparisonUse,
  };
}

async function repositoryState() {
  const commit = execText("git", ["rev-parse", "HEAD"]);
  const worktreeStatus = execText("git", ["status", "--porcelain=v2", "--untracked-files=all"]);
  return {
    branch: execText("git", ["rev-parse", "--abbrev-ref", "HEAD"]),
    commit,
    tree: execText("git", ["rev-parse", "HEAD^{tree}"]),
    dirty: Boolean(worktreeStatus),
    worktreeFingerprint: sha256Value(worktreeStatus),
  };
}

function compareVideo(expected, actual, issues, prefix) {
  const exactFields = ["codec", "width", "height", "frameCount", "pixelFormat", "colorRange", "colorSpace", "colorTransfer", "colorPrimaries", "hasAudio"];
  for (const field of exactFields) {
    if (expected[field] !== actual[field]) {
      issues.push(blocker(`${prefix}_${field.toUpperCase()}_MISMATCH`, `${prefix} ${field} changed`, { expected: expected[field], actual: actual[field] }));
    }
  }
  if (expected.frameRate?.numerator !== actual.frameRate?.numerator || expected.frameRate?.denominator !== actual.frameRate?.denominator) {
    issues.push(blocker(`${prefix}_FRAME_RATE_MISMATCH`, `${prefix} frame rate changed`, { expected: expected.frameRate, actual: actual.frameRate }));
  }
  if (Math.abs(Number(expected.durationSeconds) - Number(actual.durationSeconds)) > 0.001) {
    issues.push(blocker(`${prefix}_DURATION_MISMATCH`, `${prefix} duration changed`, { expected: expected.durationSeconds, actual: actual.durationSeconds }));
  }
}

async function verifyAsset(root, expected, kind, issues, prefix) {
  try {
    const actual = kind === "video"
      ? await inspectVideo(root, expected.role, expected.path, expected.sourceAlias)
      : await inspectScreenshot(root, expected.role, expected.path, expected.comparisonUse);
    if (expected.sha256 !== actual.sha256) {
      issues.push(blocker(`${prefix}_HASH_MISMATCH`, `${prefix} SHA-256 changed`, { expected: expected.sha256, actual: actual.sha256 }));
    }
    if (expected.bytes !== actual.bytes) {
      issues.push(blocker(`${prefix}_SIZE_MISMATCH`, `${prefix} byte size changed`, { expected: expected.bytes, actual: actual.bytes }));
    }
    if (kind === "video") compareVideo(expected.video, actual.video, issues, prefix);
    if (kind === "image" && (expected.width !== actual.width || expected.height !== actual.height)) {
      issues.push(blocker(`${prefix}_DIMENSIONS_MISMATCH`, `${prefix} dimensions changed`, {
        expected: { width: expected.width, height: expected.height },
        actual: { width: actual.width, height: actual.height },
      }));
    }
    return actual;
  } catch (error) {
    issues.push(blocker(`${prefix}_UNREADABLE`, `${prefix} cannot be verified`, error instanceof Error ? error.message : String(error)));
    return null;
  }
}

export function assetIdentity(lock) {
  return {
    schemaVersion: lock.schemaVersion,
    referenceSet: lock.referenceSet,
    private: lock.private,
    assets: lock.assets,
    inputScript: lock.inputScript,
  };
}

export function assetIdentitySha256(lock) {
  return sha256Value(assetIdentity(lock));
}

export function lockInvariantBlockers(lock, calibration) {
  const issues = [];
  if (lock.schemaVersion !== 1) issues.push(blocker("LOCK_SCHEMA_UNSUPPORTED", "manifest.lock.json schemaVersion must be 1"));
  if (lock.referenceSet !== calibration.golden.referenceSet) {
    issues.push(blocker("REFERENCE_SET_MISMATCH", "Golden referenceSet does not match calibration", { expected: calibration.golden.referenceSet, actual: lock.referenceSet }));
  }
  if (lock.private !== true) issues.push(blocker("LOCK_NOT_PRIVATE", "Golden lock must declare private: true"));
  if (!lock.assets?.targetVideo) issues.push(blocker("TARGET_VIDEO_MISSING", "Frozen target video is missing from the lock"));
  if (!lock.assets?.currentVideo) issues.push(blocker("CURRENT_VIDEO_MISSING", "Frozen current video is missing from the lock"));
  if (!Array.isArray(lock.assets?.referenceScreenshots) || lock.assets.referenceScreenshots.length === 0) {
    issues.push(blocker("REFERENCE_SCREENSHOT_MISSING", "At least one reference screenshot is required"));
  }
  if (lock.assets?.targetVideo?.role !== "frozen-target") issues.push(blocker("TARGET_VIDEO_ROLE_INVALID", "Target video role must be frozen-target"));
  if (lock.assets?.currentVideo?.role !== "frozen-current-baseline") issues.push(blocker("CURRENT_VIDEO_ROLE_INVALID", "Current video role must be frozen-current-baseline"));
  const shaPattern = /^[0-9a-f]{64}$/i;
  for (const [label, asset] of [["TARGET_VIDEO", lock.assets?.targetVideo], ["CURRENT_VIDEO", lock.assets?.currentVideo]]) {
    if (!asset) continue;
    if (!asset.path || isAbsolute(asset.path)) issues.push(blocker(`${label}_PATH_INVALID`, `${label} path must be relative`));
    if (!(asset.bytes > 0)) issues.push(blocker(`${label}_SIZE_INVALID`, `${label} byte size must be positive`));
    if (!asset.video?.codec || !(asset.video?.width > 0) || !(asset.video?.height > 0)
      || !(asset.video?.frameRate?.numerator > 0) || !(asset.video?.frameRate?.denominator > 0)
      || !(asset.video?.durationSeconds > 0)) {
      issues.push(blocker(`${label}_METADATA_INVALID`, `${label} ffprobe metadata is incomplete`));
    }
  }
  if (!shaPattern.test(lock.assets?.targetVideo?.sha256 ?? "")) issues.push(blocker("TARGET_VIDEO_HASH_INVALID", "Target video SHA-256 is missing or malformed"));
  if (!shaPattern.test(lock.assets?.currentVideo?.sha256 ?? "")) issues.push(blocker("CURRENT_VIDEO_HASH_INVALID", "Current video SHA-256 is missing or malformed"));
  if (lock.assets?.targetVideo?.path === lock.assets?.currentVideo?.path || lock.assets?.targetVideo?.sha256 === lock.assets?.currentVideo?.sha256) {
    issues.push(blocker("TARGET_CURRENT_IDENTICAL", "Target and current video must be distinct frozen assets"));
  }
  for (const [index, screenshot] of (lock.assets?.referenceScreenshots ?? []).entries()) {
    if (!shaPattern.test(screenshot.sha256 ?? "")) issues.push(blocker(`REFERENCE_SCREENSHOT_${index}_HASH_INVALID`, "Reference screenshot SHA-256 is missing or malformed"));
    if (!screenshot.path || isAbsolute(screenshot.path)) issues.push(blocker(`REFERENCE_SCREENSHOT_${index}_PATH_INVALID`, "Reference screenshot path must be relative"));
    if (!(screenshot.bytes > 0) || !(screenshot.width > 0) || !(screenshot.height > 0)) issues.push(blocker(`REFERENCE_SCREENSHOT_${index}_METADATA_INVALID`, "Reference screenshot metadata is incomplete"));
    if (!["annotation-only", "pixel-golden"].includes(screenshot.comparisonUse)) issues.push(blocker(`REFERENCE_SCREENSHOT_${index}_USE_INVALID`, "Reference screenshot comparisonUse is invalid"));
  }
  const hasPixelGolden = (lock.assets?.referenceScreenshots ?? []).some((screenshot) => screenshot.comparisonUse === "pixel-golden");
  if (!hasPixelGolden) {
    issues.push(blocker("CLEAN_PIXEL_GOLDEN_MISSING", "An annotation-only screenshot cannot satisfy pixel comparison; add a clean pixel-golden or a separately specified mask workflow"));
  }
  if (!lock.inputScript?.path || !lock.inputScript?.sha256) {
    issues.push(blocker("INPUT_SCRIPT_MISSING", "Deterministic input script and SHA-256 are required"));
  } else {
    if (lock.inputScript.path !== calibration.golden.inputScript || isAbsolute(lock.inputScript.path)) {
      issues.push(blocker("INPUT_SCRIPT_PATH_INVALID", "Input script path must equal the calibrated repository path", { expected: calibration.golden.inputScript, actual: lock.inputScript.path }));
    }
    if (!shaPattern.test(lock.inputScript.sha256)) issues.push(blocker("INPUT_SCRIPT_HASH_INVALID", "Input script SHA-256 is malformed"));
  }
  if (lock.capture?.currentSourceCommit && lock.capture.currentSourceCommit !== calibration.baseline.sourceCommit) {
    issues.push(blocker("CAPTURE_COMMIT_MISMATCH", "Current baseline capture commit does not match the frozen V3 source commit", { expected: calibration.baseline.sourceCommit, actual: lock.capture.currentSourceCommit }));
  }
  const identity = assetIdentitySha256(lock);
  if (identity !== calibration.golden.assetIdentitySha256) {
    issues.push(blocker("GOLDEN_ASSET_IDENTITY_MISMATCH", "Golden asset identity is not anchored by calibration", { expected: calibration.golden.assetIdentitySha256, actual: identity }));
  }
  return issues;
}

export async function createGoldenLock({ env = process.env } = {}) {
  const startedAt = new Date().toISOString();
  const rootResult = await goldenRootFromEnv(env);
  if (!rootResult.root) {
    return { schemaVersion: 1, status: BLOCKED, generatedAt: startedAt, blockers: rootResult.blockers };
  }
  const root = rootResult.root;
  const lockPath = resolve(root, "manifest.lock.json");
  try {
    await access(lockPath);
    return {
      schemaVersion: 1,
      status: BLOCKED,
      generatedAt: startedAt,
      blockers: [blocker("GOLDEN_LOCK_EXISTS", "manifest.lock.json already exists and will not be overwritten")],
    };
  } catch {
    // Expected for first creation.
  }

  try {
    const calibration = await readJson(resolve(REPO_ROOT, "config/calibration.v4.json"));
    const inputPath = resolve(REPO_ROOT, "qa-v4/input-sequence.v4.json");
    const capture = captureFromEnv(env);
    const lock = {
      schemaVersion: 1,
      referenceSet: calibration.golden.referenceSet,
      private: true,
      createdAt: startedAt,
      assets: {
        targetVideo: await inspectVideo(root, "frozen-target", env.ILG_TARGET_VIDEO ?? "target.mp4", "第二次案例视频(1).mp4"),
        currentVideo: await inspectVideo(root, "frozen-current-baseline", env.ILG_CURRENT_VIDEO ?? "current.mp4"),
        referenceScreenshots: [
          await inspectScreenshot(root, "target-annotated-roi", env.ILG_TARGET_SCREENSHOT ?? "target-annotated.png", "annotation-only"),
        ],
      },
      capture,
      inputScript: {
        path: "qa-v4/input-sequence.v4.json",
        sha256: await sha256File(inputPath),
      },
    };
    await writeJson(lockPath, lock, { flag: "wx" });
    const blockers = captureBlockers(capture);
    return {
      schemaVersion: 1,
      status: blockers.length ? BLOCKED : READY,
      generatedAt: startedAt,
      lockPath,
      blockers,
      assetIdentitySha256: assetIdentitySha256(lock),
      assets: lock.assets,
    };
  } catch (error) {
    return {
      schemaVersion: 1,
      status: BLOCKED,
      generatedAt: startedAt,
      blockers: [blocker("GOLDEN_LOCK_CREATION_FAILED", "Golden lock could not be created", error instanceof Error ? error.message : String(error))],
    };
  }
}

export async function verifyGolden({ env = process.env } = {}) {
  const generatedAt = new Date().toISOString();
  const rootResult = await goldenRootFromEnv(env);
  if (!rootResult.root) {
    return { schemaVersion: 1, status: BLOCKED, generatedAt, blockers: rootResult.blockers, comparisonRan: false };
  }
  const root = rootResult.root;
  const lockPath = resolve(root, "manifest.lock.json");
  let lock;
  let calibration;
  try {
    lock = await readJson(lockPath);
    calibration = await readJson(resolve(REPO_ROOT, "config/calibration.v4.json"));
  } catch (error) {
    return {
      schemaVersion: 1,
      status: BLOCKED,
      generatedAt,
      blockers: [blocker("GOLDEN_LOCK_MISSING", "manifest.lock.json is missing or unreadable", error instanceof Error ? error.message : String(error))],
      comparisonRan: false,
    };
  }

  const before = await repositoryState();
  const blockers = [...lockInvariantBlockers(lock, calibration), ...captureBlockers(lock.capture ?? {})];
  const observed = { targetVideo: null, currentVideo: null, referenceScreenshots: [] };
  if (lock.assets?.targetVideo) observed.targetVideo = await verifyAsset(root, lock.assets.targetVideo, "video", blockers, "TARGET_VIDEO");
  if (lock.assets?.currentVideo) observed.currentVideo = await verifyAsset(root, lock.assets.currentVideo, "video", blockers, "CURRENT_VIDEO");
  if (observed.targetVideo?.sha256 && observed.targetVideo.sha256 === observed.currentVideo?.sha256) {
    blockers.push(blocker("TARGET_CURRENT_OBSERVED_IDENTICAL", "Observed target and current video resolve to identical content"));
  }
  for (let i = 0; i < (lock.assets?.referenceScreenshots?.length ?? 0); i += 1) {
    observed.referenceScreenshots.push(await verifyAsset(root, lock.assets.referenceScreenshots[i], "image", blockers, `REFERENCE_SCREENSHOT_${i}`));
  }

  if (lock.inputScript?.path && lock.inputScript?.sha256) {
    try {
      const inputPath = await resolveRepositoryFile(lock.inputScript.path);
      const actualInputHash = await sha256File(inputPath);
      if (actualInputHash !== lock.inputScript.sha256) {
        blockers.push(blocker("INPUT_SCRIPT_HASH_MISMATCH", "Deterministic input script changed", { expected: lock.inputScript.sha256, actual: actualInputHash }));
      }
    } catch (error) {
      blockers.push(blocker("INPUT_SCRIPT_UNREADABLE", "Deterministic input script cannot be read", error instanceof Error ? error.message : String(error)));
    }
  }

  if (before.dirty) blockers.push(blocker("TEST_WORKTREE_DIRTY", "Golden QA requires a clean tested commit"));
  const after = await repositoryState();
  if (after.dirty) blockers.push(blocker("TEST_WORKTREE_DIRTY_AFTER", "Working tree became dirty during Golden verification"));
  if (before.worktreeFingerprint !== after.worktreeFingerprint) blockers.push(blocker("TEST_WORKTREE_CHANGED", "Working tree state changed during Golden verification"));
  if (before.commit !== after.commit) blockers.push(blocker("TEST_COMMIT_CHANGED", "HEAD changed during Golden verification"));
  if (before.tree !== after.tree) blockers.push(blocker("TEST_TREE_CHANGED", "Git tree changed during Golden verification"));

  return {
    schemaVersion: 1,
    status: blockers.length ? BLOCKED : READY,
    generatedAt,
    goldenDirectory: root,
    lockPath,
    repository: after,
    capture: lock.capture ?? null,
    inputScript: lock.inputScript ?? null,
    observed,
    blockers,
    comparisonRan: false,
  };
}

export async function writeGoldenResult(path, result) {
  await mkdir(dirname(path), { recursive: true });
  await writeJson(path, result);
}

export const GOLDEN_STATUS = { READY, BLOCKED };
