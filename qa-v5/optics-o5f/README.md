# O5F — Material Cache and Portrait Source Reconciliation

**Status: ROUND PAUSED BY USER — INTERIM SNAPSHOT.** No §十七 final state is
asserted. Everything below is complete and sealed except the §十四 stress
re-run (sessions interrupted mid-capture) and the aggregate regression /
recording stages, which were skipped at the pause.

Reviewed baseline: O5R at `445037e`. Shipped default remains
`opticalBody=current`. Target Visual PASS: **NOT ASSERTED**.

## Phase A — the material cache (COMPLETE, PASS)

The O5R finding: every quality step rebuilt and disposed the body materials,
retaining ~68 KB per step (39.36 MB in the six-minute quality-cycle arm;
session GC-trough rises +18.59/+20.03/+22.15 MB against a control at −1.04).

The fix (`v5-o5f-material-cache-code`, 30b91f6): a finite keyed cache —
one 5-sample set shared by High+Medium, one 3-sample set for Low, both built
at initialisation; a quality change is a set switch plus a material rebind,
never a create or dispose. A retired defect fell out of the same edit: the
old quality path swapped the source-contract 16x12 tessellated plane for the
control lane's convex geometry after the first step (977,083 differing
pixels per cycle at the baseline; exact 0 after).

* `material-cache-contract.json` — the §四–§七 pre-registration, sealed
  before any candidate measurement.
* `material-cache-identity.json` — §六: current lane 35/35 exact zero vs a
  445037e build, candidate 35/35 exact zero, program hashes match at both
  tiers. **PASS.**
* `material-cache-stress.json` — §七: 10/10 sealed checks. 1,200 quality
  steps: 0 pixel mismatches, creation constant at 6, renderer programs
  constant at 6. Six 15-minute sessions: candidate final-third slopes
  0.475/−0.0495/−0.0122 MB/min (threshold 1.4368 = the control window);
  GC-trough rises **−1.46/−0.50/−0.87 MB** against threshold 5.68 — where
  O5R rose +18.59/+20.03/+22.15. **PASS.**

## Phase B — the 390x844 portrait residual (forensics COMPLETE)

Sealed residuals under examination: dark-side luma 58.57 vs Target 51.28
(window 6.0), white-reflection ratio 3.8676 vs 4.9035 (window 0.15).

* `target-mobile-tier.json` — §十B, **the proven source mismatch**. The
  Target's tier is a device predicate (bundle byte 1968911: pointer-coarse
  OR cores≤6 OR deviceMemory≤4, nullish defaults 8, decided once at load;
  no viewport term). Live probe: at 390x844 and 844x390 the Target compiles
  **3 refract calls**; our candidate ran 5. Counting convention validated
  on the desktop control (predicted 5, observed 5); live bundle sha256
  equals the archived bundle. READABLE.
* `portrait-term-decomposition.json` — §九: nine QA-only term programs vs
  a CPU replay of the source formula, validated at 1440x900 before P0 was
  read. **Every readable term MATCHES at both viewports**
  (analytic-normal 0.008, reflection-vector 0.005, equirect-uv 0.002,
  raw-env-sample 0.005, fresnel 0.003, env-mix 0.002, white-rim 0.0006,
  final-colour 0.014 — tolerances 0.02–0.06). `firstDivergingTerm: null` —
  the transcription is faithful; the residual is carried by a chain INPUT.
  body-refracted failed its own validation and is INSTRUMENT_UNREADABLE
  (never converted to a verdict); its question is covered by the sealed
  refraction-compression instrument, the sealed media-fit suites and the
  frozen source contract.
* `clip-index-attribution.json` — §十A: under occupant rotation
  (scroll +cellW/+2·cellW) the residual is **anchored to the screen rect,
  not the clip index** — rect pixels are exactly identical across all
  three occupants. The frozen clip-2 crop is ELIMINATED as the carrier.
  The per-rect numbers reconcile the sealed gate exactly:
  mean(81.56, 35.58) = 58.57 candidate, mean(80.82, 21.75) = 51.28 Target.
