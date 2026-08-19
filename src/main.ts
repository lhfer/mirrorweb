import "./style.css";
import { App } from "./app/App";
import { installQAHooks } from "./debug/QAHooks";

// V4 optics are an opt-in experiment behind ?optics=v4. Any other value, and
// no value at all, boots the untouched V3 application below, which stays the
// page default. The V4 chunk is dynamically imported so the default path does
// not even download it.
if (new URLSearchParams(location.search).get("optics") === "v4") {
  const { startGridPreviewV4 } = await import("./v4/preview/entry");
  await startGridPreviewV4();
} else {
  const app = new App();
  await app.start();
  installQAHooks(app);
}
