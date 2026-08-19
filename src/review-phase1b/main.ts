import "./review.css";
import {
  ASSET_KINDS,
  CORNER_IDS,
  FEATURE_IDS,
  ROLE_IDS,
  type AssetKind,
  type CoordinateView,
  type FeatureId,
  type NormalizedPoint,
  type NormalizedQuad,
  type OverlayId,
  type ReviewAnnotations,
  type ReviewApiState,
  type ReviewRoleEvidence,
  type ReviewStatus,
  type RoiId,
  type RoleId,
  type SaveApiResponse,
  type ZoneDraft,
} from "./types";
import {
  parseReviewState,
  quadFrom,
  validateQuad,
  validateZoneDraft,
  zoneDraftFrom,
} from "./validation";
import { boundariesFromWidths, widthsFromBoundaries, withBoundaryAt } from "./zone-model";

const API_ROOT = "/__phase1b_review__";
const SVG_NS = "http://www.w3.org/2000/svg";
const ROLE_LABELS: Record<RoleId, string> = {
  bright: "Bright",
  dark: "Dark",
  highTexture: "High Texture",
  lowTexture: "Low Texture",
  front: "Front",
  leftTilt: "Left Tilt",
  rightTilt: "Right Tilt",
};
const FEATURE_LABELS: Record<FeatureId, { name: string; detail: string }> = {
  edge: { name: "Edge structure", detail: "Silhouette, four edges, four corners" },
  highlight: { name: "Highlight", detail: "Width, position, clipping and path" },
  dispersion: { name: "Dispersion", detail: "Outer-rim chroma localization" },
  sharpness: { name: "Sharpness", detail: "Center / rim sharpness profile" },
};
const CORNER_LABELS = ["TL", "TR", "BR", "BL"] as const;
const ROI_LABELS: Record<RoiId, string> = {
  all: "FULL CARD PLANE",
  topLeft: "TOP LEFT CORNER",
  top: "TOP EDGE",
  topRight: "TOP RIGHT CORNER",
  left: "LEFT EDGE",
  right: "RIGHT EDGE",
  bottomLeft: "BOTTOM LEFT CORNER",
  bottom: "BOTTOM EDGE",
  bottomRight: "BOTTOM RIGHT CORNER",
};
const ROI_ORIGINS: Record<RoiId, [number, number]> = {
  all: [50, 50],
  topLeft: [9, 9],
  top: [50, 9],
  topRight: [91, 9],
  left: [9, 50],
  right: [91, 50],
  bottomLeft: [9, 91],
  bottom: [50, 91],
  bottomRight: [91, 91],
};

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`Review UI is missing ${selector}`);
  return element;
}

const dom = {
  globalStatus: requiredElement<HTMLElement>("#global-status"),
  saveState: requiredElement<HTMLElement>("#save-state"),
  saveButton: requiredElement<HTMLButtonElement>("#save-button"),
  roleProgress: requiredElement<HTMLElement>("#role-progress"),
  roleList: requiredElement<HTMLElement>("#role-list"),
  evidenceDot: requiredElement<HTMLElement>("#evidence-dot"),
  evidenceFrozen: requiredElement<HTMLElement>("#evidence-frozen"),
  evidenceHead: requiredElement<HTMLElement>("#evidence-head"),
  evidenceRuntime: requiredElement<HTMLElement>("#evidence-runtime"),
  evidenceBundle: requiredElement<HTMLElement>("#evidence-bundle"),
  evidencePrivate: requiredElement<HTMLElement>("#evidence-private"),
  viewButtons: [...document.querySelectorAll<HTMLButtonElement>("[data-view]")],
  overlayButtons: [...document.querySelectorAll<HTMLButtonElement>("[data-overlay]")],
  resetViewButton: requiredElement<HTMLButtonElement>("#reset-view-button"),
  roiButtons: [...document.querySelectorAll<HTMLButtonElement>("[data-roi]")],
  roiOutput: requiredElement<HTMLElement>("#roi-output"),
  roiHint: requiredElement<HTMLElement>("#roi-hint"),
  targetStage: requiredElement<HTMLElement>("#target-stage"),
  localStage: requiredElement<HTMLElement>("#local-stage"),
  targetBase: requiredElement<HTMLImageElement>("#target-base"),
  localBase: requiredElement<HTMLImageElement>("#local-base"),
  targetEdge: requiredElement<HTMLImageElement>("#target-edge"),
  localEdge: requiredElement<HTMLImageElement>("#local-edge"),
  targetHighlight: requiredElement<HTMLImageElement>("#target-highlight"),
  localHighlight: requiredElement<HTMLImageElement>("#local-highlight"),
  targetDispersion: requiredElement<HTMLImageElement>("#target-dispersion"),
  localDispersion: requiredElement<HTMLImageElement>("#local-dispersion"),
  targetAnalysis: requiredElement<HTMLCanvasElement>("#target-sharpness"),
  localAnalysis: requiredElement<HTMLCanvasElement>("#local-sharpness"),
  targetSvg: requiredElement<SVGSVGElement>("#target-annotation"),
  localSvg: requiredElement<SVGSVGElement>("#local-annotation"),
  targetEvidenceLabel: requiredElement<HTMLElement>("#target-evidence-label"),
  localEvidenceLabel: requiredElement<HTMLElement>("#local-evidence-label"),
  activeRoleIndex: requiredElement<HTMLElement>("#active-role-index"),
  activeRoleStatus: requiredElement<HTMLElement>("#active-role-status"),
  activeRoleName: requiredElement<HTMLElement>("#active-role-name"),
  activeRoleCategory: requiredElement<HTMLElement>("#active-role-category"),
  reusedFrameNote: requiredElement<HTMLElement>("#reused-frame-note"),
  cornerInputs: requiredElement<HTMLElement>("#corner-inputs"),
  quadStatus: requiredElement<HTMLOutputElement>("#quad-status"),
  quadError: requiredElement<HTMLElement>("#quad-error"),
  quadApproval: requiredElement<HTMLInputElement>("#quad-approval"),
  zoneInputs: requiredElement<HTMLElement>("#zone-inputs"),
  zoneStatus: requiredElement<HTMLOutputElement>("#zone-status"),
  zoneError: requiredElement<HTMLElement>("#zone-error"),
  zoneApproval: requiredElement<HTMLInputElement>("#zone-approval"),
  zoneWidthSidewall: requiredElement<HTMLElement>("#zone-width-sidewall"),
  zoneWidthRim: requiredElement<HTMLElement>("#zone-width-rim"),
  zoneWidthShoulder: requiredElement<HTMLElement>("#zone-width-shoulder"),
  zoneWidthCenter: requiredElement<HTMLElement>("#zone-width-center"),
  featureDecisions: requiredElement<HTMLElement>("#feature-decisions"),
  featureStatus: requiredElement<HTMLOutputElement>("#feature-status"),
  decisionReadiness: requiredElement<HTMLOutputElement>("#decision-readiness"),
  roleNotes: requiredElement<HTMLTextAreaElement>("#role-notes"),
  notesCount: requiredElement<HTMLElement>("#notes-count"),
  rejectRole: requiredElement<HTMLButtonElement>("#reject-role"),
  approveRole: requiredElement<HTMLButtonElement>("#approve-role"),
  decisionHelp: requiredElement<HTMLElement>("#decision-help"),
  precisionGate: requiredElement<HTMLElement>("#precision-gate"),
  blockingGate: requiredElement<HTMLElement>("#blocking-gate"),
  blockingTitle: requiredElement<HTMLElement>("#blocking-title"),
  blockingMessage: requiredElement<HTMLElement>("#blocking-message"),
  blockingDetails: requiredElement<HTMLElement>("#blocking-details"),
  retryButton: requiredElement<HTMLButtonElement>("#retry-button"),
  toast: requiredElement<HTMLElement>("#toast"),
};

