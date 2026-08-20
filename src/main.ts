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
if (query.get("optics") === "v4" || query.get("foundation") === "layout"
  || query.get("composition") === "v2") {
  const { startGridPreviewV4 } = await import("./v4/preview/entry");
  await startGridPreviewV4();
} else {
  const app = new App();
  await app.start();
  installQAHooks(app);
}
