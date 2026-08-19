#!/usr/bin/env node

import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { REPO_ROOT, writeJson } from "./lib/common.mjs";
import { buildReferenceStatus } from "./lib/reference-status.mjs";
import { runSourceContract } from "./lib/source-contract.mjs";

try {
  const source = await runSourceContract();
  const result = await buildReferenceStatus({ sourceStatus: source.status });
  const output = resolve(REPO_ROOT, "qa-v4/results/reference-status.v4.json");
  await mkdir(resolve(REPO_ROOT, "qa-v4/results"), { recursive: true });
  await writeJson(output, result);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.phase1Allowed ? 0 : 2;
} catch (error) {
  console.error(JSON.stringify({ status: "ERROR", error: error instanceof Error ? error.message : String(error) }, null, 2));
  process.exitCode = 1;
}
