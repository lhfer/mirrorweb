# O5 product review — source-exact card optical body

Reviewed at `c940a3102b466476249d45f632bc9ccdcd1bcb9f`. This is the product
record for the O5 round and the document that opens O5R.

O5 stopped substituting one optical term at a time and built the Target's
**complete card optical body as one coherent material system**. The
architecture is accepted. The absolute gate result is **not** overwritten: it
stands sealed at **FAIL, 8 / 14**.

What changed in this review is the *reading* of those six failures. Two are
candidate residuals confined to one viewport. Four are instruments that could
not do the job they were sealed to do — and two of the eight passes carry no
signal at all. That is the finding O5R is opened to repair.

## ACCEPTED

### The Target optical body source contract

57 sites, 0 failed, every offset **seek-verified** against the live bundle in
raw bytes rather than in a decoded string — the bundle carries six non-ASCII
characters before the material factory, so a decoded index reads ten low and an
unverified offset would have been fiction. Absences are proved over two spans:
the 3747-byte material factory for output claims, the 9886-byte card component
for geometry claims, because the factory contains no geometry code and an
absence claimed there would be vacuous.

Accepted as the canonical description of the Target's card material.

### The O5 target-source architecture

Accepted as the architecture, in full:

- `PlaneGeometry(1,1,16,12)`, unit plane scaled by the layout
- vertex-stage sphere dome in `positionNode`
- rounded-rect SDF alpha with `fwidth` antialiasing
- analytic bevel normal — power-law profile, central-difference gradient,
  slope clamp, sphere curvature term
- own-media texture per card, clamp-then-cover
- per-IOR `refract()`, five calls at high and medium, three at low
- per-channel-normalised spectral tent weights
- level-0 sampling, no mip blur
- no adaptive contrast, edge lift or internal shadow
- the accepted System B studio reflection **integrated into the same body**
- white SDF rim
- no separate reflection shell
- no scene-colour pass
- material rebuild on a quality step, because the sample count is a build-time
  literal

### The own-media pipeline

Accepted, and proved at runtime rather than by a string search: the
scene-colour pass draws **0 calls** and the media plane is hidden, yet the cards
still show media. Neighbour bleed is structurally impossible — the refracted UV
is clamped before the cover transform.

### Per-IOR spectral refraction and the analytic normal

Accepted. The compiled program contains exactly five `refract()` calls at high
and three at low, tracking the sample count; the analytic normal decodes to
unit length on **95.0%** of 634 495 card pixels with per-channel standard
deviation [46.94, 46.12, 46.62]. The O4A zero-normal defect has **no surface**
here: the candidate program declares no shared normal varying at all.

### The SDF silhouette mechanism

The mechanism is accepted as transcription. The *measurement* of it is not —
see item 10 below.

### The no-scene-colour architecture

Accepted, and §十 authorised it explicitly. 52 draw calls in the control, 0 in
the candidate; ready in 305 ms against 361; CPU frame p99 1.0 ms against 1.4.

### Control identity — 35 / 35

`opticalBody=current` at the O5 code commit against a worktree build of
`5a87751`: **exactly zero** differing pixels across 5 viewports × 7 states,
every state probe matching, 0 console errors. Re-verified after the one
mid-round code change and still exactly zero.

Every O5 comparison is therefore against the accepted O2 body and not against
something that drifted.

### Compiled body audit — 15 / 15

Including a genuine positive control for the no-mip claim: the same probe finds
20 explicit-LOD samples in the control program and 0 in the candidate.

### The reflection-band result

**Accepted as the round's substantive optical achievement.** The band enters the
Target's window at **every** viewport — the measurement O3 and O4 both failed:

| viewport | Target | control | candidate | window | Δ |
|---|---|---|---|---|---|
| 1440x900 | 3.3 px | 15.3 px | **3.3 px** | ±1.5 | 0.0 |
| 390x844 | 1.5 px | 8.0 px | **2.0 px** | ±1.5 | 0.5 |
| 844x390 | 2.0 px | 8.0 px | **2.0 px** | ±1.5 | 0.0 |
| 700x700 | 2.0 px | 7.0 px | **2.0 px** | ±1.5 | 0.0 |

### The HF spectral-structure result

Per-tile high-frequency structure correlates **0.9274** with the Target across
4477 tiles, against the control's 0.6886 and a pre-registered floor of 0.70. HF
energy retention 1.0276 — the candidate reads 153.68 against the Target's
149.55, where the control reads 183.34.

Interior chroma, which was not part of any item's verdict and is the more
telling number: on hf-checker the candidate reads **79.07** against the Target's
**79.77**, where the control reads **0.12**. The candidate reproduces the
Target's interior spectral behaviour almost exactly; the control has none of it.

### The pipeline direction

Accepted as a direction. Not accepted as a resource verdict — see §十二 of the
O5R brief and the NOT YET ACCEPTED list below.

## NOT YET ACCEPTED

- **The shipped default flip.** `opticalBody=current` remains shipped.
- **390x844 dark-side luma.** 58.46 against a Target of 51.28, window ±6.0.
- **390x844 white reflection ratio.** 3.8712 against a Target of 4.9035,
  window ±0.15.
