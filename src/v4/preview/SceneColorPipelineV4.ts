import {
  ACESFilmicToneMapping,
  NoToneMapping,
  PerspectiveCamera,
  type Scene,
  type WebGPURenderer,
} from "three/webgpu";
import { SceneColorTargetV4 } from "../../rendering/SceneColorTargetV4";
import { V4_OPTICS_CONFIG } from "../OpticsConfigV4";
import type { QualityLevel } from "../../config";
import type { InfiniteGlassGridV4 } from "./InfiniteGlassGridV4";

/**
 * Two-pass V4 pipeline for the real multi-card page.
 *
 * Pass 1 renders the card media and the gutter into a linear half-float
 * scene-color target with mipmaps, using an OVERSCANNED camera. Pass 2 renders
 * the glass, which samples that target in screen space.
 *
 * The overscan is what keeps a partially off-screen card honest: its strong rim
 * can refract up to `maxRefractionUv` of the frame, and without extra scene
 * outside the visible frame that sample clamps to the border and smears the
 * last column of pixels along the edge.
 */
export class SceneColorPipelineV4 {
  /**
   * O4 factor E -- the transform the GLASS pass renders through.
   *
   * The Target disables tone mapping on the card MATERIAL
   * (`toneMapped:!1`, bundle byte 1976900). That mechanism does not exist
   * in our stack: three's WebGPU node renderer never reads
   * `Material.toneMapped` -- the string does not appear anywhere in
   * three.webgpu.js -- and applies the transform at the renderer's output
   * stage instead. So the faithful place to neutralise it here is the pass
   * itself, and the glass pass is the right scope: the media is already
   * written to the scene-colour target with NoToneMapping, and the final
   * pass draws the glass alone (media visible = false, labels are CSS3D).
   * Setting this therefore changes the body's output transform and nothing
   * the media or the UI sees. The reflection shell, when enabled, shares
   * the pass -- recorded rather than hidden.
   */
  glassToneMapping: typeof ACESFilmicToneMapping | typeof NoToneMapping =
    ACESFilmicToneMapping;

  readonly sceneColor: SceneColorTargetV4;
  private readonly overscanCamera = new PerspectiveCamera();
  private overscan: number;
  private cssWidth = 1;
  private cssHeight = 1;
  private dpr = 1;

  constructor(quality: QualityLevel = "high", overscan: number = 1.3) {
    this.sceneColor = new SceneColorTargetV4(quality);
    this.overscan = Math.max(1, Math.min(1.6, overscan));
    this.overscanCamera.name = "MirrorWeb.V4.SceneColorOverscanCamera";
  }

  /** screen UV -> scene-target UV scale handed to the material. */
  get sceneUvScale(): number {
    return 1 / this.overscan;
  }

  get overscanFactor(): number {
    return this.overscan;
  }

  /**
   * Distance, in scene-target UV, between the furthest sample this material can
   * ever request and the edge of the target. Positive means screen-UV clamping
   * — and therefore border smearing — is impossible by construction.
   */
  get clampHeadroom(): number {
    const material = V4_OPTICS_CONFIG.material;
    const reach = 0.5 + material.maxRefractionUv + material.dispersionUv + material.adaptivityRadiusUv;
    return 0.5 - this.sceneUvScale * reach;
  }

  describe() {
    return {
      ...this.sceneColor.describe(),
      overscan: this.overscan,
      sceneUvScale: this.sceneUvScale,
      clampHeadroom: this.clampHeadroom,
      cssWidth: this.cssWidth,
      cssHeight: this.cssHeight,
      dpr: this.dpr,
    };
  }

  resize(cssWidth: number, cssHeight: number, dpr: number): void {
    this.cssWidth = Math.max(1, cssWidth);
    this.cssHeight = Math.max(1, cssHeight);
    this.dpr = Math.max(0.25, dpr);
    this.sceneColor.resize(this.cssWidth * this.overscan, this.cssHeight * this.overscan, this.dpr);
  }

  setQuality(level: QualityLevel): void {
    if (this.sceneColor.setQuality(level)) {
      this.sceneColor.resize(this.cssWidth * this.overscan, this.cssHeight * this.overscan, this.dpr);
    }
  }

  draw(
    renderer: WebGPURenderer,
    scene: Scene,
    camera: PerspectiveCamera,
    grid: InfiniteGlassGridV4,
    collect?: (pass: "sceneColor" | "final", calls: number, triangles: number) => void,
  ): void {
    this.syncOverscanCamera(camera);

    // Per-pass stats need deterministic reset boundaries. The renderer's own
    // autoReset fires inside its INTERNAL animation loop, not per render()
    // call, and `info.render.calls` counts render() invocations since load --
    // the per-frame field is `drawCalls`. While collecting, take explicit
    // control of the reset; restore the flag afterwards.
    const info = renderer.info as unknown as {
      autoReset: boolean;
      reset: () => void;
      render: { drawCalls: number; triangles: number };
    };
    const prevAutoReset = collect ? info.autoReset : false;
    if (collect) {
      info.autoReset = false;
      info.reset();
    }

    grid.setGlassVisible(false);
    grid.setMediaVisible(true);
    renderer.toneMapping = NoToneMapping;
    renderer.setRenderTarget(this.sceneColor.target);
    renderer.clear();
    renderer.render(scene, this.overscanCamera);
    renderer.setRenderTarget(null);
    if (collect) {
      collect("sceneColor", info.render.drawCalls, info.render.triangles);
      info.reset();
    }

    renderer.toneMapping = this.glassToneMapping;
    grid.setGlassVisible(true);
    grid.setMediaVisible(false);
    renderer.render(scene, camera);
    if (collect) {
      collect("final", info.render.drawCalls, info.render.triangles);
      info.autoReset = prevAutoReset;
    }
  }

  private syncOverscanCamera(camera: PerspectiveCamera): void {
    const wide = this.overscanCamera;
    wide.position.copy(camera.position);
    wide.quaternion.copy(camera.quaternion);
    wide.up.copy(camera.up);
    wide.near = camera.near;
    wide.far = camera.far;
    wide.aspect = camera.aspect;
    // A pinhole camera scales uniformly with tan(fov/2), so widening the
    // vertical field by `overscan` zooms the projected image out by exactly the
    // same factor on both axes.
    const halfFov = (camera.fov * Math.PI) / 360;
    wide.fov = (2 * Math.atan(Math.tan(halfFov) * this.overscan) * 180) / Math.PI;
    wide.updateProjectionMatrix();
    wide.updateMatrixWorld();
  }

  dispose(): void {
    this.sceneColor.dispose();
  }
}
