import "./lab.css";
import {
  ACESFilmicToneMapping,
  AmbientLight,
  Color,
  HalfFloatType,
  LinearSRGBColorSpace,
  Mesh,
  MeshBasicMaterial,
  MeshBasicNodeMaterial,
  NoToneMapping,
  OrthographicCamera,
  PerspectiveCamera,
  PlaneGeometry,
  RenderTarget,
  RepeatWrapping,
  Scene,
  SRGBColorSpace,
  Vector2,
  WebGPURenderer,
} from "three/webgpu";
import { Fn, mix, screenUV, step, texture, vec3 } from "three/tsl";
import { TILE } from "../config";
import {
  createLiquidGlassMaterialV4,
  createLiquidGlassParamsV4,
  createPointerKeyLightV4,
  updatePointerKeyLightV4,
} from "../materials/LiquidGlassMaterialV4";
import { createGlassMaterial, createGlassParams } from "../materials/LiquidGlassMaterial";
import { SceneColorTargetV4 } from "../rendering/SceneColorTargetV4";
import { createConvexGlassGeometryV4 } from "../scene/ConvexGlassGeometryV4";
import { createConvexGlassGeometry } from "../scene/ConvexGlassGeometry";
import {
  V4_OPTICS_CONFIG,
  type V4DebugMode,
  type V4ShellMode,
} from "../v4/OpticsConfigV4";
import { createStripLightEnvironmentV4 } from "../v4/StripLightEnvironmentV4";
import { LabPatternTexture, parseLabPattern } from "./patterns";
import {
  LAB_DEBUG_VIEWS,
  LAB_MODES,
  LAB_PATTERNS,
  LAB_POSES,
  LAB_SHELL_MODES,
  type LabDebugView,
  type LabMode,
  type LabPattern,
  type LabPointer,
  type LabPose,
  type LabQaApi,
  type LabShellMode,
  type LabState,
} from "./types";

const DEFAULT_MODE: LabMode = "split";
const DEFAULT_PATTERN: LabPattern = "checker";
const DEFAULT_DEBUG: LabDebugView = "beauty";
const DEFAULT_SHELL_MODE: LabShellMode = "energy-controlled";
const DEFAULT_POSE: LabPose = "front";
const DPR_LIMIT = 2;
const POINTER_SPRING = 10.5;
const FRAME_SAMPLE_LIMIT = 240;
const LAB_POSE_ROTATIONS: Readonly<Record<LabPose, readonly [number, number, number]>> = {
  front: [0, 0, 0],
  left: [-0.04, 0.48, -0.025],
  right: [0.04, -0.48, 0.025],
};

function requireElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  if (!element) throw new Error(`V4 lab shell is missing ${selector}`);
  return element;
}

const stage = requireElement<HTMLElement>("#lab-stage");
const canvasHost = requireElement<HTMLElement>("#lab-canvas");
const blocked = requireElement<HTMLElement>("#lab-blocked");

const ui = {
  modeControls: document.querySelector<HTMLElement>("#mode-controls")!,
  poseControls: document.querySelector<HTMLElement>("#pose-controls")!,
  patternControls: document.querySelector<HTMLElement>("#pattern-controls")!,
  shellControls: document.querySelector<HTMLElement>("#shell-controls")!,
  debugSelect: document.querySelector<HTMLSelectElement>("#debug-select")!,
  videoInput: document.querySelector<HTMLInputElement>("#video-input")!,
  resetButton: document.querySelector<HTMLButtonElement>("#reset-button")!,
  modeOutput: document.querySelector<HTMLOutputElement>("#mode-output")!,
  poseOutput: document.querySelector<HTMLOutputElement>("#pose-output")!,
  patternOutput: document.querySelector<HTMLOutputElement>("#pattern-output")!,
  debugOutput: document.querySelector<HTMLOutputElement>("#debug-output")!,
  shellOutput: document.querySelector<HTMLOutputElement>("#shell-output")!,
  readyOutput: document.querySelector<HTMLOutputElement>("#ready-output")!,
  stageProfile: document.querySelector<HTMLElement>("#stage-profile")!,
  stagePattern: document.querySelector<HTMLElement>("#stage-pattern")!,
  stagePointer: document.querySelector<HTMLElement>("#stage-pointer")!,
  metricBackend: document.querySelector<HTMLElement>("#metric-backend")!,
  metricTarget: document.querySelector<HTMLElement>("#metric-target")!,
  metricFrame: document.querySelector<HTMLElement>("#metric-frame")!,
  metricLight: document.querySelector<HTMLElement>("#metric-light")!,
};

