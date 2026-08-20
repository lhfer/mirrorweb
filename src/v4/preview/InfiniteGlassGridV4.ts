import {
  Group,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  type BufferGeometry,
  type Texture,
} from "three/webgpu";
import { CanvasTexture, SRGBColorSpace, LinearFilter } from "three/webgpu";
import { GRID, TILE, type QualityLevel } from "../../config";
import {
  placeSourceExactSlot, slotCode, REFERENCE_PLANE_WIDTH,
  type SourceExactLayoutFrame, type SlotPose,
} from "../../layout/SourceExactLayout";
import { Quaternion, Vector3 } from "three/webgpu";
import { catalogAt } from "../../content/catalog";
import { clipFocus } from "../../content/VideoClips";
import { createTestPattern } from "../../content/TestPatterns";
import {
  applyMediaFit,
  computeMediaFit,
  readMediaFitMode,
  type MediaFitMode,
  type MediaFitResult,
} from "../../content/MediaFit";
import { effectiveCellH, placeTile, V1_COMPOSITION, type Composition, type TilePose } from "../../scene/GridCurvature";
import { createConvexGlassGeometryV4 } from "../../scene/ConvexGlassGeometryV4";
import {
  createLiquidGlassMaterialV4,
  createLiquidGlassParamsV4,
  type LiquidGlassMaterialV4Handle,
} from "../../materials/LiquidGlassMaterialV4";
import type { V4DebugMode, V4ShellMode } from "../OpticsConfigV4";
import { FOUNDATION_SLAB_COLOR } from "../../debug/FoundationMode";
import { ClipReelV4 } from "./ClipReelV4";

export type SlotV4 = {
  group: Group;
  /** In foundation-layout mode this is the flat grey slab, not glass. */
  glass: Mesh;
  shell?: Mesh;
  media?: Mesh;
  i: number;
  j: number;
  slotIndex: number;
  /** Source-exact only: the ILG code bound to this POOL SLOT, = slotIndex + 1. */
  code?: number;
  /** Source-exact only: false while the slot is outside the active cols x rows. */
  active?: boolean;
};

const pose: TilePose = { x: 0, y: 0, z: 0, rotX: 0, rotY: 0 };

/**
 * Source-exact pool capacity.
 *
 * The Target's counts move with the viewport and are clamped to 16, so 16 x 16
 * is the most it can ever ask for. Allocating all of them once and switching
 * slots on and off is what makes a resize free of mesh, material, texture and
 * video churn -- the alternative, rebuilding the pool per viewport, reloads
 * video and pops resources in exactly the way the runtime gate forbids.
 */
const SOURCE_EXACT_POOL = 16 * 16;
const _sePose: SlotPose = { x: 0, y: 0, z: 0, nx: 0, ny: 0, nz: 1, xArc: 0, yArc: 0, poolRow: 0, poolCol: 0 };
const _seFrom = new Vector3(0, 0, 1);
const _seTo = new Vector3();
const _seQuat = new Quaternion();

/**
 * The real brick grid, rendered with V4 optics.
 *
 * Layout, curvature, pool size and catalog mapping are the untouched V3 rules
 * (GRID/TILE config, placeTile, catalogAt). Only the optical stack changes:
 * V4 geometry with its optical-zone attributes, one shared refraction body and
 * one shared reflection shell. V4 samples the scene-color target only, so a
 * single material can serve every card instead of one material per clip.
 */
export class InfiniteGlassGridV4 {
  readonly root = new Group();
  readonly slots: SlotV4[] = [];
  created = 0;
  destroyed = 0;
  remaps = 0;
  reel?: ClipReelV4;
  private glassGeometry: BufferGeometry = createConvexGlassGeometryV4("high");
  private mediaGeometry = new PlaneGeometry(TILE.width, TILE.height);
  private handle?: LiquidGlassMaterialV4Handle;
  private mediaMaterials: MeshBasicMaterial[] = [];
  private quality: QualityLevel = "high";
  private foundation = false;
  private slabGeometry?: PlaneGeometry;
  private slabMaterial?: MeshBasicMaterial;
  private mediaFitMode: MediaFitMode = "cover";
  composition: Composition = V1_COMPOSITION;
  /** Set only on the source-exact path. Everything reads it, nobody recomputes it. */
  frame?: SourceExactLayoutFrame;
  activeSlotCount = 0;
  private sourceExact = false;
  private mediaFits: MediaFitResult[] = [];
  private calibrationTextures: CanvasTexture[] = [];

