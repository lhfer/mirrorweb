import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import {
  AdapterError,
  type AdminAdapter,
  type AuthState,
  type ContentManifest,
  type ContentVersion,
  type DraftSnapshot,
  type MediaAsset,
  type PreparedMedia,
  type UploadProgress,
  type WorkspaceSnapshot,
} from "../domain";

type UnknownRow = Record<string, unknown>;

function firstRow(value: unknown): UnknownRow {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate || typeof candidate !== "object") {
    throw new AdapterError("backend", "Supabase 返回了空记录");
  }
  return candidate as UnknownRow;
}

function mapDraft(value: unknown): DraftSnapshot {
  const row = firstRow(value);
  return {
    id: String(row.id ?? "content-draft"),
    manifest: row.manifest as ContentManifest,
    revision: Number(row.revision ?? 0),
    updatedBy: String(row.updated_by ?? row.updatedBy ?? "—"),
    updatedAt: String(row.updated_at ?? row.updatedAt ?? new Date().toISOString()),
  };
}

function mapVersion(value: unknown): ContentVersion {
  const row = firstRow(value);
  return {
    id: String(row.id),
    version: Number(row.version),
    manifest: row.manifest as ContentManifest,
    createdBy: String(row.created_by ?? row.createdBy ?? "—"),
    createdAt: String(row.created_at ?? row.createdAt ?? new Date().toISOString()),
    releaseNote: String(row.release_note ?? row.releaseNote ?? ""),
    draftRevision: row.draftRevision === undefined ? undefined : Number(row.draftRevision),
  };
}

function mapMedia(value: unknown): MediaAsset {
  const row = value as UnknownRow;
  return {
    id: String(row.id),
    originalName: String(row.original_name ?? "untitled.mp4"),
    storagePath: String(row.storage_path ?? ""),
    posterPath: String(row.poster_path ?? ""),
    mimeType: String(row.mime_type ?? "video/mp4"),
    sizeBytes: Number(row.size_bytes ?? 0),
    width: Number(row.width ?? 0),
    height: Number(row.height ?? 0),
    durationMs: Number(row.duration_ms ?? 0),
    status: String(row.status ?? "failed") as MediaAsset["status"],
    mediaUrl: String(row.media_url ?? ""),
    posterUrl: row.poster_url ? String(row.poster_url) : undefined,
    sha256: row.sha256 ? String(row.sha256) : undefined,
    createdAt: String(row.created_at ?? new Date().toISOString()),
    updatedAt: String(row.updated_at ?? new Date().toISOString()),
  };
}

function adapterError(error: { message?: string; code?: string } | null, fallback: string): AdapterError {
  const message = error?.message || fallback;
  const normalized = message.toLocaleLowerCase();
  if (normalized.includes("stale") || normalized.includes("revision") || error?.code === "40001") {
    return new AdapterError("conflict", message);
  }
  if (normalized.includes("forbidden") || normalized.includes("permission") || error?.code === "42501") {
    return new AdapterError("forbidden", message);
  }
  return new AdapterError("backend", message);
}

export function hasSupabaseEnvironment(): boolean {
  if (String(import.meta.env.VITE_CONTENT_ADMIN_LOCAL_MODE ?? "").toLowerCase() === "true") {
    return false;
  }
  return Boolean(
    import.meta.env.VITE_SUPABASE_URL?.trim()
    && import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY?.trim(),
  );
}

export class SupabaseAdminAdapter implements AdminAdapter {
  readonly mode = "supabase" as const;
  private readonly client: SupabaseClient;

