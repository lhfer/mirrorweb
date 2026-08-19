import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const repoRoot = resolve(import.meta.dirname, "../..");
const script = resolve(repoRoot, "scripts/v4/golden-manifest.mjs");

function run(env) {
  return spawnSync(process.execPath, [script, "--verify"], {
    cwd: repoRoot,
    env,
    encoding: "utf8",
  });
}

test("missing ILG_GOLDEN_DIR is BLOCKED and never passes", () => {
  const env = { ...process.env };
  delete env.ILG_GOLDEN_DIR;
  const result = run(env);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.status, "BLOCKED");
  assert.equal(report.comparisonRan, false);
  assert.deepEqual(report.blockers.map((item) => item.code), ["ILG_GOLDEN_DIR_UNSET"]);
});

test("a Golden directory without a frozen lock is BLOCKED", async () => {
  const directory = await mkdtemp(join(tmpdir(), "mirrorweb-v4-empty-golden-"));
  try {
    const result = run({ ...process.env, ILG_GOLDEN_DIR: directory });
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.status, "BLOCKED");
    assert.equal(report.comparisonRan, false);
    assert.deepEqual(report.blockers.map((item) => item.code), ["GOLDEN_LOCK_MISSING"]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
