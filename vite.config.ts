import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
import { defineConfig, type PreviewServer, type ViteDevServer } from "vite";

function glassLabRoute() {
  const privateReferencePath = /^\/(?:__phase1b_review__\/|\.private\/|qa-v4\/review\/|qa-v4\/reference\/frozen-visual\/(?:frames\/|crops\/|masks\/|overlays\/|manifest\.private\.json|annotations\.private\.json))/;
  const denyPrivateReference = (
    req: { url?: string },
    res: { statusCode: number; setHeader(name: string, value: string): void; end(body?: string): void },
    next: () => void,
  ) => {
    const pathname = (req.url ?? "").split("?", 1)[0];
    if (!privateReferencePath.test(pathname)) {
      next();
      return;
    }
    res.statusCode = 404;
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.end("Private review assets are available only through the local Phase 1B review server.\n");
  };
  const rewrite = (req: { url?: string }) => {
    if (!req.url) return;
    if (req.url === "/glass-lab" || req.url.startsWith("/glass-lab?")) {
      req.url = req.url.replace("/glass-lab", "/glass-lab.html");
    }
    if (req.url === "/glass-lab-v4" || req.url.startsWith("/glass-lab-v4?")) {
      req.url = req.url.replace("/glass-lab-v4", "/glass-lab-v4.html");
      return;
    }
    if (req.url === "/phase-1b-review" || req.url.startsWith("/phase-1b-review?")) {
      req.url = req.url.replace("/phase-1b-review", "/phase-1b-review.html");
    }
  };
  return {
    name: "glass-lab-route",
    configureServer(server: ViteDevServer) {
      server.middlewares.use(denyPrivateReference);
      server.middlewares.use((req, _res, next) => {
        rewrite(req);
        next();
      });
    },
    configurePreviewServer(server: PreviewServer) {
      server.middlewares.use(denyPrivateReference);
      server.middlewares.use((req, _res, next) => {
        rewrite(req);
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [glassLabRoute()],
  server: {
    host: "127.0.0.1",
    port: 5280,
    strictPort: true,
    fs: {
      deny: [
        ".env",
        ".env.*",
        "*.{crt,pem}",
        "**/.git/**",
        "**/.private/**",
        "**/qa-v4/review/**",
        "**/qa-v4/reference/frozen-visual/**/*.private.json",
        "**/qa-v4/reference/frozen-visual/{frames,crops,masks,overlays}/**",
      ],
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 5280,
    strictPort: true,
  },
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      input: {
        main: resolve(root, "index.html"),
        glassLab: resolve(root, "glass-lab.html"),
        glassLabV4: resolve(root, "glass-lab-v4.html"),
        phase1bReview: resolve(root, "phase-1b-review.html"),
      },
    },
  },
});
