import { GRID, MOTION } from "../config";
import { SourceExactMotion, SOURCE_EXACT_VELOCITY_WINDOW_MS, type PanInfo }
  from "./SourceExactMotion";

/** One release, recorded from inside the model. QA evidence; never read back. */
export type ReleaseRecord = {
  recordedAtStep: number;
  commitStep: number;
  cancelled: boolean;
  eventTimeStamp: number;
  listenerEntryTime: number;
  historyCount: number;
  history: Array<[number, number, number]>;
  newestUsed: [number, number, number] | null;
  oldestUsed: [number, number, number] | null;
  windowDtMs: number;
  clampedToSecondPoint: boolean;
  velocityWindowMs: number;
  computedVelocityX: number;
  computedVelocityY: number;
  releasePointX: number; releasePointY: number;
  releaseDeltaX: number; releaseDeltaY: number;
  releaseOffsetX: number; releaseOffsetY: number;
  targetXBeforeRelease: number; targetYBeforeRelease: number;
  flingDeltaX: number; flingDeltaY: number;
  targetXAfterRelease: number; targetYAfterRelease: number;
};

const TILT = (MOTION.tiltDeg * Math.PI) / 180;

/**
 * Motion for both paths.
 *
 * The legacy model -- drag gain, exponential inertia, wheel gain, card tilt,
 * camera parallax, pointer easing, light travel -- is untouched and still runs
 * v1, v2 and the bare route. `enableSourceExact()` swaps in the model read out
 * of the Target's own bundle instead, which shares none of those parts: it has
 * springs where the legacy path has an inertia integrator, no wheel handling
 * at all, and no maximum speed or stop threshold.
 *
 * One class rather than two because everything downstream -- pose, recycling,
 * QA readback -- consumes the same fields; splitting it would mean two
 * readbacks and, sooner or later, two answers to the same question.
 */
export class MotionController {
  scrollX = 0;
  scrollY = 0;
  velocityX = 0;
  velocityY = 0;
  dragging = false;
  paused = false;
  pointerTargetX = 0;
  pointerTargetY = 0;
  pointerX = 0;
  pointerY = 0;
  rotX = 0;
  rotY = 0;
  camX = 0;
  camY = 0;
  lightX = -420;
  lightY = 720;
  private pendingDragX = 0;
  private pendingDragY = 0;
  private pendingDragDt = 0;
  private pendingWheelX = 0;
  private pendingWheelY = 0;
  /** Smoothed |velocity|, the Target's camera-dolly driver. Source-exact only. */
  magnitude = 0;
  private se: SourceExactMotion | null = null;
  private nowMs = 0;

  /** Swap in the Target's model. Irreversible for the lifetime of the app. */
  enableSourceExact(): void {
    this.se = new SourceExactMotion();
  }

  get sourceExact(): boolean {
    return this.se !== null;
  }

  /** The spring's target, not its value. Source-exact only; 0 on the legacy path. */
  get scrollTargetX(): number { return this.se ? this.se.targetX : 0; }
  get scrollTargetY(): number { return this.se ? this.se.targetY : 0; }
  /** Has the gesture passed the 3 px threshold? Source-exact only. */
  get gestureStarted(): boolean { return this.se ? this.se.session.started : this.dragging; }

  get dragSurfaceTakesPointerCapture(): boolean {
    // The Target's PanSession listens on the window in the capture phase and
    // never calls setPointerCapture, which is why lostpointercapture plays no
    // part in its gesture. Reproduced, and exposed so a proof can assert it
    // rather than read it out of a comment.
    return this.se === null;
  }

