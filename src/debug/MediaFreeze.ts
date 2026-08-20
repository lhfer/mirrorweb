/**
 * QA-only media time freeze.
 *
 * Capture fairness needs every video to sit on the same decoded frame on both
 * sides of a comparison. `seek()` alone cannot do that: the clips are
 * `autoplay loop`, so setting `currentTime` on a playing video only nudges a
 * timeline that immediately keeps running, and two captures taken seconds apart
 * land on different frames. That is what made states drop out of the blind
 * batches with a V3-vs-V3 correlation as low as 0.21.
 *
 * Nothing here runs unless a QA caller invokes it. The module is imported only
 * by the two QA hook sites, and it touches the video elements the page already
 * owns; it adds no render-loop work and no behaviour to a normal preview.
 */

export type FrozenVideoReport = {
  index: number;
  requestedTime: number;
  currentTime: number;
  /** rVFC metadata: the presentation timestamp of the decoded frame, if one arrived. */
  mediaTime: number | null;
  /** rVFC metadata: frames presented since the element was created. */
  presentedFrames: number | null;
  readyState: number;
  paused: boolean;
  videoWidth: number;
  videoHeight: number;
  /** How the frame wait ended. `timeout` and `unsupported` are not failures on their own. */
  frameWait: "presented" | "timeout" | "unsupported";
  seekError: number;
  /** Frame index this media time belongs to, at the nominal clip rate. */
  wantedFrame?: number;
  /** Frame index the decoder actually presented. */
  landedFrame?: number | null;
  frameAttempts?: number;
  /** The claim that matters for fairness: the intended frame is on screen. */
  frameMatched?: boolean;
};

export type FreezeReport = {
  requestedTime: number;
  videos: FrozenVideoReport[];
  /** Largest |currentTime - requestedTime| across clips, in seconds. */
  maxSeekError: number;
  /** Largest currentTime movement observed over the settle window, in seconds. */
  maxDrift: number;
  driftWindowMs: number;
  allPaused: boolean;
  /** Every clip presented the frame its media time belongs to. */
  allFramesMatched: boolean;
  /** True only when every clip is paused, on time, and stayed there. */
  frozen: boolean;
  thresholds: { seekError: number; drift: number };
};

const NOMINAL_FPS = 30;
const FRAME_RETRIES = 4;
const SEEK_TOLERANCE = 1 / 60;
const DRIFT_TOLERANCE = 1 / 120;
const FRAME_TIMEOUT_MS = 1500;
const SEEK_TIMEOUT_MS = 3000;
const DRIFT_WINDOW_MS = 500;

type FrameMeta = { mediaTime: number; presentedFrames: number };

function nextPresentedFrame(video: HTMLVideoElement): Promise<FrameMeta | null> {
  if (!("requestVideoFrameCallback" in video)) return Promise.resolve(null);
  return new Promise((resolve) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      resolve(null);
    }, FRAME_TIMEOUT_MS);
    video.requestVideoFrameCallback((_now, metadata) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ mediaTime: metadata.mediaTime, presentedFrames: metadata.presentedFrames });
    });
  });
}

function seeked(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      video.removeEventListener("seeked", finish);
      resolve();
    };
    const timer = setTimeout(finish, SEEK_TIMEOUT_MS);
    video.addEventListener("seeked", finish, { once: true });
  });
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Target time wrapped into the clip's own duration, so every clip gets the same phase. */
function wrap(video: HTMLVideoElement, seconds: number): number {
  const duration = video.duration;
  if (!duration || !Number.isFinite(duration)) return Math.max(0, seconds);
  return ((seconds % duration) + duration) % duration;
}

/**
 * Seek once and report which frame actually got presented.
 *
 * Pinning `currentTime` is not enough on its own: the decoder can present a
 * neighbouring frame for the same requested time, and two processes then render
 * different media while both truthfully report the same currentTime. That is
 * why a fairness run could score 13/13 once and 7/13 the next time.
 */
async function seekOnce(video: HTMLVideoElement, target: number) {
  const frame = nextPresentedFrame(video);
  const settle = seeked(video);
  video.currentTime = target;
  await settle;
  const meta = await frame;
  video.pause();
  return meta;
}

