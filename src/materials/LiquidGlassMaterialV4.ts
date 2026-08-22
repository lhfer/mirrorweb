import {
  AdditiveBlending,
  DirectionalLight,
  MeshBasicNodeMaterial,
  MeshPhysicalNodeMaterial,
  NormalBlending,
  type Texture,
} from "three/webgpu";
import {
  Fn,
  abs,
  attribute,
  cameraWorldMatrix,
  cameraProjectionMatrix,
  clamp,
  cos,
  equirectUV,
  float,
  max,
  min,
  mix,
  normalView,
  normalViewGeometry,
  positionView,
  positionViewDirection,
  pow,
  reflect,
  screenUV,
  sin,
  texture,
  uniform,
  varying,
  vec2,
  vec3,
  vec4,
} from "three/tsl";
import {
  V4_DEBUG_CODE,
  V4_OPTICS_CONFIG,
  type V4DebugMode,
  type V4DispersionLaw,
  type V4ReflectionSupport,
  type V4ShellMode,
} from "../v4/OpticsConfigV4";
import {
  applyTargetBevelFrameV4,
  createTargetBevelFieldV4,
  createTargetBevelUniformsV4,
  type TargetBevelUniformsV4,
} from "./TargetBevelFieldV4";

export function createLiquidGlassParamsV4() {
  const defaults = V4_OPTICS_CONFIG.material;
  return {
    ior: uniform(defaults.ior),
    refractionDistance: uniform(defaults.refractionDistance),
    maxRefractionUv: uniform(defaults.maxRefractionUv),
    blurLod: uniform(defaults.blurLod),
    // O1 System A: superseded by the Target-law spectral dispersion below.
    // Kept so QA surfaces and stored params keep their shape; no longer read
    // by the shader.
    dispersionUv: uniform(defaults.dispersionUv),
    // O1 System A: relative spread of the refraction displacement per unit
    // spectral offset -- the screen-space analogue of the Target's
    // eta_i = 1/(ior + dispersion*offset_i) spread. A sample at spectral
    // position o in [-0.5, +0.5] refracts with displacement scaled by
    // (1 + dispersionSpread * o * zone).
    dispersionSpread: uniform(defaults.dispersionSpread),
    reflectionStrength: uniform(defaults.reflectionStrength),
    roughnessCenter: uniform(defaults.roughnessCenter),
    roughnessRim: uniform(defaults.roughnessRim),
    fresnelPower: uniform(defaults.fresnelPower),
    adaptivityRadiusUv: uniform(defaults.adaptivityRadiusUv),
    // O2 System B -- the Target's fresnel-capped LERP toward the white
    // studio environment. Source values adopted verbatim
    // (qa-v5/optics-o2/o2-selected-system.json); the *Scale uniforms are
    // QA-only floor instruments with product value 1.
    fresnelF0: uniform(defaults.systemB.fresnelF0),
    envIntensity: uniform(defaults.systemB.envIntensity),
    envMaxMix: uniform(defaults.systemB.envMaxMix),
    envRotationY: uniform(defaults.systemB.envRotationY),
    envRotationX: uniform(defaults.systemB.envRotationX),
    rimIntensity: uniform(defaults.systemB.rimIntensity),
    envMixScale: uniform(1),
    rimScale: uniform(1),
    // Maps screen space into the scene-color target. 1 means the target covers
    // exactly the visible frame; a smaller value means the target was rendered
    // with overscan, which is what stops a partially off-screen card from
    // clamping its refracted sample into a column of repeated border pixels.
    sceneUvScale: uniform(1),
  };
}

export type LiquidGlassParamsV4 = ReturnType<typeof createLiquidGlassParamsV4>;

