# M0 / M1 — source-exact motion

The Target's motion was **read**, not fitted. Its application bundle carries the
whole model as literals, in a settings object whose setter is never called
anywhere in the bundle — no debug panel, no query-string override, no runtime
mutation path. The live traces confirm that rather than establish it: the
measured follow ratio comes out at the bundle's own 1.5 plus its own fling term,
and the camera orbit comes out at exactly ±0.05 rad.

Full write-up: [`docs/v5/SOURCE_EXACT_MOTION.md`](../../docs/v5/SOURCE_EXACT_MOTION.md).
Contract: [`config/target-motion-source-v1.json`](../../config/target-motion-source-v1.json).

## How this was measured

Everything here is driven by **real input**. Mouse, wheel and touch events are
dispatched through the automation protocol as trusted browser input, on both
sides, and no QA hook moves either page. `setOffset` exists on our page and is
deliberately never used to produce a trace or a recording: a curve produced by
writing the offset would show the renderer working and say nothing about the
gesture layer, which is the thing under test. The one labelled exception is
wheel `deltaMode` 1 and 2, which no real device can produce through the
protocol; those are synthetic `WheelEvent`s, and an untrusted wheel event still
reaches a listener if one exists, so absence of response is evidence either way.

The Target's scroll lives in closed-over motion values that no page script can
reach. It is recovered instead, exactly, from the Target's own CSS3D card
matrices — every card's world position is a function of the scroll, so the
per-frame change in arc coordinate is the per-frame change in scroll. Cards the
page has culled are excluded: their matrices are stale rather than stationary.

## Thresholds

Derived from the Target against **itself**, before any candidate number was
looked at: the same trajectory run three times, at four viewports, and the
pointwise spread of those runs is the repeatability. Every threshold is
`max(2 × that spread, an explicit floor)`, and the floors are declared once in
[`m1-motion-gate.py`](../../scripts/v5/m1-motion-gate.py) rather than per
sequence.

## The chain

Four questions, each meaningful only if the one before it held:

| file | what it settles |
| --- | --- |
| `target-motion-contract.json` | Does the CONTRACT reproduce the Target? The model is driven by the Target's own recorded input and compared with the Target's own recovered trajectory. |
| `engine-vs-contract.json` | Does OUR ENGINE reproduce the contract? The model is replayed on our page's own recorded input and compared with what our page actually did. This separates "the model is right" from "we implemented the model". |
| `drag-response.json` | Displacement, follow ratio and input-to-motion latency, ours against the Target's, at every threshold above. |
| `flick-decay.json` | Release velocity, time to 50%, to 10%, to visual stop, travel after release, and the largest single-frame velocity step — the abrupt-stop check. |
| `pointer-orbit.json` | The camera orbit driven by the smoothed pointer, recovered from the CSS3D camera matrix on both sides. |
| `wheel-normalization.json` | Proof of ABSENCE, at `deltaMode` 0, 1 and 2, on both sides. |
| `touch-runtime.json` | Touch and mouse parity, and whether a cancelled or capture-lost gesture leaves the page stuck. |
| `wrap-continuity.json` | Does any visible card teleport when the infinite grid recycles? |
| `resize-continuity.json` | A resize taken while the page is still moving, on both sides. |
| `card-label-motion.json` | Does the type stay on its card while the page moves? |
| `legacy-invariance.json` | v1, v2 and the bare route rendered by the pre-motion commit and by the candidate, byte for byte. |
| `typography-regression.json` | The accepted T1 gates, re-run at this tip. |
| `source-contract.json` | The 36-viewport engineering contract, re-run at this tip. |
| `input-trajectories.json` | What was actually dispatched, on both sides, and by what means. |
| `gate-summary.json` | Every landmark comparison, and every failure. |

## Two cameras, on purpose

The Target dollies its render camera with the smoothed velocity magnitude and
keeps a **second camera without the dolly** for the CSS3D transform, the
projection and the culling. So under fast motion its glass dollies and its
labels do not — they separate, deliberately.

`card-label-motion.json` therefore gates the label against the card plane
projected through the **label** camera, which is the invariant the Target
actually maintains. Gating against the dollied glass silhouette would fail a
faithful reproduction *for being faithful*. The separation itself is recorded
beside the verdict, as contract behaviour.

Both cameras are identical at rest, which is where the layout contract measures,
so the source contract is untouched.

## Depth carry-forward from T1

T1 recorded `actualOverlappingCardPlaneSamples = 0` — no two card planes were
ever observed overlapping on screen, so its depth result established the clip
structure and single-card interior ordering, not real occlusion ordering.
Motion moves the planes, so the count is re-taken here at the four extremes of
the pointer orbit and three scroll offsets. The result is in
`typography-regression.json`.

## Fixed capture conditions

Quality high with the adaptive sampler off, media frozen at t=2, DPR 1, and the
`?composition=sourceExact` defaults. Motion is **not** paused for a motion
trace, which is the point of one.