  reset() {
    this.scrollX = 0;
    this.scrollY = 0;
    this.velocityX = 0;
    this.velocityY = 0;
    this.dragging = false;
    this.pointerTargetX = 0;
    this.pointerTargetY = 0;
    this.pointerX = 0;
    this.pointerY = 0;
    this.rotX = 0;
    this.rotY = 0;
    this.camX = 0;
    this.camY = 0;
    this.lightX = -420;
    this.lightY = 720;
    this.pendingDragX = 0;
    this.pendingDragY = 0;
    this.pendingDragDt = 0;
    this.pendingWheelX = 0;
    this.pendingWheelY = 0;
    this.magnitude = 0;
    this.pendingRelease = null;
    // The QA readbacks are part of the truth this controller publishes, so a
    // reset has to clear them too: a stale releaseVelocity or motionSteps
    // surviving a reset makes a fixed-state capture describe the run before
    // it. Semantics of the readback only -- nothing here feeds the model.
    this.motionSteps = 0;
    this.releaseVelocityX = 0;
    this.releaseVelocityY = 0;
    this.lastReleaseStep = -1;
    this.releaseRecords.length = 0;
    this.se?.reset();
  }

  setPointer(x: number, y: number) {
    this.pointerTargetX = clamp(x, -1, 1);
    this.pointerTargetY = clamp(y, -1, 1);
    // Source-exact: record only. The retarget is COMMITTED on the frame, with
    // that frame's clock, in stepSourceExact -- which is what the Target does:
    // its passive effect records the target and schedules the rebuild on the
    // frame loop, where the new solve is stamped with the frame's own
    // timestamp. Stamping it here would use `this.nowMs`, which is the
    // PREVIOUS frame's time, so the pointer spring would start a frame before
    // the scroll spring and settle sooner than the Target's.
  }

  /**
   * Jump the smoothed pointer, for a harness that needs a fixed state.
   *
   * `setPointer` writes the smoothing TARGET, and `step` carries the applied
   * pointer toward it -- so on a PAUSED page `setPointer` moves nothing, which
   * the T0 render-loop evidence records deliberately. A paused sweep across
   * pointer extremes therefore needs this: the spring value and the applied
   * fields are written too, so the very next `renderOnce` draws the pose.
   */
  jumpPointer(x: number, y: number): void {
    this.pointerTargetX = clamp(x, -1, 1);
    this.pointerTargetY = clamp(y, -1, 1);
    this.pointerX = this.pointerTargetX;
    this.pointerY = this.pointerTargetY;
    if (this.se) {
      this.se.pointerX.reset(this.pointerTargetX);
      this.se.pointerY.reset(this.pointerTargetY);
      this.se.beginFrame();
      // The Target's source-exact pose carries no tilt, no camera translation
      // and no light travel; only the orbit reads the pointer.
      return;
    }
    this.rotX = this.pointerY * TILT;
    this.rotY = -this.pointerX * TILT;
    this.camX = this.pointerX * GRID.cellW * MOTION.parallax;
    this.camY = -this.pointerY * GRID.cellH * MOTION.parallax;
    this.lightX = -420 + this.pointerX * MOTION.lightTravel;
    this.lightY = 720 - this.pointerY * MOTION.lightTravel * 0.7;
  }

  /* ---------------- source-exact gesture input ---------------- */

  /** Raw pointer down, in client pixels. Source-exact only. */
  pointerDown(x: number, y: number, tMs: number): void {
    this.se?.session.down(x, y, tMs);
    if (this.se) this.dragging = true;
  }

  /** Raw pointer move. Stored; the Target dispatches on the frame, not here. */
  pointerMove(x: number, y: number): void {
    this.se?.session.move(x, y);
  }

