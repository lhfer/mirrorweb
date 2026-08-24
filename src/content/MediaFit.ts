import { ClampToEdgeWrapping, type Texture } from "three/webgpu";
import { MAX_MEDIA_ZOOM, MIN_MEDIA_ZOOM } from "./ContentManifest";

/**
 * Aspect-correct fitting of a media source onto a card.
 *
 * Before this module every clip was mapped straight onto the card plane with
 * the default 0..1 UVs, so a 16:9 source was squeezed into a 1.35:1 card: a
 * 24% horizontal compression that no amount of optics tuning can undo. Fitting
 * happens on the texture matrix (repeat/offset), which the media plane's
 * MeshBasicMaterial applies, so nothing about the geometry or the glass changes.
 *
 * `cover` is the shipping mode. `contain` and `stretch` exist only as debug
 * comparisons -- `stretch` is the old, wrong behaviour, kept so a capture can
 * show what was fixed. Neither may ship.
 */

export const MEDIA_FIT_MODES = ["cover", "contain", "stretch"] as const;
export type MediaFitMode = (typeof MEDIA_FIT_MODES)[number];

export type MediaFocus = {
  /** Horizontal focal point of the source, 0 = left edge, 1 = right edge. */
  focusX: number;
  /** Vertical focal point of the source, 0 = TOP edge, 1 = bottom edge. */
  focusY: number;
  /** >= 1. 1 is the tightest crop that still covers the card. */
  zoom: number;
};

export const DEFAULT_FOCUS: MediaFocus = { focusX: 0.5, focusY: 0.5, zoom: 1 };

export type MediaFitResult = {
  mode: MediaFitMode;
  sourceWidth: number;
  sourceHeight: number;
  sourceAspect: number;
  cardAspect: number;
  repeatX: number;
  repeatY: number;
  offsetX: number;
  offsetY: number;
  /** Which axis lost pixels, for the crop preview. "none" for stretch. */
  croppedAxis: "x" | "y" | "none";
  /** Visible fraction of the source, per axis. */
  visibleX: number;
  visibleY: number;
  /**
   * On-card pixels per source pixel, per axis. `cover` and `contain` keep these
   * equal, which is exactly what "a circle stays a circle" means; `stretch`
   * does not.
   */
  scaleX: number;
  scaleY: number;
  aspectErrorPct: number;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function computeMediaFit(
  sourceWidth: number,
  sourceHeight: number,
  cardWidth: number,
  cardHeight: number,
  mode: MediaFitMode = "cover",
  focus: MediaFocus = DEFAULT_FOCUS,
): MediaFitResult {
  const sw = Math.max(1, sourceWidth);
  const sh = Math.max(1, sourceHeight);
  const sourceAspect = sw / sh;
  const cardAspect = Math.max(1e-6, cardWidth / cardHeight);

  let repeatX = 1;
  let repeatY = 1;
  let croppedAxis: MediaFitResult["croppedAxis"] = "none";

  if (mode === "cover") {
    if (sourceAspect > cardAspect) {
      // Source is wider than the card: keep its height, crop left and right.
      repeatX = cardAspect / sourceAspect;
      croppedAxis = "x";
    } else if (sourceAspect < cardAspect) {
      // Source is taller than the card: keep its width, crop top and bottom.
      repeatY = sourceAspect / cardAspect;
      croppedAxis = "y";
    }
    const zoom = clamp(focus.zoom, MIN_MEDIA_ZOOM, MAX_MEDIA_ZOOM);
    repeatX /= zoom;
    repeatY /= zoom;
    if (zoom > 1) croppedAxis = croppedAxis === "none" ? "x" : croppedAxis;
  } else if (mode === "contain") {
    // Letterbox: the whole source is inside the card, so a repeat above 1
    // reaches outside the source. Wrapping is clamp-to-edge, so the bars are
    // edge-smear rather than a solid colour. Debug only.
    if (sourceAspect > cardAspect) repeatY = sourceAspect / cardAspect;
    else if (sourceAspect < cardAspect) repeatX = cardAspect / sourceAspect;
  }

  let offsetX: number;
  let offsetY: number;
  if (mode === "cover") {
    offsetX = clamp(focus.focusX, 0, 1) * (1 - repeatX);
    // three's UV origin is bottom-left; focusY is measured from the top.
    offsetY = (1 - clamp(focus.focusY, 0, 1)) * (1 - repeatY);
  } else {
    offsetX = (1 - repeatX) / 2;
    offsetY = (1 - repeatY) / 2;
  }

  const scaleX = cardWidth / (sw * repeatX);
  const scaleY = cardHeight / (sh * repeatY);
  const aspectErrorPct = (Math.abs(scaleX - scaleY) / Math.max(scaleX, scaleY)) * 100;

  return {
    mode,
    sourceWidth: sw,
    sourceHeight: sh,
    sourceAspect,
    cardAspect,
    repeatX,
    repeatY,
    offsetX,
    offsetY,
    croppedAxis,
    visibleX: repeatX,
    visibleY: repeatY,
    scaleX,
    scaleY,
    aspectErrorPct,
  };
}

export function applyMediaFit(texture: Texture, fit: MediaFitResult): void {
  texture.wrapS = ClampToEdgeWrapping;
  texture.wrapT = ClampToEdgeWrapping;
  texture.center.set(0, 0);
  texture.rotation = 0;
  texture.repeat.set(fit.repeatX, fit.repeatY);
  texture.offset.set(fit.offsetX, fit.offsetY);
  texture.matrixAutoUpdate = true;
  texture.updateMatrix();
  texture.needsUpdate = true;
}

export function readMediaFitMode(search: string = location.search): MediaFitMode {
  const value = new URLSearchParams(search).get("mediafit");
  return (MEDIA_FIT_MODES as readonly string[]).includes(value ?? "")
    ? (value as MediaFitMode)
    : "cover";
}
