/**
 * Reviewer Mode: a guided five-step target annotation for one human reviewer.
 *
 * Hard rules encoded here:
 *   - Steps 1-4 are the Target Annotation stage. The local candidate is not
 *     fetched, not decoded and not rendered while the reviewer is in them.
 *   - Optical boundaries are dragged on the real, rectified target card. The
 *     percentages are derived from the drag; nothing is typed.
 *   - Frame, quad, zones and local match are four independent states.
 *   - Every change autosaves to the private reviewer draft. The annotation
 *     contract file is never read or written from this module.
 */

import "./reviewer.css";
import { ROLE_IDS, type NormalizedQuad, type RoleId } from "../types";
import {
  SUGGESTED_ZONE_WIDTHS,
  boundariesFromWidths,
  clampZoneWidths,
  withBoundaryAt,
  type ZoneWidths,
} from "../zone-model";
import {
  cardMetrics,
  cardPositionToRatio,
  cardToPlanePixel,
  planePixelToCard,
  quadArea,
  quadBoundingBox,
  rectifyCardPlane,
  zoneInsetFractions,
  type CardMetrics,
  type Quad,
  type RectifiedPlane,
} from "../geometry";
import { ReviewerStore, fetchReviewerState, loadVerifiedImage, type SaveStatus } from "./api";
import { computeTargetAnnotationHash } from "./hash";
import { language, setLanguage, t, type Language } from "./i18n";
import { renderTutorial, syntheticCard } from "./tutorial";
import {
  COMPARE_VERDICTS,
  FRAME_REJECT_REASONS,
  type CandidateFrame,
  type CompareVerdict,
  type FrameRejectReason,
  type ReviewerApiPayload,
  type ReviewerRoleEvidence,
  type ReviewerRoleState,
  type ReviewerState,
  type ReviewerStep,
} from "./types";

const STEP_COUNT = 5;
const PLANE_SIZE = 900;
const PLANE_DRAG_SIZE = 280;
const PLANE_MARGIN = 0.08;
const STAGE_PADDING = 1.06;

let payload: ReviewerApiPayload;
let store: ReviewerStore;
let state: ReviewerState;
let roles: ReviewerRoleEvidence[] = [];
let activeRoleId: RoleId = ROLE_IDS[0];
let tutorialOpen = false;
let renderGeneration = 0;
let exampleOpen = true;

const frameImages = new Map<string, HTMLImageElement>();
const planeCache = new Map<string, RectifiedPlane>();
let saveStatus: SaveStatus = "IDLE";
let saveDetail: string | null = null;

/* ------------------------------------------------------------------ utils */

function roleEvidence(id: RoleId = activeRoleId): ReviewerRoleEvidence {
  const role = roles.find((entry) => entry.id === id);
  if (!role) throw new Error(`Unknown role ${id}`);
  return role;
}

function roleState(id: RoleId = activeRoleId): ReviewerRoleState {
  return state.roles[id];
}

function candidatesFor(role: ReviewerRoleEvidence): CandidateFrame[] {
  if (role.candidates.length > 0) return role.candidates;
  const asset = role.assets["target-source"];
  return [{
    id: "primary",
    frameIndex: -1,
    primary: true,
    offsetFromSelected: 0,
    width: 0,
    height: 0,
    sha256: asset.sha256,
    thumbnailSha256: asset.sha256,
    url: asset.url,
    thumbnailUrl: asset.url,
  }];
}

function selectedCandidate(role: ReviewerRoleEvidence, current = roleState(role.id)): CandidateFrame {
  const list = candidatesFor(role);
  return list.find((entry) => entry.id === current.frame.candidateId)
    ?? list.find((entry) => entry.primary)
    ?? list[0];
}

function maxReachableStep(role: ReviewerRoleState): ReviewerStep {
  if (role.frame.status !== "ACCEPTED") return 1;
  if (role.quad.status !== "ACCEPTED") return 2;
  if (role.zones.status !== "ACCEPTED") return 3;
  if (role.lock.status !== "LOCKED") return 4;
  return 5;
}

function progressOf(role: ReviewerRoleState): string {
  if (role.frame.status === "REJECTED") return "REJECTED";
  if (role.lock.status === "LOCKED") return "TARGET_LOCKED";
  if (role.zones.status === "ACCEPTED") return "PENDING_LOCK";
  if (role.quad.status === "ACCEPTED") return "PENDING_ZONES";
  if (role.frame.status === "ACCEPTED") return "PENDING_QUAD";
  return "PENDING_FRAME";
}

const PROGRESS_LABEL: Record<string, Parameters<typeof t>[0]> = {
  PENDING_FRAME: "statePendingFrame",
  PENDING_QUAD: "statePendingQuad",
  PENDING_ZONES: "statePendingZones",
  PENDING_LOCK: "statePendingLock",
  TARGET_LOCKED: "stateLocked",
  REJECTED: "stateRejected",
};

/** Same convexity and ordering rule the server enforces; used as a drag guard. */
function quadIsLegal(quad: NormalizedQuad): boolean {
  if (quad.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1)) return false;
  for (let index = 0; index < 4; index += 1) {
    const point = quad[index];
    const next = quad[(index + 1) % 4];
    const after = quad[(index + 2) % 4];
    const cross = (next[0] - point[0]) * (after[1] - next[1]) - (next[1] - point[1]) * (after[0] - next[0]);
    if (cross <= 1e-6) return false;
  }
  const topY = (quad[0][1] + quad[1][1]) / 2;
  const bottomY = (quad[2][1] + quad[3][1]) / 2;
  const leftX = (quad[0][0] + quad[3][0]) / 2;
  const rightX = (quad[1][0] + quad[2][0]) / 2;
  return topY < bottomY && leftX < rightX;
}

function workingQuad(role: ReviewerRoleEvidence, current = roleState(role.id)): NormalizedQuad | null {
  return current.quad.quadNormalized ?? role.suggestedQuadNormalized ?? null;
}

function workingWidths(current = roleState()): ZoneWidths {
  return clampZoneWidths(current.zones.widths ?? SUGGESTED_ZONE_WIDTHS);
}

function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function shortHash(value: string | null | undefined, size = 12): string {
  return value ? `${value.slice(0, size)}…` : "—";
}

function mutate(apply: (draft: ReviewerState) => void, options: { rerender?: boolean } = {}): void {
  apply(state);
  state.updatedAt = new Date().toISOString();
  store.replace(state);
  store.queue();
  if (options.rerender !== false) void render();
  else renderChrome();
}

/* ------------------------------------------------------------------- shell */

function shell(): HTMLElement {
  let root = document.querySelector<HTMLElement>("#reviewer-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "reviewer-root";
    document.body.append(root);
  }
  if (!root.firstChild) {
    root.innerHTML = `
      <div class="rv" data-stage="target-only">
        <header class="rv-head">
          <div class="rv-brand">
            <span class="rv-mark" aria-hidden="true"></span>
            <div>
              <p class="rv-eyebrow">MIRRORWEB · V4</p>
              <h1 id="rv-app-title"></h1>
            </div>
          </div>
          <p id="rv-progress" class="rv-progress"></p>
          <div class="rv-head-right">
            <span id="rv-stage-badge" class="rv-stage-badge"></span>
            <span id="rv-save" class="rv-save" data-status="IDLE"></span>
            <button id="rv-lang" type="button" class="rv-quiet"></button>
            <a id="rv-advanced" class="rv-quiet" href="?mode=advanced"></a>
          </div>
        </header>
        <aside class="rv-rail" aria-label="review queue">
          <h2 id="rv-rail-title"></h2>
          <button id="rv-tutorial-open" type="button" class="rv-tutorial-open"></button>
          <nav id="rv-role-list" class="rv-role-list"></nav>
          <p id="rv-autosave-hint" class="rv-hint"></p>
        </aside>
        <main id="rv-main" class="rv-main"></main>
        <aside id="rv-example" class="rv-example" aria-label="examples"></aside>
        <div id="rv-blocked" class="rv-blocked" hidden>
          <div>
            <h2 id="rv-blocked-title"></h2>
            <pre id="rv-blocked-detail"></pre>
            <button id="rv-blocked-retry" type="button" class="rv-primary"></button>
          </div>
        </div>
      </div>
    `;
  }
  return root;
}

function setBlocked(detail: string): void {
  const node = document.querySelector<HTMLElement>("#rv-blocked");
  if (!node) return;
  node.hidden = false;
  document.querySelector<HTMLElement>("#rv-blocked-title")!.textContent = t("blockedTitle");
  document.querySelector<HTMLElement>("#rv-blocked-detail")!.textContent = detail;
  const retry = document.querySelector<HTMLButtonElement>("#rv-blocked-retry")!;
  retry.textContent = t("blockedRetry");
  retry.onclick = () => void boot();
}

function renderSaveState(): void {
  const node = document.querySelector<HTMLElement>("#rv-save");
  if (!node) return;
  node.dataset.status = saveStatus;
  node.textContent = saveStatus === "SAVING"
    ? t("saveSaving")
    : saveStatus === "SAVED"
      ? t("saveSaved")
      : saveStatus === "FAILED"
        ? t("saveFailed")
        : t("saveIdle");
  node.title = saveDetail ?? "";
}

