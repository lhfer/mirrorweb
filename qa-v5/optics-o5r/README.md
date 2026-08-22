# O5R — target-source optical body product closure

This is a **closure round**, not a new optics round. O5 built the Target's
complete card optical body and its absolute gate returned **FAIL, 8 / 14**.
The product review of that result found that only two of the six failures were
readings of the candidate; four were instruments that could not do the job they
were sealed to do, and two of the eight passes carried no signal at all.

O5R repairs those instruments, removes the one known non-source deviation in
the body, and re-scores. It does not tune a source constant, does not flip the
shipped default, and does not assert a Target Visual PASS.

The sealed O5 result is **not rewritten**. It is re-run unchanged, and it still
produces its own verdict: sealed 8 / 14 FAIL, re-run 8 / 14 FAIL, identical.

---

## The verdict

**Corrected O5R product gate: PASS 7 / FAIL 7 / NOT_APPLICABLE 0 /
INSTRUMENT_UNREADABLE 0 of 14 — gate FAIL.**

Instrument definitions were sealed in `instrument-contract.json` and committed
**before** any O5R candidate frame was captured. Six instruments, 66 of 66 unit
tests, every one carrying the six test kinds §三 requires: positive, negative,
Target self-test, Control self-test, Candidate-readable, and an explicit
UNREADABLE state.

| # | product system | status | rows |
|---|---|---|---|
| 1 | reflection band | PASS | 4 PASS |
| 2 | dark-side luma | FAIL | 3 PASS, 1 FAIL |
| 3 | white reflection ratio | FAIL | 3 PASS, 1 FAIL |
| 4 | grayscale / false colour | FAIL | 12 FAIL |
| 5 | saturated edge | FAIL | 12 FAIL |
| 6 | refraction compression | PASS | 3 PASS, 1 UNREADABLE |
| 7 | interior fidelity | FAIL | 10 PASS, 12 N/A, 2 FAIL |
| 8 | own-media isolation | PASS | — |
| 9 | silhouette | FAIL | 3 PASS, 1 FAIL |
| 10 | pointer path | PASS | 1 PASS, 3 UNREADABLE |
| 11 | temporal continuity | PASS | 20 clips, 4 lanes, none fired |
| 12 | mobile consistency | PASS | 12 PASS |
| 13 | full-frame readiness | PASS | 112 frames, 0 missing |
| 14 | pipeline / resources | FAIL | 7 PASS, 2 FAIL, 1 UNREADABLE |

An UNREADABLE row is never converted into a PASS. It is not converted into a
FAIL either.

**Final state: O5R TARGET-SOURCE BODY FAILED CORRECTED PRODUCT GATE.**

**Recommended product decision: keep `opticalBody=current` as the shipped
default and keep target-source as a candidate.** There are now two independent
reasons, not one — the portrait optical residuals that the authorised code
change did not close, and a candidate-lane memory retention §十二 found that the
shipped lane does not have. The agent prepares evidence; it does not approve
itself.

---

## The one code change, and what it did

§十 authorised removing `envSampleCeiling = 16` — a clamp we added in O2 that
the Target does not have — on condition that the HDR asset be audited first.

**The audit came first.** `hdr-radiance-audit.json` decodes the product HDR
from its own bytes with a from-scratch Radiance decoder: 1024 × 512, 524 288
texels, **0 NaN, 0 Inf**, maximum radiance 3581.99, p99 14.05, p99.9 124.05,
p99.99 2971.6. **0.9055%** of colour channels exceed 16 and **5186 texels
(0.9892%)** carry at least one — so the clamp was not decorative: roughly one
texel in a hundred was being dimmed, and the brightest by a factor of 224.
Verdict **SOURCE ASSET FINITE**, `authorisesUnclamp: true`.

