# V5 M3 — Final Motion Source Reconciliation

One question this round: the M2 gate failed 92 camera-dolly rows and 53
release-velocity rows, and M2 had already refuted the mechanism M1 blamed. What
actually causes it?

The answer was in the Target's bundle, not in a residual.

## The magnitude MotionValue has two writers, and the frame decides between them

The value that drives the camera dolly is written from two places:

- **the gesture** — `g.set(hypot(t.velocity.x, t.velocity.y))` in `onPan` and
  `onPanEnd`. That is the FINGER's speed.
- **the scroll springs** — `g.set(hypot(f.getVelocity(), p.getVelocity()))` in
  their own change handlers. That is the SPRING's speed: the finger's times the
  1.5 drag gain, minus the spring's own lag.

They are not two estimates of one quantity. They are two different quantities
written to one value, and they differ by about the drag gain while a finger is
down. Whichever writes last in a frame is the one the magnitude spring
retargets to at that frame's `postRender`.

Two lines of the bundle settle which one that is:

- `let Sy=e=>(t,r)=>{e&&mH.update(()=>e(t,r),!1,!0)}` — every pan handler is
  wrapped in this. The third argument is `immediate`, which with the step
  already processing appends the callback to the **live** update set. `Set.forEach`
  visits entries added during iteration, so the application's `onPan` runs
  after every spring tick already queued — whatever order they were registered
  in.
- `onEnd:(e,t)=>{delete this.session,i&&mH.postRender(()=>i(e,t))}` — `onPanEnd`
  is not wrapped. It is scheduled straight onto `postRender` from inside the
  pointerup listener, which runs in the input-dispatch phase, so it is the
  first entry in that frame's postRender set — ahead of the spring's own
  retarget.

So: **the gesture writer wins every frame that carries a pan dispatch, and the
release frame. The scroll writer stands alone on every frame that carries
neither**, which is every frame after the release. Twenty source sites, each
with its byte offset and the verbatim text at it, are in
`magnitude-writer-order-source.json`. All 20 of them re-verify.

## What that predicted, and what it did

The residual was never a scale factor: it changed SIGN with the phase of the
gesture. The Target dollied LESS than the frozen law during a drag and
MORE during a fling. Two writers that disagree by the drag gain, with
the gesture one winning while the finger is down, is exactly that shape.

Replayed on the Target's own recorded input, changing nothing but which writer
the magnitude spring retargets to:

| magnitude writer order | signed median ratio | median absolute residual |
|---|---|---|
| `scrollLastAlways` (pre-M3) | 0.9514 | 17.82% |
| `gestureLastWhileActive` (recovered) | 1.0249 | 2.58% |

Both readings are quoted because they say different things. The signed number
is the smaller of the two under the old order **because the drag and flick
residuals had opposite signs and cancelled**; reporting only the signed −4.5%
understates what any single sequence showed.

This is a source read, not a fit. It was derived before the candidate was
replayed, it changes no constant, it adds no scale factor and no per-sequence
branch, and it predicted the direction of the error in both phases at once.

## The five release runs M2 could not settle

M2 reported three runs as `INSTRUMENT_SUBFRAME_RACE` and two as failures, all
at the release instant, all turning on something invisible from outside the
page: whether the page's own frame callback had pushed another point into the
gesture history before the pointerup.

Two recordings closed it, and neither is a reading:

- **The raw rAF timestamp.** The engine stamps its gesture history with the
  frame's rAF timestamp. The M2 replay ran on `t = raf - t0` rounded to a
  thousandth, and framer-motion's velocity window is a strict `> 100 ms`. A
  history point exactly one window old therefore falls inside the window on one
  time origin and outside it on the other, purely in the last bit of a double:
  `7048.6 - 6948.6` is `99.99999999999909` and `142.3 - 42.3` is
  `100.00000000000001`. Measured on the first M3 smoke run, the engine took its
  window over 108.3 ms and the replay over 100.0 ms — an 8.3% difference in the
  fling, out of a change of origin.
- **The release record.** The model now writes down every release as it commits
  it: the complete history, the two points the window used, the velocity that
  came out, the scroll target either side of the fling. Written inside
  `pointerUp`, read back by nothing.

Result: **132 of 132** releases exact to floating point. The
vocabulary this file is allowed to use is `EXACT` and
`INSTRUMENT_UNREADABLE_WITH_DIRECT_PROOF`; there is no "likely", no "probably"
and no "almost matches" in it, because there is nothing left to be uncertain
about.

Engine against the frozen contract, on our own page's real input, replayed in
true callback order: **180 of 180** exact to floating point,
0 outside the absolute gate of 0.13276 world units.

## Attribution is per cell now

