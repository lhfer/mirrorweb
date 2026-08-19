import "../../style.css";
import "./lab.css";
import { V4_DEBUG_MODES, V4_SHELL_MODES, type V4DebugMode, type V4ShellMode } from "../OpticsConfigV4";
import { startGridPreviewV4 } from "./entry";
import type { GridAppV4 } from "./GridAppV4";

/**
 * /grid-lab-v4 — the real multi-card page rendered with V4 optics, plus a small
 * review console. The console is overlay-only: it never changes the scene, and
 * `?hud=0` removes it for clean capture frames.
 */

const query = new URLSearchParams(location.search);
const hudEnabled = query.get("hud") !== "0";

function label(value: string): string {
  return value.replaceAll("-", " ").toUpperCase();
}

function buildHud(app: GridAppV4): void {
  const hud = document.createElement("aside");
  hud.id = "grid-hud";
  hud.className = "grid-hud";
  hud.innerHTML = `
    <header>
      <span class="grid-hud__dot" aria-hidden="true"></span>
      <div>
        <strong>V4 GRID PREVIEW</strong>
        <small>ROUND 1 · EXPERIMENT · V3 REMAINS DEFAULT</small>
      </div>
    </header>
    <nav class="grid-hud__links">
      <a href="/?optics=v3">Main page · V3</a>
      <a href="/?optics=v4">Main page · V4</a>
      <a href="/glass-lab-v4">Optics bench</a>
    </nav>
    <label class="grid-hud__field">
      <span>V4 view</span>
      <select id="grid-hud-debug"></select>
    </label>
    <label class="grid-hud__field">
      <span>Reflection shell</span>
      <select id="grid-hud-shell"></select>
    </label>
    <div class="grid-hud__buttons">
      <button type="button" id="grid-hud-pause">Pause</button>
      <button type="button" id="grid-hud-reset">Reset</button>
      <button type="button" id="grid-hud-hide">Hide</button>
    </div>
    <dl class="grid-hud__metrics">
      <div><dt>Frame</dt><dd id="grid-hud-frame">—</dd></div>
      <div><dt>Quality</dt><dd id="grid-hud-quality">—</dd></div>
      <div><dt>Scene RT</dt><dd id="grid-hud-target">—</dd></div>
      <div><dt>Overscan</dt><dd id="grid-hud-overscan">—</dd></div>
      <div><dt>Pool</dt><dd id="grid-hud-pool">—</dd></div>
      <div><dt>Video / render</dt><dd id="grid-hud-video">—</dd></div>
    </dl>
  `;
  document.body.append(hud);

  const debugSelect = hud.querySelector<HTMLSelectElement>("#grid-hud-debug")!;
  for (const mode of V4_DEBUG_MODES) {
    const option = document.createElement("option");
    option.value = mode;
    option.textContent = label(mode);
    debugSelect.append(option);
  }
  debugSelect.value = app.getDebugMode();
  debugSelect.addEventListener("change", () => {
    app.setDebugMode(debugSelect.value as V4DebugMode);
  });

  const shellSelect = hud.querySelector<HTMLSelectElement>("#grid-hud-shell")!;
  for (const mode of V4_SHELL_MODES) {
    const option = document.createElement("option");
    option.value = mode;
    option.textContent = label(mode);
    shellSelect.append(option);
  }
  shellSelect.value = (app.getV4State().shell as string) ?? "energy-controlled";
  shellSelect.addEventListener("change", () => {
    app.setShellMode(shellSelect.value as V4ShellMode);
  });

  let paused = false;
  const pauseButton = hud.querySelector<HTMLButtonElement>("#grid-hud-pause")!;
  pauseButton.addEventListener("click", () => {
    paused = !paused;
    if (paused) app.pause();
    else app.resume();
    pauseButton.textContent = paused ? "Resume" : "Pause";
  });
  hud.querySelector<HTMLButtonElement>("#grid-hud-reset")!.addEventListener("click", () => app.reset());
  hud.querySelector<HTMLButtonElement>("#grid-hud-hide")!.addEventListener("click", () => {
    hud.dataset.collapsed = hud.dataset.collapsed === "true" ? "false" : "true";
  });

  const frame = hud.querySelector<HTMLElement>("#grid-hud-frame")!;
  const quality = hud.querySelector<HTMLElement>("#grid-hud-quality")!;
  const target = hud.querySelector<HTMLElement>("#grid-hud-target")!;
  const overscan = hud.querySelector<HTMLElement>("#grid-hud-overscan")!;
  const pool = hud.querySelector<HTMLElement>("#grid-hud-pool")!;
  const video = hud.querySelector<HTMLElement>("#grid-hud-video")!;
  window.setInterval(() => {
    const metrics = app.getMetrics() as { medianFrameMs?: number; fps?: number; quality?: string };
    const state = app.getV4State() as {
      sceneColor: { width: number; height: number; scale: number; overscan: number };
      pool: { slots: number; materials: number; geometries: number };
      videoFrames: number;
      renderedFrames: number;
    };
    frame.textContent = `${(metrics.medianFrameMs ?? 0).toFixed(2)} ms · ${Math.round(metrics.fps ?? 0)} fps`;
    quality.textContent = String(metrics.quality ?? "—").toUpperCase();
    target.textContent = `${state.sceneColor.width}×${state.sceneColor.height} · ${state.sceneColor.scale.toFixed(2)}`;
    overscan.textContent = `${state.sceneColor.overscan.toFixed(2)}×`;
    pool.textContent = `${state.pool.slots} slots · ${state.pool.materials} mat · ${state.pool.geometries} geo`;
    video.textContent = `${state.videoFrames} / ${state.renderedFrames}`;
  }, 400);
}

function showBlocked(error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  const panel = document.createElement("div");
  panel.className = "grid-blocked";
  panel.innerHTML = `<strong>V4 grid preview blocked</strong><p></p><a href="/?optics=v3">Open the V3 page</a>`;
  panel.querySelector("p")!.textContent = message;
  document.body.append(panel);
  document.body.dataset.ready = "blocked";
  console.error("[MirrorWeb V4 Grid]", error);
}

startGridPreviewV4()
  .then((app) => {
    document.body.dataset.ready = "true";
    if (hudEnabled) buildHud(app);
  })
  .catch(showBlocked);
