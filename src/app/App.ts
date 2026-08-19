import { Vector3, type DirectionalLight } from "three/webgpu";
import { CAMERA, GRID, TILE, type QualityLevel } from "../config";
import { DebugHud } from "../debug/DebugHud";
import { isLayoutDebug, readDebugMode, type DebugMode } from "../debug/DebugMode";
import { InputController } from "../interaction/InputController";
import { MotionController } from "../interaction/MotionController";
import { AdaptiveQuality } from "../quality/AdaptiveQuality";
import { addStudioLights, createStudioEnvironment } from "../rendering/StudioEnvironment";
import { RenderPipeline } from "../rendering/RenderPipeline";
import { RendererController } from "../rendering/RendererController";
import { InfiniteGlassGrid } from "../scene/InfiniteGlassGrid";
import { LoadingOverlay } from "../ui/LoadingOverlay";
import { PageOverlay } from "../ui/PageOverlay";
import { TileLabelLayer } from "../ui/TileLabelLayer";

const _ndc = new Vector3();
const frameTimes: number[] = [];

export class App {
  readonly motion = new MotionController();
  readonly renderer = new RendererController();
  readonly grid = new InfiniteGlassGrid();
  readonly quality = new AdaptiveQuality("high");
  readonly debugMode: DebugMode = readDebugMode();
  private labels!: TileLabelLayer;
  private hud!: DebugHud;
  private pipeline!: RenderPipeline;
  private input!: InputController;
  private loading!: LoadingOverlay;
  private raf = 0;
  private lastT = 0;
  private elapsed = 0;
  private resizeTimer = 0;
  private visible = true;
  private keyLight?: DirectionalLight;

  async start() {
    this.loading = new LoadingOverlay(document.getElementById("loading-overlay")!);
    new PageOverlay(document.getElementById("page-overlay")!);
    this.labels = new TileLabelLayer(document.getElementById("labels")!);
    this.hud = new DebugHud(document.getElementById("app")!);
    this.hud.setMode(this.debugMode);
    this.loading.setPercent(8);

    const forceWebGL = new URLSearchParams(location.search).get("gl") === "1";
    const handle = await this.renderer.init(document.getElementById("viewport")!, forceWebGL);
    this.loading.setPercent(24);
    const lights = addStudioLights(handle.scene);
    this.keyLight = lights.key;
    handle.scene.environment = createStudioEnvironment(handle.renderer);
    this.loading.setPercent(36);

    if (!isLayoutDebug(this.debugMode)) {
      await this.grid.prepare((value) => this.loading.setPercent(value));
      this.grid.reel?.unlock();
    }
    this.pipeline = new RenderPipeline(this.renderer, this.labels, this.grid);
    this.pipeline.resize();
    this.grid.build(this.quality.level, handle.backend, this.debugMode, this.pipeline.sceneTexture);
    handle.scene.add(this.grid.root);
    this.labels.attach(this.grid, this.debugMode);
    this.labels.setSize(window.innerWidth, window.innerHeight);
    this.grid.update(0, 0);
    this.applyPose();
    this.labels.sync(this.grid, handle.camera);

    this.input = new InputController(handle.canvas, this.motion, () => this.grid.reel?.unlock());
    this.bindWindow();
    this.grid.syncVideos();
    this.pipeline.draw();
    this.grid.syncVideos();
    this.pipeline.draw();
    this.loading.setPercent(100);
    if (isLayoutDebug(this.debugMode) || this.grid.getAssetState().ready) {
      this.loading.hide();
    }
    this.lastT = performance.now();
    this.tick(this.lastT);
  }

  pause() {
    this.motion.paused = true;
  }

  resume() {
    this.motion.paused = false;
    this.lastT = performance.now();
  }

  setTime(seconds: number) {
    this.elapsed = seconds;
    this.grid.reel?.seek(seconds);
  }

  setPointer(x: number, y: number) {
    this.motion.setPointer(x, y);
  }

  setOffset(x: number, y: number) {
    this.motion.scrollX = x;
    this.motion.scrollY = y;
    this.grid.update(x, y);
    this.applyPose();
  }

  setVelocity(x: number, y: number) {
    this.motion.velocityX = x;
    this.motion.velocityY = y;
  }

  setQuality(level: QualityLevel) {
    this.quality.level = level;
    this.grid.setQuality(level);
  }

