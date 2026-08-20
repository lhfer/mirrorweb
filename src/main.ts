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
