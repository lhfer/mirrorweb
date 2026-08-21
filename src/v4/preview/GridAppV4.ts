import { AmbientLight, PerspectiveCamera, Vector3, type DirectionalLight } from "three/webgpu";
import {
  CAMERA, GRID, TILE, compositionParams, compositionScale, compositionVersion, isPortrait,
  isSourceExact,
  landscapeRowOrigin, phaseModel, portraitLaw,
  portraitVerticalModel, restOffset, verticalMode, verticalOverride,
  type CompositionVersion, type LandscapeRowOrigin, type PhaseModel, type PortraitLaw,
  type PortraitVerticalModel,
  type QualityLevel, type VerticalMode,
} from "../../config";
import { rowOrigin } from "../../scene/RowPhase";
import { sourceExactLayout, slotCode, type SourceExactLayoutFrame } from "../../layout/SourceExactLayout";
import { catalogAt } from "../../content/catalog";
import { readDebugMode, type DebugMode } from "../../debug/DebugMode";
import { isFoundationLayout, readFoundationMode, type FoundationMode } from "../../debug/FoundationMode";
import { FoundationOverlay } from "../../debug/FoundationOverlay";
import { effectiveCellH } from "../../scene/GridCurvature";
import { InputController } from "../../interaction/InputController";
import { MotionController } from "../../interaction/MotionController";
import { MOTION_CONTRACT, sourceExactDolly, sourceExactMaxZoomZ, sourceExactOrbit }
  from "../../interaction/SourceExactMotion";
import { AdaptiveQuality } from "../../quality/AdaptiveQuality";
import { isMobileViewport } from "../../quality/DeviceProfile";
import { RendererController } from "../../rendering/RendererController";
import type { InfiniteGlassGrid } from "../../scene/InfiniteGlassGrid";
import { LoadingOverlay } from "../../ui/LoadingOverlay";
import { PageOverlay } from "../../ui/PageOverlay";
import { TileLabelLayer } from "../../ui/TileLabelLayer";
import { SourceExactLabelCulling } from "../../ui/SourceExactLabelCulling";
import {
  createPointerKeyLightV4,
  updatePointerKeyLightV4,
} from "../../materials/LiquidGlassMaterialV4";
import { V4_DEBUG_MODES, V4_OPTICS_CONFIG, type V4DebugMode, type V4ShellMode } from "../OpticsConfigV4";
import { createStripLightEnvironmentV4 } from "../StripLightEnvironmentV4";
import { InfiniteGlassGridV4 } from "./InfiniteGlassGridV4";
import { SceneColorPipelineV4 } from "./SceneColorPipelineV4";
import { freezeMediaTime, readMediaState, type FreezeReport, type MediaSnapshot } from "../../debug/MediaFreeze";
import { MEDIA_FIT_MODES, type MediaFitMode } from "../../content/MediaFit";

const _ndc = new Vector3();

export type GridAppV4Options = {
  /** Host ids, so the lab page and the real page can share one implementation. */
  viewportId?: string;
  labelsId?: string;
  loadingId?: string;
  pageOverlayId?: string;
  debugMode?: V4DebugMode;
  shellMode?: V4ShellMode;
  overscan?: number;
  /** Dev/QA only. `layout` strips everything that is not geometry. */
  foundation?: FoundationMode;
  /** `v1` is the F2 candidate, kept reachable; `v2` is the F2.5 candidate. */
  composition?: CompositionVersion;
  vertical?: VerticalMode;
  portraitLaw?: PortraitLaw;
  /** F2.7. `rowOrigin` derives the rest phase; `aspect` is the F2.6 rollback. */
  phaseModel?: PhaseModel;
  /** F2.7 portrait-only vertical composition: v0 control, v1, v2. */
  portraitVertical?: PortraitVerticalModel;
  /** Diagnostic only, default off. See config.ts. */
  landscapeRowOrigin?: LandscapeRowOrigin;
};

/**
 * The real page, rendered with V4 optics.
 *
 * Motion, input, curvature, pool size, catalog and CSS3D typography are the
 * untouched V3 systems; this app only swaps the optical stack and the
 * scene-color pipeline. V3 remains the default and is never loaded here.
 */
export class GridAppV4 {
  readonly motion = new MotionController();
  readonly renderer = new RendererController();
  readonly grid = new InfiniteGlassGridV4();
  readonly quality = new AdaptiveQuality("high");
  readonly debugMode: DebugMode = readDebugMode();
  private pipeline!: SceneColorPipelineV4;
  private labels!: TileLabelLayer;
  private loading!: LoadingOverlay;
  private input!: InputController;
  private pointerLight?: DirectionalLight;
  /** The CSS3D transform camera: same orbit AND same velocity dolly as the render camera; drives the CSS3D transform. */
  private css3dTransformCamera?: PerspectiveCamera;
  /**
   * The coverage camera: same lens, same pointer orbit, NO velocity dolly.
   * The Target keeps a dedicated dolly-free camera whose ONLY job is the
   * label coverage projection -- it renders nothing, transforms nothing and
   * gates nothing else. Byte-anchored in
   * `qa-v5/culling/target-culling-source.json` -> coverageCameraPose.
   */
  private sourceExactCoverageCamera?: PerspectiveCamera;
  private readonly labelCulling = new SourceExactLabelCulling();
  /**
   * QA-only labels.sync CPU probe. OFF by default so the product frame loop
   * carries no timing calls; a perf harness turns it on for a measured run.
   */
  private labelSyncProbe = false;
  private labelSyncTimes: number[] = [];
  private environment?: ReturnType<typeof createStripLightEnvironmentV4>;
  private raf = 0;
  private lastT = 0;
  private elapsed = 0;
  private resizeTimer = 0;
  private visible = true;
  private disposed = false;
  private frameTimes: number[] = [];
  private renderedFrames = 0;
  private v4Debug: V4DebugMode;
  private v4Shell: V4ShellMode;
  private startedAt = 0;
  readonly foundation: FoundationMode;
  readonly composition: CompositionVersion;
  readonly verticalMode: VerticalMode;
  readonly portraitLaw: PortraitLaw;
  readonly phaseModel: PhaseModel;
  readonly portraitVertical: PortraitVerticalModel;
  readonly landscapeRowOrigin: LandscapeRowOrigin;
  /** True for ?composition=sourceExact. Nothing fitted runs on that path. */
  get sourceExact(): boolean { return isSourceExact(this.composition); }
  /** The one layout frame for this viewport; the renderer owns it. */
  private get frame(): SourceExactLayoutFrame | undefined { return this.renderer.frame; }
  private foundationOverlay?: FoundationOverlay;