let apiState: ReviewApiState | null = null;
let roles: ReviewRoleEvidence[] = [];
let annotations: ReviewAnnotations | null = null;
let activeRoleId: RoleId = ROLE_IDS[0];
let coordinateView: CoordinateView = "source";
let activeRoi: RoiId = "all";
let activeOverlays = new Set<OverlayId>(["edge"]);
let dirty = false;
let saving = false;
let blocked = true;
let assetReady = false;
const invalidCategories = new Set<string>();
let loadGeneration = 0;
let toastTimer = 0;
let pointerDrag: { cornerIndex: number; pointerId: number } | null = null;
let assetUrls = new Map<AssetKind, string>();
const workingQuads = new Map<string, NormalizedQuad>();
const workingZones = new Map<string, ZoneDraft>();

function cloneQuad(quad: NormalizedQuad): NormalizedQuad {
  return quad.map(([x, y]) => [x, y]) as NormalizedQuad;
}

function shortHash(value: string, size = 10): string {
  return `${value.slice(0, size)}…`;
}

function activeRole(): ReviewRoleEvidence {
  const role = roles.find((entry) => entry.id === activeRoleId);
  if (!role) throw new Error(`Unknown role ${activeRoleId}`);
  return role;
}

function activeCategory() {
  if (!annotations) throw new Error("Annotations are not bound");
  const role = activeRole();
  const category = annotations.categories[role.targetCategory];
  if (!category) throw new Error(`Missing category ${role.targetCategory}`);
  return category;
}

function activeRoleAnnotation() {
  if (!annotations) throw new Error("Annotations are not bound");
  return annotations.roles[activeRoleId];
}

function currentQuad(): NormalizedQuad {
  const role = activeRole();
  const quad = workingQuads.get(role.targetCategory);
  if (!quad) throw new Error(`${role.targetCategory} has no working quad`);
  return quad;
}

function currentZones(): ZoneDraft {
  const role = activeRole();
  const zones = workingZones.get(role.targetCategory);
  if (!zones) throw new Error(`${role.targetCategory} has no working zones`);
  return zones;
}

function precisionEligible(): boolean {
  return window.innerWidth >= 980 && window.matchMedia("(pointer: fine)").matches;
}

function setStatus(element: HTMLElement, status: string): void {
  element.dataset.status = status;
  element.textContent = status;
}

function showToast(message: string, tone: "neutral" | "success" | "danger" = "neutral"): void {
  window.clearTimeout(toastTimer);
  dom.toast.textContent = message;
  dom.toast.dataset.tone = tone;
  dom.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    dom.toast.hidden = true;
  }, 3200);
}

function setBlocked(title: string, message: string, details = ""): void {
  blocked = true;
  dom.blockingTitle.textContent = title;
  dom.blockingMessage.textContent = message;
  dom.blockingDetails.textContent = details;
  dom.blockingDetails.hidden = details.length === 0;
  dom.blockingGate.hidden = false;
  dom.saveState.textContent = "BLOCKED";
  updateActionState();
}

function clearBlocked(): void {
  blocked = false;
  dom.blockingGate.hidden = true;
  dom.blockingDetails.textContent = "";
  updatePrecisionGate();
  updateActionState();
}

function markDirty(message = "UNSAVED CHANGES"): void {
  dirty = true;
  dom.saveState.textContent = message;
  dom.saveState.dataset.dirty = "true";
  updateActionState();
}

function markClean(message = "SAVED LOCALLY"): void {
  dirty = false;
  dom.saveState.textContent = message;
  dom.saveState.dataset.dirty = "false";
  updateActionState();
}

function updatePrecisionGate(): void {
  const eligible = precisionEligible();
  dom.precisionGate.hidden = eligible;
  document.body.dataset.precision = eligible ? "fine" : "blocked";
  dom.quadApproval.disabled = !eligible || blocked;
  dom.zoneApproval.disabled = !eligible || blocked;
  updateActionState();
}

function roleAssets(role: ReviewRoleEvidence): NonNullable<ReviewRoleEvidence["assets"]> {
  if (!role.assets) throw new Error(`${role.id} has no asset evidence`);
  return role.assets;
}

function expectedAssetSha(role: ReviewRoleEvidence, kind: AssetKind): string {
  const asset = roleAssets(role)[kind];
  if (typeof asset === "string") return asset;
  if (asset && typeof asset.sha256 === "string") return asset.sha256;
  throw new Error(`${role.id}/${kind} is not hash bound`);
}

async function sha256(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function verifyImageBlob(role: ReviewRoleEvidence, kind: AssetKind): Promise<string> {
  const response = await fetch(`${API_ROOT}/asset/${role.id}/${kind}`, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { Accept: "image/png,image/jpeg,image/webp" },
  });
  if (!response.ok) throw new Error(`${role.id}/${kind} returned HTTP ${response.status}`);
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.startsWith("image/")) throw new Error(`${role.id}/${kind} is not an image response`);
  const buffer = await response.arrayBuffer();
  const actualSha = await sha256(buffer);
  const expectedSha = expectedAssetSha(role, kind);
  if (actualSha !== expectedSha) throw new Error(`${role.id}/${kind} hash mismatch`);
  const blobUrl = URL.createObjectURL(new Blob([buffer], { type: contentType }));
  const probe = new Image();
  const loaded = new Promise<void>((resolve, reject) => {
    probe.onload = () => resolve();
    probe.onerror = () => reject(new Error(`${role.id}/${kind} failed image decoding`));
  });
  probe.src = blobUrl;
  await loaded;
  const metadata = roleAssets(role)[kind];
  if (typeof metadata === "object" && metadata) {
    if (typeof metadata.width === "number" && metadata.width !== probe.naturalWidth) {
      URL.revokeObjectURL(blobUrl);
      throw new Error(`${role.id}/${kind} width mismatch`);
    }
    if (typeof metadata.height === "number" && metadata.height !== probe.naturalHeight) {
      URL.revokeObjectURL(blobUrl);
      throw new Error(`${role.id}/${kind} height mismatch`);
    }
  }
  return blobUrl;
}

function revokeAssetUrls(urls = assetUrls): void {
  for (const url of urls.values()) URL.revokeObjectURL(url);
  urls.clear();
}

async function loadRoleAssets(): Promise<void> {
  const role = activeRole();
  const generation = ++loadGeneration;
  assetReady = false;
  updateActionState();
  for (const stage of [dom.targetStage, dom.localStage]) {
    stage.classList.add("is-loading");
    stage.querySelector<HTMLElement>(".stage-loading")!.hidden = false;
  }

  const pending = new Map<AssetKind, string>();
  try {
    const values = await Promise.all(
      ASSET_KINDS.map(async (kind) => [kind, await verifyImageBlob(role, kind)] as const),
    );
    if (generation !== loadGeneration) {
      for (const [, url] of values) URL.revokeObjectURL(url);
      return;
    }
    for (const [kind, url] of values) pending.set(kind, url);
    revokeAssetUrls();
    assetUrls = pending;
    await updateDisplayedAssets();
    assetReady = true;
    for (const stage of [dom.targetStage, dom.localStage]) {
      stage.classList.remove("is-loading");
      stage.querySelector<HTMLElement>(".stage-loading")!.hidden = true;
    }
    updateActionState();
  } catch (error) {
    revokeAssetUrls(pending);
    if (generation !== loadGeneration) return;
    const detail = error instanceof Error ? error.message : String(error);
    setBlocked(
      "Private asset verification failed",
      "This role cannot be reviewed because at least one runtime image is missing, undecodable, or not the hash-bound evidence.",
      detail,
    );
  }
}

