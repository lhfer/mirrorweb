import { ClipReel } from "../../content/VideoClips";

/**
 * V4 shares the manifest-driven media pool with V3. The pool creates one DOM
 * video per unique media asset and one texture per unique card crop binding.
 * V4 adds only its decoded-frame counter; texture uploads remain driven by
 * requestVideoFrameCallback inside three's VideoTexture.
 */
export class ClipReelV4 extends ClipReel {
  private frameCallbacks = 0;
  private callbackIds: number[] = [];

  override async load(onProgress: (value: number) => void): Promise<void> {
    await super.load(onProgress);
    for (const video of this.uniqueVideoElements) this.countFrames(video);
  }

  /** Decoded video frames observed since load; the upload driver for V4. */
  get videoFrames(): number {
    return this.frameCallbacks;
  }

  get usesFrameCallback(): boolean {
    return this.uniqueVideoElements.every((video) => "requestVideoFrameCallback" in video);
  }

  override dispose(): void {
    const videos = this.uniqueVideoElements;
    for (const [index, video] of videos.entries()) {
      const id = this.callbackIds[index];
      if (id && "cancelVideoFrameCallback" in video) video.cancelVideoFrameCallback(id);
    }
    this.callbackIds.length = 0;
    super.dispose();
  }

  private countFrames(video: HTMLVideoElement): void {
    if (!("requestVideoFrameCallback" in video)) return;
    const index = this.uniqueVideoElements.indexOf(video);
    const tick = () => {
      this.frameCallbacks += 1;
      this.callbackIds[index] = video.requestVideoFrameCallback(tick);
    };
    this.callbackIds[index] = video.requestVideoFrameCallback(tick);
  }
}
