import { MeshBasicNodeMaterial, type Texture, type Vector2 } from "three/webgpu";
import {
  Fn,
  abs,
  cameraPosition,
  clamp,
  cos,
  equirectUV,
  faceDirection,
  float,
  fwidth,
  length,
  materialOpacity,
  max,
  min,
  mix,
  modelWorldMatrix,
  modelWorldMatrixInverse,
  positionLocal,
  pow,
  refract,
  saturate,
  sin,
  smoothstep,
  sqrt,
  texture,
  uniform,
  uv,
  vec2,
  vec3,
  vec4,
} from "three/tsl";
import { V4_OPTICS_CONFIG, type V4QualityLevel } from "../v4/OpticsConfigV4";

/**
 * O5 -- the Target's COMPLETE card optical body, as one material.
 *
 * Every previous round replaced a single term of our screen-space body while
 * holding the rest frozen, and each ran into the other half of the same wall:
 * O3 showed the support field is not the binding constraint given this body,
 * O4 showed the body is not the binding constraint given this support. This
 * module stops subtracting terms and instead builds the chain the Target
 * actually has, from `qa-v5/optics-o5/target-optical-body-contract.json`
 * (57 sites, 0 failed, plus 9 complete-span absence claims).
 *
 * What the Target's body IS
 * -------------------------
 * A subdivided unit plane, domed in the VERTEX stage onto the layout sphere;
 * a rounded-rect SDF for both silhouette and bevel; an ANALYTIC normal built
 * from a numeric gradient of the bevel thickness plus the sphere's own tilt;
 * five per-IOR `refract()` calls against that normal, each sampling THE CARD'S
 * OWN media texture at level 0; a per-channel-normalised tent recombination;
 * then the accepted System B environment and the Target's white SDF rim, in
 * the same material.
 *
 * What it is NOT: there is no scene-colour render target, no mip/LOD blur, no
 * adaptive contrast, edge lift or internal shadow, no separate reflection
 * shell, no side wall and no back dish. Those are the nine absence claims,
 * each established over the whole 3747-byte material factory rather than by a
 * pretended byte offset.
 *
 * Coordinate space
 * ----------------
 * The mesh is a PlaneGeometry(1,1,16,12) scaled to (planeWidth, planeHeight, 1)
 * -- the Target's own `t.scale.set(d,h,1)`. So `positionLocal.xy` is in
 * [-0.5, 0.5] and `positionLocal.xy * planeSize` is the point in CARD PIXELS,
 * which is the space every constant here lives in. The `planeSize` multiply on
 * the view vector and the matching divide in `toWorld` are a pair: together
 * they undo the anisotropic mesh scale so that directions are compared in the
 * same metric the normal is built in. Simplifying either away silently skews
 * refraction and reflection on any card that is not square.
 *
 * Why there are no debug branches in this file
 * --------------------------------------------
 * The O4A audit found that three's TSL emits a shared varying's unpack into
 * only the FIRST debug-select branch that references it, leaving every other
 * branch reading a zero-initialised private -- which is why the shipped body's
 * `refract()` consumes a zero normal. Nothing here reads a shared varying at
 * all: the normal is computed per fragment from `positionLocal`, so the defect
 * has no surface to occur on. Debug views are built as SEPARATE PROGRAMS via
 * `view`, never as branches inside the Beauty program.
 */

/**
 * Bundle-anchored Target constants. None is tunable; see the contract.
 *
 * Byte offsets in the comments below are REAL byte offsets into
 * `artifacts/f27/bundles/03lo820gl57km.js`, not indices into a decoded string.
 * The bundle carries non-ASCII characters before the material factory, so the
 * two differ by 10 there -- seeking to a character index lands mid-token on
 * something that still looks plausible.
 */
export const TARGET_BODY_SOURCE = {
  cornerRadiusRatio: 0.163,
  bevelWidthRatio: 0.192,
  bevelPower: 3.9,
  bevelMaxSlope: 1.74,
  thicknessPerCardScale: 155,
  rimWidthPerCardScale: 10,
  ior: 2.3,
  refractStrength: 0.7,
  dispersion: 0.32,
  dispersionSamples: 5,
  fresnelF0: 0.045,
  envIntensity: 1.93,
  envMaxMix: 0.27,
  envRotation: -2,
  envRotationX: 0,
  rimIntensity: 0.11,
  gradientEpsilonRatio: 0.06,
  gradientEpsilonFloorPx: 0.35,
  travelZFloor: 0.05,
  etaFloor: 1.0001,
  alphaTest: 0.001,
  sdfAaFloor: 1e-4,
  sphereRadicandFloor: 1,
} as const;

