import {
  Fn,
  abs,
  clamp,
  faceDirection,
  float,
  length,
  max,
  min,
  modelWorldMatrix,
  cameraViewMatrix,
  pow,
  smoothstep,
  sqrt,
  uniform,
  uv,
  varying,
  vec2,
  vec3,
} from "three/tsl";

/**
 * O3 -- the Target's analytic bevel reflection support.
 *
 * O2 adopted the Target's reflection LAW and product review froze it. What
 * O2 did not have is the FIELD that law is evaluated on: it stood our baked
 * geometry shoulder normal in for the Target's analytic bevel normal, and
 * the `strongLensRim` vertex attribute in for the Target's rounded-rect SDF
 * rim. That field spreads the white reflection over 15.3 px where the
 * Target spreads it over 3.3 px.
 *
 * This module is the Target's field, transcribed from the byte-anchored
 * source contract in `qa-v5/optics-o3/target-bevel-reflection-source.json`.
 * Every constant is a source constant; none was chosen against a measured
 * result.
 *
 * Coordinate space
 * ----------------
 * Everything is evaluated in PLANE-PIXEL space: the card's local XY scaled
 * to world pixels, with Z carrying the same pixel metric. That is the
 * Target's own convention (`positionLocal.xy.mul(planeSize)`), and our card
 * uv maps onto it exactly -- our sourceExact glass geometry is built at the
 * reference plane size and scaled UNIFORMLY by cardScale, so
 * `(uv - 0.5) * planeSize` reproduces the Target's plane point.
 *
 * Getting the normal back out is likewise an identity rather than an
 * analogue. The Target's bridge is
 * `normalize(modelWorldMatrix * vec4(v.xy / planeSize, v.z, 0))`, whose
 * division cancels its own (planeWidth, planeHeight, 1) mesh scale and
 * leaves the card's pure rotation. Our uniform cardScale cancels in the
 * same way under plain `normalize(modelWorldMatrix * vec4(v, 0))`, so both
 * reduce to the same rotation -- and dot products are therefore equal in
 * plane, world and view space.
 *
 * Scope: the outputs here may drive ONLY the System B fresnel, the System B
 * environment reflection direction, and the Target white rim. Refraction,
 * dispersion, blur, geometry position and the card silhouette keep their
 * frozen paths, even though the Target derives some of them from this same
 * field.
 */

/** The Target's shipped bevel constants (bundle byte 1303608). */
export const TARGET_BEVEL_SOURCE = {
  /** cornerRadius = 0.163 * planeWidth */
  cornerRadiusRatio: 0.163,
  /** bevelWidth = 0.192 * planeWidth */
  bevelWidthRatio: 0.192,
  bevelPower: 3.9,
  bevelMaxSlope: 1.74,
  /** thickness = 155 * cardScale */
  thicknessPerCardScale: 155,
  /** rimWidth = 10 * cardScale */
  rimWidthPerCardScale: 10,
  /** Numeric gradient step: max(bevelWidth * 0.06, 0.35) px. */
  gradientEpsilonRatio: 0.06,
  gradientEpsilonFloorPx: 0.35,
} as const;

export function createTargetBevelUniformsV4() {
  return {
    /** (planeWidth, planeHeight) in world px, written per layout frame. */
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
  };
}

export type TargetBevelUniformsV4 = ReturnType<typeof createTargetBevelUniformsV4>;

/** Per-frame uniform writes -- the Target's own, at bundle byte 1978215. */
export function applyTargetBevelFrameV4(
  u: TargetBevelUniformsV4,
  frame: { planeWidth: number; planeHeight: number; cardScale: number; sphereRadius: number },
): void {
  const S = TARGET_BEVEL_SOURCE;
  u.planeSize.value.set(frame.planeWidth, frame.planeHeight);
  u.sphereRadius.value = frame.sphereRadius;
  u.cornerRadius.value = S.cornerRadiusRatio * frame.planeWidth;
  u.bevelWidth.value = S.bevelWidthRatio * frame.planeWidth;
  u.thickness.value = S.thicknessPerCardScale * frame.cardScale;
  u.rimWidth.value = S.rimWidthPerCardScale * frame.cardScale;
}

