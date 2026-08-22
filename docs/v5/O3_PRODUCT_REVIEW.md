# O3 product review — decision record

Product review of the O3 round, held at
`eba0aa0ccffc650768436f86018ab46152f5c475`. This file records what the
review accepted, what it rejected, and what it opened. It is a decision
record, not a re-argument of the evidence: the measurements live in
[`qa-v5/optics-o3/README.md`](../../qa-v5/optics-o3/README.md) and
[`o3-absolute-gate.json`](../../qa-v5/optics-o3/o3-absolute-gate.json).

| | |
| --- | --- |
| Reviewed round | O3 — Target Analytic Bevel Reflection Support |
| Review head | `eba0aa0ccffc650768436f86018ab46152f5c475` |
| O3 absolute gate | **FAILED** — 11/20 PASS, 9/20 FAIL |
| O3 product candidate | **REJECTED** |
| Shipped default | `reflectionSupport=geometry`, `dispersionLaw=o1-spectral` |
| Target Visual PASS | **NOT ASSERTED** |
| Main | no merge, no force push |

## Accepted

**O3 source forensics.** The Target's analytic bevel field is read out of
the bundle at 29 byte-anchored sites, 0 failed, every occurrence unique,
and the live bundle hash matches the captured one. Six sites are
independently re-verified against the O0 diagnosis and agree. This is now
the reference description of the Target's bevel support field and is
accepted as such.

**`TargetBevelFieldV4` transcription — ENGINEERING PASS.** The module is a
faithful transcription of those sites: rounded-rect SDF, superellipse
thickness at `bevelPower` 3.9, the coarse numeric gradient at
`max(bevelWidth * 0.06, 0.35)`, the `bevelMaxSlope` 1.74 clamp, the sphere
curvature term, and the rim band `smoothstep(-rimWidth, 0, sdf) * 0.11`.
Not one constant was chosen against a measured result. The plane→world
bridge is an identity rather than an analogue, because our card carries a
uniform `cardScale` that cancels exactly as the Target's `planeSize`
division does.

**The corrected instruments.** The F5 / F10 / F11 codings, their 36 unit
tests — including a non-monotonic path that genuinely fires — and the dry
run that exercised them on the already-accepted O2 captures before sealing.
Three further defects found and fixed inside the O3 round itself (profile
averaging across cards before thresholding; two aggregator shape errors)
are part of what is accepted here.

**The `target-sdf` diagnostic lane.** It stays in the tree, reachable by
`?reflectionSupport=target-sdf`, as
a diagnostic lane, a source reference, and the lane a post-body-fix
re-evaluation will be run on. It is not a product default and is not
scheduled to become one by this decision.

**The frozen-body-floor finding.** This is the round's substantive result.
With System B entirely off (`envMixScale=0`, `rimScale=0`) the two
reflection-support lanes are identical, and the frozen refraction /
dispersion / adaptive-contrast composition alone paints:

| Viewport | Local body floor, System B OFF | Target |
| --- | --- | --- |
| 1440x900 | 9.7 px | 3.3 px |
| 390x844 | 6.0 px | 1.5 px |
| 844x390 | 6.0 px | 2.0 px |

At every viewport the local body floor alone exceeds the Target's entire
measured band. That establishes the binding constraint, and it is why O4
exists.

## Rejected

**The O3 candidate as shipped default.** 9 of 20 absolute-gate items
failed. The candidate is not shipped.

**The default flip to `target-sdf`.** The sealed default-flip rule's
negative branch executed during the O3 evidence pass; this review affirms
it. `reflectionSupport` stays `geometry`.

**Further Rim / Fresnel / Env tuning.** Not reopened. O3 demonstrated that
the reflection support is not the binding constraint, so moving reflection
parameters could only mask a body-floor error. The O2 System B parameters
stay frozen exactly as
[`O2_OPTICS_FREEZE_CONTRACT.md`](O2_OPTICS_FREEZE_CONTRACT.md) sets them.

## How this round should be characterised

O3 is **not** "no progress", and it is **not** product accepted.

It is a round that produced an accepted source description, an accepted
transcription, accepted instruments, and one decisive measurement that
redirected the programme. The candidate was rejected on its own gate; the
knowledge the round produced was accepted. Both halves are true at once,
and the record should not be summarised as either half alone.

The specific thing O3 bought: before it, "our white band is too wide" had
at least two plausible causes — the reflection support field, or the body
underneath it. O3 removed the first by transcribing the Target's own field
exactly and measuring that the band stayed wide. What is left is the body.

## What O4 opens

One objective: **attribute and reduce the frozen body floor.**

O4 is scoped to the System-B-OFF body path and nothing else. It may not
modify layout, typography, motion, label culling, render culling, media
fit / focus, camera, card size, card placement, physical geometry, the O2
environment asset, `envIntensity`, `envMaxMix`, the env rotations, the
Fresnel F0 / exponent, the O2 shell-off architecture, the O3 rim source
constants, or the O3 analytic bevel source constants.

O4 selects and implements exactly **one** body subsystem, chosen by a rule
sealed before its candidate code exists. If no single subsystem satisfies
that rule, the correct outcome is to say so and stop rather than to
combine subsystems until something passes.

The current product remains the O2 geometry lane throughout.
