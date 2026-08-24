import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";

/**
 * v1.1.0 multi-page build.
 *
 * The public product, content admin and authenticated draft preview are three
 * separate Rollup entries. The admin and preview may share content-domain code,
 * but the public product must never import either entry and therefore never
 * downloads their UI/auth modules.
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
    manifest: true,
    rollupOptions: {
      input: {
        product: fileURLToPath(new URL("./index.html", import.meta.url)),
        admin: fileURLToPath(new URL("./admin.html", import.meta.url)),
        draftPreview: fileURLToPath(new URL("./draft-preview.html", import.meta.url)),
      },
    },
  },
});
