# V5 M2 — Motion Closure

What this round asked, in one line: of the 64 landmark failures the M1 gate
reported, how many were the engine, how many were the instrument, and how many
were a difference the product has decided to accept?

The answer is in `gate-summary.json`. This file says how to read it and how to
reproduce it.

## The instrument was the largest single defect

The M1 replay decided which frame an input event belonged to with
`event.t <= frame.t`. Those two numbers come from different points in the
browser's frame pipeline: `event.t` is `performance.now()` at listener entry,
`frame.t` is the rAF timestamp, which is when the frame STARTED — before any
callback in it ran. Chrome dispatches input before the rAF block, so an event
dispatched during frame N satisfies `event.t > frame_N.t` and the rule handed
it to frame N+1.

Measured on the M1 traces: **a median of 88% of all recorded events**, one frame
late, always the same direction. That is the whole of the "persistent final
error" M1 reported — 0.1457 of travel on every reverse-flick row and 0.0527 on
every fast-flick row, identical across four viewports and three repeats. A
number that lands on the same four decimals in twelve independent runs is a
constant, not an engine.

The M2 recorder does not infer ordering from a clock. It bumps ONE monotone
counter from every event listener and every frame callback, so the order the
page's own JavaScript ran in is a recorded fact. `frame.t` keeps its real job —
it is the clock the springs integrate on — and is no longer asked a question it
cannot answer.

With that fixed, and the comparison made against the engine's own published
state rather than a recovery of it, **175 of 180 runs come out
exact to floating point** — a final error of 0.00e+00, not a small one. No
motion code was changed to achieve that; the M1 gap was the reader.

The remaining 5 runs are all at the release instant, and they are the
instrument's floor rather than the engine's error:

- 3 are a proven sub-frame race. A pointerup dispatched between two of
  our sample callbacks may or may not have been preceded by the PAGE's own
  frame callback pushing another point into the gesture history — and if it
  was, `up()` measured its velocity over a longer history. We cannot see the
  page's callback from outside. Both readings are replayed; the default is
  exact on 176 runs and the alternative is wrong on 44, which is what makes the
  default the right reading rather than the chosen one. These runs are
  classified by proof: either the alternative reading brings them inside the
  gate, or the engine's own recorded release velocity lies strictly BETWEEN the
  two readings, which means the instrument cannot resolve them.
- **2 still fail the absolute gate** and are reported as failures.
  Their alternate-ordering readings land within 0.09% and 0.9% of the engine's
  own release velocity, so the mechanism is the same race, but they are not
  formally bracketed and are not classified as if they were.

So the absolute gate of `final target error <= max(4 x worst recovery error,
0.1 world units)` = 0.1245 is **not met**: 2 of 180 runs
are outside it. The M1 error it replaces was PERSISTENT — every repeat of every
sequence at every viewport, identical to four decimals. This one is not: it is
run-specific, its mechanism is identified, and it is bounded.

## Which failures are ours, and which are the contract's

A candidate-vs-Target failure cannot by itself say whether our engine misses
the contract or the contract misses the Target. Those need opposite responses,
so they are separated by measurement.

`contract-vs-target.json` replays the FROZEN CONTRACT on the Target's own
recorded input and compares the result with what the Target actually did, on
the same landmarks against the same sealed thresholds. Result: the contract
reproduces the Target in 1518 of 1576 comparisons and misses in
58. Every landmark it misses is one no faithful implementation of that
contract can pass.

`dolly-attribution.json` does the same for the camera dolly, which is read from
the camera matrix and cannot be replayed. Three numbers per run: what the
Target did, what the frozen law predicts on the Target's own input, and what
the magnitude spring produces when fed the Target's OWN observed scroll — the
signal that actually carries the jitter. **M1 attributed the 17
`cameraDistanceOverPerspectivePeak` failures to jitter inflating a backward
difference. That is refuted here**: feeding the spring the real jittered signal
moves the dolly peak by 0.3%, while the Target's dolly differs from
the frozen law by 4.5%. Our own engine reproduces the law at
0.9998. The residual changes SIGN with the gesture — the Target dollies
more than the law during a fling and less during a drag — and the bundle shows
why: the magnitude MotionValue has two writers, the gesture handler and the
spring change handler, and which one runs last in a frame decides the value.
That is a Source Baseline this round accepted and is forbidden to re-fit, so it
is recorded for product review and not acted on.

## What is left, and what it is

The Target's scroll deviates from its own local trend by a median of 0.10303 per frame; ours by 0.0145. That is the two-rAF architecture: the Target solves its springs in framer-motion's frame loop and paints them in r3f's, and we do both in one.

