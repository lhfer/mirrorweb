import "./style.css";
import { App } from "./app/App";
import { installQAHooks } from "./debug/QAHooks";

// V4 optics are an opt-in experiment behind ?optics=v4. Any other value, and
// no value at all, boots the untouched V3 application below, which stays the
// page default. The V4 chunk is dynamically imported so the default path does
// not even download it.
//
// `?foundation=layout` is the V5 dev/QA layout view. It routes to V4 as well,
// because V4 is the build under review; the layout it shows is the shared
// GRID/TILE/placeTile geometry, so it is equally valid for V3.
// `?review=target` / `?review=current` are the product review routes: one
// URL, no hand-assembled query, the complete page. `target` pins the leading
// optical candidate (composition=sourceExact + opticalBody=target-source-
// unclamped, which carries the Target device-tier sample law); `current`
// pins the same page on the shipped optical default, for comparison.
// Everything else -- labels, footer, motion, coverage culling, source-exact
// typography, beauty view, real media, adaptive quality -- is already the
// default on this path, so the route only pins what a query could vary.
// The expansion is written back onto location.search BEFORE anything boots
// because config.ts readers (compositionVersion, verticalMode, ...) parse
// location.search themselves; review= wins over any conflicting param. The
// shipped no-query default is untouched: no review, nothing changes.
const REVIEW_ROUTES: Record<string, string> = {
  target: "target-source-unclamped",
  current: "current",
};
{
  const review = new URLSearchParams(location.search).get("review") ?? "";
  if (review in REVIEW_ROUTES) {
    const expanded = new URLSearchParams(location.search);
    expanded.set("composition", "sourceExact");
    expanded.set("opticalBody", REVIEW_ROUTES[review]);
    history.replaceState(null, "", `${location.pathname}?${expanded}${location.hash}`);
  }
}
const query = new URLSearchParams(location.search);
// Any V5 composition selects the V4 build, because that is the build those
// compositions exist in. `composition=sourceExact` previously fell through to
// V3, so the route named in every brief and every preview link only worked when
// `optics=v4` was passed alongside it -- a URL nobody would guess from the docs.
// V4 remains opt-in: no composition and no optics still boots V3.
const V5_COMPOSITIONS = new Set(["v1", "v2", "sourceExact"]);
if (query.get("optics") === "v4" || query.get("foundation") === "layout"
  || V5_COMPOSITIONS.has(query.get("composition") ?? "")) {
  const { startGridPreviewV4 } = await import("./v4/preview/entry");
  await startGridPreviewV4();
} else {
  const app = new App();
  await app.start();
  installQAHooks(app);
}
