import CONTRACT from "../../config/target-motion-source-v1.json";

/**
 * The Target's motion, computed the way the Target computes it.
 *
 * Every constant comes from `config/target-motion-source-v1.json`, which is the
 * single source contract, read out of the Target's own application bundle.
 * There is no fitted number in this file. `scripts/v5/source_motion.py` is the
 * Python twin and reads the same file; neither keeps its own copy, because two
 * hand-maintained copies drift and the drift is invisible until a gate
 * disagrees.
 *
 * The Target composes its motion out of framer-motion primitives:
 *
 *   a full-viewport pan surface  ->  onPan / onPanEnd
 *   scrollTarget += 1.5 * panDelta          (both axes, both positive)
 *   scrollTarget += releaseVelocity * 0.1   (once, on release)
 *   scroll        = a spring chasing that target
 *   |velocity|    = a second spring, driving a camera dolly
 *   pointer       = a third spring, driving a camera orbit
 *
 * There is no inertia integrator, no maximum speed, no stop threshold and no
 * wheel handling anywhere in it. The springs are the whole dynamics.
 */

export const MOTION_CONTRACT = CONTRACT;

const SPRINGS = CONTRACT.springs;
const DRAG = CONTRACT.drag;
const GESTURE = CONTRACT.input.gesture;
const VELOCITY = CONTRACT.input.velocityEstimation;

type SpringConfig = { stiffness: number; damping: number; mass: number;
                      restDelta: number; restSpeed: number };

/**
 * One closed-form spring solve, transcribed from the bundled framer-motion.
 *
 * Time is milliseconds and `velocity0` is units per second -- the units the
 * library reports and re-consumes on a retarget. All three of the Target's
 * springs are overdamped, but the other branches are written out anyway: a
 * solver that silently handles one regime is a solver that will be wrong the
 * first time a constant moves.
 */
class SpringSolver {
  private readonly zeta: number;
  private readonly omega: number;
  private readonly delta: number;
  private readonly mode: "under" | "critical" | "over";
  private wd = 0;
  private a = 0;
  private s = 0;
  private o = 0;
  private b = 0;
  private e = 0;
  private t_ = 0;
  private n_ = 0;
  private a_ = 0;

  constructor(from: number, readonly to: number, velocity0: number,
              readonly cfg: SpringConfig) {
    // The library passes `-(velocity / 1000)` in and reports `1000 * i(t)`
    // back out, so the internal sign is inverted on purpose.
    const b = -(velocity0 / 1000);
    this.zeta = cfg.damping / (2 * Math.sqrt(cfg.stiffness * cfg.mass));
    this.delta = to - from;
    this.omega = Math.sqrt(cfg.stiffness / cfg.mass) / 1000;
    const z = this.zeta, S = this.delta, w = this.omega;
    if (z < 1) {
      this.mode = "under";
      this.wd = w * Math.sqrt(1 - z * z);
      this.a = this.wd ? (b + z * w * S) / this.wd : 0;
      this.s = z * w * this.a + S * this.wd;
      this.o = z * w * S - this.a * this.wd;
    } else if (z === 1) {
      this.mode = "critical";
      this.b = b;
      this.e = b + w * S;
    } else {
      this.mode = "over";
      this.wd = w * Math.sqrt(z * z - 1);
      this.t_ = (b + z * w * S) / this.wd;
      this.n_ = z * w * this.t_ - S * this.wd;
      this.a_ = z * w * S - this.t_ * this.wd;
    }
  }

  value(t: number): number {
    const z = this.zeta, S = this.delta, w = this.omega;
    if (this.mode === "under") {
      return this.to - Math.exp(-z * w * t)
        * (this.a * Math.sin(this.wd * t) + S * Math.cos(this.wd * t));
    }
    if (this.mode === "critical") return this.to - Math.exp(-w * t) * (S + this.e * t);
    // The library caps the sinh/cosh argument at 300 and leaves the decaying
    // exponential uncapped. Reproduced rather than tidied.
    const i = Math.min(this.wd * t, 300);
    return this.to - Math.exp(-z * w * t)
      * (this.t_ * this.wd * Math.sinh(i) + this.wd * S * Math.cosh(i)) / this.wd;
  }

