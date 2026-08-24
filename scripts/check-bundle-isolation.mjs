import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const manifestPath = resolve(root, "dist/.vite/manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

const productKey = Object.keys(manifest).find((key) => {
  const item = manifest[key];
  return item?.isEntry && (item.src === "index.html" || key === "index.html");
});
if (!productKey) throw new Error("Vite manifest has no public index.html entry");

const visited = new Set();
const visit = (key) => {
  if (visited.has(key)) return;
  visited.add(key);
  const item = manifest[key];
  if (!item) throw new Error(`Vite manifest is missing imported chunk: ${key}`);
  for (const dependency of [...(item.imports ?? []), ...(item.dynamicImports ?? [])]) {
    visit(dependency);
  }
};
visit(productKey);

const forbiddenSource = /(^|\/)src\/(admin|preview)(\/|$)|@supabase\//;
const violations = [...visited].filter((key) => {
  const item = manifest[key];
  return forbiddenSource.test(key) || forbiddenSource.test(item?.src ?? "");
});
if (violations.length) {
  throw new Error(`Public entry reaches admin/auth code: ${violations.join(", ")}`);
}

const assetDir = resolve(root, "dist/assets");
const assetNames = await readdir(assetDir);
const secretMarkers = [
  { label: "SUPABASE_SERVICE_ROLE_KEY", pattern: /SUPABASE_SERVICE_ROLE_KEY/ },
  { label: "sb_secret_<value>", pattern: /sb_secret_[A-Za-z0-9_-]{20,}/ },
];
for (const name of assetNames.filter((value) => /\.(?:js|css|map)$/.test(value))) {
  const content = await readFile(resolve(assetDir, name), "utf8");
  const marker = secretMarkers.find(({ pattern }) => pattern.test(content));
  if (marker) {
    throw new Error(`Forbidden secret marker ${marker.label} found in dist/assets/${name}`);
  }
}

const productFiles = [...visited].map((key) => manifest[key]?.file).filter(Boolean);
console.log(JSON.stringify({
  gate: "public-bundle-isolation",
  status: "PASS",
  productEntry: productKey,
  productFiles,
  adminOrPreviewModules: 0,
  secretMarkers: 0,
}, null, 2));
