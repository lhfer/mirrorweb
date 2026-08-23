import type { GridAppV4 } from "../v4/preview/GridAppV4";

/**
 * The real-device status readout (Final Motion §六, extended for Final Entry §九).
 *
 * Final Entry adds the frame-pacing tail (p99 and the longest frame, not just
 * p95 -- §八 is explicit that an average is not an answer), the CSS3D layer
 * census (mounted / visible / transform writes) and the cold-load entry state,
 * because those are the three things this round changed and a phone is where
 * they most need checking.
 *
 * A phone on the LAN has no console, so the numbers the brief asks for have to
 * be on the glass. This is the only way to get them there, and it is a QA
 * surface, not a product one:
 *
 *  - it mounts ONLY when `status=1` is in the query. Without it this module's
 *    `mount` is never called and nothing is created, so the product page is
 *    byte-identical to a build without it;
 *  - it must be OFF for any capture, recording or review pass. §五 says "no
 *    debug HUD", and this is one;
 *  - it reads the app's existing public readbacks and writes nothing back.
 *    Turning it on cannot change what the page renders.
 *
 * `blackFrames` is a proxy and is named as one. It counts SAMPLES -- not
 * frames -- on which at least one clip element was not decodable
 * (`readyState < HAVE_CURRENT_DATA`, or a zero `videoWidth`), which is the
 * state a card would be drawn black in. It is not a pixel test, and a sample
 * that catches nothing is not proof that no frame was black between samples.
 */

const SAMPLE_MS = 500;

export class StatusReadout {
  private readonly el: HTMLDivElement;
  private timer = 0;
  private blackSamples = 0;
  private samples = 0;

  constructor(private readonly app: GridAppV4) {
    this.el = document.createElement("div");
    this.el.dataset.qaStatus = "1";
    this.el.style.cssText = [
      "position:fixed", "top:8px", "left:8px", "z-index:2147483647",
      "font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace",
      "color:#e8e8e8", "background:rgba(0,0,0,.62)",
      "-webkit-backdrop-filter:blur(6px)", "backdrop-filter:blur(6px)",
      "padding:6px 8px", "border-radius:6px", "white-space:pre",
      "pointer-events:none", "user-select:none",
      "max-width:60vw", "overflow:hidden",
    ].join(";");
    document.body.appendChild(this.el);
    this.tick();
    this.timer = window.setInterval(() => this.tick(), SAMPLE_MS);
  }

  dispose(): void {
    window.clearInterval(this.timer);
    this.el.remove();
  }

  private tick(): void {
    const m = this.app.getMetrics() as Record<string, number | string | boolean>;
    const optics = this.app.getOpticsState() as Record<string, unknown>;
    const cache = this.app.getBodyMaterialCacheTruth() as Record<string, unknown>;
    const media = this.app.getMediaState() as Array<{ readyState: number;
                                                      videoWidth: number }>;
    this.samples += 1;
    if (media.some((v) => v.readyState < 2 || v.videoWidth === 0)) this.blackSamples += 1;
    const fps = typeof m.fps === "number" ? m.fps : 0;
    const rows = [
      `fps        ${fps.toFixed(1)}  p95 ${Number(m.p95FrameMs ?? 0).toFixed(1)}`
        + `  p99 ${Number(m.p99FrameMs ?? 0).toFixed(1)}`
        + `  max ${Number(m.longestFrameMs ?? 0).toFixed(1)} ms`,
      `intro      ${String(m.introState)}`
        + `  ${(Number(m.introProgress ?? 0) * 100).toFixed(0)}%`,
      `css3d      mounted ${String(m.css3dMounted ?? "n/a")}`
        + `  vis ${String(m.css3dVisible ?? "n/a")}`
        + `  writes ${String(m.css3dTransformWrites ?? "n/a")}`,
      `quality    ${String(m.quality)}${m.adaptiveSampler ? "" : "  [adaptive off]"}`,
      `sampleTier ${String(optics.opticalBodySamples ?? "n/a")}`
        + `  body ${String(optics.opticalBody ?? "n/a")}`,
      `cacheSize  ${String(cache.cacheSize ?? "n/a")}`
        + `  tex ${String(cache.rendererTextures ?? "n/a")}`,
      `blackFrame ${this.blackSamples} / ${this.samples} samples`,
      `viewport   ${window.innerWidth}x${window.innerHeight} @${window.devicePixelRatio}`
        + `  ${String(m.backend)}`,
    ];
    this.el.textContent = rows.join("\n");
  }
}

/** Mounted only from the `status=1` branch in the V4 entry. */
export function mountStatusReadout(app: GridAppV4): StatusReadout {
  return new StatusReadout(app);
}