The safety argument is **structural, not statistical**: three's RGBE decode
applies `Math.min(v, 65504)` per channel before packing the half-float, so the
sampled texture cannot carry Inf or NaN whatever the file encodes — and the
Target, loading the same asset through the same loader, is bounded identically.
Verified against the vendored loader source rather than assumed.

`source-env-correction.json` scores the change from the **generated WGSL**,
7 / 7, with the sealed lane standing beside it as a positive control:

- the clamp is present in `target-source` and absent in `target-source-unclamped`
- the O5R program is **84 bytes shorter** — a ceiling swapped for a soft knee or
  a tone curve would make it longer, and §十 forbids all three
- `environmentMode=off` **omits the environment sample completely**: 5 texture
  samples against 6 (exactly the five per-IOR media samples), 0 `atan2`, 0
  `asin`, 4 bindings against 6. Not `envMixScale = 0` multiplied onto an
  already-sampled value, which is the shape §十 rules out
- five `refract()` calls in every mode, unchanged
- four distinct measurement-program hashes, each smaller than Beauty — separate
  programs, not debug branches inside Beauty
- 0 console or page errors across all eight program captures

**One candidate only.** `target-source-unclamped` is the single variant §十
authorises. No constant was tuned and no second no-clamp variant exists.

### The two candidate lanes really are different programs

They read identically to four decimal places on most metrics, which is
physically right — the clamp only reaches pixels reflecting a texel above 16 —
but it is also what a capture mix-up would look like. So it is asserted rather
than argued: every `o5-clamped` capture reports `envSampleClamped: true` and
every `o5r-unclamped` capture reports `false`, with no exceptions in either
direction (`portrait-closure.json`, check 0).

---

## Portrait closure: the residual did NOT close

P0 is **390 × 844**, where both open O5 residuals live. The Target was
re-captured **three times per asset per viewport before any candidate frame was
scored**, and every window in this round is `max(that spread, a pre-registered
floor)`.

| metric | Target | control | O5 clamped | O5R unclamped | window | remaining |
|---|---|---|---|---|---|---|
| dark-side luma | 51.28 | 78.94 | 58.46 | **58.57** | ±6.0 | **7.29** |
| white reflection ratio | 4.9035 | 2.5755 | 3.8712 | **3.8676** | ±0.15 | **1.0359** |

The unclamp moved dark-side luma by **+0.11** of a 7.29 gap and white ratio by
**−0.0036** of a 1.0359 gap. §十一 is explicit about what happens next: report
the exact remaining difference, do not tune other constants, keep target-source
as a candidate, stop for product review. That is what this document does.

What the change *did* do is remove a documented non-source deviation. Whether
or not it moved these two numbers, the body is closer to the source contract
than it was.

`portrait-closure.json` scores eleven checks, **8 PASS / 2 FAIL / 1
UNREADABLE**. The two FAILs are the two rows above. The UNREADABLE is the
pointer path at 390 × 844, where no candidate lane produced a readable path.
The rest pass, including the three the unclamp specifically owes:

- **no HDR hot-pixel flash** — near-white card area compared against the
  Target's across 56 asset × viewport × pointer-state rows. The candidate's
  worst excess over the Target is **−0.01024** (it carries *less* near-white
  area than the Target everywhere), and the unclamp added at most **0.000989**
- **no NaN / Inf / black-card frame** — 0 cards below mean luma 1, 0 console
  errors. A non-finite fragment reaches an 8-bit attachment as zero, so at the
  pixel level these are the same measurement
- **no broad white shoulder** — worst excess over the Target **−0.008073**
- no regression at 1440 × 900, 844 × 390 or 700 × 700

---

## The repaired instruments, and what they say now

### §六 refraction compression — the round's substantive instrument result

The O5 instrument assumed the media maps linearly across a flat card. The card
is a **domed plane under perspective**, so it does not, and the sealed guard
correctly refused to answer rather than emit a confident wrong number.

