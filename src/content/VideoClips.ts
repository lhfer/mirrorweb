import {
  CanvasTexture,
  LinearFilter,
  SRGBColorSpace,
  Texture,
  VideoTexture,
} from "three/webgpu";
import {
  getContentRuntime,
  type ContentMediaBinding,
  type ContentMediaSource,
} from "./ContentRepository";

const MEDIA_READY_TIMEOUT_MS = 12_000;
const POSTER_READY_TIMEOUT_MS = 6_000;
let mediaWarningIssued = false;

type LoadedMediaSource = {
  definition: ContentMediaSource;
  video: HTMLVideoElement;
  playable: boolean;
  poster?: HTMLImageElement;
};

export function getClipBindings(): readonly ContentMediaBinding[] {
  return getContentRuntime().mediaBindings;
}

export function clipFocus(index: number): ContentMediaBinding {
  const bindings = getClipBindings();
  return bindings[((index % bindings.length) + bindings.length) % bindings.length];
}

function attachHiddenVideo(src: string): HTMLVideoElement {
  const video = document.createElement("video");
  video.src = src;
  video.muted = true;
  video.defaultMuted = true;
  video.volume = 0;
  video.loop = true;
  video.autoplay = true;
  video.playsInline = true;
  video.crossOrigin = "anonymous";
  video.setAttribute("playsinline", "");
  video.setAttribute("webkit-playsinline", "");
  video.setAttribute("muted", "");
  video.preload = "auto";
  video.controls = false;
  video.style.cssText =
    "position:fixed;left:-64px;top:-64px;width:16px;height:16px;opacity:0;pointer-events:none";
  document.body.appendChild(video);
  return video;
}

async function waitDecoded(video: HTMLVideoElement): Promise<void> {
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.videoWidth === 0) {
    await new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(
        () => finish(new DOMException("Video readiness timed out", "TimeoutError")),
        MEDIA_READY_TIMEOUT_MS,
      );
      const loaded = () => {
        if (video.videoWidth > 0 && video.videoHeight > 0) finish();
      };
      const failed = () => finish(new Error("Video failed to decode"));
      const finish = (error?: Error) => {
        window.clearTimeout(timeout);
        video.removeEventListener("loadeddata", loaded);
        video.removeEventListener("canplay", loaded);
        video.removeEventListener("error", failed);
        if (error) reject(error);
        else resolve();
      };
      video.addEventListener("loadeddata", loaded);
      video.addEventListener("canplay", loaded);
      video.addEventListener("error", failed, { once: true });
      video.load();
    });
  }

  await video.play().catch(() => undefined);
  if ("requestVideoFrameCallback" in video) {
    await new Promise<void>((resolve) => {
      let callbackId = 0;
      const timeout = window.setTimeout(() => {
        if (callbackId && "cancelVideoFrameCallback" in video) {
          video.cancelVideoFrameCallback(callbackId);
        }
        resolve();
      }, 1_500);
      callbackId = video.requestVideoFrameCallback(() => {
        window.clearTimeout(timeout);
        resolve();
      });
    });
  }
}

async function loadPoster(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    const timeout = window.setTimeout(() => finish(new Error("Poster readiness timed out")),
      POSTER_READY_TIMEOUT_MS);
    const finish = (error?: Error) => {
      window.clearTimeout(timeout);
      image.onload = null;
      image.onerror = null;
      if (error) reject(error);
      else resolve(image);
    };
    image.onload = () => finish();
    image.onerror = () => finish(new Error("Poster failed to load"));
    image.src = src;
  });
}

function safeTextureCanvas(binding: ContentMediaBinding): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 48;
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height);
  gradient.addColorStop(0, binding.fallbackPalette[2]);
  gradient.addColorStop(1, binding.fallbackPalette[3]);
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.globalAlpha = 0.34;
  context.fillStyle = binding.fallbackPalette[1];
  context.fillRect(0, canvas.height * 0.62, canvas.width, canvas.height * 0.38);
  context.globalAlpha = 1;
  return canvas;
}

