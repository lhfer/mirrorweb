# Visual Convergence Sprint 2 — matched-content truth, and one visible fix

**Review Candidate URL:** `http://127.0.0.1:5293/?review=target`
**Review Current URL:** `http://127.0.0.1:5293/?review=current`

```bash
npm run review
```

There is no remote preview for this branch. `npm run review` builds and serves
both routes at `127.0.0.1:5293`; the two URLs above are the complete pages, one
query parameter each, nothing hand-assembled.

Baseline: `7672ec3` (Integrated Visual Sprint 1). Shipped optical default
remains `opticalBody=current`; **Target Visual PASS is NOT asserted**; main is
untouched.

## §三 — the matched-content harness: `matched-content-contract.json`

Sprint 1 compared two pages that were each showing their own clips and their
own headlines. A dark shoulder could have been the glass or the clip behind
it, and no amount of ROI statistics separates those. This round both pages are
served **one locally generated media asset per category** (the Target's mux
HLS requests and our `/clips/*.mp4` requests fulfilled from the same H.264
elementary stream) and **one injected copy set**, then read back and measured:

- six §三A categories — dark cinematic, bright low-saturation, warm skin, cool
  blue, high texture, black/white structured
- decoded frames compared **per pixel**: five of six bit-identical; the sixth
  differs on 60 of 1,080,000 pixels by at most 3/255, on the hard edge of its
  highlight disc. The gate is per-pixel *and* per-area, and both the allowance
  and the measurement are published.
- same injected copy hash on both pages, uniform across every card, zero
  structural failures
- same viewport, DPR, pointer class, card-plane CSS box, cover fit and visible
  card count at all four review viewports

**Verdict: MATCHED-CONTENT HARNESS PROVEN.**

## §五 — dynamic card geometry: `card-trajectory-thresholds.json`, `card-trajectory-truth.json`

Global phase correlation is not used and is not sufficient. Ten neighbouring
cards, seven scenarios, every animation frame, the full CSS3D matrix and the
browser's own projected rect, one reader on both pages. Thresholds were set
from the **Target's own three repeats per scenario, per scenario**, and
committed before a single candidate trajectory was read.

- **Static layout is exact.** At rest, at every viewport, every observable
  agrees to 0.000 — centres, projected sizes, gutters (17.337 px horizontal,
  16.616 px vertical at 1440x900), row stagger.
- **Spacing under motion is not the problem.** Slow drag, pointer sweep and
  mobile touch drag are inside every threshold; wrap travel matches to 3 px.
- **Two real divergences, both carried to the next round.** The fling is
  **bimodal**: three candidate runs travel 815.55/815.76/815.55 px — inside the
  Target's own 814.75–817.18 spread — and two travel 832.15/833.07, roughly two
  runs in five overshooting by ~17.4 px on identical input, where the Target
  shows one mode. And the portrait→landscape relayout makes **one ~36.7 px
  single-frame step** (36.72/36.72/36.79 across three runs) where the Target's
  largest single-frame move is 4.5 px.
- Where the candidate's own repeat spread already exceeds a threshold, the row
  is published as **UNRESOLVABLE** rather than passed or failed through.

`p0-decision.json` carries a dated **correction**: its first-draft motion
numbers came from one Target run against one candidate run, and are superseded
by the pair-matrix measurement above. The original text is left standing.

## §六 — the P0: `p0-decision.json`

Committed before any product code. Three systems were weighed against matched
evidence; **C. Typography / Footer / Brand** was chosen, because it is the only
one with a difference that can be pointed at in a 1× full frame:

**The Target paints a 144 px black-to-transparent scrim across the full width
of every page, inside its footer container, over the cards and their labels.
We painted nothing.** On matched stills the bottom 144 rows read 39.1 vs 52.3
luma at 1440x900, 37.5 vs 54.5 at 390x844, 28.8 vs 43.3 at 844x390, 33.3 vs
52.2 at 700x700 — and 19 to 43 levels apart at the very last screen row.

## §七/§八 — the change and the gate: `product-closure.json`

Two files, one system: `src/ui/PageOverlay.ts` and the chrome block of
`src/style.css`. The scrim; the Target's own footer law (the row never stacks,
only the wordmark link does, and only below its `lg` breakpoint); the
wordmark's box (`min(26vw, 148px)` with its drop shadow) carrying **our own**
ATELIER mark as inline SVG — the Target's logo is its own studio mark and is
not reproduced here; and the CTA pill's missing top sheen.

| | 1440x900 | 390x844 | 844x390 | 700x700 |
| --- | --- | --- | --- | --- |
| bottom-144 luma delta, before | +13.19 | +17.05 | +14.49 | +18.91 |
| bottom-144 luma delta, after | **+0.85** | **+0.54** | **+0.41** | **+0.76** |
| last screen row, before → after | +18.94 → **+1.04** | +16.25 → **−0.62** | +24.98 → **+0.48** | +43.22 → **+0.37** |

Footer geometry now matches the Target's to under 0.05 px at both measured
viewports. Across every frame of the six real-input recordings the same band
tracks the Target within ±1.1 luma mean. All ten §八 conditions pass, including
Source Contract **PASS 36/36**, typography contract **PASS 29/29**, route check
PASS (the shipped default still boots V3; `?review=current` still pins the
shipped optical default at exposure 1.05), TypeScript PASS, Vite build PASS,
zero console/page errors.

**Honest grade: MATERIAL AND POINTABLE AT 1×** — the bottom sixth of every
viewport changed colour, not a few grey levels.

## §九 — performance: `perf-smoke.json`

Ten bounded minutes: five desktop at full speed with High/Medium/Low actually
exercised (adaptive off for the cycle, back on afterwards), five on a phone
context under a **4× CPU throttle**. Cache constant, no black cards, media
advancing, zero errors, GC floor flat. A throttled headless 120 Hz run is not a
real-device PASS and is not reported as one.

## §十 — delivery

Public tree: this README + MANIFEST + six JSONs (8 files, ≤10, no images).
Private package: `qa-v5/private/vc2-visual-convergence.zip` — 16.5 MiB, 6
side-by-side videos, 24 full-page stills, 12 contact sheets, per-file SHA-256,
`capturedAtHead`/`reviewHead`, missing 0 / unlisted 0. Target pixels live only
there.

## Final state (§十二)

**READY FOR MATCHED-CONTENT VISUAL PRODUCT REVIEW.**

Not asserted: Target Visual PASS. Not touched: the shipped optical default,
main, motion code, the layout contract, the glass.
