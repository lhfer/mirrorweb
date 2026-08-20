# qa-v5/fsx — source-exact composition rebase

Status: **READY FOR PREVIEW-FIRST PRODUCT REVIEW**

Full write-up: [`docs/v5/SOURCE_EXACT_COMPOSITION.md`](../../docs/v5/SOURCE_EXACT_COMPOSITION.md).
Contract: [`config/target-layout-source-v2.json`](../../config/target-layout-source-v2.json).

LOCAL pixels and Target-derived NUMBERS only. Anything embedding Target pixels
is in `qa-v5/private/`, which is git-ignored.

## Headline

| | |
| --- | --- |
| Source contract | **PASS 36/36** viewports |
| worst slot world position, engine vs model | **0.0** world (limit 0.1) |
| worst orientation, engine vs model | **1.21e-6** deg (limit 0.05) |
| worst projected card corner, engine vs model | **0.0** px (limit 0.5) |
| worst world delta, engine vs the Target's own DOM | **0.005366** world (limit 0.1) |
| `npm run v5:target-layout-source` | **PASS 14/14**, failure branch exercised and exits 1 |
| Pixel gate | **8/14** viewports, **115/122** checks (F2.7 measured identically: 7/14, 112/123) |
| Runtime | **PASS 64/64** |
| F0 regression | **PASS 20/20**, baseline frame byte-identical |
| v1 / v2 / default | byte-identical to before, `sourceExact` is not the default |

## What changed structurally

- One sphere with one radius, replacing a cylinder plus a fitted `radiusY`.
- Camera at `(0, 0, perspective)` on axis: one world unit is exactly one CSS
  pixel at z = 0, delta **0**, where every earlier path carried 3.2e-5 from
  `CAMERA.y = 8`.
- Card size, cell pitch and pool shape are per-viewport facts from one
  `SourceExactLayoutFrame`, consumed by renderer, grid, foundation, MediaFit and
  QA hooks. Nobody recomputes it.
- 256 preallocated slots; a resize changes only `activeSlotCount` and per-slot
  scale. No mesh, material, texture or video churn.
- `ILG code = slotIndex + 1`, bound to the pool slot as the Target binds it.
- No rest offset and no phase rule: an even column count puts the seam on the
  centre line by itself.

## Files

| file | what it is |
| --- | --- |
| `source-contract.json` | The engineering gate over 36 viewports, with every tolerance and every measured value. |
| `target-layout-source.json` | `npm run v5:target-layout-source` output: bundle hash, TS/Python/DOM agreement. |
| `gate.json` | Pixel gate over the 14 mandatory viewports, plus `notMeasuredBackfill` mapping every unmeasurable pixel item to the numeric checks that cover it. |
| `detector-residual.json` | How far the detector reads a TARGET card from where the TARGET's own DOM says it is — both sides of that comparison come from the Target alone. |
| `sphere-occlusion.json` | Target-vs-engine overlap classification: 21 pairs and 3 same-depth collisions each at 899x900. |
| `runtime-assertions.json` | 64/64, including every reachable pool-size transition and why 4, 6 and cols>10 are unreachable. |
| `default-proof.json` | v1, v2 and the bare route render byte-identically; `sourceExact` is not the default. |
| `f0-regression.json` | 20/20. |
| `local/`, `session/` | Candidate frames and runtime state. |

## What still fails, and why it is not the layout

Every remaining pixel-gate failure is **gutter centre** (3.5–6.5 px against a
3 px limit) at 1366x768, 1440x900, 1440x1080, 780x470, 960x500, 960x720, plus one
gutter width at 780x470. Card size, card centre, edge yaw, row parity, centre
dark band, overlap and large void pass everywhere.

The source contract shows the engine matches the Target's own DOM geometry to
0.005 world units, so the geometry is not what is wrong. Two measurements say
what is:

1. The detector disagrees with the Target about the Target: reading the Target's
   own frame, it places card centres up to **2.67 px** and widths up to
   **71.89 px** away from the Target's own DOM geometry, always smaller.
2. Our frame reads **closer** to the Target's true geometry than the Target's own
   frame does, at all nine viewports tested (1440x900: 11.88 px against 21.38 px;
   667x375: 1.12 px against 23.50 px).

A flat opaque slab has a crisp edge; a video-filled glass card does not.

## Two harness defects fixed this round

- **`pick_void` used an absolute 20 000-pixel threshold**, which is ~1.5% of a
  1440x900 frame but 8% of a 667x375 one. 667x375 has 16 588 void pixels — 6.6%
  of the frame, and 3 412 short — so it fell through to a preset matching nothing
  and the whole frame read as one solid card. Now a fraction of the frame. This
  had degraded every small-viewport measurement since F0.
- **The overlap check assumed a cylinder.** On a sphere, rows at different depths
  occlude, which is correct. Measured at 899x900 the Target's own geometry
  produces the same 21 overlapping pairs and 3 same-depth collisions the engine
  does, so the assertion is now Target-referenced and the strict count is
  reported beside it.

No gate threshold was changed.