function title(value: string) {
  return value.replaceAll("-", " ").toUpperCase();
}

function clampPointer(value: number) {
  return Math.max(-1, Math.min(1, Number.isFinite(value) ? value : 0));
}

function percentile(values: readonly number[], amount: number) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * amount) - 1))];
}

function parseMode(value: string | null): LabMode {
  return LAB_MODES.includes(value as LabMode) ? (value as LabMode) : DEFAULT_MODE;
}

function parseDebug(value: string | null): LabDebugView {
  return LAB_DEBUG_VIEWS.includes(value as LabDebugView) ? (value as LabDebugView) : DEFAULT_DEBUG;
}

function parseShellMode(value: string | null): LabShellMode {
  return LAB_SHELL_MODES.includes(value as LabShellMode) ? (value as LabShellMode) : DEFAULT_SHELL_MODE;
}

function parsePose(value: string | null): LabPose {
  return LAB_POSES.includes(value as LabPose) ? (value as LabPose) : DEFAULT_POSE;
}

function readInitialState() {
  const query = new URLSearchParams(location.search);
  const optics = query.get("optics");
  return {
    mode: optics === "v3" || optics === "v4" ? optics : parseMode(query.get("mode")),
    pattern: parseLabPattern(query.get("pattern") ?? "") ?? DEFAULT_PATTERN,
    debug: parseDebug(query.get("debug")),
    shellMode: parseShellMode(query.get("shell")),
    pose: parsePose(query.get("pose")),
  };
}

function makeComparisonTarget(name: string) {
  const target = new RenderTarget(1, 1, {
    type: HalfFloatType,
    colorSpace: LinearSRGBColorSpace,
    depthBuffer: true,
    stencilBuffer: false,
    samples: 0,
  });
  target.texture.name = name;
  return target;
}

function createCompositeMaterial(
  mode: LabMode,
  v3Target: RenderTarget,
  v4Target: RenderTarget,
) {
  const v3Texture = texture(v3Target.texture);
  const v4Texture = texture(v4Target.texture);
  const material = new MeshBasicNodeMaterial();
  material.name = `MirrorWeb.V4.LabComposite.${mode}`;
  material.depthTest = false;
  material.depthWrite = false;
  material.toneMapped = true;
  material.colorNode = Fn(() => {
    const v3 = v3Texture.sample(screenUV).rgb;
    const v4 = v4Texture.sample(screenUV).rgb;
    if (mode === "v3") return v3;
    if (mode === "v4") return v4;
    if (mode === "difference") {
      const delta = v4.sub(v3).abs();
      const energy = delta.r.add(delta.g).add(delta.b).div(3);
      return delta.mul(3.25).add(vec3(energy.mul(0.28)));
    }
    return mix(v3, v4, step(0.5, screenUV.x));
  })();
  return material;
}

function setQueryState(
  mode: LabMode,
  pattern: LabPattern,
  debug: LabDebugView,
  shellMode: LabShellMode,
  pose: LabPose,
) {
  const url = new URL(location.href);
  url.searchParams.set("mode", mode);
  if (mode === "v3" || mode === "v4") url.searchParams.set("optics", mode);
  else url.searchParams.delete("optics");
  url.searchParams.set("pattern", pattern);
  url.searchParams.set("debug", debug);
  url.searchParams.set("shell", shellMode);
  url.searchParams.set("pose", pose);
  history.replaceState(null, "", url);
}

