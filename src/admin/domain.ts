import {
  CONTENT_LIMITS as RUNTIME_CONTENT_LIMITS,
  ContentManifestValidationError,
  MAX_MEDIA_ZOOM,
  MIN_MEDIA_ZOOM,
  parseContentManifest,
  type ContentCard as RuntimeContentCard,
  type ContentManifest as RuntimeContentManifest,
  type ContentSite,
} from "../content/ContentManifest";

export type Palette = [string, string, string, string];
export type ContentCard = RuntimeContentCard;
export type SiteSettings = ContentSite;
export type ContentManifest = RuntimeContentManifest;

export type MediaStatus = "uploading" | "ready" | "archived" | "failed";

export type MediaAsset = {
  id: string;
  originalName: string;
  storagePath: string;
  posterPath: string;
  mimeType: string;
  sizeBytes: number;
  width: number;
  height: number;
  durationMs: number;
  status: MediaStatus;
  mediaUrl: string;
  posterUrl?: string;
  sha256?: string;
  createdAt: string;
  updatedAt: string;
};

export type ContentVersion = {
  id: string;
  version: number;
  manifest: ContentManifest;
  createdBy: string;
  createdAt: string;
  releaseNote: string;
  draftRevision?: number;
};

export type DraftSnapshot = {
  id: string;
  manifest: ContentManifest;
  revision: number;
  updatedBy: string;
  updatedAt: string;
};

export type WorkspaceSnapshot = {
  draft: DraftSnapshot;
  published: ContentManifest;
  media: MediaAsset[];
  history: ContentVersion[];
};

export type AdminActor = {
  id: string;
  email: string;
};

export type AuthState =
  | { kind: "anonymous" }
  | { kind: "forbidden"; email: string }
  | { kind: "authenticated"; actor: AdminActor };

export type PreparedMedia = {
  file: File;
  poster: Blob;
  width: number;
  height: number;
  durationMs: number;
  sha256: string;
};

export type UploadProgress = {
  phase: "preparing" | "video" | "poster" | "registering" | "done";
  value: number;
};

export type Unsubscribe = () => void;

export type AdapterMode = "local" | "supabase";

export interface AdminAdapter {
  readonly mode: AdapterMode;
  getAuthState(): Promise<AuthState>;
  onAuthChange(listener: () => void): Unsubscribe;
  sendMagicLink(email: string): Promise<void>;
  signOut(): Promise<void>;
  loadWorkspace(): Promise<WorkspaceSnapshot>;
  saveDraft(manifest: ContentManifest, expectedRevision: number): Promise<DraftSnapshot>;
  publish(expectedRevision: number, releaseNote: string): Promise<ContentVersion>;
  restoreToDraft(versionId: string): Promise<DraftSnapshot>;
  uploadMedia(
    media: PreparedMedia,
    signal: AbortSignal,
    onProgress: (progress: UploadProgress) => void,
  ): Promise<MediaAsset>;
  archiveMedia(assetId: string): Promise<MediaAsset>;
  purgeMedia(asset: MediaAsset): Promise<void>;
}

export class AdapterError extends Error {
  constructor(
    readonly code: "conflict" | "forbidden" | "validation" | "backend" | "cancelled",
    message: string,
  ) {
    super(message);
    this.name = "AdapterError";
  }
}

export type ValidationIssue = {
  path: string;
  message: string;
};

export const CONTENT_LIMITS = {
  code: RUNTIME_CONTENT_LIMITS.code,
  category: RUNTIME_CONTENT_LIMITS.category,
  title: RUNTIME_CONTENT_LIMITS.title,
  deck: RUNTIME_CONTENT_LIMITS.deck,
  footerCaption: RUNTIME_CONTENT_LIMITS.footerCaption,
  compactSiteText: RUNTIME_CONTENT_LIMITS.brandText,
  url: RUNTIME_CONTENT_LIMITS.url,
  zoomMin: MIN_MEDIA_ZOOM,
  zoomMax: MAX_MEDIA_ZOOM,
  maxMediaBytes: 100 * 1024 * 1024,
} as const;

const HEX = /^#[0-9a-fA-F]{6}$/;

function textIssue(path: string, value: string, max: number): ValidationIssue | undefined {
  const trimmed = value.trim();
  if (!trimmed) return { path, message: "不能为空" };
  if (trimmed.length > max) return { path, message: `不能超过 ${max} 个字符` };
  return undefined;
}

function urlIssue(
  path: string,
  value: string,
  protocols: readonly string[],
): ValidationIssue | undefined {
  const base = textIssue(path, value, CONTENT_LIMITS.url);
  if (base) return base;
  try {
    const url = new URL(value);
    if (!protocols.includes(url.protocol)) {
      return { path, message: `仅允许 ${protocols.join(" / ")}` };
    }
  } catch {
    return { path, message: "请输入完整、有效的 URL" };
  }
  return undefined;
}