  constructor(private readonly options: GridAppV4Options = {}) {
    this.v4Debug = options.debugMode ?? "beauty";
    this.v4Shell = options.shellMode ?? "energy-controlled";
    this.foundation = options.foundation ?? readFoundationMode();
    this.composition = options.composition ?? compositionVersion();
    this.verticalMode = options.vertical ?? verticalMode();
    this.portraitLaw = options.portraitLaw ?? portraitLaw();
    this.phaseModel = options.phaseModel ?? phaseModel();
    this.portraitVertical = options.portraitVertical ?? portraitVerticalModel();
    this.landscapeRowOrigin = options.landscapeRowOrigin ?? landscapeRowOrigin();
    this.grid.composition = { version: this.composition, verticalMode: this.verticalMode,
                              portraitLaw: this.portraitLaw,
                              vertical: verticalOverride(window.innerWidth, window.innerHeight,
                                                         this.composition, this.portraitVertical,
                                                         this.landscapeRowOrigin) };
  }

  /**
   * Re-resolve the portrait-only vertical override.
   *
   * It depends on the viewport, and placement does not see one, so it has to be
   * refreshed whenever the viewport changes -- including across an orientation
   * flip, where it appears or disappears entirely.
   */
  private syncVerticalOverride(): void {
    this.grid.composition = {
      ...this.grid.composition,
      vertical: verticalOverride(window.innerWidth, window.innerHeight,
                                 this.composition, this.portraitVertical, this.landscapeRowOrigin),
    };
  }

  private get layoutOnly(): boolean {
    return isFoundationLayout(this.foundation);
  }

  /**
   * World offset the grid is placed at: the user's scroll plus the regime's
   * rest offset. Keeping it in one place means recycling, projected quads and
   * QA landmarks all agree about where the grid actually is.
   */
  private gridX(scrollX = this.motion.scrollX): number {
    // Source-exact has NO rest offset. Its phase falls out of an even column
    // count putting a seam on the centre line; adding a rest offset on top
    // would shift the grid a second time.
    //
    // No sign conversion any more either. The composition round inverted
    // scrollX here because the legacy model SUBTRACTS the drag while the
    // Target ADDS it, and motion was frozen at the time. The source-exact
    // model now carries the Target's own sign from the gesture onward, so the
    // conversion would flip the drag direction back to wrong.
    if (this.sourceExact) return scrollX;
    return scrollX + restOffset(window.innerWidth, window.innerHeight, this.composition,
                                this.verticalMode, this.phaseModel).x;
  }

  private gridY(scrollY = this.motion.scrollY): number {
    if (this.sourceExact) return scrollY;
    return scrollY + restOffset(window.innerWidth, window.innerHeight, this.composition,
                                this.verticalMode, this.phaseModel).y;
  }

  async start(): Promise<void> {
    const loadingHost = document.getElementById(this.options.loadingId ?? "loading-overlay");
    const overlayHost = document.getElementById(this.options.pageOverlayId ?? "page-overlay");
    this.loading = new LoadingOverlay(loadingHost!);
    // Foundation mode drops the footer overlay and the CSS3D type layer: both
    // sit on top of the cards and would contaminate a layout measurement.
    if (overlayHost && !this.layoutOnly) new PageOverlay(overlayHost);
    this.labels = new TileLabelLayer(document.getElementById(this.options.labelsId ?? "labels")!);
    this.loading.setPercent(8);

    this.renderer.composition = this.composition;
    this.renderer.verticalMode = this.verticalMode;
    this.renderer.portraitLaw = this.portraitLaw;
    this.renderer.portraitVertical = this.portraitVertical;
    const handle = await this.renderer.init(
      document.getElementById(this.options.viewportId ?? "viewport")!,
      false,
    );
    this.loading.setPercent(22);

    this.environment = createStripLightEnvironmentV4();
    handle.scene.environment = this.environment;
    const ambient = new AmbientLight(0xffffff, 0.18);
    ambient.name = "MirrorWeb.V4.Ambient";
    this.pointerLight = createPointerKeyLightV4();
    handle.scene.add(ambient, this.pointerLight, this.pointerLight.target);

    if (!this.layoutOnly) {
      await this.grid.prepare((value) => this.loading.setPercent(value));
      this.grid.reel?.unlock();
    }

    this.pipeline = new SceneColorPipelineV4(this.quality.level, this.options.overscan);
    this.applyPipelineSize();
    this.grid.build(
      this.quality.level,
      this.pipeline.sceneColor.texture,
      this.v4Debug,
      this.v4Shell,
      this.layoutOnly,
      this.frame,
    );
    if (this.frame) this.grid.setFrame(this.frame);
    this.grid.setSceneUvScale(this.pipeline.sceneUvScale);
    handle.scene.add(this.grid.root);

    if (this.layoutOnly) {
      this.motion.paused = true;
      // `&annotate=0` renders the bare slabs, so a pixel detector reads card
      // edges and gutters without the annotation strokes on top of them.
      if (new URLSearchParams(location.search).get("annotate") !== "0") {
        this.foundationOverlay = new FoundationOverlay(
          document.getElementById(this.options.labelsId ?? "labels")!,
        );
        this.foundationOverlay.setSize(window.innerWidth, window.innerHeight);
      }
    } else {
      // The type layer consumes the SAME layout frame the renderer, the grid
      // and MediaFit consume. That is the whole plumbing fix: every card's
      // label box is the card plane, so every container-query type size is
      // measured against the card it is actually on.
      this.labels.attach(this.gridAsV3(), this.debugMode, this.frame);
      this.labels.setSize(window.innerWidth, window.innerHeight);
    }
    this.grid.update(this.gridX(0), this.gridY(0));
    this.applyPose();
    this.syncLabels();

    // Before the input controller is built: it decides at wire-up time whether
    // to take pointer capture and whether to register a wheel listener, and
    // both answers come from which motion model is running.
    if (this.sourceExact) this.motion.enableSourceExact();
    this.input = new InputController(handle.canvas, this.motion, () => this.grid.reel?.unlock());
    this.bindWindow();
    this.drawFrame();
    this.loading.setPercent(100);
    if (this.grid.getAssetState().ready) this.loading.hide();
    this.startedAt = performance.now();
    this.lastT = this.startedAt;
    this.tick(this.lastT);
  }

  /**
   * CSS3D typography is deliberately the untouched V3 layer. It only reads
   * `slots[n].group / i / j / slotIndex`, which the V4 pool provides with the
   * same meaning.
   */
  private gridAsV3(): InfiniteGlassGrid {
    return this.grid as unknown as InfiniteGlassGrid;
  }

  pause(): void {
    this.motion.paused = true;
    this.grid.reel?.pause();
  }

  resume(): void {
    this.motion.paused = false;
    this.grid.reel?.resume();
    this.lastT = performance.now();
  }

  setTime(seconds: number): void {
    this.elapsed = seconds;
    this.grid.reel?.seek(seconds);
  }

  /**
   * QA only. Pins every clip to the same decoded frame and proves it stayed
   * there. `setTime` cannot do this: the clips are autoplay+loop, so it only
   * nudges a timeline that keeps running.
   */
  async setMediaTimeAndFreeze(seconds: number): Promise<FreezeReport> {
    this.elapsed = seconds;
    const videos = this.grid.reel?.videos ?? [];
    return freezeMediaTime(videos, seconds);
  }

