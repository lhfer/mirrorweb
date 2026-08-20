import { AmbientLight, Vector3, type DirectionalLight } from "three/webgpu";
import { CAMERA, GRID, TILE, restOffset, type QualityLevel } from "../../config";
import { readDebugMode, type DebugMode } from "../../debug/DebugMode";
import { isFoundationLayout, readFoundationMode, type FoundationMode } from "../../debug/FoundationMode";
import { FoundationOverlay } from "../../debug/FoundationOverlay";
import { InputController } from "../../interaction/InputController";
import { MotionController } from "../../interaction/MotionController";
import { AdaptiveQuality } from "../../quality/AdaptiveQuality";
import { isMobileViewport } from "../../quality/DeviceProfile";
import { RendererController } from "../../rendering/RendererController";
import type { InfiniteGlassGrid } from "../../scene/InfiniteGlassGrid";
import { LoadingOverlay } from "../../ui/LoadingOverlay";
import { PageOverlay } from "../../ui/PageOverlay";
import { TileLabelLayer } from "../../ui/TileLabelLayer";
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
  private foundationOverlay?: FoundationOverlay;

  constructor(private readonly options: GridAppV4Options = {}) {
    this.v4Debug = options.debugMode ?? "beauty";
    this.v4Shell = options.shellMode ?? "energy-controlled";
    this.foundation = options.foundation ?? readFoundationMode();
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
    return scrollX + restOffset(window.innerWidth, window.innerHeight).x;
  }

  private gridY(scrollY = this.motion.scrollY): number {
    return scrollY + restOffset(window.innerWidth, window.innerHeight).y;
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
    );
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
      this.labels.attach(this.gridAsV3(), this.debugMode);
      this.labels.setSize(window.innerWidth, window.innerHeight);
    }
    this.grid.update(this.gridX(0), this.gridY(0));
    this.applyPose();
    if (!this.layoutOnly) this.labels.sync(this.gridAsV3(), handle.camera);

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
  }

  private glassLayer = true;
  private mediaLayer = true;

  setPointer(x: number, y: number): void {
    this.motion.setPointer(x, y);
  }

  setOffset(x: number, y: number): void {
    this.motion.scrollX = x;
    this.motion.scrollY = y;
    this.grid.update(this.gridX(x), this.gridY(y));
    this.applyPose();
  }

  setVelocity(x: number, y: number): void {
    this.motion.velocityX = x;
    this.motion.velocityY = y;
  }

  setQuality(level: QualityLevel): void {
    this.quality.level = level;
    this.grid.setQuality(level);
    this.pipeline.setQuality(level);
    this.grid.setSceneUvScale(this.pipeline.sceneUvScale);
  }

  setDpr(value: number): void {
    this.renderer.setDpr(value);
    this.applyPipelineSize();
    this.labels.setSize(window.innerWidth, window.innerHeight);
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

  /** QA only. Per-clip crop numbers behind the current fit. */
  getMediaFits() {
    return this.grid.getMediaFits();
  }

  reset(): void {
    this.motion.reset();
    this.elapsed = 0;
    this.grid.update(this.gridX(0), this.gridY(0));
    this.applyPose();
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
    const halfWidth = TILE.width * 0.5;
    const halfHeight = TILE.height * 0.5;
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
    return this.grid.slots.map((slot) => ({
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
    };
  }

  getPoolState() {
    return this.grid.getPoolState();
  }

  getAssetState() {
    return this.grid.getAssetState();
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
      this.labels.render(handle.camera);
      return;
    }
    this.pipeline.draw(handle.renderer, handle.scene, handle.camera, this.grid);
    this.labels.render(handle.camera);
  }

  private applyPipelineSize(): void {
    const dpr = this.renderer.handle?.renderer.getPixelRatio() ?? 1;
    this.pipeline.resize(window.innerWidth, window.innerHeight, dpr);
  }

  private bindWindow(): void {
    const apply = () => {
      this.renderer.resize();
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
    const level = this.quality.sample(dt * 1000, now);
    if (level !== this.quality.level) this.setQuality(level);
    this.motion.step(dt);
    this.grid.update(this.gridX(), this.gridY());
    this.applyPose();
    const handle = this.renderer.handle;
    if (!this.layoutOnly) this.labels.sync(this.gridAsV3(), handle.camera);
    handle.renderer.info.reset?.();
    this.drawFrame();
    this.renderedFrames += 1;
  };

  private applyPose(): void {
    const handle = this.renderer.handle;
    if (!handle) return;
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
