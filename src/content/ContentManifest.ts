export const CONTENT_SCHEMA_VERSION = 1 as const;

export const MIN_MEDIA_ZOOM = 1;
export const MAX_MEDIA_ZOOM = 1.5;
export const MEDIA_ZOOM_RANGE = Object.freeze({
  min: MIN_MEDIA_ZOOM,
  max: MAX_MEDIA_ZOOM,
});

export const CONTENT_LIMITS = Object.freeze({
  code: 64,
  id: 128,
  category: 80,
  title: 120,
  deck: 280,
  footerCaption: 120,
  brandText: 80,
  ctaLabel: 80,
  loaderBrandText: 80,
  url: 2048,
  cards: 256,
});

export type ContentCard = {
  id: string;
  code: string;
  category: string;
  title: string;
  deck: string;
  accent: string;
  palette: [string, string, string, string];
  mediaAssetId: string;
  mediaUrl: string;
  posterUrl?: string;
  focusX: number;
  focusY: number;
  zoom: number;
  enabled: boolean;
  sortOrder: number;
};

export type ContentSite = {
  footerCaption: string;
  brandText: string;
  brandUrl: string;
  ctaLabel: string;
  ctaUrl: string;
  loaderBrandText: string;
};

export type ContentManifest = {
  schemaVersion: typeof CONTENT_SCHEMA_VERSION;
  version: number;
  cards: ContentCard[];
  site: ContentSite;
};

export class ContentManifestValidationError extends Error {
  readonly issues: readonly string[];

  constructor(issues: readonly string[]) {
    super(`Invalid content manifest: ${issues.join("; ")}`);
    this.name = "ContentManifestValidationError";
    this.issues = Object.freeze([...issues]);
  }
}

const HEX_COLOUR = /^#[0-9a-fA-F]{6}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CONTROL_CHARACTER = /[\u0000-\u001f\u007f]/;
const URL_UNSAFE_CHARACTER = /[\s<>]/;

const MANIFEST_KEYS = new Set(["schemaVersion", "version", "cards", "site"]);
const CARD_KEYS = new Set([
  "id", "code", "category", "title", "deck", "accent", "palette",
  "mediaAssetId", "mediaUrl", "posterUrl", "focusX", "focusY", "zoom",
  "enabled", "sortOrder",
]);
const SITE_KEYS = new Set([
  "footerCaption", "brandText", "brandUrl", "ctaLabel", "ctaUrl",
  "loaderBrandText",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function rejectUnknownKeys(
  value: Record<string, unknown>,
  allowed: ReadonlySet<string>,
  path: string,
  issues: string[],
): void {
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) issues.push(`${path}.${key} is not supported`);
  }
}

function readSafeText(
  value: unknown,
  path: string,
  maxLength: number,
  issues: string[],
): string {
  if (typeof value !== "string") {
    issues.push(`${path} must be a string`);
    return "";
  }
  if (value.trim().length === 0) issues.push(`${path} must not be empty`);
  if (value.length > maxLength) issues.push(`${path} exceeds ${maxLength} characters`);
  if (CONTROL_CHARACTER.test(value)) issues.push(`${path} contains a control character`);
  return value;
}

function readUuid(value: unknown, path: string, issues: string[]): string {
  if (typeof value !== "string" || !UUID.test(value)) {
    issues.push(`${path} must be a UUID`);
    return "00000000-0000-4000-8000-000000000000";
  }
  return value;
}

function readCardId(value: unknown, path: string, issues: string[]): string {
  const id = readSafeText(value, path, CONTENT_LIMITS.id, issues);
  if (id && !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(id)) {
    issues.push(`${path} contains unsupported identifier characters`);
  }
  return id;
}

function readColour(value: unknown, path: string, issues: string[]): string {
  if (typeof value !== "string" || !HEX_COLOUR.test(value)) {
    issues.push(`${path} must be a #RRGGBB colour`);
    return "#ffffff";
  }
  return value;
}

function readFiniteRange(
  value: unknown,
  path: string,
  min: number,
  max: number,
  issues: string[],
): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    issues.push(`${path} must be a finite number in [${min}, ${max}]`);
    return min;
  }
  return value;
}

function readNonNegativeInteger(value: unknown, path: string, issues: string[]): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    issues.push(`${path} must be a non-negative integer`);
    return 0;
  }
  return value;
}

type UrlPolicy = "media" | "https" | "https-or-mailto";

function isSafeRootRelativeUrl(value: string): boolean {
  return value.startsWith("/")
    && !value.startsWith("//")
    && !value.includes("\\")
    && !URL_UNSAFE_CHARACTER.test(value);
}