The repair replays the source refraction formula on the CPU — live layout
frame, live card matrix, plane size, analytic normal, coverScale/coverOffset,
per-IOR source contract — and reads the candidate's own UV fields out of three
QA-only measurement programs (`uv-unrefracted`, `uv-refracted`,
`refraction-displacement`), which are separate programs, never branches inside
Beauty.

Two things had to be right and were not obvious:

- a disc inside the bevel is **smeared**, so its image centroid is not the
  refracted position of its centre. The replay forward-maps every card fragment
  and takes the centroid of those landing inside each disc — the same measurand
  a blob detector reads
- replay grid cells are not screen pixels. Converting by
  `px_per_cell = card_area_px / n²` was worth ~1.5× on every area ratio

**Validated against the Target's own render**, which is what makes it a
measurement rather than a model: replay residual **1.437 px** at 1440 × 900,
**1.397** at 390 × 844, **1.555** at 700 × 700, against a threshold of 3.0 px
decided from Target pixels alone.

| viewport | Target displacement | control | candidate | candidate vector Δ | control vector Δ |
|---|---|---|---|---|---|
| 1440x900 | 18.399 px | 14.724 | **19.029** | **0.793** | 8.879 |
| 390x844 | 6.432 px | 5.613 | **7.133** | **1.040** | 4.857 |
| 700x700 | 9.364 px | 5.264 | **10.156** | **1.079** | 5.045 |
| 844x390 | — | — | — | INSTRUMENT_UNREADABLE | — |

The candidate's displacement field enters the Target's window at every readable
viewport, four to seven times closer than the shipped body at each. 844 × 390
is UNREADABLE and reported as such: no card's Target replay validated inside
3.0 px there, so the viewport has no verified baseline and §六 says not to
score it FAIL. This is the measurement three rounds of flat-baseline
instruments could not make.

### §七 interior fidelity — the question was wrong, not the answer

O5 asked "is the candidate no blurrier than the control". On hf-checker the
control is *sharper than the Target*, so the candidate failed **for being
closer**. The repair asks `distance(candidate, Target)` against
`distance(control, Target)`, and marks flat-interior assets NOT_APPLICABLE by
name when the Target's own HF energy is below the pre-registered floor — 12 of
24 rows — rather than letting a 0.2 difference near a 1–5 noise floor decide a
product.

On hf-checker at 1440 × 900 the candidate's distance from the Target is
**4.13** in HF energy where the control's is 33.79, and **2.69** in interior
chroma where the control's is **77.20**. Across the item the candidate is
closer to the Target on **45 of 48** quality comparisons.

It still FAILS, on exactly two rows: rgb-micro interior luminance and chroma at
390 × 844 and 844 × 390.

### §四 grayscale / false colour — one item, two opposite readings

The O5 coding scored p99.5 chroma against an absolute ceiling of 6.0. The
candidate read 18.0, the control 18.0, and **the Target 30.0** — five times the
ceiling. A test the Target fails worse than the candidate is not measuring the
candidate. The repair is seven Target-relative, feature-local measurements with
the window set by the Target's own repeatability.

The repaired instrument still fails, and now it says something. It says two
different things, and they must not be collapsed:

| asset (1440x900) | Target | control | candidate | who is closer |
|---|---|---|---|---|
| bw-split, chroma at gradients | 6.99 | 7.41 | 12.26 | **control** |
| hf-checker, chroma at gradients | 84.67 | **1.20** | 86.72 | **candidate** |

On coarse achromatic edges the candidate carries roughly twice the Target's
edge chroma, and on bw-split the shipped body is closer at all four viewports.
On textured media the candidate reproduces edge chroma the shipped body misses
by a factor of seventy — and still fails, at a distance of 12 where the
alternative's distance is 94. Both readings are real. Reporting only the first
would misrepresent the candidate; reporting only the second would flatter it.

`checker-spectral-hf-checker-*.png` in the review package shows this directly:
the control's chroma panel is near-black where the Target's and the candidate's
are not.

