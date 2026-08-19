import type { MotionController } from "./MotionController";

export class InputController {
  private lastX = 0;
  private lastY = 0;
  private lastT = 0;
  private pointerId: number | null = null;
  private viewW = 1;
  private viewH = 1;
  downs = 0;

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly motion: MotionController,
    private readonly onUnlock?: () => void,
  ) {
    this.onPointerDown = this.onPointerDown.bind(this);
    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerUp = this.onPointerUp.bind(this);
    this.onWheel = this.onWheel.bind(this);
    this.setViewSize(window.innerWidth, window.innerHeight);
    window.addEventListener("pointerdown", this.onPointerDown, { capture: true });
    window.addEventListener("pointermove", this.onPointerMove, { capture: true });
    window.addEventListener("pointerup", this.onPointerUp, { capture: true });
    window.addEventListener("pointercancel", this.onPointerUp, { capture: true });
    window.addEventListener("wheel", this.onWheel, { passive: false, capture: true });
  }

  setViewSize(width: number, height: number) {
    this.viewW = Math.max(1, width);
    this.viewH = Math.max(1, height);
  }

  dispose() {
    window.removeEventListener("pointerdown", this.onPointerDown, true);
    window.removeEventListener("pointermove", this.onPointerMove, true);
    window.removeEventListener("pointerup", this.onPointerUp, true);
    window.removeEventListener("pointercancel", this.onPointerUp, true);
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
    this.motion.beginDrag();
    try {
      this.canvas.setPointerCapture?.(event.pointerId);
    } catch {
      // capture is optional
    }
  }

  private onPointerMove(event: PointerEvent) {
    this.motion.setPointer(this.ndcX(event.clientX), this.ndcY(event.clientY));
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
    if (!this.motion.dragging) return;
    if (this.pointerId !== null && event.pointerId !== this.pointerId) return;
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