  /** QA only. Read-only proof that the freeze still holds at capture time. */
  getMediaState(): MediaSnapshot[] {
    return readMediaState(this.grid.reel?.videos ?? []);
  }

  /**
   * QA only. Media-only capture: the media planes and the gutter, with the
   * refraction body, the reflection shell and the CSS3D typography hidden.
   * Two builds that render the same media at the same time on the same cell
   * must produce identical pixels here, which is what makes a blind pair fair.
   */
  setRenderLayers(layers: { glass?: boolean; media?: boolean; labels?: boolean }): void {
    if (layers.glass !== undefined) {
      this.glassLayer = layers.glass;
      this.grid.setGlassVisible(layers.glass);
    }
    if (layers.media !== undefined) {
      this.mediaLayer = layers.media;
      this.grid.setMediaVisible(layers.media);
    }
    if (layers.labels !== undefined) this.labels.setVisible(layers.labels);
    this.renderOnce();
  }

  private glassLayer = true;
  private mediaLayer = true;

  /**
   * QA only. What the render layers ARE, read off the scene.
   *
   * A capture that says "glass off" has to be able to show that the glass
   * meshes were actually invisible when the pixels were taken, and which draw
   * path produced them. Reporting the flags the setter just wrote would prove
   * only that the setter ran.
   */
  getRenderLayerState(): Record<string, unknown> {
    const active = this.grid.slots.filter((s) => s.active !== false);
    return {
      requested: { glass: this.glassLayer, media: this.mediaLayer,
                   labels: this.labels ? this.labels.isVisible() : null },
      actual: {
        activeSlots: active.length,
        glassMeshesVisible: active.filter((s) => s.glass.visible).length,
        reflectionShellsVisible: active.filter((s) => s.shell?.visible).length,
        mediaMeshesVisible: active.filter((s) => s.media?.visible).length,
        labelLayerDisplay: this.labels ? (this.labels.isVisible() ? "block" : "none") : null,
        labelElementsShown: this.labels ? this.labels.visibleCount() : null,
      },
      drawPath: this.layoutOnly
        ? "foundation: scene straight to screen"
        : this.glassLayer
          ? "two-pass scene-colour pipeline (glass samples the scene colour target)"
          : "direct scene render: the two-pass pipeline re-asserts glass-on every "
            + "frame, so a glass-free frame cannot come out of it",
      quality: this.grid.getPoolState().quality,
      renderStamp: this.renderStamp,
    };
  }

  setPointer(x: number, y: number): void {
    this.motion.setPointer(x, y);
    this.renderOnce();
  }

  /**
   * QA only. Move the APPLIED pointer, not just its smoothing target, so a
   * paused sweep actually changes the pose. `setPointer` keeps its documented
   * behaviour; this is the fixed-state form.
   */
  jumpPointer(x: number, y: number): void {
    this.motion.jumpPointer(x, y);
    this.renderOnce();
  }

  setOffset(x: number, y: number): void {
    // Through the controller, not into the field: on the source-exact path the
    // scroll is a spring, and writing only the field would leave the spring
    // pulling the page back to where it was on the very next frame.
    this.motion.setScroll(x, y);
    this.renderOnce();
  }

  setVelocity(x: number, y: number): void {
    this.motion.setReleaseVelocity(x, y);
  }

  /**
   * QA only. With the adaptive sampler actually working, an idle headless page
   * climbs straight back to `high` after any manual step, which makes a
   * level-by-level invariance sweep impossible to hold still. Turning the
   * sampler off is a harness capability; it changes no product behaviour and
   * the adaptive path is proven separately, with it on.
   */
  setAdaptiveQuality(enabled: boolean): void {
    this.adaptiveQuality = enabled;
    this.renderOnce();
  }

  private adaptiveQuality = true;
  /** Every level change the adaptive sampler made on its own, for evidence. */
  private adaptiveChanges: Array<{ atSeconds: number; level: QualityLevel }> = [];

  getAdaptiveState(): Record<string, unknown> {
    return {
      enabled: this.adaptiveQuality,
      /** What the sampler believes. */
      level: this.quality.level,
      /** What the grid and the scene-colour pipeline are ACTUALLY running. */
      appliedLevel: this.grid.getPoolState().quality,
      changes: this.adaptiveChanges.slice(-20),
      changeCount: this.adaptiveChanges.length,
    };
  }

  setQuality(level: QualityLevel): void {
    this.quality.level = level;
    this.grid.setQuality(level);
    this.pipeline.setQuality(level);
    this.grid.setSceneUvScale(this.pipeline.sceneUvScale);
    this.renderOnce();
  }

  setDpr(value: number): void {
    this.renderer.setDpr(value);
    this.applyPipelineSize();
    this.labels.setSize(window.innerWidth, window.innerHeight);
    this.renderOnce();
  }

  setDebugMode(mode: V4DebugMode): void {
    if (!V4_DEBUG_MODES.includes(mode)) throw new Error(`Unknown V4 debug mode: ${mode}`);
    this.v4Debug = mode;
    this.grid.setDebugMode(mode);
  }

  getDebugMode(): V4DebugMode {
    return this.v4Debug;
  }

  setShellMode(mode: V4ShellMode): void {
    this.v4Shell = mode;
    this.grid.setShellMode(mode);
  }

  /** QA only. `stretch` reproduces the pre-V5 squeeze for a before/after pair. */
  setMediaFitMode(mode: MediaFitMode): void {
    if (!MEDIA_FIT_MODES.includes(mode)) throw new Error(`Unknown media fit mode: ${mode}`);
    this.grid.setMediaFitMode(mode);
  }

