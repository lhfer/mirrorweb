import type { QualityLevel } from "../config";

export class AdaptiveQuality {
  level: QualityLevel;
  private frames: number[] = [];
  private lockedUntil = 0;

  constructor(initial: QualityLevel = "high") {
    this.level = initial;
  }

  sample(frameMs: number, now: number) {
    this.frames.push(frameMs);
    if (this.frames.length > 90) this.frames.shift();
    if (now < this.lockedUntil || this.frames.length < 45) return this.level;

    const sorted = [...this.frames].sort((a, b) => a - b);
    const p95 = sorted[Math.floor(sorted.length * 0.95)];
    const fps = 1000 / (sorted[Math.floor(sorted.length * 0.5)] || 16.6);

    let next = this.level;
    if (this.level === "high" && (p95 > 22 || fps < 48)) next = "medium";
    else if (this.level === "medium" && (p95 > 28 || fps < 40)) next = "low";
    else if (this.level === "low" && p95 < 18 && fps > 55) next = "medium";
    else if (this.level === "medium" && p95 < 15 && fps > 58) next = "high";

    if (next !== this.level) {
      this.level = next;
      this.lockedUntil = now + 2500;
      this.frames.length = 0;
    }
    return this.level;
  }
}
