import bundledContent from "./default-content.json";
import {
  parseContentManifest,
  type ContentCard,
  type ContentManifest,
} from "./ContentManifest";

export type ContentSource =
  | "remote"
  | "last-known-good"
  | "bundled"
  | "draft-preview"
  | "published-preview";

export type ContentMediaSource = {
  mediaAssetId: string;
  mediaUrl: string;
  posterUrl?: string;
};

/**
 * A binding is a crop, not a video element. Several bindings may point at the
 * same source when two cards select the same asset with different focus/zoom.
 */
export type ContentMediaBinding = ContentMediaSource & {
  sourceIndex: number;
  focusX: number;
  focusY: number;
  zoom: number;
  fallbackPalette: [string, string, string, string];
};

export type RuntimeContentCard = ContentCard & {
  /** Explicit binding into mediaBindings; never derived from card position. */
  clipIndex: number;
};

export type ContentRuntime = {
  manifest: ContentManifest;
  source: ContentSource;
  catalog: readonly RuntimeContentCard[];
  mediaSources: readonly ContentMediaSource[];
  mediaBindings: readonly ContentMediaBinding[];
};

export type ContentBootResult = {
  manifest: ContentManifest;
  source: ContentSource;
  runtime: ContentRuntime;
};

const ACTIVE_MANIFEST_RPC = "get_active_content_manifest";
const LAST_KNOWN_GOOD_KEY = "mirrorweb:content-manifest:last-known-good:v1";
const DEFAULT_FETCH_TIMEOUT_MS = 4_500;
const MAX_MANIFEST_BYTES = 1_000_000;

const bundledManifest = parseContentManifest(bundledContent);
let runtime = buildRuntime(bundledManifest, "bundled");
let installed = false;
let bootPromise: Promise<ContentBootResult> | undefined;
let warningIssued = false;

function bindingKey(card: ContentCard): string {
  return JSON.stringify([
    card.mediaAssetId,
    card.focusX,
    card.focusY,
    card.zoom,
  ]);
}

function buildRuntime(manifest: ContentManifest, source: ContentSource): ContentRuntime {
  const enabledCards = manifest.cards
    .filter((card) => card.enabled)
    .slice()
    .sort((a, b) => a.sortOrder - b.sortOrder);
  const mediaSources: ContentMediaSource[] = [];
  const sourceByAssetId = new Map<string, number>();
  const mediaBindings: ContentMediaBinding[] = [];
  const bindingByKey = new Map<string, number>();

  const catalog = enabledCards.map((card): RuntimeContentCard => {
    let sourceIndex = sourceByAssetId.get(card.mediaAssetId);
    if (sourceIndex === undefined) {
      sourceIndex = mediaSources.length;
      sourceByAssetId.set(card.mediaAssetId, sourceIndex);
      mediaSources.push(Object.freeze({
        mediaAssetId: card.mediaAssetId,
        mediaUrl: card.mediaUrl,
        ...(card.posterUrl === undefined ? {} : { posterUrl: card.posterUrl }),
      }));
    }

    const key = bindingKey(card);
    let clipIndex = bindingByKey.get(key);
    if (clipIndex === undefined) {
      clipIndex = mediaBindings.length;
      bindingByKey.set(key, clipIndex);
      const fallbackPalette = [...card.palette] as ContentMediaBinding["fallbackPalette"];
      Object.freeze(fallbackPalette);
      mediaBindings.push(Object.freeze({
        mediaAssetId: card.mediaAssetId,
        mediaUrl: card.mediaUrl,
        ...(card.posterUrl === undefined ? {} : { posterUrl: card.posterUrl }),
        sourceIndex,
        focusX: card.focusX,
        focusY: card.focusY,
        zoom: card.zoom,
        fallbackPalette,
      }));
    }

    return Object.freeze({ ...card, clipIndex });
  });

  Object.freeze(catalog);
  Object.freeze(mediaSources);
  Object.freeze(mediaBindings);
  return Object.freeze({ manifest, source, catalog, mediaSources, mediaBindings });
}

function resultFromRuntime(value: ContentRuntime): ContentBootResult {
  return Object.freeze({ manifest: value.manifest, source: value.source, runtime: value });
}

function setSourceMarker(source: ContentSource): void {
  if (typeof document !== "undefined" && document.body) {
    document.body.dataset.contentSource = source;
    document.body.dataset.contentVersion = String(runtime.manifest.version);
  }
}

/**
 * The only mutable seam in the public content path. Installation validates,
 * copies and deep-freezes the manifest, builds every lookup once, then closes
 * permanently for the life of the page. Running textures are never swapped.
 */
export function installContentManifest(
  value: unknown,
  source: ContentSource,
): ContentBootResult {
  if (installed) throw new Error("Content manifest is already installed for this page boot");
  const manifest = parseContentManifest(value);
  runtime = buildRuntime(manifest, source);
  installed = true;
  setSourceMarker(source);
  return resultFromRuntime(runtime);
}

export function getContentManifest(): ContentManifest {
  return runtime.manifest;
}

export function getContentRuntime(): ContentRuntime {
  return runtime;
}