export type LiquidGlassMaterialV4Handle = {
  bodyMaterial: MeshBasicNodeMaterial;
  reflectionMaterial: MeshPhysicalNodeMaterial;
  params: LiquidGlassParamsV4;
  setSceneColorTexture: (texture: Texture) => void;
  setSceneUvScale: (scale: number) => void;
  setDebugMode: (mode: V4DebugMode) => void;
  getDebugMode: () => V4DebugMode;
  setShellMode: (mode: V4ShellMode) => void;
  getShellMode: () => V4ShellMode;
  getDispersionLaw: () => V4DispersionLaw;
  getReflectionSupport: () => V4ReflectionSupport;
  /**
   * O3: the Target's per-frame bevel uniform writes. A no-op on the GPU in
   * the geometry lane, where nothing references them.
   */
  setLayoutFrame: (frame: {
    planeWidth: number; planeHeight: number; cardScale: number; sphereRadius: number;
  }) => void;
  dispose: () => void;
};

function luminanceNode(color: any) {
  return color.dot(vec3(0.2126, 0.7152, 0.0722));
}

/**
 * V4's normal path accepts only the linear scene-color target. There is no
 * media-map parameter by design, so direct media cannot become the optical
 * body accidentally.
 */
export type LiquidGlassMaterialV4Options = {
  /**
   * O2 System B: the white studio equirect. When absent the body renders
   * exactly the pre-O2 composition (legacy callers stay byte-identical).
   */
  envTexture?: Texture | null;
  /**
   * O2 lane switch: "v1-taps" is the 5159cf8 dispersion restored verbatim
   * (the B-only lane base); "o1-spectral" is the e01fb30 law (the A+B lane
   * base). Chosen at material build time -- a JS branch, not a shader one.
   */
  dispersionLaw?: V4DispersionLaw;
  /**
   * O3 lane switch: "geometry" is the accepted O2 control (the
   * v_o2NormalView geometry normal and the strongLensRim mask);
   * "target-sdf" is the candidate (the Target's analytic bevel normal and
   * its rounded-rect SDF rim). A build-time JS branch on purpose -- the
   * geometry lane must emit the O2 shader byte for byte.
   */
  reflectionSupport?: V4ReflectionSupport;
};

