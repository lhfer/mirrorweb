import {
  Group,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  type BufferGeometry,
  type Texture,
} from "three/webgpu";
import { GRID, TILE, type QualityLevel } from "../../config";
import { catalogAt } from "../../content/catalog";
import { placeTile, type TilePose } from "../../scene/GridCurvature";
import { createConvexGlassGeometryV4 } from "../../scene/ConvexGlassGeometryV4";
import {
  createLiquidGlassMaterialV4,
  createLiquidGlassParamsV4,
  type LiquidGlassMaterialV4Handle,
} from "../../materials/LiquidGlassMaterialV4";
import type { V4DebugMode, V4ShellMode } from "../OpticsConfigV4";
import { ClipReelV4 } from "./ClipReelV4";

export type SlotV4 = {
  group: Group;
  glass: Mesh;
  shell: Mesh;
  media: Mesh;
  i: number;
  j: number;
  slotIndex: number;
};

const pose: TilePose = { x: 0, y: 0, z: 0, rotX: 0, rotY: 0 };

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
  ): void {
    this.disposePool();
    this.quality = quality;
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(quality);
    this.handle = createLiquidGlassMaterialV4(sceneColor, this.params, debugMode, shellMode);
    this.mediaMaterials = (this.reel?.textures ?? []).map(
      (map, index) => {
        const material = new MeshBasicMaterial({ map, toneMapped: true });
        material.name = `MirrorWeb.V4.Media.${index}`;
        return material;
      },
    );

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
    this.handle?.setDebugMode(mode);
    const beauty = mode === "beauty" || mode === "reflection";
    for (const slot of this.slots) slot.shell.visible = beauty && this.shellEnabled;
  }

  setShellMode(mode: V4ShellMode): void {
    this.handle?.setShellMode(mode);
    this.shellEnabled = mode !== "off";
    for (const slot of this.slots) slot.shell.visible = this.shellEnabled;
  }

  private shellEnabled = true;

  setGlassVisible(visible: boolean): void {
    for (const slot of this.slots) {
      slot.glass.visible = visible;
      slot.shell.visible = visible && this.shellEnabled;
    }
  }

  setMediaVisible(visible: boolean): void {
    for (const slot of this.slots) slot.media.visible = visible;
  }

  update(scrollX: number, scrollY: number): void {
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
          slot.media.material = this.mediaFor(i, j);
        }
        placeTile(i, j, scrollX, scrollY, pose);
        slot.group.position.set(pose.x, pose.y, pose.z);
        slot.group.rotation.set(pose.rotX, pose.rotY, 0);
      }
    }
  }

  setQuality(quality: QualityLevel): void {
    if (quality === this.quality) return;
    this.quality = quality;
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(quality);
    for (const slot of this.slots) {
      slot.glass.geometry = this.glassGeometry;
      slot.shell.geometry = this.glassGeometry;
    }
  }

  getPoolState() {
    return {
      slots: this.slots.length,
      created: this.created,
      destroyed: this.destroyed,
      remaps: this.remaps,
      cols: GRID.cols,
      rows: GRID.rows,
      // One refraction body plus one reflection shell serve the whole pool.
      materials: 2 + this.mediaMaterials.length,
      geometries: 2,
      textures: this.reel?.textures.length ?? 0,
      videos: this.reel?.videos.length ?? 0,
      glass: "v4-volume",
    };
  }

  getAssetState() {
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
  }

  dispose(): void {
    this.disposePool();
    this.glassGeometry.dispose();
    this.mediaGeometry.dispose();
    this.reel?.dispose();
    this.reel = undefined;
  }
}
