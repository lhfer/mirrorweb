/**
 * Development and QA only: a pure-layout view of the grid.
 *
 * `?foundation=layout` strips everything that is not geometry — media, glass,
 * reflection shell, dispersion, typography, footer — and freezes motion, so a
 * layout measurement cannot be contaminated by video content, rim glow or
 * CSS3D type. Cards become flat opaque grey slabs whose silhouette is exactly
 * TILE.width x TILE.height, which is what the layout fitter reasons about.
 *
 * The running product page never enters this mode: it requires the query flag.
 */

export const FOUNDATION_MODES = ["off", "layout"] as const;
export type FoundationMode = (typeof FOUNDATION_MODES)[number];

export function readFoundationMode(search: string = location.search): FoundationMode {
  const value = new URLSearchParams(search).get("foundation");
  return (FOUNDATION_MODES as readonly string[]).includes(value ?? "")
    ? (value as FoundationMode)
    : "off";
}

export function isFoundationLayout(mode: FoundationMode): boolean {
  return mode === "layout";
}

/** One flat grey for every card, so no card can be told apart by its material. */
export const FOUNDATION_SLAB_COLOR = 0x8a8a8a;