### §五 saturated edge — was unreadable, now discriminates, still fails

O5 returned Target 0.0, control 0.0, candidate 0.0 for every saturated asset.
That was **unreadable, not a pass**; it scored PASS because "closer to the
Target than the control" is vacuously true when all three inputs are zero.

The repair is feature-local, with a **per-channel** gradient mask maximised
over R/G/B — a chroma-scalar mask has zero gradient across a red-to-blue
boundary, because max-minus-min is a saturation measure. On cool-blue at
1440 × 900 the candidate sits **2.15** from the Target in chroma at features
where the control sits **30.33**, and fringe localisation reads 0.6969 against
the Target's 0.71 and the control's 0.4518.

It FAILS, mostly on `broadRimColouredFraction`. It is also the **one item where
the shipped body is closer to the Target more often than the candidate is** —
26 quality comparisons to 22. The candidate wins where colour *sits* (chroma at
features 9–3, fringe localisation 10–2) and loses on how much of the rim
carries colour at all (1–11) and on chroma away from features (2–10).

### §八 silhouette — the reference is now right; the other half is not

O5 evaluated an axis-aligned rounded-rect SDF over the card's screen bounding
box, whose corners sit up to 109 px from the real projected quad. The repair
uses the **sdf-mask program's own coverage**: the Target's SDF rendered through
the real PlaneGeometry projection, the real card matrix and the real `fwidth`
alpha.

The projected reference is correct now. The **rendered** side still needs a
background to compare against, and that is where the remaining limit is — see
the disclosure below. The row stands as the sealed instrument scored it.

---

## Performance and resources — the one new failure this round found

§十二 replaces O5's five-minute start/end heap delta with **three independent
fifteen-minute candidate sessions plus a control reference**, sampled every ten
seconds, under a rotating workload: desktop drag and wrap, mobile touch and
wrap, landscape drag and wrap, and a high → medium → low → high quality cycle,
with a resize or orientation change between every phase.

**7 PASS / 2 FAIL / 1 UNREADABLE of 10 — item 14 FAILS.**

What passes: no material, geometry, texture, video-element or slot growth in
any session (identical first sample to last, both lanes); no duplicate video
element; no first-frame black card; adaptive-quality sample counts hold at
**5 / 5 / 3** across 180 quality steps per session; 0 console or page errors in
any session. Shader program count is UNREADABLE — the WebGPU backend does not
expose it, and draw calls answer a different question.

What fails: **the candidate lane retains JS-side memory across a session and
the shipped lane does not.**

| lane | heap start → end | final-third slope | GC trough, first third → final third |
|---|---|---|---|
| candidate s1 | 21.8 → 69.8 MB | 2.58 MB/min | 23.14 → 41.74 (**+18.59**) |
| candidate s2 | 27.0 → 53.7 MB | 1.86 MB/min | 22.63 → 42.66 (**+20.03**) |
| candidate s3 | 25.6 → 53.5 MB | 1.01 MB/min | 21.74 → 43.89 (**+22.15**) |
| control s1 | 19.6 → 20.4 MB | −0.20 MB/min | 20.34 → 19.30 (**−1.04**) |

The raw heap sawtooths under GC, so a least-squares slope through it mostly
reports where the endpoints landed — the forced-GC reading came out *above* the
final sample in two sessions, which a genuine collection cannot do. The **GC
trough** does not have that problem: a leak raises the floor the collector can
return to, and noise does not. It agrees with the slope and is far more
consistent: the candidate's floor rises 18.6 / 20.0 / 22.2 MB over ten minutes
in three independent sessions, and the control's falls 1.0 MB under an
identical workload.

The trough statistic was chosen **after** seeing the curve and is reported
beside the pre-registered slope check, never instead of it. It does not
overturn anything; it happens to point the same way.

Structural resources are flat, so what is retained is JS-side and invisible to
the pool state.

### Attributed: the quality-step material rebuild