export function createLiquidGlassMaterialV4(
  sceneColorTexture: Texture,
  params: LiquidGlassParamsV4 = createLiquidGlassParamsV4(),
  initialDebugMode: V4DebugMode = "beauty",
  initialShellMode: V4ShellMode = "energy-controlled",
  options: LiquidGlassMaterialV4Options = {},
): LiquidGlassMaterialV4Handle {
  const dispersionLaw: V4DispersionLaw =
    options.dispersionLaw ?? V4_OPTICS_CONFIG.material.dispersionLaw;
  const reflectionSupport: V4ReflectionSupport =
    options.reflectionSupport ?? V4_OPTICS_CONFIG.material.reflectionSupport;
  // Created unconditionally so the handle's shape does not depend on the
  // lane; only the target-sdf branch REFERENCES them, and an unreferenced
  // uniform is not emitted into the program.
  const bevelUniforms: TargetBevelUniformsV4 = createTargetBevelUniformsV4();
  const sceneColor = texture(sceneColorTexture);
  const debugCode = uniform(V4_DEBUG_CODE[initialDebugMode]);
  let debugMode = initialDebugMode;
  let shellMode = initialShellMode;

  const shoulder = clamp(attribute<"float">("aShoulder", "float"), 0, 1);
  const strongLensRim = clamp(attribute<"float">("aLensRim", "float"), 0, 1);
  const sidewall = clamp(attribute<"float">("aSidewall", "float"), 0, 1);
  const thickness = max(attribute<"float">("aThickness", "float"), 0);
  const curvature = clamp(attribute<"float">("aCurvature", "float"), 0, 1);
  const centerFace = float(1).sub(clamp(shoulder.add(strongLensRim).add(sidewall), 0, 1));
  const zoneCoefficients = V4_OPTICS_CONFIG.material.zoneCoefficients;
  const refractionZone = clamp(
    centerFace.mul(zoneCoefficients.refraction.center)
      .add(shoulder.mul(zoneCoefficients.refraction.shoulder))
      .add(strongLensRim.mul(zoneCoefficients.refraction.strongLensRim))
      .add(sidewall.mul(zoneCoefficients.refraction.sidewall)),
    0,
    1,
  );
  const blurZone = clamp(
    centerFace.mul(zoneCoefficients.blur.center)
      .add(shoulder.mul(zoneCoefficients.blur.shoulder))
      .add(strongLensRim.mul(zoneCoefficients.blur.strongLensRim))
      .add(sidewall.mul(zoneCoefficients.blur.sidewall)),
    0,
    1,
  );
  const dispersionZone = clamp(
    centerFace.mul(zoneCoefficients.dispersion.center)
      .add(shoulder.mul(zoneCoefficients.dispersion.shoulder))
      .add(strongLensRim.mul(zoneCoefficients.dispersion.strongLensRim))
      .add(sidewall.mul(zoneCoefficients.dispersion.sidewall)),
    0,
    1,
  );
  const shellZone = clamp(
    centerFace.mul(zoneCoefficients.shell.center)
      .add(shoulder.mul(zoneCoefficients.shell.shoulder))
      .add(strongLensRim.mul(zoneCoefficients.shell.strongLensRim))
      .add(sidewall.mul(zoneCoefficients.shell.sidewall)),
    0,
    1,
  );
  const thicknessNorm = clamp(
    thickness.div(V4_OPTICS_CONFIG.geometry.baseThickness + V4_OPTICS_CONFIG.geometry.rolloverDepthPx),
    0,
    1,
  );
  const facing = clamp(normalView.dot(positionViewDirection), 0, 1);
  const fresnel = pow(float(1).sub(facing), params.fresnelPower);

  const incident = positionViewDirection.negate();
  const refracted = incident.refract(normalView, float(1).div(params.ior));
  const opticalTravel = params.refractionDistance
    .mul(refractionZone)
    .mul(mix(0.35, 1, thicknessNorm))
    .mul(mix(0.82, 1.12, curvature));
  const surfaceClip = cameraProjectionMatrix.mul(vec4(positionView, 1));
  const exitView = positionView.add(refracted.mul(opticalTravel));
  const exitClip = cameraProjectionMatrix.mul(vec4(exitView, 1));
  const surfaceNdc = surfaceClip.xy.div(surfaceClip.w);
  const exitNdc = exitClip.xy.div(exitClip.w);
  const rawOffset = exitNdc.sub(surfaceNdc).mul(vec2(0.5, -0.5));
  // A finite scene plane needs a projected thin-lens correction in addition
  // to the local Snell exit point. This keeps the center nearly untouched while
  // producing measurable, continuous compression across the optical shoulder
  // and the strong rim instead of only blurring otherwise straight lines.
  // This is the only term that tracks the surface normal directly, so it is
  // what can put a depth-dependent gradient across the shoulder. Its old
  // curvature floor of 0.06 suppressed it five-fold exactly where the shoulder
  // is gentlest, which is most of the band.
  const projectedNormalOffset = vec2(normalView.x, normalView.y.negate())
    .mul(params.maxRefractionUv)
    .mul(refractionZone)
    .mul(mix(0.3, 0.55, curvature))
    .mul(mix(0.65, 1, thicknessNorm));
  const surfaceUv = attribute<"vec2">("uv", "vec2");
  const radialScreenDirection = vec2(
    surfaceUv.x.sub(0.5),
    surfaceUv.y.sub(0.5).negate(),
  ).add(vec2(1e-6, 0)).normalize();
  // A constant-magnitude radial push is a zoom, not a compression: it shifts
  // the whole band by the same amount and so hides the gradient the shoulder is
  // supposed to show. Halved.
  const radialLensOffset = radialScreenDirection
    .mul(params.maxRefractionUv)
    .mul(refractionZone)
    .mul(0.02)
    .mul(mix(0.65, 1, thicknessNorm));
  const refractionOffset = clamp(
    rawOffset.mul(2).add(projectedNormalOffset).add(radialLensOffset),
    vec2(params.maxRefractionUv.negate()),
    vec2(params.maxRefractionUv),
  );
  // Screen space -> scene-color target space. With sceneUvScale = 1 this is the
  // identity and the optics bench is bit-for-bit unchanged.
  const sceneSamplePoint = screenUV
    .add(refractionOffset)
    .sub(vec2(0.5))
    .mul(params.sceneUvScale)
    .add(vec2(0.5));
  const refractedUv = clamp(sceneSamplePoint, vec2(0.001), vec2(0.999));
  const blurLod = params.blurLod
    .mul(pow(blurZone, 1.6))
    .mul(mix(0.4, 1, thicknessNorm));

  // O1 System A -- the Target's dispersion LAW, ported to our sampling
  // architecture. The Target accumulates N=5 refraction samples whose IOR is
  // spread across the spectrum (eta_i = 1/(ior + dispersion*offset_i)) and
  // weights each sample's RGB by tent functions centred at 0 / 0.5 / 1 with
  // half-width 0.5, normalised per channel (byte-anchored in
  // qa-v5/optics/o0-source-diagnosis.json). Two properties follow, and both
  // are what the previous fixed R/B tap split lacked:
  //   - the spectral spread SCALES WITH the local displacement, so flat
  //     centres carry no fringe and the fringe grows with the lens, and
  //   - each channel is a NORMALISED BLEND of adjacent spectral samples, so
  //     the fringe is energy-conserving and bounded by the scene's own
  //     colours instead of a manufactured pure cyan/magenta line.
  // Screen-space analogue: sample_i displaces by
  // refractionOffset * (1 + dispersionSpread * offset_i * zone).
  // The two lanes are selected HERE, at build time, as plain JS -- no
  // shader branch exists. "v1-taps" below is the 5159cf8 block restored
  // verbatim; the blocking equivalence gate proves each lane pixel-equal
  // to its base commit's build.
  // Loosely typed on purpose: the two lanes produce different node
  // subclasses (a Join vs a reduced Add tree) with one vec3 meaning.
  let refractedColor: any;
  let dispersionDebug: any;
  if (dispersionLaw === "v1-taps") {
    const fallbackDirection = vec2(normalView.x, normalView.y.negate())
      .add(vec2(1e-5, 0))
      .normalize();
    const dispersionDirection = refractionOffset.length().greaterThan(1e-5)
      .select(refractionOffset.normalize(), fallbackDirection);
    const dispersionDelta = dispersionDirection
      .mul(params.dispersionUv)
      .mul(dispersionZone)
      .mul(params.sceneUvScale);
    const uvR = clamp(refractedUv.add(dispersionDelta), vec2(0.001), vec2(0.999));
    const uvB = clamp(refractedUv.sub(dispersionDelta), vec2(0.001), vec2(0.999));

    const sampleR = sceneColor.sample(uvR).level(blurLod);
    const sampleG = sceneColor.sample(refractedUv).level(blurLod);
    const sampleB = sceneColor.sample(uvB).level(blurLod);
    refractedColor = vec3(sampleR.r, sampleG.g, sampleB.b);
    dispersionDebug = vec3(
      abs(sampleR.r.sub(sampleG.r)).mul(5),
      0,
      abs(sampleB.b.sub(sampleG.b)).mul(5),
    );
  } else {
    const DISPERSION_SAMPLES = 5; // the Target's own count (low tier caps at 3)
    const spectral = (() => {
      const n = DISPERSION_SAMPLES;
      const tent = (x: number, c: number) => Math.max(0, 1 - Math.abs(x - c) / 0.5);
      const rows: Array<{ offset: number; weight: [number, number, number] }> = [];
      const sums: [number, number, number] = [0, 0, 0];
      for (let i = 0; i < n; i += 1) {
        const s = i / (n - 1);
        const w: [number, number, number] = [tent(s, 0), tent(s, 0.5), tent(s, 1)];
        sums[0] += w[0]; sums[1] += w[1]; sums[2] += w[2];
        rows.push({ offset: s - 0.5, weight: w });
      }
      return rows.map(({ offset, weight }) => ({
        offset,
        weight: [weight[0] / sums[0], weight[1] / sums[1], weight[2] / sums[2]] as
          [number, number, number],
      }));
    })();

    // Built as a pure expression tree: this block runs at material BUILD
    // time, outside any Fn scope, where VarNode assignments do not emit.
    const spectralSamples = spectral.map(({ offset }) => {
      const scale = float(1).add(
        params.dispersionSpread.mul(offset).mul(dispersionZone));
      const sampleUv = clamp(
        screenUV.add(refractionOffset.mul(scale))
          .sub(vec2(0.5)).mul(params.sceneUvScale).add(vec2(0.5)),
        vec2(0.001), vec2(0.999));
      return sceneColor.sample(sampleUv).level(blurLod);
    });
    refractedColor = spectralSamples
      .map((s, i) => s.rgb.mul(vec3(...spectral[i].weight)))
      .reduce((a, b) => a.add(b));
    const spectralEnds = [spectralSamples[0],
                          spectralSamples[spectralSamples.length - 1]];
    dispersionDebug = vec3(
      abs(spectralEnds[0].r.sub(spectralEnds[1].r)).mul(5),
      0,
      abs(spectralEnds[0].b.sub(spectralEnds[1].b)).mul(5),
    );
  }

  const adaptRadius = params.adaptivityRadiusUv.mul(params.sceneUvScale);
  const sampleLeft = sceneColor.sample(clamp(refractedUv.sub(vec2(adaptRadius, 0)), vec2(0.001), vec2(0.999))).level(float(0));
  const sampleRight = sceneColor.sample(clamp(refractedUv.add(vec2(adaptRadius, 0)), vec2(0.001), vec2(0.999))).level(float(0));
  const sampleTop = sceneColor.sample(clamp(refractedUv.sub(vec2(0, adaptRadius)), vec2(0.001), vec2(0.999))).level(float(0));
  const sampleBottom = sceneColor.sample(clamp(refractedUv.add(vec2(0, adaptRadius)), vec2(0.001), vec2(0.999))).level(float(0));
  const localLuma = luminanceNode(refractedColor);
  const lumaLeft = luminanceNode(sampleLeft.rgb);
  const lumaRight = luminanceNode(sampleRight.rgb);
  const lumaTop = luminanceNode(sampleTop.rgb);
  const lumaBottom = luminanceNode(sampleBottom.rgb);
  const localContrast = clamp(
    abs(lumaLeft.sub(lumaRight)).add(abs(lumaTop.sub(lumaBottom))).mul(1.8),
    0,
    1,
  );
  const maxChannel = max(max(refractedColor.r, refractedColor.g), refractedColor.b);
  const minChannel = min(min(refractedColor.r, refractedColor.g), refractedColor.b);
  const localChroma = clamp(maxChannel.sub(minChannel), 0, 1);
  const darkBoost = float(1).sub(clamp(localLuma, 0, 1));
  const flatBoost = float(1).sub(localContrast);
  const adaptivity = clamp(darkBoost.mul(0.55).add(flatBoost.mul(0.3)).add(localChroma.mul(0.15)), 0, 1);

  // Neutral contrast shaping only; V4 deliberately has no fixed blue/black body tint.
  const contrastGain = float(1).add(localContrast.mul(blurZone).mul(0.08));
  const contrastShaped = refractedColor
    .sub(vec3(localLuma))
    .mul(contrastGain)
    .add(vec3(localLuma));
  // Content-adaptive neutral volume cue: dark flat content receives a faint
  // curvature lift, while bright flat content receives an equally local
  // internal shadow. Both vanish on the clear center face and neither can
  // become a fixed dark/blue body rim.
  const adaptiveVolume = flatBoost.mul(curvature).mul(blurZone);
  const adaptiveEdgeLift = adaptiveVolume.mul(darkBoost).mul(0.08);
  const adaptiveInternalShadow = flatBoost
    .mul(blurZone)
    .mul(clamp(localLuma, 0, 1))
    .mul(mix(0.06, 0.2, curvature));
  const beauty = contrastShaped
    .add(vec3(adaptiveEdgeLift))
    .sub(vec3(adaptiveInternalShadow));

  // O2 System B -- the Target's white studio reflection as a fresnel-capped
  // LERP inside the body colour (source contract:
  // qa-v5/optics-o2/target-system-b-source.json). Everything here follows
  // the byte-anchored sites: Schlick fresnel F0 0.045 exponent 5 on the
  // bevel-territory normal; the world reflection of the view direction
  // rotated -2 rad about Y (0 about X); the equirect sampled at level 0;
  // the LERP factor min(saturate(schlick * envIntensity), envMaxMix); a
  // weak additive white rim. Our structural analogues, declared in
  // o2-selected-system.json BEFORE this code existed: the geometry's baked
  // shoulder/rim vertex normal stands in for the Target's analytic bevel
  // normal, and the strongLensRim zone drives the rim in place of the
  // Target's rounded-rect SDF. The env sample is clamped to a finite
  // ceiling so a hot HDR texel cannot inject Inf into the LERP (and so
  // envMixScale=0 reproduces `beauty` exactly -- 0 * Inf would not).
  // Without an env texture the body renders the pre-O2 composition
  // unchanged.
  //
  // O3 swaps exactly TWO inputs into the block below and nothing else: the
  // normal the fresnel and the reflection are built from, and the mask the
  // white rim rides on. Every other line -- the schlick expression, the
  // reflect idiom, both env rotations, the sample ceiling, the LERP, the
  // rim intensity -- is shared between the lanes by construction, so a
  // difference between them can only be the support field.
  const o3Field = reflectionSupport === "target-sdf"
    ? createTargetBevelFieldV4(bevelUniforms)
    : null;

  let bodyBeauty = beauty;
  if (options.envTexture) {
    const envTex = texture(options.envTexture);
    // Branch-safe inputs: the debug select chain makes three's TSL emit
    // the normalView varying unpack only into the FIRST branch that
    // references it (the normals debug view), so the beauty path reads
    // the shared normal globals as zeros -- the latent state V1's
    // `facing` has always had. System B therefore reads the interpolated
    // geometry normal through its own varying and mirrors the Target's
    // law in view space; the rotation to world (three's own
    // reflectVector idiom) preserves dot products and commutes with
    // reflect, so the math equals the Target's world-space form at the
    // pre-registered analytic-vs-geometry normal analogue.
    const supportNormalView = o3Field
      ? o3Field.analyticBevelNormalView
      : varying(normalViewGeometry, "v_o2NormalView").normalize();
    const o2Facing = clamp(supportNormalView.dot(positionViewDirection), 0, 1);
    const schlick = params.fresnelF0.add(
      float(1).sub(params.fresnelF0).mul(
        pow(clamp(float(1).sub(o2Facing), 0, 1), 5)));
    const reflected = reflect(positionViewDirection.negate(), supportNormalView)
      .transformDirection(cameraWorldMatrix);
    const cy = cos(params.envRotationY);
    const sy = sin(params.envRotationY);
    const rotY = vec3(
      reflected.x.mul(cy).sub(reflected.z.mul(sy)),
      reflected.y,
      reflected.x.mul(sy).add(reflected.z.mul(cy)),
    );
    const cx = cos(params.envRotationX);
    const sx = sin(params.envRotationX);
    const envDirection = vec3(
      rotY.x,
      rotY.y.mul(cx).sub(rotY.z.mul(sx)),
      rotY.y.mul(sx).add(rotY.z.mul(cx)),
    );
    const envSample = clamp(
      envTex.sample(equirectUV(envDirection)).rgb,
      vec3(0),
      vec3(V4_OPTICS_CONFIG.material.systemB.envSampleCeiling),
    );
    const envMixFactor = min(
      clamp(schlick.mul(params.envIntensity), 0, 1),
      params.envMaxMix,
    ).mul(params.envMixScale);
    const rimMask = o3Field ? o3Field.targetRimMask : strongLensRim;
    const rimTerm = rimMask
      .mul(params.rimIntensity)
      .mul(params.rimScale);
    bodyBeauty = mix(beauty, envSample, envMixFactor).add(vec3(rimTerm));
  }

  const edgeDebug = vec3(shoulder, strongLensRim, sidewall);
  // Unlike edge-mask's continuous weights, this palette is deliberately
  // one-hot so screen-space QA can measure each optical band independently.
  const opticalZonesDebug = sidewall.greaterThan(0.001).select(
    vec3(0, 0, 1),
    strongLensRim.greaterThan(0.01).select(
      vec3(0, 1, 0),
      shoulder.greaterThan(0.001).select(vec3(1, 0, 0), vec3(0.25)),
    ),
  );
  const normalsDebug = normalView.mul(0.5).add(0.5);
  const thicknessDebug = vec3(thicknessNorm);
  const offsetDebug = vec3(
    refractionOffset.x.div(params.maxRefractionUv).mul(0.5).add(0.5),
    refractionOffset.y.div(params.maxRefractionUv).mul(0.5).add(0.5),
    refractionZone,
  );
  const reflectionDebugBody = vec3(0);
  const fresnelDebug = vec3(fresnel);
  const adaptivityDebug = vec3(localLuma, localContrast, localChroma);

  // §十 support-field views. They are wired ONLY in the target-sdf lane:
  // adding their branches to the control chain would change the control
  // program, and the control must stay byte-identical to O2. Each gets its
  // OWN field instance, and therefore its own varying -- three's TSL emits
  // a varying's unpack into the first branch that references it, so two
  // branches sharing one would leave the later reading zeros. That is the
  // hazard O2 root-caused, defended against by construction here.
  const rimMaskDebug = o3Field
    ? vec3(createTargetBevelFieldV4(bevelUniforms, "v_o3CardUvRim").targetRimMask)
    : null;
  const analyticNormalDebug = o3Field
    ? createTargetBevelFieldV4(bevelUniforms, "v_o3CardUvNormal")
        .analyticBevelNormalView.mul(0.5).add(0.5)
    : null;

  const debugChain = () => debugCode.equal(V4_DEBUG_CODE["edge-mask"]).select(
    edgeDebug,
    debugCode.equal(V4_DEBUG_CODE["optical-zones"]).select(
      opticalZonesDebug,
      debugCode.equal(V4_DEBUG_CODE.normals).select(
        normalsDebug,
        debugCode.equal(V4_DEBUG_CODE.thickness).select(
          thicknessDebug,
          debugCode.equal(V4_DEBUG_CODE["refraction-offset"]).select(
            offsetDebug,
            debugCode.equal(V4_DEBUG_CODE.reflection).select(
              reflectionDebugBody,
              debugCode.equal(V4_DEBUG_CODE.fresnel).select(
                fresnelDebug,
                debugCode.equal(V4_DEBUG_CODE.dispersion).select(
                  dispersionDebug,
                  debugCode.equal(V4_DEBUG_CODE.adaptivity).select(adaptivityDebug, bodyBeauty),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );

  const bodyColorNode = Fn(() => (
    rimMaskDebug && analyticNormalDebug
      ? debugCode.equal(V4_DEBUG_CODE["rim-mask"]).select(
          rimMaskDebug,
          debugCode.equal(V4_DEBUG_CODE["analytic-normal"]).select(
            analyticNormalDebug,
            debugChain(),
          ),
        )
      : debugChain()
  ))();

  const bodyMaterial = new MeshBasicNodeMaterial();
  bodyMaterial.name = "MirrorWeb.LiquidGlassV4.Body";
  bodyMaterial.colorNode = bodyColorNode;
  bodyMaterial.transparent = false;
  bodyMaterial.depthWrite = true;
  bodyMaterial.toneMapped = true;

  const shellEnabled = debugCode.equal(V4_DEBUG_CODE.beauty)
    .or(debugCode.equal(V4_DEBUG_CODE.reflection))
    .select(1, 0);
  const shellConfig = V4_OPTICS_CONFIG.material.shell;
  const shellOpacity = fresnel
    .mul(shellConfig.fresnelOpacity)
    .add(shellZone.mul(shellConfig.zoneOpacity))
    .mul(shellEnabled);
  const reflectionMaterial = new MeshPhysicalNodeMaterial();
  reflectionMaterial.name = "MirrorWeb.LiquidGlassV4.ReflectionShell";
  reflectionMaterial.colorNode = vec3(0);
  reflectionMaterial.metalnessNode = float(0);
  reflectionMaterial.roughnessNode = mix(params.roughnessCenter, params.roughnessRim, shellZone);
  reflectionMaterial.iorNode = params.ior;
  reflectionMaterial.specularColorNode = vec3(1);
  reflectionMaterial.specularIntensityNode = params.reflectionStrength
    .mul(mix(shellConfig.adaptivityMin, shellConfig.adaptivityMax, adaptivity));
  reflectionMaterial.clearcoatNode = shellZone.mul(shellConfig.clearcoat);
  reflectionMaterial.clearcoatRoughnessNode = params.roughnessRim;
  reflectionMaterial.transmissionNode = float(0);
  reflectionMaterial.opacityNode = clamp(shellOpacity, 0, shellConfig.opacityMax);
  reflectionMaterial.transparent = true;
  reflectionMaterial.depthWrite = false;
  reflectionMaterial.blending = AdditiveBlending;
  reflectionMaterial.toneMapped = true;

  const setShellMode = (mode: V4ShellMode) => {
    shellMode = mode;
    const energyControlled = mode !== "additive";
    reflectionMaterial.blending = energyControlled ? NormalBlending : AdditiveBlending;
    reflectionMaterial.premultipliedAlpha = energyControlled;
    reflectionMaterial.visible = mode !== "off";
    reflectionMaterial.name = energyControlled
      ? "MirrorWeb.LiquidGlassV4.ReflectionShell.EnergyControlled"
      : "MirrorWeb.LiquidGlassV4.ReflectionShell.Additive";
    reflectionMaterial.needsUpdate = true;
  };
  setShellMode(initialShellMode);

  return {
    bodyMaterial,
    reflectionMaterial,
    params,
    setSceneColorTexture: (next: Texture) => {
      sceneColor.value = next;
    },
    setSceneUvScale: (scale: number) => {
      params.sceneUvScale.value = Math.max(0.05, Math.min(1, scale));
    },
    setDebugMode: (mode: V4DebugMode) => {
      debugMode = mode;
      debugCode.value = V4_DEBUG_CODE[mode];
    },
    getDebugMode: () => debugMode,
    setShellMode,
    getShellMode: () => shellMode,
    getDispersionLaw: () => dispersionLaw,
    getReflectionSupport: () => reflectionSupport,
    setLayoutFrame: (frame) => applyTargetBevelFrameV4(bevelUniforms, frame),
    dispose: () => {
      bodyMaterial.dispose();
      reflectionMaterial.dispose();
    },
  };
}

export function createPointerKeyLightV4(): DirectionalLight {
  const config = V4_OPTICS_CONFIG.pointerLight;
  const light = new DirectionalLight(0xffffff, config.intensity);
  light.name = "MirrorWeb.V4.PointerKeyLight";
  light.position.set(config.baseX, config.baseY, config.z);
  light.target.position.set(0, 0, 0);
  return light;
}

export function updatePointerKeyLightV4(light: DirectionalLight, x: number, y: number): void {
  const config = V4_OPTICS_CONFIG.pointerLight;
  const px = Math.max(-1, Math.min(1, x));
  const py = Math.max(-1, Math.min(1, y));
  light.position.set(
    config.baseX + px * config.travelX,
    config.baseY - py * config.travelY,
    config.z,
  );
  light.updateMatrixWorld();
}