function configureTexture(texture: Texture, name: string): Texture {
  texture.name = name;
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Owns one DOM video per unique mediaAssetId, while exposing a binding-indexed
 * video array for the frozen V3/V4 callers. Repeated array entries are the same
 * element; the DOM never receives duplicates for repeated card selections.
 */
export class ClipReel {
  readonly videos: HTMLVideoElement[] = [];
  readonly textures: Texture[] = [];
  protected readonly sources: LoadedMediaSource[] = [];
  protected bindings: readonly ContentMediaBinding[] = [];
  private loaded = false;

  async load(onProgress: (value: number) => void): Promise<void> {
    this.bindings = getClipBindings();
    const definitions = getContentRuntime().mediaSources;
    for (let index = 0; index < definitions.length; index += 1) {
      const definition = definitions[index];
      const video = attachHiddenVideo(definition.mediaUrl);
      let playable = false;
      let poster: HTMLImageElement | undefined;
      try {
        await waitDecoded(video);
        playable = true;
      } catch {
        video.pause();
        video.removeAttribute("src");
        video.load();
        video.remove();
        if (definition.posterUrl) {
          try {
            poster = await loadPoster(definition.posterUrl);
          } catch {
            poster = undefined;
          }
        }
      }
      this.sources.push({ definition, video, playable, ...(poster ? { poster } : {}) });
      onProgress(24 + Math.round(((index + 1) / definitions.length) * 60));
    }

    for (const binding of this.bindings) {
      this.videos.push(this.sources[binding.sourceIndex].video);
    }
    this.textures.push(...this.createTextureSet("MirrorWeb.Clip"));
    this.loaded = true;

    if (this.fallbackCount > 0 && !mediaWarningIssued) {
      mediaWarningIssued = true;
      console.warn(
        `[MirrorWeb media] ${this.fallbackCount} card media binding(s) use a poster or safe texture.`,
      );
    }
  }

  createTextureSet(namePrefix: string): Texture[] {
    return this.bindings.map((binding, index) => {
      const source = this.sources[binding.sourceIndex];
      const texture = source.playable
        ? new VideoTexture(source.video)
        : source.poster
          ? new Texture(source.poster)
          : new CanvasTexture(safeTextureCanvas(binding));
      return configureTexture(texture, `${namePrefix}.${index}`);
    });
  }

  dimensionsForBinding(index: number): readonly [number, number] {
    const binding = this.bindings[index];
    const source = binding ? this.sources[binding.sourceIndex] : undefined;
    if (source?.playable) return [source.video.videoWidth, source.video.videoHeight];
    if (source?.poster) return [source.poster.naturalWidth, source.poster.naturalHeight];
    return [64, 48];
  }

  isFallbackBinding(index: number): boolean {
    const binding = this.bindings[index];
    return binding ? !this.sources[binding.sourceIndex]?.playable : true;
  }

  get uniqueVideoElements(): readonly HTMLVideoElement[] {
    return this.sources.filter((source) => source.playable).map((source) => source.video);
  }

  get uniqueVideoCount(): number {
    return this.sources.filter((source) => source.playable).length;
  }

  get fallbackCount(): number {
    let count = 0;
    for (let index = 0; index < this.bindings.length; index += 1) {
      if (this.isFallbackBinding(index)) count += 1;
    }
    return count;
  }

  seek(seconds: number): void {
    for (const source of this.sources) {
      const video = source.video;
      if (source.playable && video.duration && Number.isFinite(video.duration)) {
        video.currentTime = ((seconds % video.duration) + video.duration) % video.duration;
      }
    }
  }

  unlock(): void {
    for (const source of this.sources) {
      if (!source.playable) continue;
      source.video.muted = true;
      source.video.volume = 0;
      void source.video.play().catch(() => undefined);
    }
  }

  pause(): void {
    for (const source of this.sources) source.video.pause();
  }

  resume(): void {
    this.unlock();
  }

  update(): void {
    for (const texture of this.textures) {
      if (texture instanceof VideoTexture) texture.update();
    }
  }

  get ready(): boolean {
    return this.loaded && this.textures.length === this.bindings.length;
  }

  dispose(): void {
    for (const source of this.sources) {
      const video = source.video;
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
    }
    for (const texture of this.textures) texture.dispose();
    this.sources.length = 0;
    this.videos.length = 0;
    this.textures.length = 0;
    this.bindings = [];
    this.loaded = false;
  }
}

export async function loadClipTextures(onProgress: (value: number) => void): Promise<ClipReel> {
  const reel = new ClipReel();
  await reel.load(onProgress);
  return reel;
}

export function unlockClipPlayback(reel: { unlock?: () => void } | undefined): void {
  reel?.unlock?.();
}