M2 corrects how M1 described the mechanism. M1 called it dropped frames — "a frame on which framer did not tick repaints the same value, and the next frame carries double". The measurement does not support that. The Target's frame interval is as steady as ours (8.3 ms median against our 8.3 ms), its near-zero-step fraction is 0.0 and its double-step fraction is 0.0. It does not miss beats. What it has is a smooth spread of the per-frame step around its own trend, roughly 0.89x to 1.13x — a continuous phase difference between the loop that solves the spring and the loop that samples it.

That difference lives in `raw-scheduler-metrics.json` and is covered by
`product-exception-candidate.json` (MOTION-EXC-01). It covers the raw
single-frame numbers and nothing else — not final position, travel, decay,
pointer orbit, touch behaviour, wrap continuity, or the filtered camera-dolly
envelope, all of which are gated normally and listed by name in that file.

## The 149 remaining landmark failures, sorted

`failure-classification.json` puts every one of them in a category, by
measurement rather than by argument:

| category | rows |
| --- | --- |
| `SOURCE_BASELINE_RESIDUAL` | 138 |
| `SOURCE_BASELINE_RESIDUAL_LANDMARK` | 11 |

`SOURCE_BASELINE_RESIDUAL` is not category one wearing a different name. It is
decided by a measurement that never looks at our page: the contract replayed on
the Target's own input. Three of these rows are systematic-sign summaries where
no individual cell exceeds its threshold but every cell leans the same way —
and the frozen contract leans the SAME way, by 5.6, 5.6 and 2.8 ms against our
5.2, 9.9 and 6.5. The part that is not inherited is reported on each row rather
than folded into the attribution.

**Nothing is left in "the candidate owns it".** That is a strong claim and it
rests on two things a reviewer should check independently: that
`engine-vs-contract-v2.json` really compares the engine's own published state
(it does — 175 of 180 runs at exactly 0.00e+00), and that `contract-vs-target`
really replays on the Target's own recorded input (it does — the replay takes
the Target's events and nothing of ours).

## The baseline was sealed before the candidate existed

`target-scheduler-invariant-baseline.json` is computed from the Target alone.
Every threshold in it is `max(2 × the Target's own repeatability, a floor
declared in `scripts/v5/m2-baseline.py` before any candidate was captured)`.
Its SHA-256 is `a0a5a1f6b95b685e18453d889a9a57798fd6f73e9e47d9edc9c2a087ddf29224`, recorded in
`target-scheduler-invariant-baseline.sha256`; the gate recomputes it and
refuses to run against a modified copy. The order — Target, seal, candidate —
is the order `scripts/v5/run-m2.sh` executes in and the order the commits
landed in, so it is auditable rather than promised.

## The sign test now knows which way is worse

M1 applied the one-sided rule per cell and then a plain two-sided sign test to
the systematic-sign summary. A candidate that was smoother than the Target in
every single cell — the one thing a one-sided-upper landmark exists to allow —
was reported as a systematic FAIL. Three landmarks failed that way and none was
a defect. Every row now carries an explicit `gateType` and `status`, and the
summary is direction-aware.

## Reproducing a trace

```
scripts/v5/run-m2.sh target      # the Target, 4 viewports x 15 sequences x 3
scripts/v5/run-m2.sh baseline    # Target only; seal this before the candidate
scripts/v5/run-m2.sh candidate   # our page, same 15 x 3 x 4
scripts/v5/run-m2.sh gate exception frozen evidence
```

Every sequence is real browser input — mouse, wheel or touch dispatched through
the automation protocol. No QA hook moves either page. The two exceptions are
labelled in the traces themselves by `isTrusted`: wheel `deltaMode` 1 and 2
cannot be produced by a real device through the protocol, and neither can
`lostpointercapture`.

## Target pixels

This directory holds LOCAL pixels and Target-derived NUMBERS only. Target
pixels and side-by-side comparisons live in `qa-v5/private/`, which is
git-ignored.

## Files

- `README.md` — 10,230 bytes
- `continuity-and-input.json` — 109,748 bytes
- `contract-vs-target.json` — 606,546 bytes
- `dolly-attribution.json` — 112,168 bytes
- `engine-vs-contract-v2.json` — 304,774 bytes
- `failure-classification.json` — 95,819 bytes
- `gate-summary.json` — 75,535 bytes
- `product-exception-candidate.json` — 51,924 bytes
- `raw-scheduler-metrics.json` — 172,754 bytes
- `scheduler-invariant-gate.json` — 1,293,495 bytes
- `source-contract.json` — 170,080 bytes
- `target-scheduler-invariant-baseline.json` — 1,037,158 bytes
- `target-scheduler-invariant-baseline.sha256` — 107 bytes
- `typography-regression.json` — 4,848 bytes
