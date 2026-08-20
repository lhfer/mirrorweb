/**
 * 2D annotation layer for `?foundation=layout`.
 *
 * Draws each card's projected quad, its centre cross and its `i,j` index over
 * the grey slabs, so the projected geometry the engine actually produces can be
 * read straight off the screen and compared with the Target landmarks.
 */

export type FoundationCard = {
  i: number;
  j: number;
  slotIndex: number;
  /** Normalised screen space, [0..1] with y down — as getCardQuads() returns. */
  quad: number[][];
};

export class FoundationOverlay {
  readonly canvas = document.createElement("canvas");
  private ctx: CanvasRenderingContext2D;
  private width = 1;
  private height = 1;
  private dpr = 1;

  constructor(host: HTMLElement) {
    this.canvas.style.cssText =
      "position:absolute;inset:0;z-index:6;pointer-events:none;display:block";
    host.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d")!;
  }

  setSize(width: number, height: number, dpr = 1): void {
    this.width = width;
    this.height = height;
    this.dpr = dpr;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  draw(cards: FoundationCard[]): void {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    ctx.lineWidth = 1;
    ctx.font = "12px ui-monospace, Menlo, monospace";
    ctx.textBaseline = "top";

    for (const card of cards) {
      const pts = card.quad.map(([nx, ny]) => [nx * this.width, ny * this.height] as const);
      const xs = pts.map((p) => p[0]);
      const ys = pts.map((p) => p[1]);
      if (Math.max(...xs) < -80 || Math.min(...xs) > this.width + 80) continue;
      if (Math.max(...ys) < -80 || Math.min(...ys) > this.height + 80) continue;

      ctx.strokeStyle = "rgba(255,72,72,0.95)";
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let n = 1; n < pts.length; n += 1) ctx.lineTo(pts[n][0], pts[n][1]);
      ctx.closePath();
      ctx.stroke();

      const cx = xs.reduce((a, b) => a + b, 0) / xs.length;
      const cy = ys.reduce((a, b) => a + b, 0) / ys.length;
      ctx.strokeStyle = "rgba(64,255,160,0.95)";
      ctx.beginPath();
      ctx.moveTo(cx - 10, cy);
      ctx.lineTo(cx + 10, cy);
      ctx.moveTo(cx, cy - 10);
      ctx.lineTo(cx, cy + 10);
      ctx.stroke();

      ctx.fillStyle = "rgba(64,255,160,0.95)";
      ctx.fillText(`${card.i},${card.j}`, cx + 13, cy - 16);
      ctx.fillStyle = "rgba(255,255,255,0.55)";
      ctx.fillText(`#${card.slotIndex}`, cx + 13, cy + 2);
    }

    // Viewport centre reticle: at rest the Target puts a horizontal gutter here.
    ctx.strokeStyle = "rgba(120,180,255,0.9)";
    ctx.setLineDash([6, 6]);
    ctx.beginPath();
    ctx.moveTo(0, this.height / 2);
    ctx.lineTo(this.width, this.height / 2);
    ctx.moveTo(this.width / 2, 0);
    ctx.lineTo(this.width / 2, this.height);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  dispose(): void {
    this.canvas.remove();
  }
}