function assignImage(image: HTMLImageElement, url: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (image.src === url && image.complete && image.naturalWidth > 0) {
      resolve();
      return;
    }
    image.onload = () => resolve();
    image.onerror = () => reject(new Error(`${image.id} failed to display verified pixels`));
    image.src = url;
  });
}

async function updateDisplayedAssets(): Promise<void> {
  const targetBaseKind: AssetKind = coordinateView === "source" ? "target-source" : "target-plane";
  const localBaseKind: AssetKind = coordinateView === "source" ? "local-source" : "local-plane";
  const required = [targetBaseKind, localBaseKind, "target-edge", "target-highlight", "local-edge", "local-highlight", "local-dispersion", "local-zones"] as const;
  for (const kind of required) {
    if (!assetUrls.has(kind)) throw new Error(`Verified runtime asset ${kind} is unavailable`);
  }
  await Promise.all([
    assignImage(dom.targetBase, assetUrls.get(targetBaseKind)!),
    assignImage(dom.localBase, assetUrls.get(localBaseKind)!),
    assignImage(dom.targetEdge, assetUrls.get("target-edge")!),
    assignImage(dom.targetHighlight, assetUrls.get("target-highlight")!),
    assignImage(dom.localEdge, assetUrls.get(coordinateView === "source" ? "local-zones" : "local-edge")!),
    assignImage(dom.localHighlight, assetUrls.get("local-highlight")!),
    assignImage(dom.localDispersion, assetUrls.get("local-dispersion")!),
  ]);
  drawAnnotationLayers();
  applyViewTransform();
  updateOverlays();
}

function svgNode<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attributes: Record<string, string | number>,
): SVGElementTagNameMap[K] {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, String(value));
  return element;
}

function scaledQuad(quad: NormalizedQuad, width: number, height: number): NormalizedQuad {
  return quad.map(([x, y]) => [x * width, y * height]) as NormalizedQuad;
}

function quadPoint(quad: NormalizedQuad, u: number, v: number): NormalizedPoint {
  const top: NormalizedPoint = [
    quad[0][0] + (quad[1][0] - quad[0][0]) * u,
    quad[0][1] + (quad[1][1] - quad[0][1]) * u,
  ];
  const bottom: NormalizedPoint = [
    quad[3][0] + (quad[2][0] - quad[3][0]) * u,
    quad[3][1] + (quad[2][1] - quad[3][1]) * u,
  ];
  return [top[0] + (bottom[0] - top[0]) * v, top[1] + (bottom[1] - top[1]) * v];
}

function quadPoints(quad: NormalizedQuad): string {
  return quad.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function insetQuad(quad: NormalizedQuad, inwardRatio: number): NormalizedQuad {
  const center: NormalizedPoint = [
    quad.reduce((sum, point) => sum + point[0], 0) / 4,
    quad.reduce((sum, point) => sum + point[1], 0) / 4,
  ];
  const scale = Math.max(0.04, 1 - inwardRatio * 2);
  return quad.map(([x, y]) => [center[0] + (x - center[0]) * scale, center[1] + (y - center[1]) * scale]) as NormalizedQuad;
}

function roiCell(quad: NormalizedQuad, roi: RoiId): NormalizedQuad | null {
  if (roi === "all") return null;
  const cells: Record<Exclude<RoiId, "all">, [number, number]> = {
    topLeft: [0, 0], top: [1, 0], topRight: [2, 0],
    left: [0, 1], right: [2, 1],
    bottomLeft: [0, 2], bottom: [1, 2], bottomRight: [2, 2],
  };
  const [column, row] = cells[roi];
  const u0 = column / 3;
  const u1 = (column + 1) / 3;
  const v0 = row / 3;
  const v1 = (row + 1) / 3;
  return [quadPoint(quad, u0, v0), quadPoint(quad, u1, v0), quadPoint(quad, u1, v1), quadPoint(quad, u0, v1)];
}

function drawCardOverlay(
  svg: SVGSVGElement,
  image: HTMLImageElement,
  side: "target" | "local",
): void {
  const width = image.naturalWidth || 1;
  const height = image.naturalHeight || 1;
  svg.replaceChildren();
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  const normalized: NormalizedQuad = coordinateView === "plane"
    ? [[0.02, 0.03], [0.98, 0.03], [0.98, 0.97], [0.02, 0.97]]
    : side === "target"
      ? currentQuad()
      : [[0, 0], [1, 0], [1, 1], [0, 1]];
  const quad = scaledQuad(normalized, width, height);
  const shouldShowGeometry = side === "target" || coordinateView === "plane";
  if (!shouldShowGeometry) return;

  const geometry = svgNode("g", { class: "card-geometry" });
  geometry.append(svgNode("polygon", { class: "card-plane-outline", points: quadPoints(quad) }));

  for (const t of [1 / 3, 2 / 3]) {
    const verticalStart = quadPoint(quad, t, 0);
    const verticalEnd = quadPoint(quad, t, 1);
    const horizontalStart = quadPoint(quad, 0, t);
    const horizontalEnd = quadPoint(quad, 1, t);
    geometry.append(
      svgNode("line", { class: "roi-grid-line", x1: verticalStart[0], y1: verticalStart[1], x2: verticalEnd[0], y2: verticalEnd[1] }),
      svgNode("line", { class: "roi-grid-line", x1: horizontalStart[0], y1: horizontalStart[1], x2: horizontalEnd[0], y2: horizontalEnd[1] }),
    );
  }
  const cell = roiCell(quad, activeRoi);
  if (cell) geometry.append(svgNode("polygon", { class: "roi-selection", points: quadPoints(cell) }));

  if (side === "target" && activeOverlays.has("edge")) {
    const zones = currentZones();
    const boundaries = [
      [zones.sidewallToStrongLensRim, "zone-boundary zone-boundary--sidewall"],
      [zones.strongLensRimToOpticalShoulder, "zone-boundary zone-boundary--rim"],
      [zones.opticalShoulderToCenterFace, "zone-boundary zone-boundary--shoulder"],
    ] as const;
    for (const [ratio, className] of boundaries) {
      geometry.append(svgNode("polygon", { class: className, points: quadPoints(insetQuad(quad, ratio)) }));
    }
  }
  svg.append(geometry);

  if (side === "target" && coordinateView === "source") {
    const handles = svgNode("g", { class: "corner-handles" });
    quad.forEach(([x, y], index) => {
      const hit = svgNode("circle", {
        class: "corner-handle-hit",
        cx: x,
        cy: y,
        r: Math.max(16, Math.min(width, height) * 0.018),
        tabindex: 0,
        role: "slider",
        "aria-label": `${CORNER_LABELS[index]} card corner`,
        "aria-valuetext": `${(normalized[index][0] * 100).toFixed(2)}%, ${(normalized[index][1] * 100).toFixed(2)}%`,
        "data-corner-index": index,
      });
      const dot = svgNode("circle", {
        class: "corner-handle-dot",
        cx: x,
        cy: y,
        r: Math.max(4, Math.min(width, height) * 0.005),
      });
      const label = svgNode("text", {
        class: "corner-handle-label",
        x: x + Math.max(9, width * 0.008),
        y: y - Math.max(9, height * 0.012),
      });
      label.textContent = CORNER_LABELS[index];
      handles.append(hit, dot, label);
    });
    svg.append(handles);
  }
}

function drawAnnotationLayers(): void {
  if (!annotations || !roles.length || !dom.targetBase.complete || !dom.localBase.complete) return;
  drawCardOverlay(dom.targetSvg, dom.targetBase, "target");
  drawCardOverlay(dom.localSvg, dom.localBase, "local");
}

function rgbaComposite(target: Uint8ClampedArray, offset: number, color: [number, number, number], alpha: number): void {
  if (alpha <= 0) return;
  const currentAlpha = target[offset + 3] / 255;
  const outAlpha = Math.min(1, currentAlpha + alpha * (1 - currentAlpha));
  if (outAlpha <= 0) return;
  target[offset] = Math.min(255, target[offset] + color[0] * alpha);
  target[offset + 1] = Math.min(255, target[offset + 1] + color[1] * alpha);
  target[offset + 2] = Math.min(255, target[offset + 2] + color[2] * alpha);
  target[offset + 3] = Math.round(outAlpha * 255);
}

function renderAnalysisOverlay(image: HTMLImageElement, canvas: HTMLCanvasElement, side: "target" | "local"): void {
  const computed = {
    edge: coordinateView === "plane" && activeOverlays.has("edge"),
    highlight: coordinateView === "plane" && activeOverlays.has("highlight"),
    dispersion: activeOverlays.has("dispersion") && (coordinateView === "plane" || side === "target"),
    sharpness: activeOverlays.has("sharpness"),
  };
  if (!Object.values(computed).some(Boolean) || !image.naturalWidth || !image.naturalHeight) {
    canvas.hidden = true;
    return;
  }
  const scale = Math.min(1, 720 / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(2, Math.round(image.naturalWidth * scale));
  const height = Math.max(2, Math.round(image.naturalHeight * scale));
  canvas.width = width;
  canvas.height = height;
  const work = document.createElement("canvas");
  work.width = width;
  work.height = height;
  const workContext = work.getContext("2d", { willReadFrequently: true });
  const context = canvas.getContext("2d");
  if (!workContext || !context) throw new Error("Canvas analysis is unavailable");
  workContext.drawImage(image, 0, 0, width, height);
  const source = workContext.getImageData(0, 0, width, height).data;
  const output = context.createImageData(width, height);
  const luma = new Float32Array(width * height);
  const histogram = new Uint32Array(256);
  for (let index = 0; index < width * height; index += 1) {
    const offset = index * 4;
    const value = source[offset] * 0.2126 + source[offset + 1] * 0.7152 + source[offset + 2] * 0.0722;
    luma[index] = value;
    histogram[Math.max(0, Math.min(255, Math.round(value)))] += 1;
  }
  let cumulative = 0;
  let highlightThreshold = 235;
  const percentile = width * height * 0.975;
  for (let value = 0; value < 256; value += 1) {
    cumulative += histogram[value];
    if (cumulative >= percentile) {
      highlightThreshold = Math.max(180, value);
      break;
    }
  }
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      const offset = index * 4;
      const gx = luma[index + 1] - luma[index - 1];
      const gy = luma[index + width] - luma[index - width];
      const gradient = Math.min(1, Math.hypot(gx, gy) / 88);
      const r = source[offset];
      const g = source[offset + 1];
      const b = source[offset + 2];
      const chroma = (Math.max(r, g, b) - Math.min(r, g, b)) / 255;
      if (computed.edge) rgbaComposite(output.data, offset, [201, 243, 91], Math.max(0, gradient - 0.16) * 0.8);
      if (computed.highlight) {
        const energy = Math.max(0, (luma[index] - highlightThreshold) / Math.max(1, 255 - highlightThreshold));
        rgbaComposite(output.data, offset, [255, 236, 170], energy * 0.9);
      }
      if (computed.dispersion) rgbaComposite(output.data, offset, [238, 84, 208], Math.max(0, chroma - 0.08) * 0.7);
      if (computed.sharpness) rgbaComposite(output.data, offset, [82, 210, 224], Math.max(0, gradient - 0.06) * 0.72);
    }
  }
  context.putImageData(output, 0, 0);
  canvas.hidden = false;
}

