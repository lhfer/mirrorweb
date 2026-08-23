import ENTRY from "../../config/target-entry-source-v1.json";
import { TARGET_GRID, type SourceExactLayoutFrame } from "../layout/SourceExactLayout";
import { Spring } from "./SourceExactMotion";

/**
 * The Target's cold-load entry: ONE spring, on ONE number.
 *
 * There is no per-card stagger, no opacity ramp and no scale animation in the
 * Target's entry, and this module does not invent any. What it has is the grid
 * GAP RATIO, held at 3 while the page loads and sprung down to the layout
 * contract's 0.045 the moment the scene reports ready:
 *
 *     b0 = mY(3)
 *     useEffect(() => { if (!ready) return
 *                       const a = animate(b0, grid.gapRatio, {type:"spring", ...b$})
 *                       return () => a.stop() }, [ready, grid.gapRatio])
 *
 * At gap 3 the cell pitch is four times the card width, so the grid is spread
 * across roughly sixteen times its resting area: the columns either side of
 * centre are off the edges of the screen and what remains visible is a handful
 * of cards from far around the sphere, small because they are far away. As the
 * gap collapses everything sweeps inward and grows into place. That is the
 * whole of the aggregation the entry reads as. See
 * `config/target-entry-source-v1.json` for the source expressions and
 * `qa-v5/final-entry/target-entry-contract.json` for the measurement that
 * recovers gap(t) = 3.00000 -> 0.04500 out of the live Target's own DOM.
 *
 * WHY THIS IS NOT A CHANGE TO THE FROZEN LAYOUT. The Target computes
 * `cols`, `rows`, `planeWidth`, `planeHeight`, `sphereRadius`, `cardScale` and
 * the camera from L6 with the STATIC gap ratio, and multiplies only the pitch
 * at placement time (`A = d*(1+m)`, `E = f*A`). Nothing the layout contract
 * fixes is a function of the animated value, the pool never resizes, and the
 * spring's own rest value is the contract's gap ratio -- so the entry ends at
 * the frozen layout exactly, not near it.
 *
 * It is deliberately separate from `SourceExactMotion`: it shares that module's
 * spring solver, because there is only one framer-motion to transcribe, and
 * shares nothing else. It cannot see the scroll springs, the pointer springs,
 * the magnitude spring, the drag state or the release velocity, and none of
 * them can see it.
 */
const SPRING = ENTRY.intro.spring;

export type IntroState = "waiting" | "running" | "done";

/** The gap the grid rests at -- the layout contract's own value. */
export const INTRO_REST_GAP: number = TARGET_GRID.gapRatio;

/** The gap the grid is held at until ready. */
export const INTRO_FROM_GAP: number = ENTRY.intro.from;

export class SourceExactIntro {
  private readonly spring = new Spring(
    { stiffness: SPRING.stiffness, damping: SPRING.damping, mass: SPRING.mass,
      restDelta: SPRING.restDelta, restSpeed: SPRING.restSpeed },
    INTRO_FROM_GAP,
  );

  private phase: IntroState = "waiting";
  private startedAtMs = 0;
  private endedAtMs = 0;

  get state(): IntroState { return this.phase; }

  get done(): boolean { return this.phase === "done"; }

  /** The live gap ratio. Exactly the contract value once the entry is over. */
  get gap(): number {
    return this.phase === "done" ? INTRO_REST_GAP
      : this.phase === "waiting" ? INTRO_FROM_GAP : this.spring.value;
  }

  /**
   * 0 at the start of the entry, 1 at the end.
   *
   * The fraction of the gap's travel that has been covered. Reported for the
   * status readout and the QA surface; nothing in the render path consumes it,
   * because the render path consumes the gap itself.
   */
  get progress(): number {
    if (this.phase === "done") return 1;
    if (this.phase === "waiting") return 0;
    const travel = INTRO_FROM_GAP - INTRO_REST_GAP;
    return travel === 0 ? 1
      : Math.min(1, Math.max(0, (INTRO_FROM_GAP - this.spring.value) / travel));
  }

  /** Milliseconds since the entry started; 0 before it does. */
  elapsedMs(nowMs: number): number {
    if (this.phase === "waiting") return 0;
    return (this.phase === "done" ? this.endedAtMs : nowMs) - this.startedAtMs;
  }

  /** Ready. One shot: a second call is ignored, as a second mount would be. */
  start(nowMs: number): void {
    if (this.phase !== "waiting") return;
    this.phase = "running";
    this.startedAtMs = nowMs;
    this.spring.setTarget(INTRO_REST_GAP, nowMs);
  }

  advance(nowMs: number): void {
    if (this.phase !== "running") return;
    this.spring.advance(nowMs);
    // The solver assigns its exact target on the frame it rests, so this
    // comparison is the spring's own completion and not a threshold of ours.
    if (this.spring.value === INTRO_REST_GAP) {
      this.phase = "done";
      this.endedAtMs = nowMs;
    }
  }

  /**
   * End the entry now, at exact identity.
   *
   * QA only. Every fixed-state harness in this repo loads the page, waits for
   * the assets and then pins a pose; an entry still running underneath would
   * make those poses depend on how long the harness happened to take. `pause()`
   * calls this, so a paused page is a settled page. The product path never
   * calls it -- the entry ends because the spring rests.
   */
  finish(nowMs: number): void {
    if (this.phase === "done") return;
    if (this.phase === "waiting") this.startedAtMs = nowMs;
    this.spring.reset(INTRO_REST_GAP);
    this.phase = "done";
    this.endedAtMs = nowMs;
  }

  /**
   * The layout frame the grid should place against THIS frame.
   *
   * Once the entry is done this is the caller's own frame object, untouched, so
   * every number the placement reads is the one it read before this module
   * existed -- not a recomputation that happens to agree. While the entry runs
   * it is a shallow view of that frame with the four spacing quantities
   * rewritten, exactly as the Target rewrites them:
   *
   *     A = planeWidth * (1 + gap)   E = cols * A
   *     y = planeHeight * (1 + gap)  S = rows * y
   *
   * The view is allocated once and rewritten in place: an entry is 150 frames
   * and a per-frame object would be 150 allocations during the one stretch of
   * the page's life that is already the busiest.
   */
  frameFor(frame: SourceExactLayoutFrame | undefined): SourceExactLayoutFrame | undefined {
    if (frame === undefined || this.phase === "done") return frame;
    const gap = this.gap;
    const view = (this.view ??= { ...frame }) as SourceExactLayoutFrame;
    Object.assign(view, frame);
    view.cellW = frame.planeWidth * (1 + gap);
    view.cellH = frame.planeHeight * (1 + gap);
    view.periodX = frame.cols * view.cellW;
    view.periodY = frame.rows * view.cellH;
    return view;
  }

  private view: SourceExactLayoutFrame | null = null;

  /** QA and the status readout. */
  truth(nowMs: number): Record<string, unknown> {
    return {
      state: this.phase,
      gap: this.gap,
      restGap: INTRO_REST_GAP,
      fromGap: INTRO_FROM_GAP,
      progress: this.progress,
      elapsedMs: Math.round(this.elapsedMs(nowMs)),
      atIdentity: this.phase === "done" && this.gap === INTRO_REST_GAP,
      spring: SPRING,
    };
  }
}