function renderChrome(): void {
  const role = roleState();
  const index = ROLE_IDS.indexOf(activeRoleId) + 1;
  document.querySelector<HTMLElement>("#rv-app-title")!.textContent = `${t("appTitle")} · ${t("reviewerMode")}`;
  document.querySelector<HTMLElement>("#rv-progress")!.textContent = tutorialOpen
    ? t("tutorialTitle")
    : `${t("roleHeader")} ${index} / ${ROLE_IDS.length} · ${t("stepHeader")} ${role.step} / ${STEP_COUNT}`;
  const badge = document.querySelector<HTMLElement>("#rv-stage-badge")!;
  const comparing = !tutorialOpen && role.step === 5;
  badge.textContent = comparing ? t("localVisibleBadge") : t("targetOnlyBadge");
  badge.dataset.stage = comparing ? "compare" : "target-only";
  document.querySelector<HTMLElement>(".rv")!.dataset.stage = comparing ? "compare" : "target-only";
  document.querySelector<HTMLElement>("#rv-rail-title")!.textContent = t("roleQueue");
  document.querySelector<HTMLElement>("#rv-autosave-hint")!.textContent = t("autosaveHint");
  const languageButton = document.querySelector<HTMLButtonElement>("#rv-lang")!;
  languageButton.textContent = language() === "zh" ? "English" : "中文";
  languageButton.onclick = () => {
    const next: Language = language() === "zh" ? "en" : "zh";
    setLanguage(next);
    mutate((draft) => { draft.language = next; });
  };
  const advanced = document.querySelector<HTMLAnchorElement>("#rv-advanced")!;
  advanced.textContent = t("openAdvanced");
  const tutorialButton = document.querySelector<HTMLButtonElement>("#rv-tutorial-open")!;
  tutorialButton.textContent = state.tutorialAcknowledged ? t("tutorialReopen") : t("tutorialEntry");
  tutorialButton.classList.toggle("is-active", tutorialOpen);
  tutorialButton.onclick = () => { tutorialOpen = true; void render(); };
  renderSaveState();
  renderRail();
}

function renderRail(): void {
  const list = document.querySelector<HTMLElement>("#rv-role-list")!;
  list.replaceChildren();
  roles.forEach((role, index) => {
    const current = state.roles[role.id];
    const progress = progressOf(current);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "rv-role";
    button.dataset.progress = progress;
    button.classList.toggle("is-active", role.id === activeRoleId && !tutorialOpen);
    const number = document.createElement("b");
    number.textContent = String(index + 1).padStart(2, "0");
    const copy = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = role.label;
    const status = document.createElement("small");
    status.textContent = t(PROGRESS_LABEL[progress]);
    copy.append(name, status);
    const step = document.createElement("i");
    step.textContent = `${current.step}/${STEP_COUNT}`;
    button.append(number, copy, step);
    button.onclick = () => {
      activeRoleId = role.id;
      tutorialOpen = false;
      mutate((draft) => { draft.activeRoleId = role.id; });
    };
    list.append(button);
  });
}

/* ------------------------------------------------------------- image cache */

async function candidateImage(role: ReviewerRoleEvidence, candidate: CandidateFrame): Promise<HTMLImageElement> {
  const key = `${role.targetCategory}/${candidate.id}`;
  const cached = frameImages.get(key);
  if (cached) return cached;
  const image = await loadVerifiedImage(candidate.url, candidate.sha256);
  frameImages.set(key, image);
  return image;
}

async function planeAsset(role: ReviewerRoleEvidence, kind: "target-plane" | "local-plane"): Promise<HTMLImageElement> {
  const key = `${role.id}/${kind}`;
  const cached = frameImages.get(key);
  if (cached) return cached;
  const asset = role.assets[kind];
  const image = await loadVerifiedImage(asset.url, asset.sha256);
  frameImages.set(key, image);
  return image;
}

function rectified(
  role: ReviewerRoleEvidence,
  image: HTMLImageElement,
  quad: NormalizedQuad,
  size: number,
): RectifiedPlane {
  const key = `${role.id}|${quad.map((point) => point.map((value) => value.toFixed(5)).join(",")).join(";")}|${size}`;
  const cached = planeCache.get(key);
  if (cached) return cached;
  const plane = rectifyCardPlane(image, quad as Quad, { maxSize: size, margin: PLANE_MARGIN });
  planeCache.set(key, plane);
  if (planeCache.size > 24) planeCache.delete(planeCache.keys().next().value as string);
  return plane;
}

/* ------------------------------------------------------------ step helpers */

function stepHeader(titleKey: Parameters<typeof t>[0], leadKey: Parameters<typeof t>[0]): HTMLElement {
  const header = document.createElement("header");
  header.className = "rv-step-head";
  const title = document.createElement("h2");
  title.textContent = t(titleKey);
  const lead = document.createElement("p");
  lead.textContent = t(leadKey);
  header.append(title, lead);
  return header;
}

function actionBar(...buttons: HTMLElement[]): HTMLElement {
  const bar = document.createElement("div");
  bar.className = "rv-actions";
  bar.append(...buttons);
  return bar;
}

function button(
  label: string,
  onClick: () => void,
  variant: "primary" | "quiet" | "danger" = "quiet",
  id?: string,
): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.className = `rv-${variant}`;
  node.textContent = label;
  if (id) node.id = id;
  node.onclick = onClick;
  return node;
}

/**
 * A review stage that really keeps the card's aspect ratio.
 *
 * CSS `aspect-ratio` plus `max-block-size` silently gives up the ratio when the
 * height clamps, which is how a tall card ended up letterboxed inside a wide
 * black stage. The box is therefore fitted in script against its frame.
 */
function stageBox(aspect: number, id: string): { frame: HTMLElement; stage: HTMLElement } {
  const frame = document.createElement("div");
  frame.className = "rv-stage-frame";
  const stage = document.createElement("div");
  stage.className = "rv-stage";
  stage.id = id;
  stage.dataset.aspect = String(Math.max(0.2, Math.min(8, aspect)));
  frame.append(stage);
  return { frame, stage };
}

function fitStage(stage: HTMLElement): void {
  const frame = stage.parentElement;
  if (!frame) return;
  const aspect = Number(stage.dataset.aspect) || 1.6;
  const frameWidth = frame.clientWidth;
  const frameHeight = frame.clientHeight;
  if (frameWidth < 2 || frameHeight < 2) return;
  const width = Math.max(80, Math.min(frameWidth, frameHeight * aspect));
  stage.style.width = `${Math.floor(width)}px`;
  stage.style.height = `${Math.floor(width / aspect)}px`;
}

function canvasIn(stage: HTMLElement): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.className = "rv-canvas";
  stage.append(canvas);
  return canvas;
}

function svgIn(stage: HTMLElement, width: number, height: number): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "rv-overlay");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  stage.append(svg);
  return svg;
}

function svgNode<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attributes: Record<string, string | number>,
): SVGElementTagNameMap[K] {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}

/* --------------------------------------------------------------- example UI */

interface ExampleCopy {
  judge: string[];
  skip: string[];
  correct: string;
  wrong: string;
}

const EXAMPLES: Record<number, () => ExampleCopy> = {
  1: () => ({
    judge: [
      language() === "zh" ? "整张卡片是否完整、清晰、没有被光标或高光挡住" : "Whether the whole card is complete, sharp and unobstructed",
      language() === "zh" ? "这一帧是不是这个角色应该看的画面" : "Whether this frame really belongs to this role",
    ],
    skip: [
      language() === "zh" ? "不要在这一步判断边界位置" : "Do not judge boundary positions here",
      language() === "zh" ? "不要和本地结果比较" : "Do not compare against the local result",
    ],
    correct: language() === "zh" ? "卡片四边都在画面内，边缘清楚。" : "All four edges are inside the frame and readable.",
    wrong: language() === "zh" ? "卡片被裁切，或者边缘因为运动而拖影。" : "The card is clipped, or the edge smears from motion.",
  }),
  2: () => ({
    judge: [
      language() === "zh" ? "四个角是否落在卡片真实的外轮廓上" : "Whether the four corners sit on the card's real outline",
    ],
    skip: [
      language() === "zh" ? "不要把角点放到光晕或阴影上" : "Do not put a corner on the halo or the shadow",
      language() === "zh" ? "这一步不需要标记分区" : "No zone marking in this step",
    ],
    correct: language() === "zh" ? "角点压在卡片边上，右侧拉平后四边是直的。" : "Corners sit on the card edge; the flattened card has straight sides.",
    wrong: language() === "zh" ? "角点放在光晕外缘，拉平后卡片带黑边。" : "Corners on the halo; the flattened card keeps a dark frame.",
  }),
  3: () => ({
    judge: [
      language() === "zh" ? "内容从哪里开始弯曲（肩部）" : "Where content starts to bend (shoulder)",
      language() === "zh" ? "内容在哪里被快速压缩、折叠（强边缘）" : "Where content compresses and folds fast (strong rim)",
      language() === "zh" ? "最外层反射侧壁有多宽" : "How wide the outer reflective sidewall is",
    ],
    skip: [
      language() === "zh" ? "不要按高光条画线" : "Do not follow the specular highlight",
      language() === "zh" ? "不要按卡片上的文字画线" : "Do not follow the typography",
      language() === "zh" ? "不需要输入任何百分比" : "No percentage needs to be typed",
    ],
    correct: language() === "zh" ? "三条线落在内容行为改变的位置。" : "Each line sits where the content behaviour changes.",
    wrong: language() === "zh" ? "三条线落在光晕、高光或色散最外缘。" : "Lines placed on halo, highlight or the outer dispersion fringe.",
  }),
  4: () => ({
    judge: [
      language() === "zh" ? "摘要里的画面、四角和四个分区是不是你刚才标的" : "Whether the summary matches what you just marked",
    ],
    skip: [
      language() === "zh" ? "锁定不代表本地结果通过" : "Locking says nothing about the local result",
    ],
    correct: language() === "zh" ? "四边和四角裁切里，边界都落在同一位置。" : "Every edge and corner crop shows the boundary in the same place.",
    wrong: language() === "zh" ? "某一个角的边界明显和其它三个不一致。" : "One corner disagrees clearly with the other three.",
  }),
  5: () => ({
    judge: [
      language() === "zh" ? "本地边缘比目标宽还是窄" : "Whether the local edge is wider or narrower than the target",
      language() === "zh" ? "高光和色散的位置是否一致" : "Whether highlight and dispersion sit in the same place",
    ],
    skip: [
      language() === "zh" ? "不要因为本地不像就改目标标注" : "Never change the target annotation because local disagrees",
    ],
    correct: language() === "zh" ? "按四边和四角逐个比较。" : "Compare edge by edge and corner by corner.",
    wrong: language() === "zh" ? "只看整张卡片的整体印象。" : "Judging only by the overall impression of the whole card.",
  }),
};