function updateOverlays(): void {
  const sourceView = coordinateView === "source";
  dom.targetEdge.hidden = !(coordinateView === "plane" && activeOverlays.has("edge"));
  dom.localEdge.hidden = !activeOverlays.has("edge");
  dom.targetHighlight.hidden = !(sourceView && activeOverlays.has("highlight"));
  dom.localHighlight.hidden = !(sourceView && activeOverlays.has("highlight"));
  dom.targetDispersion.hidden = true;
  dom.localDispersion.hidden = !(sourceView && activeOverlays.has("dispersion"));
  if (assetReady || (dom.targetBase.complete && dom.localBase.complete)) {
    renderAnalysisOverlay(dom.targetBase, dom.targetAnalysis, "target");
    renderAnalysisOverlay(dom.localBase, dom.localAnalysis, "local");
  }
  drawAnnotationLayers();
}

function applyViewTransform(): void {
  const planeZoom = coordinateView === "plane" && activeRoi !== "all";
  const [originX, originY] = ROI_ORIGINS[activeRoi];
  for (const stage of [dom.targetStage, dom.localStage]) {
    stage.classList.toggle("is-plane", coordinateView === "plane");
    stage.classList.toggle("is-roi-zoom", planeZoom);
    stage.style.setProperty("--roi-origin-x", `${originX}%`);
    stage.style.setProperty("--roi-origin-y", `${originY}%`);
  }
  dom.roiHint.textContent = coordinateView === "plane"
    ? activeRoi === "all"
      ? "Select an edge or corner to magnify the same normalized region."
      : "Both card planes are magnified around the same normalized region."
    : "Switch to Card Plane to magnify this normalized region; the source frame keeps full context.";
}

function invalidateRolesForCategory(categoryId: string): void {
  if (!annotations) return;
  for (const role of roles) {
    if (role.targetCategory === categoryId) annotations.roles[role.id].reviewStatus = "PENDING";
  }
  annotations.categories[categoryId].reviewStatus = "PENDING";
}

function recomputeCategoryStatus(categoryId: string): void {
  if (!annotations) return;
  const category = annotations.categories[categoryId];
  const linkedRoles = roles.filter((role) => role.targetCategory === categoryId);
  const linkedAnnotations = linkedRoles.map((role) => annotations!.roles[role.id]);
  category.approvals.existingHighlightMask = linkedAnnotations.every(
    (role) => role.featureDecisions.highlight === "APPROVED",
  );
  category.approvals.naturalFeatureSignature = linkedAnnotations.every((role) =>
    FEATURE_IDS.every((feature) => role.featureDecisions[feature] === "APPROVED"),
  );
  if (category.quadReviewStatus === "REJECTED" || category.zoneReviewStatus === "REJECTED") {
    category.reviewStatus = "REJECTED";
  } else if (
    linkedAnnotations.every((role) => role.reviewStatus === "APPROVED") &&
    category.quadReviewStatus === "APPROVED" &&
    category.zoneReviewStatus === "APPROVED"
  ) category.reviewStatus = "APPROVED";
  else category.reviewStatus = "PENDING";
}