  constructor(
    private readonly url = import.meta.env.VITE_SUPABASE_URL.trim(),
    private readonly publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY.trim(),
  ) {
    this.client = createClient(url, publishableKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }

  async getAuthState(): Promise<AuthState> {
    const { data: sessionData, error: sessionError } = await this.client.auth.getSession();
    if (sessionError) throw adapterError(sessionError, "无法恢复管理员会话");
    if (!sessionData.session) return { kind: "anonymous" };

    const { data: userData, error: userError } = await this.client.auth.getUser();
    if (userError || !userData.user) return { kind: "anonymous" };

    const { data: admin, error: adminError } = await this.client
      .from("admin_users")
      .select("user_id,email")
      .eq("user_id", userData.user.id)
      .maybeSingle();
    if (adminError) throw adapterError(adminError, "无法验证管理员白名单");
    if (!admin) return { kind: "forbidden", email: userData.user.email ?? "unknown" };
    return {
      kind: "authenticated",
      actor: { id: userData.user.id, email: String(admin.email ?? userData.user.email ?? "admin") },
    };
  }

  onAuthChange(listener: () => void): () => void {
    const { data } = this.client.auth.onAuthStateChange(() => listener());
    return () => data.subscription.unsubscribe();
  }

  async sendMagicLink(email: string): Promise<void> {
    const redirect = new URL("admin.html", `${location.origin}${location.pathname.replace(/[^/]*$/, "")}`).toString();
    const { error } = await this.client.auth.signInWithOtp({
      email,
      options: {
        shouldCreateUser: false,
        emailRedirectTo: redirect,
      },
    });
    if (error) throw adapterError(error, "Magic Link 发送失败");
  }

  async signOut(): Promise<void> {
    const { error } = await this.client.auth.signOut();
    if (error) throw adapterError(error, "退出失败");
  }

  async loadWorkspace(): Promise<WorkspaceSnapshot> {
    const [draftResult, mediaResult, historyResult, activeResult] = await Promise.all([
      this.client.from("content_drafts").select("id,manifest,revision,updated_by,updated_at").limit(1).single(),
      this.client.from("media_assets").select("*").order("created_at", { ascending: false }),
      this.client.from("content_versions").select("*").order("version", { ascending: false }),
      this.client.rpc("get_active_content_manifest"),
    ]);
    if (draftResult.error) throw adapterError(draftResult.error, "草稿读取失败");
    if (mediaResult.error) throw adapterError(mediaResult.error, "媒体库读取失败");
    if (historyResult.error) throw adapterError(historyResult.error, "历史版本读取失败");
    if (activeResult.error) throw adapterError(activeResult.error, "线上 Manifest 读取失败");

    const activeRow = firstRow(activeResult.data);
    const published = (activeRow.manifest ?? activeRow.active_manifest ?? activeResult.data) as ContentManifest;
    const media = (mediaResult.data ?? []).map(mapMedia);
    for (const asset of media) {
      if (!asset.mediaUrl) {
        asset.mediaUrl = this.client.storage.from("card-media").getPublicUrl(asset.storagePath).data.publicUrl;
      }
      if (!asset.posterUrl && asset.posterPath) {
        asset.posterUrl = this.client.storage.from("card-media").getPublicUrl(asset.posterPath).data.publicUrl;
      }
    }
    return {
      draft: mapDraft(draftResult.data),
      published,
      media,
      history: (historyResult.data ?? []).map(mapVersion),
    };
  }

  async saveDraft(manifest: ContentManifest, expectedRevision: number): Promise<DraftSnapshot> {
    const { data, error } = await this.client.rpc("save_content_draft", {
      expected_revision: expectedRevision,
      manifest,
    });
    if (error) throw adapterError(error, "草稿保存失败");
    return mapDraft(data);
  }

  async publish(expectedRevision: number, releaseNote: string): Promise<ContentVersion> {
    const { data, error } = await this.client.rpc("publish_content", {
      expected_revision: expectedRevision,
      release_note: releaseNote.trim() || null,
    });
    if (error) throw adapterError(error, "发布失败");
    return mapVersion(data);
  }

  async restoreToDraft(versionId: string): Promise<DraftSnapshot> {
    const { data, error } = await this.client.rpc("rollback_content", { version_id: versionId });
    if (error) throw adapterError(error, "恢复草稿失败");
    return mapDraft(data);
  }

  async uploadMedia(
    media: PreparedMedia,
    signal: AbortSignal,
    onProgress: (progress: UploadProgress) => void,
  ): Promise<MediaAsset> {
    const { data: userData, error: userError } = await this.client.auth.getUser();
    if (userError || !userData.user) {
      throw new AdapterError("forbidden", "管理员会话已过期");
    }
    const id = crypto.randomUUID();
    const videoPath = `media/${id}.mp4`;
    const posterPath = `posters/${id}.jpg`;
    const mediaUrl = this.client.storage.from("card-media").getPublicUrl(videoPath).data.publicUrl;
    const posterUrl = this.client.storage.from("card-media").getPublicUrl(posterPath).data.publicUrl;
    const now = new Date().toISOString();
    const uploadingRow = {
      id,
      original_name: media.file.name,
      storage_path: videoPath,
      poster_path: posterPath,
      media_url: mediaUrl,
      poster_url: posterUrl,
      mime_type: media.file.type,
      size_bytes: media.file.size,
      width: media.width,
      height: media.height,
      duration_ms: media.durationMs,
      sha256: media.sha256,
      status: "uploading",
      created_by: userData.user.id,
      created_at: now,
      updated_at: now,
    };
    const { error: insertError } = await this.client.from("media_assets").insert(uploadingRow);
    if (insertError) throw adapterError(insertError, "媒体登记失败");

    const uploadedPaths: string[] = [];
    try {
      await this.uploadObject(videoPath, media.file, signal, (value) => {
        onProgress({ phase: "video", value: 5 + value * 0.65 });
      });
      uploadedPaths.push(videoPath);
      await this.uploadObject(posterPath, media.poster, signal, (value) => {
        onProgress({ phase: "poster", value: 72 + value * 0.18 });
      });
      uploadedPaths.push(posterPath);
      onProgress({ phase: "registering", value: 94 });

      const { data, error } = await this.client
        .from("media_assets")
        .update({ status: "ready", updated_at: new Date().toISOString() })
        .eq("id", id)
        .select("*")
        .single();
      if (error) throw adapterError(error, "媒体 Ready 状态写入失败");
      onProgress({ phase: "done", value: 100 });
      return { ...mapMedia(data), mediaUrl, posterUrl, sha256: media.sha256 };
    } catch (error) {
      if (uploadedPaths.length) {
        await this.client.storage.from("card-media").remove(uploadedPaths).catch(() => undefined);
      }
      await this.client
        .from("media_assets")
        .update({ status: "failed", updated_at: new Date().toISOString() })
        .eq("id", id);
      if (signal.aborted) throw new AdapterError("cancelled", "上传已取消，残留对象已清理");
      throw error instanceof AdapterError ? error : new AdapterError("backend", "媒体上传失败");
    }
  }

  async archiveMedia(assetId: string): Promise<MediaAsset> {
    const { data, error } = await this.client.rpc("archive_media_asset", { media_asset_id: assetId });
    if (error) throw adapterError(error, "媒体归档失败");
    const asset = mapMedia(firstRow(data));
    if (!asset.mediaUrl) {
      asset.mediaUrl = this.client.storage.from("card-media").getPublicUrl(asset.storagePath).data.publicUrl;
    }
    if (!asset.posterUrl && asset.posterPath) {
      asset.posterUrl = this.client.storage.from("card-media").getPublicUrl(asset.posterPath).data.publicUrl;
    }
    return asset;
  }

  async purgeMedia(asset: MediaAsset): Promise<void> {
    const { data: prepared, error: prepareError } = await this.client.rpc("prepare_media_asset_purge", {
      media_asset_id: asset.id,
    });
    if (prepareError) throw adapterError(prepareError, "媒体 purge 准备失败");
    const ticket = firstRow(prepared);
    const storagePath = String(ticket.storagePath ?? asset.storagePath);
    const rawPosterPath = ticket.posterPath === undefined ? (asset.posterPath || null) : ticket.posterPath;
    const posterPath = rawPosterPath === null ? null : String(rawPosterPath);
    const paths = [storagePath, posterPath].filter((path): path is string => Boolean(path));
    const { error: storageError } = await this.client.storage.from("card-media").remove(paths);
    if (storageError) {
      await this.client.rpc("cancel_media_asset_purge", { media_asset_id: asset.id });
      throw adapterError(storageError, "Storage 对象删除失败；purge 已取消");
    }
    const { error: finalizeError } = await this.client.rpc("finalize_media_asset_purge", {
      media_asset_id: asset.id,
      expected_storage_path: storagePath,
      expected_poster_path: posterPath,
    });
    if (finalizeError) throw adapterError(finalizeError, "Storage 已删除，但数据库 purge 未完成");
  }

  private async uploadObject(
    path: string,
    body: Blob,
    signal: AbortSignal,
    onProgress: (value: number) => void,
  ): Promise<void> {
    const { data, error } = await this.client.auth.getSession();
    if (error || !data.session) throw new AdapterError("forbidden", "管理员会话已过期");
    const objectPath = path.split("/").map(encodeURIComponent).join("/");

    await new Promise<void>((resolve, reject) => {
      const request = new XMLHttpRequest();
      const abort = () => request.abort();
      signal.addEventListener("abort", abort, { once: true });
      request.open("POST", `${this.url}/storage/v1/object/card-media/${objectPath}`);
      request.setRequestHeader("apikey", this.publishableKey);
      request.setRequestHeader("Authorization", `Bearer ${data.session.access_token}`);
      request.setRequestHeader("Content-Type", body.type || "application/octet-stream");
      request.setRequestHeader("x-upsert", "false");
      request.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) onProgress(event.loaded / event.total);
      });
      request.addEventListener("load", () => {
        signal.removeEventListener("abort", abort);
        if (request.status >= 200 && request.status < 300) resolve();
        else reject(new AdapterError("backend", `Storage 上传失败 (${request.status})`));
      });
      request.addEventListener("error", () => {
        signal.removeEventListener("abort", abort);
        reject(new AdapterError("backend", "Storage 网络错误"));
      });
      request.addEventListener("abort", () => {
        signal.removeEventListener("abort", abort);
        reject(new AdapterError("cancelled", "上传已取消"));
      });
      request.send(body);
    });
  }
}
