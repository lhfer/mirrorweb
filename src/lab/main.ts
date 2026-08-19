import "../style.css";
import "./lab.css";
import {
  ACESFilmicToneMapping,
  Color,
  Group,
  Mesh,
  MeshBasicMaterial,
  NoToneMapping,
  PerspectiveCamera,
  PlaneGeometry,
  RenderTarget,
  Scene,
  Vector3,
  WebGPURenderer,
} from "three/webgpu";
import { CSS3DObject, CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { CAMERA, CLEAR_COLOR, GLASS, TILE } from "../config";
import { createTestPattern, paintPattern, TEST_BACKGROUNDS, type TestBackground } from "../content/TestPatterns";
import { isGlassDebug, readDebugMode, type DebugMode, type GlassDebugMode } from "../debug/DebugMode";
import { createGlassMaterial, createGlassParams, setGlassParam, type GlassParamSet } from "../materials/LiquidGlassMaterial";
import { detectBackend, resolveDpr } from "../quality/DeviceProfile";
import { addStudioLights, createStudioEnvironment } from "../rendering/StudioEnvironment";
import { createConvexGlassGeometry } from "../scene/ConvexGlassGeometry";
import { MotionController } from "../interaction/MotionController";

const params = createGlassParams();
const motion = new MotionController();
const _look = new Vector3();

const debugMode = readDebugMode();
document.body.dataset.debug = debugMode;

const viewport = document.getElementById("viewport")!;
const labelsHost = document.getElementById("labels")!;
const panel = document.getElementById("lab-panel")!;

const canvas = document.createElement("canvas");
viewport.appendChild(canvas);

const backend = await detectBackend(new URLSearchParams(location.search).get("gl") === "1");
const renderer = new WebGPURenderer({
  canvas,
  antialias: true,
  alpha: false,
  forceWebGL: backend === "webgl2",
});
await renderer.init();
renderer.setClearColor(new Color(CLEAR_COLOR), 1);
renderer.toneMapping = ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new Scene();
scene.background = new Color(CLEAR_COLOR);
const camera = new PerspectiveCamera(CAMERA.fov, 1, CAMERA.near, CAMERA.far);
const lights = addStudioLights(scene);
scene.environment = createStudioEnvironment(renderer);

const pattern = createTestPattern("checker");
const sceneTarget = new RenderTarget(1, 1);
const glassDebug: GlassDebugMode | "off" = isGlassDebug(debugMode) ? debugMode : "off";
const handle = createGlassMaterial(sceneTarget.texture, params, glassDebug);
const glass = new Mesh(createConvexGlassGeometry("high"), handle.material);
const card = new Group();
card.add(glass);
scene.add(card);

const back = new Mesh(new PlaneGeometry(TILE.width * 2.4, TILE.height * 2.4), new MeshBasicMaterial({ map: pattern, toneMapped: false }));
back.position.z = -80;
scene.add(back);

const css = new CSS3DRenderer();
css.domElement.style.position = "absolute";
css.domElement.style.inset = "0";
css.domElement.style.pointerEvents = "none";
labelsHost.appendChild(css.domElement);
const typeEl = document.createElement("div");
typeEl.className = "tile-card lab-type";
typeEl.style.width = `${TILE.width}px`;
typeEl.style.height = `${TILE.height}px`;
typeEl.style.containerType = "inline-size";
typeEl.innerHTML = `
  <div class="tile-card-top"><span>GLASS LAB</span><span>ILG—00</span></div>
  <div class="tile-card-bottom"><h2>Single Lens</h2><div class="tile-rule"></div><p class="tile-deck">The slab samples the scene behind it. Type stays in front.</p></div>
`;
const typeObj = new CSS3DObject(typeEl);
const cssScene = new Scene();
cssScene.add(typeObj);

let background: TestBackground = "checker";
let lastT = performance.now();
let paused = false;
let visible = true;

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const dpr = resolveDpr(backend);
  renderer.setPixelRatio(dpr);
  renderer.setSize(width, height, false);
  sceneTarget.setSize(Math.max(1, Math.floor(width * dpr)), Math.max(1, Math.floor(height * dpr)));
  canvas.style.width = "100%";
  canvas.style.height = "100%";
  camera.aspect = width / height;
  camera.fov = (2 * Math.atan(height / 2 / CAMERA.perspectivePx) * 180) / Math.PI;
  camera.updateProjectionMatrix();
  css.setSize(width, height);
}

function applyPose() {
  card.rotation.set(motion.rotX, motion.rotY, 0);
  camera.position.set(motion.camX - 70, CAMERA.y + motion.camY, 780);
  camera.lookAt(_look.set(motion.camX - 70, CAMERA.lookY + motion.camY, 0));
  lights.key.position.set(motion.lightX, motion.lightY, 1100);
  typeObj.position.set(0, 0, TILE.thickness * 0.5 + TILE.frontBulge + 6).applyQuaternion(card.quaternion);
  typeObj.quaternion.copy(card.quaternion);
}

function setBackground(next: TestBackground) {
  background = next;
  const ctx = (pattern.image as HTMLCanvasElement).getContext("2d");
  if (!ctx) return;
  paintPattern(ctx, next, pattern.image.width as number, pattern.image.height as number, 0);
  pattern.needsUpdate = true;
  syncPanel();
}

function ndc(clientX: number, clientY: number) {
  return {
    x: (clientX / window.innerWidth) * 2 - 1,
    y: (clientY / window.innerHeight) * 2 - 1,
  };
}

window.addEventListener("pointermove", (event) => {
  const p = ndc(event.clientX, event.clientY);
  motion.setPointer(p.x, p.y);
});
window.addEventListener("resize", resize);
document.addEventListener("visibilitychange", () => {
  visible = document.visibilityState === "visible";
  if (visible) lastT = performance.now();
});

