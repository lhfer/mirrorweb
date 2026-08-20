import {
  ACESFilmicToneMapping,
  Color,
  PerspectiveCamera,
  Scene,
  WebGPURenderer,
} from "three/webgpu";
import { CAMERA, CLEAR_COLOR, compositionScale, effectivePerspectivePx, viewZoom } from "../config";
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
  /** Screen px per world unit on the z = 0 plane, after the F2 responsive law. */
  compositionScale = 1;
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
    this.compositionScale = compositionScale(width, height);
    this.viewZoom = viewZoom(width, height);
    this.handle.camera.aspect = width / height;
    // fov is always derived from the effective focal length, so one world unit
    // stays one CSS pixel at z = 0 divided by the composition scale, whichever
    // mechanism the responsive law uses.
    const focal = effectivePerspectivePx(width, height);
    this.handle.camera.fov = (2 * Math.atan(height / 2 / focal) * 180) / Math.PI;
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