In the rotating workload, "quality steps so far" and "minutes elapsed" are the
same variable, so those sessions could establish the fact but not the cause. A
diagnostic run separates them: five arms on the candidate lane, each running
**one** phase alone for six minutes.

| arm | work units | GC trough rise |
|---|---|---|
| idle (render loop only) | 0 | 1.99 MB |
| desktop drag + wrap | 144 | 0.89 MB |
| mobile touch + cancel | 144 | 1.21 MB |
| resize / orientation | 576 | 2.06 MB |
| **quality cycle** | **576** | **39.36 MB** |

The quality cycle is the source, by a factor of nineteen over every other arm —
including the resize arm, which drove the *same* number of work units and cost
2.06 MB. Per quality step: **≈ 68 KB retained**.

The candidate's spectral sample count is a build-time literal, so a quality
step must rebuild the body materials; the shipped body has nothing to rebuild.
But the rebuild **does** dispose the previous materials —
`InfiniteGlassGridV4.rebuildBodyMaterials` calls `dispose()` on every prior
handle after rebinding — so this is not a missing dispose call. What is
retained is whatever the node and pipeline caches hold per material, and naming
that exactly needs heap snapshots this round did not take.

Honest about scope: the §十二 sessions drove roughly 120 quality steps per ten
minutes, which at this per-step figure accounts for about a third to a half of
the 18.6–22.2 MB they showed. The claim is that the quality cycle is the
dominant phase by a wide margin, not that it is the only source.

This diagnostic is **not part of the gate**; item 14 fails on the sessions
themselves. But it is a genuine new finding about the candidate, not an
instrument artefact, and it is a second reason — independent of the optical
residuals — not to flip the default today.

---

## Temporal continuity

20 clips: pointer sweep, slow horizontal drag and fast flick at 1440 × 900,
touch drag-and-release at 390 × 844, and a pointer sweep on hf-checker — each
over all four lanes, every frame driven by a real mouse or touch event over
CDP through the same sequence module the motion gates use.

Scored by O5's **sealed** pop coding, imported unedited: no adjacent-frame
relative change above 40%, and no rim break. Nothing fired in any lane. The
worst adjacent jump anywhere is **2.34%** (candidate, touch-drag-release),
against a Target that reads 2.13% on the same gesture. No clip has all four
lanes returning the same value, so this is a readable pass rather than the
degenerate kind O5's item 5 turned out to be — though on the quietest clip
(pointer sweep, bw-split) three of the four lanes read 0.0009 and only the
shipped body differs, so that clip carries little signal on its own.

---

## Disclosures

These are limits of this round's evidence. They are recorded because a reader
who found them later would be right to distrust everything around them.

**1. The window floors are scale-blind (items 4 and 5).** Target repeatability
on deterministic media is essentially zero, so every window falls back to its
pre-registered floor: 3.0 chroma levels for item 4, against statistics ranging
1.8 → 218, and 0.004 area fraction for item 5, against `broadRim` fractions of
0.5 → 0.9. A floor that binds equally at both ends of that range is too tight
at the top and too loose at the bottom. The instruments discriminate strongly —
that is not in question — but a future round should make the floor relative to
the statistic's own scale. **This is disclosed, not relabelled**: the rows stand
as FAIL, exactly as O5's item 4 stood.

**2. Item 9's background ring is contaminated at packed layouts.** The
rendered-alpha side of the silhouette instrument estimates the background from a
6 px ring outside the card rect and calls a pixel "lit" when it differs by more
than 2/255. At these layouts the ring lands on **neighbouring cards**: its own
standard deviation is 9.5 to 77.4, which is 5× to 38× the detection threshold.

The consequences are visible in the readings and are stated plainly:

- at 1440 × 900, all three lanes read **17 416 / 17 418 / 17 412** lit pixels
  beyond the silhouette, out of the 17 430 the rect contains. The metric is
  saturated and identical across lanes; the three PASSes at 1440 × 900, 844 ×
  390 and 700 × 700 are **near-degenerate** and should not be cited as proof
