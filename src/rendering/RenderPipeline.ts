import { ACESFilmicToneMapping, NoToneMapping, RenderTarget, SRGBColorSpace } from "three/webgpu";
import type { InfiniteGlassGrid } from "../scene/InfiniteGlassGrid";
import type { RendererController } from "./RendererController";
import type { TileLabelLayer } from "../ui/TileLabelLayer";

export class RenderPipeline {
  readonly target = new RenderTarget(1, 1, {
    colorSpace: SRGBColorSpace,
    depthBuffer: true,
  });

  constructor(
    private readonly renderer: RendererController,
    private readonly labels: TileLabelLayer,
    private readonly grid: InfiniteGlassGrid,
  ) {}

  get sceneTexture() {
    return this.target.texture;
  }

  resize() {
    const width = Math.max(1, Math.floor(window.innerWidth * this.renderer.handle.renderer.getPixelRatio()));
    const height = Math.max(1, Math.floor(window.innerHeight * this.renderer.handle.renderer.getPixelRatio()));
    this.target.setSize(width, height);
  }

  draw() {
    const { renderer, scene, camera } = this.renderer.handle;
    if (this.grid.needsBackgroundPass) {
      this.grid.setGlassVisible(false);
      this.grid.setMediaVisible(true);
      renderer.toneMapping = NoToneMapping;
      renderer.setRenderTarget(this.target);
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.toneMapping = ACESFilmicToneMapping;
      this.grid.setGlassVisible(true);
      this.grid.setMediaVisible(false);
    }
    renderer.render(scene, camera);
    this.labels.render(camera);
  }

  dispose() {
    this.target.dispose();
  }
}
