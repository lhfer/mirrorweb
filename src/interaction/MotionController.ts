import { GRID, MOTION } from "../config";
import { SourceExactMotion, type PanInfo } from "./SourceExactMotion";

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
  pointerUp(x: number, y: number, tMs: number, cancelled = false): void {
    if (!this.se) return;
    const info = this.se.session.up(x, y, cancelled);
    this.dragging = false;
    if (info) this.pendingRelease = info;
  }

  private pendingRelease: PanInfo | null = null;

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
      se.onPanEnd(this.pendingRelease, nowMs);
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
