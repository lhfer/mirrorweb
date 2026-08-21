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

## How to reproduce a trace

The Target side is one run per output directory:

```
node scripts/v5/m0-motion-trace.mjs --out=artifacts/motion/target --repeat=3
node scripts/v5/m0-motion-trace.mjs --out=artifacts/motion/target-wheel --seqs=wheel-deltamode --repeat=3
```

Our side is captured **one viewport per process**:

```
for vp in 1440x900 390x844 844x390 700x700; do
  NODE_OPTIONS=--max-old-space-size=6144 node scripts/v5/m0-motion-trace.mjs \
    "--url=http://127.0.0.1:5280/?qa=1&composition=sourceExact" \
    --out=artifacts/motion/local-$vp --vps=$vp --repeat=3
done
```

Not for tidiness: the harness holds every frame of every run in memory until it
writes, and our page carries roughly twice the Target's live card count, so all
four viewports in one process exhausts Node's heap near the end of the last one.
The shards are merged by the gate through `--localExtra`, and the split changes
nothing a run measures — each viewport is captured exactly as it would be alone.

## Thresholds

Derived from the Target against **itself**, before any candidate number was
looked at: the same trajectory run three times, at four viewports, and the
pointwise spread of those runs is the repeatability. Every threshold is
`max(2 × that spread, an explicit floor)`, and the floors are declared once in
[`m1-motion-gate.py`](../../scripts/v5/m1-motion-gate.py) rather than per
sequence.

No threshold in this round was changed after a candidate number was seen. The
floors are in the script's history, and the repeatability half is computed from
the Target trace alone — it cannot move in response to our page because our page
is not one of its inputs.

Every failure mode reaches the verdict. The landmark comparisons, the axis
signs, the wheel rows, the wrap teleports, the gestures that never came to rest
and the console and page errors are folded into a single `verdict` in
`gate-summary.json`; a row that is recorded but cannot change the verdict is not
a gate, and three of those rows previously sat outside it.

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
| `highlight-path.json` | Where the specular highlight travels as the pointer sweeps. |
| `legacy-invariance.json` | v1, v2 and the bare route, pre-motion commit against candidate — judged on a deterministic geometry readback, because a whole-frame pixel comparison across two origins is provably incapable here. The control is in the file. |
| `typography-regression.json` | The accepted T1 gates, re-run at this tip, and the depth carry-forward verdict. |
| `depth-carry-forward.json` | The depth / clipping gate re-taken across the pointer orbit's four extremes and three scroll offsets. |
| `source-contract.json` | The 36-viewport engineering contract, re-run at this tip. |
| `input-trajectories.json` | What was actually dispatched, on both sides, and by what means. |
| `gate-summary.json` | Every landmark comparison, and every failure. |
| `release-decay.png` | The Target's release-decay landmarks, drawn from the numbers rather than from frames. |

The **recordings** are not here. They are in `qa-v5/private/motion-review.zip`,
which is where the brief puts them and where Target pixels are allowed to live.
An earlier pass wrote them into this tree as well and put 274 MB of GIF into the
repository; a repository is forever, so they were taken back out. The blobs
remain in history because this branch does not force-push.

## One camera, not two

An earlier reading had the Target keeping a dolly-free second camera for the
CSS3D layer, so that glass and labels separated under fast motion by design.
Its own recorded CSS3D camera matrix refutes it: solve the camera position out
of the inverse matrix and its distance from the origin is exactly 1000.000 at
rest, 1158.13 during a fast flick, 1223.01 during a long drag — and exactly
1000.000 through an entire pointer sweep, which moves the camera all over the
orbit and produces no velocity. A dolly-free CSS3D camera cannot do that.

`card-label-motion.json` now gates the label against the card plane through the
camera that paints both, and asserts that the two cameras **agree** at every
frame rather than that they separate. The dolly is zero at rest, which is where
the layout contract measures, so the source contract is untouched either way.

## The comparison that could not be made with pixels

`legacy-invariance.json` asks whether the motion work changed v1, v2 or the
bare V3 route. It used to answer by comparing canvas bytes, and it reported
that all three DIFFER.

They do — but not because of the code. The two builds have to be served from
two **origins**, and each origin decodes the media independently: probed live,
the same clip read `currentTime` 2.764 on one and 2.741 on the other at the
same point in the harness. Serving the **same commit** on two ports and running
the same comparison gives 0/3 identical, on the bare V3 route as much as on v1
and v2.

That control now runs first, and it is in the file. When it fails — as it does
here — the pixel rows are reported and explicitly **not** gated, and the
verdict rests on a readback that is deterministic across origins: the projected
slot landmarks, which are pure geometry. Those are identical on all six
route-viewport pairs, and the control confirms the substitute instrument is
capable where the original was not.

## The highlight, and what a pixel can settle here

The Target has no light object: the forensics established that by absence, and
the highlight is moved solely by the camera orbit. That mechanism is measured
on **both** sides, like for like, by the orbit rows in `pointer-orbit.json` --
the camera angles are recovered from each page's own CSS3D matrix.

`highlight-path.json` measures the highlight itself, from the recorded pixels.
Its candidate rows are gated on a sweep taken with the media layer **off**,
where the highlight is the only bright thing in frame. The cross-side
correlation is reported and deliberately **not** gated: our page freezes its
media for a fixed state and the Target's video cannot be turned off, so a
whole-frame luminance centroid has moving video in it on one side and not the
other. How far the highlight travels and how bright it is are functions of the
glass optics, which this stage may not touch and which the product has not
accepted -- gating them here would fail motion for an optics difference.

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