/**
 * Sample count per quality level.
 *
 * The Target has TWO device tiers -- `maxDispersionSamples: low ? 3 : Infinity`
 * against a configured 5, so 5 on high and 3 on low. We have three quality
 * levels and a FROZEN adaptive-quality policy, so we read our level and map it
 * rather than adopting the Target's device predicate. Medium takes 5 so the
 * optical behaviour is identical across the two tiers a desktop review sees;
 * low keeps the Target's own floor of 3.
 */
export const V5_BODY_SAMPLES: Readonly<Record<V4QualityLevel, number>> = {
  high: 5,
  medium: 5,
  low: 3,
};

/** The Target's tent: max(0, 1 - |x - c| / 0.5), at bundle byte 1959836. */
function tent(x: number, centre: number): number {
  return Math.max(0, 1 - Math.abs(x - centre) / 0.5);
}

export type SpectralSampleV5 = { offset: number; weight: [number, number, number] };

/**
 * The Target's spectral sample table, built on the CPU exactly as the Target
 * builds it, so the weights arrive in the shader as literals.
 *
 * The normalisation is PER CHANNEL, not per sample: each of R, G and B sums to
 * 1 across the samples independently. That is what keeps an achromatic input
 * achromatic, and it is the structural reason the grayscale gate can be passed
 * at all -- per-sample normalisation would tint the whole card.
 */
export function spectralSamplesV5(count: number): SpectralSampleV5[] {
  const n = Math.max(3, Math.round(count));
  const rows: { offset: number; weight: number[] }[] = [];
  const sums = [0, 0, 0];
  for (let i = 0; i < n; i += 1) {
    const t = i / (n - 1);
    const w = [tent(t, 0), tent(t, 0.5), tent(t, 1)];
    sums[0] += w[0];
    sums[1] += w[1];
    sums[2] += w[2];
    rows.push({ offset: t - 0.5, weight: w });
  }
  return rows.map(({ offset, weight }) => ({
    offset,
    weight: [weight[0] / sums[0], weight[1] / sums[1], weight[2] / sums[2]],
  }));
}

/**
 * Geometry uniforms, shared across every per-clip material.
 *
 * The Target spreads ONE uniform block into each of its per-media materials
 * (`{...i ?? L3(r), coverScale, coverOffset}`), so a layout change writes each
 * value once rather than once per clip. Adopted unchanged.
 */
export function createTargetOpticalBodyUniformsV5() {
  const B = V4_OPTICS_CONFIG.material.systemB;
  return {
    /** (planeWidth, planeHeight) in world px. */
    planeSize: uniform(vec2(1, 1)),
    /** The LAYOUT sphere radius -- the card's curvature is the grid's. */
    sphereRadius: uniform(1000),
    /** 0.163 * planeWidth */
    cornerRadius: uniform(1),
    /** 0.192 * planeWidth */
    bevelWidth: uniform(1),
    /** 155 * cardScale */
    thickness: uniform(1),
    /** 10 * cardScale */
    rimWidth: uniform(1),
    ior: uniform(TARGET_BODY_SOURCE.ior),
    dispersion: uniform(TARGET_BODY_SOURCE.dispersion),
    refractStrength: uniform(TARGET_BODY_SOURCE.refractStrength),
    fresnelF0: uniform(B.fresnelF0),
    envIntensity: uniform(B.envIntensity),
    envMaxMix: uniform(B.envMaxMix),
    envRotation: uniform(B.envRotationY),
    envRotationX: uniform(B.envRotationX),
    rimIntensity: uniform(B.rimIntensity),
    /**
     * O2's NaN guard, retained and declared as a local deviation the Target
     * does not have: a hot HDR texel can be Inf, and 0 * Inf = NaN would
     * destroy the envMixScale = 0 floor.
     *
     * It DOES bind, and saying otherwise was an error worth correcting in
     * place. An earlier note here argued the ceiling could not matter because
     * 16 is far above envIntensity * envMaxMix = 0.521 -- but 16 bounds
     * RADIANCE and 0.521 is a dimensionless mix weight, so the comparison is
     * meaningless. Measured on the actual asset: 0.98% of the environment's
     * texels exceed 16 and the brightest is 3568, 223x the ceiling. Wherever a
     * card reflects one of those, this clamp makes our highlight dimmer than
     * the Target's.
     *
     * See o5-architecture.json / envSampleCeilingRetained.
     */
    envSampleCeiling: uniform(B.envSampleCeiling),
    /** QA scales, 1 in the product path. Never used to tune a look. */
    envMixScale: uniform(1),
    rimScale: uniform(1),
  };
}

