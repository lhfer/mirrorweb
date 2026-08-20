import { CSS3DObject, CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { Quaternion, Scene, Vector3, type PerspectiveCamera } from "three/webgpu";
import { TILE } from "../config";
import { catalogAt } from "../content/catalog";
import { isLayoutDebug, type DebugMode } from "../debug/DebugMode";
import type { SourceExactLayoutFrame } from "../layout/SourceExactLayout";
import type { InfiniteGlassGrid } from "../scene/InfiniteGlassGrid";

const _dir = new Vector3();
const _toCam = new Vector3();
const _quat = new Quaternion();

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
  el.innerHTML = `
    <div class="tile-card-top">
      <span>${mode.toUpperCase()}</span>
      <span>SLOT ${slotIndex}</span>
    </div>
    <div class="tile-card-bottom">
      <h2>${i},${j}</h2>
    </div>
  `;
}

function bindCatalogCard(el: HTMLElement, i: number, j: number, mode: DebugMode) {
  const item = catalogAt(i, j);
  el.className = mode === "typography" ? "tile-card is-type-debug" : "tile-card";
  el.style.setProperty("--accent", item.accent);
  el.innerHTML = `
    <div class="tile-card-top">
      <span>${item.code} ${item.category}</span>
      <span>SELECTED WORK — 2026</span>
    </div>
    <div class="tile-card-bottom">
      <h2>${item.title}</h2>
      <div class="tile-rule"></div>
      <p class="tile-deck">${item.deck}</p>
    </div>
  `;
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
  el.innerHTML = `
    <div class="se-clip">
      <div class="se-content">
        <div class="se-meta">
          <div class="se-meta-left">
            <span>${label}</span><span class="se-dim">${item.category}</span>
          </div>
          <div class="se-meta-right">
            <span>SELECTED WORK</span><span class="se-dot"></span><span>2026</span>
          </div>
        </div>
        <div class="se-bottom">
          <div class="se-rule"></div>
          <h2 class="se-title">${item.title}</h2>
          <div class="se-deck-row"><p class="se-deck">${item.deck}</p></div>
        </div>
      </div>
    </div>
  `;
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

  constructor(host: HTMLElement) {
    this.renderer.domElement.style.position = "absolute";
    this.renderer.domElement.style.inset = "0";
    this.renderer.domElement.style.pointerEvents = "none";
    this.renderer.domElement.style.zIndex = "5";
    host.appendChild(this.renderer.domElement);
  }

  attach(grid: InfiniteGlassGrid, mode: DebugMode, frame?: SourceExactLayoutFrame) {
    this.clear();
    this.mode = mode;
    this.frame = frame;
    this.renderer.domElement.style.display = "block";
    for (const slot of grid.slots) {
      const el = document.createElement("div");
      el.style.containerType = "inline-size";
      if (slot.code !== undefined) bindSlotCard(el, slot.code, slot.slotIndex, mode);
      else bindCard(el, slot.i, slot.j, slot.slotIndex, mode);
      const object = new CSS3DObject(el);
      this.scene.add(object);
      this.objects.push(object);
      // Slot-bound cards never rebind: their identity does not change.
      this.boundKey.push(slot.code !== undefined ? Number.NaN : slot.i * 10007 + slot.j);
    }
    this.applyBox();
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
    this.applyBox();
  }

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
        return {
          slotIndex: n,
          visible: o.element.style.visibility !== "hidden",
          cssWidth: parseFloat(cs.width),
          cssHeight: parseFloat(cs.height),
          objectScale: [o.scale.x, o.scale.y, o.scale.z],
          /** Screen-space AABB of the projected element. */
          rectPx: [r.x, r.y, r.width, r.height],
          world: [o.position.x, o.position.y, o.position.z],
        };
      }),
    };
  }

  sync(grid: InfiniteGlassGrid, camera: PerspectiveCamera) {
    for (let n = 0; n < grid.slots.length; n += 1) {
      const slot = grid.slots[n];
      const object = this.objects[n];
      if (slot.active === false) {
        object.element.style.visibility = "hidden";
        continue;
      }
      if (slot.code !== undefined) {
        this.syncPose(slot, object, camera);
        continue;
      }
      const key = slot.i * 10007 + slot.j;
      if (this.boundKey[n] !== key) {
        this.boundKey[n] = key;
        bindCard(object.element, slot.i, slot.j, slot.slotIndex, this.mode);
      }
      this.syncPose(slot, object, camera);
    }
  }

  private syncPose(slot: InfiniteGlassGrid["slots"][number], object: CSS3DObject, camera: PerspectiveCamera) {
    slot.group.getWorldPosition(object.position);
    object.quaternion.copy(slot.group.getWorldQuaternion(_quat));
    slot.group.getWorldDirection(_dir);
    const push = this.frame ? TYPE_Z_SOURCE_EXACT : TYPE_Z;
    if (push !== 0) object.position.addScaledVector(_dir, push);
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
