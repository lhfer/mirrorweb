# Phase 1B Frozen Visual calibration

Status: **CONDITIONAL; human review required; Phase 2 and final target match are BLOCKED.**

## Evidence layers

The clean foundation rerun is historical, immutable evidence for commit
`3f57807cd6927935bd854a8a5ae7dbb1e551f4dd`:

- runtime scope dirty: `false`
- runtime source-set SHA-256: `e50dd5f0d82689125056865d2e043e6072ddceff775d8c326eab765c67e503b3`
- capture-manifest SHA-256: `4ad727a12ffe63f16541ef7d3ebf85bfe14f46fbdb5700f0ca282fe58285642e`
- screenshot-set SHA-256: `8e45f6053260124ad158bda7e81c93266777bb9b85aa5fd6a0d4da0580367722`
- evidence-set SHA-256: `108cb070d54dcc27882d96a297d2b351158f10ce195f98eb2bd558bc50be00f3`

`qa-v4/results/optics-lab-foundation.json` contains that clean rerun. Phase
1B has a separate runtime identity and result so the accepted foundation is
not silently rewritten by later calibration.

The Frozen target remains hash-locked by video SHA-256
`b6e79250c75e0357e489de87b63ffd4a5097a573eb7baced35e5de8b050c2435`.
Its v1 Shoulder/Rim/Sidewall masks are configured search windows. They are not
measured target boundaries and are never promoted to target truth.

## Calibration choices

The `71 px / 10.7903%` foundation number combined Shoulder and Rim. Phase 1B
replaces that ambiguous metric with mutually exclusive screen-space zones:

- Center Face
- Optical Shoulder
- Strong Lens Rim
- Sidewall

The Lab also reports highlight width and content-bending width, producing the
six requested metrics. The user-measured target Strong Rim range of
`4.6%–4.9%` is retained as a provisional `CONDITIONAL` prior; the wider
`4.5%–5.5%` band is the first-round local calibration gate.

The reviewed V4 parameters are:

- `shoulderOuterPx = 64`
- `rolloverInsetPx = 16`
- `rolloverDepthPx = 27`
- `lensRimWidthPx = 30`
- `blurLod = 2.35`
- `maxRefractionUv = 0.125`
- Shell zone coefficients: Center `0.012`, Shoulder `0.48`, Strong Rim `1.0`, Sidewall `0.30`
- Shell opacity: Fresnel `0.20`, zone `0.13`, maximum `0.42`

The Scene Color Target-only body path is unchanged. Center refraction remains
small but still samples the Scene Target. Dispersion remains zero outside the
Strong Lens Rim.

## Clean measured result

The formal run was captured from clean evidence commit
`7f9295b45d21349930037643ecc5ce71139c5d79`, with runtime source-set
`1d6bfdb59f1a125ec85c33971d2f5e13c175511568cf1469fe58eba6ce2aefbb`.
The evidence-only amend does not alter any runtime file in that set.

- Dist tree: `2f7cc92fbd42ba62ae7018ec94627a9837a9212fda018c1491815b52b590536f`
- Served-resource manifest: `ecebecb81bde6ee98da65e28a4ec5ab15e88c106255b7765af7d65b8a00c2856` (7 matched resources)
- Screenshot set: `759c3190bc740d9b89d7c8bd70dee2a66685f3b4f293a6eef51e957370ce75f5`
- Private session video: `2f3fec6b832920b01cae8f4f79396c07f8358ea13f23a7494408260776a76c7b`
- Browser/GPU: Chrome `151.0.7922.138`, Apple `metal-3`, non-fallback WebGPU, `1440×900`, DPR `1`

| Local metric | Result |
| --- | ---: |
| Center Face area | `0.613588` |
| Optical Shoulder width / short side | `0.073661` |
| Strong Lens Rim width / short side | `0.049107` |
| Sidewall screen width / short side | `0.006696` (left/right, 269 rays each) |
| Highlight width / short side | `0.020579` |
| Content-bending width / short side | `0.198036` |
| Center/Rim sharpness ratio | `1.391783` |
| Dispersion width / short side | `0.030026` |
| Dispersion outer-energy share | `0.9999985` |
| Highlight path travel | `0.740728`; max/median jump `1.672343` |
| Tilted line-spacing ratio | `1.0625` left and right |

The Strong Rim is inside the first-round `4.5%–5.5%` local gate. It is
`0.0107` percentage points above the provisional `4.9%` upper estimate, so the
relative result remains `CONDITIONAL` rather than being rounded into a pass.
The tilted line ratio is measured local expansion (`> 1`), not evidence of
target-matched compression.

## Reflection Shell A/B

The Lab-only switch has three modes:

- `additive`: retained only as the original A control
- `energy-controlled`: `NormalBlending` with premultiplied alpha; calibrated default
- `off`: body-only baseline

Each A/B variant is captured on black, white, and color backgrounds plus
left/center/right pointer positions. Measurement compares clipping, Rim luma,
bright-background discernibility, dark halo width, reflection energy,
highlight width/path, and neutral white-outline bias. The local preference does
not establish target lighting equivalence.

| A/B metric | Additive | Energy-controlled |
| --- | ---: | ---: |
| Color reflection energy vs Shell-off | `0.000247734` | `0.000117929` |
| White Rim luma delta vs Shell-off | `0.000401519` | `0.000164553` |
| White-outline pixel ratio | `0.004443` | `0.002330` |
| Bright-background discernibility | `0.022994` | `0.046733` |
| Dark halo width | `0.031010` | `0.029947` |
| Highlight width | `0.038002` | `0.020946` |
| Highlight path travel | `0.741016` | `0.740393` |
| Highlight clipped pixels | `0` | `0` |

