import { isLayoutDebug, type DebugMode } from "./DebugMode";

export class DebugHud {
  private readonly root: HTMLElement;
  private readonly frame: HTMLElement;
  private readonly stats: HTMLElement;

  constructor(host: HTMLElement) {
    this.root = document.createElement("div");
    this.root.id = "debug-hud";
    this.root.hidden = true;
    this.frame = document.createElement("div");
    this.frame.className = "debug-overscan-frame";
    this.stats = document.createElement("pre");
    this.stats.className = "debug-stats";
    this.root.append(this.frame, this.stats);
    host.appendChild(this.root);
  }

  setMode(mode: DebugMode) {
    this.root.hidden = mode === "off";
    this.root.dataset.mode = mode;
    this.frame.hidden = !isLayoutDebug(mode);
  }

  setText(text: string) {
    this.stats.textContent = text;
  }

  dispose() {
    this.root.remove();
  }
}