function isAllowedUrl(value: string, policy: UrlPolicy): boolean {
  if (value.length === 0 || value.length > CONTENT_LIMITS.url || URL_UNSAFE_CHARACTER.test(value)) {
    return false;
  }
  if (policy === "media" && isSafeRootRelativeUrl(value)) return true;
  try {
    const url = new URL(value);
    if (url.username || url.password) return false;
    if (value.startsWith("https://") && url.protocol === "https:") return true;
    if (policy !== "https-or-mailto"
        || !value.startsWith("mailto:") || url.protocol !== "mailto:") return false;
    return url.pathname.trim().length > 0;
  } catch {
    return false;
  }
}

function readUrl(
  value: unknown,
  path: string,
  policy: UrlPolicy,
  issues: string[],
): string {
  if (typeof value !== "string" || !isAllowedUrl(value, policy)) {
    const allowed = policy === "media"
      ? "a root-relative or https URL"
      : policy === "https" ? "an https URL" : "an https or mailto URL";
    issues.push(`${path} must be ${allowed}`);
    return policy === "media" ? "/" : "https://invalid.example/";
  }
  return value;
}

function readCard(value: unknown, index: number, issues: string[]): ContentCard {
  const path = `cards[${index}]`;
  if (!isRecord(value)) {
    issues.push(`${path} must be an object`);
    return {
      id: "00000000-0000-4000-8000-000000000000",
      code: "invalid",
      category: "invalid",
      title: "invalid",
      deck: "invalid",
      accent: "#ffffff",
      palette: ["#ffffff", "#ffffff", "#ffffff", "#ffffff"],
      mediaAssetId: "00000000-0000-4000-8000-000000000000",
      mediaUrl: "/",
      focusX: 0.5,
      focusY: 0.5,
      zoom: MIN_MEDIA_ZOOM,
      enabled: false,
      sortOrder: 0,
    };
  }
  rejectUnknownKeys(value, CARD_KEYS, path, issues);
  const paletteValue = value.palette;
  let palette: [string, string, string, string];
  if (!Array.isArray(paletteValue) || paletteValue.length !== 4) {
    issues.push(`${path}.palette must contain exactly four colours`);
    palette = ["#ffffff", "#ffffff", "#ffffff", "#ffffff"];
  } else {
    palette = [
      readColour(paletteValue[0], `${path}.palette[0]`, issues),
      readColour(paletteValue[1], `${path}.palette[1]`, issues),
      readColour(paletteValue[2], `${path}.palette[2]`, issues),
      readColour(paletteValue[3], `${path}.palette[3]`, issues),
    ];
  }
  let posterUrl: string | undefined;
  if (value.posterUrl !== undefined) {
    posterUrl = readUrl(value.posterUrl, `${path}.posterUrl`, "media", issues);
  }
  if (typeof value.enabled !== "boolean") issues.push(`${path}.enabled must be a boolean`);
  return {
    id: readCardId(value.id, `${path}.id`, issues),
    code: readSafeText(value.code, `${path}.code`, CONTENT_LIMITS.code, issues),
    category: readSafeText(value.category, `${path}.category`, CONTENT_LIMITS.category, issues),
    title: readSafeText(value.title, `${path}.title`, CONTENT_LIMITS.title, issues),
    deck: readSafeText(value.deck, `${path}.deck`, CONTENT_LIMITS.deck, issues),
    accent: readColour(value.accent, `${path}.accent`, issues),
    palette,
    mediaAssetId: readUuid(value.mediaAssetId, `${path}.mediaAssetId`, issues),
    mediaUrl: readUrl(value.mediaUrl, `${path}.mediaUrl`, "media", issues),
    ...(posterUrl === undefined ? {} : { posterUrl }),
    focusX: readFiniteRange(value.focusX, `${path}.focusX`, 0, 1, issues),
    focusY: readFiniteRange(value.focusY, `${path}.focusY`, 0, 1, issues),
    zoom: readFiniteRange(
      value.zoom, `${path}.zoom`, MIN_MEDIA_ZOOM, MAX_MEDIA_ZOOM, issues,
    ),
    enabled: typeof value.enabled === "boolean" ? value.enabled : false,
    sortOrder: readNonNegativeInteger(value.sortOrder, `${path}.sortOrder`, issues),
  };
}