export async function freezeMediaTime(
  videos: HTMLVideoElement[],
  seconds: number,
): Promise<FreezeReport> {
  for (const video of videos) video.pause();

  const reports: FrozenVideoReport[] = [];
  for (const [index, video] of videos.entries()) {
    const target = wrap(video, seconds);
    const wantFrame = Math.round(target * NOMINAL_FPS);
    let meta = await seekOnce(video, target);
    let attempts = 1;
    // Nudge back and seek forward again if the decoder presented a frame that
    // does not belong to this media time. This is a best-effort stabiliser at
    // the nominal rate, not a gate: see allFramesMatched below.
    while (
      meta && Math.round(meta.mediaTime * NOMINAL_FPS) !== wantFrame
      && attempts < FRAME_RETRIES
    ) {
      await seekOnce(video, wrap(video, target - 2 / NOMINAL_FPS));
      meta = await seekOnce(video, target);
      attempts += 1;
    }
    const landedFrame = meta ? Math.round(meta.mediaTime * NOMINAL_FPS) : null;
    reports.push({
      index,
      requestedTime: target,
      currentTime: video.currentTime,
      mediaTime: meta ? meta.mediaTime : null,
      presentedFrames: meta ? meta.presentedFrames : null,
      readyState: video.readyState,
      paused: video.paused,
      videoWidth: video.videoWidth,
      videoHeight: video.videoHeight,
      frameWait: meta
        ? "presented"
        : ("requestVideoFrameCallback" in video ? "timeout" : "unsupported"),
      seekError: Math.abs(video.currentTime - target),
      wantedFrame: wantFrame,
      landedFrame,
      frameAttempts: attempts,
      frameMatched: landedFrame === wantFrame,
    });
  }

  // Confirm the timeline actually stopped rather than merely being paused once.
  const before = videos.map((video) => video.currentTime);
  await wait(DRIFT_WINDOW_MS);
  let maxDrift = 0;
  for (const [index, video] of videos.entries()) {
    maxDrift = Math.max(maxDrift, Math.abs(video.currentTime - before[index]));
    if (!video.paused) video.pause();
  }

  const maxSeekError = reports.reduce((worst, r) => Math.max(worst, r.seekError), 0);
  const allPaused = reports.every((r) => r.paused) && videos.every((video) => video.paused);
  const allFramesMatched = reports.every((r) => r.frameMatched === true);
  return {
    requestedTime: seconds,
    videos: reports,
    maxSeekError,
    maxDrift,
    driftWindowMs: DRIFT_WINDOW_MS,
    allPaused,
    // Reported, not gated. `wantedFrame` assumes a nominal 30 fps for every
    // clip, and the clips are not all 30 fps - observed presented mediaTimes
    // include 1.708 and 1.6, which are not multiples of 1/30. Gating on it
    // would reject a perfectly frozen capture. What actually proves two
    // captures share a frame is media-only hash equality between them, which
    // the fairness report checks directly.
    allFramesMatched,
    frozen: allPaused && maxSeekError <= SEEK_TOLERANCE && maxDrift <= DRIFT_TOLERANCE,
    thresholds: { seekError: SEEK_TOLERANCE, drift: DRIFT_TOLERANCE },
  };
}

export type MediaSnapshot = {
  index: number;
  currentTime: number;
  readyState: number;
  paused: boolean;
  videoWidth: number;
  videoHeight: number;
};

/**
 * Read-only snapshot, for proving the freeze still holds at capture time.
 *
 * Deliberately narrower than FrozenVideoReport. An earlier version reused that
 * shape and filled `frameWait: "presented"` and `seekError: 0` as constants,
 * which made a caller believe the snapshot had verified a decoded frame when it
 * had verified nothing of the sort. Only what can actually be read here is
 * returned.
 */
export function readMediaState(videos: HTMLVideoElement[]): MediaSnapshot[] {
  return videos.map((video, index) => ({
    index,
    currentTime: video.currentTime,
    readyState: video.readyState,
    paused: video.paused,
    videoWidth: video.videoWidth,
    videoHeight: video.videoHeight,
  }));
}