export type TargetOpticalBodyUniformsV5 = ReturnType<
  typeof createTargetOpticalBodyUniformsV5
>;

/**
 * Per-frame uniform writes -- the Target's own, at bundle byte 1978213.
 *
 * `frame` is the FROZEN SourceExactLayoutFrame. L6 is never re-derived here:
 * our frame already reproduces it exactly at every O5 viewport, so reading it
 * is both correct and the only route that cannot drift from the layout the
 * rest of the app uses.
 */
export function applyTargetOpticalBodyFrameV5(
  u: TargetOpticalBodyUniformsV5,
  frame: {
    planeWidth: number;
    planeHeight: number;
    cardScale: number;
    sphereRadius: number;
  },
): void {
  const S = TARGET_BODY_SOURCE;
  u.planeSize.value.set(frame.planeWidth, frame.planeHeight);
  u.sphereRadius.value = frame.sphereRadius;
  u.cornerRadius.value = S.cornerRadiusRatio * frame.planeWidth;
  u.bevelWidth.value = S.bevelWidthRatio * frame.planeWidth;
  u.thickness.value = S.thicknessPerCardScale * frame.cardScale;
  u.rimWidth.value = S.rimWidthPerCardScale * frame.cardScale;
}

/** Build-time view selection. Each is a SEPARATE program, never a branch. */
export const V5_BODY_VIEWS = [
  "beauty",
  "sdf-mask",
  "analytic-normal",
  "refraction-only",
] as const;
export type V5BodyView = (typeof V5_BODY_VIEWS)[number];

export type TargetOpticalBodyOptionsV5 = {
  uniforms: TargetOpticalBodyUniformsV5;
  /** This card's OWN media texture. */
  media: Texture;
  /** The accepted O2 studio environment. */
  environment: Texture;
  /** Cover fit, from the FROZEN MediaFit result. */
  coverScale: [number, number];
  coverOffset: [number, number];
  quality: V4QualityLevel;
  view?: V5BodyView;
};

/** A per-clip material and the two uniforms the layout writes into it. */
export type TargetOpticalBodyHandleV5 = {
  material: MeshBasicNodeMaterial;
  coverScale: { value: Vector2 };
  coverOffset: { value: Vector2 };
  samples: number;
  view: V5BodyView;
};

/**
 * Build one card material.
 *
 * One material per CLIP, as the Target does -- not one per card. Safe because
 * nothing gives cards per-card opacity: no site in the Target bundle assigns
 * `.opacity` on these materials, and our own frozen motion does not either.
 */
