#!/usr/bin/env node

import path from "node:path";

import { REVIEW_HOST, REVIEW_PORT, startPrivateReviewServer } from "./lib/private-review-server.mjs";
import { DEFAULT_REVIEWER_STATE_PATH } from "./lib/reviewer-state.mjs";

const REPO_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");

const options = { host: REVIEW_HOST, port: REVIEW_PORT };
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--reviewer-state=")) {
    options.reviewerStatePath = path.resolve(REPO_ROOT, argument.slice("--reviewer-state=".length));
  } else if (argument.startsWith("--port=")) {
    options.port = Number(argument.slice("--port=".length));
  } else {
    throw new Error(`Unknown argument: ${argument}`);
  }
}

const instance = await startPrivateReviewServer(options);

console.log(`Reviewer Mode (default entry): ${instance.runtime.origin}/`);
console.log(`Advanced Inspector: ${instance.runtime.origin}/phase-1b-review?mode=advanced`);
console.log(`Private annotations (never written by Reviewer Mode): ${instance.runtime.evidence.privateOutputPath}`);
console.log(`Reviewer drafts: ${instance.runtime.evidence.reviewerStatePath} (default ${DEFAULT_REVIEWER_STATE_PATH})`);
console.log(`Candidate frames: ${instance.runtime.evidence.candidateFrameCount}`);
console.log("Target pixels remain local-only; final target match remains BLOCKED.");

let closing = false;
async function close(signal) {
  if (closing) return;
  closing = true;
  try {
    await instance.close();
    process.exitCode = 0;
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  } finally {
    if (signal) console.log(`Private review server stopped (${signal}).`);
  }
}

process.once("SIGINT", () => { void close("SIGINT"); });
process.once("SIGTERM", () => { void close("SIGTERM"); });