  /**
   * Raw pointer up or cancel. The gesture ends here; the FLING does not.
   *
   * Applying the fling in the event handler advances the springs to the event
   * timestamp, off the frame grid -- so the next frame publishes a value that
   * already contains a partial extra step, and the release reads as an
   * instantaneous velocity spike instead of a ramp. Measured on a touch
   * release at 1440x900: the first frame after release came out at -7969
   * against the Target's -2889, settling back to agreement within about 20 ms.
   *
   * The Target has no out-of-band path at all. Its pan end is dispatched by
   * the same frame loop as everything else, so the release is just another
   * frame's retarget. Recorded here and applied on the next frame.
   */
  pointerUp(x: number, y: number, tMs: number, cancelled = false,
            qa?: { eventTimeStamp?: number; listenerEntryTime?: number }): void {
    if (!this.se) return;
    const history = this.se.session.historySnapshot();
    const info = this.se.session.up(x, y, cancelled);
    this.dragging = false;
    if (!info) return;
    this.pendingRelease = info;
    const w = this.se.session.lastVelocityWindow;
    this.releaseRecords.push({
      recordedAtStep: this.motionSteps,
      commitStep: -1,
      cancelled,
      eventTimeStamp: qa?.eventTimeStamp ?? tMs,
      listenerEntryTime: qa?.listenerEntryTime ?? tMs,
      historyCount: history.length,
      history,
      newestUsed: w ? w.newest : null,
      oldestUsed: w ? w.oldest : null,
      windowDtMs: w ? w.dtMs : 0,
      clampedToSecondPoint: w ? w.clampedToSecondPoint : false,
      velocityWindowMs: SOURCE_EXACT_VELOCITY_WINDOW_MS,
      computedVelocityX: info.velocity[0],
      computedVelocityY: info.velocity[1],
      releasePointX: info.point[0], releasePointY: info.point[1],
      releaseDeltaX: info.delta[0], releaseDeltaY: info.delta[1],
      releaseOffsetX: info.offset[0], releaseOffsetY: info.offset[1],
      targetXBeforeRelease: this.se.targetX, targetYBeforeRelease: this.se.targetY,
      flingDeltaX: 0, flingDeltaY: 0,
      targetXAfterRelease: 0, targetYAfterRelease: 0,
    });
    if (this.releaseRecords.length > 64) this.releaseRecords.shift();
  }

  private pendingRelease: PanInfo | null = null;

  /**
   * QA-only: the complete truth of every release the model committed.
   *
   * The M2 round could not settle five runs because it had to infer the
   * release window from an external scroll curve: from outside, a pointerup
   * dispatched between two sample callbacks may or may not have been preceded
   * by the page's own frame callback pushing another point into the gesture
   * history, and the two readings give different flings. Nothing outside can
   * see that. So it is recorded from inside instead: the history as it stood,
   * the two points the velocity window actually used, the velocity that came
   * out, and the scroll target either side of the fling.
   *
   * Written, never read. No branch in this file or below it consults this
   * array, and the motion produced with it present is the motion produced
   * without it. Capped so a long session cannot grow it without bound.
   */
  readonly releaseRecords: ReleaseRecord[] = [];

  /* ---- readbacks -------------------------------------------------------
   *
   * Four numbers that answer, from outside, questions the M2 brief asks about
   * scheduling: on which frame did the model actually run, on which frame was
   * a release committed, and with what velocity. They are RECORDED, never
   * read back into the model -- nothing below `step()` consults them and no
   * branch depends on them, so the motion produced with them present is the
   * motion produced without them. They exist because the alternative is to
   * infer the release frame from a curve, which is how the last round put a
   * one-frame attribution error into a product verdict.
   */
  /** Frames of motion this controller has actually integrated. */
  motionSteps = 0;
  /** Velocity carried by the last release the model committed, in px/s. */
  releaseVelocityX = 0;
  releaseVelocityY = 0;
  /** `motionSteps` at the frame that release was committed on; -1 if none. */
  lastReleaseStep = -1;
  /** Releases recorded but not yet committed. 0 or 1 by construction. */
  get pendingReleaseCount(): number { return this.pendingRelease ? 1 : 0; }
  /** The magnitude writer order this build is running. Evidence, not a switch. */
  get magnitudeWriterOrder(): string { return this.se ? this.se.magnitudeWriterOrder : "n/a"; }