function mountButtons(
  host: HTMLElement,
  values: readonly string[],
  onSelect: (value: string) => void,
) {
  const fragment = document.createDocumentFragment();
  for (const value of values) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "control-button";
    button.dataset.value = value;
    button.textContent = title(value);
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => onSelect(value));
    fragment.append(button);
  }
  host.replaceChildren(fragment);
}

function mountDebugOptions() {
  const fragment = document.createDocumentFragment();
  for (const debug of LAB_DEBUG_VIEWS) {
    const option = document.createElement("option");
    option.value = debug;
    option.textContent = title(debug);
    fragment.append(option);
  }
  ui.debugSelect.replaceChildren(fragment);
}

function showBlocked(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  blocked.hidden = false;
  blocked.querySelector("p")!.textContent = message;
  ui.readyOutput.textContent = "BLOCKED";
  ui.readyOutput.style.color = "var(--signal)";
  document.body.dataset.ready = "blocked";
  console.error("[MirrorWeb V4 Lab]", error);
}

async function startLab() {
  if (!navigator.gpu) throw new Error("navigator.gpu is unavailable. Enable WebGPU or use a supported browser/GPU.");
  const probeAdapter = await navigator.gpu.requestAdapter();
  if (!probeAdapter) throw new Error("No WebGPU adapter is available.");
  const adapterFallback = (probeAdapter as typeof probeAdapter & { isFallbackAdapter?: boolean }).isFallbackAdapter;
  if (adapterFallback === true) throw new Error("A fallback/software WebGPU adapter cannot run the V4 optics gate.");

  const initial = readInitialState();
  let mode = initial.mode;
  let pattern = initial.pattern;
  let debug = initial.debug;
  let shellMode = initial.shellMode;
  let pose = initial.pose;
  let ready = false;
  let paused = false;
  let disposed = false;
  let lastFrame = performance.now();
  let lastTelemetry = 0;
  const frameIntervals: number[] = [];
  const pointerTarget: LabPointer = { x: 0, y: 0 };
  const pointerCurrent: LabPointer = { x: 0, y: 0 };

  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-label", "Liquid Glass V4 optical render");
  canvasHost.append(canvas);

  const renderer = new WebGPURenderer({ canvas, antialias: true, alpha: false });
  await renderer.init();
  const isWebGpuBackend = (renderer as WebGPURenderer & {
    backend?: { isWebGPUBackend?: boolean };
  }).backend?.isWebGPUBackend === true;
  if (!isWebGpuBackend) throw new Error("The renderer did not initialize a WebGPU backend.");
  renderer.setClearColor(new Color(0x050708), 1);
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1;

  const worldScene = new Scene();
  worldScene.background = new Color(0x050708);
  const stripLightEnvironment = createStripLightEnvironmentV4();
  worldScene.environment = stripLightEnvironment;
  const camera = new PerspectiveCamera(45, 1, 5, 4000);
  camera.position.set(0, 0, 820);
  camera.lookAt(0, 0, 0);

  const patternHandle = new LabPatternTexture();
  patternHandle.setPattern(pattern);
  const backdropWidth = TILE.width * 3.3;
  const backdropHeight = TILE.height * 2.55;
  const scenePatternTexture = patternHandle.texture.clone();
  scenePatternTexture.image = patternHandle.canvas;
  scenePatternTexture.wrapS = RepeatWrapping;
  scenePatternTexture.wrapT = RepeatWrapping;
  scenePatternTexture.needsUpdate = true;
  const backdropMaterial = new MeshBasicMaterial({ map: scenePatternTexture, toneMapped: false });
  const backdrop = new Mesh(new PlaneGeometry(backdropWidth, backdropHeight), backdropMaterial);
  backdrop.name = "MirrorWeb.V4.Lab.SceneSource";
  backdrop.position.z = -130;
  worldScene.add(backdrop);

  const ambient = new AmbientLight(0xffffff, 0.18);
  const pointerLight = createPointerKeyLightV4();
  pointerLight.name = "MirrorWeb.V4.Lab.PointerKey";
  pointerLight.target.name = "MirrorWeb.V4.Lab.PointerKeyTarget";
  worldScene.add(ambient, pointerLight, pointerLight.target);

  const sceneColor = new SceneColorTargetV4("high");
  const v3Comparison = makeComparisonTarget("MirrorWeb.V4.Lab.V3.LinearHalfFloat");
  const v4Comparison = makeComparisonTarget("MirrorWeb.V4.Lab.V4.LinearHalfFloat");

  const v3Params = createGlassParams();
  const v3Handle = createGlassMaterial(sceneColor.texture, v3Params, "off", patternHandle.texture);
  const v3Geometry = createConvexGlassGeometry("high");
  const v3Glass = new Mesh(v3Geometry, v3Handle.material);
  v3Glass.name = "MirrorWeb.V4.Lab.V3Control";
  worldScene.add(v3Glass);

  const v4Params = createLiquidGlassParamsV4();
  const v4Handle = createLiquidGlassMaterialV4(
    sceneColor.texture,
    v4Params,
    debug as V4DebugMode,
    shellMode as V4ShellMode,
  );
  const v4Geometry = createConvexGlassGeometryV4("high");
  const v4Body = new Mesh(v4Geometry, v4Handle.bodyMaterial);
  const v4Reflection = new Mesh(v4Geometry, v4Handle.reflectionMaterial);
  v4Body.name = "MirrorWeb.V4.Lab.RefractionBody";
  v4Reflection.name = "MirrorWeb.V4.Lab.ReflectionShell";
  v4Body.renderOrder = 10;
  v4Reflection.renderOrder = 11;
  worldScene.add(v4Body, v4Reflection);

  const applyPose = () => {
    const [x, y, z] = LAB_POSE_ROTATIONS[pose];
    for (const specimen of [v3Glass, v4Body, v4Reflection]) {
      specimen.rotation.set(x, y, z);
      specimen.updateMatrixWorld();
    }
  };
  applyPose();

  const compositeScene = new Scene();
  const compositeCamera = new OrthographicCamera(-1, 1, 1, -1, 0, 2);
  compositeCamera.position.z = 1;
  const compositeMaterials = Object.fromEntries(
    LAB_MODES.map((item) => [item, createCompositeMaterial(item, v3Comparison, v4Comparison)]),
  ) as Record<LabMode, MeshBasicNodeMaterial>;
  const compositeQuad = new Mesh(new PlaneGeometry(2, 2), compositeMaterials[mode]);
  compositeQuad.frustumCulled = false;
  compositeScene.add(compositeQuad);

  const syncUi = () => {
    document.body.dataset.mode = mode;
    document.body.dataset.pattern = pattern;
    document.body.dataset.debug = debug;
    document.body.dataset.shell = shellMode;
    document.body.dataset.pose = pose;
    const syncButtons = (host: HTMLElement, value: string) => {
      for (const button of host.querySelectorAll<HTMLButtonElement>("[data-value]")) {
        button.setAttribute("aria-pressed", String(button.dataset.value === value));
      }
    };
    syncButtons(ui.modeControls, mode);
    syncButtons(ui.poseControls, pose);
    syncButtons(ui.patternControls, pattern);
    syncButtons(ui.shellControls, shellMode);
    ui.debugSelect.value = debug;
    ui.modeOutput.textContent = title(mode);
    ui.poseOutput.textContent = title(pose);
    ui.patternOutput.textContent = title(pattern);
    ui.debugOutput.textContent = title(debug);
    ui.shellOutput.textContent = title(shellMode);
    ui.stagePattern.textContent = `PATTERN · ${title(pattern)}`;
    compositeQuad.material = compositeMaterials[mode];
    v4Handle.setDebugMode(debug as V4DebugMode);
    v4Reflection.visible = shellMode !== "off" && (debug === "beauty" || debug === "reflection");
    setQueryState(mode, pattern, debug, shellMode, pose);
  };

  const state = (): LabState => {
    const target = sceneColor.describe();
    const geometryConfig = V4_OPTICS_CONFIG.geometry;
    const materialConfig = V4_OPTICS_CONFIG.material;
    const coefficients = materialConfig.zoneCoefficients;
    return {
      ready,
      route: "/glass-lab-v4",
      mode,
      pattern,
      debug,
      shellMode,
      pose,
      backend: ready && isWebGpuBackend ? "webgpu" : "blocked",
      v3Preserved: true,
      normalPathDirectMedia: false,
      opticalConfig: {
        shoulderOuterPx: geometryConfig.shoulderOuterPx,
        rolloverInsetPx: geometryConfig.rolloverInsetPx,
        rolloverDepthPx: geometryConfig.rolloverDepthPx,
        lensRimWidthPx: geometryConfig.lensRimWidthPx,
        maxRefractionUv: materialConfig.maxRefractionUv,
        blurLod: materialConfig.blurLod,
        refractionCoefficients: { ...coefficients.refraction },
        blurCoefficients: { ...coefficients.blur },
        dispersionCoefficients: { ...coefficients.dispersion },
        shellCoefficients: { ...coefficients.shell },
        shell: { ...materialConfig.shell },
      },
      sceneTarget: {
        type: target.type === HalfFloatType ? "half-float" : "unexpected",
        colorSpace: target.colorSpace === LinearSRGBColorSpace ? "linear" : "unexpected",
        quality: target.quality,
        scale: target.scale,
        width: target.width,
        height: target.height,
      },
      pointer: { ...pointerCurrent },
      highlight: {
        source: "pointer-key-light-proxy",
        proxyX: pointerCurrent.x,
        proxyY: pointerCurrent.y,
        measuredCentroidAvailable: false,
        continuousInput: true,
      },
      frame: {
        medianMs: percentile(frameIntervals, 0.5),
        p95Ms: percentile(frameIntervals, 0.95),
        samples: frameIntervals.length,
      },
    };
  };

  const setMode = (value: LabMode | string) => {
    const next = parseMode(value);
    mode = next;
    syncUi();
    return state();
  };

  const setPattern = (value: LabPattern | string) => {
    const next = parseLabPattern(value);
    if (!next) throw new Error(`Unknown V4 lab pattern: ${value}`);
    pattern = next;
    patternHandle.setPattern(next);
    scenePatternTexture.needsUpdate = true;
    syncUi();
    return state();
  };

  const setDebug = (value: LabDebugView | "difference" | string) => {
    if (value === "difference") {
      mode = "difference";
      debug = "beauty";
    } else {
      const next = parseDebug(value);
      if (next !== value) throw new Error(`Unknown V4 lab debug view: ${value}`);
      debug = next;
    }
    syncUi();
    return state();
  };

  const setShellMode = (value: LabShellMode | string) => {
    const next = parseShellMode(value);
    if (next !== value) throw new Error(`Unknown V4 shell mode: ${value}`);
    shellMode = next;
    v4Handle.setShellMode(next as V4ShellMode);
    syncUi();
    return state();
  };

  const setPose = (value: LabPose | string) => {
    const next = parsePose(value);
    if (next !== value) throw new Error(`Unknown V4 lab pose: ${value}`);
    pose = next;
    applyPose();
    syncUi();
    return state();
  };

  const setPointer = (x: number, y: number) => {
    pointerTarget.x = clampPointer(x);
    pointerTarget.y = clampPointer(y);
    return state();
  };

  const reset = () => {
    mode = DEFAULT_MODE;
    debug = DEFAULT_DEBUG;
    shellMode = DEFAULT_SHELL_MODE;
    pose = DEFAULT_POSE;
    pointerTarget.x = 0;
    pointerTarget.y = 0;
    pointerCurrent.x = 0;
    pointerCurrent.y = 0;
    pattern = DEFAULT_PATTERN;
    patternHandle.setPattern(pattern);
    scenePatternTexture.needsUpdate = true;
    v4Handle.setShellMode(shellMode as V4ShellMode);
    applyPose();
    syncUi();
    return state();
  };

  const qa: LabQaApi & {
    getMetrics: () => LabState["frame"];
    pause: () => void;
    resume: () => void;
  } = {
    get ready() { return ready; },
    getState: state,
    setPattern,
    setMode,
    setDebug,
    setShellMode,
    setPose,
    setPointer,
    getMeasurementState: state,
    reset,
    getMetrics: () => state().frame,
    pause: () => { paused = true; },
    resume: () => {
      paused = false;
      lastFrame = performance.now();
    },
  };
  window.__ILG_V4_LAB_QA__ = qa;
  const host = window as Window & { __ILG_QA__?: typeof qa; __LIQUID_GLASS_QA__?: typeof qa };
  host.__ILG_QA__ = qa;
  host.__LIQUID_GLASS_QA__ = qa;

  mountButtons(ui.modeControls, LAB_MODES, (value) => setMode(value));
  mountButtons(ui.poseControls, LAB_POSES, (value) => setPose(value));
  mountButtons(ui.patternControls, LAB_PATTERNS, (value) => setPattern(value));
  mountButtons(ui.shellControls, LAB_SHELL_MODES, (value) => setShellMode(value));
  mountDebugOptions();
  ui.debugSelect.addEventListener("change", () => setDebug(ui.debugSelect.value));
  ui.videoInput.addEventListener("change", async () => {
    const file = ui.videoInput.files?.[0];
    if (!file) return;
    await patternHandle.loadVideoFile(file);
    scenePatternTexture.needsUpdate = true;
    pattern = "video";
    syncUi();
  });
  ui.resetButton.addEventListener("click", reset);

  const resize = () => {
    const rect = stage.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    const dpr = Math.min(DPR_LIMIT, Math.max(1, devicePixelRatio || 1));
    renderer.setPixelRatio(dpr);
    renderer.setSize(width, height, false);
    sceneColor.resize(width, height, dpr);
    v3Comparison.setSize(Math.max(1, Math.floor(width * dpr)), Math.max(1, Math.floor(height * dpr)));
    v4Comparison.setSize(Math.max(1, Math.floor(width * dpr)), Math.max(1, Math.floor(height * dpr)));
    camera.aspect = width / height;
    const fovRadians = (camera.fov * Math.PI) / 180;
    const verticalDistance = (TILE.height * 0.5) / (Math.tan(fovRadians * 0.5) * 0.72);
    const horizontalDistance = (TILE.width * 0.5) / (Math.tan(fovRadians * 0.5) * camera.aspect * 0.72);
    camera.position.z = Math.max(650, verticalDistance, horizontalDistance);
    camera.updateProjectionMatrix();
    const backdropPerspectiveScale = (camera.position.z - backdrop.position.z) / camera.position.z;
    const repeatX = backdropWidth / (TILE.width * backdropPerspectiveScale);
    const repeatY = backdropHeight / (TILE.height * backdropPerspectiveScale);
    scenePatternTexture.repeat.set(repeatX, repeatY);
    scenePatternTexture.offset.set(0.5 - repeatX * 0.5, 0.5 - repeatY * 0.5);
    scenePatternTexture.needsUpdate = true;
    ui.stageProfile.textContent = `RT ${sceneColor.scale.toFixed(2)} · DPR ${dpr.toFixed(2)}`;
  };

  const onPointer = (event: PointerEvent) => {
    const rect = stage.getBoundingClientRect();
    setPointer(
      ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1,
      -(((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1),
    );
  };
  stage.addEventListener("pointermove", onPointer, { passive: true });
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const mapped = LAB_MODES[Number(event.key) - 1];
    if (mapped) setMode(mapped);
    if (event.key.toLowerCase() === "d") {
      const index = LAB_DEBUG_VIEWS.indexOf(debug);
      setDebug(LAB_DEBUG_VIEWS[(index + 1) % LAB_DEBUG_VIEWS.length]);
    }
  });
  document.addEventListener("visibilitychange", () => {
    paused = document.visibilityState !== "visible";
    lastFrame = performance.now();
  });

  const renderWorldPass = (target: RenderTarget, version: "v3" | "v4") => {
    v3Glass.visible = version === "v3";
    v4Body.visible = version === "v4";
    v4Reflection.visible = version === "v4"
      && shellMode !== "off"
      && (debug === "beauty" || debug === "reflection");
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(worldScene, camera);
  };

  const renderFrame = (now: number) => {
    if (disposed) return;
    requestAnimationFrame(renderFrame);
    const interval = Math.max(0, Math.min(100, now - lastFrame));
    lastFrame = now;
    if (paused) return;
    if (interval > 0) {
      frameIntervals.push(interval);
      if (frameIntervals.length > FRAME_SAMPLE_LIMIT) frameIntervals.shift();
    }
    const dt = Math.min(0.05, interval / 1000);
    const spring = 1 - Math.exp(-POINTER_SPRING * dt);
    pointerCurrent.x += (pointerTarget.x - pointerCurrent.x) * spring;
    pointerCurrent.y += (pointerTarget.y - pointerCurrent.y) * spring;
    updatePointerKeyLightV4(pointerLight, pointerCurrent.x, pointerCurrent.y);
    if (patternHandle.update(now / 1000)) scenePatternTexture.needsUpdate = true;

    v3Glass.visible = false;
    v4Body.visible = false;
    v4Reflection.visible = false;
    renderer.toneMapping = NoToneMapping;
    renderer.setRenderTarget(sceneColor.target);
    renderer.clear();
    renderer.render(worldScene, camera);

    renderWorldPass(v3Comparison, "v3");
    renderWorldPass(v4Comparison, "v4");

    renderer.setRenderTarget(null);
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.clear();
    renderer.render(compositeScene, compositeCamera);

    if (now - lastTelemetry > 180) {
      lastTelemetry = now;
      const metrics = state();
      ui.stagePointer.textContent = `POINTER · ${pointerCurrent.x >= 0 ? "+" : ""}${pointerCurrent.x.toFixed(3)} / ${pointerCurrent.y >= 0 ? "+" : ""}${pointerCurrent.y.toFixed(3)}`;
      ui.metricFrame.textContent = `${metrics.frame.medianMs.toFixed(2)} MS`;
      ui.metricLight.textContent = `${pointerCurrent.x.toFixed(2)} / ${pointerCurrent.y.toFixed(2)}`;
    }
  };

  const dispose = () => {
    disposed = true;
    stripLightEnvironment.dispose();
    patternHandle.dispose();
    scenePatternTexture.dispose();
    backdropMaterial.dispose();
    backdrop.geometry.dispose();
    v3Handle.material.dispose();
    v3Geometry.dispose();
    v4Handle.dispose();
    v4Geometry.dispose();
    v3Comparison.dispose();
    v4Comparison.dispose();
    sceneColor.dispose();
    compositeQuad.geometry.dispose();
    for (const material of Object.values(compositeMaterials)) material.dispose();
    renderer.dispose();
  };
  window.addEventListener("pagehide", dispose, { once: true });

  resize();
  syncUi();
  updatePointerKeyLightV4(pointerLight, 0, 0);
  ready = true;
  ui.readyOutput.textContent = "LIVE";
  ui.readyOutput.style.color = "var(--acid)";
  ui.metricBackend.textContent = "WEBGPU";
  ui.metricTarget.textContent = "RGBA16F / LINEAR";
  document.body.dataset.ready = "true";
  blocked.hidden = true;
  requestAnimationFrame(renderFrame);
}

startLab().catch(showBlocked);