function storeWorkingQuad(invalidateApproval = true): boolean {
  if (!annotations) return false;
  const role = activeRole();
  const category = activeCategory();
  try {
    const validated = validateQuad(currentQuad(), `${role.id}.quad`);
    invalidCategories.delete(`${role.targetCategory}:quad`);
    dom.quadError.hidden = true;
    category.quadNormalized = cloneQuad(validated);
    if (invalidateApproval) {
      category.quadReviewStatus = "PENDING";
      invalidateRolesForCategory(role.targetCategory);
    }
    return true;
  } catch (error) {
    invalidCategories.add(`${role.targetCategory}:quad`);
    dom.quadError.textContent = error instanceof Error ? error.message : String(error);
    dom.quadError.hidden = false;
    category.quadReviewStatus = "PENDING";
    invalidateRolesForCategory(role.targetCategory);
    return false;
  }
}

function setQuadPoint(index: number, x: number, y: number, focusAfter = false): void {
  const role = activeRole();
  const quad = cloneQuad(currentQuad());
  quad[index] = [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))];
  workingQuads.set(role.targetCategory, quad);
  storeWorkingQuad(true);
  markDirty();
  renderCornerInputs();
  drawAnnotationLayers();
  updateInspectorState();
  if (focusAfter) {
    requestAnimationFrame(() => {
      dom.targetSvg.querySelector<SVGElement>(`[data-corner-index="${index}"]`)?.focus();
    });
  }
}

function renderCornerInputs(): void {
  const quad = currentQuad();
  dom.cornerInputs.replaceChildren();
  quad.forEach(([x, y], index) => {
    const row = document.createElement("div");
    row.className = "corner-row";
    const label = document.createElement("strong");
    label.textContent = CORNER_LABELS[index];
    for (const [axis, value] of [["X", x], ["Y", y]] as const) {
      const control = document.createElement("label");
      const axisLabel = document.createElement("span");
      axisLabel.textContent = axis;
      const input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.max = "1";
      input.step = "0.0005";
      input.value = value.toFixed(6);
      input.inputMode = "decimal";
      input.setAttribute("aria-label", `${CORNER_LABELS[index]} ${axis} normalized coordinate`);
      input.addEventListener("change", () => {
        const number = Number(input.value);
        if (!Number.isFinite(number)) {
          input.setAttribute("aria-invalid", "true");
          return;
        }
        input.removeAttribute("aria-invalid");
        const current = currentQuad()[index];
        setQuadPoint(index, axis === "X" ? number : current[0], axis === "Y" ? number : current[1]);
      });
      control.append(axisLabel, input);
      row.append(control);
    }
    row.prepend(label);
    dom.cornerInputs.append(row);
  });
}

type ZoneKey = keyof ZoneDraft;
const ZONE_CONTROLS: Array<{ key: ZoneKey; name: string; code: string; boundary: 0 | 1 | 2 }> = [
  { key: "sidewallToStrongLensRim", name: "Sidewall → Strong Rim", code: "S1", boundary: 0 },
  { key: "strongLensRimToOpticalShoulder", name: "Strong Rim → Shoulder", code: "S2", boundary: 1 },
  { key: "opticalShoulderToCenterFace", name: "Shoulder → Center", code: "S3", boundary: 2 },
];

function validateAndStoreZones(invalidateApproval = true): boolean {
  if (!annotations) return false;
  const role = activeRole();
  const category = activeCategory();
  try {
    const zones = validateZoneDraft(currentZones(), `${role.id}.zoneBoundaries`);
    invalidCategories.delete(`${role.targetCategory}:zones`);
    dom.zoneError.hidden = true;
    category.zoneBoundaries = {
      coordinateSpace: "inward-ratio-of-card-minor-axis",
      sidewallOuter: 0,
      ...zones,
    };
    if (invalidateApproval) {
      category.zoneReviewStatus = "PENDING";
      invalidateRolesForCategory(role.targetCategory);
    }
    return true;
  } catch (error) {
    invalidCategories.add(`${role.targetCategory}:zones`);
    dom.zoneError.textContent = error instanceof Error ? error.message : String(error);
    dom.zoneError.hidden = false;
    category.zoneReviewStatus = "PENDING";
    invalidateRolesForCategory(role.targetCategory);
    return false;
  }
}

/**
 * Boundaries are edited through the shared width model, so a slider can never
 * push one cumulative boundary past its neighbour. The previous version wrote
 * the three values independently, which is what produced a Shoulder of 0% next
 * to an ordering error the reviewer then had to repair by hand.
 */
function setZoneBoundary(boundary: 0 | 1 | 2, value: number): void {
  const role = activeRole();
  const widths = withBoundaryAt(widthsFromBoundaries(currentZones()), boundary, value);
  const zones: ZoneDraft = boundariesFromWidths(widths);
  workingZones.set(role.targetCategory, zones);
  validateAndStoreZones(true);
  markDirty();
  renderZoneInputs();
  drawAnnotationLayers();
  updateInspectorState();
}

function percent(value: number, precision = 2): string {
  return `${(value * 100).toFixed(precision)}%`;
}

function renderZoneInputs(): void {
  const zones = currentZones();
  dom.zoneInputs.replaceChildren();
  for (const control of ZONE_CONTROLS) {
    const row = document.createElement("div");
    row.className = "zone-row";
    const heading = document.createElement("div");
    const code = document.createElement("span");
    code.textContent = control.code;
    const label = document.createElement("strong");
    label.textContent = control.name;
    heading.append(code, label);
    const range = document.createElement("input");
    range.type = "range";
    range.min = "0";
    range.max = "0.5";
    range.step = "0.001";
    range.value = String(zones[control.key]);
    range.setAttribute("aria-label", `${control.name} boundary`);
    const numberWrap = document.createElement("label");
    const number = document.createElement("input");
    number.type = "number";
    number.min = "0";
    number.max = "50";
    number.step = "0.1";
    number.value = (zones[control.key] * 100).toFixed(2);
    number.inputMode = "decimal";
    number.setAttribute("aria-label", `${control.name} percent`);
    const unit = document.createElement("span");
    unit.textContent = "%";
    numberWrap.append(number, unit);
    range.addEventListener("input", () => setZoneBoundary(control.boundary, Number(range.value)));
    number.addEventListener("change", () => {
      const value = Number(number.value) / 100;
      if (!Number.isFinite(value)) {
        number.setAttribute("aria-invalid", "true");
        return;
      }
      number.removeAttribute("aria-invalid");
      setZoneBoundary(control.boundary, value);
    });
    row.append(heading, range, numberWrap);
    dom.zoneInputs.append(row);
  }
  const widths = widthsFromBoundaries(zones);
  const sidewall = widths.sidewall;
  const rim = widths.strongRim;
  const shoulder = widths.shoulder;
  const center = Math.max(0, 1 - 2 * zones.opticalShoulderToCenterFace);
  dom.zoneWidthSidewall.textContent = percent(sidewall, 3);
  dom.zoneWidthRim.textContent = percent(rim, 3);
  dom.zoneWidthShoulder.textContent = percent(shoulder, 3);
  dom.zoneWidthCenter.textContent = percent(center, 2);
  document.documentElement.style.setProperty("--zone-sidewall", `${Math.min(100, sidewall * 200)}%`);
  document.documentElement.style.setProperty("--zone-rim", `${Math.min(100, zones.strongLensRimToOpticalShoulder * 200)}%`);
  document.documentElement.style.setProperty("--zone-shoulder", `${Math.min(100, zones.opticalShoulderToCenterFace * 200)}%`);
}