function renderExample(step: number): void {
  const panel = document.querySelector<HTMLElement>("#rv-example")!;
  panel.replaceChildren();
  const copy = EXAMPLES[step]?.();
  if (!copy) return;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "rv-example-toggle";
  toggle.id = "rv-example-toggle";
  toggle.textContent = exampleOpen ? t("hideExample") : t("showExample");
  toggle.onclick = () => { exampleOpen = !exampleOpen; renderExample(step); };
  panel.append(toggle);
  if (!exampleOpen) return;

  const body = document.createElement("div");
  body.className = "rv-example-body";
  const good = document.createElement("figure");
  good.className = "rv-figure-card";
  good.dataset.tone = "good";
  const goodTitle = document.createElement("h4");
  goodTitle.textContent = t("exampleCorrect");
  const goodCaption = document.createElement("figcaption");
  goodCaption.textContent = copy.correct;
  good.append(goodTitle, syntheticCard({ variant: "correct", width: 260, height: 170 }), goodCaption);

  const bad = document.createElement("figure");
  bad.className = "rv-figure-card";
  bad.dataset.tone = "bad";
  const badTitle = document.createElement("h4");
  badTitle.textContent = t("exampleWrong");
  const badCaption = document.createElement("figcaption");
  badCaption.textContent = copy.wrong;
  bad.append(badTitle, syntheticCard({ variant: "wrong", width: 260, height: 170 }), badCaption);
  body.append(good, bad);

  for (const [titleKey, items] of [["exampleJudgeTitle", copy.judge], ["exampleSkipTitle", copy.skip]] as const) {
    const section = document.createElement("section");
    const heading = document.createElement("h4");
    heading.textContent = t(titleKey);
    const list = document.createElement("ul");
    for (const item of items) {
      const entry = document.createElement("li");
      entry.textContent = item;
      list.append(entry);
    }
    section.append(heading, list);
    body.append(section);
  }
  panel.append(body);
}

/* ------------------------------------------------------------------ step 1 */

async function renderStep1(main: HTMLElement, role: ReviewerRoleEvidence, current: ReviewerRoleState): Promise<void> {
  main.append(stepHeader("step1Title", "step1Lead"));
  const body = document.createElement("div");
  body.className = "rv-step-body rv-step-body--frame";
  main.append(body);

  const candidate = selectedCandidate(role, current);
  const image = await candidateImage(role, candidate);
  const quad = workingQuad(role, current);

  const left = document.createElement("section");
  left.className = "rv-panel";
  const leftTitle = document.createElement("h3");
  leftTitle.textContent = t("sourceFrame");
  const { frame: frameFrame, stage: frameStage } = stageBox(image.naturalWidth / image.naturalHeight, "rv-frame-stage");
  const frameCanvas = canvasIn(frameStage);
  left.append(leftTitle, frameFrame);

  const right = document.createElement("section");
  right.className = "rv-panel";
  const rightTitle = document.createElement("h3");
  rightTitle.textContent = t("selectedCard");
  const previewAspect = quad
    ? quadBoundingBox(quad as Quad, image.naturalWidth, image.naturalHeight).width
      / quadBoundingBox(quad as Quad, image.naturalWidth, image.naturalHeight).height
    : 1.4;
  const { frame: previewFrame, stage: previewStage } = stageBox(previewAspect, "rv-frame-preview");
  const previewCanvas = canvasIn(previewStage);
  right.append(rightTitle, previewFrame);

  body.append(left, right);

  const strip = document.createElement("section");
  strip.className = "rv-candidates";
  const stripTitle = document.createElement("h3");
  stripTitle.textContent = t("candidateStrip");
  strip.append(stripTitle);
  const list = document.createElement("div");
  list.className = "rv-candidate-list";
  const candidates = candidatesFor(role);
  if (role.candidates.length === 0) {
    const notice = document.createElement("p");
    notice.className = "rv-notice";
    notice.textContent = t("candidateMissing");
    strip.append(notice);
  }
  for (const entry of candidates) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-candidate";
    item.dataset.candidate = entry.id;
    item.classList.toggle("is-selected", entry.id === candidate.id);
    const thumb = document.createElement("img");
    thumb.alt = "";
    thumb.loading = "lazy";
    void loadVerifiedImage(entry.thumbnailUrl, entry.thumbnailSha256)
      .then((loaded) => { thumb.src = loaded.src; })
      .catch(() => { item.classList.add("is-broken"); });
    const label = document.createElement("span");
    label.textContent = entry.primary
      ? t("candidatePrimary")
      : `${entry.offsetFromSelected > 0 ? "+" : ""}${entry.offsetFromSelected}`;
    item.append(thumb, label);
    item.onclick = () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.frame.candidateId = entry.id;
        target.frame.status = "PENDING";
        target.quad.status = "PENDING";
        target.zones.status = "PENDING";
        if (target.lock.status === "LOCKED") {
          target.lock = { ...target.lock, status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null };
        }
        target.compare = { verdicts: [], note: target.compare.note };
        target.step = 1;
      });
    };
    list.append(item);
  }
  strip.append(list);
  if (!candidate.primary) {
    const warning = document.createElement("p");
    warning.className = "rv-notice rv-notice--warn";
    warning.textContent = t("alternateFrameWarning");
    strip.append(warning);
  }
  main.append(strip);

  const rejectPanel = document.createElement("div");
  rejectPanel.className = "rv-reject";
  rejectPanel.hidden = current.frame.status !== "REJECTED";
  const rejectTitle = document.createElement("h4");
  rejectTitle.textContent = t("rejectReasonTitle");
  rejectPanel.append(rejectTitle);
  const reasons = document.createElement("div");
  reasons.className = "rv-chips";
  const REASON_LABEL: Record<FrameRejectReason, Parameters<typeof t>[0]> = {
    "motion-blur": "reasonMotionBlur",
    "cursor-occlusion": "reasonCursor",
    "highlight-occlusion": "reasonHighlight",
    "card-clipped": "reasonClipped",
    "wrong-role": "reasonWrongRole",
    "boundary-unclear": "reasonUnclear",
  };
  const chosen = new Set<FrameRejectReason>(current.frame.rejectionReasons);
  for (const reason of FRAME_REJECT_REASONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "rv-chip-button";
    chip.dataset.reason = reason;
    chip.textContent = t(REASON_LABEL[reason]);
    chip.setAttribute("aria-pressed", String(chosen.has(reason)));
    chip.classList.toggle("is-on", chosen.has(reason));
    chip.onclick = () => {
      const next = new Set(chosen);
      if (next.has(reason)) next.delete(reason);
      else next.add(reason);
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.frame.rejectionReasons = [...next];
        target.frame.status = next.size > 0 ? "REJECTED" : "PENDING";
        if (next.size > 0) {
          target.quad.status = "PENDING";
          target.zones.status = "PENDING";
          target.lock = { ...target.lock, status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null };
          target.compare = { verdicts: [], note: target.compare.note };
          target.step = 1;
        }
      });
    };
    reasons.append(chip);
  }
  rejectPanel.append(reasons);
  main.append(rejectPanel);

  const acceptButton = button(t("acceptFrame"), () => {
    mutate((draft) => {
      const target = draft.roles[role.id];
      target.frame.status = "ACCEPTED";
      target.frame.candidateId = candidate.id;
      target.frame.rejectionReasons = [];
      target.step = 2;
      if (!target.quad.quadNormalized && role.suggestedQuadNormalized) {
        target.quad.quadNormalized = role.suggestedQuadNormalized;
      }
    });
  }, "primary", "rv-accept-frame");
  const rejectButton = button(t("rejectFrame"), () => {
    rejectPanel.hidden = false;
    rejectPanel.scrollIntoView({ block: "nearest" });
  }, "danger", "rv-reject-frame");
  const anotherButton = button(t("chooseAnother"), () => {
    list.scrollIntoView({ block: "nearest", behavior: "smooth" });
    (list.querySelector<HTMLElement>(".rv-candidate:not(.is-selected)"))?.focus();
  }, "quiet", "rv-choose-frame");
  main.append(actionBar(acceptButton, anotherButton, rejectButton));

  requestAnimationFrame(() => {
    fitStage(frameStage);
    fitStage(previewStage);
    drawSourceFrame(frameStage, frameCanvas, image, quad);
    drawCardPreview(previewStage, previewCanvas, image, quad);
  });
}

