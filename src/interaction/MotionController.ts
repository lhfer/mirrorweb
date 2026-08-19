import { GRID, MOTION } from "../config";

const TILT = (MOTION.tiltDeg * Math.PI) / 180;

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
  }

  setPointer(x: number, y: number) {
    this.pointerTargetX = clamp(x, -1, 1);
    this.pointerTargetY = clamp(y, -1, 1);
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

  step(dt: number) {
    if (this.paused) return;
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
