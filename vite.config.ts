import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
import { defineConfig, type PreviewServer, type ViteDevServer } from "vite";

function glassLabRoute() {
  const rewrite = (req: { url?: string }) => {
    if (!req.url) return;
    if (req.url === "/glass-lab" || req.url.startsWith("/glass-lab?")) {
      req.url = req.url.replace("/glass-lab", "/glass-lab.html");
    }
    if (req.url === "/glass-lab-v4" || req.url.startsWith("/glass-lab-v4?")) {
      req.url = req.url.replace("/glass-lab-v4", "/glass-lab-v4.html");
      return;
    }
  };
  return {
    name: "glass-lab-route",
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, _res, next) => {
        rewrite(req);
        next();
      });
    },
    configurePreviewServer(server: PreviewServer) {
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
      },
    },
  },
});
