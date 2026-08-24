import test from "node:test";
import assert from "node:assert/strict";
import { AdapterError } from "../src/admin/domain";
import { LocalAdminAdapter } from "../src/admin/adapters/local";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length(): number { return this.values.size; }
  clear(): void { this.values.clear(); }
  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  key(index: number): string | null { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string): void { this.values.delete(key); }
  setItem(key: string, value: string): void { this.values.set(key, value); }
}

test("local sandbox enforces revisioned save, publish, and restore semantics", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    value: new MemoryStorage(), configurable: true,
  });
  try {
    const adapter = new LocalAdminAdapter();
    const initial = await adapter.loadWorkspace();
    assert.equal(initial.draft.revision, 1);
    assert.equal(initial.history.length, 1);

    const changed = structuredClone(initial.draft.manifest);
    changed.cards[0].title = "Revision-safe title";
    const saved = await adapter.saveDraft(changed, 1);
    assert.equal(saved.revision, 2);

    await assert.rejects(
      () => adapter.saveDraft(changed, 1),
      (error: unknown) => error instanceof AdapterError && error.code === "conflict",
    );

    const published = await adapter.publish(2, "Content Admin test publish");
    assert.equal(published.version, 2);
    assert.equal(published.manifest.version, 2);

    const afterPublish = await adapter.loadWorkspace();
    assert.equal(afterPublish.published.cards[0].title, "Revision-safe title");
    const restored = await adapter.restoreToDraft(afterPublish.history.at(-1)!.id);
    assert.equal(restored.revision, afterPublish.draft.revision + 1);

    const afterRestore = await adapter.loadWorkspace();
    assert.equal(afterRestore.published.cards[0].title, "Revision-safe title");
    assert.equal(afterRestore.draft.manifest.cards[0].title, initial.history[0].manifest.cards[0].title);
    assert.notDeepEqual(afterRestore.draft.manifest.cards, afterRestore.published.cards);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});

test("local sandbox blocks purge while any retained manifest references media", async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    value: new MemoryStorage(), configurable: true,
  });
  try {
    const adapter = new LocalAdminAdapter();
    const workspace = await adapter.loadWorkspace();
    await assert.rejects(
      () => adapter.purgeMedia(workspace.media[0]),
      (error: unknown) => error instanceof AdapterError && error.code === "validation",
    );
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
    else delete (globalThis as { localStorage?: unknown }).localStorage;
  }
});
