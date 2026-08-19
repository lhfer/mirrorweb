import { spawnSync } from "node:child_process";
import { readFile, readdir } from "node:fs/promises";
import { isDeepStrictEqual } from "node:util";
import { resolve } from "node:path";
import ts from "typescript";
import { REPO_ROOT, execText, readJson, sha256File, stable } from "./common.mjs";

function literalValue(node) {
  if (ts.isNumericLiteral(node)) return Number(node.text);
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (node.kind === ts.SyntaxKind.NullKeyword) return null;
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.MinusToken) {
    return -Number(literalValue(node.operand));
  }
  if (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isSatisfiesExpression(node)) {
    return literalValue(node.expression);
  }
  if (ts.isArrayLiteralExpression(node)) return node.elements.map(literalValue);
  if (ts.isObjectLiteralExpression(node)) {
    const value = {};
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) throw new Error("Only literal property assignments are supported");
      const key = ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)
        ? property.name.text
        : property.name.getText();
      value[key] = literalValue(property.initializer);
    }
    return value;
  }
  throw new Error(`Unsupported config syntax: ${ts.SyntaxKind[node.kind]}`);
}

async function exportedConst(path, name) {
  const source = await readFile(path, "utf8");
  const file = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  for (const statement of file.statements) {
    if (!ts.isVariableStatement(statement)) continue;
    if (!statement.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.ExportKeyword)) continue;
    for (const declaration of statement.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.name.text === name && declaration.initializer) {
        return literalValue(declaration.initializer);
      }
    }
  }
  throw new Error(`Exported const ${name} not found in ${path}`);
}

function expectedDocContract(calibration) {
  const v3 = calibration.baseline.v3;
  return {
    baselineSourceCommit: calibration.baseline.sourceCommit,
    optics: {
      currentVersion: v3.opticsMaterial.version,
      materialClass: v3.opticsMaterial.materialClass,
      materialSource: v3.opticsMaterial.source,
      materialSha256: v3.opticsMaterial.sourceSha256,
    },
    pool: {
      cols: v3.grid.cols,
      rows: v3.grid.rows,
      slots: v3.grid.slots,
    },
    motion: v3.motion.values,
    golden: {
      directoryEnv: calibration.golden.directoryEnv,
      missingPolicy: calibration.golden.missingPolicy,
    },
    v4: {
      optics: calibration.v4.optics.status,
      motionFit: calibration.v4.motionFit.status,
      gridRingBuffer: calibration.v4.gridRingBuffer.status,
    },
  };
}

async function readDocContract(path) {
  const source = await readFile(path, "utf8");
  const match = source.match(/<!-- V4_CONTRACT_START -->\s*```json\s*([\s\S]*?)\s*```\s*<!-- V4_CONTRACT_END -->/);
  if (!match) throw new Error("V4 machine-readable documentation contract is missing");
  return JSON.parse(match[1]);
}

function isIgnored(path) {
  const result = spawnSync("git", ["check-ignore", "-q", "--", path], {
    cwd: REPO_ROOT,
    stdio: "ignore",
  });
  return result.status === 0;
}

function addCheck(checks, id, passed, expected, actual) {
  checks.push({ id, status: passed ? "PASSED" : "FAILED", expected, actual });
}