  constructor(private readonly params = createLiquidGlassParamsV4()) {
    this.root.name = "MirrorWeb.V4.GridRoot";
  }

  async prepare(onProgress: (value: number) => void): Promise<void> {
    this.reel = new ClipReelV4();
    await this.reel.load(onProgress);
  }

  build(
    quality: QualityLevel,
    sceneColor: Texture,
    debugMode: V4DebugMode = "beauty",
    shellMode: V4ShellMode = "energy-controlled",
    foundation = false,
    frame?: SourceExactLayoutFrame,
  ): void {
    this.disposePool();
    this.quality = quality;
    this.foundation = foundation;
    this.sourceExact = Boolean(frame);
    this.frame = frame;
    this.activeSlotCount = frame ? frame.activeSlotCount : 0;
    if (foundation) {
      this.buildFoundationPool();
      return;
    }
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(quality);
    this.handle = createLiquidGlassMaterialV4(sceneColor, this.params, debugMode, shellMode);
    this.mediaFitMode = readMediaFitMode();
    const calibration = new URLSearchParams(location.search).get("mediacal") === "1";
    const maps = calibration ? this.buildCalibrationTextures() : (this.reel?.textures ?? []);
    this.mediaMaterials = maps.map((map, index) => {
      const material = new MeshBasicMaterial({ map, toneMapped: true });
      material.name = `MirrorWeb.V4.Media.${index}`;
      return material;
    });
    this.applyMediaFits();

    if (this.sourceExact) {
      this.buildSourceExactPool();
      return;
    }
    const halfCols = Math.floor(GRID.cols / 2);
    const halfRows = Math.floor(GRID.rows / 2);
    let slotIndex = 0;
    for (let dj = -halfRows; dj <= halfRows; dj += 1) {
      for (let di = -halfCols; di <= halfCols; di += 1) {
        const group = new Group();
        const glass = new Mesh(this.glassGeometry, this.handle.bodyMaterial);
        glass.name = "MirrorWeb.V4.RefractionBody";
        glass.renderOrder = 10;
        const shell = new Mesh(this.glassGeometry, this.handle.reflectionMaterial);
        shell.name = "MirrorWeb.V4.ReflectionShell";
        shell.renderOrder = 11;
        const media = new Mesh(this.mediaGeometry, this.mediaFor(di, dj));
        media.name = "MirrorWeb.V4.Media";
        media.position.z = -TILE.thickness * 0.5 - TILE.backDish - 2;
        media.renderOrder = -1;
        group.add(glass, shell, media);
        this.root.add(group);
        this.slots.push({ group, glass, shell, media, i: di, j: dj, slotIndex });
        this.created += 1;
        slotIndex += 1;
      }
    }
  }

  /**
   * Source-exact beauty pool.
   *
   * Card ASPECT is a constant 4/3 in the Target, so only card SIZE varies with
   * the viewport -- which means the glass volume can be built once at a
   * reference size and scaled UNIFORMLY. A uniform scale leaves surface normals
   * pointing where they did, so the frozen refraction is untouched; a
   * non-uniform one would not. It is also what the Target does: its own
   * `cardScale` multiplies thickness and rim width the same way.
   *
   * Geometry is rebuilt here at 4:3 rather than at TILE's 1.3508, because the
   * contract says the card is 4/3. Every optical parameter is left alone.
   */
  private buildSourceExactPool(): void {
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(this.quality, {
      width: REFERENCE_PLANE_WIDTH,
      height: REFERENCE_PLANE_WIDTH / (4 / 3),
    });
    this.mediaGeometry.dispose();
    this.mediaGeometry = new PlaneGeometry(1, 1);
    for (let n = 0; n < SOURCE_EXACT_POOL; n += 1) {
      const group = new Group();
      const glass = new Mesh(this.glassGeometry, this.handle!.bodyMaterial);
      glass.name = "MirrorWeb.V4.RefractionBody";
      glass.renderOrder = 10;
      const shell = new Mesh(this.glassGeometry, this.handle!.reflectionMaterial);
      shell.name = "MirrorWeb.V4.ReflectionShell";
      shell.renderOrder = 11;
      // Clip binding is by POOL SLOT and is set once, here. Resize never
      // rebinds it, so a resize cannot reload a video -- and unlike the Target,
      // which shuffles its clip list with Math.random() on load, this is
      // deterministic and therefore reproducible for QA.
      const media = new Mesh(this.mediaGeometry, this.mediaForSlot(n));
      media.name = "MirrorWeb.V4.Media";
      media.renderOrder = -1;
      group.add(glass, shell, media);
      group.visible = false;
      this.root.add(group);
      this.slots.push({ group, glass, shell, media, i: 0, j: 0, slotIndex: n,
                        code: slotCode(n), active: false });
      this.created += 1;
    }
  }