  /**
   * Jump the scroll, for a harness that needs a fixed state.
   *
   * On the source-exact path this has to move the spring as well as its
   * target: writing only the target would leave the page sliding into the
   * requested offset over the next second, and a capture taken during that
   * would be of somewhere else.
   */
  setScroll(x: number, y: number): void {
    this.scrollX = x;
    this.scrollY = y;
    // The legacy path keeps its old semantics exactly -- it wrote the two
    // fields and nothing else, and a harness that relied on carrying a
    // velocity across a jump must keep working.
    if (!this.se) return;
    this.velocityX = 0;
    this.velocityY = 0;
    this.se.targetX = x;
    this.se.targetY = y;
    this.se.scrollX.reset(x);
    this.se.scrollY.reset(y);
    this.se.magnitude.reset(0);
    this.magnitude = 0;
    // A jump is a fixed state, not a frame of motion: the one-frame render
    // delay would otherwise hold the page at the OLD offset for a capture that
    // never steps again.
    this.se.beginFrame();
  }

  /**
   * Hand the model a release velocity, for a harness that needs a repeatable
   * flick. It goes through the SAME path a real release takes -- the fling
   * term -- rather than writing a velocity field the source-exact model does
   * not have. Evidence recordings still use real input; this exists for fixed
   * states, not for recordings.
   */
  setReleaseVelocity(x: number, y: number): void {
    this.velocityX = x;
    this.velocityY = y;
    if (!this.se) return;
    this.releaseVelocityX = x;
    this.releaseVelocityY = y;
    this.lastReleaseStep = this.motionSteps;
    this.se.onPanEnd({ point: [0, 0], delta: [0, 0], offset: [0, 0], velocity: [x, y] },
                     this.nowMs);
  }

  beginDrag() {
    this.dragging = true;
  }

  queueDrag(dx: number, dy: number, dt: number) {
    this.pendingDragX += dx;
    this.pendingDragY += dy;
    this.pendingDragDt += dt;
  }

  queueWheel(dx: number, dy: number) {
    this.pendingWheelX += dx;
    this.pendingWheelY += dy;
  }

  endDrag() {
    this.dragging = false;
  }

  step(dt: number, nowMs?: number) {
    if (this.paused) return;
    this.motionSteps += 1;
    this.nowMs = nowMs ?? (this.nowMs + dt * 1000);
    if (this.se) { this.stepSourceExact(this.nowMs); return; }
    this.consumeDrag(dt);
    this.consumeWheel();
    if (!this.dragging) this.integrateInertia(dt);
    this.easePointer(dt);
    this.rotX = this.pointerY * TILT;
    this.rotY = -this.pointerX * TILT;
    this.camX = this.pointerX * GRID.cellW * MOTION.parallax;
    this.camY = -this.pointerY * GRID.cellH * MOTION.parallax;
    this.lightX = -420 + this.pointerX * MOTION.lightTravel;
    this.lightY = 720 - this.pointerY * MOTION.lightTravel * 0.7;
  }