  velocity(t: number): number {
    const z = this.zeta, w = this.omega;
    if (this.mode === "under") {
      return 1000 * Math.exp(-z * w * t)
        * (this.s * Math.sin(this.wd * t) + this.o * Math.cos(this.wd * t));
    }
    if (this.mode === "critical") return 1000 * Math.exp(-w * t) * (w * this.e * t - this.b);
    const i = Math.min(this.wd * t, 300);
    return 1000 * Math.exp(-z * w * t) * (this.n_ * Math.sinh(i) + this.a_ * Math.cosh(i));
  }

  done(t: number): boolean {
    return Math.abs(this.velocity(t)) <= this.cfg.restSpeed
        && Math.abs(this.to - this.value(t)) <= this.cfg.restDelta;
  }
}

/**
 * A `useSpring`: an output that chases a source, re-solving on every change.
 *
 * The library ticks the animation in the frame's update step and schedules the
 * retarget at that same frame's postRender, so a new solve always starts from
 * the value the animation just produced. `setTarget` therefore advances to now
 * before it re-solves -- retargeting from a stale value freezes the spring on
 * every frame that carries input, which during a drag is most of them.
 */
export class Spring {
  value: number;
  target: number;
  private solver: SpringSolver | null = null;
  private t0 = 0;
  private vel = 0;

  constructor(readonly cfg: SpringConfig, initial = 0) {
    this.value = initial;
    this.target = initial;
  }

  static of(name: keyof typeof SPRINGS, initial = 0): Spring {
    const s = SPRINGS[name] as unknown as SpringConfig;
    return new Spring({ stiffness: s.stiffness, damping: s.damping, mass: s.mass,
                        restDelta: s.restDelta, restSpeed: s.restSpeed }, initial);
  }

  setTarget(target: number, nowMs: number): void {
    this.advance(nowMs);
    if (target === this.target && this.solver !== null) return;
    this.target = target;
    if (target === this.value) { this.solver = null; this.vel = 0; return; }
    this.solver = new SpringSolver(this.value, target, this.vel, this.cfg);
    this.t0 = nowMs;
  }

  advance(nowMs: number): number {
    if (this.solver === null) return this.value;
    const t = nowMs - this.t0;
    if (this.solver.done(t)) {
      this.value = this.solver.to;
      this.vel = 0;
      this.solver = null;
      return this.value;
    }
    this.value = this.solver.value(t);
    this.vel = this.solver.velocity(t);
    return this.value;
  }

  get velocity(): number { return this.vel; }

  reset(value = 0): void {
    this.value = value; this.target = value; this.solver = null; this.t0 = 0; this.vel = 0;
  }
}

/** The Target's gesture velocity window, in ms. Read from the contract. */
export const SOURCE_EXACT_VELOCITY_WINDOW_MS: number = VELOCITY.sampleWindowMs;

export type PanInfo = { point: [number, number]; delta: [number, number];
                        offset: [number, number]; velocity: [number, number] };

/**
 * framer-motion's PanSession, transcribed.
 *
 * Three behaviours here are load-bearing and none of them is obvious:
 *
 *  - the gesture does not start until the pointer has moved 3 px from where it
 *    went down, and nothing is pushed to history before that, so the first
 *    delta that does fire carries the whole pre-threshold movement;
 *  - dispatch is scheduled with keepAlive, so it re-runs EVERY frame while the
 *    gesture is alive, not only on frames that carried a move. A stationary
 *    finger keeps pushing the same point with a fresh timestamp, so after about
 *    100 ms of stillness the velocity window holds only identical points and the
 *    measured velocity is zero: hold still before letting go and there is no
 *    fling at all;
 *  - the info is built from the history BEFORE the current point is pushed, so
 *    the reported velocity lags by one dispatch. The fling multiplies it, so
 *    this is worth a line of comment rather than a silent simplification.
 *
 * It never takes pointer capture: it listens on the window in the capture
 * phase, which is why `lostpointercapture` plays no part in it.
 */
