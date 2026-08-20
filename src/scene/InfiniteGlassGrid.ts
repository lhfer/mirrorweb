import { Color, Group, Mesh, MeshBasicMaterial, PlaneGeometry, type Material, type Texture } from "three/webgpu";
import { TILE, GRID, type QualityLevel } from "../config";
import { catalogAt } from "../content/catalog";
import { clipFocus, loadClipTextures, type ClipReel } from "../content/VideoClips";
import { applyMediaFit, computeMediaFit, readMediaFitMode } from "../content/MediaFit";
import { isGlassDebug, isLayoutDebug, type DebugMode, type GlassDebugMode } from "../debug/DebugMode";
import { createGlassMaterial, createGlassParams, type GlassMaterialHandle } from "../materials/LiquidGlassMaterial";
import { createConvexGlassGeometry } from "./ConvexGlassGeometry";
import { placeTile, V1_COMPOSITION, type Composition, type TilePose } from "./GridCurvature";

export type Slot = {
  group: Group;
  glass: Mesh;
  media?: Mesh;
  i: number;
  j: number;
  slotIndex: number;
};

const pose: TilePose = { x: 0, y: 0, z: 0, rotX: 0, rotY: 0 };

const COVERAGE = [
  0xff2d55, 0xffcc00, 0x00e676, 0x00b0ff, 0xd500f9, 0xff6d00, 0x64ffda, 0xffff00, 0xff4081,
];

function coverageColor(slotIndex: number, i: number, j: number, mode: DebugMode): Color {
  if (mode === "coverage") {
    return new Color(COVERAGE[((i + 20) * 3 + (j + 20)) % COVERAGE.length]);
  }
  if (mode === "pool") {
    return new Color().setHSL((slotIndex * 0.13) % 1, 0.75, 0.52);
  }
  return new Color(0xb8b8b8);
}

export class InfiniteGlassGrid {
  readonly root = new Group();
  readonly slots: Slot[] = [];
  created = 0;
  destroyed = 0;
  remaps = 0;
  reel?: ClipReel;
  private glassGeometry = createConvexGlassGeometry("high");
  private mediaGeometry = new PlaneGeometry(TILE.width, TILE.height);
  private sharedMaterial?: Material;
  private glassHandle?: GlassMaterialHandle;
  private glassHandles: GlassMaterialHandle[] = [];
  private mediaMaterials: MeshBasicMaterial[] = [];
  private debugMode: DebugMode = "off";
  private params = createGlassParams();
  composition: Composition = V1_COMPOSITION;

  async prepare(onProgress: (value: number) => void) {
    this.reel = await loadClipTextures(onProgress);
  }

  build(quality: QualityLevel, _backend: string, debugMode: DebugMode = "off", sceneMap?: Texture) {
    this.debugMode = debugMode;
    this.disposePool();
    this.glassGeometry.dispose();
    this.mediaGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometry(quality);
    this.mediaGeometry = new PlaneGeometry(TILE.width, TILE.height);

    const layout = isLayoutDebug(debugMode);
    const glassDebug: GlassDebugMode | "off" = isGlassDebug(debugMode) ? debugMode : "off";
    if (!layout && sceneMap && this.reel) {
      this.glassHandles = this.reel.textures.map((map) =>
        createGlassMaterial(sceneMap, this.params, glassDebug, map),
      );
      this.glassHandle = this.glassHandles[0];
      // Aspect-correct crop for the media planes. V3's glass body samples the
      // clip texture directly through a TSL texture node, which does not read
      // the texture matrix, so the media INSIDE V3 glass stays uncropped. V3 is
      // not the page under review and its optics are out of scope this session;
      // recorded in docs/v5/FOUNDATION_FIT.md as a known gap.
      const mode = readMediaFitMode();
      this.mediaMaterials = this.reel.textures.map((map, index) => {
        const video = this.reel!.videos[index];
        const fit = computeMediaFit(
          video?.videoWidth ?? 0,
          video?.videoHeight ?? 0,
          TILE.width,
          TILE.height,
          mode,
          clipFocus(index),
        );
        if (video?.videoWidth) applyMediaFit(map, fit);
        return new MeshBasicMaterial({ map, toneMapped: true });
      });
    } else if (!layout && sceneMap) {
      this.glassHandle = createGlassMaterial(sceneMap, this.params, glassDebug);
    }

    const halfCols = Math.floor(GRID.cols / 2);
    const halfRows = Math.floor(GRID.rows / 2);
    let slotIndex = 0;
    for (let dj = -halfRows; dj <= halfRows; dj += 1) {
      for (let di = -halfCols; di <= halfCols; di += 1) {
        const group = new Group();
        const glass = new Mesh(
          this.glassGeometry,
          layout
            ? new MeshBasicMaterial({
                color: coverageColor(slotIndex, di, dj, debugMode),
                wireframe: debugMode === "geometry",
                toneMapped: false,
              })
            : this.glassFor(di, dj),
        );
        group.add(glass);
        let media: Mesh | undefined;
        if (!layout && this.mediaMaterials.length) {
          media = new Mesh(this.mediaGeometry, this.mediaFor(di, dj));
          media.position.z = -TILE.thickness * 0.5 - TILE.backDish - 2;
          media.renderOrder = -1;
          group.add(media);
        }
        this.root.add(group);
        this.slots.push({ group, glass, media, i: di, j: dj, slotIndex });
        this.created += 1;
        slotIndex += 1;
      }
    }
  }

