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
  cameraProjectionMatrix,
  clamp,
  float,
  max,
  min,
  mix,
  normalView,
  positionView,
  positionViewDirection,
  pow,
  screenUV,
  texture,
  uniform,
  vec2,
  vec3,
  vec4,
} from "three/tsl";
import {
  V4_DEBUG_CODE,
  V4_OPTICS_CONFIG,
  type V4DebugMode,
  type V4ShellMode,
} from "../v4/OpticsConfigV4";

export function createLiquidGlassParamsV4() {
  const defaults = V4_OPTICS_CONFIG.material;
  return {
    ior: uniform(defaults.ior),
    refractionDistance: uniform(defaults.refractionDistance),
    maxRefractionUv: uniform(defaults.maxRefractionUv),
    blurLod: uniform(defaults.blurLod),
    dispersionUv: uniform(defaults.dispersionUv),
    reflectionStrength: uniform(defaults.reflectionStrength),
    roughnessCenter: uniform(defaults.roughnessCenter),
    roughnessRim: uniform(defaults.roughnessRim),
    fresnelPower: uniform(defaults.fresnelPower),
    adaptivityRadiusUv: uniform(defaults.adaptivityRadiusUv),
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
export function createLiquidGlassMaterialV4(
  sceneColorTexture: Texture,
  params: LiquidGlassParamsV4 = createLiquidGlassParamsV4(),
  initialDebugMode: V4DebugMode = "beauty",
  initialShellMode: V4ShellMode = "energy-controlled",
): LiquidGlassMaterialV4Handle {
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
  const refractedColor = vec3(sampleR.r, sampleG.g, sampleB.b);

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
  const dispersionDebug = vec3(
    abs(sampleR.r.sub(sampleG.r)).mul(5),
    0,
    abs(sampleB.b.sub(sampleG.b)).mul(5),
  );
  const adaptivityDebug = vec3(localLuma, localContrast, localChroma);

  const bodyColorNode = Fn(() => debugCode.equal(V4_DEBUG_CODE["edge-mask"]).select(
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
                  debugCode.equal(V4_DEBUG_CODE.adaptivity).select(adaptivityDebug, beauty),
                ),
              ),
            ),
          ),
        ),
      ),
    ),
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
