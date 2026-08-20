import { CSS3DObject, CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { Quaternion, Scene, Vector3, type PerspectiveCamera } from "three/webgpu";
import { TILE } from "../config";
import { catalogAt } from "../content/catalog";
import { isLayoutDebug, type DebugMode } from "../debug/DebugMode";
import type { InfiniteGlassGrid } from "../scene/InfiniteGlassGrid";

const _dir = new Vector3();
const _toCam = new Vector3();
const _quat = new Quaternion();
const TYPE_Z = TILE.thickness * 0.5 + TILE.frontBulge + 6;

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
 * Slot identity on the source-exact path.
 *
 * The Target binds a card's label to its POOL SLOT, not to a world cell: its
 * ILG code is `slotIndex + 1` and a card keeps that code as it wraps. Ours bound
 * to (i, j). Only the DATA binding changes here; no style, no layout and no
 * typography parameter is touched this stage.
 */
function bindSlotCard(el: HTMLElement, code: number, slotIndex: number, mode: DebugMode) {
  if (isLayoutDebug(mode)) {
    bindDebugCard(el, slotIndex % 16, Math.floor(slotIndex / 16), slotIndex, mode);
    return;
  }
  const item = catalogAt(slotIndex, 0);
  el.className = mode === "typography" ? "tile-card is-type-debug" : "tile-card";
  el.style.setProperty("--accent", item.accent);
  const label = `ILG\u2014${String(code).padStart(2, "0")}`;
  el.innerHTML = `
    <div class="tile-card-top">
      <span>${label} ${item.category}</span>
      <span>SELECTED WORK — 2026</span>
    </div>
    <div class="tile-card-bottom">
      <h2>${item.title}</h2>
      <div class="tile-rule"></div>
      <p class="tile-deck">${item.deck}</p>
    </div>
  `;
}

export class TileLabelLayer {
  readonly renderer = new CSS3DRenderer();
  readonly scene = new Scene();
  private objects: CSS3DObject[] = [];
  private boundKey: number[] = [];
  private mode: DebugMode = "off";

  constructor(host: HTMLElement) {
    this.renderer.domElement.style.position = "absolute";
    this.renderer.domElement.style.inset = "0";
    this.renderer.domElement.style.pointerEvents = "none";
    this.renderer.domElement.style.zIndex = "5";
    host.appendChild(this.renderer.domElement);
  }

  attach(grid: InfiniteGlassGrid, mode: DebugMode) {
    this.clear();
    this.mode = mode;
    this.renderer.domElement.style.display = "block";
    for (const slot of grid.slots) {
      const el = document.createElement("div");
      el.style.width = `${TILE.width}px`;
      el.style.height = `${TILE.height}px`;
      el.style.containerType = "inline-size";
      if (slot.code !== undefined) bindSlotCard(el, slot.code, slot.slotIndex, mode);
      else bindCard(el, slot.i, slot.j, slot.slotIndex, mode);
      const object = new CSS3DObject(el);
      this.scene.add(object);
      this.objects.push(object);
      // Slot-bound cards never rebind: their identity does not change.
      this.boundKey.push(slot.code !== undefined ? Number.NaN : slot.i * 10007 + slot.j);
    }
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
    object.position.addScaledVector(_dir, TYPE_Z);
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