function stageSize(stage: HTMLElement): { width: number; height: number; ratio: number } {
  const rect = stage.getBoundingClientRect();
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  return { width: Math.max(2, Math.round(rect.width)), height: Math.max(2, Math.round(rect.height)), ratio };
}

function prepareCanvas(stage: HTMLElement, canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const { width, height, ratio } = stageSize(stage);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2D canvas is unavailable");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  return context;
}

function drawSourceFrame(
  stage: HTMLElement,
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  quad: NormalizedQuad | null,
): void {
  const context = prepareCanvas(stage, canvas);
  const { width, height } = stageSize(stage);
  context.clearRect(0, 0, width, height);
  const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;
  context.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);
  if (!quad) return;
  context.save();
  context.strokeStyle = "#c9f35b";
  context.lineWidth = 3;
  context.setLineDash([]);
  context.beginPath();
  quad.forEach(([x, y], index) => {
    const px = offsetX + x * drawWidth;
    const py = offsetY + y * drawHeight;
    if (index === 0) context.moveTo(px, py);
    else context.lineTo(px, py);
  });
  context.closePath();
  context.stroke();
  context.strokeStyle = "rgba(201, 243, 91, 0.28)";
  context.lineWidth = 12;
  context.stroke();
  context.restore();
}

function drawCardPreview(
  stage: HTMLElement,
  canvas: HTMLCanvasElement,
  image: HTMLImageElement,
  quad: NormalizedQuad | null,
): void {
  const context = prepareCanvas(stage, canvas);
  const { width, height } = stageSize(stage);
  context.clearRect(0, 0, width, height);
  if (!quad) return;
  const box = quadBoundingBox(quad as Quad, image.naturalWidth, image.naturalHeight);
  const padX = box.width * 0.14;
  const padY = box.height * 0.14;
  const sx = Math.max(0, box.x - padX);
  const sy = Math.max(0, box.y - padY);
  const sw = Math.min(image.naturalWidth - sx, box.width + padX * 2);
  const sh = Math.min(image.naturalHeight - sy, box.height + padY * 2);
  const scale = Math.min(width / sw, height / sh);
  const drawWidth = sw * scale;
  const drawHeight = sh * scale;
  const offsetX = (width - drawWidth) / 2;
  const offsetY = (height - drawHeight) / 2;
  context.drawImage(image, sx, sy, sw, sh, offsetX, offsetY, drawWidth, drawHeight);
  context.save();
  context.strokeStyle = "rgba(201, 243, 91, 0.9)";
  context.lineWidth = 2;
  context.beginPath();
  quad.forEach(([x, y], index) => {
    const px = offsetX + (x * image.naturalWidth - sx) * scale;
    const py = offsetY + (y * image.naturalHeight - sy) * scale;
    if (index === 0) context.moveTo(px, py);
    else context.lineTo(px, py);
  });
  context.closePath();
  context.stroke();
  context.restore();
}

/* ------------------------------------------------------------------ step 2 */

interface QuadView {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

let quadZoom = 1;

function quadView(image: HTMLImageElement, quad: NormalizedQuad, stageAspect: number, zoom: number): QuadView {
  const box = quadBoundingBox(quad as Quad, image.naturalWidth, image.naturalHeight);
  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  let viewWidth = Math.max(box.width * STAGE_PADDING, box.height * STAGE_PADDING * stageAspect);
  let viewHeight = viewWidth / stageAspect;
  viewWidth /= zoom;
  viewHeight /= zoom;
  return { sx: centerX - viewWidth / 2, sy: centerY - viewHeight / 2, sw: viewWidth, sh: viewHeight };
}

async function renderStep2(main: HTMLElement, role: ReviewerRoleEvidence, current: ReviewerRoleState): Promise<void> {
  main.append(stepHeader("step2Title", "step2Lead"));
  const body = document.createElement("div");
  body.className = "rv-step-body rv-step-body--quad";
  main.append(body);

  const candidate = selectedCandidate(role, current);
  const image = await candidateImage(role, candidate);
  let quad = (current.quad.quadNormalized ?? role.suggestedQuadNormalized) as NormalizedQuad | null;
  if (!quad) {
    const notice = document.createElement("p");
    notice.className = "rv-notice rv-notice--warn";
    notice.textContent = t("candidateMissing");
    body.append(notice);
    return;
  }

  const box = quadBoundingBox(quad as Quad, image.naturalWidth, image.naturalHeight);
  const stageAspect = box.width / box.height;
  // A wide card cannot fill a tall two-column stage, so the panels stack and
  // the review stage takes the full width instead of leaving black space.
  body.dataset.layout = stageAspect > 1.5 ? "stacked" : "columns";

  const left = document.createElement("section");
  left.className = "rv-panel rv-panel--grow";
  const zoomBar = document.createElement("div");
  zoomBar.className = "rv-zoombar";
  const zoomLabel = document.createElement("span");
  zoomLabel.textContent = t("zoomLabel");
  zoomBar.append(zoomLabel);
  for (const level of [1, 2, 4]) {
    const zoomButton = document.createElement("button");
    zoomButton.type = "button";
    zoomButton.className = "rv-chip-button";
    zoomButton.dataset.zoom = String(level);
    zoomButton.textContent = `${level}×`;
    zoomButton.classList.toggle("is-on", quadZoom === level);
    zoomButton.onclick = () => { quadZoom = level; void render(); };
    zoomBar.append(zoomButton);
  }
  const coverage = document.createElement("output");
  coverage.id = "rv-coverage";
  coverage.className = "rv-coverage";
  zoomBar.append(coverage);
  const { frame: stageFrame, stage } = stageBox(stageAspect, "rv-quad-stage");
  const canvas = canvasIn(stage);
  const overlay = svgIn(stage, 1000, 1000);
  const loupe = document.createElement("div");
  loupe.className = "rv-loupe";
  loupe.hidden = true;
  const loupeCanvas = document.createElement("canvas");
  loupeCanvas.width = 190;
  loupeCanvas.height = 190;
  loupe.append(loupeCanvas);
  stage.append(loupe);
  left.append(zoomBar, stageFrame);

  const right = document.createElement("section");
  right.className = "rv-panel";
  const rightTitle = document.createElement("h3");
  rightTitle.textContent = t("rectifiedCard");
  const planeHost = document.createElement("div");
  planeHost.className = "rv-plane-host";
  planeHost.id = "rv-quad-plane";
  const hint = document.createElement("p");
  hint.className = "rv-hint";
  hint.textContent = t("loupeHint");
  right.append(rightTitle, planeHost, hint);
  body.append(left, right);

  const draw = (previewOnly = false): void => {
    fitStage(stage);
    const context = prepareCanvas(stage, canvas);
    const { width, height } = stageSize(stage);
    const view = quadView(image, quad!, width / height, quadZoom);
    context.clearRect(0, 0, width, height);
    context.drawImage(image, view.sx, view.sy, view.sw, view.sh, 0, 0, width, height);
    overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
    overlay.replaceChildren();
    const toStage = ([x, y]: [number, number]): [number, number] => [
      ((x * image.naturalWidth - view.sx) / view.sw) * width,
      ((y * image.naturalHeight - view.sy) / view.sh) * height,
    ];
    const points = quad!.map(toStage);
    overlay.append(svgNode("polygon", {
      class: "rv-quad-outline",
      points: points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" "),
    }));
    const labels = [t("cornerTL"), t("cornerTR"), t("cornerBR"), t("cornerBL")];
    points.forEach(([x, y], index) => {
      overlay.append(svgNode("circle", { class: "rv-handle-hit", cx: x, cy: y, r: 26, "data-corner": index, tabindex: 0, role: "slider", "aria-label": labels[index] }));
      overlay.append(svgNode("circle", { class: "rv-handle", cx: x, cy: y, r: 9 }));
    });
    // Coverage is measured on the projected card, not on the normalized quad:
    // the stage shows a cropped view, so the normalized coordinates alone say
    // nothing about how much of the review stage the card actually fills.
    const projected = points.map(([x, y]) => [x / width, y / height] as [number, number]) as NormalizedQuad;
    const fill = quadArea(projected as Quad, width, height) / (width * height);
    coverage.textContent = `${t("coverageLabel")} ${percent(fill, 0)}`;
    coverage.dataset.fill = fill.toFixed(4);
    coverage.dataset.ok = String(fill >= 0.65);
    if (!previewOnly) {
      const plane = rectified(role, image, quad!, PLANE_SIZE);
      planeHost.replaceChildren(plane.canvas);
      plane.canvas.className = "rv-plane-canvas";
    }
  };

