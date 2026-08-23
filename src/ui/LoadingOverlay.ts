import ENTRY from "../../config/target-entry-source-v1.json";
import { Spring } from "../interaction/SourceExactMotion";

const PROGRESS = ENTRY.progress;
const EXIT = ENTRY.loader.exit;

/**
 * The loading overlay.
 *
 * The legacy paths (V3, composition v1/v2) keep the behaviour they were built
 * with: the raw percentage, and a 480 ms fade. `sourceExact` switches on the
 * Target's own, which differs in three ways that are all visible:
 *
 * 1. THE NUMBER IS SPRUNG, NOT WRITTEN. The Target shows
 *    `Math.round(100 * useSpring(progress, {stiffness:90, damping:24,
 *    mass:.55}))`, so the digits chase the real progress instead of jumping
 *    with it. One consequence is worth stating because it looks like a bug and
 *    is not: the loader is removed when the page is ready, which is before the
 *    spring has caught up, so the last number a viewer sees is not 100. Ours
 *    lands in the high eighties or low nineties for the same reason the
 *    Target's does.
 *
 * 2. THE PROGRESS ONLY GOES UP. `b5` in the Target is
 *    `e > b8.get() && b8.set(Math.min(1, e))`. Ours clamps the same way, so a
 *    stage that reports a lower number than the one before it cannot walk the
 *    percentage backwards.
 *
 * 3. THE EXIT IS 1.15 s OF EASE-OUT-EXPO, NOT 480 ms OF EASE. Measured on the
 *    live Target at 1150.0 ms from the first exit frame to the element leaving
 *    the document, across all four load conditions.
 *
 * Pointer events are dropped on the first frame of the exit, not at the end of
 * it -- the Target's exit variant carries `pointerEvents: "none"` -- so the
 * page becomes draggable while the cards are still converging. That is the
 * Target's unlock point and it is deliberate; see
 * `config/target-entry-source-v1.json` -> inputUnlock.
 */
export class LoadingOverlay {
  private readonly root: HTMLElement;
  private readonly percentEl: HTMLElement;
  private readonly sourceExact: boolean;
  private readonly spring: Spring | null;
  private value = 0;
  private shown = -1;
  private raf = 0;
  private hidden = false;

  constructor(host: HTMLElement, sourceExact = false) {
    this.root = host;
    this.sourceExact = sourceExact;
    host.innerHTML = `
      <div class="loader-cluster">
        <div class="loader-brand">
          <div class="brand-mark" aria-hidden="true"></div>
          <p class="brand-word">ATELIER</p>
        </div>
        <p class="loader-percent">0%</p>
      </div>
    `;
    this.percentEl = host.querySelector(".loader-percent") as HTMLElement;
    if (sourceExact) {
      host.classList.add("is-source-exact");
      host.setAttribute("role", "progressbar");
      host.setAttribute("aria-valuemin", "0");
      host.setAttribute("aria-valuemax", "100");
      this.spring = new Spring({
        stiffness: PROGRESS.displaySpring.stiffness,
        damping: PROGRESS.displaySpring.damping,
        mass: PROGRESS.displaySpring.mass,
        restDelta: PROGRESS.displaySpring.restDelta,
        restSpeed: PROGRESS.displaySpring.restSpeed,
      }, 0);
      this.tick(performance.now());
    } else {
      this.spring = null;
    }
  }

  setPercent(value: number) {
    const clamped = Math.max(0, Math.min(100, value));
    if (clamped <= this.value && this.sourceExact) return;
    this.value = Math.max(this.value, clamped);
    if (!this.spring) {
      this.paint(Math.round(this.value));
      return;
    }
    this.spring.setTarget(this.value, performance.now());
  }

  private paint(rounded: number) {
    if (rounded === this.shown) return;
    this.shown = rounded;
    this.percentEl.textContent = `${rounded}%`;
    if (this.sourceExact) this.root.setAttribute("aria-valuenow", String(rounded));
  }

  /**
   * The display spring's own frame loop.
   *
   * It has to be its own, because the overlay exists and is showing numbers
   * before the app's render loop starts -- that is the entire window the
   * loader is for. It stops the moment the overlay is hidden.
   */
  private tick = (now: number) => {
    if (this.hidden || !this.spring) return;
    this.spring.advance(now);
    this.paint(Math.round(this.spring.value));
    this.raf = requestAnimationFrame(this.tick);
  };

  /** The last percentage a viewer actually saw. QA and evidence only. */
  displayedPercent(): number { return this.shown; }

  hide() {
    if (this.hidden) return;
    this.hidden = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    // The Target does NOT snap its percentage to 100 on the way out: the
    // element is removed while the display spring is still climbing. Writing
    // 100 here would be a difference a viewer can read in the last frames of
    // the fade, so the legacy paths keep their snap and the source-exact path
    // leaves the number where the spring left it.
    if (!this.sourceExact) this.setPercent(100);
    this.root.classList.add("is-hidden");
    window.setTimeout(() => {
      this.root.style.display = "none";
    }, this.sourceExact ? EXIT.durationMs : 480);
  }
}