  /**
   * Layout-only pool: one flat grey slab per cell whose silhouette is exactly
   * TILE.width x TILE.height. No glass, no shell, no media, no per-card colour.
   */
  private buildFoundationPool(): void {
    // A UNIT plane on the source-exact path: the card's size is a per-viewport
    // fact from the layout frame, applied as a mesh scale, not a constant baked
    // into geometry. Legacy keeps its fixed TILE-sized slab.
    this.slabGeometry = this.sourceExact
      ? new PlaneGeometry(1, 1)
      : new PlaneGeometry(TILE.width, TILE.height);
    this.slabMaterial = new MeshBasicMaterial({ color: FOUNDATION_SLAB_COLOR, toneMapped: false });
    this.slabMaterial.name = "MirrorWeb.V5.FoundationSlab";
    if (this.sourceExact) {
      for (let n = 0; n < SOURCE_EXACT_POOL; n += 1) {
        const group = new Group();
        const slab = new Mesh(this.slabGeometry, this.slabMaterial);
        slab.name = "MirrorWeb.V5.FoundationSlab";
        group.add(slab);
        group.visible = false;
        this.root.add(group);
        this.slots.push({ group, glass: slab, i: 0, j: 0, slotIndex: n, code: slotCode(n), active: false });
        this.created += 1;
      }
      return;
    }
    const halfCols = Math.floor(GRID.cols / 2);
    const halfRows = Math.floor(GRID.rows / 2);
    let slotIndex = 0;
    for (let dj = -halfRows; dj <= halfRows; dj += 1) {
      for (let di = -halfCols; di <= halfCols; di += 1) {
        const group = new Group();
        const slab = new Mesh(this.slabGeometry, this.slabMaterial);
        slab.name = "MirrorWeb.V5.FoundationSlab";
        group.add(slab);
        this.root.add(group);
        this.slots.push({ group, glass: slab, i: di, j: dj, slotIndex });
        this.created += 1;
        slotIndex += 1;
      }
    }
  }

  get isFoundation(): boolean {
    return this.foundation;
  }

  /**
   * Calibration stand-ins for the three clips, at the clips' own 960x540 pixel
   * size, so `?mediacal=1` exercises exactly the same fit maths the videos do.
   */
  private buildCalibrationTextures(): CanvasTexture[] {
    this.calibrationTextures = [0, 1, 2].map(() => {
      const texture = createTestPattern("calibration", 960, 540);
      texture.colorSpace = SRGBColorSpace;
      texture.minFilter = LinearFilter;
      texture.magFilter = LinearFilter;
      texture.generateMipmaps = false;
      return texture;
    });
    return this.calibrationTextures;
  }

  /**
   * Fit every clip onto the card. Card aspect is the same for every cell, and
   * each clip owns its own texture, so one texture matrix per clip is enough.
   * Source size comes from the decoded video (or the calibration canvas), never
   * from a hard-coded assumption.
   */
  private applyMediaFits(): void {
    this.mediaFits = [];
    const videos = this.reel?.videos ?? [];
    for (let index = 0; index < this.mediaMaterials.length; index += 1) {
      const map = this.mediaMaterials[index].map;
      if (!map) continue;
      const video = videos[index];
      const image = map.image as { width?: number; height?: number } | undefined;
      const sourceWidth = video?.videoWidth || image?.width || 0;
      const sourceHeight = video?.videoHeight || image?.height || 0;
      if (!sourceWidth || !sourceHeight) continue;
      // Card size is a per-viewport fact on the source-exact path, so the cover
      // matrix is recomputed from the layout frame rather than from the fixed
      // TILE. The accepted F1 focus values are passed through unchanged.
      const cardW = this.frame ? this.frame.planeWidth : TILE.width;
      const cardH = this.frame ? this.frame.planeHeight : TILE.height;
      const fit = computeMediaFit(
        sourceWidth,
        sourceHeight,
        cardW,
        cardH,
        this.mediaFitMode,
        clipFocus(index),
      );
      applyMediaFit(map, fit);
      this.mediaFits.push(fit);
    }
  }