  const setLoupe = (cornerIndex: number | null, clientX = 0, clientY = 0): void => {
    if (cornerIndex === null) {
      loupe.hidden = true;
      return;
    }
    const rect = stage.getBoundingClientRect();
    const { width, height } = stageSize(stage);
    const view = quadView(image, quad!, width / height, quadZoom);
    const [nx, ny] = quad![cornerIndex];
    const context = loupeCanvas.getContext("2d");
    if (!context) return;
    const zoomFactor = 6;
    const sourceSpan = (view.sw / width) * (loupeCanvas.width / zoomFactor);
    context.imageSmoothingEnabled = false;
    context.clearRect(0, 0, loupeCanvas.width, loupeCanvas.height);
    context.drawImage(
      image,
      nx * image.naturalWidth - sourceSpan / 2,
      ny * image.naturalHeight - sourceSpan / 2,
      sourceSpan,
      sourceSpan,
      0,
      0,
      loupeCanvas.width,
      loupeCanvas.height,
    );
    context.strokeStyle = "#c9f35b";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(loupeCanvas.width / 2, 0);
    context.lineTo(loupeCanvas.width / 2, loupeCanvas.height);
    context.moveTo(0, loupeCanvas.height / 2);
    context.lineTo(loupeCanvas.width, loupeCanvas.height / 2);
    context.stroke();
    loupe.hidden = false;
    const localX = clientX - rect.left;
    const localY = clientY - rect.top;
    loupe.style.left = `${Math.min(rect.width - 200, Math.max(10, localX + 24))}px`;
    loupe.style.top = `${Math.min(rect.height - 200, Math.max(10, localY - 210))}px`;
  };

  let dragging: number | null = null;
  overlay.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Element ? event.target.closest<SVGElement>("[data-corner]") : null;
    if (!target) return;
    dragging = Number(target.dataset.corner);
    overlay.setPointerCapture(event.pointerId);
    setLoupe(dragging, event.clientX, event.clientY);
    event.preventDefault();
  });
  overlay.addEventListener("pointermove", (event) => {
    if (dragging === null) return;
    const rect = stage.getBoundingClientRect();
    const { width, height } = stageSize(stage);
    const view = quadView(image, quad!, width / height, quadZoom);
    const sourceX = view.sx + ((event.clientX - rect.left) / rect.width) * view.sw;
    const sourceY = view.sy + ((event.clientY - rect.top) / rect.height) * view.sh;
    const next = quad!.map((point) => [...point] as [number, number]) as NormalizedQuad;
    next[dragging] = [
      Math.min(1, Math.max(0, sourceX / image.naturalWidth)),
      Math.min(1, Math.max(0, sourceY / image.naturalHeight)),
    ];
    if (!quadIsLegal(next)) return;
    quad = next;
    draw(true);
    setLoupe(dragging, event.clientX, event.clientY);
  });
  const endDrag = (event: PointerEvent): void => {
    if (dragging === null) return;
    if (overlay.hasPointerCapture(event.pointerId)) overlay.releasePointerCapture(event.pointerId);
    dragging = null;
    setLoupe(null);
    mutate((draft) => {
      const target = draft.roles[role.id];
      target.quad.quadNormalized = quad;
      target.quad.status = "PENDING";
      target.zones.status = "PENDING";
      if (target.lock.status === "LOCKED") {
        target.lock = { ...target.lock, status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null };
      }
    }, { rerender: false });
    draw();
  };
  overlay.addEventListener("pointerup", endDrag);
  overlay.addEventListener("pointercancel", endDrag);
  overlay.addEventListener("keydown", (event) => {
    const target = event.target instanceof Element ? event.target.closest<SVGElement>("[data-corner]") : null;
    if (!target || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    const index = Number(target.dataset.corner);
    const step = event.shiftKey ? 0.004 : 0.0004;
    const [x, y] = quad![index];
    const next = quad!.map((point) => [...point] as [number, number]) as NormalizedQuad;
    next[index] = [
      Math.min(1, Math.max(0, x + (event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0))),
      Math.min(1, Math.max(0, y + (event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0))),
    ];
    if (!quadIsLegal(next)) return;
    quad = next;
    event.preventDefault();
    draw();
    mutate((draft) => {
      draft.roles[role.id].quad.quadNormalized = quad;
      draft.roles[role.id].quad.status = "PENDING";
    }, { rerender: false });
  });

  main.append(actionBar(
    button(t("acceptQuad"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.quad.quadNormalized = quad;
        target.quad.status = "ACCEPTED";
        target.step = 3;
        if (!target.zones.widths) target.zones.widths = { ...SUGGESTED_ZONE_WIDTHS };
      });
    }, "primary", "rv-accept-quad"),
    button(t("resetQuad"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.quad.quadNormalized = role.suggestedQuadNormalized;
        target.quad.status = "PENDING";
      });
    }, "quiet", "rv-reset-quad"),
    button(t("back"), () => mutate((draft) => { draft.roles[role.id].step = 1; }), "quiet", "rv-back"),
    button(t("rejectFrame"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.step = 1;
        target.frame.status = "PENDING";
      });
    }, "danger", "rv-reject-from-quad"),
  ));

  requestAnimationFrame(() => draw());
}

/* ------------------------------------------------------------------ step 3 */

type ZoneFocus = "all" | "top" | "right" | "bottom" | "left" | "tl" | "tr" | "br" | "bl";
let zoneFocus: ZoneFocus = "all";
let zoneZoom = 4;

const FOCUS_LABEL: Record<ZoneFocus, Parameters<typeof t>[0]> = {
  all: "viewWhole",
  top: "viewTop",
  right: "viewRight",
  bottom: "viewBottom",
  left: "viewLeft",
  tl: "viewCornerTL",
  tr: "viewCornerTR",
  br: "viewCornerBR",
  bl: "viewCornerBL",
};

function focusRect(focus: ZoneFocus, plane: RectifiedPlane, zoom: number): { x: number; y: number; w: number; h: number } {
  if (focus === "all") return { x: 0, y: 0, w: plane.width, h: plane.height };
  const w = plane.width / zoom;
  const h = plane.height / zoom;
  const centers: Record<Exclude<ZoneFocus, "all">, [number, number]> = {
    top: [0.5, 0],
    right: [1, 0.5],
    bottom: [0.5, 1],
    left: [0, 0.5],
    tl: [0, 0],
    tr: [1, 0],
    br: [1, 1],
    bl: [0, 1],
  };
  const [u, v] = centers[focus];
  const [cx, cy] = cardToPlanePixel(plane, u, v);
  return {
    x: Math.min(Math.max(cx - w / 2, 0), plane.width - w),
    y: Math.min(Math.max(cy - h / 2, 0), plane.height - h),
    w,
    h,
  };
}

