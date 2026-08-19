import { execFileSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * Measures centre-card luminance and texture for a set of PNG buffers.
 *
 * Node has no PNG decoder, so the pixels go through the same Python/Pillow
 * stack the rest of the V4 measurement scripts use.
 */
export async function analyzeBuffers(buffers) {
  const directory = await mkdtemp(path.join(tmpdir(), "ilg-round1-"));
  try {
    const files = [];
    for (const [index, buffer] of buffers.entries()) {
      const file = path.join(directory, `probe-${index}.png`);
      await writeFile(file, buffer);
      files.push(file);
    }
    const output = execFileSync("python3", [path.join(REPO_ROOT, "scripts/v4/frame-stats.py"), ...files], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    return JSON.parse(output);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