  setSceneMap(map: Texture) {
    this.glassHandle?.setMap(map);
    for (const handle of this.glassHandles) handle.setMap(map);
  }

  setGlassVisible(visible: boolean) {
    if (isLayoutDebug(this.debugMode)) return;
    for (const slot of this.slots) slot.glass.visible = visible;
  }

  setMediaVisible(visible: boolean) {
    if (isLayoutDebug(this.debugMode)) return;
    for (const slot of this.slots) {
      if (slot.media) slot.media.visible = visible;
    }
  }

  get needsBackgroundPass() {
    return !isLayoutDebug(this.debugMode) && Boolean(this.glassHandle);
  }

  update(scrollX: number, scrollY: number) {
    const originI = Math.round(scrollX / GRID.cellW);
    const originJ = Math.round(scrollY / GRID.cellH);
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
          if (this.debugMode === "coverage") {
            (slot.glass.material as MeshBasicMaterial).color.copy(coverageColor(slot.slotIndex, i, j, "coverage"));
          } else {
            slot.glass.material = this.glassFor(i, j);
            if (slot.media) slot.media.material = this.mediaFor(i, j);
          }
        }
        placeTile(i, j, scrollX, scrollY, pose, this.composition);
        slot.group.position.set(pose.x, pose.y, pose.z);
        slot.group.rotation.set(pose.rotX, pose.rotY, 0);
      }
    }
  }

  getPoolState() {
    const layout = isLayoutDebug(this.debugMode);
    return {
      slots: this.slots.length,
      created: this.created,
      destroyed: this.destroyed,
      remaps: this.remaps,
      cols: GRID.cols,
      rows: GRID.rows,
      materials: layout ? this.slots.length : this.glassHandles.length + this.mediaMaterials.length || 1,
      geometries: layout ? 1 : 2,
      textures: this.reel?.textures.length ?? 0,
      videos: this.reel?.videos.length ?? 0,
      glass: layout ? "debug-slab" : "volume",
    };
  }

  getAssetState() {
    if (isLayoutDebug(this.debugMode)) {
      return {
        videos: 0,
        textures: 0,
        ready: true,
        media: "debug-slab",
        glass: "debug-slab",
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
      glass: "volume",
      placeholderTileCount: 0,
      unreadyVisibleTileCount: ready ? 0 : this.slots.length,
    };
  }

  syncVideos() {
    this.reel?.update();
  }

  setQuality(quality: QualityLevel) {
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometry(quality);
    for (const slot of this.slots) slot.glass.geometry = this.glassGeometry;
  }

  private mediaFor(i: number, j: number) {
    const item = catalogAt(i, j);
    return this.mediaMaterials[item.clipIndex ?? 0];
  }

  private glassFor(i: number, j: number) {
    const item = catalogAt(i, j);
    const handle = this.glassHandles[item.clipIndex ?? 0] ?? this.glassHandle;
    return handle!.material;
  }

  private disposePool() {
    for (const slot of this.slots) {
      this.root.remove(slot.group);
      if (isLayoutDebug(this.debugMode)) {
        (slot.glass.material as Material).dispose();
      }
      this.destroyed += 1;
    }
    this.slots.length = 0;
    if (this.glassHandles.length) {
      for (const handle of this.glassHandles) handle.material.dispose();
    } else {
      this.glassHandle?.material.dispose();
    }
    this.glassHandles.length = 0;
    this.glassHandle = undefined;
    for (const material of this.mediaMaterials) material.dispose();
    this.mediaMaterials.length = 0;
    this.sharedMaterial?.dispose();
    this.sharedMaterial = undefined;
  }

  dispose() {
    this.disposePool();
    this.glassGeometry.dispose();
    this.mediaGeometry.dispose();
    this.reel?.dispose();
    this.reel = undefined;
  }
}
