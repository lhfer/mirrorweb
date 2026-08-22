# O5R product review — corrected instruments + source environment

Reviewed at `445037e11eb44ae07bca6360707e043d969b1d4b`. This is the product
record for the O5R closure round and the document that opens O5F.

O5R was a closure round: it repaired the four instruments the O5 review found
unable to discriminate, removed the one known non-source deviation
(`envSampleCeiling = 16`) after an HDR radiance audit proved removal safe, and
re-scored everything under a corrected gate. The corrected gate result is
**sealed and not rewritten**:

> **PASS 7 / FAIL 7 / NOT_APPLICABLE 0 / INSTRUMENT_UNREADABLE 0 — FAIL.**
> **O5R TARGET-SOURCE BODY FAILED CORRECTED PRODUCT GATE.**

`target-source-unclamped` is now the **only active optics candidate**. The
sealed `target-source` (clamped) lane is retained **for regression only** — its
evidence is never modified, so the original O5 gate stays re-runnable against
the exact pixels it scored. The shipped default remains `opticalBody=current`,
and this round does not flip it.

## ACCEPTED

### The HDR audit and the unclamp, as a source correction

The Target does not clamp the HDR at 16. Ours did — an O2 guard against a
non-finite texel. The audit made removal structural rather than statistical:
three's own RGBE decode clamps every channel at 65504 before packing the
half-float, so the sampled texture cannot carry Inf or NaN whatever the file
encodes, and the Target is bounded identically by the same loader. The asset
itself decodes finite everywhere — 0 NaN, 0 Inf — with 0.99% of texels above
the old ceiling. Accepted as a **source correction**, not a tune: no
replacement clamp, no new constant.

### The structural environment-off program

`environmentMode=off` omits the environment from the **program** — no texture
fetch, no Fresnel, no mix — rather than multiplying a sampled value by zero.
Accepted as the structural floor control §十 asked for.

### The corrected refraction-compression instrument, and its result

The O5 instrument assumed a flat card and correctly refused to answer. The
O5R replacement replays the source displacement formula through the **live**
card matrix and camera, and is validated on the Target's own render to
1.4–1.6 px before it scores anyone. The candidate's displacement field enters
the Target's window at every readable viewport — vector Δ 0.79 / 1.04 /
1.08 px against the shipped body's 8.88 / 4.86 / 5.05. Accepted.

### The reflection-band result

Still inside the Target's window at **all four** viewports (3.3 / 2.0 / 2.0 /
2.0 px against Target 3.3 / 1.5 / 2.0 / 2.0, window ±1.5), where the control
reads 15.3 / 8.0 / 8.0 / 7.0. Accepted, carried from O5 and re-confirmed under
the corrected gate.

### Own-media isolation

No neighbour bleed, no scene-colour cross-card contamination; the refracted UV
clamp makes it structural. Accepted.

### Temporal continuity

No pop during pointer sweep, slow drag, fast flick or touch release. Accepted.

### The mobile direction

Every edge metric moves **toward** the Target at every viewport, including the
two portrait metrics that do not enter their windows. Accepted as a direction.

### Control identity, sealed-lane identity, frozen regressions

Control identity 35/35 exactly zero. The sealed O5 lane byte-identical,
22/22. Frozen regressions 24/24 PASS, with the sealed O5 gate re-run
**unchanged** to its own 8/14. Accepted.

## NOT ACCEPTED

- **The default flip.** `opticalBody=current` remains shipped.
- **390x844 dark-side luma.** 58.57 against a Target of 51.28, window ±6.0.
  The authorised unclamp moved it +0.11 of a 7.29 gap.
- **390x844 white reflection ratio.** 3.8676 against a Target of 4.9035,
  window ±0.15. The unclamp moved it −0.0036 of a 1.0359 gap.
- **Candidate memory/resource stability.** The candidate lane's GC trough
  rises 18.59 / 20.03 / 22.15 MB per ten minutes across three sessions where
  the shipped lane's falls 1.04 MB under the identical workload. A five-arm
  diagnostic attributes it to the quality-step material rebuild: 39.36 MB in
  six minutes in the quality-cycle arm against at most 2.06 MB in every other
  arm — about 68 KB per step — despite `dispose()` being called.
- **Target Visual PASS.** NOT ASSERTED.

## Evidence wording corrections

Recorded here so the sealed O5R evidence is read correctly. The sealed files
are not edited.

**A — "every instrument now reads" is wrong for the pointer path.** The
pointer-path item carries **one readable PASS row (1440x900) and three
INSTRUMENT_UNREADABLE rows** (390x844, 844x390, 700x700). Its item-level PASS
is the verdict of the one readable row. It may not be described as a
four-viewport pass.

**B — full-frame readiness is not a visual verdict.** Item 13 proves the
review package exists and is complete. It is **not** a product visual PASS;
full-frame judgment is owned by product review.

**C — the silhouette item, read precisely.** The background ring outside the
card rect lands on neighbouring cards, so the ring statistic is contaminated.
The three PASS rows are near-degenerate — at 1440x900 the four lanes read
17 416 / 17 418 / 17 412 / 17 412 lit-beyond pixels, differences of single
pixels on a statistic of seventeen thousand. And at 390x844 the **candidate is
the closest silhouette match** (528 px beyond the projected silhouette, IoU
0.9905) while Target and control read 3 114 / 3 174 at IoU 0.9467 / 0.9457 —
yet the sealed row reads FAIL on the fixed windows. The sealed FAIL stands;
the reading above travels with it.

**D — the grayscale and saturated-edge instruments discriminate, but their
floors are not calibrated.** The corrected instruments separate the lanes
where O5's could not, and the sealed FAIL rows stand — but their fixed window
floors are **scale-blind** across statistics whose magnitudes range roughly
1.8 to 218. They may not be cited as calibrated absolute product thresholds.

**E — private-package metadata defect.** The O5R package recorded
`reviewHead = 726ee02` (the capture head). The semantic reviewHead — the
final evidence commit — is `445037e`. The fix is applied **in the next
package only**: `capturedAtHead` = the SHA the captures actually ran at,
`reviewHead` = the final evidence SHA. No standalone hygiene delivery is
created.

## What O5F is authorised to do

O5F is **not** a broad optics round. It has exactly two sequential
objectives:

**A — eliminate the quality-step material retention.** Replace the per-step
material rebuild with a finite cached material-set structure (one 5-sample
set shared by High and Medium, one 3-sample set for Low), prove identity of
both lanes against a `445037e` build to exactly zero pixels before any memory
scoring, and pass a pre-registered stress gate. No optics product correction
is allowed until this passes.

**B — identify the first source-level cause of the 390x844 portrait
residual.** Term-by-term decomposition against the source formula, per-clip
attribution (the frozen clip-2 crop is a known product deviation from the
Target's centred cover), a live-runtime proof of the Target's mobile sample
tier, reflection-direction and output-transform checks, and ROI-contamination
proofs. At most **one** code correction, and only for a directly proven
source transcription mismatch. No Target source constant may be tuned. If no
source mismatch exists, the residual is declared for a product tolerance
decision and product code is not modified.

O5F may not: flip the shipped default, merge main, tune source constants,
create another optics architecture, rewrite O5 or O5R sealed evidence, enter
Final Integration, or assert Target Visual PASS. The reflection-band result
is frozen and must remain inside its windows.