async function renderStep3(main: HTMLElement, role: ReviewerRoleEvidence, current: ReviewerRoleState): Promise<void> {
  main.append(stepHeader("step3Title", "step3Lead"));
  const body = document.createElement("div");
  body.className = "rv-step-body rv-step-body--zones";
  main.append(body);

  const candidate = selectedCandidate(role, current);
  const image = await candidateImage(role, candidate);
  const quad = workingQuad(role, current);
  if (!quad) return;
  const plane = rectified(role, image, quad, PLANE_SIZE);
  const metrics: CardMetrics = cardMetrics(quad as Quad, image.naturalWidth, image.naturalHeight);
  body.dataset.layout = plane.width / plane.height > 1.5 ? "stacked" : "columns";
  let widths = workingWidths(current);

  const left = document.createElement("section");
  left.className = "rv-panel rv-panel--grow";
  const focusBar = document.createElement("div");
  focusBar.className = "rv-zoombar";
  for (const focus of ["all", "top", "right", "bottom", "left", "tl", "tr", "br", "bl"] as ZoneFocus[]) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-chip-button";
    item.dataset.focus = focus;
    item.textContent = t(FOCUS_LABEL[focus]);
    item.classList.toggle("is-on", zoneFocus === focus);
    item.onclick = () => { zoneFocus = focus; void render(); };
    focusBar.append(item);
  }
  for (const level of [4, 8]) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-chip-button rv-chip-button--zoom";
    item.dataset.zoneZoom = String(level);
    item.textContent = `${level}×`;
    item.classList.toggle("is-on", zoneZoom === level);
    item.onclick = () => { zoneZoom = level; if (zoneFocus !== "all") void render(); };
    focusBar.append(item);
  }
  const { frame: stageFrame, stage } = stageBox(plane.width / plane.height, "rv-zone-stage");
  const canvas = canvasIn(stage);
  const overlay = svgIn(stage, 1000, 1000);
  left.append(focusBar, stageFrame);

  const right = document.createElement("section");
  right.className = "rv-panel";
  const legendTitle = document.createElement("h3");
  legendTitle.textContent = t("derivedPercent");
  const legend = document.createElement("dl");
  legend.className = "rv-zone-legend";
  right.append(legendTitle, legend);
  const dragHint = document.createElement("p");
  dragHint.className = "rv-hint";
  dragHint.textContent = t("dragHint");
  right.append(dragHint);
  body.append(left, right);

  const renderLegend = (): void => {
    legend.replaceChildren();
    const bounds = boundariesFromWidths(widths);
    const rows: Array<[string, string, string, string]> = [
      ["center", t("zoneCenter"), t("zoneCenterHelp"), percent(Math.max(0, 1 - bounds.opticalShoulderToCenterFace * 2))],
      ["shoulder", t("zoneShoulder"), t("zoneShoulderHelp"), percent(widths.shoulder)],
      ["rim", t("zoneRim"), t("zoneRimHelp"), percent(widths.strongRim)],
      ["sidewall", t("zoneSidewall"), t("zoneSidewallHelp"), percent(widths.sidewall)],
    ];
    for (const [key, term, help, value] of rows) {
      const row = document.createElement("div");
      row.dataset.zone = key;
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.innerHTML = `<b data-zone-width="${key}">${value}</b><span>${help}</span>`;
      row.append(dt, dd);
      legend.append(row);
    }
  };

  const draw = (): void => {
    fitStage(stage);
    const context = prepareCanvas(stage, canvas);
    const { width, height } = stageSize(stage);
    const view = focusRect(zoneFocus, plane, zoneZoom);
    context.clearRect(0, 0, width, height);
    context.imageSmoothingEnabled = zoneFocus === "all";
    context.drawImage(plane.canvas, view.x, view.y, view.w, view.h, 0, 0, width, height);
    overlay.setAttribute("viewBox", `0 0 ${width} ${height}`);
    overlay.replaceChildren();
    const toStage = (u: number, v: number): [number, number] => {
      const [px, py] = cardToPlanePixel(plane, u, v);
      return [((px - view.x) / view.w) * width, ((py - view.y) / view.h) * height];
    };
    const bounds = boundariesFromWidths(widths);
    const boundaries: Array<[number, string, number]> = [
      [bounds.sidewallToStrongLensRim, "rim", 0],
      [bounds.strongLensRimToOpticalShoulder, "shoulder", 1],
      [bounds.opticalShoulderToCenterFace, "center", 2],
    ];
    overlay.append(svgNode("polygon", {
      class: "rv-card-outline",
      points: [toStage(0, 0), toStage(1, 0), toStage(1, 1), toStage(0, 1)].map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" "),
    }));
    for (const [ratio, tone, index] of boundaries) {
      const { u, v } = zoneInsetFractions(metrics, ratio);
      const corners = [toStage(u, v), toStage(1 - u, v), toStage(1 - u, 1 - v), toStage(u, 1 - v)];
      const points = corners.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
      overlay.append(svgNode("polygon", { class: `rv-zone-line rv-zone-line--${tone}`, points }));
      overlay.append(svgNode("polygon", { class: "rv-zone-hit", points, "data-boundary": index }));
    }
    renderLegend();
  };

  let draggingBoundary: number | null = null;
  const pointerRatio = (event: PointerEvent): number => {
    const rect = stage.getBoundingClientRect();
    const { width, height } = stageSize(stage);
    const view = focusRect(zoneFocus, plane, zoneZoom);
    const planeX = view.x + ((event.clientX - rect.left) / rect.width) * view.w;
    const planeY = view.y + ((event.clientY - rect.top) / rect.height) * view.h;
    const [u, v] = planePixelToCard(plane, planeX, planeY);
    const candidates: Array<"top" | "right" | "bottom" | "left"> = ["top", "right", "bottom", "left"];
    return Math.min(...candidates.map((edge) => cardPositionToRatio(metrics, u, v, edge)));
  };
  overlay.addEventListener("pointerdown", (event) => {
    const target = event.target instanceof Element ? event.target.closest<SVGElement>("[data-boundary]") : null;
    if (!target) return;
    draggingBoundary = Number(target.dataset.boundary);
    overlay.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  overlay.addEventListener("pointermove", (event) => {
    if (draggingBoundary === null) return;
    widths = withBoundaryAt(widths, draggingBoundary as 0 | 1 | 2, pointerRatio(event));
    draw();
  });
  const endBoundaryDrag = (event: PointerEvent): void => {
    if (draggingBoundary === null) return;
    if (overlay.hasPointerCapture(event.pointerId)) overlay.releasePointerCapture(event.pointerId);
    draggingBoundary = null;
    mutate((draft) => {
      const target = draft.roles[role.id];
      target.zones.widths = widths;
      target.zones.status = "PENDING";
      if (target.lock.status === "LOCKED") {
        target.lock = { ...target.lock, status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null };
      }
    }, { rerender: false });
  };
  overlay.addEventListener("pointerup", endBoundaryDrag);
  overlay.addEventListener("pointercancel", endBoundaryDrag);

  main.append(actionBar(
    button(t("acceptZones"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.zones.widths = widths;
        target.zones.status = "ACCEPTED";
        target.step = 4;
      });
    }, "primary", "rv-accept-zones"),
    button(t("resetZones"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.zones.widths = { ...SUGGESTED_ZONE_WIDTHS };
        target.zones.status = "PENDING";
      });
    }, "quiet", "rv-reset-zones"),
    button(t("boundaryUnclear"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.zones.widths = widths;
        target.zones.status = "UNCLEAR";
      });
    }, "quiet", "rv-zones-unclear"),
    button(t("back"), () => mutate((draft) => { draft.roles[role.id].step = 2; }), "quiet", "rv-back"),
    button(t("rejectFrame"), () => {
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.step = 1;
        target.frame.status = "PENDING";
        target.quad.status = "PENDING";
        target.zones.status = "PENDING";
      });
    }, "danger", "rv-reject-from-zones"),
  ));

  requestAnimationFrame(() => draw());
}

/* ------------------------------------------------------------------ step 4 */

function cropCanvas(plane: RectifiedPlane, u: number, v: number, span: number, size = 150): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  const [cx, cy] = cardToPlanePixel(plane, u, v);
  const half = (plane.width * span) / 2;
  context.imageSmoothingEnabled = false;
  context.drawImage(plane.canvas, cx - half, cy - half, half * 2, half * 2, 0, 0, size, size);
  return canvas;
}

