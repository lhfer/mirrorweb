import {
  getContentRuntime,
  type RuntimeContentCard,
} from "./ContentRepository";

export type CatalogItem = RuntimeContentCard;

/** The published, enabled and sortOrder-sorted catalog for this page boot. */
export function getCatalog(): readonly CatalogItem[] {
  return getContentRuntime().catalog;
}

/**
 * The spatial hash is the frozen v1.0 rule. Only its input array moved from a
 * compile-time constant to the once-installed runtime. The returned object is
 * precomputed and frozen, so normal motion performs no content allocation.
 */
export function catalogAt(i: number, j: number): CatalogItem {
  const catalog = getContentRuntime().catalog;
  const n = catalog.length;
  const index = ((i * 7 + j * 13) % n + n) % n;
  return catalog[index];
}
