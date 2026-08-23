import { defineConfig } from "vite";

/**
 * v1.0.0.
 *
 * The development tree built five HTML entries: the product page plus four lab
 * and review surfaces (glass-lab, glass-lab-v4, grid-lab-v4, phase-1b-review).
 * Those four are QA instruments and are not in this branch, so there is one
 * entry and Vite finds it at the root without being told.
 *
 * The dev-server middleware that used to 404 private QA reference assets went
 * with them. It existed to stop `qa-v4/review/`, `.private/` and the frozen
 * Target frames being served by a dev server someone had pointed at their LAN;
 * none of those paths exist in this tree, so the guard has nothing left to
 * guard and keeping it would only suggest it does.
 *
 * `sourcemap: true` is kept: it is what the release file manifest's per-file
 * "why is this in the tree" reasons were derived from, and keeping it means
 * that derivation can be re-run against any future build.
 */
export default defineConfig({
  server: { host: "127.0.0.1", port: 5280, strictPort: true },
  preview: { host: "127.0.0.1", port: 5280, strictPort: true },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