async function renderStep4(main: HTMLElement, role: ReviewerRoleEvidence, current: ReviewerRoleState): Promise<void> {
  main.append(stepHeader("step4Title", "step4Lead"));
  const body = document.createElement("div");
  body.className = "rv-step-body rv-step-body--lock";
  main.append(body);

  const candidate = selectedCandidate(role, current);
  const image = await candidateImage(role, candidate);
  const quad = workingQuad(role, current);
  if (!quad) return;
  const plane = rectified(role, image, quad, PLANE_SIZE);
  const widths = workingWidths(current);
  const bounds = boundariesFromWidths(widths);

  const summary = document.createElement("section");
  summary.className = "rv-panel";
  const planeHost = document.createElement("div");
  planeHost.className = "rv-plane-host";
  planeHost.append(plane.canvas);
  plane.canvas.className = "rv-plane-canvas";
  summary.append(planeHost);

  const facts = document.createElement("dl");
  facts.className = "rv-facts";
  const rows: Array<[string, string]> = [
    [t("summaryFrame"), `${candidate.primary ? t("candidatePrimary") : `#${candidate.frameIndex}`} · ${shortHash(role.targetFrameSha256)}`],
    [t("summaryQuad"), quad.map(([x, y]) => `${x.toFixed(3)}/${y.toFixed(3)}`).join("  ")],
    [t("zoneSidewall"), percent(widths.sidewall, 2)],
    [t("zoneRim"), percent(widths.strongRim, 2)],
    [t("zoneShoulder"), percent(widths.shoulder, 2)],
    [t("zoneCenter"), percent(Math.max(0, 1 - bounds.opticalShoulderToCenterFace * 2), 2)],
    [t("annotationHash"), current.lock.targetAnnotationSha256 ? shortHash(current.lock.targetAnnotationSha256, 24) : "—"],
  ];
  for (const [term, value] of rows) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    row.append(dt, dd);
    facts.append(row);
  }
  summary.append(facts);

  const crops = document.createElement("section");
  crops.className = "rv-panel";
  const cropTitle = document.createElement("h3");
  cropTitle.textContent = `${t("summaryEdges")} · ${t("summaryCorners")}`;
  crops.append(cropTitle);
  const cropGrid = document.createElement("div");
  cropGrid.className = "rv-crop-grid";
  const spots: Array<[string, number, number]> = [
    [t("viewTop"), 0.5, 0],
    [t("viewRight"), 1, 0.5],
    [t("viewBottom"), 0.5, 1],
    [t("viewLeft"), 0, 0.5],
    [t("viewCornerTL"), 0, 0],
    [t("viewCornerTR"), 1, 0],
    [t("viewCornerBR"), 1, 1],
    [t("viewCornerBL"), 0, 1],
  ];
  for (const [label, u, v] of spots) {
    const figure = document.createElement("figure");
    figure.className = "rv-crop";
    figure.append(cropCanvas(plane, u, v, 0.16));
    const caption = document.createElement("figcaption");
    caption.textContent = label;
    figure.append(caption);
    cropGrid.append(figure);
  }
  crops.append(cropGrid);
  body.append(summary, crops);

  const locked = current.lock.status === "LOCKED";
  if (locked) {
    const notice = document.createElement("p");
    notice.className = "rv-notice";
    notice.textContent = `${t("lockedNotice")} ${t("annotationHash")}: ${current.lock.targetAnnotationSha256}`;
    main.append(notice);
  }

  const lockButton = button(t("lockButton"), () => {
    void (async () => {
      const hash = await computeTargetAnnotationHash({
        roleId: role.id,
        targetCategory: role.targetCategory,
        targetFrameSha256: role.targetFrameSha256,
        sourceVideoSha256: state.sourceVideoSha256,
        evidenceBinding: state.evidenceBinding,
      }, {
        ...current,
        quad: { status: "ACCEPTED", quadNormalized: quad },
        zones: { status: "ACCEPTED", widths },
      });
      mutate((draft) => {
        const target = draft.roles[role.id];
        target.quad.quadNormalized = quad;
        target.quad.status = "ACCEPTED";
        target.zones.widths = widths;
        target.zones.status = "ACCEPTED";
        target.lock = {
          status: "LOCKED",
          targetAnnotationSha256: hash,
          lockedAt: new Date().toISOString(),
          unlockCount: target.lock.unlockCount,
          unlockReason: target.lock.unlockReason,
        };
        target.step = 5;
      });
    })();
  }, "primary", "rv-lock");
  const unlockButton = button(t("unlockButton"), () => {
    const reason = window.prompt(t("unlockReasonPrompt"), current.lock.unlockReason || "");
    if (!reason || reason.trim().length < 8) return;
    mutate((draft) => {
      const target = draft.roles[role.id];
      target.lock = {
        status: "UNLOCKED",
        targetAnnotationSha256: null,
        lockedAt: null,
        unlockCount: target.lock.unlockCount + 1,
        unlockReason: reason.trim(),
      };
      target.compare = { verdicts: [], note: target.compare.note };
      target.step = 3;
    });
  }, "danger", "rv-unlock");

  main.append(actionBar(
    locked ? unlockButton : lockButton,
    ...(locked ? [button(t("next"), () => mutate((draft) => { draft.roles[role.id].step = 5; }), "primary", "rv-goto-compare")] : []),
    button(t("back"), () => mutate((draft) => { draft.roles[role.id].step = 3; }), "quiet", "rv-back"),
  ));
}

/* ------------------------------------------------------------------ step 5 */

type CompareOverlay = "none" | "edge" | "highlight" | "dispersion" | "sharpness";
let compareOverlay: CompareOverlay = "none";
let compareBlend = 0;

function analysisCanvas(image: HTMLImageElement, mode: CompareOverlay): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return canvas;
  context.drawImage(image, 0, 0);
  if (mode === "none") return canvas;
  const { width, height } = canvas;
  const source = context.getImageData(0, 0, width, height);
  const data = source.data;
  const luma = new Float32Array(width * height);
  for (let index = 0; index < width * height; index += 1) {
    const offset = index * 4;
    luma[index] = data[offset] * 0.2126 + data[offset + 1] * 0.7152 + data[offset + 2] * 0.0722;
  }
  const output = context.createImageData(width, height);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      const offset = index * 4;
      const gx = luma[index + 1] - luma[index - 1];
      const gy = luma[index + width] - luma[index - width];
      const gradient = Math.min(1, Math.hypot(gx, gy) / 90);
      const r = data[offset];
      const g = data[offset + 1];
      const b = data[offset + 2];
      const chroma = (Math.max(r, g, b) - Math.min(r, g, b)) / 255;
      let alpha = 0;
      let color: [number, number, number] = [201, 243, 91];
      if (mode === "edge") alpha = Math.max(0, gradient - 0.14);
      else if (mode === "highlight") {
        color = [255, 236, 170];
        alpha = Math.max(0, (luma[index] - 205) / 50);
      } else if (mode === "dispersion") {
        color = [238, 84, 208];
        alpha = Math.max(0, chroma - 0.09);
      } else {
        color = [82, 210, 224];
        alpha = Math.max(0, gradient - 0.05) * 0.9;
      }
      output.data[offset] = color[0];
      output.data[offset + 1] = color[1];
      output.data[offset + 2] = color[2];
      output.data[offset + 3] = Math.round(Math.min(1, alpha) * 235);
    }
  }
  context.putImageData(output, 0, 0);
  return canvas;
}

let compareFocus: ZoneFocus = "all";
let compareZoom = 4;
let comparePan = { x: 0, y: 0 };

interface CompareView { x: number; y: number; w: number; h: number }

/**
 * One view rectangle shared by target, local and the overlay. Because both card
 * planes are produced by the same rectification at the same size, the same
 * rectangle addresses the same edge or corner on both sides, which is what
 * makes the per-edge and per-corner regions correspond one to one.
 */
function compareView(width: number, height: number, focus: ZoneFocus, zoom: number): CompareView {
  if (focus === "all") return { x: 0, y: 0, w: width, h: height };
  const w = width / zoom;
  const h = height / zoom;
  const centers: Record<Exclude<ZoneFocus, "all">, [number, number]> = {
    top: [0.5, 0],
    right: [1, 0.5],
    bottom: [0.5, 1],
    left: [0, 0.5],
    tl: [0, 0],
    tr: [1, 0],
    br: [1, 1],
    bl: [0, 1],
  };
  const [u, v] = centers[focus];
  return {
    x: Math.min(Math.max(u * width - w / 2 + comparePan.x, 0), Math.max(0, width - w)),
    y: Math.min(Math.max(v * height - h / 2 + comparePan.y, 0), Math.max(0, height - h)),
    w,
    h,
  };
}

