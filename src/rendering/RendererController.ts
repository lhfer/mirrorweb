import {
  ACESFilmicToneMapping,
  Color,
  PerspectiveCamera,
  Scene,
  WebGPURenderer,
} from "three/webgpu";
import { CAMERA, CLEAR_COLOR, compositionScale, effectivePerspectivePx, isSourceExact,
  verticalScaleY, viewZoom, PORTRAIT_VERTICAL, type CompositionVersion, type PortraitLaw,
  type PortraitVerticalModel, type VerticalMode } from "../config";
import { sourceExactLayout, TARGET_CAMERA, type SourceExactLayoutFrame } from "../layout/SourceExactLayout";
import { detectBackend, resolveDpr, type Backend } from "../quality/DeviceProfile";

export type RendererHandle = {
  renderer: WebGPURenderer;
  backend: Backend;
  scene: Scene;
  camera: PerspectiveCamera;
  canvas: HTMLCanvasElement;
};

export class RendererController {
  handle!: RendererHandle;
  viewZoom = 1;
  /** Screen px per world unit on the z = 0 plane, after the responsive law. */
  compositionScale = 1;
  /** Which composition the responsive law should use. */
  composition: CompositionVersion = "v1";
  verticalMode: VerticalMode = "tangent";
  portraitLaw: PortraitLaw = "p1";
  portraitVertical: PortraitVerticalModel = PORTRAIT_VERTICAL.model;
  /** Vertical projection multiplier actually applied this resize. */
  verticalScaleY = 1;
  /**
   * The one layout frame for this viewport, on the source-exact path.
   * Computed here, at resize, and handed to everyone else. Nobody recomputes it.
   */
  frame?: SourceExactLayoutFrame;
  private dprOverride?: number;

  async init(host: HTMLElement, forceWebGL = false): Promise<RendererHandle> {
    const canvas = document.createElement("canvas");
    host.appendChild(canvas);
    const backend = await detectBackend(forceWebGL);
    const renderer = new WebGPURenderer({
      canvas,
      antialias: true,
      alpha: false,
      forceWebGL: backend === "webgl2",
    });
    await renderer.init();

    renderer.setClearColor(new Color(CLEAR_COLOR), 1);
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;

    const camera = new PerspectiveCamera(CAMERA.fov, 1, CAMERA.near, CAMERA.far);
    camera.position.set(0, CAMERA.y, CAMERA.z);
    camera.lookAt(0, CAMERA.lookY, 0);

    const scene = new Scene();
    scene.background = new Color(CLEAR_COLOR);

    this.handle = { renderer, backend, scene, camera, canvas };
    this.resize();
    return this.handle;
  }

  setDpr(value?: number) {
    this.dprOverride = value;
    this.resize();
  }

  resize() {
    if (!this.handle) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const dpr = resolveDpr(this.handle.backend, this.dprOverride);
    this.handle.renderer.setPixelRatio(dpr);
    this.handle.renderer.setSize(width, height, false);
    this.handle.canvas.style.width = "100%";
    this.handle.canvas.style.height = "100%";
    if (isSourceExact(this.composition)) {
      // Source-exact camera, re-asserted every resize because the legacy branch
      // below writes position.z and fov too and would otherwise fight it.
      // The camera stands at the focal distance, on axis, with no pitch: world
      // units are CSS pixels on the z = 0 plane by construction, so there is no
      // composition scale to carry and none is computed.
      const frame = sourceExactLayout(width, height);
      this.frame = frame;
      this.compositionScale = 1;
      this.viewZoom = 1;
      this.verticalScaleY = 1;
      const camera = this.handle.camera;
      camera.position.set(0, 0, frame.perspective);
      camera.lookAt(0, 0, 0);
      camera.aspect = width / Math.max(height, 1);
      camera.fov = (2 * Math.atan(height / 2 / frame.perspective) * 180) / Math.PI;
      camera.near = TARGET_CAMERA.near;
      camera.far = TARGET_CAMERA.far;
      camera.updateProjectionMatrix();
      camera.updateMatrixWorld();
      return;
    }
    this.frame = undefined;
    this.compositionScale = compositionScale(width, height, this.composition, this.verticalMode, this.portraitLaw);
    // portraitLaw MUST reach all three. It used to be passed only to
    // compositionScale, so the reported scale followed the requested law while
    // the camera silently used the default one -- p0 and p1 rendered byte
    // identically and their gate comparison was meaningless.
    this.viewZoom = viewZoom(width, height, this.composition, this.verticalMode, this.portraitLaw);
    // fov is always derived from the effective focal length, so one world unit
    // stays one CSS pixel at z = 0 divided by the composition scale, whichever
    // mechanism the responsive law uses.
    const focal = effectivePerspectivePx(width, height, this.composition, this.verticalMode,
                                         this.portraitLaw);
    // Portrait-only anamorphic Y (F2.7). Vertical screen scale is focal/z and
    // horizontal is (focal/z) * (width/height) / aspect, so raising the focal
    // length by k and the aspect by the same k scales Y alone and leaves X
    // exactly where it was. Doing it here rather than as a scene-root scaleY
    // matters: a non-uniform root scale would perturb vertex normals, and the
    // refraction that reads them is frozen this round.
    const k = verticalScaleY(width, height, this.composition, this.portraitVertical);
    this.verticalScaleY = k;
    this.handle.camera.aspect = (k * width) / height;
    this.handle.camera.fov = (2 * Math.atan(height / 2 / (focal * k)) * 180) / Math.PI;
    this.handle.camera.position.z = CAMERA.z * this.viewZoom;
    this.handle.camera.updateProjectionMatrix();
  }

  render() {
    this.handle.renderer.render(this.handle.scene, this.handle.camera);
  }

  dispose() {
    this.handle.renderer.dispose();
    this.handle.canvas.remove();
  }
}
