# V5 Stage F0 / F1 — Foundation Fidelity Reset

Branch `rebuild/liquid-glass-v5-foundation`, based on `b071915` (stage-h touch fix).
Page under review: `/?optics=v4`.

## What was re-verified, not assumed

The brief listed twelve suspected problems as *initial* evidence. Every layout
number in that list came from `artifacts/reference/measurements/landmarks.json`,
produced by a card-blob detector that erodes the card and mis-centres clipped
tiles. Re-measuring the Target frame with a gutter-structure detector
(`scripts/v5/measure-layout.py`) moved several of them materially:

| Claim in the brief | Re-measured on `A/06-rest-5s.png` | Verdict |
| --- | --- | --- |
| Target mid card 521×364, aspect 1.431 | **526×397.7, aspect 1.323** | brief number was eroded; aspect was ~8% off |
| Target horizontal gutter 24–26 px | **14 / 22 / 14 px** (outer / centre / outer) | narrower, and it varies with curvature |
| Target vertical gutter ≈23 px | **18 px** (band y441–458) | |
| `radius=7200` yaw too large | **sign is wrong**: Target is convex, r ≈ −4059 | the real defect |
| TILE 518×438, aspect 1.183 | confirmed | |
| `cellH − TILE.height = −10` (rows overlap) | confirmed | |
| Video mapped 0..1, no cover | confirmed, 23.8% measured squeeze | |

The decisive new fact is the **curvature sign**. In the Target's bottom row the
outer cards are *smaller* than the centre card (388.3 px tall at |u| = one cell
vs 401.1 px at u = 0), and the outer cards' bottom edges tilt so the outer end
sits higher. Both mean outer columns are **farther** from the camera. The old
`radius: 7200` is concave and makes outer cards larger — the opposite. Fitting
from a concave seed converges to a flat grid with 6.9 px RMS; fitting from a
convex seed lands at 0.95 px RMS.

## The fit

`scripts/v5/fit-layout.py` mirrors `placeTile()` plus the `applyPose()` camera
exactly and solves six parameters by least squares against 20 measured Target
observables (card silhouette edges, gutters and edge slopes — never derived
quantities like "yaw", which is not directly observable).

`fov` and camera `z` are **held fixed**, not fitted: focal length, camera
distance and world scale are mutually compensating, so fitting all three gives a
degenerate valley. The Target's own HTML overlay declares `perspective: 1000px`,
and the engine independently pins focal length at `CAMERA.perspectivePx`, so one
world unit is one CSS pixel on the z=0 plane. That anchor is what makes the rest
of the fit identifiable.

Result (RMS 0.95 px, worst single residual 2.7 px over 20 observations):

```
GRID.cellW   557.72  ->  561.14
GRID.cellH   428     ->  420.43
GRID.restY0  -211.05 ->  -209.97
GRID.radius  7200    ->  -4058.94     (sign flip: concave -> convex)
TILE.width   518     ->  539.8
TILE.height  438     ->  399.6        (aspect 1.183 -> 1.351)
```

`TILE` is the slab, and a rendered glass card's silhouette is ~2 px wider and
~1.3 px taller than its slab because of the rim. The fitted *silhouette* was
540.8 × 401.6; `TILE` carries that minus the measured rim inflation, which is
why the beauty render measures 542 × 400.3 against the Target's 542 × 401.1.

## `?foundation=layout`

New dev/QA mode. Flat opaque grey slabs whose silhouette is exactly
`TILE.width × TILE.height`; no media, no glass, no reflection shell, no
dispersion, no typography, no footer; motion frozen; a 2D overlay draws each
card's projected quad, its centre cross and its `i,j` index.
`&annotate=0` drops the overlay so a pixel detector reads bare edges.

This is the surface the F0 gate measures, so no video content, rim glow or CSS3D
type can move a measured edge.

## Measuring instrument

One detector, `scripts/v5/measure-layout.py`, runs on both sides. It measures the
**negative space** — the void between cards — because gutter boundaries are
immune to whatever video is playing inside a card.