async function renderStep5(main: HTMLElement, role: ReviewerRoleEvidence, current: ReviewerRoleState): Promise<void> {
  main.append(stepHeader("step5Title", "step5Lead"));
  if (current.lock.status !== "LOCKED") {
    const notice = document.createElement("p");
    notice.className = "rv-notice rv-notice--warn";
    notice.textContent = t("lockedNotice");
    main.append(notice);
    return;
  }
  const body = document.createElement("div");
  body.className = "rv-step-body rv-step-body--compare";

  const [targetImage, localImage] = await Promise.all([
    planeAsset(role, "target-plane"),
    planeAsset(role, "local-plane"),
  ]);
  const planeWidth = Math.min(targetImage.naturalWidth, localImage.naturalWidth);
  const planeHeight = Math.min(targetImage.naturalHeight, localImage.naturalHeight);

  const controls = document.createElement("div");
  controls.className = "rv-zoombar";
  const OVERLAYS: Array<[CompareOverlay, Parameters<typeof t>[0]]> = [
    ["edge", "overlayEdge"],
    ["highlight", "overlayHighlight"],
    ["dispersion", "overlayDispersion"],
    ["sharpness", "overlaySharpness"],
  ];
  for (const [mode, key] of OVERLAYS) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-chip-button";
    item.dataset.overlay = mode;
    item.textContent = t(key);
    item.classList.toggle("is-on", compareOverlay === mode);
    item.onclick = () => { compareOverlay = compareOverlay === mode ? "none" : mode; void render(); };
    controls.append(item);
  }
  const blend = document.createElement("input");
  blend.type = "range";
  blend.min = "0";
  blend.max = "100";
  blend.value = String(compareBlend);
  blend.id = "rv-compare-blend";
  blend.setAttribute("aria-label", t("compareOverlay"));
  controls.append(blend);

  const focusBar = document.createElement("div");
  focusBar.className = "rv-zoombar";
  for (const focus of ["all", "top", "right", "bottom", "left", "tl", "tr", "br", "bl"] as ZoneFocus[]) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-chip-button";
    item.dataset.compareFocus = focus;
    item.textContent = t(FOCUS_LABEL[focus]);
    item.classList.toggle("is-on", compareFocus === focus);
    item.onclick = () => {
      compareFocus = focus;
      comparePan = { x: 0, y: 0 };
      void render();
    };
    focusBar.append(item);
  }
  for (const level of [4, 8]) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "rv-chip-button rv-chip-button--zoom";
    item.dataset.compareZoom = String(level);
    item.textContent = `${level}×`;
    item.classList.toggle("is-on", compareZoom === level);
    item.onclick = () => {
      compareZoom = level;
      comparePan = { x: 0, y: 0 };
      if (compareFocus !== "all") void render();
    };
    focusBar.append(item);
  }
  main.append(controls, focusBar, body);

  const targetBase = analysisCanvas(targetImage, "none");
  const localBase = analysisCanvas(localImage, "none");
  const targetTint = compareOverlay === "none" ? null : analysisCanvas(targetImage, compareOverlay);
  const localTint = compareOverlay === "none" ? null : analysisCanvas(localImage, compareOverlay);

  interface ComparePanel {
    canvas: HTMLCanvasElement;
    stage: HTMLElement;
    layers: Array<{ source: HTMLCanvasElement; alpha: number }>;
  }
  const panels: ComparePanel[] = [];

  const addPanel = (
    title: string,
    id: string,
    layers: Array<{ source: HTMLCanvasElement; alpha: number }>,
  ): void => {
    const panel = document.createElement("section");
    panel.className = "rv-panel";
    const heading = document.createElement("h3");
    heading.textContent = title;
    const { frame, stage } = stageBox(planeWidth / planeHeight, id);
    // The compare panels sit in a wrapping row, so the frame needs a definite
    // height of its own before the stage can be fitted inside it.
    frame.style.aspectRatio = String(planeWidth / planeHeight);
    frame.style.width = "100%";
    const canvas = canvasIn(stage);
    panel.append(heading, frame);
    body.append(panel);
    panels.push({ canvas, stage, layers });
  };

  addPanel(t("compareTarget"), "rv-compare-target", [
    { source: targetBase, alpha: 1 },
    ...(targetTint ? [{ source: targetTint, alpha: 1 }] : []),
  ]);
  addPanel(t("compareLocal"), "rv-compare-local", [
    { source: localBase, alpha: 1 },
    ...(localTint ? [{ source: localTint, alpha: 1 }] : []),
  ]);
  addPanel(t("compareOverlay"), "rv-compare-overlay", [
    { source: targetBase, alpha: 1 },
    { source: localBase, alpha: 0.5 },
  ]);

  const drawAll = (): void => {
    const view = compareView(planeWidth, planeHeight, compareFocus, compareZoom);
    for (const panel of panels) {
      fitStage(panel.stage);
      const context = prepareCanvas(panel.stage, panel.canvas);
      const { width, height } = stageSize(panel.stage);
      context.clearRect(0, 0, width, height);
      context.imageSmoothingEnabled = compareFocus === "all";
      for (const layer of panel.layers) {
        context.globalAlpha = layer.alpha;
        context.drawImage(layer.source, view.x, view.y, view.w, view.h, 0, 0, width, height);
      }
      context.globalAlpha = 1;
      panel.canvas.dataset.view = `${view.x.toFixed(1)},${view.y.toFixed(1)},${view.w.toFixed(1)},${view.h.toFixed(1)}`;
    }
  };

  blend.oninput = () => {
    compareBlend = Number(blend.value);
    const overlayPanel = panels[2];
    if (overlayPanel) overlayPanel.layers[1].alpha = 0.25 + compareBlend / 200;
    drawAll();
  };
  panels[2].layers[1].alpha = 0.25 + compareBlend / 200;

  // Dragging any panel pans all three by the same amount.
  let panPointer: { id: number; x: number; y: number } | null = null;
  for (const panel of panels) {
    panel.stage.addEventListener("pointerdown", (event) => {
      if (compareFocus === "all") return;
      panPointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
      panel.stage.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    panel.stage.addEventListener("pointermove", (event) => {
      if (!panPointer || panPointer.id !== event.pointerId) return;
      const { width } = stageSize(panel.stage);
      const scale = (planeWidth / compareZoom) / Math.max(1, width);
      comparePan = {
        x: comparePan.x - (event.clientX - panPointer.x) * scale,
        y: comparePan.y - (event.clientY - panPointer.y) * scale,
      };
      panPointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
      drawAll();
    });
    const endPan = (event: PointerEvent): void => {
      if (!panPointer || panPointer.id !== event.pointerId) return;
      if (panel.stage.hasPointerCapture(event.pointerId)) panel.stage.releasePointerCapture(event.pointerId);
      panPointer = null;
    };
    panel.stage.addEventListener("pointerup", endPan);
    panel.stage.addEventListener("pointercancel", endPan);
  }

  const notice = document.createElement("p");
  notice.className = "rv-notice";
  notice.textContent = t("noSsimNotice");
  main.append(notice);

  const verdictSection = document.createElement("section");
  verdictSection.className = "rv-panel";
  const verdictTitle = document.createElement("h3");
  verdictTitle.textContent = t("compareVerdictTitle");
  verdictSection.append(verdictTitle);
  const chips = document.createElement("div");
  chips.className = "rv-chips";
  const VERDICT_LABEL: Record<CompareVerdict, Parameters<typeof t>[0]> = {
    "local-looks-close": "verdictClose",
    "local-too-wide": "verdictTooWide",
    "local-too-narrow": "verdictTooNarrow",
    "wrong-refraction-direction": "verdictDirection",
    "highlight-mismatch": "verdictHighlight",
    "dispersion-mismatch": "verdictDispersion",
    "needs-later-review": "verdictLater",
  };
  const active = new Set<CompareVerdict>(current.compare.verdicts);
  for (const verdict of COMPARE_VERDICTS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "rv-chip-button";
    chip.dataset.verdict = verdict;
    chip.textContent = t(VERDICT_LABEL[verdict]);
    chip.classList.toggle("is-on", active.has(verdict));
    chip.setAttribute("aria-pressed", String(active.has(verdict)));
    chip.onclick = () => {
      const next = new Set(active);
      if (next.has(verdict)) next.delete(verdict);
      else next.add(verdict);
      mutate((draft) => { draft.roles[role.id].compare.verdicts = [...next]; });
    };
    chips.append(chip);
  }
  const note = document.createElement("textarea");
  note.className = "rv-note";
  note.id = "rv-compare-note";
  note.rows = 3;
  note.maxLength = 1200;
  note.placeholder = t("compareNote");
  note.value = current.compare.note;
  note.oninput = () => {
    mutate((draft) => { draft.roles[role.id].compare.note = note.value; }, { rerender: false });
  };
  verdictSection.append(chips, note);
  main.append(verdictSection);

  main.append(actionBar(
    button(t("back"), () => mutate((draft) => { draft.roles[role.id].step = 4; }), "quiet", "rv-back"),
  ));

  requestAnimationFrame(() => drawAll());
}

/* -------------------------------------------------------------------- boot */

async function render(): Promise<void> {
  const generation = ++renderGeneration;
  renderChrome();
  const main = document.querySelector<HTMLElement>("#rv-main")!;
  main.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "rv-hint";
  loading.textContent = t("loading");
  main.append(loading);

  if (tutorialOpen) {
    document.querySelector<HTMLElement>("#rv-example")!.replaceChildren();
    document.querySelector<HTMLElement>(".rv")!.dataset.view = "tutorial";
    const role = roleEvidence(ROLE_IDS[0]);
    let realCard: HTMLCanvasElement | null = null;
    try {
      const candidate = selectedCandidate(role);
      const image = await candidateImage(role, candidate);
      const quad = workingQuad(role);
      if (quad) realCard = rectified(role, image, quad, 460).canvas;
    } catch {
      realCard = null;
    }
    if (generation !== renderGeneration) return;
    main.replaceChildren(renderTutorial({
      realCard,
      onStart: () => {
        tutorialOpen = false;
        mutate((draft) => { draft.tutorialAcknowledged = true; });
      },
    }));
    return;
  }

  document.querySelector<HTMLElement>(".rv")!.dataset.view = "role";
  const role = roleEvidence();
  const current = roleState();
  const step = Math.min(current.step, maxReachableStep(current)) as ReviewerStep;
  if (step !== current.step) {
    state.roles[activeRoleId].step = step;
  }
  try {
    const staging = document.createElement("div");
    staging.className = "rv-step";
    if (step === 1) await renderStep1(staging, role, current);
    else if (step === 2) await renderStep2(staging, role, current);
    else if (step === 3) await renderStep3(staging, role, current);
    else if (step === 4) await renderStep4(staging, role, current);
    else await renderStep5(staging, role, current);
    if (generation !== renderGeneration) return;
    main.replaceChildren(...staging.childNodes);
    renderExample(step);
  } catch (error) {
    if (generation !== renderGeneration) return;
    setBlocked(error instanceof Error ? error.message : String(error));
  }
}

async function boot(): Promise<void> {
  shell();
  try {
    payload = await fetchReviewerState();
    roles = payload.roles;
    state = payload.state;
    setLanguage(state.language);
    activeRoleId = (state.activeRoleId && ROLE_IDS.includes(state.activeRoleId)) ? state.activeRoleId : ROLE_IDS[0];
    tutorialOpen = !state.tutorialAcknowledged;
    store = new ReviewerStore(payload, state, (status, detail) => {
      saveStatus = status;
      saveDetail = detail;
      state = store.snapshot();
      renderSaveState();
    });
    document.querySelector<HTMLElement>("#rv-blocked")!.hidden = true;
    document.body.dataset.reviewer = "ready";
    await render();
  } catch (error) {
    setBlocked(error instanceof Error ? error.message : String(error));
  }
}

let resizeTimer = 0;
window.addEventListener("resize", () => {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => { void render(); }, 180);
});

void boot();