export function validateManifest(
  manifest: ContentManifest,
  media: readonly MediaAsset[],
  phase: "draft" | "publish" = "publish",
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const ids = new Set<string>();
  const codes = new Set<string>();
  const sortOrders = new Set<number>();
  const mediaById = new Map(media.map((asset) => [asset.id, asset]));

  try {
    parseContentManifest(manifest);
  } catch (error) {
    if (error instanceof ContentManifestValidationError) {
      for (const message of error.issues) issues.push({ path: "manifest", message });
    } else {
      issues.push({ path: "manifest", message: "Manifest 结构无效" });
    }
  }

  if (manifest.schemaVersion !== 1) {
    issues.push({ path: "schemaVersion", message: "仅支持 schemaVersion 1" });
  }
  if (!manifest.cards.some((card) => card.enabled)) {
    issues.push({ path: "cards", message: "至少需要一张启用的卡片" });
  }

  manifest.cards.forEach((card, index) => {
    const root = `cards[${index}]`;
    if (!card.id.trim()) issues.push({ path: `${root}.id`, message: "卡片 ID 不能为空" });
    else if (ids.has(card.id)) issues.push({ path: `${root}.id`, message: "卡片 ID 必须唯一" });
    ids.add(card.id);

    const fields: Array<[string, string, number]> = [
      ["code", card.code, CONTENT_LIMITS.code],
      ["category", card.category, CONTENT_LIMITS.category],
      ["title", card.title, CONTENT_LIMITS.title],
      ["deck", card.deck, CONTENT_LIMITS.deck],
    ];
    for (const [name, value, limit] of fields) {
      const issue = textIssue(`${root}.${name}`, value, limit);
      if (issue) issues.push(issue);
    }

    const normalizedCode = card.code.trim().toLocaleLowerCase();
    if (normalizedCode && codes.has(normalizedCode)) {
      issues.push({ path: `${root}.code`, message: "卡片 Code 必须唯一" });
    }
    codes.add(normalizedCode);

    if (!HEX.test(card.accent)) {
      issues.push({ path: `${root}.accent`, message: "颜色必须是 #RRGGBB" });
    }
    card.palette.forEach((colour, colourIndex) => {
      if (!HEX.test(colour)) {
        issues.push({ path: `${root}.palette[${colourIndex}]`, message: "颜色必须是 #RRGGBB" });
      }
    });

    if (!Number.isFinite(card.focusX) || card.focusX < 0 || card.focusX > 1) {
      issues.push({ path: `${root}.focusX`, message: "焦点必须在 0 到 1 之间" });
    }
    if (!Number.isFinite(card.focusY) || card.focusY < 0 || card.focusY > 1) {
      issues.push({ path: `${root}.focusY`, message: "焦点必须在 0 到 1 之间" });
    }
    if (
      !Number.isFinite(card.zoom)
      || card.zoom < CONTENT_LIMITS.zoomMin
      || card.zoom > CONTENT_LIMITS.zoomMax
    ) {
      issues.push({ path: `${root}.zoom`, message: "缩放必须在 1 到 1.5 之间" });
    }

    const asset = mediaById.get(card.mediaAssetId);
    const allowedStatuses: MediaStatus[] = phase === "draft" ? ["ready", "archived"] : ["ready"];
    if (!asset || !allowedStatuses.includes(asset.status)) {
      issues.push({
        path: `${root}.mediaAssetId`,
        message: phase === "draft" ? "草稿只能保留 Ready 或 Archived 视频" : "发布只能使用 Ready 视频",
      });
    }
    if (!Number.isInteger(card.sortOrder) || card.sortOrder < 0) {
      issues.push({ path: `${root}.sortOrder`, message: "排序值必须是非负整数" });
    } else if (sortOrders.has(card.sortOrder)) {
      issues.push({ path: `${root}.sortOrder`, message: "排序值必须唯一" });
    }
    sortOrders.add(card.sortOrder);

    const mediaUrlIssue = publicMediaUrlIssue(`${root}.mediaUrl`, card.mediaUrl);
    if (mediaUrlIssue) issues.push(mediaUrlIssue);
    if (card.posterUrl) {
      const posterUrlIssue = publicMediaUrlIssue(`${root}.posterUrl`, card.posterUrl);
      if (posterUrlIssue) issues.push(posterUrlIssue);
    }
  });

  const siteFields: Array<[string, string, number]> = [
    ["footerCaption", manifest.site.footerCaption, CONTENT_LIMITS.footerCaption],
    ["brandText", manifest.site.brandText, CONTENT_LIMITS.compactSiteText],
    ["ctaLabel", manifest.site.ctaLabel, CONTENT_LIMITS.compactSiteText],
    ["loaderBrandText", manifest.site.loaderBrandText, CONTENT_LIMITS.compactSiteText],
  ];
  for (const [name, value, limit] of siteFields) {
    const issue = textIssue(`site.${name}`, value, limit);
    if (issue) issues.push(issue);
  }
  const brandUrlIssue = urlIssue("site.brandUrl", manifest.site.brandUrl, ["https:"]);
  if (brandUrlIssue) issues.push(brandUrlIssue);
  const ctaUrlIssue = urlIssue("site.ctaUrl", manifest.site.ctaUrl, ["https:", "mailto:"]);
  if (ctaUrlIssue) issues.push(ctaUrlIssue);

  return issues;
}

function publicMediaUrlIssue(path: string, value: string): ValidationIssue | undefined {
  if (value.startsWith("/") && !value.startsWith("//")) return undefined;
  try {
    if (new URL(value).protocol === "https:") return undefined;
  } catch {
    // Fall through to the shared message.
  }
  return { path, message: "媒体 URL 仅允许根相对路径或 https" };
}

export function cloneManifest(manifest: ContentManifest): ContentManifest {
  return structuredClone(manifest);
}

export function sortCards(cards: ContentCard[]): ContentCard[] {
  return cards
    .slice()
    .sort((a, b) => a.sortOrder - b.sortOrder)
    .map((card, index) => ({ ...card, sortOrder: index }));
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value >= 10 || index === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[index]}`;
}

export function formatDuration(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
