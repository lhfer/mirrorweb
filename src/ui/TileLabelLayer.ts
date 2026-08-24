import { CSS3DObject, CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { Quaternion, Scene, Vector3, type PerspectiveCamera } from "three/webgpu";
import { TILE } from "../config";
import { catalogAt } from "../content/catalog";
import { isLayoutDebug, type DebugMode } from "../debug/DebugMode";
import type { SourceExactLayoutFrame } from "../layout/SourceExactLayout";
import type { InfiniteGlassGrid } from "../scene/InfiniteGlassGrid";
import type { LabelCullingVerdict } from "./SourceExactLabelCulling";

const _dir = new Vector3();
const _toCam = new Vector3();
const _quat = new Quaternion();

/**
 * Guarded visibility write: the DOM is touched only when the state actually
 * changes. The Target guards its hide path exactly like this (`Po` in the
 * bundle); it assigns `visible` unconditionally, where this helper guards
 * both directions -- observationally identical, and the write hygiene the
 * V0 brief requires.
 */
function setVisibility(el: HTMLElement, visible: boolean): void {
  const want = visible ? "visible" : "hidden";
  if (el.style.visibility !== want) el.style.visibility = want;
}

/** Legacy paths (V3, composition v1/v2) keep the offset they were tuned with. */
const TYPE_Z = TILE.thickness * 0.5 + TILE.frontBulge + 6;

/**
 * Source-exact: the text plane sits ON the card plane. Zero, measured.
 *
 * Every Target label's CSS3D translation is exactly on the sphere -- the radial
 * distance from the sphere centre to the label's own world position is R to
 * within 1.2e-3 world units across 36 viewports, with no constant residual and
 * no term that scales with the responsive factor. There is no translateZ in the
 * Target at all, so there is none here. See
 * `qa-v5/t1/target-typography-contract.json` -> textPlaneDepth.
 */
const TYPE_Z_SOURCE_EXACT = 0;

function bindDebugCard(el: HTMLElement, i: number, j: number, slotIndex: number, mode: DebugMode) {
  el.className = "tile-card tile-card-debug";
  const top = document.createElement("div");
  top.className = "tile-card-top";
  const modeLabel = document.createElement("span");
  modeLabel.textContent = mode.toUpperCase();
  const slotLabel = document.createElement("span");
  slotLabel.textContent = `SLOT ${slotIndex}`;
  top.append(modeLabel, slotLabel);
  const bottom = document.createElement("div");
  bottom.className = "tile-card-bottom";
  const title = document.createElement("h2");
  title.textContent = `${i},${j}`;
  bottom.appendChild(title);
  el.replaceChildren(top, bottom);
}

function bindCatalogCard(el: HTMLElement, i: number, j: number, mode: DebugMode) {
  const item = catalogAt(i, j);
  el.className = mode === "typography" ? "tile-card is-type-debug" : "tile-card";
  el.style.setProperty("--accent", item.accent);
  const top = document.createElement("div");
  top.className = "tile-card-top";
  const meta = document.createElement("span");
  meta.textContent = `${item.code} ${item.category}`;
  const selectedWork = document.createElement("span");
  selectedWork.textContent = "SELECTED WORK — 2026";
  top.append(meta, selectedWork);
  const bottom = document.createElement("div");
  bottom.className = "tile-card-bottom";
  const title = document.createElement("h2");
  title.textContent = item.title;
  const rule = document.createElement("div");
  rule.className = "tile-rule";
  const deck = document.createElement("p");
  deck.className = "tile-deck";
  deck.textContent = item.deck;
  bottom.append(title, rule, deck);
  el.replaceChildren(top, bottom);
}

function bindCard(el: HTMLElement, i: number, j: number, slotIndex: number, mode: DebugMode) {
  if (isLayoutDebug(mode)) bindDebugCard(el, i, j, slotIndex, mode);
  else bindCatalogCard(el, i, j, mode);
}

/**
 * Slot identity and card structure on the source-exact path.
 *
 * The Target binds a card's label to its POOL SLOT, not to a world cell: its
 * ILG code is `slotIndex + 1` and a card keeps that code as it wraps.
 *
 * The element tree mirrors the Target's own, read from its DOM at seven
 * viewports (`qa-v5/t1/target-typography-contract.json`):
 *
 *   card            @container, box-border, sized to the card plane
 *     se-clip       absolute inset-0, overflow hidden   <- the only clip
 *       se-content  absolute inset-0, flex column, space-between, padding 7cqw
 *         se-meta   mono 1.7cqw / 1.5 / 0.18em / 500 / uppercase
 *         se-bottom rule -> title -> deck, in that order
 *
 * The rule sits ABOVE the title in the Target, not between the title and the
 * deck; the previous markup had it the other way round.
 */
function bindSlotCard(el: HTMLElement, code: number, slotIndex: number, mode: DebugMode) {
  if (isLayoutDebug(mode)) {
    bindDebugCard(el, slotIndex % 16, Math.floor(slotIndex / 16), slotIndex, mode);
    return;
  }
  const item = catalogAt(slotIndex, 0);
  el.className = mode === "typography" ? "tile-card-se is-type-debug" : "tile-card-se";
  el.style.setProperty("--accent", item.accent);
  // Slot identity on the element itself. `innerText` is render-aware and comes
  // back empty for a hidden label, so anything reading identity out of the DOM
  // -- container alignment, the depth-order probe -- needs a marker that does
  // not depend on the card being visible.
  el.dataset.slot = String(slotIndex);
  el.dataset.ilg = String(code);
  const label = `ILG\u2014${String(code).padStart(2, "0")}`;
  const clip = document.createElement("div");
  clip.className = "se-clip";
  const content = document.createElement("div");
  content.className = "se-content";
  const meta = document.createElement("div");
  meta.className = "se-meta";
  const metaLeft = document.createElement("div");
  metaLeft.className = "se-meta-left";
  const codeLabel = document.createElement("span");
  codeLabel.textContent = label;
  const category = document.createElement("span");
  category.className = "se-dim";
  category.textContent = item.category;
  metaLeft.append(codeLabel, category);
  const metaRight = document.createElement("div");
  metaRight.className = "se-meta-right";
  const selectedWork = document.createElement("span");
  selectedWork.textContent = "SELECTED WORK";
  const dot = document.createElement("span");
  dot.className = "se-dot";
  const year = document.createElement("span");
  year.textContent = "2026";
  metaRight.append(selectedWork, dot, year);
  meta.append(metaLeft, metaRight);
  const bottom = document.createElement("div");
  bottom.className = "se-bottom";
  const rule = document.createElement("div");
  rule.className = "se-rule";
  const title = document.createElement("h2");
  title.className = "se-title";
  title.textContent = item.title;
  const deckRow = document.createElement("div");
  deckRow.className = "se-deck-row";
  const deck = document.createElement("p");
  deck.className = "se-deck";
  deck.textContent = item.deck;
  deckRow.appendChild(deck);
  bottom.append(rule, title, deckRow);
  content.append(meta, bottom);
  clip.appendChild(content);
  el.replaceChildren(clip);
}

export class TileLabelLayer {
  readonly renderer = new CSS3DRenderer();
  readonly scene = new Scene();
  private objects: CSS3DObject[] = [];
  private boundKey: number[] = [];
  private mode: DebugMode = "off";
  /**
   * The one layout frame, on the source-exact path.
   *
   * Every label container is sized from THIS -- `planeWidth` x `planeHeight`,
   * with the CSS3D object scale left at 1. The alternative (a fixed reference
   * box scaled by `cardScale`) would land in the same place, but the two must
   * not be mixed, and the Target settles it: at all seven measured viewports
   * its label element's computed width equals the card plane width exactly and
   * the basis columns of its matrix3d are unit length, so its object scale is
   * 1. The elements are the ones that resize.
   *
   * Undefined on the legacy paths, which keep the fixed TILE box.
   */
  private frame?: SourceExactLayoutFrame;

  /** The pool the labels were attached to; `setFrame` needs it to re-mount. */
  private grid?: InfiniteGlassGrid;

  /**
   * The verdicts of the most recent `sync`, kept for QA readbacks only.
   * Undefined on the legacy paths and before the first culled sync.
   */
  /** The verdict array consumed by the last sync -- QA readback surface. */
  lastCulling?: LabelCullingVerdict[];

  constructor(host: HTMLElement) {
    this.renderer.domElement.style.position = "absolute";
    this.renderer.domElement.style.inset = "0";
    this.renderer.domElement.style.pointerEvents = "none";
    this.renderer.domElement.style.zIndex = "5";
    host.appendChild(this.renderer.domElement);
  }

  /**
   * How many label elements this layer should have mounted.
   *
   * On the source-exact path: `cols * rows` for the CURRENT viewport, and
   * nothing else. The Target renders `Array.from({length: b1.get()}, ...)`
   * where `b1` is set to `cols * rows` in the grid's own layout effect, so a
   * 1440x900 desktop has 100 label elements in its document and a 390x844
   * phone has 96 -- not the pool maximum, and not an overscanned pool around
   * the visible set. There is no recycling and no free list in the Target: an
   * element belongs to one slot index for as long as it is mounted, and a
   * cols/rows change adds or removes elements at the end of the array.
   *
   * We were mounting the WebGL pool's fixed 16x16 = 256 regardless, and hiding
   * the surplus. Those 156 extra elements are inert to look at and expensive to
   * own: they are 2.5x the Target's document, they are restyled on every
   * viewport change, and the previous round measured the cost of carrying them
   * as most of a ~40 ms main-thread block at an orientation flip against the
   * Target's ~10 ms.
   *
   * The WebGL pool is NOT touched by any of this -- it stays 256 slabs with the
   * surplus marked inactive, which is what the layout contract and every frozen
   * optical gate were measured against.
   */
  private mountCountFor(grid: InfiniteGlassGrid, frame?: SourceExactLayoutFrame): number {
    if (!frame) return grid.slots.length;
    return Math.max(0, Math.min(frame.activeSlotCount, grid.slots.length));
  }

  attach(grid: InfiniteGlassGrid, mode: DebugMode, frame?: SourceExactLayoutFrame) {
    this.clear();
    this.mode = mode;
    this.frame = frame;
    this.grid = grid;
    this.renderer.domElement.style.display = "block";
    this.mountTo(this.mountCountFor(grid, frame));
    this.applyBox();
  }

  /** Add or remove elements at the end of the array until there are `want`. */
  private mountTo(want: number): void {
    const grid = this.grid;
    if (!grid) return;
    for (let n = this.objects.length; n > want; n -= 1) {
      const object = this.objects[n - 1];
      this.scene.remove(object);
      object.element.remove();
      this.objects.pop();
      this.boundKey.pop();
    }
    for (let n = this.objects.length; n < want; n += 1) {
      const slot = grid.slots[n];
      if (!slot) break;
      const el = document.createElement("div");
      el.style.containerType = "inline-size";
      // Source-exact: the Target's label element carries
      // `backface-visibility: hidden` INLINE, and that CSS is its ONLY
      // backface handling -- there is no JS backface test in its culling.
      // A coverage-drawn but back-facing card must hide at paint, not render
      // mirrored. Byte-anchored in qa-v5/culling/target-culling-source.json
      // -> labelInitialStyle.
      if (this.frame) {
        el.style.backfaceVisibility = "hidden";
        // The Target mounts every label hidden and writes no transform until
        // the coverage test first draws it (`Ph`'s inline style is
        // `{transformStyle, willChange, visibility:"hidden",
        // backfaceVisibility}`, with no transform). An element that appears
        // mid-entry therefore cannot flash at the origin on its mount frame.
        el.style.visibility = "hidden";
      }
      if (slot.code !== undefined) bindSlotCard(el, slot.code, slot.slotIndex, this.mode);
      else bindCard(el, slot.i, slot.j, slot.slotIndex, this.mode);
      const object = new CSS3DObject(el);
      this.scene.add(object);
      this.objects.push(object);
      // Slot-bound cards never rebind: their identity does not change.
      this.boundKey.push(slot.code !== undefined ? Number.NaN : slot.i * 10007 + slot.j);
    }
  }

  /**
   * Re-point the type layer at a new layout frame.
   *
   * A resize changes the card plane, so it changes the label box with it --
   * and because every type size is a container query against that box, the
   * whole type scale follows from this one call. Nothing is rebound and no
   * element is recreated: slot identity, and the ILG code on it, survive.
   */
  setFrame(frame: SourceExactLayoutFrame): void {
    this.frame = frame;
    // A viewport change can change cols x rows, and with it how many labels
    // should exist. Elements are added or removed at the END of the array, so
    // every slot index that survives keeps its own element, its ILG code and
    // its bound copy -- the identity gates read exactly that.
    if (this.grid) this.mountTo(this.mountCountFor(this.grid, frame));
    this.applyBox();
  }

  /** How many label elements are in the document. */
  mountedCount(): number { return this.objects.length; }

  /** Write the current card box onto every label element. */
  private applyBox(): void {
    const w = this.frame ? this.frame.planeWidth : TILE.width;
    const h = this.frame ? this.frame.planeHeight : TILE.height;
    for (const object of this.objects) {
      object.element.style.width = `${w}px`;
      object.element.style.height = `${h}px`;
      // The object scale stays 1: the element is the thing that resizes. See
      // the note on `frame`.
      object.scale.set(1, 1, 1);
    }
  }

  /** QA only. The label boxes, so container alignment can be measured. */
  getLabelTruth(): Record<string, unknown> {
    const w = this.frame ? this.frame.planeWidth : TILE.width;
    const h = this.frame ? this.frame.planeHeight : TILE.height;
    return {
      sourceExact: Boolean(this.frame),
      elementBox: [w, h],
      framePlane: this.frame ? [this.frame.planeWidth, this.frame.planeHeight] : null,
      typeZ: this.frame ? TYPE_Z_SOURCE_EXACT : TYPE_Z,
      slots: this.objects.map((o, n) => {
        const r = o.element.getBoundingClientRect();
        const cs = getComputedStyle(o.element);
        const verdict = this.lastCulling ? this.lastCulling[n] : undefined;
        return {
          slotIndex: n,
          visible: o.element.style.visibility !== "hidden",
          cssWidth: parseFloat(cs.width),
          cssHeight: parseFloat(cs.height),
          objectScale: [o.scale.x, o.scale.y, o.scale.z],
          /**
           * Screen-space AABB of the projected element. On the source-exact
           * path a CULLED slot's rect is STALE BY DESIGN -- the Target
           * leaves culled transforms unwritten -- so a reader must treat
           * `rectPx` of a slot with `culling.coverageVisible === false` as
           * the last drawn pose, not the current one.
           */
          rectPx: [r.x, r.y, r.width, r.height],
          world: [o.position.x, o.position.y, o.position.z],
          /** The full coverage verdict, when the culled path is active. */
          culling: verdict ?? null,
        };
      }),
    };
  }

  /**
   * Per-slot pose and visibility.
   *
   * With `culling` verdicts (the source-exact path), visibility is the
   * Target's own rule and nothing else:
   *
   * - a coverage-drawn slot gets its pose synced and `visibility:visible`;
   * - a culled slot gets `visibility:hidden` and its pose is NOT touched --
   *   the Target leaves culled labels' transforms stale, and our
   *   CSS3DRenderer's style cache then skips their DOM transform writes for
   *   free. The motion round measured exactly this staleness on the Target's
   *   recorded card matrices.
   * - both writes are guarded on the current inline value. The Target guards
   *   only the hide and assigns `visible` unconditionally; the guard is
   *   observationally identical and declared in
   *   `qa-v5/culling/target-culling-source.json` -> observedNotApplied.
   *
   * The JS backface dot-product does NOT feed visibility on this path: the
   * Target has no JS backface test -- its labels carry inline
   * `backface-visibility: hidden` and ours now do too (see `attach`).
   *
   * Without `culling` (legacy V3 / composition v1/v2), behaviour is
   * unchanged: pose every frame, backface dot-product decides visibility.
   */
  sync(grid: InfiniteGlassGrid, camera: PerspectiveCamera, culling?: LabelCullingVerdict[]) {
    this.lastCulling = culling;
    this.lastTransformWrites = 0;
    // Bounded by the LABELS, not by the pool. On the source-exact path there
    // are fewer labels than slots by design (see `mountCountFor`), and the
    // verdict array is still per-slot, so index n means the same thing in
    // both -- the labels are slots 0..mounted-1, which are exactly the active
    // ones.
    for (let n = 0; n < this.objects.length; n += 1) {
      const slot = grid.slots[n];
      const object = this.objects[n];
      if (slot.active === false) {
        setVisibility(object.element, false);
        continue;
      }
      if (culling) {
        const verdict = culling[n];
        const draw = verdict ? verdict.coverageVisible : true;
        if (draw) this.syncPose(slot, object, camera, true);
        setVisibility(object.element, draw);
        continue;
      }
      if (slot.code !== undefined) {
        this.syncPose(slot, object, camera, false);
        continue;
      }
      const key = slot.i * 10007 + slot.j;
      if (this.boundKey[n] !== key) {
        this.boundKey[n] = key;
        bindCard(object.element, slot.i, slot.j, slot.slotIndex, this.mode);
      }
      this.syncPose(slot, object, camera, false);
    }
  }

  private syncPose(
    slot: InfiniteGlassGrid["slots"][number], object: CSS3DObject, camera: PerspectiveCamera,
    skipBackfaceVisibility: boolean,
  ) {
    this.lastTransformWrites += 1;
    slot.group.getWorldPosition(object.position);
    object.quaternion.copy(slot.group.getWorldQuaternion(_quat));
    slot.group.getWorldDirection(_dir);
    const push = this.frame ? TYPE_Z_SOURCE_EXACT : TYPE_Z;
    if (push !== 0) object.position.addScaledVector(_dir, push);
    if (skipBackfaceVisibility) return;
    _toCam.subVectors(camera.position, object.position);
    object.element.style.visibility = _toCam.dot(_dir) > 0 ? "visible" : "hidden";
  }

  setSize(width: number, height: number) {
    this.renderer.setSize(width, height);
    this.renderer.domElement.style.pointerEvents = "none";
  }

  render(camera: PerspectiveCamera) {
    this.renderer.render(this.scene, camera);
  }

  private clear() {
    for (const object of this.objects) {
      this.scene.remove(object);
      object.element.remove();
    }
    this.objects.length = 0;
    this.boundKey.length = 0;
    this.grid = undefined;
  }

  /**
   * QA only. Hides the whole CSS3D typography layer so a capture can show the
   * media and the gutter alone. Never called by the running preview.
   */
  setVisible(visible: boolean): void {
    this.renderer.domElement.style.display = visible ? "block" : "none";
  }

  /** Read back, from the DOM, rather than from a flag the setter also wrote. */
  isVisible(): boolean {
    return this.renderer.domElement.style.display !== "none";
  }

  /**
   * CSS3D transform writes issued on the LAST sync.
   *
   * The engine-side count: how many labels this layer posed. It is not the
   * number of `style.transform` assignments the browser saw -- CSS3DRenderer
   * keeps its own cache and skips a write whose matrix string has not changed
   * -- so this is an upper bound on the DOM writes and a lower bound on
   * nothing. §九 asks for it on the device readout; it is counted here rather
   * than by patching the renderer, because patching the renderer to measure it
   * would change the thing being measured.
   */
  lastTransformWrites = 0;

  /** How many label elements are currently drawable. */
  visibleCount(): number {
    let n = 0;
    for (const o of this.objects) if (o.element.style.visibility !== "hidden") n += 1;
    return n;
  }

  dispose() {
    this.clear();
    this.renderer.domElement.remove();
  }
}