export function createTargetOpticalBodyMaterialV5(
  options: TargetOpticalBodyOptionsV5,
): TargetOpticalBodyHandleV5 {
  const S = TARGET_BODY_SOURCE;
  const u = options.uniforms;
  const view: V5BodyView = options.view ?? "beauty";
  const samples = V5_BODY_SAMPLES[options.quality];
  const spectral = spectralSamplesV5(samples);

  const coverScale = uniform(vec2(options.coverScale[0], options.coverScale[1]));
  const coverOffset = uniform(vec2(options.coverOffset[0], options.coverOffset[1]));

  const mediaTex = texture(options.media);
  const envTex = texture(options.environment);
  const half = u.planeSize.mul(0.5);

  // --- sphere and dome, bundle bytes 1973800 / 1973917 -------------------
  const sphereZ = Fn(([p]: [any]) =>
    sqrt(max(u.sphereRadius.mul(u.sphereRadius).sub(p.dot(p)), float(S.sphereRadicandFloor))),
  );
  const domeZ = Fn(([p]: [any]) => sphereZ(p).sub(u.sphereRadius));

  // --- rounded-rect SDF, byte 1973962 ------------------------------------
  const sdfAt = Fn(([p]: [any]) => {
    const r = min(u.cornerRadius, min(half.x, half.y));
    const q = abs(p).sub(half).add(r);
    return length(max(q, vec2(0))).add(min(max(q.x, q.y), float(0))).sub(r);
  });

  // --- bevel thickness profile, byte 1974177 -----------------------------
  const bevelOf = Fn(([s]: [any]) => {
    const t = clamp(float(1).add(s.div(max(u.bevelWidth, float(0.001)))), 0, 1);
    const k = max(float(S.bevelPower), float(1));
    return pow(max(float(1).sub(pow(t, k)), float(0)), float(1).div(k)).mul(u.thickness);
  });
  const thicknessAt = Fn(([p]: [any]) => bevelOf(sdfAt(p)));

  // --- direction back to world, byte 1974489 -----------------------------
  // The xy divide undoes the (planeWidth, planeHeight, 1) mesh scale; it is
  // the exact inverse of the planeSize multiply on the view vector below.
  const toWorld = Fn(([d]: [any]) =>
    modelWorldMatrix.mul(vec4(d.xy.div(u.planeSize), d.z, 0)).xyz.normalize(),
  );

  /** The whole body colour chain. Returns the analytic normal too, so the
   *  normal debug view is the SAME expression the Beauty path uses. */
  const bodyChain = () => {
    const p = positionLocal.xy.mul(u.planeSize).toVar();
    const sdf = sdfAt(p).toVar();

    // Numeric central-difference gradient of the thickness field.
    const eps = max(
      u.bevelWidth.mul(S.gradientEpsilonRatio),
      float(S.gradientEpsilonFloorPx),
    ).toVar();
    const grad = vec2(
      thicknessAt(p.add(vec2(eps, 0))).sub(thicknessAt(p.sub(vec2(eps, 0)))),
      thicknessAt(p.add(vec2(0, eps))).sub(thicknessAt(p.sub(vec2(0, eps)))),
    )
      .div(eps.mul(2))
      .toVar();
    const slope = length(grad).toVar();
    // Magnitude clamp preserving direction -- NOT a normalise.
    const clampedGrad = grad.mul(
      min(slope, float(S.bevelMaxSlope)).div(max(slope, float(1e-4))),
    );

    // The card's own tilt on the layout sphere.
    const curvature = p.div(sphereZ(p)).toVar();

    // The analytic normal. No varying, no shared unpack -- see the header.
    const N = vec3(curvature.sub(clampedGrad), float(1))
      .normalize()
      .mul(faceDirection)
      .toVar();

    // View vector, built in LOCAL space then scaled into the same
    // anisotropic metric the normal lives in.
    const camLocal = modelWorldMatrixInverse.mul(vec4(cameraPosition, 1)).xyz;
    const surface = vec3(positionLocal.xy, domeZ(p));
    const toCam = camLocal.sub(surface).toVar();
    const V = vec3(toCam.xy.mul(u.planeSize), toCam.z).normalize().toVar();

    // --- per-IOR spectral refraction, byte 1975453 ----------------------
    // Every sample runs its OWN refract() against the analytic normal and
    // samples the card's OWN media at level 0. The UV is CLAMPED before the
    // cover transform, so a refracted sample can never reach outside the
    // media's own frame -- which is what makes own-media isolation
    // structural rather than incidental.
    const baseUv = uv();
    let accumulated: any = vec3(0);
    for (const sample of spectral) {
      const eta = float(1).div(
        max(u.ior.add(u.dispersion.mul(float(sample.offset))), float(S.etaFloor)),
      );
      const r = refract(V.negate(), N, eta);
      const travel = u.thickness.div(max(abs(r.z), float(S.travelZFloor)));
      const displaced = baseUv.add(
        r.xy.mul(travel).mul(u.refractStrength).div(u.planeSize),
      );
      const sampleUv = clamp(displaced, 0, 1).mul(coverScale).add(coverOffset);
      const rgb = mediaTex.sample(sampleUv).rgb.mul(
        vec3(sample.weight[0], sample.weight[1], sample.weight[2]),
      );
      accumulated = accumulated.add(rgb);
    }
    const body = accumulated.toVar();

    // --- environment, byte 1975760 --------------------------------------
    const Nw = toWorld(N).toVar();
    const Vw = toWorld(V).toVar();
    const reflected = Vw.negate()
      .sub(Nw.mul(Vw.negate().dot(Nw).mul(2)))
      .normalize()
      .toVar();
    const cy = cos(u.envRotation);
    const sy = sin(u.envRotation);
    const rotY = vec3(
      reflected.x.mul(cy).sub(reflected.z.mul(sy)),
      reflected.y,
      reflected.x.mul(sy).add(reflected.z.mul(cy)),
    );
    const cx = cos(u.envRotationX);
    const sx = sin(u.envRotationX);
    const rotX = vec3(
      rotY.x,
      rotY.y.mul(cx).sub(rotY.z.mul(sx)),
      rotY.y.mul(sx).add(rotY.z.mul(cx)),
    );
    const envColor = envTex
      .sample(equirectUV(rotX))
      .rgb.clamp(0, u.envSampleCeiling)
      .toVar();

    // Schlick, exponent 5, on the LOCAL-space dot -- before toWorld().
    const fresnel = u.fresnelF0.add(
      float(1)
        .sub(u.fresnelF0)
        .mul(pow(saturate(float(1).sub(N.dot(V))), 5)),
    );
    const envMix = min(
      saturate(fresnel.mul(u.envIntensity)),
      u.envMaxMix,
    ).mul(u.envMixScale);

    // --- white SDF rim, byte 1976273 ------------------------------------
    const rim = smoothstep(u.rimWidth.negate(), float(0), sdf)
      .mul(u.rimIntensity)
      .mul(u.rimScale);
    // rimColor and rimColorTop are both #ffffff in the shipped settings, so
    // the Target's vertical gradient between them is inert. It is transcribed
    // rather than folded away, because folding it away would silently discard
    // a parameter the Target exposes.
    const rimColor = vec3(1, 1, 1);

    const colour = mix(body, envColor, envMix).add(rimColor.mul(rim));
    return { colour, N, sdf, body };
  };

  // --- alpha, byte 1976585 ------------------------------------------------
  const alphaNode = Fn(() => {
    const sdf = sdfAt(positionLocal.xy.mul(u.planeSize));
    const aa = max(fwidth(sdf).mul(0.5), float(S.sdfAaFloor));
    return float(1).sub(smoothstep(aa.negate(), aa, sdf)).mul(materialOpacity);
  });

  const material = new MeshBasicNodeMaterial({
    transparent: true,
    alphaTest: S.alphaTest,
    depthWrite: true,
    depthTest: true,
    // Transcribed from the Target, and INERT in exactly the same way there.
    // three's WebGPU node renderer never reads Material.toneMapped: the string
    // occurs 0 times in our three.webgpu.js, and all four reads in the
    // Target's own bundle are WebGL-only parameter builders. So the Target's
    // cards are tone-mapped by its renderer's output stage despite this flag,
    // and so are ours. Setting the renderer to NoToneMapping for this lane
    // would introduce a difference the Target does not have -- being faithful
    // here means reproducing the inertness, not compensating for it.
    toneMapped: false,
  });
  material.name = `MirrorWeb.V5.TargetOpticalBody.${view}`;

  // The dome is applied in the VERTEX stage, which is why the plane carries
  // 16x12 segments: the curvature is resolved by tessellation, not by a
  // fragment trick.
  material.positionNode = vec3(
    positionLocal.xy,
    domeZ(positionLocal.xy.mul(u.planeSize)),
  );

  // Build-time view selection. Each view produces a DIFFERENT PROGRAM; there
  // is no runtime branch and no shared varying, so the O4A codegen defect
  // cannot occur here.
  material.colorNode = Fn(() => {
    const chain = bodyChain();
    if (view === "analytic-normal") return chain.N.mul(0.5).add(0.5);
    if (view === "sdf-mask") {
      const inside = smoothstep(float(0), float(-1), chain.sdf);
      return vec3(inside, inside, inside);
    }
    // The spectral accumulator BEFORE environment and rim. Named
    // "refraction-only" and not "media-only" because the evidence
    // package uses "media-only" for the media-PLANE capture, which is
    // a different picture answering a different question.
    if (view === "refraction-only") return chain.body;
    return chain.colour;
  })();

  material.opacityNode = alphaNode();

  return {
    material,
    coverScale: coverScale as unknown as { value: Vector2 },
    coverOffset: coverOffset as unknown as { value: Vector2 },
    samples,
    view,
  };
}
