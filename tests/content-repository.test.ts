import test from "node:test";
import assert from "node:assert/strict";
import {
  bootPublicContent,
  getContentRuntime,
  isContentInstalled,
} from "../src/content/ContentRepository";

test("public boot fails over to bundled content once and never hot-swaps", async () => {
  const warnings: unknown[][] = [];
  const originalWarn = console.warn;
  const localStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", { value: undefined, configurable: true });
  console.warn = (...args: unknown[]) => warnings.push(args);
  try {
    const progress: number[] = [];
    const first = await bootPublicContent((value) => progress.push(value));
    const second = await bootPublicContent();

    assert.equal(first.source, "bundled");
    assert.equal(second.runtime, first.runtime);
    assert.equal(isContentInstalled(), true);
    assert.equal(warnings.length, 1);
    assert.equal(progress.at(-1), 1);

    const runtime = getContentRuntime();
    assert.equal(runtime.catalog.length, 24);
    assert.equal(runtime.mediaSources.length, 3);
    assert.equal(runtime.mediaBindings.length, 3);
    assert.deepEqual(
      runtime.catalog.slice(0, 6).map((card) => card.mediaAssetId),
      [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
      ],
    );
  } finally {
    console.warn = originalWarn;
    if (localStorageDescriptor) {
      Object.defineProperty(globalThis, "localStorage", localStorageDescriptor);
    } else {
      delete (globalThis as { localStorage?: unknown }).localStorage;
    }
  }
});
