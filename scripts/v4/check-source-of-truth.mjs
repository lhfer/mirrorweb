#!/usr/bin/env node
import { runSourceContract } from "./lib/source-contract.mjs";

try {
  const result = await runSourceContract();
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.status === "PASSED" ? 0 : 1;
} catch (error) {
  console.error(JSON.stringify({
    schemaVersion: 1,
    status: "ERROR",
    error: error instanceof Error ? error.message : String(error),
  }, null, 2));
  process.exitCode = 1;
}