  /** Debug only. `stretch` is the pre-V5 behaviour and must never ship. */
  setMediaFitMode(mode: MediaFitMode): void {
    this.mediaFitMode = mode;
    this.applyMediaFits();
  }

  getMediaFits(): MediaFitResult[] {
    return this.mediaFits;
  }

  get materialHandle(): LiquidGlassMaterialV4Handle | undefined {
    return this.handle;
  }

  setSceneColorTexture(texture: Texture): void {
    this.handle?.setSceneColorTexture(texture);
  }

  setSceneUvScale(scale: number): void {
    this.handle?.setSceneUvScale(scale);
  }

  setDebugMode(mode: V4DebugMode): void {
    if (this.foundation) return;
    this.handle?.setDebugMode(mode);
    const beauty = mode === "beauty" || mode === "reflection";
    for (const slot of this.slots) {
      if (slot.shell) slot.shell.visible = beauty && this.shellEnabled;
    }
  }

  setShellMode(mode: V4ShellMode): void {
    if (this.foundation) return;
    this.handle?.setShellMode(mode);
    this.shellEnabled = mode !== "off";
    for (const slot of this.slots) {
      if (slot.shell) slot.shell.visible = this.shellEnabled;
    }
  }

  private shellEnabled = true;

  setGlassVisible(visible: boolean): void {
    if (this.foundation) return;
    for (const slot of this.slots) {
      slot.glass.visible = visible;
      if (slot.shell) slot.shell.visible = visible && this.shellEnabled;
    }
  }

  setMediaVisible(visible: boolean): void {
    if (this.foundation) return;
    for (const slot of this.slots) {
      if (slot.media) slot.media.visible = visible;
    }
  }

  /**
   * Re-point the pool at a new layout frame.
   *
   * Only `activeSlotCount` and the per-slot scales change. No mesh is created or
   * destroyed, no material is rebuilt, no texture or video is touched, and slot
   * identity -- and therefore the ILG code bound to it -- is stable across every
   * resize. Slots beyond the active count are hidden, not removed.
   */
  setFrame(frame: SourceExactLayoutFrame): void {
    this.frame = frame;
    this.activeSlotCount = Math.min(frame.activeSlotCount, this.slots.length);
    for (let n = 0; n < this.slots.length; n += 1) {
      const slot = this.slots[n];
      const active = n < this.activeSlotCount;
      slot.active = active;
      slot.group.visible = active;
      if (!active) continue;
      if (this.foundation) {
        slot.glass.scale.set(frame.planeWidth, frame.planeHeight, 1);
      } else {
        slot.glass.scale.setScalar(frame.cardScale);
        slot.shell?.scale.setScalar(frame.cardScale);
        if (slot.media) {
          slot.media.scale.set(frame.planeWidth, frame.planeHeight, 1);
          // The media plane sits behind the glass volume, and that clearance is
          // in card units, so it has to scale with the card or media pokes
          // through the back of a small one.
          slot.media.position.z = (-TILE.thickness * 0.5 - TILE.backDish - 2) * frame.cardScale;
        }
      }
    }
    if (!this.foundation) this.applyMediaFits();
  }

  /**
   * Source-exact placement: one sphere, and the orientation is the exact
   * rotation taking the card's local +Z onto the surface normal -- a quaternion,
   * not a pair of independent Euler angles that only approximate it.
   */
  updateSourceExact(scrollX: number, scrollY: number): void {
    const frame = this.frame;
    if (!frame) return;
    for (let n = 0; n < this.activeSlotCount; n += 1) {
      const slot = this.slots[n];
      placeSourceExactSlot(n, scrollX, scrollY, frame, _sePose);
      slot.group.position.set(_sePose.x, _sePose.y, _sePose.z);
      _seTo.set(_sePose.nx, _sePose.ny, _sePose.nz);
      _seQuat.setFromUnitVectors(_seFrom, _seTo);
      slot.group.quaternion.copy(_seQuat);
      slot.i = _sePose.poolCol;
      slot.j = _sePose.poolRow;
    }
  }

