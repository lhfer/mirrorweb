import {
  AdapterError,
  cloneManifest,
  type AdminAdapter,
  type AuthState,
  type ContentVersion,
  type DraftSnapshot,
  type MediaAsset,
  type PreparedMedia,
  type UploadProgress,
  type WorkspaceSnapshot,
} from "../domain";
import { createSeedManifest, SEED_MEDIA } from "../seed";

const STORAGE_KEY = "mirrorweb-content-admin-local-v1";
const LOCAL_ACTOR = { id: "local-admin", email: "local@mirrorweb.invalid" };

type LocalState = WorkspaceSnapshot;

function initialState(): LocalState {
  const manifest = createSeedManifest();
  const createdAt = new Date().toISOString();
  return {
    draft: {
      id: "local-draft",
      manifest: cloneManifest(manifest),
      revision: 1,
      updatedBy: LOCAL_ACTOR.email,
      updatedAt: createdAt,
    },
    published: cloneManifest(manifest),
    media: structuredClone(SEED_MEDIA),
    history: [
      {
        id: "local-version-1",
        version: 1,
        manifest: cloneManifest(manifest),
        createdBy: LOCAL_ACTOR.email,
        createdAt,
        releaseNote: "v1.0.0 seeded content",
      },
    ],
  };
}

function readState(): LocalState {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return initialState();
  try {
    const state = JSON.parse(stored) as LocalState;
    return state?.draft?.manifest && Array.isArray(state.media) ? state : initialState();
  } catch {
    return initialState();
  }
}

function writeState(state: LocalState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function assertNotAborted(signal: AbortSignal): void {
  if (signal.aborted) throw new AdapterError("cancelled", "上传已取消");
}

async function tick(signal: AbortSignal, delay = 80): Promise<void> {
  assertNotAborted(signal);
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, delay);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new AdapterError("cancelled", "上传已取消"));
    }, { once: true });
  });
}

export class LocalAdminAdapter implements AdminAdapter {
  readonly mode = "local" as const;

  async getAuthState(): Promise<AuthState> {
    return { kind: "authenticated", actor: LOCAL_ACTOR };
  }

  onAuthChange(): () => void {
    return () => undefined;
  }

  async sendMagicLink(): Promise<void> {
    throw new AdapterError("backend", "LOCAL SANDBOX 不发送 Magic Link");
  }

  async signOut(): Promise<void> {
    return undefined;
  }

  async loadWorkspace(): Promise<WorkspaceSnapshot> {
    return structuredClone(readState());
  }

  async saveDraft(manifest: WorkspaceSnapshot["draft"]["manifest"], expectedRevision: number): Promise<DraftSnapshot> {
    const state = readState();
    if (state.draft.revision !== expectedRevision) {
      throw new AdapterError("conflict", `草稿已从 r${expectedRevision} 更新为 r${state.draft.revision}`);
    }
    state.draft = {
      ...state.draft,
      manifest: cloneManifest(manifest),
      revision: expectedRevision + 1,
      updatedBy: LOCAL_ACTOR.email,
      updatedAt: new Date().toISOString(),
    };
    writeState(state);
    return structuredClone(state.draft);
  }

  async publish(expectedRevision: number, releaseNote: string): Promise<ContentVersion> {
    const state = readState();
    if (state.draft.revision !== expectedRevision) {
      throw new AdapterError("conflict", `发布前草稿 revision 已变为 r${state.draft.revision}`);
    }
    const version = Math.max(0, ...state.history.map((item) => item.version)) + 1;
    const manifest = cloneManifest(state.draft.manifest);
    manifest.version = version;
    const record: ContentVersion = {
      id: `local-version-${version}-${crypto.randomUUID()}`,
      version,
      manifest,
      createdBy: LOCAL_ACTOR.email,
      createdAt: new Date().toISOString(),
      releaseNote: releaseNote.trim(),
      draftRevision: state.draft.revision + 1,
    };
    state.published = cloneManifest(manifest);
    state.history.unshift(record);
    state.draft = {
      ...state.draft,
      manifest: cloneManifest(manifest),
      revision: state.draft.revision + 1,
      updatedBy: LOCAL_ACTOR.email,
      updatedAt: new Date().toISOString(),
    };
    writeState(state);
    return structuredClone(record);
  }

  async restoreToDraft(versionId: string): Promise<DraftSnapshot> {
    const state = readState();
    const version = state.history.find((item) => item.id === versionId);
    if (!version) throw new AdapterError("validation", "找不到该历史版本");
    state.draft = {
      ...state.draft,
      manifest: cloneManifest(version.manifest),
      revision: state.draft.revision + 1,
      updatedBy: LOCAL_ACTOR.email,
      updatedAt: new Date().toISOString(),
    };
    writeState(state);
    return structuredClone(state.draft);
  }

  async uploadMedia(
    media: PreparedMedia,
    signal: AbortSignal,
    onProgress: (progress: UploadProgress) => void,
  ): Promise<MediaAsset> {
    onProgress({ phase: "video", value: 12 });
    await tick(signal);
    onProgress({ phase: "video", value: 52 });
    await tick(signal);
    onProgress({ phase: "poster", value: 76 });
    await tick(signal);
    onProgress({ phase: "registering", value: 92 });
    await tick(signal);
    assertNotAborted(signal);

    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const asset: MediaAsset = {
      id,
      originalName: media.file.name,
      storagePath: `local/${id}.mp4`,
      posterPath: `local/${id}.jpg`,
      mimeType: media.file.type,
      sizeBytes: media.file.size,
      width: media.width,
      height: media.height,
      durationMs: media.durationMs,
      status: "ready",
      mediaUrl: URL.createObjectURL(media.file),
      posterUrl: URL.createObjectURL(media.poster),
      sha256: media.sha256,
      createdAt: now,
      updatedAt: now,
    };
    const state = readState();
    state.media.unshift(asset);
    writeState(state);
    onProgress({ phase: "done", value: 100 });
    return structuredClone(asset);
  }

  async archiveMedia(assetId: string): Promise<MediaAsset> {
    const state = readState();
    const asset = state.media.find((item) => item.id === assetId);
    if (!asset) throw new AdapterError("validation", "找不到媒体");
    asset.status = "archived";
    asset.updatedAt = new Date().toISOString();
    writeState(state);
    return structuredClone(asset);
  }

  async purgeMedia(asset: MediaAsset): Promise<void> {
    const state = readState();
    const manifests = [state.draft.manifest, state.published, ...state.history.map((item) => item.manifest)];
    const references = manifests.reduce(
      (total, manifest) => total + manifest.cards.filter((card) => card.mediaAssetId === asset.id).length,
      0,
    );
    if (references > 0) {
      throw new AdapterError("validation", `该媒体仍有 ${references} 个草稿、线上或历史引用`);
    }
    state.media = state.media.filter((item) => item.id !== asset.id);
    writeState(state);
  }
}
