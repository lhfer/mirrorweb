import assert from "node:assert/strict";
import test from "node:test";
import { runSourceContract } from "../../scripts/v4/lib/source-contract.mjs";

test("V4 source-of-truth matches the untouched V3 implementation", async () => {
  const result = await runSourceContract();
  assert.equal(result.status, "PASSED", JSON.stringify(result.failed));
  assert.deepEqual(result.failed, []);
});
