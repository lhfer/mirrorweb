import { AdapterError, CONTENT_LIMITS, type PreparedMedia } from "./domain";

function once(target: EventTarget, event: string, errorEvent = "error"): Promise<void> {
  return new Promise((resolve, reject) => {
    const done = () => {
      cleanup();
      resolve();
    };
    const fail = () => {
      cleanup();
      reject(new AdapterError("validation", "无法读取该 MP4 的视频信息"));
    };
    const cleanup = () => {
      target.removeEventListener(event, done);
      target.removeEventListener(errorEvent, fail);
    };
    target.addEventListener(event, done, { once: true });
    target.addEventListener(errorEvent, fail, { once: true });
  });
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function prepareMedia(file: File): Promise<PreparedMedia> {
  if (!file.name.toLocaleLowerCase().endsWith(".mp4")) {
    throw new AdapterError("validation", "仅接受扩展名为 .mp4 的文件");
  }
  if (file.type !== "video/mp4") {
    throw new AdapterError("validation", `MIME 必须是 video/mp4，当前为 ${file.type || "unknown"}`);
  }
  if (file.size > CONTENT_LIMITS.maxMediaBytes) {
    throw new AdapterError("validation", "视频超过默认 100 MB 上限");
  }
  if (file.size === 0) throw new AdapterError("validation", "视频文件为空");

  const objectUrl = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.preload = "metadata";
  video.muted = true;
  video.playsInline = true;
  video.src = objectUrl;

  try {
    video.load();
    await once(video, "loadedmetadata");
    if (!video.videoWidth || !video.videoHeight || !Number.isFinite(video.duration) || video.duration <= 0) {
      throw new AdapterError("validation", "视频缺少有效的宽、高或时长信息");
    }

    const seekTime = Math.min(Math.max(video.duration * 0.1, 0.05), Math.max(video.duration - 0.05, 0.05));
    video.currentTime = seekTime;
    await once(video, "seeked");

    const maxPosterWidth = 1280;
    const scale = Math.min(1, maxPosterWidth / video.videoWidth);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) throw new AdapterError("validation", "浏览器无法生成 Poster");
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const poster = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) => blob ? resolve(blob) : reject(new AdapterError("validation", "Poster 编码失败")),
        "image/jpeg",
        0.86,
      );
    });

    const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return {
      file,
      poster,
      width: video.videoWidth,
      height: video.videoHeight,
      durationMs: Math.round(video.duration * 1000),
      sha256: toHex(hash),
    };
  } finally {
    video.pause();
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(objectUrl);
  }
}