* `reflection-direction.json` — §十C: every direction term matches;
  envRotation/envRotationX match the bundle source-to-source.
* `output-transform.json` — §十D: the compiled-program marker comparison
  is vacuous (both runtimes apply the transform outside the card program);
  the operative evidence is the final-colour term match plus the sealed O5
  compiled audit.
* `roi-isolation.json` — §十E: the measurement bands intersect product DOM
  typography, and masking off-silhouette pixels moves the worst-rect
  dark-luma residual **13.83 → 19.15**: the differing background ring (O5R
  correction C, here quantified) was DILUTING the sealed number — the card
  body carries more residual than the sealed row states.

## The one §十一 correction (`v5-o5f-portrait-source-code`, c545649)

`targetDeviceTierV5()` — the bundle predicate transcribed exactly — now
drives the body sample count of the **unclamped candidate lane only**,
decided once at load, identical at every quality level. The sealed clamped
lane keeps the frozen quality map; the control lane is untouched; both
cache sets are still built at initialisation. Live verification: desktop
5/5/5, mobile-emulated 3/3/3, zero cache switches, creation 6, cacheSize 2;
the desktop Beauty program remains byte-identical to the §六C sealed hashes.

* `portrait-source-code.json` — the §十四 verification record.
  - `controlIdentityAfterFix: PASS` — control 35/35 exact zero vs the
    445037e baseline; sealed lanes (control + o5-clamped, 224 comparisons)
    exact zero vs the O5R captures; candidate exact zero at every
    fine-pointer viewport; candidate DIFFERENT at 390x844/844x390
    (769–3,575 px per state) — the correction's pre-registered signature.
  - `stressRerun: INCOMPLETE_PAUSED` — the §十四 quality-cycle re-run
    passed (1,200 steps, 0 mismatches, cross-tier diagnostic flipped
    exactly as pre-registered); the six sessions were interrupted by the
    user pause. `scripts/v5/o5f-stress-postfix.py` (sealed in the
    correction commit) can resume with unchanged expectations.
  - `postFixP0`: **the correction does NOT close the sealed windows.** On
    the sealed asset the 3-vs-5 sample difference lands entirely outside
    the scored bands (bw-split is centred-crop and dispersion insensitive
    there; the environment term computes once, outside the spectral loop),
    so the band metrics are bit-identical pre/post. The tier hypothesis as
    the residual's CAUSE is falsified by measurement; the correction
    stands on its own proof as a real transcription fix.

## Closure

* `portrait-closure.json` — the pre-registered §十/§十一 decision tree
  (amendments recorded in the file). Interim state:
  **CORRECTION APPLIED AND DISCLOSED; RESIDUAL NOT CLOSED; §十四 STRESS
  RE-RUN INCOMPLETE.** If resumed and the stress re-run passes, the tree
  resolves to READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT RESIDUAL.

## Regressions at the forensics head

* `sealed-lane-identity.json` — 312/312 comparisons exact zero across
  control / o5-clamped / o5r-unclamped: the cache and the six QA views
  moved no pixel of the scored suite.
* `control-identity.json` — the sealed aggregator's schema view, 35 rows
  exact zero.
* `o5r-gate-regression.json` — the sealed O5R corrected gate re-run on
  this round's own frames: identical PASS 7 / FAIL 7. Not rewritten.
* `original-o5-gate-regression.json` — the sealed O5 absolute gate re-run:
  identical 8/14.
* NOT RUN at the pause: the full frozen-suite aggregate
  (`regressions.json` — run-o5f.sh rendergate/labelgate/frozen/o2suites),
  review recordings, and the §十四 sessions.

## Review-summary wording rules (§十二, carried)

Silhouette rows are N/A-UNREADABLE in this round's summary (ring
contamination; three near-degenerate sealed PASS rows). The pointer path is
one readable PASS row plus three INSTRUMENT_UNREADABLE — never a
four-viewport PASS. Full-frame readiness proves the package exists, not a
visual PASS. The sealed O5R gate counts stay sealed. No threshold in this
round was created after candidate capture.
