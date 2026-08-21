# qa-v5/t1 — T0 render-loop repair, T1 source-exact typography

Status: **READY FOR TYPOGRAPHY PRODUCT REVIEW.** Typography is a candidate. It is
not accepted, no Target visual pass is asserted, motion and optics are
unmodified and main is not merged.

This directory holds LOCAL pixels and Target-derived NUMBERS only. Target pixels
and any Target/local overlay live in `qa-v5/private/`, which is git-ignored.

## T0 — the render loop, and what it invalidated

`GridAppV4.tick` contained

```
if (!this.adaptiveQuality) return;
```

above `motion.step`, `grid.update`, `applyPose`, `labels.sync` and `drawFrame`.
Turning the adaptive sampler off — which every FSX-A capture did, to hold a
quality level still — froze the page. Three FSX-A results were artefacts of it:
media-only and glass+media were byte identical because `setRenderLayers` changed
the scene graph and nothing redrew it; the 24-frame recordings were 24 copies of
one image; and the quality sweep's screenshots were stale.

Now only the sampler is conditional, and `renderOnce()` draws a frame
synchronously at the end of every state hook.

| file | what it settles |
| --- | --- |
| `render-loop-proof.json` | **PASS 22/22.** 165 frames in 1200 ms with the sampler off; it was 0. Every hook advances a monotonic render stamp; with no QA hook called the explicit render stamp stays unchanged between two reads. |
| `beauty-before.json` | The four render states per viewport, each hashed, with the render-layer state read back off the scene, and the media-only / glass+media pixel diff: 70–84% of pixels differ, mean delta 11.6–18.1. |
| `recording.json` | 24/24 unique frames on desktop and mobile, offsets read back from the engine rather than logged as requested. |
| `quality-invariance.json` | **PASS 57/57**, off the real glass mesh — geometry bounding box 656.64 × 492.48 (exactly 4:3), 5570/3242/1850 vertices across high/medium/low, a fresh geometry per level, a redrawn silhouette each, and the label rect unchanged. |

The stamp, not the hash, is the primary evidence for the hook path: the live
loop repaints too, so an unchanged hash cannot distinguish "the explicit redraw
ran" from "the loop happened to redraw anyway". The stamp counts `renderOnce()`
calls and nothing else, so the idle check states that the explicit render stamp
stays unchanged without a QA hook -- not that the page did not repaint, which
the stamp cannot see.

One finding recorded rather than patched: `setPointer` writes the smoothing
TARGET and `MotionController.step` carries the applied pointer toward it, so a
paused page legitimately produces an identical frame. Motion is frozen this
round. The proof steps the page briefly and shows the pixels move.

**`qa-v5/fsx-a` is superseded** for the media/glass comparison, the recordings
and the quality sweep. Its route proof and source contract stand.

## T1 — typography

`TileLabelLayer` sized every label element to `TILE.width` × `TILE.height`
(539.8 × 399.6, fixed) while a source-exact card is `frame.planeWidth` ×
`frame.planeHeight`. Every type size in the card is a container query against
that element, so the type was scaled against a card that did not exist: +113% at
667x375, +103% at 700x700, +92% at 390x844, −26% at 1920x1080 — and −1.4% at
1440x900, the viewport the layer was tuned at.

| file | what it settles |
| --- | --- |
| `target-typography-contract.json` | **PASS 29/29.** Every measured Target property, per viewport, beside ours. Both sides read by the same instrument. |
| `container-alignment.json` | **PASS 47/47.** Label corners reconstructed through the live CSS3D chain and validated against the browser's own bounding rect (0.005 px), then compared with the card mid-plane: worst 0.011 px against a 1 px gate. |
| `depth-clipping.json` | **PASS 30/30.** The Target's clip structure reproduced; no title collides with a title on a non-overlapping card; at 1199 sampled pixels the topmost label is the nearest card's, 0 wrong. **Scope:** `actualOverlappingCardPlaneSamples = 0` -- no two card planes were observed overlapping on screen, so this proves the clip structure and single-card interior ordering, not real occlusion ordering. Carried to the motion stage. |
| `label-ink.json` | **PASS.** Zero label ink outside the card silhouettes at all seven viewports, measured in pixels from a labels-only capture. |
| `source-contract.json` | **PASS 36/36.** The engineering contract re-run at this tip, not asserted from the freeze diff: engine vs model vs the Target's own DOM. Worst slot world delta vs model 0.0, worst orientation 1.21e-06 deg, worst projected corner 0.0 px, worst world delta vs Target DOM 0.005366 across 36 viewports. |
| `viewport-gate.json` | **PASS 7/7 viewports, 13/13 engineering.** Each row names the file that produced it, including the Source Contract row, which now reads its verdict out of `source-contract.json` instead of asserting it. |
| `attribution.json` | What is left, and which system owns it. |
| `session/session.json` | One live page resized landscape → portrait → square → landscape: the label box tracks the frame at every step and slot identity holds. |

### What the Target actually does

Read from its own DOM at seven viewports. It has **no responsive branch**: one
container-query scale, every ratio identical to the digit across all seven.

* label element sized to the card plane, CSS3D object scale 1 — scheme A,
  decided by measurement (its `matrix3d` basis columns are unit length);
* text plane depth **zero** — every Target label sits exactly on the sphere,
  radial distance = R to within 1.2e-3 world units across 36 viewports. Ours was
  pushed 49 units along the normal by a number nothing measured;
* padding 7cqw; title 12cqw / 0.82 / −0.085em / 600 / max-width 92% /
  `text-wrap: wrap`; meta 1.7cqw / 1.5 / 0.18em / 500 mono; deck 2.5cqw / 1.25 /
  −0.01em / 500 / max-width 58cqw; rule 0.2cqw at white/55 **above** the title
  with 3.3cqw clear of it;
* one clip: an absolute layer at the card box with `overflow: hidden`, no
  clip-path, no radius.

The title box's bottom offset -- distance from the card bottom to the bottom
edge of the title box, as a percentage of card height -- now matches the Target
to three decimals at every viewport. It is reported as
`titleBoxBottomOffsetPct`; this instrument reads boxes, not font metrics, so
nothing here is a typographic baseline.

## Visual set

Per viewport, in `local/`: the four render states, the media-vs-glass difference
map, before-vs-candidate, labels-only, and the card-mask/label-bounds overlay.
Target Full Beauty, the Target/Candidate 50-50 and the three-way strips are in
the private package, because they contain Target pixels.

## Fixed capture conditions

Quality high with the adaptive sampler off, media frozen at t=2, motion paused,
pointer (0,0), DPR 1, `?composition=sourceExact` defaults, and an explicit
`renderOnce()` after every state change.