export class PanSession {
  private history: Array<[number, number, number]> = [];
  private pending: [number, number] | null = null;
  started = false;
  active = false;

  /* ---- QA-only readback ------------------------------------------------
   *
   * The velocity window this session last used, recorded as it is used. It is
   * WRITTEN by `velocityOfHistory` and read by nothing: no branch below
   * consults it, so the velocity computed with it present is the velocity
   * computed without it. It exists because the M2 round had to infer the
   * release window from an external scroll curve and could not settle five
   * runs; a window that is recorded cannot be mis-inferred.
   */
  lastVelocityWindow: {
    historyCount: number;
    newest: [number, number, number] | null;
    oldest: [number, number, number] | null;
    dtMs: number;
    velocity: [number, number];
    clampedToSecondPoint: boolean;
  } | null = null;

  /** A copy of the gesture history, for evidence. Never read back. */
  historySnapshot(): Array<[number, number, number]> {
    return this.history.map((h) => [h[0], h[1], h[2]] as [number, number, number]);
  }

  down(x: number, y: number, t: number): void {
    this.active = true;
    this.started = false;
    this.history = [[x, y, t]];
    this.pending = null;
  }

  move(x: number, y: number): void {
    this.pending = [x, y];
  }

  /** One frame's dispatch. */
  frame(t: number): PanInfo | null {
    if (!this.active || this.pending === null) return null;
    const [x, y] = this.pending;
    const origin = this.history[0];
    const offset: [number, number] = [x - origin[0], y - origin[1]];
    if (!this.started && Math.hypot(offset[0], offset[1]) < GESTURE.distanceThresholdPx) {
      return null;
    }
    const last = this.history[this.history.length - 1];
    const info: PanInfo = { point: [x, y], delta: [x - last[0], y - last[1]],
                            offset, velocity: this.velocityOfHistory() };
    this.history.push([x, y, t]);
    this.started = true;
    return info;
  }

  /** Release info. A gesture that never passed the threshold produces nothing. */
  up(x: number, y: number, cancelled = false): PanInfo | null {
    if (!this.active) return null;
    this.active = false;
    if (!this.started) return null;
    // pointercancel reports from the last MOVE, not from the cancel point.
    if (cancelled && this.history.length) {
      const last = this.history[this.history.length - 1];
      x = last[0]; y = last[1];
    }
    const last = this.history[this.history.length - 1];
    return { point: [x, y], delta: [x - last[0], y - last[1]],
             offset: [x - this.history[0][0], y - this.history[0][1]],
             velocity: this.velocityOfHistory() };
  }

  private velocityOfHistory(): [number, number] {
    const h = this.history;
    if (h.length < 2) { this.recordWindow(h.length, null, null, 0, [0, 0], false); return [0, 0]; }
    const newest = h[h.length - 1];
    let i = h.length - 1;
    let oldest: [number, number, number] | null = null;
    while (i >= 0) {
      oldest = h[i];
      if (newest[2] - oldest[2] > VELOCITY.sampleWindowMs) break;
      i -= 1;
    }
    if (!oldest) { this.recordWindow(h.length, newest, null, 0, [0, 0], false); return [0, 0]; }
    let clamped = false;
    if (oldest === h[0] && h.length > 2
        && newest[2] - oldest[2] > 2 * VELOCITY.sampleWindowMs) {
      oldest = h[1];
      clamped = true;
    }
    const dt = (newest[2] - oldest[2]) / 1000;
    if (dt === 0) {
      this.recordWindow(h.length, newest, oldest, 0, [0, 0], clamped);
      return [0, 0];
    }
    const vx = (newest[0] - oldest[0]) / dt;
    const vy = (newest[1] - oldest[1]) / dt;
    const v: [number, number] = [Number.isFinite(vx) ? vx : 0, Number.isFinite(vy) ? vy : 0];
    this.recordWindow(h.length, newest, oldest, dt * 1000, v, clamped);
    return v;
  }

