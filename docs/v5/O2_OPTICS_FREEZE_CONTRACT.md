# O2 System B optics freeze contract

O2 passed its absolute gate and product review accepted it. This file is the
record of what that freezes, at which heads, and — just as load-bearing —
what it deliberately does **not** freeze. The findings live in
[`qa-v5/optics-o2/README.md`](../../qa-v5/optics-o2/README.md); this file is
the decision.

## Acceptance record

| | |
| --- | --- |
| O2 System B absolute gate | **PASS** (15/15) |
| Product acceptance | **ACCEPTED** — O2 System B product review |
| O2 behaviour baseline | `e913aa6a33e384ba4fc80eb28b9a8718fb20e5b9` — the code commit every candidate capture was taken at |
| O2 accepted review tip | `fd12b97c4d9a28b732d3611035d98446a0201c68` |
| Selected product lane | **A+B** — `dispersionLaw=o1-spectral` |
| O1 System A historic verdict | **STILL FAILED** — see below |
| Target Visual PASS | **NOT ASSERTED** |
| Main merge / force push | **NOT AUTHORISED** |

## O1 is not retroactively overturned

System A entered the product path through the **O2 interaction gate only**.
The pre-registered §四 rule required A+B to beat B-only on all six criteria
under the same deterministic media in the same build; it did
(`qa-v5/optics-o2/candidate-selection.json`). That is a statement about A
*in combination with* B, measured at O2's thresholds.

It is not a re-scoring of O1. The O1 first-optics-candidate verdict remains
**FAILED ABSOLUTE GATE**, `e01fb30` remains an experimental lane in the
history, and no later round may cite A's presence in the product as evidence
that O1 passed.

## What O2 freezes

The System B architecture, as accepted:

- the deterministic shared-media harness — every optics candidate is scored
  against routed, frozen renditions, never a random Target page load
  (`qa-v5/optics-o2/shared-media-harness.json`)
- the environment asset `public/hdri/studio_small_03_1k.hdr` and its
  [provenance record](../../public/hdri/PROVENANCE.md) — CC0, byte-identical
  to the Target's served environment, obtained independently of the Target
- the integrated body-colour LERP: the white studio reflection is mixed
  **into** the body colour, not added as a second surface, and the Beauty
  path carries no shell double-count
- Schlick fresnel, F0 `0.045`, exponent `5`
- `envIntensity 1.93`
- `envMaxMix 0.27` — the reflection is a capped LERP, never additive energy
- `envRotationY -2`, `envRotationX 0`
- level-0 equirect sampling — no roughness, no PMREM, no blur
- sourceExact Beauty shell **OFF**
- the **A+B** default lane
- the `v_o2NormalView` branch-safe private varying, and the reason it exists:
  three's TSL emits a varying unpack only into the first debug branch that
  references it, so System B must not read the shared normal globals
- media-only output unchanged — the glass-hidden render is bit-identical
  across every lane
- `envMixScale` / `rimScale` as QA floor levers with product value `1`

## What O2 does NOT freeze

O2 accepted the reflection *mechanism*. It did not accept the field that
mechanism is evaluated on. The following are explicitly left open and are
the authorised O3 scope:

- **Geometry Normal as the System B fresnel-normal analogue** — the baked
  shoulder/rim vertex normal standing in for the Target's analytic bevel
  normal
- **`strongLensRim` as the white rim mask** — the geometry attribute
  standing in for the Target's rounded-rect SDF rim
- **reflection support width**
- **reflection band luminance**
- **rim spatial profile**

## Known O2 deviations, carried into O3

Measured on bw-split, desktop, at the accepted candidate:

| Measurand | O2 candidate | Target |
| --- | --- | --- |
| Reflection band width | 15.3 px | 3.3 px |
| Dark-side edge luma | 95.1 | 48.1 |
| Dark / bright ratio | 0.5006 | 0.2484 |

These were recorded as observed-not-gated at O2 and are the reason O3
exists. They are a **support-field** error — the reflection law is right and
the field it is evaluated on is too wide — so they may not be answered by
lowering `envIntensity`, `envMaxMix`, `fresnelF0` or `rimIntensity`.

## O3: the only authorised change

**Target Analytic Bevel Reflection Support**, and nothing else. O3 replaces
the support field — the normal and the mask System B consumes — with the
Target's analytic bevel field, and leaves every accepted O2 parameter above
at its frozen value.

O3 may not modify: Layout, Typography, Motion, Label / Render Culling, Media
Fit / Focus, the environment asset, `envIntensity`, `envMaxMix`, the env
rotations, Fresnel F0 / exponent, Dispersion, refraction offset / distance,
Blur, the scene-colour pipeline, Tone mapping, physical card geometry,
Adaptive Quality, or Camera.

## O4 is not authorised by this contract

Accepting O2 authorises O3's scope and no further. Own-media refraction, a
second refraction event, tone-mapping work and any re-opening of the frozen
list above each require their own product decision. Passing O3 does not
create one.