export async function runSourceContract() {
  const calibrationPath = resolve(REPO_ROOT, "config/calibration.v4.json");
  const calibration = await readJson(calibrationPath);
  const checks = [];
  const configPath = resolve(REPO_ROOT, "src/config.ts");
  const motion = await exportedConst(configPath, "MOTION");
  const grid = await exportedConst(configPath, "GRID");

  const currentBranch = execText("git", ["rev-parse", "--abbrev-ref", "HEAD"]);
  addCheck(checks, "V4_BRANCH_MATCHES_CONFIG", currentBranch === calibration.baseline.branch, calibration.baseline.branch, currentBranch);
  const ancestor = spawnSync("git", ["merge-base", "--is-ancestor", calibration.baseline.sourceCommit, "HEAD"], {
    cwd: REPO_ROOT,
    stdio: "ignore",
  }).status === 0;
  addCheck(checks, "BASELINE_COMMIT_IS_ANCESTOR", ancestor, true, ancestor);
  const protectedPaths = [
    "src",
    "public",
    "index.html",
    "glass-lab.html",
    "vite.config.ts",
    "playwright.config.ts",
    "tsconfig.json",
    "package-lock.json",
  ];
  const protectedDiff = execText("git", ["diff", "--name-only", calibration.baseline.sourceCommit, "--", ...protectedPaths])
    .split("\n")
    .filter(Boolean);
  addCheck(checks, "PHASE0_RUNTIME_PATHS_UNCHANGED", protectedDiff.length === 0, [], protectedDiff);

  addCheck(
    checks,
    "MOTION_MATCHES_CONFIG",
    isDeepStrictEqual(stable(motion), stable(calibration.baseline.v3.motion.values)),
    calibration.baseline.v3.motion.values,
    motion,
  );
  addCheck(
    checks,
    "POOL_MATCHES_CONFIG",
    grid.cols === calibration.baseline.v3.grid.cols
      && grid.rows === calibration.baseline.v3.grid.rows
      && grid.cols * grid.rows === calibration.baseline.v3.grid.slots,
    calibration.baseline.v3.grid,
    { cols: grid.cols, rows: grid.rows, slots: grid.cols * grid.rows },
  );

  const fingerprints = [
    ["V3_MATERIAL_FINGERPRINT", calibration.baseline.v3.opticsMaterial.source, calibration.baseline.v3.opticsMaterial.sourceSha256],
    ["V3_SCENE_TARGET_FINGERPRINT", calibration.baseline.v3.opticsMaterial.sceneTargetSource, calibration.baseline.v3.opticsMaterial.sceneTargetSourceSha256],
    ["V3_GEOMETRY_FINGERPRINT", calibration.baseline.v3.geometry.source, calibration.baseline.v3.geometry.sourceSha256],
    ["V3_GRID_FINGERPRINT", calibration.baseline.v3.grid.source, calibration.baseline.v3.grid.sourceSha256],
    ["V3_DOM_FINGERPRINT", calibration.baseline.v3.grid.domSource, calibration.baseline.v3.grid.domSourceSha256],
    ["V3_MOTION_FINGERPRINT", calibration.baseline.v3.motion.source, calibration.baseline.v3.motion.sourceSha256],
    ["V3_VIDEO_UPLOAD_FINGERPRINT", calibration.baseline.v3.videoUpload.source, calibration.baseline.v3.videoUpload.sourceSha256],
    ["V3_ADAPTIVE_QUALITY_FINGERPRINT", calibration.baseline.v3.adaptiveQuality.source, calibration.baseline.v3.adaptiveQuality.sourceSha256],
  ];
  for (const [id, path, expected] of fingerprints) {
    const actual = await sha256File(resolve(REPO_ROOT, path));
    addCheck(checks, id, actual === expected, expected, actual);
  }

  const materialSource = await readFile(resolve(REPO_ROOT, calibration.baseline.v3.opticsMaterial.source), "utf8");
  const materialTokens = [
    `export function ${calibration.baseline.v3.opticsMaterial.factory}`,
    `new ${calibration.baseline.v3.opticsMaterial.materialClass}()`,
    "mix(own, worldMix, leak)",
    "const body = vec3(0.045, 0.05, 0.07)",
    "pow(max(n.y, 0), float(14))",
  ];
  addCheck(
    checks,
    "V3_MATERIAL_IDENTITY",
    materialTokens.every((token) => materialSource.includes(token)),
    materialTokens,
    materialTokens.filter((token) => materialSource.includes(token)),
  );

  const docContract = await readDocContract(resolve(REPO_ROOT, "docs/v4/SOURCE_OF_TRUTH.md"));
  const expectedDocs = expectedDocContract(calibration);
  addCheck(
    checks,
    "DOC_CONTRACT_MATCHES_CONFIG",
    isDeepStrictEqual(stable(docContract), stable(expectedDocs)),
    expectedDocs,
    docContract,
  );

  const activeRootDocs = (await readdir(resolve(REPO_ROOT, "docs"), { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => entry.name);
  const archived = (await readdir(resolve(REPO_ROOT, "docs/archive/pre-v4")))
    .filter((name) => name.endsWith(".md"));
  const expectedArchive = [
    "00-root-cause-audit.md",
    "01-rebuild-plan.md",
    "02-glass-model.md",
    "03-motion-model.md",
    "implementation-plan.md",
    "reference-spec.md",
  ];
  addCheck(checks, "NO_STALE_ROOT_DOCS", activeRootDocs.length === 0, [], activeRootDocs);
  addCheck(
    checks,
    "PRE_V4_DOCS_ARCHIVED",
    expectedArchive.every((name) => archived.includes(name)),
    expectedArchive,
    archived,
  );

  addCheck(checks, "PRIVATE_GOLDEN_IGNORED", isIgnored(".private/ilg-golden-v4/target.mp4"), true, isIgnored(".private/ilg-golden-v4/target.mp4"));
  addCheck(checks, "LOCAL_MANIFEST_IGNORED", isIgnored("qa-v4/reference/manifest.local.json"), true, isIgnored("qa-v4/reference/manifest.local.json"));
  addCheck(checks, "REFERENCE_MEDIA_IGNORED", isIgnored("qa-v4/reference/target.mp4") && isIgnored("qa-v4/reference/target.png"), true, isIgnored("qa-v4/reference/target.mp4") && isIgnored("qa-v4/reference/target.png"));
  addCheck(checks, "LOCAL_RESULTS_IGNORED", isIgnored("qa-v4/results/example.local.json"), true, isIgnored("qa-v4/results/example.local.json"));
  addCheck(checks, "MANIFEST_EXAMPLE_TRACKABLE", !isIgnored("qa-v4/reference/manifest.example.json"), true, !isIgnored("qa-v4/reference/manifest.example.json"));

  const failed = checks.filter((check) => check.status === "FAILED");
  return {
    schemaVersion: 1,
    status: failed.length ? "FAILED" : "PASSED",
    checks,
    failed: failed.map((check) => check.id),
  };
}
