# Integrated Visual Sprint 1 — Product-Driven Review

The round that switched from band metrics to complete pages. Reviewed
baseline: O5F interim snapshot at `e7c0c2c`. Shipped default remains
`opticalBody=current`; Target Visual PASS **NOT ASSERTED**; main untouched.

## The review routes (§三, `v5-integrated-review-route`)

`?review=target` boots the complete page on the leading candidate —
sourceExact composition, `target-source-unclamped` body, the Target
device-tier sample law, labels, footer, motion, coverage culling,
source-exact typography, real media, adaptive quality — one query param,
nothing hand-assembled. `?review=current` is the same page on the shipped
optical default. Verified live on fine-pointer and coarse-pointer contexts
(pinned optics, 5/3 samples by the device predicate, real drags move the
grid, no debug HUD). The §二 external reference map is
`docs/v5/EXTERNAL_GLASS_REFERENCE_MAP.md` (one page: no published Target
breakdown exists; two external repos mapped as methodology, not
architecture).

## Before evidence (§四)

12 full-page stills (Target / review-current / review-target at 1440x900,
700x700, 390x844, 844x390) and 12 recordings (six scenarios × both sides,
real CDP pointer/touch only, identical input sequences). Media runs each
side's OWN clips — the product ships its own media and label content by
design, so every pair compares systems, not clip content. Pixels live in
the private package; nothing in this tree carries a Target pixel.

## P0 ranking (§五): `p0-ranking.json`

1. Glass output-transform (dark shoulder / plastic feel) — FIXED this round
2. Typography loaded-face proof — PROVEN, no fix needed
3. Motion trajectories/wrap — DIAGNOSED, no visible P0 found
4. Smoothness/pop-in — bounded smoke

## Phase A — Glass (§七, `v5-integrated-glass-closure`)

`glass-selected-problem.json` + `glass-closure.json`. The code-to-code
audit of the archived bundle found the card program transcription-complete
(every constant matches; the tint/rim foldings are proven inert; the
served HDR is byte-identical). The real divergence sat OUTSIDE the card
program, where every sealed instrument was structurally blind: our
renderer ran ACESFilmic at **exposure 1.05** (day-one import; the pre-V4
reference spec left exposure "missing as a numeric value") while the
Target runs the r3f default ACESFilmic at the three.js default **1.0**.

Fix: the candidate lane renders at 1.0; control and sealed clamped lanes
keep 1.05 — verified 0 differing pixels on `review=current` at all four
viewports. The candidate moves page-wide with the exposure-through-ACES
signature (mid-tone darkening peaking −3.4 bytes at luma 96–160), closing
roughly a third of the sealed dark-band residual in its proven direction.
**Honest visibility grade: SUBTLE-BUT-PAGE-WIDE** — the page settles in a
direct A/B; it is not a transformative jump, and the remaining gap to the
Target's deep-dark contrast stays declared.

## Phase B — Typography (§八, `v5-integrated-typography-closure`)

`typography-closure.json`. Live dual-side re-read with ONE reader plus a
new loaded-face proof (document.fonts.check + two-fallback shaping test +
glyph bounds). The loaded faces shape **bit-equal glyph bounds**; every
text-carrying style matches at all four viewports; text-plane depth
matches to the third decimal; nothing falls back to system-ui. **No code
change was needed** — the deliverable is the proof that was missing from
the O5F package.

## Motion (§九): `motion-visual-diagnosis.json`

Diagnosis only, code untouched. All seven questions answered from
synchronized real-input recordings with displacement-trace overlays:
trajectories align (flick glide 1.881 vs 1.840 s; wrap displacement
exactly equal at −1144 px; zero >120 px discontinuities — no wrap pop on
either side). **No visible motion P0 was found for the next round.**

## Performance (§十): `perf-smoke.json`

One bounded 10-minute candidate smoke (6 min desktop drag/flick/wrap with
High/Medium/Low cycles, 4 min mobile touch/wrap): heap, cache truth, FPS,
frame-time p95, pop-in stills. Raw series in the private package.

## Delivery (§十一)

Public tree: this README + MANIFEST + six JSONs (≤10 files, no images).
Private package: `qa-v5/private/ivr1-integrated-review.zip` — ≤60 MB,
8 videos (4 synchronized pairs), ≤24 full-page stills + per-viewport
contact sheets, motion overlays, raw data.

## Final product state (§十二)

**READY FOR INTEGRATED VISUAL PRODUCT REVIEW** — see MANIFEST.json for
the state record and the honest visibility grades. Not asserted: Target
Visual PASS. Not touched: shipped default, main, motion code, O6.
