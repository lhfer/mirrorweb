# V0 — source-exact CSS3D label coverage culling

The Target keeps ~16 labels alive per frame at 1440x900. Before this round our
page kept 81 — its only test was a JS backface dot-product. V0 read the
Target's culling out of its bundle, byte by byte, and implemented it: a
dedicated dolly-free coverage camera, the four projected card corners, the NDC
z skip, the 1 px² minimum area, and the exact 64 px margin. Nothing was tuned
against a visible count.

## Verdicts

| gate | result |
| --- | --- |
| Target rule source verification | **PASS** — 20131 frames replayed against the Target's own DOM, 363 slot mismatches (363 wrap-seam-sensitive, 0 beyond the 0.05 px float boundary) |
| Candidate rule consistency | **PASS** — 20372 frames, 0 mismatches (0 beyond boundary) |
| Page-vs-replay bit exactness | **PASS** — 40 settled snapshots, worst AABB delta 9.095e-13 px |
| Visible slot identity vs Target | **PASS** — 40/40 settled states identical, by ILG code |
| Lost / intruding labels | **PASS** — lost 0+0, intruding 0+0 |
| Stale-but-visible rects | **PASS** — 2456 drawn labels over 120 settled runs, worst rect-vs-replayed-AABB delta 0.0135 px (tolerance 0.5 px), 0 stale; 6 wrap-seam relocations positionally demonstrated (perturbed replay matches the DOM rect) |
| Edge pop-in | **PASS** — candidate max strict-overlap at entry 171.72 px against the Target's own 171 px |
| DOM write pressure | **PASS** — worst-case p95 transform writes/frame 120 before → 36 candidate (Target 36) |
| Performance, measured | **PASS** — see below |
| Depth carry-forward | NOT APPLICABLE — no overlapping card planes on screen: 30 front-facing pairs intersect only inside the 64 px margin band (worst 85.45 px², never inside the strict viewport), and every larger projected intersection involves a back-facing plane that paints no ink (CSS backface-visibility) — measured over 40 settled states: 83 projected intersections, 30 front-facing (worst 85.45 px², margin band only), 0 on screen |
| Console / page errors | **PASS** — target 0, before 0, candidate 0, across all 65 capture runs per lane |
| Typography regression | **PASS** — 4/4 |
| Card / label under motion | **PASS** — 34 assertions, corner delta ≤ 1 px |
| Source contract | **PASS** — 36/36 viewports |
| Motion freeze smoke | **PASS** — engine vs contract 15 rows / 0 failed, release history 11/11 exact, wrap teleports 0, wheel responses 0 |

At 1440x900 rest the Target shows **16** labels and the candidate shows **16** — the same codes, not merely the same count. The Before build showed 81.

## What was read, and from where

`target-culling-source.json` carries 30 byte-anchored sites,
every one re-found at its recorded offset, and the live bundle downloaded this
round is byte-identical to the captured one
(SHA `4983307288d9e6c5…`). The deciding line poses two cameras
in one statement: `Py.position.set(d,h,f)` — the coverage camera, pointer
orbit, NO dolly — against `t.position.set(d,h,f+p)` — the render camera with
the dolly. Coverage projects the four card corners through `Py`; a corner with
NDC z outside [-1, 1] is skipped; the surviving corners' pixel AABB must
exceed 1 px²; `draw` needs strictly positive overlap with the viewport
expanded exactly 64 px per side; the ≥ 0.5 half-area rule gates only
`interactive`, which the shipped Target publishes to a MotionValue nothing
reads.

Hidden labels stop receiving transform writes — the hide path writes at most
a guarded `visibility:hidden` and leaves the matrix stale. The backface test
is CSS (`backface-visibility:hidden`, inline), not JS: our source-exact path
now carries the same inline property and the JS dot-product no longer feeds
DOM visibility (it remains a QA diagnostic).

## Observed in source, deliberately not applied

The Target drives its WebGL **glass mesh** `visible` flag from the same
verdict (`s.visible=o.draw`). That is not label visibility, so V0 records it
(byte-anchored) and does not touch the mesh path. Flagged for a product
decision.

Two declared instrument-level deviations, both observationally identical:
the Target assigns `visibility:visible` unconditionally per drawn frame where
we guard both directions; and the Target rewrites `style.transform` every
drawn frame where our CSS3DRenderer's style cache skips identical strings.