M2 attributed by landmark NAME: if the contract missed a landmark anywhere, a
candidate failure carrying that name was called inherited. Eleven rows were
classified that way and the brief bans the shortcut. A landmark can be
reproduced exactly in one cell and missed badly in another.

`failure-attribution-v2.json` decomposes every failing cell exactly, with no
remainder:

```
candidateObserved - targetObserved
    = (contractOnTargetInput    - targetObserved)          inherited
    + (contractOnCandidateInput - contractOnTargetInput)   input stream
    + (candidateObserved - contractOnCandidateInput)       candidate
```

A cell is attributed to the term that both exceeds that cell's own threshold
and is the largest of the three. If none does, it stays
`UNRESOLVED_ATTRIBUTION`, which is a result and not a hole to fill.

| category | failing cells |
|---|---|
| `SOURCE_CONTRACT_RESIDUAL_EXACT_CELL` | 38 |
| `TARGET_INPUT_VARIATION` | 18 |
| `INSTRUMENT_UNREADABLE` | 7 |
| `UNRESOLVED_ATTRIBUTION` | 2 |

## The gate

Verdict **FAIL**, against the M2 baseline sealed at
`a0a5a1f6b95b685e18453d889a9a57798fd6f73e9e47d9edc9c2a087ddf29224` before any candidate existed. This round did not
recompute it, did not move a floor and did not re-capture the Target.

| input | count |
|---|---|
| landmarkFailures | 65 |
| engineVsContractFailures | 0 |
| visibleWrapTeleportsOurSide | 0 |
| wheelResponsesOurSide | 0 |
| gesturesNeverAtRestOurSide | 0 |
| consoleAndPageErrorsOurSide | 0 |

## One instrument limit, stated

Our traces carry the raw rAF timestamps. The Target's predate that field and
carry the shifted, rounded clock, so a Target replay that sits exactly on the
velocity-window boundary cannot be resolved. Every Target replay is therefore
run three times, nudged either way by 1e-9, and a cell whose answer moves is
flagged `windowBoundarySensitive` and carries both readings. It is never
resolved by picking whichever fits. 758 cells are flagged.

The obvious question about a bracket that wide is whether it explains away the
cells the contract misses. It does not: of the 106 cells the contract
misses, 90 are boundary sensitive, but only
**12 of them would actually close under the other reading**, and
those twelve are reported as misses rather than closed.

## The release velocity is quantised, and the Target disagrees with itself

framer-motion measures the release over a window it closes with a strict `>`,
and the gesture history is fed at frame rate. A release therefore measures over
either N or N+1 points, and the span it actually used is either about 100.1 ms
or about 108.3 ms, never between. One extra 8.3 ms sample inside a 100 ms window
moves the answer by roughly 8%.

**The Target's own three repeats of one scripted gesture land on opposite sides
of that boundary in 33 of its 44 cells**, spreading
its own release velocity by a median 7.78% and up to
8.81%. The gesture is identical each time; the answer is not.

This was found while checking whether one candidate capture was noisier than
another, and three tests falsified that: the fast gestures' event streams are
identical across every lane, stripping the raw rAF clock changes nothing, and
stripping the release record changes nothing. The per-run differences are 0.00%
wherever two captures landed on the same side and 6.7-7.6% wherever they did
not, with nothing in between — a quantum, not noise.

Nothing was added to the gate to make it boundary-aware. Discovering a
quantisation and then teaching the scorer to forgive it is fitting, one step
removed. It reaches the gate as `inputStreamResidual` and is categorised by the
attribution rule that was frozen before any of this was measured.

## Which capture was scored, and why

`capture-acceptance-rule.json` carries this in full, including the parts that
did not go the way the rule expected. In short: a first M3 capture overlapped
the visual recording lane, so a rule was written — before any gate was run —
that it would be replaced only on capture quality and that the replacement's
verdict would stand whatever it turned out to be. **The replacement then FAILED
that rule on 4 of its 6 landmarks**, and the investigation above showed the
rule's premise was wrong rather than the capture. The clean capture was scored
anyway, on three grounds fixed before its verdict existed: it ran on an idle
machine, its input stream matches the Target's on the fast gestures, and it
agrees with the Target's window side in 75 of 132 runs against the replaced
capture's 71.

For comparison, and not re-run: the replaced capture gave 84 landmark failures,
the same 180/180 engine-vs-contract, the same 132/132 releases, and 13 failing
dolly cells against this one's 8.

## The dolly cells that still fail