  /**
   * QA only. Everything the motion gate needs, read off the live model.
   *
   * `renderCamera` and `css3dTransformCamera` are reported separately on purpose: the
   * Target dollies BOTH, so `camerasSeparated` must read false at every moment
   * and a regression that un-dollied the label camera could not pass quietly.
   */
  getMotionTruth(): Record<string, unknown> {
    const handle = this.renderer.handle;
    const frame = this.frame;
    const label = frame ? this.css3dTransformCamera : undefined;
    return {
      sourceExact: this.motion.sourceExact,
      contract: this.motion.sourceExact ? MOTION_CONTRACT.motionVersion : "legacy MOTION",
      takesPointerCapture: this.motion.dragSurfaceTakesPointerCapture,
      wheelListenerRegistered: this.input ? this.input.wheelListenerRegistered : null,
      scrollX: this.motion.scrollX,
      scrollY: this.motion.scrollY,
      scrollTargetX: this.motion.scrollTargetX,
      scrollTargetY: this.motion.scrollTargetY,
      velocityX: this.motion.velocityX,
      velocityY: this.motion.velocityY,
      magnitude: this.motion.magnitude,
      dragging: this.motion.dragging,
      gestureStarted: this.motion.gestureStarted,
      pointerX: this.motion.pointerX,
      pointerY: this.motion.pointerY,
      pointerTargetX: this.motion.pointerTargetX,
      pointerTargetY: this.motion.pointerTargetY,
      rotX: this.motion.rotX,
      rotY: this.motion.rotY,
      lightX: this.motion.lightX,
      lightY: this.motion.lightY,
      lightWorld: this.pointerLight
        ? [this.pointerLight.position.x, this.pointerLight.position.y,
           this.pointerLight.position.z]
        : null,
      dollyZ: frame ? sourceExactDolly(this.motion.magnitude, sourceExactMaxZoomZ(frame.perspective)) : 0,
      // Scheduling readbacks. Which frame the model has reached, which frame a
      // release was committed on and with what velocity -- so a replay can be
      // checked against the frame the engine actually did the work on instead
      // of against a frame inferred from a curve.
      motionSteps: this.motion.motionSteps,
      releaseVelocityX: this.motion.releaseVelocityX,
      releaseVelocityY: this.motion.releaseVelocityY,
      lastReleaseStep: this.motion.lastReleaseStep,
      pendingReleaseCount: this.motion.pendingReleaseCount,
      // Which of the magnitude MotionValue's two writers writes last in a
      // frame, exposed so evidence records the order that was actually
      // running rather than the order a document says should be.
      magnitudeWriterOrder: this.motion.magnitudeWriterOrder,
      releaseRecords: this.motion.releaseRecords,
      maxZoomZ: frame ? sourceExactMaxZoomZ(frame.perspective) : null,
      renderCamera: handle
        ? [handle.camera.position.x, handle.camera.position.y, handle.camera.position.z]
        : null,
      css3dTransformCamera: label
        ? [label.position.x, label.position.y, label.position.z] : null,
      // The same three numbers under the name they were published as before
      // this round. `labelCamera` was a misnomer -- the camera drives the CSS3D
      // transform, the projection and the culling, and "label" named only the
      // first thing that happened to use it -- but T1's depth-clipping evidence
      // reads this key, and an evidence script that stops reproducing is a
      // break rather than a rename. Kept as an alias, marked as one.
      labelCamera: label ? [label.position.x, label.position.y, label.position.z] : null,
      labelCameraIsAliasOf: "css3dTransformCamera",
      // Kept as a readback: the Target's CSS3D camera carries the dolly, so
      // this must be false at every moment. It is the thing that would go
      // wrong silently if the label camera were ever un-dollied again.
      camerasSeparated: !!(handle && label)
        && Math.abs(handle.camera.position.z - label.position.z) > 1e-9,
      cameraDistance: handle
        ? Math.hypot(handle.camera.position.x, handle.camera.position.y,
                     handle.camera.position.z)
        : null,
      gridX: this.gridX(),
      gridY: this.gridY(),
      renderStamp: this.renderStamp,
    };
  }

  /** QA only. Label boxes and projected rects, for container alignment. */
  getLabelTruth(): Record<string, unknown> {
    if (!this.labels || this.layoutOnly) return { sourceExact: false, slots: [] };
    return this.labels.getLabelTruth();
  }

  /** QA only. Per-clip crop numbers behind the current fit. */
  getMediaFits() {
    return this.grid.getMediaFits();
  }

  reset(): void {
    this.motion.reset();
    this.elapsed = 0;
    this.renderOnce();
  }

  getState(): Record<string, unknown> {
    if (!this.renderer.handle) return { ready: false, landmarks: [] };
    this.applyPose();
    const { camera } = this.renderer.handle;
    this.grid.root.updateWorldMatrix(true, true);
    const landmarks = this.grid.slots.map((slot) => {
      slot.group.getWorldPosition(_ndc);
      _ndc.project(camera);
      return {
        i: slot.i,
        j: slot.j,
        slotIndex: slot.slotIndex,
        title: `${slot.i},${slot.j}`,
        nx: (_ndc.x + 1) * 0.5,
        ny: (1 - _ndc.y) * 0.5,
      };
    });
    return {
      ready: true,
      optics: "v4",
      backend: this.renderer.handle.backend,
      quality: this.quality.level,
      debug: this.debugMode,
      v4Debug: this.v4Debug,
      v4Shell: this.v4Shell,
      milestone: 4,
      glass: "v4-volume",
      samplesScene: true,
      normalPathDirectMedia: false,
      elapsed: this.elapsed,
      scrollX: this.motion.scrollX,
      scrollY: this.motion.scrollY,
      velocityX: this.motion.velocityX,
      velocityY: this.motion.velocityY,
      dragging: this.motion.dragging,
      pointerX: this.motion.pointerX,
      pointerY: this.motion.pointerY,
      pointerTargetX: this.motion.pointerTargetX,
      pointerTargetY: this.motion.pointerTargetY,
      rotX: this.motion.rotX,
      rotY: this.motion.rotY,
      camX: this.motion.camX,
      camY: this.motion.camY,
      lightX: this.motion.lightX,
      lightY: this.motion.lightY,
      tile: TILE,
      grid: GRID,
      compositionScale: this.renderer.compositionScale,
      landmarks,
    };
  }

  /**
   * Projected card rectangles in normalized screen space.
   *
   * The Round 1 pixel gate needs to know exactly where a card's interior and
   * its rim land on screen; deriving that from landmark centres alone would be
   * guesswork on a curved, tilted grid.
   */
  getCardQuads(): Array<{ i: number; j: number; slotIndex: number; quad: number[][] }> {
    const handle = this.renderer.handle;
    if (!handle) return [];
    this.applyPose();
    this.grid.root.updateWorldMatrix(true, true);
    // Half-extents come from the layout frame on the source-exact path, because
    // the card's size is a per-viewport fact there and the slot group carries
    // position and orientation only.
    const frame = this.frame;
    const halfWidth = (frame ? frame.planeWidth : TILE.width) * 0.5;
    const halfHeight = (frame ? frame.planeHeight : TILE.height) * 0.5;
    // Corners are taken on the card MID-PLANE (local z = 0), not the front
    // face. That is the plane whose outline a pixel detector actually reads off
    // a rendered card, and the plane the V5 layout fitter models, so quads,
    // detector and fitter all speak about the same rectangle. Projecting the
    // front face instead inflated every quad by thickness/2 -> ~2.1%.
    const corners: Array<[number, number]> = [
      [-halfWidth, halfHeight],
      [halfWidth, halfHeight],
      [halfWidth, -halfHeight],
      [-halfWidth, -halfHeight],
    ];
    const slots = this.sourceExact
      ? this.grid.slots.slice(0, this.grid.activeSlotCount)
      : this.grid.slots;
    return slots.map((slot) => ({
      i: slot.i,
      j: slot.j,
      slotIndex: slot.slotIndex,
      quad: corners.map(([x, y]) => {
        _ndc.set(x, y, 0);
        slot.group.localToWorld(_ndc);
        _ndc.project(handle.camera);
        return [(_ndc.x + 1) * 0.5, (1 - _ndc.y) * 0.5];
      }),
    }));
  }