function readSite(value: unknown, issues: string[]): ContentSite {
  if (!isRecord(value)) {
    issues.push("site must be an object");
    return {
      footerCaption: "invalid",
      brandText: "invalid",
      brandUrl: "https://invalid.example/",
      ctaLabel: "invalid",
      ctaUrl: "https://invalid.example/",
      loaderBrandText: "invalid",
    };
  }
  rejectUnknownKeys(value, SITE_KEYS, "site", issues);
  return {
    footerCaption: readSafeText(
      value.footerCaption, "site.footerCaption", CONTENT_LIMITS.footerCaption, issues,
    ),
    brandText: readSafeText(
      value.brandText, "site.brandText", CONTENT_LIMITS.brandText, issues,
    ),
    brandUrl: readUrl(value.brandUrl, "site.brandUrl", "https", issues),
    ctaLabel: readSafeText(
      value.ctaLabel, "site.ctaLabel", CONTENT_LIMITS.ctaLabel, issues,
    ),
    ctaUrl: readUrl(value.ctaUrl, "site.ctaUrl", "https-or-mailto", issues),
    loaderBrandText: readSafeText(
      value.loaderBrandText, "site.loaderBrandText", CONTENT_LIMITS.loaderBrandText, issues,
    ),
  };
}

function freezeManifest(manifest: ContentManifest): ContentManifest {
  for (const card of manifest.cards) {
    Object.freeze(card.palette);
    Object.freeze(card);
  }
  Object.freeze(manifest.cards);
  Object.freeze(manifest.site);
  return Object.freeze(manifest);
}

/**
 * Runtime validation is deliberately independent from the admin form. The
 * public renderer trusts only the immutable value returned here, regardless
 * of whether it came from PostgREST, localStorage, or the bundled seed.
 *
 * Media readiness is a publish-time database invariant. This layer validates
 * the UUID reference and a consistent public URL, but cannot and does not
 * infer a media_assets.status row from public JSON.
 */
export function parseContentManifest(value: unknown): ContentManifest {
  const issues: string[] = [];
  if (!isRecord(value)) throw new ContentManifestValidationError(["manifest must be an object"]);
  rejectUnknownKeys(value, MANIFEST_KEYS, "manifest", issues);

  if (value.schemaVersion !== CONTENT_SCHEMA_VERSION) {
    issues.push(`schemaVersion must be ${CONTENT_SCHEMA_VERSION}`);
  }
  const version = readNonNegativeInteger(value.version, "version", issues);
  const rawCards = value.cards;
  if (!Array.isArray(rawCards)) issues.push("cards must be an array");
  const cards = Array.isArray(rawCards)
    ? rawCards.map((card, index) => readCard(card, index, issues))
    : [];
  if (cards.length > CONTENT_LIMITS.cards) {
    issues.push(`cards exceeds the ${CONTENT_LIMITS.cards}-card runtime limit`);
  }
  if (!cards.some((card) => card.enabled)) issues.push("at least one card must be enabled");

  const ids = new Set<string>();
  const codes = new Set<string>();
  const sortOrders = new Set<number>();
  const mediaUrls = new Map<string, string>();
  const posterUrls = new Map<string, string | undefined>();
  for (const [index, card] of cards.entries()) {
    if (ids.has(card.id)) issues.push(`cards[${index}].id must be unique`);
    ids.add(card.id);
    if (codes.has(card.code)) issues.push(`cards[${index}].code must be unique`);
    codes.add(card.code);
    if (sortOrders.has(card.sortOrder)) issues.push(`cards[${index}].sortOrder must be unique`);
    sortOrders.add(card.sortOrder);

    const knownUrl = mediaUrls.get(card.mediaAssetId);
    if (knownUrl !== undefined && knownUrl !== card.mediaUrl) {
      issues.push(`cards[${index}].mediaUrl conflicts with its mediaAssetId`);
    } else {
      mediaUrls.set(card.mediaAssetId, card.mediaUrl);
    }
    if (posterUrls.has(card.mediaAssetId)
        && posterUrls.get(card.mediaAssetId) !== card.posterUrl) {
      issues.push(`cards[${index}].posterUrl conflicts with its mediaAssetId`);
    } else {
      posterUrls.set(card.mediaAssetId, card.posterUrl);
    }
  }

  const site = readSite(value.site, issues);
  if (issues.length) throw new ContentManifestValidationError(issues);
  return freezeManifest({
    schemaVersion: CONTENT_SCHEMA_VERSION,
    version,
    cards,
    site,
  });
}

export function isContentManifest(value: unknown): value is ContentManifest {
  try {
    parseContentManifest(value);
    return true;
  } catch {
    return false;
  }
}