  /**
   * One frame of the Target's model.
   *
   * The pan dispatch runs every frame while the gesture is alive, not only on
   * frames that carried a move -- that is what makes the velocity decay to
   * zero when a finger holds still, and with it the fling.
   */
  private stepSourceExact(nowMs: number) {
    const se = this.se!;
    // What the Target PAINTS this frame is what its model produced LAST frame:
    // its renderer and framer-motion's loop are two different frame callbacks
    // and the renderer's runs first. Snapshot before this frame's input, then
    // tick -- so the pose applied below is one frame behind the model, as the
    // Target's is. See SourceExactMotion.beginFrame for the measurement.
    se.beginFrame();
    // Commit the pointer target on THIS frame's clock, beside the scroll path.
    se.setPointer(this.pointerTargetX, this.pointerTargetY, nowMs);
    const info: PanInfo | null = se.session.frame(nowMs);
    if (info) se.onPan(info, nowMs);
    // The release, on the frame -- never in the event handler.
    if (this.pendingRelease) {
      this.releaseVelocityX = this.pendingRelease.velocity[0];
      this.releaseVelocityY = this.pendingRelease.velocity[1];
      this.lastReleaseStep = this.motionSteps;
      const beforeX = se.targetX, beforeY = se.targetY;
      se.onPanEnd(this.pendingRelease, nowMs);
      const rec = this.releaseRecords[this.releaseRecords.length - 1];
      if (rec && rec.commitStep < 0) {
        rec.commitStep = this.motionSteps;
        rec.targetXBeforeRelease = beforeX;
        rec.targetYBeforeRelease = beforeY;
        rec.targetXAfterRelease = se.targetX;
        rec.targetYAfterRelease = se.targetY;
        rec.flingDeltaX = se.targetX - beforeX;
        rec.flingDeltaY = se.targetY - beforeY;
      }
      this.pendingRelease = null;
    }
    se.advance(nowMs);
    const p = se.published;
    this.scrollX = p.scrollX;
    this.scrollY = p.scrollY;
    this.velocityX = p.velocityX;
    this.velocityY = p.velocityY;
    this.magnitude = p.magnitude;
    this.dragging = se.session.active;
    this.pointerX = p.pointerX;
    this.pointerY = p.pointerY;
    // The Target tilts nothing, translates nothing and moves no light. Held at
    // zero rather than left stale, so a readback cannot report a pose the
    // source-exact path never applies.
    this.rotX = 0; this.rotY = 0; this.camX = 0; this.camY = 0;
    this.lightX = -420; this.lightY = 720;
  }

  private consumeDrag(dt: number) {
    if (this.pendingDragX === 0 && this.pendingDragY === 0) return;
    const gx = this.pendingDragX * MOTION.dragGain;
    const gy = this.pendingDragY * MOTION.dragGain;
    this.scrollX -= gx;
    this.scrollY += gy;
    const sampleDt = this.pendingDragDt > 1e-4 ? this.pendingDragDt : dt;
    if (Math.hypot(gx, gy) > 0.15) {
      this.velocityX = -gx / sampleDt;
      this.velocityY = gy / sampleDt;
      this.clampSpeed();
    }
    this.pendingDragX = 0;
    this.pendingDragY = 0;
    this.pendingDragDt = 0;
  }

  private consumeWheel() {
    if (this.pendingWheelX === 0 && this.pendingWheelY === 0) return;
    const gx = this.pendingWheelX * MOTION.wheelGain;
    const gy = this.pendingWheelY * MOTION.wheelGain;
    this.scrollX += gx;
    this.scrollY += gy;
    this.velocityX += gx * 4;
    this.velocityY += gy * 4;
    this.clampSpeed();
    this.pendingWheelX = 0;
    this.pendingWheelY = 0;
  }

  private integrateInertia(dt: number) {
    const damp = Math.exp(-MOTION.damping * dt);
    this.velocityX *= damp;
    this.velocityY *= damp;
    const speed = Math.hypot(this.velocityX, this.velocityY);
    if (speed < MOTION.stopThreshold) {
      this.velocityX = 0;
      this.velocityY = 0;
      return;
    }
    this.scrollX += this.velocityX * dt;
    this.scrollY += this.velocityY * dt;
  }

  private easePointer(dt: number) {
    const k = 1 - Math.exp(-MOTION.pointerDamping * dt);
    this.pointerX += (this.pointerTargetX - this.pointerX) * k;
    this.pointerY += (this.pointerTargetY - this.pointerY) * k;
    if (Math.abs(this.pointerTargetX - this.pointerX) < 1e-4) this.pointerX = this.pointerTargetX;
    if (Math.abs(this.pointerTargetY - this.pointerY) < 1e-4) this.pointerY = this.pointerTargetY;
  }

  private clampSpeed() {
    const speed = Math.hypot(this.velocityX, this.velocityY);
    if (speed > MOTION.maxSpeed) {
      const s = MOTION.maxSpeed / speed;
      this.velocityX *= s;
      this.velocityY *= s;
    }
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}
