import type { QualityLevel } from "../config";
import type { App } from "../app/App";

export type LiquidGlassQA = {
  pause: () => void;
  resume: () => void;
  setTime: (seconds: number) => void;
  setOffset: (x: number, y: number) => void;
  setVelocity: (x: number, y: number) => void;
  setQuality: (level: QualityLevel) => void;
  setDpr: (value: number) => void;
  setPointer: (x: number, y: number) => void;
  getState: () => Record<string, unknown>;
  getMetrics: () => Record<string, unknown>;
  getAssetState: () => Record<string, unknown>;
  getPoolState: () => Record<string, unknown>;
  reset: () => void;
};

export function installQAHooks(app: App) {
  const enabled = import.meta.env.DEV || new URLSearchParams(location.search).has("qa");
  if (!enabled) return;
  const api: LiquidGlassQA = {
    pause: () => app.pause(),
    resume: () => app.resume(),
    setTime: (seconds) => app.setTime(seconds),
    setOffset: (x, y) => app.setOffset(x, y),
    setVelocity: (x, y) => app.setVelocity(x, y),
    setQuality: (level) => app.setQuality(level),
    setDpr: (value) => app.setDpr(value),
    setPointer: (x, y) => app.setPointer(x, y),
    getState: () => app.getState(),
    getMetrics: () => app.getMetrics(),
    getAssetState: () => app.getAssetState(),
    getPoolState: () => app.getPoolState(),
    reset: () => app.reset(),
  };
  const host = window as Window & {
    __LIQUID_GLASS_QA__?: LiquidGlassQA;
    __ILG_QA__?: LiquidGlassQA;
  };
  host.__LIQUID_GLASS_QA__ = api;
  host.__ILG_QA__ = api;
}