  private recordWindow(count: number, newest: [number, number, number] | null,
                       oldest: [number, number, number] | null, dtMs: number,
                       velocity: [number, number], clamped: boolean): void {
    this.lastVelocityWindow = {
      historyCount: count,
      newest: newest ? [newest[0], newest[1], newest[2]] : null,
      oldest: oldest ? [oldest[0], oldest[1], oldest[2]] : null,
      dtMs, velocity: [velocity[0], velocity[1]], clampedToSecondPoint: clamped,
    };
  }

  reset(): void {
    this.history = []; this.pending = null; this.started = false; this.active = false;
    this.lastVelocityWindow = null;
  }
}

/**
 * `MotionValue.getVelocity()`: a BACKWARD DIFFERENCE, not the spring's own.
 *
 * The magnitude that drives the dolly is not fed from the analytic spring
 * velocity. The bundle sets it from `f.getVelocity()` and `p.getVelocity()` on
 * the two scroll MotionValues, and `getVelocity` there is
 * `(current - prevFrameValue) / min(updatedAt - prevUpdatedAt, 30) * 1000`,
 * returning zero outright once more than 30 ms have passed since the value
 * last changed. The two agree in the middle of a smooth run and disagree
 * exactly where the dolly is most visible: at a direction change, and in the
 * last stretch before the spring comes to rest, where the analytic velocity
 * decays smoothly and this one drops to zero.
 */
class MotionValueVelocity {
  private current = 0;
  private prevFrameValue: number | null = null;
  private updatedAt = 0;
  private prevUpdatedAt = 0;

  update(value: number, nowMs: number): void {
    if (value === this.current) return;
    this.prevFrameValue = this.current;
    this.prevUpdatedAt = this.updatedAt;
    this.current = value;
    this.updatedAt = nowMs;
  }

  velocity(nowMs: number): number {
    if (this.prevFrameValue === null || nowMs - this.updatedAt > 30) return 0;
    const dt = Math.min(this.updatedAt - this.prevUpdatedAt, 30);
    if (dt <= 0) return 0;
    return ((this.current - this.prevFrameValue) / dt) * 1000;
  }

  reset(value = 0): void {
    this.current = value; this.prevFrameValue = null;
    this.updatedAt = 0; this.prevUpdatedAt = 0;
  }
}

/** Scroll, velocity magnitude and pointer, composed as the Target composes them. */
export class SourceExactMotion {
  readonly session = new PanSession();
  readonly scrollX = Spring.of("scroll");
  readonly scrollY = Spring.of("scroll");
  readonly magnitude = Spring.of("magnitude");
  readonly pointerX = Spring.of("pointer");
  readonly pointerY = Spring.of("pointer");
  targetX = 0;
  targetY = 0;
  private readonly mvX = new MotionValueVelocity();
  private readonly mvY = new MotionValueVelocity();
  /** The last gesture velocity, published exactly as the Target publishes it. */
  gestureVelocityX = 0;
  gestureVelocityY = 0;
  /**
   * Which of the magnitude MotionValue's TWO writers writes last in a frame.
   *
   * The Target's magnitude source `g` is written from two places, and they
   * disagree by construction: the gesture writes the FINGER's speed, the
   * scroll MotionValues write the SPRING's, which is the finger's times the
   * 1.5 drag gain minus the spring's own lag. Whichever runs last in the frame
   * is the one the magnitude spring retargets to at that frame's postRender.
   *
   * The order is not a choice; it is read out of the bundle's own scheduler.
   * `onPan` is dispatched with `frame.update(cb, false, true)` -- the third
   * argument appends it to the LIVE update set, so it runs after every spring
   * tick already queued, on every frame the pan session dispatches. `onPanEnd`
   * is scheduled straight onto `postRender` from the pointerup listener, which
   * puts it ahead of the spring's own `startAnimation` in that same postRender
   * pass. So the gesture writer wins every frame that carries a gesture, and
   * the scroll writer stands alone on every frame that does not.
   *
   * Full derivation with byte offsets:
   * qa-v5/motion-final/magnitude-writer-order-source.json.
   */
  magnitudeWriterOrder: "gestureLastWhileActive" | "scrollLastAlways" =
    "gestureLastWhileActive";
  private gestureMagnitude = 0;
  private gestureWroteThisFrame = false;