export type TargetBevelFieldV4 = {
  /** Rounded-rect SDF in plane px; negative inside the card. */
  roundedRectSdf: any;
  /** Superellipse bevel thickness at this point, in plane px. */
  bevelThickness: any;
  /** Numeric gradient of the thickness field (dimensionless slope). */
  bevelGradient: any;
  /** The Target's analytic bevel normal, in VIEW space. */
  analyticBevelNormalView: any;
  /** smoothstep(-rimWidth, 0, sdf) -- the Target's rim band. */
  targetRimMask: any;
  /** clamp(slope / bevelMaxSlope, 0, 1). QA and debug only. */
  bevelSupportMask: any;
};

/**
 * Build the field.
 *
 * The card uv is read through its OWN varying, and every CONSUMER gets its
 * own field with its own varying name. This is the same defence the O2
 * System B block needed, carried one step further: three's TSL emits a
 * varying's unpack only into the FIRST debug-select branch that references
 * it, so two branches sharing one varying would leave the later one reading
 * zeros. One varying per branch means each is unpacked where it is used --
 * which is why the debug views below call this again rather than reusing
 * the beauty path's field.
 */
export function createTargetBevelFieldV4(
  u: TargetBevelUniformsV4,
  varyingName = "v_o3CardUv",
): TargetBevelFieldV4 {
  const S = TARGET_BEVEL_SOURCE;

  const cardUv = varying(uv(), varyingName);
  const halfExtent = u.planeSize.mul(0.5);
  const p = cardUv.sub(0.5).mul(u.planeSize);

  // Rounded-rect SDF, verbatim (bundle byte 1973982).
  const sdfAt = Fn(([q]: [any]) => {
    const r = min(u.cornerRadius, min(halfExtent.x, halfExtent.y));
    const d = abs(q).sub(halfExtent).add(r);
    return length(max(d, vec2(0)))
      .add(min(max(d.x, d.y), float(0)))
      .sub(r);
  });

  // Superellipse thickness profile of the SDF, verbatim (byte 1974197).
  const thicknessOf = Fn(([s]: [any]) => {
    const t = clamp(float(1).add(s.div(max(u.bevelWidth, float(0.001)))), 0, 1);
    const power = max(float(S.bevelPower), float(1));
    return pow(
      max(float(1).sub(pow(t, power)), float(0)),
      float(1).div(power),
    ).mul(u.thickness);
  });

  const thicknessAt = Fn(([q]: [any]) => thicknessOf(sdfAt(q)));

  const sdf = sdfAt(p).toVar();

  // Numeric central difference over the THICKNESS field (byte 1974680).
  // The step is deliberately coarse -- it is what keeps the bevel normal
  // smooth through the corners instead of ringing.
  const eps = max(
    u.bevelWidth.mul(S.gradientEpsilonRatio),
    float(S.gradientEpsilonFloorPx),
  ).toVar();
  const grad = vec2(
    thicknessAt(p.add(vec2(eps, 0))).sub(thicknessAt(p.sub(vec2(eps, 0)))),
    thicknessAt(p.add(vec2(0, eps))).sub(thicknessAt(p.sub(vec2(0, eps)))),
  ).div(eps.mul(2)).toVar();

  // Slope clamp: the normal is never tilted past atan(1.74) = 60.1 deg.
  const slope = length(grad).toVar();
  const clampedGrad = grad.mul(
    min(slope, float(S.bevelMaxSlope)).div(max(slope, float(1e-4))),
  );

  // Sphere term: the card is a section of the LAYOUT sphere, so its normal
  // varies across the face by exactly this much. The rigid rotation that
  // puts the card on the sphere is applied by the scene graph, in both the
  // Target and here, so this is additional rather than duplicated.
  const sphereZ = sqrt(
    max(u.sphereRadius.mul(u.sphereRadius).sub(p.dot(p)), float(1)),
  );
  const sphereTerm = p.div(sphereZ);

  const normalPlane = vec3(sphereTerm.sub(clampedGrad), float(1))
    .normalize()
    .mul(faceDirection)
    .toVar();

  const analyticBevelNormalView = normalPlane
    .transformDirection(modelWorldMatrix)
    .transformDirection(cameraViewMatrix);

  return {
    roundedRectSdf: sdf,
    bevelThickness: thicknessOf(sdf),
    bevelGradient: grad,
    analyticBevelNormalView,
    targetRimMask: smoothstep(u.rimWidth.negate(), float(0), sdf),
    bevelSupportMask: clamp(slope.div(float(S.bevelMaxSlope)), 0, 1),
  };
}
