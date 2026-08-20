import type { QualityLevel } from "../config";

export class AdaptiveQuality {
  level: QualityLevel;
  private frames: number[] = [];
  private lockedUntil = 0;

  constructor(initial: QualityLevel = "high") {
    this.level = initial;
  }

  /**
   * Returns the level AND whether this call changed it.
   *
   * It used to return just the level, having already written `this.level`. The
   * one caller then asked `level !== this.quality.level`, which compares the
   * returned value with the field it was just assigned from: always false. The
   * adaptive path has therefore never actually fired -- `grid.setQuality` and
   * `pipeline.setQuality` were only ever reachable through the manual QA hook.
   */
  sample(frameMs: number, now: number): { level: QualityLevel; changed: boolean } {
    this.frames.push(frameMs);
    if (this.frames.length > 90) this.frames.shift();
    if (now < this.lockedUntil || this.frames.length < 45) {
      return { level: this.level, changed: false };
    }

    const sorted = [...this.frames].sort((a, b) => a - b);
    const p95 = sorted[Math.floor(sorted.length * 0.95)];
    const fps = 1000 / (sorted[Math.floor(sorted.length * 0.5)] || 16.6);

    let next = this.level;
    if (this.level === "high" && (p95 > 22 || fps < 48)) next = "medium";
    else if (this.level === "medium" && (p95 > 28 || fps < 40)) next = "low";
    else if (this.level === "low" && p95 < 18 && fps > 55) next = "medium";
    else if (this.level === "medium" && p95 < 15 && fps > 58) next = "high";

    if (next === this.level) return { level: this.level, changed: false };
    this.level = next;
    this.lockedUntil = now + 2500;
    this.frames.length = 0;
    return { level: this.level, changed: true };
  }
}
