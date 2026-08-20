import type { QualityLevel } from "../../config";
import type { MediaFitMode } from "../../content/MediaFit";
import { V4_DEBUG_MODES, V4_SHELL_MODES, type V4DebugMode, type V4ShellMode } from "../OpticsConfigV4";
import { GridAppV4, type GridAppV4Options } from "./GridAppV4";

export type GridQaV4 = {
  pause: () => void;
  resume: () => void;
  setTime: (seconds: number) => void;
  setMediaTimeAndFreeze: (seconds: number) => Promise<unknown>;
  getMediaState: () => unknown;
  setRenderLayers: (layers: { glass?: boolean; media?: boolean; labels?: boolean }) => void;
  setOffset: (x: number, y: number) => void;
  setVelocity: (x: number, y: number) => void;
  setQuality: (level: QualityLevel) => void;
  /** QA only: pause the adaptive sampler so a level sweep can be held still. */
  setAdaptiveQuality: (enabled: boolean) => void;
  getAdaptiveState: () => Record<string, unknown>;
  setDpr: (value: number) => void;
  /**
   * Draw one frame now. QA calls this after any state change so a paused page
   * yields a fresh canvas synchronously instead of waiting for a frame.
   */
  renderOnce: () => number;
  /** Monotonic count of frames drawn through `renderOnce`. */
  getRenderStamp: () => number;
  setPointer: (x: number, y: number) => void;
  setDebugMode: (mode: V4DebugMode) => void;
  setShellMode: (mode: V4ShellMode) => void;
  setMediaFitMode: (mode: MediaFitMode) => void;
  getMediaFits: () => unknown;
  getState: () => Record<string, unknown>;
  getV4State: () => Record<string, unknown>;
  getCardQuads: () => Array<{ i: number; j: number; slotIndex: number; quad: number[][] }>;
  /** Source-exact per-slot engine truth, for the source-contract gate. */
  getSourceExactSlots: () => Array<Record<string, unknown>>;
  /** The real glass mesh bounding box, scale and projected corners. */
  getGlassMeshTruth: () => Record<string, unknown>;
  /** Which render layers are actually visible, read off the scene. */
  getRenderLayerState: () => Record<string, unknown>;
  getMetrics: () => Record<string, unknown>;
  getAssetState: () => Record<string, unknown>;
  getPoolState: () => Record<string, unknown>;
  reset: () => void;
};

export function parseV4DebugMode(value: string | null): V4DebugMode {
  return V4_DEBUG_MODES.includes(value as V4DebugMode) ? (value as V4DebugMode) : "beauty";
}

export function parseV4ShellMode(value: string | null): V4ShellMode {
  return V4_SHELL_MODES.includes(value as V4ShellMode) ? (value as V4ShellMode) : "energy-controlled";
}

/**
 * Boots the V4 multi-card preview and publishes the same QA surface the V3 app
 * exposes, so one capture harness can drive both optical versions through the
 * identical review states.
 */
export async function startGridPreviewV4(options: GridAppV4Options = {}): Promise<GridAppV4> {
  const query = new URLSearchParams(location.search);
  const overscanQuery = Number(query.get("overscan"));
  const app = new GridAppV4({
    debugMode: parseV4DebugMode(query.get("v4debug")),
    shellMode: parseV4ShellMode(query.get("shell")),
    ...(Number.isFinite(overscanQuery) && overscanQuery >= 1 ? { overscan: overscanQuery } : {}),
    ...options,
  });
  await app.start();

  const enabled = import.meta.env.DEV || query.has("qa");
  if (enabled) {
    const api: GridQaV4 = {
      pause: () => app.pause(),
      resume: () => app.resume(),
      setTime: (seconds) => app.setTime(seconds),
      setMediaTimeAndFreeze: (seconds) => app.setMediaTimeAndFreeze(seconds),
      getMediaState: () => app.getMediaState(),
      setRenderLayers: (layers) => app.setRenderLayers(layers),
      setOffset: (x, y) => app.setOffset(x, y),
      setVelocity: (x, y) => app.setVelocity(x, y),
      setQuality: (level) => app.setQuality(level),
      setAdaptiveQuality: (enabled) => app.setAdaptiveQuality(enabled),
      getAdaptiveState: () => app.getAdaptiveState(),
      setDpr: (value) => app.setDpr(value),
      renderOnce: () => app.renderOnce(),
      getRenderStamp: () => app.getRenderStamp(),
      setPointer: (x, y) => app.setPointer(x, y),
      setDebugMode: (mode) => app.setDebugMode(mode),
      setShellMode: (mode) => app.setShellMode(mode),
      setMediaFitMode: (mode) => app.setMediaFitMode(mode),
      getMediaFits: () => app.getMediaFits(),
      getState: () => app.getState(),
      getV4State: () => app.getV4State(),
      getCardQuads: () => app.getCardQuads(),
      getSourceExactSlots: () => app.getSourceExactSlots(),
      getGlassMeshTruth: () => app.getGlassMeshTruth(),
      getRenderLayerState: () => app.getRenderLayerState(),
      getMetrics: () => app.getMetrics(),
      getAssetState: () => app.getAssetState(),
      getPoolState: () => app.getPoolState(),
      reset: () => app.reset(),
    };
    const host = window as Window & {
      __ILG_QA__?: GridQaV4;
      __LIQUID_GLASS_QA__?: GridQaV4;
      __ILG_V4_GRID_QA__?: GridQaV4;
    };
    host.__ILG_QA__ = api;
    host.__LIQUID_GLASS_QA__ = api;
    host.__ILG_V4_GRID_QA__ = api;
  }
  document.body.dataset.optics = "v4";
  return app;
}