Two void presets, because the two sides clear to different colours: the Target
clears to a navy in the range (0,3,20)…(0,6,32), this build clears to a black the
tone-mapped pipeline lands on exactly (0,0,0). The algorithm is identical; only
the colour it keys on differs, and the resolved thresholds are echoed into every
JSON output.

## Stage F1 — MediaFit

`src/content/MediaFit.ts`. Every clip is fitted onto the card through the texture
matrix (`repeat`/`offset`), which the media plane's `MeshBasicMaterial` applies.
`cover` ships; `contain` and `stretch` exist only as debug comparisons and
`stretch` is the pre-V5 behaviour, kept so a capture can show what was fixed.

All three sources are 16:9-ish (960×540, 960×556, 960×540) against a 1.351 card,
so cover keeps full height and crops left/right. Per-clip `focusX` / `focusY` /
`zoom` live on `CLIPS`. Product review set them on 2026-08-20:

| Clip | focusX | focusY | zoom | visible source | source px per card px |
| --- | --- | --- | --- | --- | --- |
| NL-01 牛来开场 | 0.50 | 0.50 | 1.00 | 76.0% × 100% | 1.351 |
| NL-02 Cursor 牛来 | 0.50 | 0.50 | 1.00 | 78.2% × 100% | 1.391 |
| NL-03 鹈鹕测 AI | 0.50 | 0.46 | 1.06 | 71.7% × 94.3% | 1.275 |

NL-03's `zoom: 1.06` was checked for the blur the product brief warned about and
**kept**. It cannot introduce magnification blur: the texture is still minified
(1.275 source pixels per card pixel, down from 1.351 — both above 1.0), so the
sampler never has to invent detail, and less aggressive minification through a
`LinearFilter`, no-mipmap texture is if anything cleaner. Measured against an
ideal LANCZOS resample of the exact decoded frame, on the same face-on card
(cell −1,0 centred), high-frequency fidelity is 1.021 at zoom 1.00 and 0.959 at
zoom 1.06 — a 6% relative difference, far below anything visible. Aspect stays
exact at 4.2e-14%.

`?mediacal=1` swaps the clips for a 960×540 calibration canvas (circles, squares,
edge markers) so the same fit maths can be checked against a known shape.

V4 is fully covered: the media plane is fitted, and V4 glass samples the rendered
scene-colour target, so the crop propagates into the refraction. **V3 is not**:
`LiquidGlassMaterial` samples the clip texture through a TSL `texture()` node,
which does not read the texture matrix, so media *inside* V3 glass stays
uncropped. V3 is not the page under review and its optics are out of scope this
session — recorded, not fixed.

## Known gaps recorded, not fixed (out of F0/F1 scope)

1. **Responsive scaling law is wrong — highest priority.** The Target scales the
   whole composition with viewport **width**: mid card 526 px at 1440 wide,
   701 px at 1920 wide (ratio 1.3327 vs the width ratio 1.3333), ~407 px at 1100
   wide. This build holds world size fixed (1 world unit = 1 CSS px at every
   size) and only zooms out below a threshold via `viewZoom`, so at 1100×720 our
   card is 540 px where the Target's is ~407. The width law does **not** extend
   to mobile — the Target's 390×844 frame shows a ~278 px hero card, not
   390/1440 × 526 = 142 px — so this needs its own multi-viewport fit and its own
   gate, not a one-line change.
2. **Background void colour.** Target gutters are navy `#000417`; ours render as
   pure `(0,0,0)` (`CLEAR_COLOR` is `0x000208` and the tone-mapped pipeline
   crushes it).
3. **Glass rim is far too wide on yawed cards.** On the beauty render the
   bottom-row gutter measures 11 px against the Target's 19 px, entirely because
   our outer cards' dark sidewall eats ~8 px of gutter. The underlying geometry
   is correct — the same gutter measures 21 px on the grey slabs.
