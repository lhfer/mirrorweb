import test from "node:test";
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) files.push(...await sourceFiles(path));
    else if (/\.(?:ts|html)$/.test(entry.name)) files.push(path);
  }
  return files;
}

test("content-controlled UI never uses an HTML injection sink", async () => {
  const roots = ["src/admin", "src/content", "src/ui", "src/preview"];
  const forbidden = /\.(?:innerHTML|outerHTML)\s*=|insertAdjacentHTML\s*\(|document\.write\s*\(/;
  const violations: string[] = [];
  for (const root of roots) {
    for (const path of await sourceFiles(resolve(process.cwd(), root))) {
      if (forbidden.test(await readFile(path, "utf8"))) violations.push(path);
    }
  }
  assert.deepEqual(violations, []);
});

test("browser source never names a service-role environment variable", async () => {
  const violations: string[] = [];
  for (const path of await sourceFiles(resolve(process.cwd(), "src"))) {
    const source = await readFile(path, "utf8");
    if (/SUPABASE_SERVICE_ROLE_KEY|VITE_.*SERVICE_ROLE/.test(source)) violations.push(path);
  }
  assert.deepEqual(violations, []);
});