- at 390 × 844 it does separate — and there the **candidate matches the
  projected silhouette best**: 528 lit pixels beyond, at a mean distance of
  **1.0 px** and a maximum of **1 px**, which is a one-pixel antialias band and
  nothing else. The Target reads 3114 and the control 3174, at mean distance
  5.3–5.4 px and a maximum of **23 px** — a distance no body glow explains, and
  their per-quadrant counts agree with each other to within 6% because they are
  seeing the same neighbouring-card content

The sealed degeneracy guard fires on *exact* equality, per §三's own wording,
so it correctly did not fire on values differing in the fourth decimal. The
instrument was sealed before capture and is **not edited after it**; the row is
reported as the sealed coding scored it, with this explanation attached.

**3. The Target renders its own labels; the candidate lanes do not.** The
Target draws a headline across the lower half of every card and has no QA
surface to switch it off, so the candidate lanes are captured with labels off
and the Target with labels on. This was disclosed in the sealed instrument
contract and drives the landmark instrument's upper-half scoring region. It is
visible in the overlays, where the Target panel carries text the others do not.

**4. Item 10's pointer path is readable at one viewport of four.** Three of its
four rows are UNREADABLE — no candidate reading at 390 × 844 or 700 × 700, no
usable path for either Target or candidate at 844 × 390. The item is PASS on
its one readable row, which is a weaker statement than a four-row PASS.

**5. Shader program count is not exposed** by the WebGPU backend. It is
reported as `null` rather than substituting draw calls, which answer a
different question.

**6. At 844 × 390 no card is fully visible**, so every per-card metric at that
viewport is read from the widest *drawn* card instead — a card the frame edge
crops. `corrected-product-gate.json → rectBasis` records which basis each
viewport used. It is the same basis O5 used, so the two rounds stay comparable,
and it is why 844 × 390 is the viewport that most often returns UNREADABLE
(item 6's replay baseline, item 10's pointer path).

---

## Candidate against the shipped body

The gate answers "is the candidate inside the Target's own spread". It does not
answer "is the candidate closer to the Target than the body we ship today", and
this round those questions come apart hard — item 4 fails on hf-checker at a
distance of 12 where the shipped body's distance is 94.

`corrected-product-gate.json → derivedCandidateVsControl` reports both
distances for every readable scored comparison. It is derived arithmetic over
the sealed instruments' own readings; it changes no status and is not part of
the gate.

**Of 204 quality comparisons: the candidate is closer to the Target on 133, the
shipped body on 58, and 13 are tied.** Per item:

| item | candidate closer | control closer | tied |
|---|---|---|---|
| 1 reflection band | 4 | 0 | 0 |
| 2 dark-side luma | 4 | 0 | 0 |
| 3 white ratio | 4 | 0 | 0 |
| 4 grayscale | 51 | 25 | 8 |
| 5 saturated edge | 22 | **26** | 0 |
| 7 interior fidelity | 45 | 3 | 0 |
| 9 silhouette | 3 | 4 | 5 |

Mask-size fields (`featurePixels`, `projectedPixels`, and similar) are tabulated
but excluded from these counts: "closer to the Target" on the size of a mask is
not a statement about optical quality.

---

## What did not move

- **Control identity: 35 / 35, exactly zero differing pixels.** `opticalBody=
  current` at the O5R head against a build of the accepted body — 5 viewports ×
  7 states, every state probe matching, 0 console errors. The shipped lane is
  untouched by the one authorised change.
- **Sealed O5 lane: 22 / 22 byte-identical.** `opticalBody=target-source` still
  renders the frames the sealed gate scored. Guaranteed structurally by a
  build-time flag that keeps the measurement expressions out of the Beauty
  program, rather than by trusting dead-code elimination.
