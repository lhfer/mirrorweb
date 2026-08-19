import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { createReadStream } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

export async function sha256File(path) {
  const hash = createHash("sha256");
  await new Promise((resolveHash, rejectHash) => {
    const stream = createReadStream(path);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", rejectHash);
    stream.on("end", resolveHash);
  });
  return hash.digest("hex");
}

export function sha256Value(value) {
  return createHash("sha256").update(JSON.stringify(stable(value))).digest("hex");
}

export async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

export async function writeJson(path, value, options = {}) {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, options);
}

export function execText(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: options.cwd ?? REPO_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

export function blocker(code, message, details = undefined) {
  return details === undefined ? { code, message } : { code, message, details };
}

export function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}