function renderFeatureDecisions(): void {
  const review = activeRoleAnnotation();
  dom.featureDecisions.replaceChildren();
  for (const feature of FEATURE_IDS) {
    const row = document.createElement("div");
    row.className = "feature-row";
    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = FEATURE_LABELS[feature].name;
    const detail = document.createElement("span");
    detail.textContent = FEATURE_LABELS[feature].detail;
    copy.append(heading, detail);
    const controls = document.createElement("div");
    controls.className = "decision-segment";
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", `${FEATURE_LABELS[feature].name} decision`);
    for (const status of ["PENDING", "APPROVED", "REJECTED"] as const) {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.status = status;
      button.classList.toggle("is-active", review.featureDecisions[feature] === status);
      button.setAttribute("aria-pressed", String(review.featureDecisions[feature] === status));
      button.textContent = status === "PENDING" ? "—" : status === "APPROVED" ? "PASS" : "FAIL";
      button.title = status;
      button.addEventListener("click", () => {
        review.featureDecisions[feature] = status;
        review.reviewStatus = "PENDING";
        recomputeCategoryStatus(activeRole().targetCategory);
        markDirty();
        renderFeatureDecisions();
        renderRoleList();
        updateInspectorState();
      });
      controls.append(button);
    }
    row.append(copy, controls);
    dom.featureDecisions.append(row);
  }
}

function displayGlobalStatus(): ReviewStatus | "PARTIAL" {
  if (!annotations) return "PENDING";
  const statuses = ROLE_IDS.map((role) => annotations!.roles[role].reviewStatus);
  if (statuses.some((status) => status === "REJECTED")) return "REJECTED";
  if (statuses.every((status) => status === "APPROVED")) return "PARTIAL";
  if (statuses.some((status) => status !== "PENDING")) return "PARTIAL";
  return annotations.reviewStatus;
}

function renderRoleList(): void {
  if (!annotations) return;
  dom.roleList.replaceChildren();
  let decided = 0;
  roles.forEach((role, index) => {
    const review = annotations!.roles[role.id];
    if (review.reviewStatus !== "PENDING") decided += 1;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "role-button";
    button.classList.toggle("is-active", role.id === activeRoleId);
    button.dataset.status = review.reviewStatus;
    button.setAttribute("aria-current", role.id === activeRoleId ? "true" : "false");
    const number = document.createElement("span");
    number.className = "role-number";
    number.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("span");
    copy.className = "role-copy";
    const name = document.createElement("strong");
    name.textContent = role.label || ROLE_LABELS[role.id];
    const category = document.createElement("small");
    category.textContent = role.targetCategory;
    copy.append(name, category);
    const state = document.createElement("i");
    state.className = "role-state";
    state.setAttribute("aria-label", review.reviewStatus);
    button.append(number, copy, state);
    if (role.frameReused || role.id === "front") {
      const reused = document.createElement("em");
      reused.textContent = "REUSED";
      button.append(reused);
    }
    button.addEventListener("click", () => selectRole(role.id));
    dom.roleList.append(button);
  });
  dom.roleProgress.textContent = `${decided} / ${ROLE_IDS.length} decided`;
  setStatus(dom.globalStatus, displayGlobalStatus());
}

function approvalReasons(): string[] {
  if (!annotations) return ["Annotations unavailable"];
  const role = activeRole();
  const category = activeCategory();
  const review = activeRoleAnnotation();
  const reasons: string[] = [];
  if (!precisionEligible()) reasons.push("Fine-pointer desktop required");
  if (blocked) reasons.push("Review gate blocked");
  if (!assetReady) reasons.push("Role assets are not fully verified");
  if ([...invalidCategories].some((entry) => entry.startsWith(`${role.targetCategory}:`))) {
    reasons.push("Geometry or zone values are invalid");
  }
  if (category.quadReviewStatus !== "APPROVED") reasons.push("Card plane is not human verified");
  if (category.zoneReviewStatus !== "APPROVED") reasons.push("Optical zones are not human marked");
  for (const feature of FEATURE_IDS) {
    if (review.featureDecisions[feature] !== "APPROVED") reasons.push(`${FEATURE_LABELS[feature].name} is not approved`);
  }
  return reasons;
}

function updateActionState(): void {
  const hasState = Boolean(annotations && apiState);
  const reasons = hasState ? approvalReasons() : ["Review state unavailable"];
  dom.saveButton.disabled = !hasState || blocked || !assetReady || saving || !dirty || invalidCategories.size > 0;
  dom.approveRole.disabled = reasons.length > 0 || saving;
  const notes = hasState ? activeRoleAnnotation().notes.trim() : "";
  dom.rejectRole.disabled = !hasState || blocked || !assetReady || saving || notes.length < 8;
  dom.decisionReadiness.textContent = reasons.length === 0 ? "READY" : "NOT READY";
  dom.decisionReadiness.dataset.ready = reasons.length === 0 ? "true" : "false";
  dom.decisionHelp.textContent = reasons.length === 0
    ? "All explicit evidence gates are satisfied. Approval remains local until saved."
    : reasons.slice(0, 3).join(" · ");
}

function updateInspectorState(): void {
  if (!annotations) return;
  const category = activeCategory();
  const review = activeRoleAnnotation();
  dom.quadApproval.checked = category.quadReviewStatus === "APPROVED";
  dom.zoneApproval.checked = category.zoneReviewStatus === "APPROVED";
  dom.quadStatus.textContent = category.quadReviewStatus === "APPROVED" ? "VERIFIED" : "UNVERIFIED";
  dom.quadStatus.dataset.status = category.quadReviewStatus;
  dom.zoneStatus.textContent = category.zoneReviewStatus === "APPROVED" ? "VERIFIED" : "SUGGESTED";
  dom.zoneStatus.dataset.status = category.zoneReviewStatus;
  const featureCount = FEATURE_IDS.filter((feature) => review.featureDecisions[feature] !== "PENDING").length;
  dom.featureStatus.textContent = `${featureCount} / ${FEATURE_IDS.length}`;
  setStatus(dom.activeRoleStatus, review.reviewStatus);
  updatePrecisionGate();
  updateActionState();
}

function renderInspector(): void {
  if (!annotations) return;
  const role = activeRole();
  const review = activeRoleAnnotation();
  const index = roles.findIndex((entry) => entry.id === role.id);
  dom.activeRoleIndex.textContent = `ROLE ${String(index + 1).padStart(2, "0")} / ${String(roles.length).padStart(2, "0")}`;
  dom.activeRoleName.textContent = role.label || ROLE_LABELS[role.id];
  dom.activeRoleCategory.textContent = role.targetCategory;
  dom.reusedFrameNote.hidden = !(role.frameReused || role.id === "front");
  dom.targetEvidenceLabel.textContent = `FRAME ${shortHash(review.targetFrameSha256, 12)}`;
  dom.localEvidenceLabel.textContent = `${review.localCaptureId.toUpperCase()} · ${shortHash(review.localCaptureSha256, 10)}`;
  dom.roleNotes.value = review.notes;
  dom.notesCount.textContent = String(review.notes.length);
  renderCornerInputs();
  renderZoneInputs();
  renderFeatureDecisions();
  renderRoleList();
  updateInspectorState();
}

async function selectRole(roleId: RoleId): Promise<void> {
  if (activeRoleId === roleId && assetReady) return;
  activeRoleId = roleId;
  activeRoi = "all";
  renderRoiState();
  renderInspector();
  await loadRoleAssets();
}

