import "./style.css";
import { App } from "./app/App";
import { installQAHooks } from "./debug/QAHooks";

// `?review=target` / `?review=current` are the product routes: one URL, no
// hand-assembled query, the complete page. `target` is the accepted candidate
// (composition=sourceExact + opticalBody=target-source-unclamped, which carries
// the Target device-tier sample law); `current` is the same page on the
// previously shipped optical default, kept as the rollback and for comparison.
// Everything else -- labels, footer, motion, coverage culling, source-exact
// typography, beauty view, real media, adaptive quality, exposure 1.0 -- is
// already the default on this path, so a route only pins what a query could
// vary.
//
// v1.0.0 CHANGES ONE THING: a URL that names no route now takes `target`
// instead of falling through to V3. Through the whole of development V4 was
// opt-in and a bare `/` booted the old V3 application, which meant the shipped
// default was the one build nobody was reviewing -- and a URL like `/?status=1`
// silently landed there too, because it pins no optics. The accepted candidate
// is the product now, so it is what `/` serves.
//
// A URL that DOES pin optics itself is left alone. `?optics=`, `?foundation=`
// and `?composition=` are the QA and comparison surfaces; overriding them here
// would make every one of them show something other than what it says.
//
// THE EXPANSION IS WRITTEN BACK ONTO location.search AND STAYS THERE. That is
// deliberate, not laziness about tidying the URL: config.ts readers
// (compositionVersion, verticalMode, portraitLaw, ...) parse location.search
// again on later events such as a resize, so a URL cleaned up after boot would
// silently revert the page to the V3 defaults mid-session.
const REVIEW_ROUTES: Record<string, string> = {
  target: "target-source-unclamped",
  current: "current",
};
const DEFAULT_ROUTE = "target";
{
  const search = new URLSearchParams(location.search);
  const review = search.get("review") ?? "";
  const pinsOptics = search.has("optics") || search.has("foundation")
    || search.has("composition");
  const route = review in REVIEW_ROUTES ? review : (pinsOptics ? "" : DEFAULT_ROUTE);
  if (route) {
    const expanded = new URLSearchParams(location.search);
    expanded.set("composition", "sourceExact");
    expanded.set("opticalBody", REVIEW_ROUTES[route]);
    history.replaceState(null, "", `${location.pathname}?${expanded}${location.hash}`);
  }
}
const query = new URLSearchParams(location.search);
// Any V5 composition selects the V4 build, because that is the build those
// compositions exist in. V3 is still here and still reachable -- an explicit
// `?composition=` naming something outside this set boots it -- because the
// release brief authorises the default-route switch and nothing more.
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