  setDpr(value: number) {
    this.renderer.setDpr(value);
    this.pipeline.resize();
    this.labels.setSize(window.innerWidth, window.innerHeight);
  }

  reset() {
    this.motion.reset();
    this.elapsed = 0;
    this.grid.update(0, 0);
    this.applyPose();
  }

  getState() {
    if (!this.renderer.handle) {
      return { ready: false, landmarks: [] };
    }
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
        title: slot.i + "," + slot.j,
        nx: (_ndc.x + 1) * 0.5,
        ny: (1 - _ndc.y) * 0.5,
      };
    });
    return {
      ready: true,
      backend: this.renderer.handle.backend,
      quality: this.quality.level,
      debug: this.debugMode,
      milestone: 3,
      glass: "volume",
      samplesScene: true,
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
      tile: TILE,
      grid: GRID,
      landmarks,
    };
  }

  getMetrics() {
    if (!this.renderer.handle) return { ready: false };
    const sorted = [...frameTimes].sort((a, b) => a - b);
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

  private bindWindow() {
    window.addEventListener("resize", () => {
      this.renderer.resize();
      this.pipeline.resize();
      this.labels.setSize(window.innerWidth, window.innerHeight);
      this.input.setViewSize(window.innerWidth, window.innerHeight);
      window.clearTimeout(this.resizeTimer);
      this.resizeTimer = window.setTimeout(() => {
        this.renderer.resize();
        this.pipeline.resize();
        this.labels.setSize(window.innerWidth, window.innerHeight);
        this.input.setViewSize(window.innerWidth, window.innerHeight);
      }, 80);
    });
    document.addEventListener("visibilitychange", () => {
      this.visible = document.visibilityState === "visible";
      if (this.visible) this.lastT = performance.now();
    });
  }

  private tick = (now: number) => {
    this.raf = requestAnimationFrame(this.tick);
    if (!this.visible) return;
    const dt = Math.min(0.05, (now - this.lastT) / 1000);
    this.lastT = now;
    if (!this.motion.paused) this.elapsed += dt;
    frameTimes.push(dt * 1000);
    if (frameTimes.length > 180) frameTimes.shift();
    this.quality.sample(dt * 1000, now);
    this.motion.step(dt);
    this.grid.syncVideos();
    this.grid.update(this.motion.scrollX, this.motion.scrollY);
    this.applyPose();
    this.labels.sync(this.grid, this.renderer.handle.camera);
    if (this.debugMode !== "off") this.hud.setText(this.debugText());
    this.renderer.handle.renderer.info.reset?.();
    this.pipeline.draw();
  };

  private debugText() {
    const pool = this.grid.getPoolState();
    const state = this.getState() as { landmarks: Array<{ nx: number; ny: number }> };
    const outside = state.landmarks.filter((item) => item.nx < 0 || item.nx > 1 || item.ny < 0 || item.ny > 1).length;
    const inside = state.landmarks.length - outside;
    return [
      `debug=${this.debugMode}`,
      `pool ${pool.cols}×${pool.rows} = ${pool.slots}`,
      `created ${pool.created}  destroyed ${pool.destroyed}  remaps ${pool.remaps}`,
      `materials ${pool.materials}  geometries ${pool.geometries}`,
      `projected inside ${inside}  overscan ${outside}`,
      `scroll ${this.motion.scrollX.toFixed(1)}, ${this.motion.scrollY.toFixed(1)}`,
      `pointer ${this.motion.pointerX.toFixed(2)}, ${this.motion.pointerY.toFixed(2)}`,
      `tilt ${(this.motion.rotX * 180 / Math.PI).toFixed(2)}°, ${(this.motion.rotY * 180 / Math.PI).toFixed(2)}°`,
    ].join("\n");
  }

  private applyPose() {
    const handle = this.renderer.handle;
    if (!handle) return;
    this.grid.root.rotation.set(this.motion.rotX, this.motion.rotY, 0);
    handle.camera.position.set(this.motion.camX, CAMERA.y + this.motion.camY, CAMERA.z * this.renderer.viewZoom);
    handle.camera.lookAt(this.motion.camX, CAMERA.lookY + this.motion.camY, 0);
    this.keyLight?.position.set(this.motion.lightX, this.motion.lightY, 1100);
  }

  dispose() {
    cancelAnimationFrame(this.raf);
    this.input.dispose();
    this.labels.dispose();
    this.hud.dispose();
    this.grid.dispose();
    this.pipeline.dispose();
    this.renderer.dispose();
  }
}
