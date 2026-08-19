export type Backend = "webgpu" | "webgl2";

export function isMobileViewport(width = window.innerWidth): boolean {
  return width <= 844 || ("ontouchstart" in window && width < 1100);
}

export function resolveDpr(backend: Backend, override?: number): number {
  if (override && override > 0) return override;
  const raw = window.devicePixelRatio || 1;
  if (isMobileViewport()) return Math.min(raw, 1.5);
  return Math.min(raw, backend === "webgpu" ? 2 : 1.5);
}

export async function detectBackend(forceWebGL = false): Promise<Backend> {
  if (forceWebGL || !("gpu" in navigator)) return "webgl2";
  try {
    const adapter = await navigator.gpu!.requestAdapter();
    if (!adapter) return "webgl2";
    const info = adapter.info;
    const desc = `${info?.vendor ?? ""} ${info?.architecture ?? ""} ${info?.description ?? ""}`.toLowerCase();
    if (desc.includes("swiftshader") || desc.includes("llvmpipe") || adapter.isFallbackAdapter) {
      return "webgl2";
    }
    return "webgpu";
  } catch {
    return "webgl2";
  }
}