Energy-controlled reduces color reflection energy by about `52%` and white Rim
luma bias by about `59%`, while retaining the same continuous pointer-light
path. It is therefore the Phase 1B default; Additive remains an explicit Lab A
control only.

## Target-relative method

Target and local cards are rectified to a canonical card plane before
comparison. Measurements use normalized edge profiles, four sides, four
corners, feature displacement, highlight centroids, chroma-energy CDFs,
sharpness profiles, and sidewall line compression. Whole-card SSIM is forbidden
because the media differ.

Seven roles are reported: bright, dark, high texture, low texture, front, left
tilt, and right tilt. The front role intentionally reuses the best non-pointer
Frozen frame because the source set contains only six non-pointer visual roles;
clipped pointer frames are not misrepresented as independent target truth.

Without `annotations.private.json`, target width, highlight, sharpness,
dispersion, corner, and sidewall comparisons that require human-confirmed
boundaries remain `BLOCKED`. The provisional Strong Rim error and reviewable
overlay hashes may be `CONDITIONAL`. Missing values are never filled with zero.

## Reproduction

Run the production preview on a port separate from the user's development tab:

```sh
npm run build
npm run v4:source
npm run v4:check
npm run v4:preview:phase1b
```

Then, from a second terminal:

```sh
npm run v4:capture:phase1b -- \
  --output=qa-v4/results/frozen-visual-calibration.private \
  --manifest=qa-v4/results/frozen-visual-calibration.capture.local.json \
  --headed

python3 scripts/v4/measure-frozen-calibration.py \
  --local-capture qa-v4/results/frozen-visual-calibration.capture.local.json \
  --output qa-v4/results/frozen-visual-calibration.json

npm run v4:review:phase1b -- \
  --input qa-v4/results/frozen-visual-calibration.capture.local.json \
  --output-dir qa-v4/review/phase-1b
```

Formal capture fails closed unless the repository is clean before and after the
session, the served resources match the `dist/` build, a non-fallback WebGPU
adapter is active, and no page/request errors occur.

All PNG/JPG/MP4/WebM pixels, private annotations, and local manifests remain
ignored. The committed result contains only hashes, aggregate metrics, evidence
states, and caveats.

## Human review surface

The private review server (`npm run v4:review:serve`, `http://127.0.0.1:5282/`)
opens in **Reviewer Mode**, a guided five-step target annotation written for a
careful reviewer who is not a graphics engineer. The original dense surface is
preserved as the **Advanced Inspector** at `?mode=advanced`.

| Step | What the reviewer does | What stays hidden |
| --- | --- | --- |
| 0 · Tutorial | Learns Center Face / Optical Shoulder / Strong Lens Rim / Sidewall from a synthetic card, a real Frozen crop, one correct and one wrong annotation, and six things that are never a boundary. Writes nothing. | Local capture |
| 1 · Target frame | Accepts, rejects (with a reason) or swaps in one of the neighbouring candidate frames decoded by `npm run v4:review:candidates`. | Local capture |
| 2 · Card quad | Drags four corners on the centred, magnified card, with a loupe and a live rectified card plane. The card fills at least 65% of the review stage. | Local capture |
| 3 · Optical zones | Drags three boundaries directly on the rectified target card. Percentages are derived from the drag; nothing is typed. | Local capture |
| 4 · Lock | Reviews frame, quad, four zone widths, four edge crops and four corner crops, then locks. Locking computes a SHA-256 target-annotation hash. | Local capture |
| 5 · Compare | Only now sees the local capture, at the same card-plane size, with edge/highlight/dispersion/sharpness overlays and per-edge/per-corner regions. | — |

Target Frame, Card Quad, Optical Zones and Local Match are four independent
states. A local mismatch never invalidates a correct target annotation.

Optical boundaries are stored as three positive band *widths*, so the cumulative
order `0 < Sidewall < Strong Rim < Shoulder < card half size` holds by
construction and an illegal ordering cannot be produced by the UI or accepted by
the server.

Reviewer Mode autosaves to `qa-v4/review/phase-1b/reviewer-state.private.json`
(private, ignored). It never reads or writes
`qa-v4/reference/frozen-visual/annotations.private.json`; promoting a locked
target annotation into that contract remains a separate, explicit step.

`npm run v4:review:screens` replays the whole flow in a browser and records the
acceptance evidence (stage coverage per role, local-hidden request audit,
boundary legality, autosave/reload, annotation-file hash) next to the
screenshots under `qa-v4/review/phase-1b/reviewer-screens/`.

## Gate

`Final Target Match = BLOCKED`. No Phase 2, Typography, Motion, Grid, or
main-page integration work is authorized until the user reviews the private
contact sheet/session video/ROI overlays and explicitly accepts the result.
The current severity ledger is:

| Severity | State | Evidence |
| --- | --- | --- |
| P0 | No open Phase 1B architecture/privacy/identity defect | Scene-only body, clean preview/resource attestation, protected V3, and private-pixel isolation pass. |
| P1 | OPEN / HUMAN REVIEW | Shoulder, highlight, sharpness, dispersion, corner, and sidewall target-relative metrics are BLOCKED until Frozen annotations are approved. Strong Rim is CONDITIONAL. |
| P1 | OPEN / TARGET UNKNOWN | Local tilted spacing ratio is `1.0625` (expansion); target comparison is unavailable, so it is not called matched compression. |
| P2 | OUTSIDE THIS GATE | rAF cadence is not GPU timestamp-query performance; final performance equivalence remains BLOCKED. |
