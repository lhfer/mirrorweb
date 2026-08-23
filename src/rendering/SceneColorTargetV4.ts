import {
  HalfFloatType,
  LinearFilter,
  LinearMipmapLinearFilter,
  LinearSRGBColorSpace,
  RGBAFormat,
  RenderTarget,
  type Texture,
} from "three/webgpu";
import { V4_OPTICS_CONFIG, type V4QualityLevel } from "../v4/OpticsConfigV4";

export type SceneColorTargetV4Description = {
  version: "v4";
  quality: V4QualityLevel;
  scale: number;
  width: number;
  height: number;
  type: number;
  typeName: "HalfFloatType";
  colorSpace: string;
  generateMipmaps: boolean;
  depthBuffer: boolean;
};

/**
 * Linear HDR scene-color storage for V4 optics.
 *
 * Three r185 automatically disables tone mapping and uses the working color
 * space for non-output render targets. The explicit LinearSRGB metadata keeps
 * subsequent TSL samples in that same linear working space.
 */
export class SceneColorTargetV4 {
  readonly target = new RenderTarget(1, 1, {
    type: HalfFloatType,
    format: RGBAFormat,
    colorSpace: LinearSRGBColorSpace,
    minFilter: LinearMipmapLinearFilter,
    magFilter: LinearFilter,
    generateMipmaps: true,
    depthBuffer: true,
    stencilBuffer: false,
    samples: 0,
  });

  private _quality: V4QualityLevel;
  private cssWidth = 1;
  private cssHeight = 1;
  private dpr = 1;

  constructor(quality: V4QualityLevel = "high") {
    this._quality = quality;
    this.target.texture.name = "MirrorWeb.V4.SceneColor.LinearHalfFloat";
  }

  get texture(): Texture {
    return this.target.texture;
  }

  get quality(): V4QualityLevel {
    return this._quality;
  }

  get scale(): number {
    return V4_OPTICS_CONFIG.sceneTarget.resolutionScale[this._quality];
  }

  resize(cssWidth: number, cssHeight: number, dpr: number): boolean {
    this.cssWidth = Math.max(1, cssWidth);
    this.cssHeight = Math.max(1, cssHeight);
    this.dpr = Math.max(0.25, dpr);
    const width = Math.max(1, Math.floor(this.cssWidth * this.dpr * this.scale));
    const height = Math.max(1, Math.floor(this.cssHeight * this.dpr * this.scale));
    if (width === this.target.width && height === this.target.height) return false;
    this.target.setSize(width, height);
    return true;
  }

  setQuality(level: V4QualityLevel): boolean {
    if (level === this._quality) return false;
    this._quality = level;
    return this.resize(this.cssWidth, this.cssHeight, this.dpr);
  }

  describe(): SceneColorTargetV4Description {
    return {
      version: "v4",
      quality: this._quality,
      scale: this.scale,
      width: this.target.width,
      height: this.target.height,
      type: this.target.texture.type,
      typeName: "HalfFloatType",
      colorSpace: this.target.texture.colorSpace,
      generateMipmaps: this.target.texture.generateMipmaps,
      depthBuffer: this.target.depthBuffer,
    };
  }

  dispose(): void {
    this.target.dispose();
  }
}