  /**
   * What the Target's renderer paints THIS frame: the model's PREVIOUS frame.
   *
   * The Target's motion values and the renderer that consumes them run in two
   * different frame callbacks, and the consumer's was registered first -- when
   * the canvas mounted, long before the first gesture started framer-motion's
   * own loop. So what reaches the screen is always one frame behind what the
   * model has computed, and every measurable thing about the Target's motion
   * carries that frame.
   *
   * Not a detail that could be left out and called close enough. Replaying the
   * model against the Target's own recorded trajectory over all 120 non-wheel
   * runs, at four viewports: with no delay the median raw peak error is 3.36%
   * of travel and the best-fit time shift is a systematic +10.5 ms; with one
   * frame, 0.76% and +2.0 ms; with two, 2.16% and -6.0 ms. One frame wins on
   * every sequence and two frames overshoots on every sequence.
   */
  readonly published = { scrollX: 0, scrollY: 0, velocityX: 0, velocityY: 0,
                         magnitude: 0, pointerX: 0, pointerY: 0 };

  /** Snapshot the previous frame's values. Call once, before this frame's input. */
  beginFrame(): void {
    const p = this.published;
    p.scrollX = this.scrollX.value; p.scrollY = this.scrollY.value;
    p.velocityX = this.scrollX.velocity; p.velocityY = this.scrollY.velocity;
    p.magnitude = this.magnitude.value;
    p.pointerX = this.pointerX.value; p.pointerY = this.pointerY.value;
  }

  onPan(info: PanInfo, nowMs: number): void {
    this.targetX += DRAG.gain * info.delta[0];
    this.targetY += DRAG.gain * info.delta[1];
    this.publishVelocity(info, nowMs);
  }

  onPanEnd(info: PanInfo, nowMs: number): void {
    this.targetX += info.velocity[0] * DRAG.fling;
    this.targetY += info.velocity[1] * DRAG.fling;
    this.publishVelocity(info, nowMs);
  }

  /** Writer A: `g.set(hypot(t.velocity.x, t.velocity.y))`, in onPan/onPanEnd. */
  writeMagnitudeFromGesture(magnitude: number, nowMs: number): void {
    this.gestureMagnitude = magnitude;
    this.gestureWroteThisFrame = true;
    this.magnitude.setTarget(magnitude, nowMs);
  }

  /** Writer B: `g.set(hypot(f.getVelocity(), p.getVelocity()))`, in the scroll
   *  MotionValues' own change handlers. */
  writeMagnitudeFromScrollMotionValue(magnitude: number, nowMs: number): void {
    this.magnitude.setTarget(magnitude, nowMs);
  }

  setPointer(ndcX: number, ndcY: number, nowMs: number): void {
    this.pointerX.setTarget(Math.max(-1, Math.min(1, ndcX)), nowMs);
    this.pointerY.setTarget(Math.max(-1, Math.min(1, ndcY)), nowMs);
  }