## Performance, measured

Sustained-input scenarios, Before vs Candidate, same instrument
(`performance.json` carries all four; drag-10s at 1440x900 shown here):

| metric | before | candidate |
| --- | --- | --- |
| visible labels p95 | 84 | 17 |
| transform writes/frame p95 | 100 | 17 |
| frame time p95 (ms) | 8.8 | 8.9 |
| labels.sync CPU p95 (ms) | not instrumentable at the Before commit | 0.3 |
| heap over scenario (MB) | 15.19 | -28.11 |

The Before build predates the labels.sync QA probe and was not patched to
carry it — patching it would have made it a second candidate. No quality
level, DPR or motion constant differs between the lanes; the adaptive quality
state is recorded per scenario in `performance.json`.

## The boundary discipline

A verdict whose deciding quantity sits within 0.05 px of its
threshold can flip on float noise between the page, the replay and a recorded
matrix. Mismatches inside that band are counted and reported separately —
0 on the Target lane, 0 on the
candidate lane — never silently forgiven. A second, distinct sensitivity
exists only on the Target lane: a slot whose wrap arc sits within
0.01 world units of the ±period/2 seam relocates
by a FULL period when the RECOVERED scroll wobbles by its ~1e-4 noise — at
scroll exactly 0 the seam column sits mathematically ON the boundary.
Proximity alone buckets nothing: it is a prefilter, and the row is counted as
wrap-seam-sensitive (363 rows) only when re-running the
verdict with the recovered scroll perturbed by ±1e-3 world units — ten times
the measured noise — actually FLIPS it. A failure that merely sits near a
seam stays beyond-boundary, because 1e-4 noise cannot flip it. The gate lines
state how many failures remain outside BOTH buckets (target
0, candidate 0). The candidate
lane replays from the page's own float-exact truth and can produce neither
bucket.

## The resize transition window

The Target re-grids its label pool AND its layout state on a debounced
commit after resize (the 150 ms debounce is a byte-anchored site in
`target-culling-source.json`), while its coverage camera tracks the new
window dimensions on the very next frame. Between a resize and that commit
the page culls OLD slot placements against the NEW viewport — a state the
offline replay cannot reproduce, because the replay's layout is the FINAL
layout for the new dimensions. Frames inside a 450 ms window after each
viewport change (and 3 samples before it) are therefore excluded as
transition on every lane alike, and each per-run row reports how many frames
that removed. The post-resize state itself is fully gated: settled slot
identity is 40/40 including resize-settle and orientation-flip, and the
stale-rect check runs on the last stable frame of every one of those runs.

## Wrap identity, by construction

The brief's "wrap keeps content and slot identity" gate has no separate
instrument because the identity comparison already reads identity FROM THE
DOM ITSELF — the Target lane by each label's rendered ILG code
(`textContent`), ours by `data-ilg` — so a broken slot-to-content binding
after a wrap would fail the settled identity gate directly, and a wrap
discontinuity would fail the frozen-motion smoke (wrap teleports our side:
0). The long-drag-multi-wrap runs
replay slot-for-slot through multiple full periods on all lanes; the culling
consumes verdicts keyed by stable slot index and never rebinds content.

## Files

| file | what |
| --- | --- |
| `target-culling-source.json` | the byte-anchored source read, 30 sites, live-bundle SHA comparison |
| `coverage-truth.json` | rule replayed against every lane's frames, slot for slot |
| `slot-verdicts.json` | settled-state visible-code identity, lane vs lane |
| `edge-pop-in.json` | label entries during gestures, strict-viewport overlap at entry |
| `transform-writes.json` | per-frame DOM style write pressure, all three lanes |
| `performance.json` | sustained-input scenarios, before vs candidate |
| `typography-regression.json` | container alignment, label ink, depth carry-forward |
| `motion-regression.json` | motion freeze smoke: engine vs contract, release history, card/label corner delta, continuity |
| `source-contract.json` | the 36-viewport layout source contract |

The private review package (`qa-v5/private/culling-review.zip`, git-ignored)
carries the coverage overlays, beauty frames and the screen recordings; its
`PACKAGE-MANIFEST.json` states the full review head. Target pixels appear
only there, never in this tree.
