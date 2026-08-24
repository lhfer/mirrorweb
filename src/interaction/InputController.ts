import type { MotionController } from "./MotionController";

/**
 * Input for both paths.
 *
 * The legacy path accumulates a drag delta with its own timestamp and hands it
 * to the legacy model; it is untouched. The source-exact path forwards the raw
 * pointer instead, because the Target's gesture layer does its own history,
 * its own 3 px threshold and its own 100 ms velocity window, and a controller
 * that pre-digested the movement would be answering a different question.
 *
 * Two differences on the source-exact path are deliberate and both come from
 * the Target:
 *
 *  - no pointer capture. The Target listens on the window in the capture phase
 *    and never calls setPointerCapture, so `lostpointercapture` cannot strand
 *    a gesture -- there is nothing to lose.
 *  - no wheel listener at all. The Target registers none; the only
 *    addEventListener("wheel") in its whole bundle is inside three.js
 *    OrbitControls, which it never mounts. So wheel and trackpad move nothing,
 *    at any deltaMode. Not registering is the faithful reproduction, and it
 *    also leaves the page's own default behaviour alone rather than
 *    preventing it.
 */
export class InputController {
  private lastX = 0;
  private lastY = 0;
  private lastT = 0;
  private pointerId: number | null = null;
  private viewW = 1;
  private viewH = 1;
  downs = 0;
  /** Read back rather than inferred: the Target registers none, and so must we. */
  readonly wheelListenerRegistered: boolean;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly motion: MotionController,
    private readonly onUnlock?: () => void,
  ) {
    this.onPointerDown = this.onPointerDown.bind(this);
    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerUp = this.onPointerUp.bind(this);
    this.onPointerCancel = this.onPointerCancel.bind(this);
    this.onLostPointerCapture = this.onLostPointerCapture.bind(this);
    this.onWheel = this.onWheel.bind(this);
    this.setViewSize(window.innerWidth, window.innerHeight);
    this.wheelListenerRegistered = !this.motion.sourceExact;
    window.addEventListener("pointerdown", this.onPointerDown, { capture: true });
    window.addEventListener("pointermove", this.onPointerMove, { capture: true });
    window.addEventListener("pointerup", this.onPointerUp, { capture: true });
    window.addEventListener("pointercancel", this.onPointerCancel, { capture: true });
    if (!this.motion.sourceExact) {
      this.canvas.addEventListener("lostpointercapture", this.onLostPointerCapture);
      window.addEventListener("wheel", this.onWheel, { passive: false, capture: true });
    }
  }

  setViewSize(width: number, height: number) {
    this.viewW = Math.max(1, width);
    this.viewH = Math.max(1, height);
  }

  dispose() {
    window.removeEventListener("pointerdown", this.onPointerDown, true);
    window.removeEventListener("pointermove", this.onPointerMove, true);
    window.removeEventListener("pointerup", this.onPointerUp, true);
    window.removeEventListener("pointercancel", this.onPointerCancel, true);
    this.canvas.removeEventListener("lostpointercapture", this.onLostPointerCapture);
    window.removeEventListener("wheel", this.onWheel, true);
  }

  private onPointerDown(event: PointerEvent) {
    if (event.button !== 0) return;
    if ((event.target as HTMLElement | null)?.closest?.("a")) return;
    this.pointerId = event.pointerId;
    this.lastX = event.clientX;
    this.lastY = event.clientY;
    this.lastT = performance.now();
    this.downs += 1;
    this.onUnlock?.();
    this.motion.setPointer(this.ndcX(event.clientX), this.ndcY(event.clientY));
    if (this.motion.sourceExact) {
      this.motion.pointerDown(event.clientX, event.clientY, event.timeStamp);
      return;
    }
    this.motion.beginDrag();
    try {
      this.canvas.setPointerCapture?.(event.pointerId);
    } catch {
      // capture is optional
    }
  }

  private onPointerMove(event: PointerEvent) {
    this.motion.setPointer(this.ndcX(event.clientX), this.ndcY(event.clientY));
    if (this.motion.sourceExact) {
      if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
      this.motion.pointerMove(event.clientX, event.clientY);
      return;
    }
    if (!this.motion.dragging) return;
    if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
    const now = performance.now();
    const dt = Math.max((now - this.lastT) / 1000, 1 / 240);
    this.motion.queueDrag(event.clientX - this.lastX, event.clientY - this.lastY, dt);
    this.lastX = event.clientX;
    this.lastY = event.clientY;
    this.lastT = now;
  }

  private onPointerUp(event: PointerEvent) {
    this.motion.setPointer(this.ndcX(event.clientX), this.ndcY(event.clientY));
    if (this.motion.sourceExact) {
      if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
      // The two clocks the release evidence needs, taken where they are true:
      // the event's own timestamp, and the moment this listener was entered.
      // Recorded by the controller, read back by nothing.
      this.motion.pointerUp(event.clientX, event.clientY, event.timeStamp, false,
                            { eventTimeStamp: event.timeStamp,
                              listenerEntryTime: performance.now() });
      this.pointerId = null;
      return;
    }
    if (!this.motion.dragging) return;
    if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
    this.motion.endDrag();
    this.pointerId = null;
  }

  /**
   * A cancelled pointer ends the gesture like a release, but the Target
   * measures the release from the last MOVE rather than from the cancel point.
   * The legacy path has no such distinction and keeps its old handler.
   */
  private onPointerCancel(event: PointerEvent) {
    if (!this.motion.sourceExact) { this.onPointerUp(event); return; }
    if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
    this.motion.pointerUp(event.clientX, event.clientY, event.timeStamp, true,
                          { eventTimeStamp: event.timeStamp,
                            listenerEntryTime: performance.now() });
    this.pointerId = null;
  }

  /**
   * Capture can be taken away without a pointerup ever arriving. Without this
   * the controller would stay in `dragging` forever and the release velocity
   * would never be handed to the motion model.
   */
  private onLostPointerCapture(event: PointerEvent) {
    if (this.pointerId === null || event.pointerId !== this.pointerId) return;
    if (!this.motion.dragging) {
      this.pointerId = null;
      return;
    }
    this.motion.endDrag();
    this.pointerId = null;
  }

  private onWheel(event: WheelEvent) {
    if ((event.target as HTMLElement | null)?.closest?.("a")) return;
    event.preventDefault();
    this.motion.queueWheel(event.deltaX, event.deltaY);
  }

  private ndcX(clientX: number) {
    return (clientX / this.viewW) * 2 - 1;
  }

  private ndcY(clientY: number) {
    return (clientY / this.viewH) * 2 - 1;
  }
}
