#!/usr/bin/env node
import { resolve } from "node:path";
import { REPO_ROOT } from "./lib/common.mjs";
import { createGoldenLock, verifyGolden, writeGoldenResult } from "./lib/golden.mjs";

function outputArgument(args) {
  const index = args.indexOf("--output");
  return index >= 0 && args[index + 1] ? resolve(REPO_ROOT, args[index + 1]) : null;
}

try {
  const args = process.argv.slice(2);
  const result = args.includes("--create-lock")
    ? await createGoldenLock()
    : await verifyGolden();
  const output = outputArgument(args);
  if (output) await writeGoldenResult(output, result);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.status === "READY" ? 0 : 2;
} catch (error) {
  console.error(JSON.stringify({
    schemaVersion: 1,
    status: "ERROR",
    error: error instanceof Error ? error.message : String(error),
  }, null, 2));
  process.exitCode = 1;
}