  private publishVelocity(info: PanInfo, nowMs: number): void {
    this.gestureVelocityX = info.velocity[0];
    this.gestureVelocityY = info.velocity[1];
    this.scrollX.setTarget(this.targetX, nowMs);
    this.scrollY.setTarget(this.targetY, nowMs);
    this.writeMagnitudeFromGesture(Math.hypot(info.velocity[0], info.velocity[1]), nowMs);
  }

  /** Advance every spring to this frame. */
  advance(nowMs: number): void {
    this.scrollX.advance(nowMs);
    this.scrollY.advance(nowMs);
    // The magnitude source is refreshed from the scroll values' own velocities
    // on every change, not only from the gesture. That is what keeps the dolly
    // alive through the whole release, long after the last pointer event. The
    // velocity is the MotionValue backward difference the bundle actually
    // reads, not the spring's analytic one.
    this.mvX.update(this.scrollX.value, nowMs);
    this.mvY.update(this.scrollY.value, nowMs);
    this.writeMagnitudeFromScrollMotionValue(
      Math.hypot(this.mvX.velocity(nowMs), this.mvY.velocity(nowMs)), nowMs);
    // Both writers land in the same frame step and the magnitude spring
    // retargets to whichever wrote LAST. On a frame the gesture dispatched,
    // that is the gesture -- see `magnitudeWriterOrder`.
    if (this.magnitudeWriterOrder === "gestureLastWhileActive" && this.gestureWroteThisFrame) {
      this.magnitude.setTarget(this.gestureMagnitude, nowMs);
    }
    this.gestureWroteThisFrame = false;
    this.magnitude.advance(nowMs);
    this.pointerX.advance(nowMs);
    this.pointerY.advance(nowMs);
  }

  reset(): void {
    this.session.reset();
    this.scrollX.reset(); this.scrollY.reset(); this.magnitude.reset();
    this.pointerX.reset(); this.pointerY.reset();
    this.targetX = 0; this.targetY = 0;
    this.gestureVelocityX = 0; this.gestureVelocityY = 0;
    this.gestureMagnitude = 0; this.gestureWroteThisFrame = false;
    this.mvX.reset(); this.mvY.reset();
    const p = this.published;
    p.scrollX = 0; p.scrollY = 0; p.velocityX = 0; p.velocityY = 0;
    p.magnitude = 0; p.pointerX = 0; p.pointerY = 0;
  }
}

/** Camera position for a smoothed pointer, on the orbit of radius `perspective`. */
export function sourceExactOrbit(pointerX: number, pointerY: number, perspective: number):
    [number, number, number] {
  const g = CONTRACT.camera.orbit.pointerGain;
  const yaw = -(g * pointerX);
  const pitch = g * pointerY;
  return [Math.sin(yaw) * Math.cos(pitch) * perspective,
          Math.sin(pitch) * perspective,
          Math.cos(yaw) * Math.cos(pitch) * perspective];
}

/**
 * The velocity dolly, added to the z of BOTH cameras.
 *
 * The render camera and the CSS3D transform camera sit at the same orbit
 * position AND the same dollied z, so glass and labels never separate. The
 * dolly-free camera in the bundle is a projection and culling concept only --
 * it reproduces the Target's label coverage test, it is not a rendering
 * camera. Zero at rest, so nothing the layout contract measures moves.
 */
/**
 * The Target's dolly scale for a viewport: `0.1 * perspective`.
 *
 * Derived here rather than added to the layout frame -- `SourceExactLayout` is
 * frozen this stage, and the number is a pure function of a field it already
 * publishes. The layout contract states the same law.
 */
export function sourceExactMaxZoomZ(perspective: number): number {
  return CONTRACT.camera.velocityDolly.maxZoomZFactor * perspective;
}

export function sourceExactDolly(magnitude: number, maxZoomZ: number): number {
  if (maxZoomZ <= 0) return 0;
  const r = 3 * maxZoomZ;
  return r * Math.tanh(0.04 * magnitude / r);
}