4. **Cyan/magenta rim fringing** at high saturation (brief item 12).
5. **Typography** `title: 9.2cqw` vs Target 12cqw; `TILE.radius` (corner) is 58
   against a Target corner of roughly 0.114 × width ≈ 61.5.
6. **Motion**: `dragGain 0.58` vs a Target follow ratio of 0.77–0.82;
   `damping 11` / `stopThreshold 70` stop well before the Target's 1.0–1.5 s.
7. **`npm run v4:source` / `v4:check` fail on this branch, and three of those
   failures are mine.** Baseline `b071915` already failed four checks
   (`V4_BRANCH_MATCHES_CONFIG`, `V3_RUNTIME_PATHS_UNCHANGED`,
   `V3_DOM_FINGERPRINT`, `V4_CAPTURED_RUNTIME_IDENTITY`). This branch adds
   `MAIN_PAGE_V4_FLAG_ADDITIVE` (main.ts now also routes on
   `foundation=layout`), `V3_GRID_FINGERPRINT` (`InfiniteGlassGrid.ts` gained
   MediaFit on the media plane) and `V3_VIDEO_UPLOAD_FINGERPRINT` (`CLIPS`
   gained focus fields). The V4 charter's premise is "V3 stays untouched"; the
   V5 brief overrides it by requiring changes to the shared layout config and
   to media fitting. The lock has deliberately **not** been re-baselined —
   re-cutting a governance contract to make a candidate pass is the user's
   decision, not the candidate's.
8. `setRenderLayers({glass:false})` used to be a no-op on the final frame,
   because the two-pass pipeline re-asserts glass-on / media-off every frame.
   Fixed in `GridAppV4.drawFrame()` so media-only QA captures are real. Any
   earlier "media-only" evidence produced through `?optics=v4` was actually
   glass-over-media.

## Smoke tests beyond the gate viewport

Not fidelity claims — the Target has its own mobile treatment and its own gate.
These only show that flipping the curvature sign on a shared config did not
break anything outside 1440x900.

| Surface | Result |
| --- | --- |
| `/` (V3 default route) | boots, `ready:true`, 3 videos, 81 slots, **zero console errors**; `qa-v5/f0/v3-default-route-smoke.png` |
| 390x844 portrait | renders, no card pair overlaps (min quad separation 7.19 px) |
| 844x390 landscape | renders, no overlaps (15.59 px) |
| 1100x720 | renders, no overlaps (15.09 px) |
| `npm run build` | passes |

`viewZoom` is active on all three small viewports (2.61x at 390 wide), which is
the pre-existing responsive path, not a new one.

## Model vs engine

`scripts/v5/model-vs-engine.py` compares the engine's own `getCardQuads()`
against the analytic model, corner by corner, at every captured offset and
viewport: **0.0 px** at 1440x900 (six offsets), 1100x720, 390x844 and 844x390.

That is what makes a rest-frame fit generalise. The Target comparison is done at
one pose; it transfers to every other pose because the engine is provably
evaluating the same closed-form geometry the fitter scored, with no
offset-dependent special case anywhere in the path.

## Reproducing

```
npx vite --port 5280 --strictPort
node scripts/v5/capture-layout.mjs --route='/?optics=v4&foundation=layout&annotate=0' --out=qa-v5/f0/foundation
node scripts/v5/capture-layout.mjs --route='/?optics=v4' --out=qa-v5/f0/beauty --states=01-rest
node scripts/v5/capture-mediafit.mjs --out=qa-v5/f1
python3 scripts/v5/f0-gate.py --target=artifacts/reference/A-1440x900-dpr1/06-rest-5s.png --local-dir=qa-v5/f0/foundation --out=qa-v5/f0
python3 scripts/v5/f0-curves.py --dir=qa-v5/f0/foundation --partial=qa-v5/f0/partial --out=qa-v5/f0
python3 scripts/v5/model-vs-engine.py --dir=qa-v5/f0/foundation --dir=qa-v5/f0/partial --out=qa-v5/f0
python3 scripts/v5/build-evidence.py .
```