  /**
   * QA only. Card mid-plane screen rects, in PIXELS, through the LABEL camera.
   *
   * Deliberately not `getCardQuads`: that one returns normalised coordinates,
   * and a label rect is measured in pixels. Both cameras carry the same
   * velocity dolly, so neither projection is an "un-dollied" one. The
   * invariant worth gating is label-to-card-plane through the camera the label
   * layer itself uses, so this projects through exactly that one.
   */
  getCardPlaneRects(): Array<{ slotIndex: number; rectPx: number[] }> {
    const handle = this.renderer.handle;
    const frame = this.frame;
    const halfWidth = frame ? frame.planeWidth / 2 : TILE.width / 2;
    const halfHeight = frame ? frame.planeHeight / 2 : TILE.height / 2;
    const camera = this.poseCamera();
    const w = window.innerWidth, h = window.innerHeight;
    const slots = this.sourceExact
      ? this.grid.slots.slice(0, this.grid.activeSlotCount)
      : this.grid.slots;
    if (!handle) return [];
    return slots.map((slot) => {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const [x, y] of [[-halfWidth, halfHeight], [halfWidth, halfHeight],
                            [halfWidth, -halfHeight], [-halfWidth, -halfHeight]]) {
        _ndc.set(x, y, 0);
        slot.group.localToWorld(_ndc);
        _ndc.project(camera);
        const px = (_ndc.x + 1) * 0.5 * w;
        const py = (1 - _ndc.y) * 0.5 * h;
        minX = Math.min(minX, px); maxX = Math.max(maxX, px);
        minY = Math.min(minY, py); maxY = Math.max(maxY, py);
      }
      return { slotIndex: slot.slotIndex, rectPx: [minX, minY, maxX - minX, maxY - minY] };
    });
  }

  /**
   * Per-slot engine truth on the source-exact path.
   *
   * World position and orientation are read back off the live object matrices,
   * not recomputed from the model -- otherwise the source-contract gate would
   * be comparing the model with itself. Projected corners come from the live
   * camera the same way.
   */
  getSourceExactSlots(): Array<Record<string, unknown>> {
    const handle = this.renderer.handle;
    const frame = this.frame;
    if (!handle || !frame) return [];
    this.applyPose();
    this.grid.root.updateWorldMatrix(true, true);
    const halfW = frame.planeWidth * 0.5;
    const halfH = frame.planeHeight * 0.5;
    const corners: Array<[number, number]> = [
      [-halfW, halfH], [halfW, halfH], [halfW, -halfH], [-halfW, -halfH],
    ];
    const out: Array<Record<string, unknown>> = [];
    for (let n = 0; n < this.grid.activeSlotCount; n += 1) {
      const slot = this.grid.slots[n];
      const pos = new Vector3();
      slot.group.getWorldPosition(pos);
      // The card's normal is its local +Z taken to world; that is exactly the
      // quantity the contract's quaternion is defined to produce.
      const normal = new Vector3(0, 0, 1).applyQuaternion(slot.group.quaternion).normalize();
      out.push({
        slotIndex: slot.slotIndex,
        code: slot.code,
        poolCol: slot.i,
        poolRow: slot.j,
        world: [pos.x, pos.y, pos.z],
        normal: [normal.x, normal.y, normal.z],
        quaternion: [slot.group.quaternion.x, slot.group.quaternion.y,
                     slot.group.quaternion.z, slot.group.quaternion.w],
        cornersPx: corners.map(([x, y]) => {
          const v = new Vector3(x, y, 0);
          slot.group.localToWorld(v);
          v.project(handle.camera);
          return [(v.x + 1) * 0.5 * window.innerWidth, (1 - v.y) * 0.5 * window.innerHeight];
        }),
      });
    }
    return out;
  }

  /**
   * QA only. The real glass mesh, measured -- not the frame that produced it.
   *
   * `getSourceExactSlots` projects the LAYOUT FRAME's half-extents, so it
   * reports what the card was asked to be. A quality step rebuilds the glass
   * geometry, and the question there is what the card actually became: this
   * reads the geometry's own bounding box, takes its corners through the mesh's
   * world matrix and projects those.
   */
  getGlassMeshTruth(): Record<string, unknown> {
    const handle = this.renderer.handle;
    const truth = this.grid.getGlassGeometryTruth();
    if (!handle) return { ...truth, slots: [] };
    this.applyPose();
    this.grid.root.updateWorldMatrix(true, true);
    const [minX, minY] = truth.boundingBoxLocal.min;
    const [maxX, maxY] = truth.boundingBoxLocal.max;
    const local: Array<[number, number]> = [
      [minX, maxY], [maxX, maxY], [maxX, minY], [minX, minY],
    ];
    const slots: Array<Record<string, unknown>> = [];
    const count = this.sourceExact ? this.grid.activeSlotCount : this.grid.slots.length;
    for (let n = 0; n < count; n += 1) {
      const mesh = this.grid.slots[n].glass;
      const cornersPx = local.map(([x, y]) => {
        const v = new Vector3(x, y, 0);
        mesh.localToWorld(v);
        v.project(handle.camera);
        return [(v.x + 1) * 0.5 * window.innerWidth, (1 - v.y) * 0.5 * window.innerHeight];
      });
      slots.push({ slotIndex: this.grid.slots[n].slotIndex, cornersPx });
    }
    return { ...truth, slots };
  }

  /** V4-specific evidence for the Round 1 engineering gate. */
  getV4State(): Record<string, unknown> {
    const asset = this.grid.getAssetState();
    return {
      optics: "v4",
      version: V4_OPTICS_CONFIG.version,
      foundation: this.foundation,
      compositionScale: this.renderer.compositionScale,
      viewZoom: this.renderer.viewZoom,
      viewport: [window.innerWidth, window.innerHeight],
      composition: this.composition,
      verticalMode: this.verticalMode,
      portraitLaw: this.portraitLaw,
      phaseModel: this.phaseModel,
      sourceExact: this.sourceExact,
      sourceExactFrame: this.frame ?? null,
      activeSlotCount: this.sourceExact ? this.grid.activeSlotCount : null,
      slotIdentity: this.sourceExact ? this.slotIdentity() : null,
      portraitVertical: this.portraitVertical,
      landscapeRowOrigin: this.landscapeRowOrigin,
      effectiveCellH: effectiveCellH(this.grid.composition),
      rowOrigin: rowOrigin(window.innerWidth, window.innerHeight, this.motion.scrollY,
                           effectiveCellH(this.grid.composition)),
      catalogRowAtCentre: this.catalogRowAtCentre(),
      // Engine-side scroll, so a recording can log where the grid ACTUALLY is
      // rather than the offset it asked for.
      scrollX: this.motion.scrollX,
      scrollY: this.motion.scrollY,
      gridX: this.gridX(),
      gridY: this.gridY(),
      ...this.runtimeTruth(),
      restOffset: restOffset(window.innerWidth, window.innerHeight, this.composition,
                             this.verticalMode, this.phaseModel),
      route: location.pathname,
      normalPathDirectMedia: false,
      v3Preserved: true,
      sceneColor: this.pipeline.describe(),
      debug: this.v4Debug,
      shell: this.v4Shell,
      pool: this.grid.getPoolState(),
      asset,
      renderedFrames: this.renderedFrames,
      videoFrames: asset.videoFrames,
      elapsedSeconds: this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0,
      mobileViewport: isMobileViewport(),
      dpr: this.renderer.handle?.renderer.getPixelRatio() ?? 1,
    };
  }

  /**
   * What the RUNTIME is actually doing, as opposed to what config says it
   * should. `scaleDerivedFromActualCameraProjection` is measured by projecting
   * a known world segment through the live camera, so it cannot agree with the
   * config function by construction -- which is exactly the failure it exists
   * to catch.
   */
  /**
   * Which catalog row the viewport centre is looking at.
   *
   * Kept separate from the geometry row index and from the pool's recycling
   * origin on purpose: aligning grey slabs while the catalog silently steps a
   * row is exactly the failure this reports. `restY0 = -cellH/2` puts row j = 1
   * immediately below the centre, so that is the row named here.
   */
  private catalogRowAtCentre(): Record<string, unknown> {
    const composition = this.grid.composition;
    const cellH = effectiveCellH(composition);
    const restY0 = composition.version === "v2"
      ? (composition.vertical?.restY0
         ?? compositionParams(composition.verticalMode, composition.portraitLaw).restY0)
      : GRID.restY0;
    // Row v = j * cellH + restY0 - scrollY; the row just below the viewport
    // centre is the smallest j whose v is not negative.
    const j = Math.ceil((this.gridY() - restY0) / cellH);
    return {
      geometryRowIndex: j,
      rowAboveCentre: j - 1,
      recyclingOriginJ: Math.round(this.gridY() / cellH),
      restY0,
      codes: [-1, 0, 1].map((di) => catalogAt(di, j).code),
    };
  }

  /**
   * Pool identity: what the source-exact path guarantees about its slots.
   *
   * ILG code is slotIndex + 1 and is bound to the SLOT, so it survives wrapping
   * and every resize -- the Target's own rule. Reported as data; no typography
   * parameter changes this stage.
   */
  private slotIdentity(): Record<string, unknown> {
    const active = this.grid.slots.slice(0, this.grid.activeSlotCount);
    return {
      activeSlotCount: active.length,
      poolCapacity: this.grid.slots.length,
      codesAreSlotIndexPlusOne: active.every((s) => s.code === slotCode(s.slotIndex)),
      firstCodes: active.slice(0, 6).map((s) => s.code),
      lastCode: active.length ? active[active.length - 1].code : null,
      allActiveVisibleFlagSet: active.every((s) => s.active === true),
      inactiveHidden: this.grid.slots.slice(this.grid.activeSlotCount)
        .every((s) => s.active === false && s.group.visible === false),
    };
  }

  private runtimeTruth(): Record<string, unknown> {
    const handle = this.renderer.handle;
    const requested = this.portraitLaw;
    const rendererLaw = this.renderer.portraitLaw;
    const gridLaw = this.grid.composition.portraitLaw ?? null;
    const frame = this.frame;
    const frameScaleTarget = frame ? 1 : null;
    let derived: number | null = null;
    let derivedY: number | null = null;
    let fov: number | null = null;
    let focalPx: number | null = null;
    if (handle) {
      const camera = handle.camera;
      fov = camera.fov;
      focalPx = (window.innerHeight / 2) / Math.tan((camera.fov * Math.PI) / 360);
      // Symmetric, short probes about the origin. A 0..100 segment measures a
      // secant, and with CAMERA.y = 8 the far end of a VERTICAL secant sits
      // measurably closer to the camera than the near end -- that alone showed
      // up as 7.4e-4 on the Y axis, which is pitch, not a projection error.
      // A short segment centred on the origin measures the local scale instead.
      const xm = new Vector3(-1, 0, 0).project(camera);
      const xp = new Vector3(1, 0, 0).project(camera);
      derived = ((xp.x - xm.x) * 0.5 * window.innerWidth) / 2;
      // The anamorphic portrait scale lives in the projection, so the only
      // honest proof it is running is to project a VERTICAL world segment
      // through the live camera and measure what comes out.
      const ym = new Vector3(0, -1, 0).project(camera);
      const yp = new Vector3(0, 1, 0).project(camera);
      derivedY = ((yp.y - ym.y) * 0.5 * window.innerHeight) / 2;
    }
    const reported = this.renderer.compositionScale;
    // On the source-exact path there is no fitted law to propagate. What has to
    // be true instead is that the camera the renderer built is the one the
    // contract specifies, and that one world unit is one CSS pixel at z = 0.
    const lawsAgree = frame
      ? true
      : requested === rendererLaw && requested === gridLaw;
    // Tolerance, not slop. The config scale is focal / perspectivePx, which
    // treats the camera as unpitched; the live projection measures along the
    // real view axis, and CAMERA.y = 8 makes that axis 1000.032 long rather
    // than 1000. That is a fixed 3.2e-5 relative difference by construction.
    // Source-exact: the camera stands at the focal distance on the axis, so a
    // world unit projects to exactly one CSS pixel at z = 0. That is the whole
    // claim, and it is measured through the live camera rather than asserted.
    const scaleAgrees = derived !== null
      && Math.abs(derived - (frameScaleTarget ?? reported)) <= 1e-4 * Math.max(1, reported);
    const k = this.renderer.verticalScaleY;
    const expectedY = (frameScaleTarget ?? reported) * k;
    const verticalAgrees = derivedY !== null
      && Math.abs(derivedY - expectedY) <= 1e-4 * Math.max(1, expectedY);
    // Landscape must be untouched by the portrait model, at every model.
    const landscapeUntouched = isPortrait(window.innerWidth, window.innerHeight) || k === 1;
    return {
      requestedPortraitLaw: requested,
      rendererPortraitLaw: rendererLaw,
      gridPortraitLaw: gridLaw,
      effectivePerspectivePx: focalPx,
      effectiveFov: fov,
      reportedCompositionScale: reported,
      scaleDerivedFromActualCameraProjection: derived,
      verticalScaleDerivedFromActualCameraProjection: derivedY,
      reportedVerticalScaleY: k,
      expectedVerticalScreenScale: expectedY,
      sourceExactCamera: frame ? {
        expectedPerspective: frame.perspective,
        actualCameraZ: handle ? handle.camera.position.z : null,
        actualFovDeg: fov,
        expectedFovDeg: (2 * Math.atan(window.innerHeight / 2 / frame.perspective) * 180) / Math.PI,
        cameraOnAxis: handle ? handle.camera.position.x === 0 && handle.camera.position.y === 0 : null,
        near: handle ? handle.camera.near : null,
        far: handle ? handle.camera.far : null,
        oneWorldUnitIsOneCssPixelAtZ0: derived,
      } : null,
      runtimeTruthAssertions: {
        portraitLawPropagated: lawsAgree,
        reportedScaleMatchesCameraProjection: scaleAgrees,
        scaleDeltaPx: derived === null ? null : derived - reported,
        verticalScaleMatchesCameraProjection: verticalAgrees,
        verticalDeltaPx: derivedY === null ? null : derivedY - expectedY,
        landscapeVerticalScaleIsExactlyOne: landscapeUntouched,
        allPass: lawsAgree && scaleAgrees && verticalAgrees && landscapeUntouched,
      },
    };
  }

  getMetrics(): Record<string, unknown> {
    if (!this.renderer.handle) return { ready: false };
    const sorted = [...this.frameTimes].sort((a, b) => a - b);
    const pick = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))] || 0;
    const info = this.renderer.handle.renderer.info;
    return {
      fps: sorted.length ? 1000 / (pick(0.5) || 16.6) : 0,
      medianFrameMs: pick(0.5),
      p95FrameMs: pick(0.95),
      p99FrameMs: pick(0.99),
      drawCalls: info.render?.calls ?? 0,
      triangles: info.render?.triangles ?? 0,
      textures: 0,
      backend: this.renderer.handle.backend,
      quality: this.quality.level,
      /** Frames drawn by the render LOOP. Proof the loop is alive. */
      renderedFrames: this.renderedFrames,
      /** Frames drawn by an explicit `renderOnce`. Proof the hook path ran. */
      renderStamp: this.renderStamp,
      adaptiveSampler: this.adaptiveQuality,
      motionPaused: this.motion.paused,
    };
  }

  getPoolState() {
    return this.grid.getPoolState();
  }

  getAssetState() {
    return this.grid.getAssetState();
  }

  private renderStamp = 0;

  /**
   * Draw one frame NOW, synchronously.
   *
   * Every QA hook that changes what the page should look like ends with this.
   * A paused capture used to depend on "some later frame will repaint" -- and
   * when the tick was returning early that frame never arrived, so a screenshot
   * taken after `setRenderLayers` showed the state BEFORE it. Waiting on a frame
   * that may not come is not a capture protocol.
   *
   * The returned stamp is the proof that this path ran. The live loop repaints
   * too, so an unchanged canvas hash alone cannot distinguish "the explicit
   * redraw happened" from "the loop happened to redraw anyway"; the stamp can.
   */
  renderOnce(): number {
    const handle = this.renderer.handle;
    if (!handle) return this.renderStamp;
    this.grid.update(this.gridX(), this.gridY());
    this.applyPose();
    this.syncLabels();
    handle.renderer.info.reset?.();
    this.drawFrame();
    this.renderStamp += 1;
    return this.renderStamp;
  }

  /** QA only. Monotonic count of frames drawn through `renderOnce`. */
  getRenderStamp(): number {
    return this.renderStamp;
  }

  /**
   * One frame. Foundation mode renders the grey slabs straight to the screen:
   * the two-pass scene-colour path exists only to feed the glass, and there is
   * no glass here.
   */
  private drawFrame(): void {
    const handle = this.renderer.handle;
    if (!handle) return;
    if (this.layoutOnly) {
      handle.renderer.render(handle.scene, handle.camera);
      this.foundationOverlay?.draw(this.getCardQuads());
      return;
    }
    if (!this.glassLayer) {
      // Media-only. The two-pass pipeline exists to feed the glass and it
      // re-asserts glass-on / media-off every frame, so asking it to draw a
      // glass-free frame is a contradiction: render the scene straight instead.
      this.grid.setGlassVisible(false);
      this.grid.setMediaVisible(this.mediaLayer);
      handle.renderer.render(handle.scene, handle.camera);
      this.labels.render(this.poseCamera());
      return;
    }
    this.pipeline.draw(handle.renderer, handle.scene, handle.camera, this.grid);
    this.labels.render(this.poseCamera());
  }

  private applyPipelineSize(): void {
    const dpr = this.renderer.handle?.renderer.getPixelRatio() ?? 1;
    this.pipeline.resize(window.innerWidth, window.innerHeight, dpr);
  }

  private bindWindow(): void {
    const apply = () => {
      this.renderer.resize();
      // The portrait vertical override depends on the viewport, so it has to be
      // re-resolved before placement -- an orientation flip adds or removes it
      // entirely.
      this.syncVerticalOverride();
      // Source-exact: the layout frame IS the resize. Slot count, card size and
      // media fit all follow from it, and nothing is created or destroyed.
      if (this.frame) this.grid.setFrame(this.frame);
      // ... and so does the type layer. A resize changes the card plane, and
      // every type size is a container query against it.
      if (this.frame && !this.layoutOnly) this.labels.setFrame(this.frame);
      // The rest offset is regime-dependent, so a resize can flip the brick
      // parity; re-place the grid before anything reads its positions.
      this.grid.update(this.gridX(), this.gridY());
      this.applyPipelineSize();
      this.labels.setSize(window.innerWidth, window.innerHeight);
      this.foundationOverlay?.setSize(window.innerWidth, window.innerHeight);
      this.input.setViewSize(window.innerWidth, window.innerHeight);
    };
    window.addEventListener("resize", () => {
      apply();
      window.clearTimeout(this.resizeTimer);
      this.resizeTimer = window.setTimeout(apply, 80);
    });
    document.addEventListener("visibilitychange", () => {
      this.visible = document.visibilityState === "visible";
      if (this.visible) this.lastT = performance.now();
    });
  }

  private tick = (now: number): void => {
    if (this.disposed) return;
    this.raf = requestAnimationFrame(this.tick);
    if (!this.visible) return;
    const dt = Math.min(0.05, (now - this.lastT) / 1000);
    this.lastT = now;
    if (!this.motion.paused) this.elapsed += dt;
    this.frameTimes.push(dt * 1000);
    if (this.frameTimes.length > 180) this.frameTimes.shift();
    // Only the SAMPLER is conditional. Turning adaptive quality off is a
    // harness capability for holding a level still; it must never stop the
    // page from stepping and drawing. The previous form was `if
    // (!this.adaptiveQuality) return;`, which returned out of the whole tick
    // and froze motion, recycling, pose, labels and the canvas along with it.
    //
    // The sampler is skipped rather than called-and-ignored because sample()
    // mutates its own `level`: reading it and discarding the answer would drift
    // the reported quality away from the quality the grid is actually running.
    if (this.adaptiveQuality) {
      const { level, changed } = this.quality.sample(dt * 1000, now);
      if (changed) {
        this.adaptiveChanges.push({
          atSeconds: this.startedAt ? (performance.now() - this.startedAt) / 1000 : 0,
          level,
        });
        this.setQuality(level);
      }
    }
    this.motion.step(dt, now);
    this.grid.update(this.gridX(), this.gridY());
    this.applyPose();
    const handle = this.renderer.handle;
    this.syncLabels();
    handle.renderer.info.reset?.();
    this.drawFrame();
    this.renderedFrames += 1;
  };

  /**
   * The camera the CSS3D layer, the projection and the culling use.
   *
   * A clone of the render camera's lens, kept at the SAME orbit position AND
   * carrying the same velocity dolly. It is created once and its lens
   * re-copied each frame,
   * so a resize or a quality change cannot leave the two disagreeing about
   * fov, aspect, near or far.
   */
  private css3dTransformCameraFor(render: PerspectiveCamera): PerspectiveCamera {
    if (!this.css3dTransformCamera) this.css3dTransformCamera = new PerspectiveCamera();
    const c = this.css3dTransformCamera;
    if (c.fov !== render.fov || c.aspect !== render.aspect
        || c.near !== render.near || c.far !== render.far) {
      c.fov = render.fov; c.aspect = render.aspect;
      c.near = render.near; c.far = render.far;
      c.updateProjectionMatrix();
    }
    return c;
  }

  /** Whichever camera the label layer and the projections should use. */
  private poseCamera(): PerspectiveCamera {
    const handle = this.renderer.handle;
    if (this.frame && this.css3dTransformCamera) return this.css3dTransformCamera;
    return handle.camera;
  }

  /**
   * The coverage camera, lens re-copied from the render camera each frame --
   * the Target does exactly this (`Py.fov = n.fov, ...` before its coverage
   * loop), so a resize or a quality change cannot leave the two disagreeing
   * about fov, aspect, near or far.
   */
  private coverageCameraFor(render: PerspectiveCamera): PerspectiveCamera {
    if (!this.sourceExactCoverageCamera) this.sourceExactCoverageCamera = new PerspectiveCamera();
    const c = this.sourceExactCoverageCamera;
    if (c.fov !== render.fov || c.aspect !== render.aspect
        || c.near !== render.near || c.far !== render.far) {
      c.fov = render.fov; c.aspect = render.aspect;
      c.near = render.near; c.far = render.far;
      c.updateProjectionMatrix();
    }
    return c;
  }

  /**
   * Sync the label layer, with coverage verdicts on the source-exact path.
   *
   * The verdict inputs mirror the Target's own: its coverage test reads the
   * live `window.innerWidth/Height` and the live layout frame every frame.
   * `applyPose` has already posed the coverage camera when this runs -- the
   * Target's camera component subscribes before its grid component, so its
   * camera writes precede its coverage loop the same way.
   */
  private syncLabels(): void {
    if (this.layoutOnly) return;
    const t0 = this.labelSyncProbe ? performance.now() : 0;
    if (this.frame && this.sourceExactCoverageCamera) {
      const verdicts = this.labelCulling.compute(
        this.grid.slots, this.sourceExactCoverageCamera,
        window.innerWidth, window.innerHeight,
        this.frame.planeWidth, this.frame.planeHeight,
      );
      this.labels.sync(this.gridAsV3(), this.poseCamera(), verdicts);
    } else {
      this.labels.sync(this.gridAsV3(), this.poseCamera());
    }
    if (this.labelSyncProbe) {
      this.labelSyncTimes.push(performance.now() - t0);
      if (this.labelSyncTimes.length > 6000) this.labelSyncTimes.splice(0, 2000);
    }
  }

  /** QA only. Arm or disarm the labels.sync CPU probe; arming clears it. */
  setLabelSyncProbe(on: boolean): void {
    this.labelSyncProbe = on;
    this.labelSyncTimes.length = 0;
  }

  /** QA only. The probe's samples in ms, drained on read. */
  getLabelSyncStats(): Record<string, unknown> {
    const samples = this.labelSyncTimes.slice();
    this.labelSyncTimes.length = 0;
    return { probe: this.labelSyncProbe, samples };
  }

  private applyPose(): void {
    const handle = this.renderer.handle;
    if (!handle) return;
    const frame = this.frame;
    if (frame) {
      // Source-exact camera pose. The Target's parallax ORBITS the camera on a
      // sphere of radius `perspective` about the origin and never rotates the
      // grid; it also has no standing pitch, so at rest the camera is exactly
      // on axis. Writing CAMERA.y here -- which the legacy branch below does --
      // is what left a 3.2e-5 residual in every scale proof so far.
      this.grid.root.rotation.set(0, 0, 0);
      const [ox, oy, oz] = sourceExactOrbit(this.motion.pointerX, this.motion.pointerY,
                                            frame.perspective);
      // The Target keeps TWO cameras at the same orbit position and BOTH carry
      // the velocity dolly on z: the render camera here, and the CSS3D transform
      // camera set below. They sit at the same z at every moment, not merely at
      // rest, so glass and labels never separate. The dolly-free camera in the
      // bundle is a projection and culling concept only; it renders nothing.
      const dz = sourceExactDolly(this.motion.magnitude, sourceExactMaxZoomZ(frame.perspective));
      handle.camera.position.set(ox, oy, oz + dz);
      handle.camera.lookAt(0, 0, 0);
      // The CSS3D camera carries the dolly TOO. An earlier reading had the
      // Target keeping a dolly-free camera for the type layer, so glass and
      // labels would separate under fast motion. Its own recorded CSS3D camera
      // matrix says otherwise: the camera's distance from the origin rises
      // from exactly 1000 at rest to 1158 on a flick and 1223 on a long drag,
      // and stays at exactly 1000 through a pointer sweep -- which moves the
      // camera but produces no velocity. A dolly-free CSS3D camera cannot do
      // that. The dolly-free camera in the bundle drives projection and
      // culling, not the transform.
      const label = this.css3dTransformCameraFor(handle.camera);
      label.position.set(ox, oy, oz + dz);
      label.lookAt(0, 0, 0);
      label.updateMatrixWorld();
      // The coverage camera: the SAME orbit, WITHOUT the dolly. The Target's
      // deciding line poses both cameras together -- `Py.position.set(d,h,f)`
      // against `t.position.set(d,h,f+p)` -- and this is that line, ours.
      const coverage = this.coverageCameraFor(handle.camera);
      coverage.position.set(ox, oy, oz);
      coverage.lookAt(0, 0, 0);
      coverage.updateMatrixWorld();
      if (this.pointerLight) {
        // The Target's scene has no light at all: its highlight moves because
        // the CAMERA orbits against a fixed environment, not because anything
        // moves a light. Our rig is held at its base position so the highlight
        // is driven by the same thing -- the orbit. The light's own intensity,
        // colour and base position are untouched; only what drives it changes.
        updatePointerKeyLightV4(this.pointerLight, 0, 0);
      }
      return;
    }
    this.grid.root.rotation.set(this.motion.rotX, this.motion.rotY, 0);
    handle.camera.position.set(
      this.motion.camX,
      CAMERA.y + this.motion.camY,
      CAMERA.z * this.renderer.viewZoom,
    );
    handle.camera.lookAt(this.motion.camX, CAMERA.lookY + this.motion.camY, 0);
    if (this.pointerLight) {
      updatePointerKeyLightV4(this.pointerLight, this.motion.pointerX, this.motion.pointerY);
    }
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.raf);
    this.input?.dispose();
    this.labels?.dispose();
    this.foundationOverlay?.dispose();
    this.grid.dispose();
    this.pipeline?.dispose();
    this.environment?.dispose();
    this.renderer.dispose();
  }
}