function renderRoiState(): void {
  for (const button of dom.roiButtons) {
    const selected = button.dataset.roi === activeRoi;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  dom.roiOutput.textContent = ROI_LABELS[activeRoi];
  applyViewTransform();
  drawAnnotationLayers();
}

function initializeWorkingValues(): void {
  if (!annotations) return;
  workingQuads.clear();
  workingZones.clear();
  invalidCategories.clear();
  for (const role of roles) {
    const category = annotations.categories[role.targetCategory];
    const quad = quadFrom(category, role);
    const zones = zoneDraftFrom(category, role);
    const existingQuad = workingQuads.get(role.targetCategory);
    const existingZones = workingZones.get(role.targetCategory);
    if (existingQuad && JSON.stringify(existingQuad) !== JSON.stringify(quad)) {
      throw new Error(`${role.targetCategory} has conflicting reused-frame quad suggestions`);
    }
    if (existingZones && JSON.stringify(existingZones) !== JSON.stringify(zones)) {
      throw new Error(`${role.targetCategory} has conflicting reused-frame zone suggestions`);
    }
    workingQuads.set(role.targetCategory, cloneQuad(quad));
    workingZones.set(role.targetCategory, { ...zones });
  }
}

function renderEvidence(): void {
  if (!apiState) return;
  const evidence = apiState.evidence;
  dom.evidenceDot.dataset.status = "PASS";
  dom.evidenceFrozen.textContent = shortHash(evidence.sourceVideoSha256);
  dom.evidenceHead.textContent = shortHash(evidence.localHead, 9);
  dom.evidenceRuntime.textContent = shortHash(evidence.localRuntimeSourceSetSha256);
  dom.evidenceBundle.textContent = shortHash(evidence.reviewBundleSha256);
  dom.evidencePrivate.textContent = evidence.privateOutput === true ? "IGNORED / LOCAL" : String(evidence.privateOutput);
}

function setCoordinateView(view: CoordinateView): void {
  if (coordinateView === view) return;
  coordinateView = view;
  for (const button of dom.viewButtons) {
    const active = button.dataset.view === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  if (!assetReady) return;
  updateDisplayedAssets().catch((error: unknown) => {
    setBlocked(
      "Coordinate view failed",
      "Verified Source and Card Plane assets could not be switched safely.",
      error instanceof Error ? error.message : String(error),
    );
  });
}

function setFeatureDecision(feature: FeatureId, status: ReviewStatus): void {
  if (!annotations) return;
  const review = activeRoleAnnotation();
  review.featureDecisions[feature] = status;
  review.reviewStatus = "PENDING";
  recomputeCategoryStatus(activeRole().targetCategory);
  markDirty();
  renderFeatureDecisions();
  renderRoleList();
  updateInspectorState();
}

function approveCurrentRole(): void {
  if (!annotations) return;
  const reasons = approvalReasons();
  if (reasons.length > 0) {
    showToast(reasons[0], "danger");
    return;
  }
  if (!storeWorkingQuad(false) || !validateAndStoreZones(false)) {
    showToast("Geometry validation failed; role remains pending", "danger");
    updateInspectorState();
    return;
  }
  activeRoleAnnotation().reviewStatus = "APPROVED";
  recomputeCategoryStatus(activeRole().targetCategory);
  markDirty("APPROVAL NOT SAVED");
  renderRoleList();
  updateInspectorState();
  showToast(`${activeRole().label} staged as APPROVED`, "success");
}

function rejectCurrentRole(): void {
  if (!annotations) return;
  const review = activeRoleAnnotation();
  if (review.notes.trim().length < 8) {
    dom.roleNotes.focus();
    showToast("Record a concrete rejection reason first", "danger");
    return;
  }
  review.reviewStatus = "REJECTED";
  recomputeCategoryStatus(activeRole().targetCategory);
  markDirty("REJECTION NOT SAVED");
  renderRoleList();
  updateInspectorState();
  showToast(`${activeRole().label} staged as REJECTED`, "danger");
}

function validateDraftForSave(): void {
  if (!annotations || !apiState) throw new Error("Review state is unavailable");
  if (invalidCategories.size > 0) throw new Error("Unsaved geometry contains invalid values");
  for (const role of roles) {
    const review = annotations.roles[role.id];
    const category = annotations.categories[role.targetCategory];
    if (review.reviewStatus === "REJECTED" && review.notes.trim().length < 8) {
      throw new Error(`${role.label} rejection has no concrete reason`);
    }
    if (review.reviewStatus === "APPROVED") {
      if (category.quadReviewStatus !== "APPROVED" || category.zoneReviewStatus !== "APPROVED") {
        throw new Error(`${role.label} approval is missing geometry approval`);
      }
      if (FEATURE_IDS.some((feature) => review.featureDecisions[feature] !== "APPROVED")) {
        throw new Error(`${role.label} approval is missing a feature decision`);
      }
      validateQuad(category.quadNormalized, `${role.id}.quadNormalized`);
      const zone = category.zoneBoundaries;
      if (
        zone.sidewallToStrongLensRim === null ||
        zone.strongLensRimToOpticalShoulder === null ||
        zone.opticalShoulderToCenterFace === null
      ) throw new Error(`${role.label} approved zones are incomplete`);
      validateZoneDraft({
        sidewallToStrongLensRim: zone.sidewallToStrongLensRim,
        strongLensRimToOpticalShoulder: zone.strongLensRimToOpticalShoulder,
        opticalShoulderToCenterFace: zone.opticalShoulderToCenterFace,
      });
    }
  }
  const serialized = JSON.stringify(annotations);
  if (/file:\/\/|\/Users\/|[A-Za-z]:\\/.test(serialized)) {
    throw new Error("Annotations contain an absolute local path");
  }
}

async function saveAnnotations(): Promise<void> {
  if (!annotations || !apiState || saving || !dirty) return;
  try {
    validateDraftForSave();
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), "danger");
    return;
  }
  saving = true;
  dom.saveState.textContent = "SAVING…";
  updateActionState();
  try {
    const response = await fetch(`${API_ROOT}/annotations`, {
      method: "PUT",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Phase1B-CSRF": apiState.csrfToken,
        "If-Match": apiState.etag,
      },
      body: JSON.stringify(annotations),
    });
    if (response.status === 409 || response.status === 412) {
      throw new Error("Write conflict: annotations changed on disk. Reload before making another decision.");
    }
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 600);
      throw new Error(`Save failed with HTTP ${response.status}${detail ? `: ${detail}` : ""}`);
    }
    const headerEtag = response.headers.get("etag");
    let payload: SaveApiResponse | ReviewApiState | null = null;
    if (response.status !== 204) {
      const text = await response.text();
      if (text) payload = JSON.parse(text) as SaveApiResponse | ReviewApiState;
    }
    if (payload && "csrfToken" in payload) {
      const parsed = parseReviewState(payload);
      apiState = parsed.state;
      roles = parsed.roles;
      annotations = structuredClone(parsed.state.annotations);
    } else if (payload?.annotations) {
      const parsed = parseReviewState({
        ...apiState,
        etag: payload.etag ?? headerEtag ?? apiState.etag,
        annotations: payload.annotations,
      });
      apiState = parsed.state;
      roles = parsed.roles;
      annotations = structuredClone(parsed.state.annotations);
    }
    apiState.etag = payload && "etag" in payload && typeof payload.etag === "string"
      ? payload.etag
      : headerEtag ?? apiState.etag;
    initializeWorkingValues();
    markClean();
    renderEvidence();
    renderInspector();
    drawAnnotationLayers();
    showToast("Private annotations saved atomically", "success");
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setBlocked(
      "Annotation write was not accepted",
      "No further review decisions can be persisted until the local state is rebound.",
      detail,
    );
  } finally {
    saving = false;
    updateActionState();
  }
}

