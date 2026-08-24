import test from "node:test";
import assert from "node:assert/strict";
import { validateManifest } from "../src/admin/domain";
import { createSeedManifest, SEED_MEDIA } from "../src/admin/seed";

test("admin draft and publish validation share the frozen content contract", () => {
  const manifest = createSeedManifest();
  const media = structuredClone(SEED_MEDIA);
  assert.deepEqual(validateManifest(manifest, media, "draft"), []);
  assert.deepEqual(validateManifest(manifest, media, "publish"), []);

  media[0].status = "archived";
  assert.equal(validateManifest(manifest, media, "draft").length, 0);
  assert.ok(validateManifest(manifest, media, "publish")
    .some((issue) => issue.path.endsWith("mediaAssetId")));
});

test("admin treats XSS-shaped copy as text but rejects executable URLs", () => {
  const manifest = createSeedManifest();
  manifest.cards[0].title = "<img src=x onerror=alert(1)>";
  manifest.cards[0].deck = "<script>literal copy</script>";
  assert.deepEqual(validateManifest(manifest, SEED_MEDIA, "publish"), []);

  manifest.site.ctaUrl = "javascript:alert(1)";
  assert.ok(validateManifest(manifest, SEED_MEDIA, "publish")
    .some((issue) => issue.path === "site.ctaUrl"));
});