- **The current O5 absolute-gate verdict**, as a statement about the candidate.
  It stands sealed as the O5 result and is re-run in O5R as a regression, but
  four of its six failures are not readings of the candidate.
- **Target Visual PASS.** NOT ASSERTED.

## The six failures, classified

The count is not the finding. The kind is.

### REAL CANDIDATE RESIDUAL

**Item 2 — dark-side edge luma, at 390x844 only.** 58.46 against 51.28. Inside
the window at the other three viewports (48.61/48.15, 87.05/86.19, 44.47/44.20),
and moved toward the Target from a control that was roughly twice as bright at
every viewport.

**Item 3 — white reflection ratio, at 390x844 only.** 3.8712 against 4.9035.
Inside the window at the other three (4.3776/4.3619, 2.2805/2.2815,
5.9784/5.8683).

Portrait mobile is the narrowest card in the set, so its bevel occupies the
largest fraction of the card — the one geometry where an error in the bevel
profile or in the reflected energy has the most room to show.

### INSTRUMENT UNREADABLE / INVALID

**Item 4 — grayscale absolute chroma ceiling.** The coding scores p99.5 chroma
against an absolute ceiling of 6.0. The candidate reads 18.0. So does the
control, at 18.0 — and so does **the Target, at 30.0**, five times the ceiling.
The ceiling is simply too tight for media that has been through a 4:2:0 video
encode, where chroma subsampling puts colour on every sharp luminance edge. A
test the Target fails worse than the candidate is not measuring the candidate.

**Item 7 — flat-card edge-compression baseline.** The analytic baseline assumes
the media maps linearly across a flat card. The card is a **domed plane under
perspective**, so it does not, and the guard sealed with the instrument
correctly refused to answer on most cards rather than emit a confident wrong
number (`flatBaselineVerified: false`). The guard worked as designed; what it
protected against was the model. One asymmetry is disclosed rather than
smoothed: the Target has no media-only render, so its baseline could not be
checked at all and its readings passed the guard by default.

**Item 9 — control-relative interior sharpness.** The coding asks that the
candidate be *no blurrier than the control*, which is the wrong question. On
hf-checker the Target reads 149.55, the control 183.34, the candidate 153.68 —
the candidate is far closer to the Target and fails the item **for being
closer**, because the control is sharper than the Target is.

Re-scoring by proximity would not simply flip it, and saying so matters more
than the excuse: the candidate wins hf-checker decisively (Δ 4.1 against the
control's 33.8) and loses bw-split (3.57 vs 3.40) and rgb-bars (3.21 vs 2.87)
narrowly. Those two assets have flat interiors, so the sharpness measure sits
near its own noise floor there — all three lanes read between 1.2 and 5.7 on a
scale where the textured asset reads 150. A 0.2 difference between numbers that
small is not evidence of anything.

**Item 10 — axis-aligned silhouette model.** The instrument evaluates an
axis-aligned rounded-rect SDF over the card's screen-space bounding box. The
cards are perspective-projected onto a sphere, so their quad corners sit up to
**109 px** from the bounding-box corners, and the region the instrument calls
"outside the silhouette" contains background and neighbouring cards. Both lanes
fail it — the control at 18 348 lit pixels, the candidate at 12 232 — which is
the tell: a test that fails the accepted body as well as the candidate is not
separating them. At 844x390 a synthetically **perfect** rounded-rect card scores
indistinguishably from the real render, so the item carries no silhouette signal
there at all.

## Two passes that may not be cited as proof

Recorded here because a pass that carries no signal is a worse liability than a
failure that does.

**Item 5 — saturated-edge metric.** Target 0.0, control 0.0, candidate 0.0 on
`fringeRB`, `fringeWidthPxMean` and `edgeChroma`, for rgb-bars, cool-blue and
warm-skin alike. Every lane returned the same constant. This is **unreadable**,
not a pass. It was scored PASS because the sealed coding's comparison
("closer to the Target than the control, no broader than either") is vacuously
true when all three inputs are zero.

**Item 14 — the third fringe sub-check.** `colouredGlassFrame_fringeWidthPx`
reads 0.0 for all three lanes, so its `candidateCloser: true` is vacuous. Item
14's verdict rests on the two sub-checks that **do** discriminate — band width
(3.3 vs the Target's 3.3, control 15.3) and interior HF energy (153.68 vs
149.55, control 183.34). That is stated in the O5 README and is restated here:
the item is not invalidated, but the fringe sub-check may not be cited.

Neither of these invalidates the product direction. Neither may be cited as
positive proof of it.

## What O5R is authorised to do

O5R is a **closure round**, not a new broad optics round. It may modify only:

- the O5 optical measurement instruments
- the one known non-source Target-body deviation, `envSampleCeiling = 16`
- QA-only structural controls
- evidence and product status

It may not touch a single Target source constant, the HDR asset, layout,
typography, motion, label culling, the render coverage verdict, media focus or
crop, the camera, or the adaptive quality policy. It does not flip the shipped
default and it does not enter Performance Final or merge main.

The sealed O5 gate is **not rewritten**. It is re-run unchanged as a regression
alongside the corrected gate.
