# O1 — first Liquid Glass optics candidate: **FAILED**

System A (edge energy / dispersion / saturation) was selected and its
failure conditions pre-registered in `o1-selected-system.json` BEFORE the
candidate code existed. The candidate replaced the fixed R/B tap split
with the Target's own dispersion law, byte-anchored in the O0 forensics:
5 spectral samples along the refraction offset, per-sample UV scale, tent
RGB weights normalised per channel.

The pre-registered condition that fired, verbatim:

> white reflection ratio does not move (wrong root cause -> System B next)

## The floor experiment (the round's decisive finding)

The candidate rebuilt with `dispersionSpread=0` — dispersion OFF,
everything else identical — measures desktop edge chroma
**59.04** against Before's
**63.13**:
the entire dispersion mechanism is worth
**4.09 edge-chroma points**
on our own page (media-stable, within-page). Its share of the gap to the
Target is **9.5–15.0%**
depending on the Target's media draw — a small minority under every draw.
dispersion owns 9.5-15.0% of the desktop edge-chroma gap to the Target (depending on the Target's media draw; the same-page lever effect is exact: 4.09 points). The residual is System B: the Target desaturates its edges by LERPing toward the white env reflection under a fresnel cap (source-anchored in the O0 forensics), while our shell ADDS white over a still-saturated refracted edge.

The white reflection ratio at spread 0.3
(0.153) differs from the floor's at
spread 0 (0.152) by
+0.0010:
the system's one tunable lever moves white by essentially nothing. The O0
attribution is corrected forward in `o0-source-diagnosis.json`
(`attributionCorrectedByFloorExperiment`) — the O2 selection must read
that field.

## Metrics, absolute (Target | Before | Candidate)

| state | edge chroma T | B | C | fringe R-B T | B | C | white ratio T | B | C |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1440x900/rest | 20.14 | 63.13 | 59.63 | 19.64 | 59.46 | 58.02 | 0.1041 | 0.1438 | 0.153 |
| 1440x900/pointer-corner-br | 20.33 | 53.23 | 48.77 | 19.82 | 48.51 | 45.77 | 0.1044 | 0.1461 | 0.1528 |
| 390x844/rest | 32.46 | 42.0 | 37.83 | 28.48 | 23.39 | 20.35 | 0.1302 | 0.2858 | 0.2902 |
| 390x844/pointer-corner-br | 28.55 | 50.08 | 43.33 | 25.99 | 26.81 | 21.88 | 0.1535 | 0.3604 | 0.3678 |

Every touched metric moved in the PRE-REGISTERED expected direction
(edge chroma down, fringe R-B down, white up) on desktop and mobile:
yes, 12/12; none fell
below the Target's sampled edge chroma. Cross-page ABSOLUTE comparison
against the Target is draw-dominated and reported with its range: the
Target's band statistics swing with its per-load media shuffle by 20–50×
the candidate-vs-before deltas (`targetLaneVariance` in the gate JSON —
a methodological finding O2's gate must design around; our own lanes are
deterministic to ≤1.3 chroma points). And the movement is not visually
obvious: the frame still reads as a dark chromatic rim next to the
Target's white glassy one (edge strips in the private package). The brief
requires a visually obvious glass advance; direction-correct but
negligible is what this FAILED state is for.

Condition 3 ("any mobile metric regresses while desktop improves") is
evaluated by the selection file's own declared signs and does not fire;
a distance-to-target-sample coding was tried first, fires on the Target's
media draw rather than on the candidate, and is recorded — with the
per-repeat evidence that rejected it — inside the condition's entry in
the gate JSON.

## What did NOT move (controls)

- **Media-only invariance**: 4 comparisons vs the pre-O1
  build, frozen media — **0 differing pixels** in all. The glass was not
  "fixed" by desaturating the media.
- **Bright/dark cohorts** (per-card samples pooled over 3 repeat loads,
  split at the pooled median interior luminance): edge chroma falls from
  Before to Candidate in BOTH cohorts in 4/4 measured
  states (`brightDarkCohorts` in the gate JSON).
- **Frozen suites**, all re-run at this build:

| suite | result |
| --- | --- |
| renderCullingGate | PASS |
| labelCullingGate | PASS |
| sourceContract | PASS |
| typography | PASS |
| motionFreeze | PASS |
| cardLabelMotion | PASS |
| typescript | PASS |
| build | PASS |

## Files

| file | what |
| --- | --- |
| `o0-source-diagnosis.json` | shader forensics + ROI statistics, attribution corrected |
| `o1-selected-system.json` | the pre-registered selection and failure conditions |
| `o1-optics-gate.json` | metrics, direction checks, floor experiment, conditions |
| `o1-regressions.json` | every frozen suite at the O1 build |

Visual evidence (Target pixels included) is PRIVATE:
`qa-v5/private/o1-optics-review.zip`.
