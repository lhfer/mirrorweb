import {
  CanvasTexture,
  EquirectangularReflectionMapping,
  LinearFilter,
  SRGBColorSpace,
} from "three/webgpu";

/**
 * Small procedural studio environment used by the isolated optics lab.
 * It contains no external or target-site pixels and can be regenerated from
 * source. The physical reflection shell consumes it through Scene.environment.
 */
export function createStripLightEnvironmentV4(): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2D canvas unavailable for V4 strip-light environment");

  const base = context.createLinearGradient(0, 0, 0, canvas.height);
  base.addColorStop(0, "#020304");
  base.addColorStop(0.45, "#111719");
  base.addColorStop(0.58, "#070a0b");
  base.addColorStop(1, "#010203");
  context.fillStyle = base;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const strips = [
    { x: 138, width: 66, color: "248,250,242", peak: 0.98 },
    { x: 392, width: 34, color: "205,232,236", peak: 0.74 },
    { x: 735, width: 92, color: "255,240,215", peak: 0.9 },
    { x: 956, width: 25, color: "213,236,255", peak: 0.58 },
  ];
  for (const strip of strips) {
    const gradient = context.createLinearGradient(strip.x - strip.width, 0, strip.x + strip.width, 0);
    gradient.addColorStop(0, `rgba(${strip.color},0)`);
    gradient.addColorStop(0.32, `rgba(${strip.color},${strip.peak * 0.18})`);
    gradient.addColorStop(0.48, `rgba(${strip.color},${strip.peak})`);
    gradient.addColorStop(0.52, `rgba(${strip.color},${strip.peak})`);
    gradient.addColorStop(0.68, `rgba(${strip.color},${strip.peak * 0.18})`);
    gradient.addColorStop(1, `rgba(${strip.color},0)`);
    context.fillStyle = gradient;
    context.fillRect(strip.x - strip.width, 70, strip.width * 2, 285);
  }

  const horizon = context.createLinearGradient(0, 315, 0, 430);
  horizon.addColorStop(0, "rgba(255,255,255,0)");
  horizon.addColorStop(0.48, "rgba(210,222,218,0.2)");
  horizon.addColorStop(0.54, "rgba(255,255,255,0.08)");
  horizon.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = horizon;
  context.fillRect(0, 315, canvas.width, 115);

  const environment = new CanvasTexture(canvas);
  environment.name = "MirrorWeb.V4.ProceduralStripLightEnvironment";
  environment.mapping = EquirectangularReflectionMapping;
  environment.colorSpace = SRGBColorSpace;
  environment.minFilter = LinearFilter;
  environment.magFilter = LinearFilter;
  environment.generateMipmaps = true;
  environment.needsUpdate = true;
  environment.userData.source = "procedural-no-external-assets";
  return environment;
}
