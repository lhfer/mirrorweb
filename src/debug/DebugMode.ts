export const LAYOUT_DEBUG = ["coverage", "geometry", "pool"] as const;
export const GLASS_DEBUG = ["normals", "thickness", "refraction", "fresnel", "dispersion", "media", "typography"] as const;

export type LayoutDebugMode = (typeof LAYOUT_DEBUG)[number];
export type GlassDebugMode = (typeof GLASS_DEBUG)[number];
export type DebugMode = "off" | LayoutDebugMode | GlassDebugMode;

export function readDebugMode(search = location.search): DebugMode {
  const value = new URLSearchParams(search).get("debug");
  if (!value) return "off";
  if ((LAYOUT_DEBUG as readonly string[]).includes(value)) return value as LayoutDebugMode;
  if ((GLASS_DEBUG as readonly string[]).includes(value)) return value as GlassDebugMode;
  return "off";
}

export function isLayoutDebug(mode: DebugMode): mode is LayoutDebugMode {
  return (LAYOUT_DEBUG as readonly string[]).includes(mode);
}

export function isGlassDebug(mode: DebugMode): mode is GlassDebugMode {
  return (GLASS_DEBUG as readonly string[]).includes(mode);
}

export function isDebugEnabled(mode: DebugMode): boolean {
  return mode !== "off";
}
