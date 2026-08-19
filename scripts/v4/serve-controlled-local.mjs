#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { realpath } from "node:fs/promises";
import path from "node:path";
import { createServer } from "vite";
import { REPO_ROOT, readJson } from "./lib/common.mjs";

const matrix = await readJson(path.join(REPO_ROOT, "qa-v4/reference/capture-matrix.json"));
const local = matrix.sites.find((site) => site.id === "local");
if (!local) throw new Error("capture matrix has no local site");

const sourceDirectory = path.resolve(process.env.ILG_LOCAL_SOURCE_DIR || REPO_ROOT);
const dependencyDirectory = await realpath(path.join(REPO_ROOT, "node_modules"));
const port = Number(process.env.ILG_LOCAL_PORT || 5281);
const git = (...args) => execFileSync("git", ["-C", sourceDirectory, ...args], { encoding: "utf8" }).trim();
const sourceCommit = git("rev-parse", "HEAD");
const sourceTree = git("rev-parse", "HEAD^{tree}");
const trackedStatus = git("status", "--porcelain", "--untracked-files=no");

if (sourceCommit !== local.expectedSourceCommit) {
  throw new Error(`expected local source ${local.expectedSourceCommit}, observed ${sourceCommit}`);
}
if (sourceTree !== local.expectedSourceTree) {
  throw new Error(`expected local tree ${local.expectedSourceTree}, observed ${sourceTree}`);
}
if (trackedStatus) throw new Error("controlled local source has tracked modifications");

const identity = Object.freeze({
  schemaVersion: 1,
  sourceCommit,
  sourceTree,
  trackedTreeClean: true,
});

const identityPlugin = {
  name: "ilg-controlled-local-identity",
  configureServer(server) {
    server.middlewares.use((request, response, next) => {
      response.setHeader("X-ILG-Source-Commit", sourceCommit);
      response.setHeader("X-ILG-Source-Tree", sourceTree);
      if (request.url?.split("?")[0] !== "/__ilg_capture_identity.json") return next();
      response.statusCode = 200;
      response.setHeader("Content-Type", "application/json; charset=utf-8");
      response.setHeader("Cache-Control", "no-store");
      response.end(`${JSON.stringify(identity)}\n`);
    });
  },
};

const server = await createServer({
  configFile: false,
  root: sourceDirectory,
  plugins: [identityPlugin],
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    fs: { allow: [sourceDirectory, dependencyDirectory] },
  },
});

await server.listen();
console.log(JSON.stringify({
  status: "READY",
  url: `http://127.0.0.1:${port}`,
  sourceCommit,
  sourceTree,
  trackedTreeClean: true,
}));
