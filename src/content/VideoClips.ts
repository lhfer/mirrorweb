import { LinearFilter, SRGBColorSpace, VideoTexture } from "three/webgpu";

/**
 * `focusX` / `focusY` / `zoom` drive MediaFit's cover crop. All three sources
 * are 16:9-ish and the card is ~1.35:1, so cover crops left and right; the
 * focus point decides which part of the frame survives. 0.5/0.5/1 is a centred,
 * tightest-possible crop.
 */
export const CLIPS = [
  {
    src: "/clips/niulai-intro.mp4",
    code: "NL—01",
    category: "GAME INTRO",
    title: "牛来开场",
    deck: "开场封面动画，截取约 5 秒。",
    accent: "#ffcc66",
    focusX: 0.5,
    focusY: 0.5,
    zoom: 1,
  },
  {
    src: "/clips/cursor-niulai.mp4",
    code: "NL—02",
    category: "STUDIO CLIP",
    title: "Cursor 牛来",
    deck: "Cursor 里的牛来片段，截取约 5 秒。",
    accent: "#8ff7ff",
    focusX: 0.5,
    focusY: 0.5,
    zoom: 1,
  },
  {
    src: "/clips/pelican-ai.mp4",
    code: "NL—03",
    category: "FIELD TEST",
    title: "鹈鹕测 AI",
    deck: "无 BGM 版，从 15 秒起截取 5 秒。",
    accent: "#ff9ad5",
    // Product review, 2026-08-20: nudge the crop up slightly and tighten it.
    // zoom 1.06 still MINIFIES the source (1.275 source px per card px, down
    // from 1.351), so it cannot introduce magnification blur.
    focusX: 0.5,
    focusY: 0.46,
    zoom: 1.06,
  },
] as const;

export function clipFocus(index: number) {
  const clip = CLIPS[index % CLIPS.length];
  return { focusX: clip.focusX, focusY: clip.focusY, zoom: clip.zoom };
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
  video.style.cssText = "position:fixed;left:-64px;top:-64px;width:16px;height:16px;opacity:0;pointer-events:none";
  document.body.appendChild(video);
  return video;
}

async function waitDecoded(video: HTMLVideoElement) {
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

export class ClipReel {
  readonly videos: HTMLVideoElement[] = [];
  readonly textures: VideoTexture[] = [];

  async load(onProgress: (value: number) => void) {
    for (let i = 0; i < CLIPS.length; i += 1) {
      const video = attachHiddenVideo(CLIPS[i].src);
      await waitDecoded(video);
      const texture = new VideoTexture(video);
      texture.colorSpace = SRGBColorSpace;
      texture.minFilter = LinearFilter;
      texture.magFilter = LinearFilter;
      texture.generateMipmaps = false;
      texture.needsUpdate = true;
      this.videos.push(video);
      this.textures.push(texture);
      onProgress(24 + Math.round(((i + 1) / CLIPS.length) * 60));
    }
  }

  seek(seconds: number) {
    for (const video of this.videos) {
      if (video.duration && Number.isFinite(video.duration)) {
        video.currentTime = ((seconds % video.duration) + video.duration) % video.duration;
      }
    }
  }

  unlock() {
    for (const video of this.videos) {
      video.muted = true;
      video.volume = 0;
      void video.play().catch(() => undefined);
    }
  }

  update() {
    for (const texture of this.textures) texture.update();
  }

  get ready() {
    return this.videos.length === CLIPS.length && this.videos.every((video) => video.readyState >= 2 && video.videoWidth > 0);
  }

  dispose() {
    for (const video of this.videos) {
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
    }
    for (const texture of this.textures) texture.dispose();
    this.videos.length = 0;
    this.textures.length = 0;
  }
}

export async function loadClipTextures(onProgress: (value: number) => void) {
  const reel = new ClipReel();
  await reel.load(onProgress);
  return reel;
}

export function unlockClipPlayback(reel: { unlock?: () => void } | undefined) {
  reel?.unlock?.();
}