export function isContentInstalled(): boolean {
  return installed;
}

function warnOnce(reasons: readonly string[], selected: ContentSource): void {
  if (warningIssued || reasons.length === 0) return;
  warningIssued = true;
  console.warn(
    `[MirrorWeb content] ${reasons.join("; ")} Using ${selected} content for this boot.`,
  );
}

function storage(): Storage | undefined {
  try {
    return typeof localStorage === "undefined" ? undefined : localStorage;
  } catch {
    return undefined;
  }
}

function readLastKnownGood(): unknown {
  const raw = storage()?.getItem(LAST_KNOWN_GOOD_KEY);
  if (!raw) throw new Error("no last-known-good manifest");
  if (raw.length > MAX_MANIFEST_BYTES) throw new Error("last-known-good manifest is too large");
  return JSON.parse(raw) as unknown;
}

function writeLastKnownGood(manifest: ContentManifest): void {
  const target = storage();
  if (!target) return;
  target.setItem(LAST_KNOWN_GOOD_KEY, JSON.stringify(manifest));
}

function safeReason(label: string, error: unknown): string {
  if (error instanceof DOMException && error.name === "AbortError") return `${label} timed out`;
  if (error instanceof Error && error.message === "Supabase is not configured") {
    return "Supabase is not configured";
  }
  if (error instanceof Error && error.message.startsWith("HTTP ")) {
    return `${label} returned ${error.message}`;
  }
  return `${label} was unavailable or invalid`;
}

function unwrapRpcManifest(value: unknown): unknown {
  if (Array.isArray(value)) {
    if (value.length !== 1) throw new Error("RPC returned an unexpected row count");
    return unwrapRpcManifest(value[0]);
  }
  if (typeof value === "object" && value !== null) {
    const row = value as Record<string, unknown>;
    if ("manifest" in row) return row.manifest;
    if (ACTIVE_MANIFEST_RPC in row) return row[ACTIVE_MANIFEST_RPC];
  }
  return value;
}

function jwtRole(key: string): string | undefined {
  const payload = key.split(".")[1];
  if (!payload || typeof atob === "undefined") return undefined;
  try {
    const decoded = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = decoded.padEnd(Math.ceil(decoded.length / 4) * 4, "=");
    const value = JSON.parse(atob(padded)) as { role?: unknown };
    return typeof value.role === "string" ? value.role : undefined;
  } catch {
    return undefined;
  }
}

function fetchTimeoutMs(): number {
  const configured = Number(import.meta.env.VITE_CONTENT_FETCH_TIMEOUT_MS);
  if (!Number.isFinite(configured)) return DEFAULT_FETCH_TIMEOUT_MS;
  return Math.max(1_000, Math.min(15_000, Math.round(configured)));
}

async function fetchRemoteManifest(): Promise<unknown> {
  const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim();
  const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!supabaseUrl || !publishableKey) throw new Error("Supabase is not configured");
  if (publishableKey.startsWith("sb_secret_") || jwtRole(publishableKey) === "service_role") {
    throw new Error("Supabase is not configured");
  }
  const base = new URL(supabaseUrl);
  if (base.protocol !== "https:") throw new Error("Supabase is not configured");

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), fetchTimeoutMs());
  try {
    const response = await fetch(
      `${supabaseUrl.replace(/\/+$/, "")}/rest/v1/rpc/${ACTIVE_MANIFEST_RPC}`,
      {
        method: "POST",
        headers: {
          apikey: publishableKey,
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: "{}",
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const raw = await response.text();
    if (raw.length > MAX_MANIFEST_BYTES) throw new Error("remote manifest is too large");
    return unwrapRpcManifest(JSON.parse(raw) as unknown);
  } finally {
    window.clearTimeout(timeout);
  }
}

/**
 * One public request, once per page boot. Any failure is collapsed into one
 * warning after the repository has selected the next valid source.
 */
export function bootPublicContent(
  onProgress: (fraction: number) => void = () => undefined,
): Promise<ContentBootResult> {
  if (installed) {
    onProgress(1);
    return Promise.resolve(resultFromRuntime(runtime));
  }
  if (bootPromise) return bootPromise;
  bootPromise = (async () => {
    const reasons: string[] = [];
    onProgress(0.05);
    try {
      const remote = parseContentManifest(await fetchRemoteManifest());
      try {
        writeLastKnownGood(remote);
      } catch {
        reasons.push("last-known-good cache could not be updated");
      }
      const result = installContentManifest(remote, "remote");
      onProgress(1);
      warnOnce(reasons, result.source);
      return result;
    } catch (error) {
      reasons.push(safeReason("active manifest", error));
    }

    onProgress(0.7);
    try {
      const cached = parseContentManifest(readLastKnownGood());
      const result = installContentManifest(cached, "last-known-good");
      onProgress(1);
      warnOnce(reasons, result.source);
      return result;
    } catch {
      reasons.push("last-known-good manifest was unavailable or invalid");
    }

    const result = installContentManifest(bundledManifest, "bundled");
    onProgress(1);
    warnOnce(reasons, result.source);
    return result;
  })();
  return bootPromise;
}