| cell | Target | Contract on Target input | Candidate | direction | size |
|---|---|---|---|---|---|
| `60Hz|700x700|slow-vertical-drag|dollyPeakTimeMs` | 1150.0 | 1150.0 | 1261.1 | later | +111.1 ms, 9.7% |
| `120Hz|700x700|slow-vertical-drag|dollyPeakTimeMs` | 1158.3 | 1152.8 | 1263.9 | later | +105.6 ms, 9.1% |
| `60Hz|1440x900|slow-horizontal-drag|dollyPeakTimeMs` | 1161.1 | 1161.1 | 1261.1 | later | +100.0 ms, 8.6% |
| `120Hz|1440x900|slow-horizontal-drag|dollyPeakTimeMs` | 1166.7 | 1158.3 | 1261.1 | later | +94.4 ms, 8.1% |
| `60Hz|700x700|diagonal-drag|dollyPeakTimeMs` | 1150.0 | 1150.0 | 1238.9 | later | +88.9 ms, 7.7% |
| `60Hz|1440x900|slow-vertical-drag|dollyPeakTimeMs` | 1150.0 | 1150.0 | 1233.3 | later | +83.3 ms, 7.2% |
| `120Hz|1440x900|slow-vertical-drag|dollyPeakTimeMs` | 1158.3 | 1152.8 | 1236.1 | later | +77.8 ms, 6.7% |
| `120Hz|700x700|diagonal-drag|dollyPeakTimeMs` | 1158.3 | 1150.0 | 1236.1 | later | +77.8 ms, 6.7% |


All of them are the same landmark, all on slow drags, all in the same direction,
and the candidate residual is **0.0 ms on every one** — our engine reproduces
the frozen contract on our own input exactly. The difference is that our
capture's 31-step drag ran 1106 ms against the Target's 1003 ms: the drag
dispatched 3.4 ms slower per step and a dolly peak that sits at the release
moves with it. Visually this is the camera reaching its furthest point about a
tenth of a second later on a one-second drag, at the same depth.

Reported per §8. No exception is proposed and none is taken.

## The two unresolved rows

2 rows are `UNRESOLVED_ATTRIBUTION`. The brief asked for zero and this round did not reach it. Both are systematic-sign SUMMARY rows — `viewport=ALL, sequence=ALL` — rather than exact cells, and in both the largest term is target input variation which just misses the bar the rule sets for carrying a summary:

- `120Hz|ALL|ALL|velocityIntegralX` — the largest term, TARGET_INPUT_VARIATION at 1.3523, is not itself lopsided (p=0.065), so no term carries the summary. Others: source 0.73152 (p=0.15), candidate 0.00673 (p=1.9e-07).
- `60Hz|ALL|ALL|timeTo10PctMs` — the largest term, TARGET_INPUT_VARIATION at 2.1233, is not itself lopsided (p=0.081), so no term carries the summary. Others: source 0 (p=7.6e-06).

The rule was frozen before this capture was scored. Moving its qualifying threshold from p<0.05 to p<0.10 would attribute both to target input variation and report zero unresolved; that change is named here and was NOT made, because choosing a threshold after seeing which side of it the data fell on is the failure mode this file exists to prevent. The candidate term on both rows is 0.00673 and 0.0 against gate thresholds of 0.4217 and 2.08, so neither row can be the engine's — but that is a bound, not the attribution the rule requires.

## What was found and NOT acted on

`onPanEnd` running at `postRender` also means its `d.set(+fling)` schedules the
SCROLL retarget into the NEXT frame's postRender — one frame later than a drag
frame does. That is a real source-read asymmetry in the scroll path. The
product re-authorised exactly two scheduling semantics this round, the release
history window and the magnitude writer order, and this is neither. It is
recorded in `magnitude-writer-order-source.json` under
`whatThisDoesNotCover` and left for the product to decide.

## Files

- `README.md` — 14,222 bytes
- `callback-order-proof.json` — 132,672 bytes
- `capture-acceptance-rule.json` — 10,636 bytes
- `card-label-motion.json` — 13,531 bytes
- `continuity-and-input.json` — 109,853 bytes
- `contract-vs-target-v2.json` — 1,420,477 bytes
- `dolly-envelope.json` — 542,414 bytes
- `engine-vs-contract-v3.json` — 291,313 bytes
- `failure-attribution-v2.json` — 71,949 bytes
- `gate-summary.json` — 36,971 bytes
- `magnitude-writer-order-source.json` — 52,328 bytes
- `raw-scheduler-metrics.json` — 172,879 bytes
- `release-history-proof.json` — 239,132 bytes
- `scheduler-invariant-gate.json` — 1,253,576 bytes
- `source-contract.json` — 170,080 bytes
- `typography-regression.json` — 4,848 bytes

## Reproducing

```
M3_CAPTURED_AT=<sha> scripts/v5/run-m3.sh
```

The Target is not re-captured and the baseline is not recomputed: the gate
recomputes the baseline's SHA-256 and refuses to run against a modified copy.
