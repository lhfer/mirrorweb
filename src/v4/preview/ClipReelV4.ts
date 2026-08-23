import { LinearFilter, SRGBColorSpace, VideoTexture } from "three/webgpu";
import { CLIPS } from "../../content/VideoClips";

/**
 * The same three production clips as V3, uploaded on video frames instead of
 * on render frames.
 *
 * three's VideoTexture already registers requestVideoFrameCallback and marks
 * itself dirty only when a new frame decodes. V3 additionally calls
 * `texture.update()` on every rAF; this reel deliberately never does, and it
 * counts decoded frames so the Round 1 gate can prove that texture uploads are
 * driven by the video and not by the render loop.
 */
export class ClipReelV4 {
  readonly videos: HTMLVideoElement[] = [];
  readonly textures: VideoTexture[] = [];
  private frameCallbacks = 0;
  private callbackIds: number[] = [];

  async load(onProgress: (value: number) => void): Promise<void> {
    for (let index = 0; index < CLIPS.length; index += 1) {
      const video = this.attach(CLIPS[index].src);
      await this.waitDecoded(video);
      const texture = new VideoTexture(video);
      texture.name = `MirrorWeb.V4.Clip.${index}`;
      texture.colorSpace = SRGBColorSpace;
      texture.minFilter = LinearFilter;
      texture.magFilter = LinearFilter;
      texture.generateMipmaps = false;
      this.videos.push(video);
      this.textures.push(texture);
      this.countFrames(video);
      onProgress(24 + Math.round(((index + 1) / CLIPS.length) * 60));
    }
  }

  /** Decoded video frames observed since load; the upload driver for V4. */
  get videoFrames(): number {
    return this.frameCallbacks;
  }

  get ready(): boolean {
    return this.videos.length === CLIPS.length
      && this.videos.every((video) => video.readyState >= 2 && video.videoWidth > 0);
  }

  get usesFrameCallback(): boolean {
    return this.videos.every((video) => "requestVideoFrameCallback" in video);
  }

  seek(seconds: number): void {
    for (const video of this.videos) {
      if (video.duration && Number.isFinite(video.duration)) {
        video.currentTime = ((seconds % video.duration) + video.duration) % video.duration;
      }
    }
  }

  unlock(): void {
    for (const video of this.videos) {
      video.muted = true;
      video.volume = 0;
      void video.play().catch(() => undefined);
    }
  }

  pause(): void {
    for (const video of this.videos) video.pause();
  }

  resume(): void {
    this.unlock();
  }

  dispose(): void {
    for (const [index, video] of this.videos.entries()) {
      const id = this.callbackIds[index];
      if (id && "cancelVideoFrameCallback" in video) video.cancelVideoFrameCallback(id);
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
    }
    for (const texture of this.textures) texture.dispose();
    this.videos.length = 0;
    this.textures.length = 0;
    this.callbackIds.length = 0;
  }

  private countFrames(video: HTMLVideoElement): void {
    if (!("requestVideoFrameCallback" in video)) return;
    const index = this.videos.indexOf(video);
    const tick = () => {
      this.frameCallbacks += 1;
      this.callbackIds[index] = video.requestVideoFrameCallback(tick);
    };
    this.callbackIds[index] = video.requestVideoFrameCallback(tick);
  }

  private attach(src: string): HTMLVideoElement {
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

  private async waitDecoded(video: HTMLVideoElement): Promise<void> {
    if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA || video.videoWidth === 0) {
      await new Promise<void>((resolve, reject) => {
        const finish = () => {
          cleanup();
          resolve();
        };
        const fail = () => {
          cleanup();
          reject(new Error(`clip failed: ${video.src}`));
        };
        const cleanup = () => {
          video.removeEventListener("loadeddata", finish);
          video.removeEventListener("canplay", finish);
          video.removeEventListener("error", fail);
        };
        video.addEventListener("loadeddata", finish, { once: true });
        video.addEventListener("canplay", finish, { once: true });
        video.addEventListener("error", fail, { once: true });
        video.load();
      });
    }
    await video.play().catch(() => undefined);
    if ("requestVideoFrameCallback" in video) {
      await new Promise<void>((resolve) => {
        video.requestVideoFrameCallback(() => resolve());
      });
    }
  }
}
