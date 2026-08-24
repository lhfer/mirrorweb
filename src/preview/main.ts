import "../style.css";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import bundledDefault from "../content/default-content.json";
import {
  bootPublicContent,
  installContentManifest,
} from "../content/ContentRepository";

const PREVIEW_STORAGE_KEYS = [
  "mirrorweb.content-admin.preview",
  "mirrorweb.admin.preview-draft",
  "mirrorweb.admin.draft",
] as const;

type PreviewMode = "draft" | "published";
class PreviewAccessHandled extends Error {}

function env(name: "VITE_SUPABASE_URL" | "VITE_SUPABASE_PUBLISHABLE_KEY"): string {
  return String(import.meta.env[name] ?? "").trim();
}

function forcedLocalMode(): boolean {
  return String(import.meta.env.VITE_CONTENT_ADMIN_LOCAL_MODE ?? "").toLowerCase() === "true";
}

function readLocalDraft(): unknown {
  for (const storage of [window.sessionStorage, window.localStorage]) {
    for (const key of PREVIEW_STORAGE_KEYS) {
      const value = storage.getItem(key);
      if (!value) continue;
      try {
        const parsed = JSON.parse(value) as { manifest?: unknown } | unknown;
        if (parsed && typeof parsed === "object" && "manifest" in parsed) {
          return (parsed as { manifest: unknown }).manifest;
        }
        return parsed;
      } catch {
        // A corrupt local preview is ignored; the next known-good source wins.
      }
    }
  }
  return bundledDefault;
}

function renderAccessError(title: string, detail: string, status: number): void {
  document.body.replaceChildren();
  document.body.dataset.previewStatus = String(status);

  const style = document.createElement("style");
  style.textContent = `
    :root { color-scheme: dark; font-family: "Geist Variable", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: #070806; color: #f0efe7; }
    main { width: min(34rem, calc(100vw - 3rem)); border-top: 1px solid #ccff00;
      padding-top: 1.25rem; }
    small { color: #ccff00; font: 600 0.68rem/1.2 "Geist Mono Variable", monospace;
      letter-spacing: .16em; }
    h1 { margin: .9rem 0 .6rem; font-size: clamp(2rem, 8vw, 4.5rem); line-height: .92; }
    p { margin: 0; max-width: 30rem; color: #a6a79f; line-height: 1.55; }
  `;
  const main = document.createElement("main");
  const code = document.createElement("small");
  code.textContent = `PREVIEW ${status}`;
  const heading = document.createElement("h1");
  heading.textContent = title;
  const copy = document.createElement("p");
  copy.textContent = detail;
  main.append(code, heading, copy);
  document.head.append(style);
  document.body.append(main);
  window.parent.postMessage({ type: "mirrorweb-preview-error", status, title }, location.origin);
}

async function requireAdmin(): Promise<SupabaseClient | null> {
  const url = env("VITE_SUPABASE_URL");
  const key = env("VITE_SUPABASE_PUBLISHABLE_KEY");
  if (forcedLocalMode() || !url || !key) return null;

  const client = createClient(url, key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  const { data, error } = await client.auth.getUser();
  if (error || !data.user) {
    renderAccessError(
      "Administrator sign-in required",
      "Open this preview from Content Admin after completing the email Magic Link.",
      401,
    );
    throw new PreviewAccessHandled();
  }

  const { data: admin, error: adminError } = await client
    .from("admin_users")
    .select("user_id")
    .eq("user_id", data.user.id)
    .maybeSingle();
  if (adminError || !admin) {
    renderAccessError(
      "Access forbidden",
      "This authenticated account is not present in the Content Admin allowlist.",
      403,
    );
    throw new PreviewAccessHandled();
  }
  return client;
}

async function loadDraft(client: SupabaseClient | null): Promise<unknown> {
  if (!client) return readLocalDraft();
  const { data, error } = await client
    .from("content_drafts")
    .select("manifest")
    .single();
  if (error || !data?.manifest) throw error ?? new Error("Draft manifest is unavailable");
  return data.manifest;
}

function pinProductionRenderer(): void {
  const query = new URLSearchParams(location.search);
  query.set("composition", "sourceExact");
  query.set("opticalBody", "target-source-unclamped");
  history.replaceState(null, "", `${location.pathname}?${query}${location.hash}`);
}

async function start(): Promise<void> {
  const mode: PreviewMode = new URLSearchParams(location.search).get("content") === "published"
    ? "published"
    : "draft";
  const client = await requireAdmin();

  if (mode === "draft") {
    installContentManifest(await loadDraft(client), "draft-preview");
  } else {
    await bootPublicContent();
  }

  pinProductionRenderer();
  const { startGridPreviewV4 } = await import("../v4/preview/entry");
  await startGridPreviewV4({ opticalBody: "target-source-unclamped" });
  document.body.dataset.previewMode = mode;
  window.parent.postMessage(
    { type: "mirrorweb-preview-ready", mode, schemaVersion: 1 },
    location.origin,
  );
}

await start().catch((error: unknown) => {
  if (error instanceof PreviewAccessHandled || document.body.dataset.previewStatus) return;
  const message = error instanceof Error ? error.message : "The draft could not be rendered.";
  renderAccessError("Preview unavailable", message, 500);
});