function slider(key: keyof GlassParamSet, label: string, min: number, max: number, step: number) {
  const wrap = document.createElement("label");
  const name = document.createElement("span");
  const value = document.createElement("span");
  const input = document.createElement("input");
  input.type = "range";
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.value = String(params[key].value);
  name.textContent = label;
  value.textContent = Number(params[key].value).toFixed(3);
  input.addEventListener("input", () => {
    setGlassParam(params, key, Number(input.value));
    value.textContent = Number(input.value).toFixed(3);
  });
  wrap.append(name, value, input);
  return wrap;
}

function syncPanel() {
  for (const button of panel.querySelectorAll<HTMLButtonElement>("[data-bg]")) {
    button.classList.toggle("is-on", button.dataset.bg === background);
  }
}

function mountPanel() {
  panel.innerHTML = `<h1>Glass Lab</h1><p>One convex volume. A background pass is sampled through the lens, including neighbors and gutters.</p>`;
  const row = document.createElement("div");
  row.className = "lab-row";
  for (const kind of TEST_BACKGROUNDS) {
    const button = document.createElement("button");
    button.dataset.bg = kind;
    button.textContent = kind;
    button.addEventListener("click", () => setBackground(kind));
    row.append(button);
  }
  panel.append(row);
  panel.append(
    slider("ior", "IOR", 1.1, 2.2, 0.01),
    slider("warp", "Warp", 0, 0.4, 0.005),
    slider("rimPower", "Rim power", 0.6, 3, 0.05),
    slider("dispersion", "Dispersion", 0, 0.1, 0.002),
    slider("fresnel", "Fresnel", 0, 0.8, 0.01),
    slider("absorption", "Absorption", 0, 0.6, 0.01),
    slider("blur", "Rim blur", 0, 0.03, 0.001),
  );
  const actions = document.createElement("div");
  actions.className = "lab-row";
  const shot = document.createElement("button");
  shot.textContent = "Screenshot";
  shot.addEventListener("click", () => {
    canvas.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `glass-lab-${background}-${Date.now()}.png`;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  });
  const debug = document.createElement("select");
  for (const mode of ["off", "normals", "thickness", "refraction", "fresnel", "dispersion", "media", "typography"] as DebugMode[]) {
    const option = document.createElement("option");
    option.value = mode;
    option.textContent = `debug=${mode}`;
    if (mode === debugMode) option.selected = true;
    debug.append(option);
  }
  debug.addEventListener("change", () => {
    const url = new URL(location.href);
    if (debug.value === "off") url.searchParams.delete("debug");
    else url.searchParams.set("debug", debug.value);
    location.href = url.toString();
  });
  actions.append(shot, debug);
  panel.append(actions);
  syncPanel();
}

function tick(now: number) {
  requestAnimationFrame(tick);
  if (!visible) return;
  const dt = Math.min(0.05, (now - lastT) / 1000);
  lastT = now;
  if (!paused) {
    motion.step(dt);
    if (background === "video") {
      const ctx = (pattern.image as HTMLCanvasElement).getContext("2d");
      if (ctx) {
        paintPattern(ctx, "video", pattern.image.width as number, pattern.image.height as number, now / 1000);
        pattern.needsUpdate = true;
      }
    }
  }
  applyPose();
  glass.visible = false;
  renderer.toneMapping = NoToneMapping;
  renderer.setRenderTarget(sceneTarget);
  renderer.render(scene, camera);
  renderer.setRenderTarget(null);
  renderer.toneMapping = ACESFilmicToneMapping;
  glass.visible = true;
  renderer.render(scene, camera);
  css.render(cssScene, camera);
}

const qa = {
  pause: () => {
    paused = true;
  },
  resume: () => {
    paused = false;
    lastT = performance.now();
  },
  setTime: () => undefined,
  setOffset: () => undefined,
  setVelocity: () => undefined,
  setQuality: () => undefined,
  setDpr: (value: number) => {
    renderer.setPixelRatio(value);
  },
  setPointer: (x: number, y: number) => motion.setPointer(x, y),
  setBackground,
  getState: () => ({
    ready: true,
    lab: true,
    milestone: 3,
    backend,
    debug: debugMode,
    background,
    glass: "volume",
    samplesScene: true,
    pointerX: motion.pointerX,
    pointerY: motion.pointerY,
    rotX: motion.rotX,
    rotY: motion.rotY,
    params: {
      ior: params.ior.value,
      warp: params.warp.value,
      rimPower: params.rimPower.value,
      dispersion: params.dispersion.value,
      fresnel: params.fresnel.value,
      absorption: params.absorption.value,
      blur: params.blur.value,
    },
  }),
  getMetrics: () => ({ backend, medianFrameMs: 0, p95FrameMs: 0, fps: 0 }),
  getAssetState: () => ({ videos: 0, textures: 1, ready: true, media: "lab-pattern" }),
  getPoolState: () => ({ slots: 1, created: 1, destroyed: 0, remaps: 0, cols: 1, rows: 1 }),
  reset: () => {
    motion.reset();
    setBackground("checker");
    for (const [key, value] of Object.entries(GLASS) as Array<[keyof GlassParamSet, number]>) {
      if (key in params) setGlassParam(params, key, value);
    }
  },
};

if (import.meta.env.DEV || new URLSearchParams(location.search).has("qa")) {
  const host = window as Window & { __LIQUID_GLASS_QA__?: typeof qa; __ILG_QA__?: typeof qa };
  host.__LIQUID_GLASS_QA__ = qa;
  host.__ILG_QA__ = qa;
}

resize();
mountPanel();
applyPose();
tick(lastT);
