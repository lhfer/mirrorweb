import test from "node:test";
import assert from "node:assert/strict";
import defaultContent from "../src/content/default-content.json";
import {
  ContentManifestValidationError,
  parseContentManifest,
} from "../src/content/ContentManifest";

function cloneDefault(): typeof defaultContent {
  return structuredClone(defaultContent);
}

function assertInvalid(value: unknown, issue: RegExp): void {
  assert.throws(
    () => parseContentManifest(value),
    (error: unknown) => error instanceof ContentManifestValidationError
      && error.issues.some((message) => issue.test(message)),
  );
}

test("bundled v1.0 content validates and is deeply frozen", () => {
  const parsed = parseContentManifest(defaultContent);
  assert.equal(parsed.schemaVersion, 1);
  assert.equal(parsed.cards.length, 24);
  assert.equal(parsed.cards.filter((card) => card.enabled).length, 24);
  assert.equal(new Set(parsed.cards.map((card) => card.mediaAssetId)).size, 3);
  assert.ok(Object.isFrozen(parsed));
  assert.ok(Object.isFrozen(parsed.cards));
  assert.ok(Object.isFrozen(parsed.cards[0]));
  assert.ok(Object.isFrozen(parsed.cards[0].palette));
  assert.ok(Object.isFrozen(parsed.site));
});

test("XSS-shaped copy remains literal content while unsafe URLs are rejected", () => {
  const literal = cloneDefault();
  literal.cards[0].title = `<img src=x onerror="globalThis.pwned=true">`;
  literal.cards[0].deck = "<script>alert('text only')</script>";
  const parsed = parseContentManifest(literal);
  assert.equal(parsed.cards[0].title, literal.cards[0].title);
  assert.equal(parsed.cards[0].deck, literal.cards[0].deck);

  const javascriptUrl = cloneDefault();
  javascriptUrl.site.ctaUrl = "javascript:alert(1)";
  assertInvalid(javascriptUrl, /site\.ctaUrl/);
});

test("colour, crop, identifier, and ordering constraints fail closed", () => {
  const colour = cloneDefault();
  colour.cards[0].accent = "red";
  assertInvalid(colour, /accent must be a #RRGGBB colour/);

  const focus = cloneDefault();
  focus.cards[0].focusX = 1.01;
  assertInvalid(focus, /focusX/);

  const zoom = cloneDefault();
  zoom.cards[0].zoom = 1.51;
  assertInvalid(zoom, /zoom/);

  const duplicate = cloneDefault();
  duplicate.cards[1].code = duplicate.cards[0].code;
  duplicate.cards[1].sortOrder = duplicate.cards[0].sortOrder;
  assertInvalid(duplicate, /code must be unique/);
  assertInvalid(duplicate, /sortOrder must be unique/);
});

test("one media id cannot resolve to conflicting public objects", () => {
  const manifest = cloneDefault();
  manifest.cards[3].mediaAssetId = manifest.cards[0].mediaAssetId;
  manifest.cards[3].mediaUrl = "/clips/a-different-file.mp4";
  assertInvalid(manifest, /mediaUrl conflicts with its mediaAssetId/);
});

test("a manifest without enabled cards cannot replace known-good content", () => {
  const manifest = cloneDefault();
  for (const card of manifest.cards) card.enabled = false;
  assertInvalid(manifest, /at least one card must be enabled/);
});
