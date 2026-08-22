import {
  Group,
  Mesh,
  MeshBasicMaterial,
  PlaneGeometry,
  type BufferGeometry,
  type Texture,
} from "three/webgpu";
import {
  CanvasTexture, ClampToEdgeWrapping, LinearFilter, SRGBColorSpace, VideoTexture,
} from "three/webgpu";
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
  type LiquidGlassMaterialV4Options,
  createLiquidGlassMaterialV4,
  createLiquidGlassParamsV4,
  type LiquidGlassMaterialV4Handle,
} from "../../materials/LiquidGlassMaterialV4";
import {
  isTargetSourceBody,
  type V4DebugMode, type V4EnvironmentMode, type V4OpticalBody, type V4ShellMode,
} from "../OpticsConfigV4";
import {
  TARGET_BODY_SOURCE,
  applyTargetOpticalBodyFrameV5,
  createTargetOpticalBodyMaterialV5,
  createTargetOpticalBodyUniformsV5,
  type TargetOpticalBodyHandleV5,
  type TargetOpticalBodyUniformsV5,
  type V5BodyView,
} from "../../materials/TargetOpticalBodyV5";
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
  /** O5 lane. "current" is the accepted O2 body; see OpticsConfigV4. */
  private opticalBody: V4OpticalBody = "current";
  private bodyUniforms?: TargetOpticalBodyUniformsV5;
  private bodyHandles: TargetOpticalBodyHandleV5[] = [];
  private bodyGeometry?: PlaneGeometry;
  /**
   * The candidate lane's OWN media textures. It never mutates the reel
   * textures the control lane shares: doing so would change control pixels
   * and forfeit the exact-identity proof the whole round rests on.
   */
  private ownMediaTextures: VideoTexture[] = [];
  private bodyView: V5BodyView = "beauty";
  /** O5R §十: the environment as a structural choice, not a multiply. */
  private environmentMode: V4EnvironmentMode = "source";
  /** Kept so a quality step can rebuild the candidate materials. */
  private bodyEnvTexture: Texture | null = null;

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
    materialOptions?: LiquidGlassMaterialV4Options,
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
    this.opticalBody = materialOptions?.opticalBody ?? "current";
    this.bodyView = materialOptions?.bodyView ?? "beauty";
    this.environmentMode = materialOptions?.environmentMode ?? "source";
    const targetSource = isTargetSourceBody(this.opticalBody) && this.sourceExact;
    this.glassGeometry.dispose();
    this.glassGeometry = createConvexGlassGeometryV4(quality);
    // The candidate lane builds NO control material: its body carries
    // refraction, environment and rim itself, and it never samples the
    // scene-colour target. Creating the control material anyway would leave a
    // second body program and a scene-colour binding alive for the §十
    // pipeline measurement to count, which would misreport what this lane
    // actually costs.
    this.handle = targetSource
      ? undefined
      : createLiquidGlassMaterialV4(
          sceneColor, this.params, debugMode, shellMode, materialOptions ?? {});
    // The build-time shell mode must seed the SAME flags the setter keeps,
    // or the mesh-visibility truth disagrees with the material state.
    this.shellEnabled = shellMode !== "off";
    this.debugShellOn = debugMode === "beauty" || debugMode === "reflection";
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
      if (isTargetSourceBody(this.opticalBody)) {
        this.buildTargetSourcePool(materialOptions?.envTexture ?? null);
      } else {
        this.buildSourceExactPool();
      }
      return;
    }
    const halfCols = Math.floor(GRID.cols / 2);
    const halfRows = Math.floor(GRID.rows / 2);
    let slotIndex = 0;
    for (let dj = -halfRows; dj <= halfRows; dj += 1) {
      for (let di = -halfCols; di <= halfCols; di += 1) {
        const group = new Group();
        const glass = new Mesh(this.glassGeometry, this.handle!.bodyMaterial);
        glass.name = "MirrorWeb.V4.RefractionBody";
        glass.renderOrder = 10;
        const shell = new Mesh(this.glassGeometry, this.handle!.reflectionMaterial);
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
   * O5 candidate pool: the Target's own topology.
   *
   * ONE mesh per card, drawn with the material belonging to that slot's clip.
   * No reflection shell -- the Target has none, and keeping ours would
   * double-count the environment. The media plane is still created, but it is
   * drawn ONLY when the glass layer is switched off, because it exists purely
   * so a media-only QA capture has something to show; in Beauty the body
   * samples its own media directly.
   *
   * The geometry is PlaneGeometry(1,1,16,12) scaled to
   * (planeWidth, planeHeight, 1) -- the Target's `t.scale.set(d,h,1)`. The
   * 16x12 tessellation is load-bearing: the dome is a vertex displacement, so
   * the curvature is resolved by subdivision.
   */
  private buildTargetSourcePool(envTexture: Texture | null): void {
    this.bodyEnvTexture = envTexture;
    this.bodyGeometry?.dispose();
    this.bodyGeometry = new PlaneGeometry(1, 1, 16, 12);
    this.mediaGeometry.dispose();
    this.mediaGeometry = new PlaneGeometry(1, 1);
    this.bodyUniforms = createTargetOpticalBodyUniformsV5();

    // The candidate's OWN textures, over the same video elements. sRGB and
    // ClampToEdge as the Target sets them; no mipmaps, so there is no chain to
    // sample even if a LOD were asked for.
    const videos = this.reel?.videos ?? [];
    this.ownMediaTextures = videos.map((video, index) => {
      const texture = new VideoTexture(video);
      texture.colorSpace = SRGBColorSpace;
      texture.wrapS = ClampToEdgeWrapping;
      texture.wrapT = ClampToEdgeWrapping;
      texture.minFilter = LinearFilter;
      texture.magFilter = LinearFilter;
      texture.generateMipmaps = false;
      texture.name = `MirrorWeb.V5.OwnMedia.${index}`;
      return texture;
    });

    // One material per CLIP, as the Target does. Cover values come from the
    // FROZEN MediaFit result, never from the Target's centred formula: media
    // focus and crop are frozen, and clip 2 carries a product decision the
    // Target's formula does not express.
    this.rebuildBodyMaterials();

    for (let n = 0; n < SOURCE_EXACT_POOL; n += 1) {
      const group = new Group();
      const body = this.bodyHandles[n % this.bodyHandles.length];
      const glass = new Mesh(this.bodyGeometry, body.material);
      glass.name = "MirrorWeb.V5.TargetOpticalBody";
      glass.renderOrder = 10;
      // Clip binding is by POOL SLOT and set once, exactly as the control
      // lane binds it, so both lanes show the same clip in the same slot.
      const media = new Mesh(this.mediaGeometry, this.mediaForSlot(n));
      media.name = "MirrorWeb.V4.Media";
      media.renderOrder = -1;
      media.visible = false;
      group.add(glass, media);
      group.visible = false;
      this.root.add(group);
      this.slots.push({ group, glass, media, i: 0, j: 0, slotIndex: n,
                        code: slotCode(n), active: false });
      this.created += 1;
    }
  }

  /**
   * (Re)build the per-clip candidate materials.
   *
   * The spectral sample count is a BUILD-TIME literal -- the Target bakes its
   * weights on the CPU and so do we -- so a quality step has to rebuild these
   * materials or the lane would keep five samples on a device that asked for
   * three. The control lane has the same property and the same limitation; the
   * difference is that here it is optically load-bearing, so it is handled.
   */
  private rebuildBodyMaterials(): void {
    if (!this.bodyUniforms) return;
    const previous = this.bodyHandles;
    const count = Math.max(1, this.ownMediaTextures.length);
    const next: TargetOpticalBodyHandleV5[] = [];
    for (let index = 0; index < count; index += 1) {
      const fit = this.mediaFits[index];
      next.push(createTargetOpticalBodyMaterialV5({
        uniforms: this.bodyUniforms,
        media: this.ownMediaTextures[index],
        environment: (this.bodyEnvTexture
          ?? this.ownMediaTextures[index]) as Texture,
        coverScale: fit ? [fit.repeatX, fit.repeatY] : [1, 1],
        coverOffset: fit ? [fit.offsetX, fit.offsetY] : [0, 0],
        quality: this.quality,
        view: this.bodyView,
        // O5R §十. The clamp survives ONLY in the lane O5 sealed, so the
        // original gate stays re-runnable against the pixels it was scored on.
        clampEnvSample: this.opticalBody === "target-source",
        environmentMode: this.environmentMode,
      }));
    }
    this.bodyHandles = next;
    for (const slot of this.slots) {
      slot.glass.material = next[slot.slotIndex % next.length].material;
    }
    // Dispose AFTER rebinding, never before: a mesh holding a disposed
    // material draws nothing for a frame, which is exactly the resource
    // pop-in §十 forbids.
    for (const handle of previous) handle.material.dispose();
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
      // Same fit, expressed as the Target's uniforms. repeat/offset IS
      // coverScale/coverOffset -- three's texture matrix and the Target's
      // `clamp(uv,0,1)*coverScale + coverOffset` are the same convention, so
      // this is a rename rather than a recomputation.
      const body = this.bodyHandles[index];
      if (body) {
        body.coverScale.value.set(fit.repeatX, fit.repeatY);
        body.coverOffset.value.set(fit.offsetX, fit.offsetY);
      }
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
    this.debugShellOn = mode === "beauty" || mode === "reflection";
    this.applyEffectiveVisibility();
  }

  setShellMode(mode: V4ShellMode): void {
    if (this.foundation) return;
    this.handle?.setShellMode(mode);
    this.shellEnabled = mode !== "off";
    this.applyEffectiveVisibility();
  }

  private shellEnabled = true;
  private debugShellOn = true;
  private passGlass = true;
  private passMedia = true;
  private coverageDraws: boolean[] | null = null;

  /**
   * V1 render culling: no system writes `.visible` on a slot mesh directly.
   * Every writer sets its own flag -- the scene-colour pipeline's per-pass
   * layer flips, the QA layer requests, the shell mode, the debug mode, the
   * active window and the coverage verdict -- and ONE applier composes them.
   * That is the layered-state model the render-culling round requires: the
   * Target collapses the same AND to a single `s.visible = o.draw` because
   * its card is one mesh and it has no layer system.
   *
   * The media plane is deliberately NOT coverage-culled. It is the input of
   * the scene-colour target -- our architecture's equivalent of the Target's
   * per-card texture binds, which the Target does not cull either (its
   * refraction samples the card's OWN media texture, so hiding a card can
   * never change another card's pixels). Coverage-culling the scene-colour
   * input would break exactly that invariant: an edge card's glass samples
   * the target beyond the 64 px coverage margin, so removing a culled
   * neighbour's media from the target would move pixels INSIDE the strict
   * viewport. Media draw calls outside the overscan frustum are already
   * skipped by the renderer's own frustum culling.
   */
  private applyEffectiveVisibility(): void {
    if (this.foundation) return;
    const draws = this.coverageDraws;
    for (const slot of this.slots) {
      const activeOk = slot.active !== false;
      const cov = draws === null ? true : (draws[slot.slotIndex] ?? true);
      slot.glass.visible = activeOk && cov && this.passGlass;
      if (slot.shell) {
        slot.shell.visible =
          slot.glass.visible && this.shellEnabled && this.debugShellOn;
      }
      if (slot.media) {
        // In the candidate lane the body draws its own media, so the plane is
        // a QA surface only: it appears exactly when the glass layer is
        // switched off, which is what a media-only capture asks for. In the
        // control lane it is the media BEHIND the glass and shows normally.
        slot.media.visible = isTargetSourceBody(this.opticalBody)
          ? activeOk && this.passMedia && !this.passGlass
          : activeOk && this.passMedia;
      }
    }
  }

  setGlassVisible(visible: boolean): void {
    if (this.foundation) return;
    this.passGlass = visible;
    this.applyEffectiveVisibility();
  }

  setMediaVisible(visible: boolean): void {
    if (this.foundation) return;
    this.passMedia = visible;
    this.applyEffectiveVisibility();
  }

  /**
   * The per-slot coverage verdict, the SAME array the label layer consumed
   * this frame -- one verdict, two surfaces, exactly the Target's one-loop
   * wiring. `null` turns coverage culling off entirely (legacy route,
   * foundation, or the QA A/B toggle) and restores the pre-V1 behaviour.
   */
  /** O2 QA-only floor levers (o2-selected-system.json); product value 1. */
  setEnvMixScale(value: number): void {
    const v = Math.max(0, Math.min(1, value));
    this.params.envMixScale.value = v;
    // The candidate carries the environment in its own body, so the QA scale
    // has to reach its uniform too or a "System B off" capture would silently
    // still have System B on in that lane.
    if (this.bodyUniforms) (this.bodyUniforms.envMixScale as { value: number }).value = v;
  }

  setRimScale(value: number): void {
    const v = Math.max(0, Math.min(1, value));
    this.params.rimScale.value = v;
    if (this.bodyUniforms) (this.bodyUniforms.rimScale as { value: number }).value = v;
  }

  getOpticsState(): Record<string, unknown> {
    return {
      dispersionLaw: this.handle?.getDispersionLaw() ?? null,
      reflectionSupport: this.handle?.getReflectionSupport() ?? null,
      bodyDiag: this.handle?.getBodyDiag() ?? null,
      bodyFloorMode: this.handle?.getBodyFloorMode() ?? null,
      opticalBody: this.opticalBody,
      opticalBodyView: isTargetSourceBody(this.opticalBody) ? this.bodyView : null,
      opticalBodySamples: this.bodyHandles[0]?.samples ?? null,
      opticalBodyMaterials: this.bodyHandles.length,
      opticalBodyOwnTextures: this.ownMediaTextures.length,
      // O5R: read off the built program, not off the requested option, so a
      // lane that failed to rebuild reports what it is rather than what it
      // was asked to be.
      environmentMode: this.bodyHandles[0]?.environment.mode
        ?? (isTargetSourceBody(this.opticalBody) ? this.environmentMode : null),
      envSampleClamped: this.bodyHandles[0]?.environment.clamped ?? null,
      envMixScale: this.params.envMixScale.value,
      rimScale: this.params.rimScale.value,
      shellMode: this.handle?.getShellMode() ?? null,
      systemB: {
        fresnelF0: this.params.fresnelF0.value,
        envIntensity: this.params.envIntensity.value,
        envMaxMix: this.params.envMaxMix.value,
        envRotationY: this.params.envRotationY.value,
        envRotationX: this.params.envRotationX.value,
        rimIntensity: this.params.rimIntensity.value,
      },
    };
  }

  /**
   * O5R QA-only: everything a CPU replay of the Target's refraction and
   * silhouette needs, read off the live scene.
   *
   * §六 and §八 both require the Target side to be replayed from the source
   * formula through the LIVE layout frame and card matrix rather than through
   * a re-derivation of them -- a re-derivation would be a second model, and a
   * disagreement between it and the engine would be indistinguishable from an
   * optical difference. Nothing here is a render input; it is only read.
   */
  getCardBodyGeometry(): Record<string, unknown> {
    const frame = this.frame;
    const slots = this.sourceExact
      ? this.slots.slice(0, this.activeSlotCount)
      : this.slots;
    const S = TARGET_BODY_SOURCE;
    return {
      sourceExact: this.sourceExact,
      opticalBody: this.opticalBody,
      frame: frame
        ? {
            planeWidth: frame.planeWidth,
            planeHeight: frame.planeHeight,
            cardScale: frame.cardScale,
            sphereRadius: frame.sphereRadius,
          }
        : null,
      // The derived per-frame values, taken from the same expressions
      // applyTargetOpticalBodyFrameV5 writes into the uniforms, so a replay
      // cannot drift from the shader by re-deriving them differently.
      derived: frame
        ? {
            cornerRadius: S.cornerRadiusRatio * frame.planeWidth,
            bevelWidth: S.bevelWidthRatio * frame.planeWidth,
            thickness: S.thicknessPerCardScale * frame.cardScale,
            rimWidth: S.rimWidthPerCardScale * frame.cardScale,
          }
        : null,
      source: { ...S },
      samples: this.bodyHandles[0]?.samples ?? null,
      cards: slots.map((slot) => {
        const fit = this.mediaFits[slot.slotIndex % Math.max(1, this.mediaFits.length)];
        return {
          slotIndex: slot.slotIndex,
          clipIndex: this.bodyHandles.length
            ? slot.slotIndex % this.bodyHandles.length
            : null,
          active: slot.active !== false,
          matrixWorld: slot.glass.matrixWorld.toArray(),
          scale: [slot.glass.scale.x, slot.glass.scale.y, slot.glass.scale.z],
          coverScale: fit ? [fit.repeatX, fit.repeatY] : [1, 1],
          coverOffset: fit ? [fit.offsetX, fit.offsetY] : [0, 0],
        };
      }),
    };
  }

  setCoverageDraws(draws: boolean[] | null): void {
    if (this.foundation) return;
    this.coverageDraws = draws;
    this.applyEffectiveVisibility();
  }

  /** QA only. The composed visibility state, read off the scene. */
  getRenderCullingState(): Record<string, unknown> {
    const active = this.slots.filter((s) => s.active !== false);
    return {
      coverageCulling: this.coverageDraws !== null,
      passGlass: this.passGlass,
      passMedia: this.passMedia,
      shellEnabled: this.shellEnabled,
      debugShellOn: this.debugShellOn,
      activeSlots: active.length,
      coverageDrawn: this.coverageDraws
        ? this.coverageDraws.filter(Boolean).length : null,
      glassVisible: active.filter((s) => s.glass.visible).length,
      shellVisible: active.filter((s) => s.shell?.visible).length,
      mediaVisible: active.filter((s) => s.media?.visible).length,
    };
  }

  /**
   * Re-point the pool at a new layout frame.
   *
   * Only `activeSlotCount` and the per-slot scales change. No mesh is created or
   * destroyed, no material is rebuilt, no texture or video is touched, and slot
   * identity -- and therefore the ILG code bound to it -- is stable across every
   * resize. Slots beyond the active count are hidden, not removed.
   */
  /** QA only: the first active glass mesh, for the O3 shader-proof gate. */
  firstGlassMesh(): Mesh | undefined {
    const slot = this.slots.find((s) => s.active) ?? this.slots[0];
    return slot?.glass as Mesh | undefined;
  }

  setFrame(frame: SourceExactLayoutFrame): void {
    this.frame = frame;
    // O3: the Target's per-frame bevel uniform writes. Harmless in the
    // geometry lane, where the shader references none of them.
    this.handle?.setLayoutFrame(frame);
    // The candidate's geometry uniforms come from the FROZEN frame. L6 is
    // never re-derived here: our frame already reproduces it exactly at every
    // O5 viewport, so reading it cannot drift from the layout the rest of the
    // app uses.
    if (this.bodyUniforms) applyTargetOpticalBodyFrameV5(this.bodyUniforms, frame);
    this.activeSlotCount = Math.min(frame.activeSlotCount, this.slots.length);
    for (let n = 0; n < this.slots.length; n += 1) {
      const slot = this.slots[n];
      const active = n < this.activeSlotCount;
      slot.active = active;
      slot.group.visible = active;
      if (!active) continue;
      if (this.foundation || isTargetSourceBody(this.opticalBody)) {
        // Unit plane scaled to the card -- the Target's own
        // `t.scale.set(d,h,1)`. Z stays 1 so the vertex dome, which is already
        // in card pixels, is not scaled twice.
        slot.glass.scale.set(frame.planeWidth, frame.planeHeight, 1);
        if (slot.media) {
          slot.media.scale.set(frame.planeWidth, frame.planeHeight, 1);
          // The candidate's media plane is a QA SURFACE ONLY -- it is hidden
          // in Beauty, where the body samples its own texture. So it must sit
          // exactly where the control's does, or a media-only capture would
          // project the media at a slightly different size in each lane and
          // the two would not be comparable. They feed the true-silhouette
          // derivation and the edge-compression baseline check, both of which
          // compare lanes, so this parity is load-bearing for QA even though
          // it is invisible in the product path.
          slot.media.position.z =
            (-TILE.thickness * 0.5 - TILE.backDish - 2) * frame.cardScale;
        }
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
    if (!this.foundation) {
      this.applyMediaFits();
      this.applyEffectiveVisibility();
    }
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
    // The source-exact card is 4:3 and is sized by a uniform scale off the
    // reference plane. Rebuilding the volume at a new quality without the
    // override would silently hand it TILE's 1.3508 aspect and TILE's width,
    // changing both the shape and the size of every card the moment adaptive
    // quality stepped -- which, until the fix in AdaptiveQuality, never happened
    // and so was never seen.
    this.glassGeometry = this.sourceExact
      ? createConvexGlassGeometryV4(quality, {
          width: REFERENCE_PLANE_WIDTH,
          height: REFERENCE_PLANE_WIDTH / (4 / 3),
        })
      : createConvexGlassGeometryV4(quality);
    for (const slot of this.slots) {
      slot.glass.geometry = this.glassGeometry;
      if (slot.shell) slot.shell.geometry = this.glassGeometry;
    }
    if (isTargetSourceBody(this.opticalBody)) this.rebuildBodyMaterials();
    // Re-apply the layout frame: the scales live on the meshes, and a quality
    // step must not be able to leave them describing the previous geometry.
    if (this.sourceExact && this.frame) this.setFrame(this.frame);
  }

  /**
   * QA only. What the glass MESH actually is, read off the mesh.
   *
   * A quality step rebuilds this geometry, so reading the layout frame back
   * afterwards proves nothing about the rebuild: the frame is the input, not
   * the result. This reports the geometry's own bounding box, the scale each
   * mesh actually carries, and therefore the card's real world footprint.
   */
  getGlassGeometryTruth() {
    const g = this.glassGeometry;
    if (!g.boundingBox) g.computeBoundingBox();
    const bb = g.boundingBox!;
    const sizeX = bb.max.x - bb.min.x;
    const sizeY = bb.max.y - bb.min.y;
    const sizeZ = bb.max.z - bb.min.z;
    const slot = this.slots.find((s) => s.active !== false) ?? this.slots[0];
    const scale = slot
      ? [slot.glass.scale.x, slot.glass.scale.y, slot.glass.scale.z]
      : [1, 1, 1];
    return {
      quality: this.quality,
      geometryUuid: g.uuid,
      vertexCount: g.getAttribute("position")?.count ?? 0,
      indexCount: g.getIndex()?.count ?? 0,
      boundingBoxLocal: {
        min: [bb.min.x, bb.min.y, bb.min.z],
        max: [bb.max.x, bb.max.y, bb.max.z],
        size: [sizeX, sizeY, sizeZ],
      },
      /** Local aspect of the built outline, before any mesh scale. */
      geometryAspect: sizeY ? sizeX / sizeY : 0,
      meshScale: scale,
      /** The card's real footprint in world units: geometry x scale. */
      worldCardWidth: sizeX * scale[0],
      worldCardHeight: sizeY * scale[1],
      worldCardAspect: sizeY * scale[1] ? (sizeX * scale[0]) / (sizeY * scale[1]) : 0,
      allSlotsShareGeometry: this.slots.every((s) => s.glass.geometry === g),
      allSlotsShareScale: this.slots
        .filter((s) => s.active !== false)
        .every((s) => s.glass.scale.x === scale[0] && s.glass.scale.y === scale[1]),
    };
  }

  getPoolState() {
    if (this.foundation) {
      return {
        slots: this.slots.length,
        quality: this.quality,
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
      quality: this.quality,
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
    for (const handle of this.bodyHandles) handle.material.dispose();
    this.bodyHandles.length = 0;
    for (const texture of this.ownMediaTextures) texture.dispose();
    this.ownMediaTextures.length = 0;
    this.bodyUniforms = undefined;
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
    this.bodyGeometry?.dispose();
    this.bodyGeometry = undefined;
    this.reel?.dispose();
    this.reel = undefined;
  }
}