function svgPointerPosition(event: PointerEvent): NormalizedPoint {
  const matrix = dom.targetSvg.getScreenCTM();
  if (!matrix || !dom.targetBase.naturalWidth || !dom.targetBase.naturalHeight) throw new Error("Target coordinate transform is unavailable");
  const point = dom.targetSvg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const local = point.matrixTransform(matrix.inverse());
  return [
    Math.max(0, Math.min(1, local.x / dom.targetBase.naturalWidth)),
    Math.max(0, Math.min(1, local.y / dom.targetBase.naturalHeight)),
  ];
}

function bindEvents(): void {
  for (const button of dom.viewButtons) {
    button.addEventListener("click", () => setCoordinateView(button.dataset.view as CoordinateView));
  }
  for (const button of dom.overlayButtons) {
    button.addEventListener("click", () => {
      const overlay = button.dataset.overlay as OverlayId;
      if (activeOverlays.has(overlay)) activeOverlays.delete(overlay);
      else activeOverlays.add(overlay);
      button.setAttribute("aria-pressed", String(activeOverlays.has(overlay)));
      updateOverlays();
    });
  }
  for (const button of dom.roiButtons) {
    button.addEventListener("click", () => {
      activeRoi = button.dataset.roi as RoiId;
      renderRoiState();
    });
  }
  dom.resetViewButton.addEventListener("click", () => {
    coordinateView = "source";
    activeRoi = "all";
    activeOverlays = new Set<OverlayId>(["edge"]);
    for (const button of dom.viewButtons) {
      const active = button.dataset.view === "source";
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    for (const button of dom.overlayButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.overlay === "edge"));
    }
    renderRoiState();
    if (assetReady) void updateDisplayedAssets();
  });
  dom.quadApproval.addEventListener("change", () => {
    if (!annotations) return;
    const category = activeCategory();
    if (dom.quadApproval.checked) {
      if (!precisionEligible() || !storeWorkingQuad(false)) {
        dom.quadApproval.checked = false;
        showToast("Card quad is not eligible for approval", "danger");
        return;
      }
      category.quadReviewStatus = "APPROVED";
    } else {
      category.quadReviewStatus = "PENDING";
      invalidateRolesForCategory(activeRole().targetCategory);
    }
    recomputeCategoryStatus(activeRole().targetCategory);
    markDirty("GEOMETRY APPROVAL NOT SAVED");
    renderRoleList();
    updateInspectorState();
  });
  dom.zoneApproval.addEventListener("change", () => {
    if (!annotations) return;
    const category = activeCategory();
    if (dom.zoneApproval.checked) {
      if (!precisionEligible() || !validateAndStoreZones(false)) {
        dom.zoneApproval.checked = false;
        showToast("Optical zones are not eligible for approval", "danger");
        return;
      }
      category.zoneReviewStatus = "APPROVED";
    } else {
      category.zoneReviewStatus = "PENDING";
      invalidateRolesForCategory(activeRole().targetCategory);
    }
    recomputeCategoryStatus(activeRole().targetCategory);
    markDirty("ZONE APPROVAL NOT SAVED");
    renderRoleList();
    updateInspectorState();
  });
  dom.roleNotes.addEventListener("input", () => {
    if (!annotations) return;
    activeRoleAnnotation().notes = dom.roleNotes.value;
    dom.notesCount.textContent = String(dom.roleNotes.value.length);
    markDirty();
    updateActionState();
  });
  dom.approveRole.addEventListener("click", approveCurrentRole);
  dom.rejectRole.addEventListener("click", rejectCurrentRole);
  dom.saveButton.addEventListener("click", () => void saveAnnotations());
  dom.retryButton.addEventListener("click", () => void boot());

  dom.targetSvg.addEventListener("pointerdown", (event) => {
    if (coordinateView !== "source") return;
    const target = event.target instanceof Element ? event.target.closest<SVGElement>("[data-corner-index]") : null;
    if (!target) return;
    const cornerIndex = Number(target.dataset.cornerIndex);
    if (!Number.isInteger(cornerIndex)) return;
    pointerDrag = { cornerIndex, pointerId: event.pointerId };
    dom.targetSvg.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  dom.targetSvg.addEventListener("pointermove", (event) => {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    const [x, y] = svgPointerPosition(event);
    setQuadPoint(pointerDrag.cornerIndex, x, y);
  });
  const endPointer = (event: PointerEvent) => {
    if (!pointerDrag || pointerDrag.pointerId !== event.pointerId) return;
    if (dom.targetSvg.hasPointerCapture(event.pointerId)) dom.targetSvg.releasePointerCapture(event.pointerId);
    pointerDrag = null;
  };
  dom.targetSvg.addEventListener("pointerup", endPointer);
  dom.targetSvg.addEventListener("pointercancel", endPointer);
  dom.targetSvg.addEventListener("keydown", (event) => {
    const target = event.target instanceof Element ? event.target.closest<SVGElement>("[data-corner-index]") : null;
    if (!target || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    const index = Number(target.dataset.cornerIndex);
    const [x, y] = currentQuad()[index];
    const step = event.shiftKey ? 0.005 : event.altKey ? 0.0001 : 0.0005;
    const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
    const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
    setQuadPoint(index, x + dx, y + dy, true);
    event.preventDefault();
  });
  window.addEventListener("resize", () => {
    updatePrecisionGate();
    drawAnnotationLayers();
  });
  window.matchMedia("(pointer: fine)").addEventListener("change", updatePrecisionGate);
  window.addEventListener("keydown", (event) => {
    const editing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void saveAnnotations();
      return;
    }
    if (!editing && !event.metaKey && !event.ctrlKey && /^[1-7]$/.test(event.key)) {
      void selectRole(ROLE_IDS[Number(event.key) - 1]);
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function boot(): Promise<void> {
  const generation = ++loadGeneration;
  assetReady = false;
  revokeAssetUrls();
  setBlocked(
    "Binding private evidence…",
    "The review surface remains locked until the API, evidence identity, geometry and private output contract are validated.",
  );
  dom.retryButton.disabled = true;
  try {
    const response = await fetch(`${API_ROOT}/state`, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`Review API returned HTTP ${response.status}`);
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) throw new Error("Review API did not return JSON");
    const parsed = parseReviewState(await response.json());
    if (generation !== loadGeneration) return;
    apiState = parsed.state;
    roles = parsed.roles;
    annotations = structuredClone(parsed.state.annotations);
    activeRoleId = roles.some((role) => role.id === activeRoleId) ? activeRoleId : roles[0].id;
    initializeWorkingValues();
    dirty = false;
    saving = false;
    renderEvidence();
    renderInspector();
    renderRoiState();
    clearBlocked();
    document.body.dataset.bound = "true";
    markClean("BOUND · NO LOCAL CHANGES");
    await loadRoleAssets();
  } catch (error) {
    if (generation !== loadGeneration) return;
    const detail = error instanceof Error ? error.message : String(error);
    setBlocked(
      "Private review is unavailable",
      "Start the local-only Phase 1B review server and verify the ignored evidence bundle. Ordinary Vite preview intentionally cannot expose or write private Golden pixels.",
      detail,
    );
  } finally {
    dom.retryButton.disabled = false;
  }
}

bindEvents();
void boot();