- **The original O5 gate, re-run unchanged: 8 / 14 FAIL, identical per item.**
  `o5-gate.py` is imported and executed as it sits on disk; only its output path
  is redirected, and `artifacts/` is symlinked so its reads still resolve. Its
  verdict is history and regression, not an O5R result.
- **Own-media isolation:** 0 scene-colour draw calls in both candidate lanes
  against 43–52 in the control, at every viewport, with the media plane hidden
  and the cards still showing media.
- **Frozen regressions: 24 / 24 PASS.** The seventeen sealed suites are scored
  by `o5-regressions.py` imported unedited — V1 render culling, V0 label
  culling, Source Contract, Layout Source, Typography, Motion Freeze Smoke,
  Release History Smoke, Card/Label Motion, Wrap = 0, Touch/Pointer Cancel,
  Console/Page Errors = 0, the O2 harness and media-only controls, A+B
  dispersion selection, coverage/slot identity, media fit/focus, TypeScript,
  Vite build. Two of its REPO-absolute reads are remapped to this round's
  captures, listed by name in the output. Seven more suites are added for O5R,
  including **Candidate Quality 5 / 5 / 3** and **V1 Render Coverage Verdict
  unchanged** — the target-source body draws one mesh per card where the
  accepted body draws three, and the frozen verdict of *which slots draw* is
  identical across all four lanes at all four viewports.

---

## Files

| file | what |
|---|---|
| `o5-product-review.json` | the O5 product review, machine-readable: accepted, not-yet-accepted, the six failures classified, and what each repaired instrument said afterwards |
| `instrument-contract.json` | the sealed definitions — 5 laws, 6 instruments, sealed before candidate capture |
| `instrument-tests.json` | 66 / 66, every instrument with all six required test kinds |
| `hdr-radiance-audit.json` | the HDR decoded from its own bytes; the precondition §十 makes the code change conditional on |
| `source-env-correction.json` | 7 / 7, scored from the generated WGSL |
| `grayscale-v2.json` | §四 |
| `saturated-edge-v2.json` | §五 |
| `refraction-compression-v2.json` | §六 |
| `interior-fidelity-v2.json` | §七 |
| `silhouette-v2.json` | §八 |
| `portrait-closure.json` | §十一, and the exact remaining difference |
| `target-repeatability.json` | the Target's own spread, and the self-test it has to survive |
| `original-o5-gate-regression.json` | §十三A |
| `corrected-product-gate.json` | §十三B, and the derived candidate-vs-control distances |
| `pipeline-performance-v2.json` | §十二 |
| `regressions.json` | §十四 |
| `control-identity.json`, `sealed-lane-identity.json` | what did not move |
| `reflection-band.json`, `dark-side-luma.json`, `white-reflection-ratio.json`, `own-media-isolation.json`, `pointer-path.json`, `temporal-continuity.json`, `mobile-consistency.json`, `full-frame-readiness.json` | the remaining gate topics, one file each |
| `MANIFEST.json` | every file above with its SHA-256 |

This public tree contains **no Target pixels and no Target video**. Those live
only in the private review package,
`qa-v5/private/o5r-optical-body-review.zip`, whose `data/` directory carries a
complete copy of this tree.

---

## What this round did not do

Not done, by instruction:

- did not flip `opticalBody` away from `current`
- did not tune a source constant — ior, dispersion, sample count,
  refractStrength, bevelWidth, bevelPower, bevelMaxSlope, thickness, corner
  radius, fresnelF0, envIntensity, envMaxMix, env rotation, rimWidth,
  rimIntensity are all untouched, as are the HDR bytes and the exposure
- did not create a second candidate variant
- did not rewrite or overwrite the sealed O5 evidence
- did not change layout, typography, motion, label culling, the render coverage
  verdict, media focus or crop, the camera, or the adaptive quality policy
- did not enter Performance Final
- did not merge or push to main
- **did not assert a Target Visual PASS**
