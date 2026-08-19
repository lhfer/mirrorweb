/**
 * Reviewer Mode transport.
 *
 * Two properties matter here and are asserted by the Phase 1B tests:
 *   1. This client only ever talks to the reviewer endpoints. It never reads
 *      and never writes qa-v4/reference/frozen-visual/annotations.private.json.
 *   2. Saving is automatic. The caller marks the draft dirty, this module
 *      coalesces writes, keeps the ETag, and reports SAVING / SAVED / FAILED.
 */

import type { ReviewerApiPayload, ReviewerState } from "./types";

const API_ROOT = "/__phase1b_review__";
const REVIEWER_STATE_URL = `${API_ROOT}/reviewer/state`;
const SAVE_DEBOUNCE_MS = 280;

export type SaveStatus = "IDLE" | "SAVING" | "SAVED" | "FAILED";

export async function fetchReviewerState(): Promise<ReviewerApiPayload> {
  const response = await fetch(REVIEWER_STATE_URL, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`Reviewer API returned HTTP ${response.status}`);
  if (!(response.headers.get("content-type") ?? "").includes("application/json")) {
    throw new Error("Reviewer API did not return JSON");
  }
  const payload = (await response.json()) as ReviewerApiPayload;
  if (!payload || typeof payload.csrfToken !== "string" || typeof payload.etag !== "string") {
    throw new Error("Reviewer API response is missing its identity fields");
  }
  if (!Array.isArray(payload.roles) || payload.roles.length === 0) {
    throw new Error("Reviewer API returned no role evidence");
  }
  return payload;
}

export async function sha256Hex(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const source = bytes instanceof Uint8Array ? (bytes.slice().buffer as ArrayBuffer) : bytes;
  const digest = await crypto.subtle.digest("SHA-256", source);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

/** Fetches a private image and refuses to display anything that is not hash bound. */
export async function loadVerifiedImage(url: string, expectedSha256: string): Promise<HTMLImageElement> {
  const response = await fetch(url, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "image/png,image/jpeg,image/webp" },
  });
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.startsWith("image/")) throw new Error(`${url} is not an image response`);
  const buffer = await response.arrayBuffer();
  const actual = await sha256Hex(buffer);
  if (actual !== expectedSha256) throw new Error(`${url} does not match its bound hash`);
  const blobUrl = URL.createObjectURL(new Blob([buffer], { type: contentType }));
  const image = new Image();
  image.decoding = "sync";
  await new Promise<void>((resolve, reject) => {
    image.onload = () => resolve();
    image.onerror = () => reject(new Error(`${url} failed image decoding`));
    image.src = blobUrl;
  });
  return image;
}

export class ReviewerStore {
  private etag: string;
  private readonly csrfToken: string;
  private timer = 0;
  private inFlight: Promise<void> | null = null;
  private pending = false;
  private lastError: string | null = null;
  private status: SaveStatus = "IDLE";

  constructor(
    initial: ReviewerApiPayload,
    private state: ReviewerState,
    private readonly onStatus: (status: SaveStatus, detail: string | null) => void,
  ) {
    this.etag = initial.etag;
    this.csrfToken = initial.csrfToken;
  }

  snapshot(): ReviewerState {
    return this.state;
  }

  replace(state: ReviewerState): void {
    this.state = state;
  }

  saveStatus(): SaveStatus {
    return this.status;
  }

  saveError(): string | null {
    return this.lastError;
  }

  /** Coalesced autosave; every mutation calls this and nothing else. */
  queue(): void {
    this.pending = true;
    this.setStatus("SAVING", null);
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => void this.flush(), SAVE_DEBOUNCE_MS);
  }

  async flush(): Promise<void> {
    if (this.inFlight) {
      await this.inFlight.catch(() => {});
      if (!this.pending) return;
    }
    if (!this.pending) return;
    this.pending = false;
    this.inFlight = this.write();
    try {
      await this.inFlight;
    } finally {
      this.inFlight = null;
    }
  }

  private async write(): Promise<void> {
    this.setStatus("SAVING", null);
    try {
      const response = await fetch(REVIEWER_STATE_URL, {
        method: "PUT",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Phase1B-CSRF": this.csrfToken,
          "If-Match": this.etag,
        },
        body: JSON.stringify(this.state),
      });
      if (!response.ok) {
        const detail = (await response.text()).slice(0, 400);
        throw new Error(`HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
      }
      const payload = (await response.json()) as { etag: string; state: ReviewerState };
      // Only the ETag is adopted. The in-memory draft stays authoritative so a
      // response that lands after a newer edit cannot roll that edit back.
      this.etag = payload.etag;
      this.setStatus("SAVED", null);
    } catch (error) {
      this.pending = true;
      this.setStatus("FAILED", error instanceof Error ? error.message : String(error));
    }
  }

  private setStatus(status: SaveStatus, detail: string | null): void {
    this.status = status;
    this.lastError = detail;
    this.onStatus(status, detail);
  }
}