  update(scrollX: number, scrollY: number): void {
    if (this.sourceExact) {
      this.updateSourceExact(scrollX, scrollY);
      return;
    }
    const originI = Math.round(scrollX / GRID.cellW);
    const originJ = Math.round(scrollY / effectiveCellH(this.composition));
    const halfCols = Math.floor(GRID.cols / 2);
    const halfRows = Math.floor(GRID.rows / 2);
    let n = 0;
    for (let dj = -halfRows; dj <= halfRows; dj += 1) {
      for (let di = -halfCols; di <= halfCols; di += 1) {
        const i = originI + di;
        const j = originJ + dj;
        const slot = this.slots[n];
        n += 1;
        if (slot.i !== i || slot.j !== j) {
          slot.i = i;
          slot.j = j;
          this.remaps += 1;
          if (slot.media) slot.media.material = this.mediaFor(i, j);
        }
        placeTile(i, j, scrollX, scrollY, pose, this.composition);
        slot.group.position.set(pose.x, pose.y, pose.z);
        slot.group.rotation.set(pose.rotX, pose.rotY, 0);
      }
    }
  }

  setQuality(quality: QualityLevel): void {
    if (this.foundation || quality === this.quality) return;
    this.quality = quality;
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(quality);
    for (const slot of this.slots) {
      slot.glass.geometry = this.glassGeometry;
      if (slot.shell) slot.shell.geometry = this.glassGeometry;
    }
  }

  getPoolState() {
    if (this.foundation) {
      return {
        slots: this.slots.length,
        activeSlots: this.sourceExact ? this.activeSlotCount : this.slots.length,
        created: this.created,
        destroyed: this.destroyed,
        remaps: this.remaps,
        cols: this.frame ? this.frame.cols : GRID.cols,
        rows: this.frame ? this.frame.rows : GRID.rows,
        materials: 1,
        geometries: 1,
        textures: 0,
        videos: 0,
        glass: "foundation-slab",
      };
    }
    return {
      slots: this.slots.length,
      activeSlots: this.sourceExact ? this.activeSlotCount : this.slots.length,
      created: this.created,
      destroyed: this.destroyed,
      remaps: this.remaps,
      cols: this.frame ? this.frame.cols : GRID.cols,
      rows: this.frame ? this.frame.rows : GRID.rows,
      // One refraction body plus one reflection shell serve the whole pool.
      materials: 2 + this.mediaMaterials.length,
      geometries: 2,
      textures: this.reel?.textures.length ?? 0,
      videos: this.reel?.videos.length ?? 0,
      glass: "v4-volume",
    };
  }

  getAssetState() {
    if (this.foundation) {
      return {
        videos: 0,
        textures: 0,
        ready: true,
        media: "foundation-slab",
        glass: "foundation-slab",
        videoFrames: 0,
        videoFrameCallback: false,
        placeholderTileCount: 0,
        unreadyVisibleTileCount: 0,
      };
    }
    const ready = Boolean(this.reel?.ready);
    return {
      videos: this.reel?.videos.length ?? 0,
      textures: this.reel?.textures.length ?? 0,
      ready,
      media: ready ? "video" : "loading",
      glass: "v4-volume",
      videoFrames: this.reel?.videoFrames ?? 0,
      videoFrameCallback: this.reel?.usesFrameCallback ?? false,
      placeholderTileCount: 0,
      unreadyVisibleTileCount: ready ? 0 : this.slots.length,
    };
  }

  /** Deterministic clip binding by pool slot. Never re-evaluated after build. */
  private mediaForSlot(slotIndex: number): MeshBasicMaterial {
    return this.mediaMaterials[slotIndex % Math.max(1, this.mediaMaterials.length)];
  }

  private mediaFor(i: number, j: number): MeshBasicMaterial {
    const item = catalogAt(i, j);
    return this.mediaMaterials[(item.clipIndex ?? 0) % Math.max(1, this.mediaMaterials.length)];
  }

  private disposePool(): void {
    for (const slot of this.slots) this.root.remove(slot.group);
    this.slots.length = 0;
    this.handle?.dispose();
    this.handle = undefined;
    for (const material of this.mediaMaterials) material.dispose();
    this.mediaMaterials.length = 0;
    for (const texture of this.calibrationTextures) texture.dispose();
    this.calibrationTextures.length = 0;
    this.mediaFits = [];
    this.slabGeometry?.dispose();
    this.slabGeometry = undefined;
    this.slabMaterial?.dispose();
    this.slabMaterial = undefined;
  }

  dispose(): void {
    this.disposePool();
    this.glassGeometry.dispose();
    this.mediaGeometry.dispose();
    this.reel?.dispose();
    this.reel = undefined;
  }
}
