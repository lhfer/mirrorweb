import { spawnSync } from "node:child_process";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const py = path.join(root, "scripts", "lib", "measure-png.py");
const result = spawnSync("python3", [py, path.join(root, "artifacts", "reference")], {
  encoding: "utf8",
  cwd: root,
});

if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
