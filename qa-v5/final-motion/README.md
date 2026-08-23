# MirrorWeb V5 — Final Motion Convergence Sprint

    Candidate  http://127.0.0.1:5293/?review=target
    Current    http://127.0.0.1:5293/?review=current
    Serve      npm run review

For a real device on the same network: `npm run review:lan` serves the same
build on `0.0.0.0:5293`, and `npm run review:lan:url` prints the addresses to
type in. Adding `&status=1` to the candidate URL mounts a small live readout —
FPS, quality, device sample tier, material-cache size, black-frame count. It is
a QA surface: it does not exist unless that query is present, and it must be off
for any capture or review pass. **No real-device result is asserted by this
round.** What is guaranteed is that the review route is reachable from a phone.

**Final product state: READY FOR FINAL REVIEW WITH DECLARED INTERMITTENT FLING
RESIDUAL.**

Target Visual PASS is **not** asserted. The shipped optical default is unchanged
(`opticalBody=current`). `main` was not merged, not force-pushed and not touched.

---

## What this round was asked to fix, and what it found

Two problems were handed over as established: an intermittent second mode on the
fast flick, and a single-frame jump through the portrait→landscape relayout.
Both were investigated with the same instrument installed on both pages. Neither
turned out to be what the handover said it was, and both findings are published
with the runs that produced them rather than summarised.

### A. The fast-flick second mode is on the Target too

Ten runs a side, identical real pointer input, same recorder:

| | mode A | mode B | rate |
|---|---|---|---|
| Target | ~816.6 px | ~833.0 px | 2/10 |
| Candidate | ~815.6 px | ~832.4 px | 4/10 |

The rate difference is **not significant** — Fisher exact, two-sided, p = 0.63.
The finding is that both pages have the mode, not that one has it more often.

The mechanism is one-frame quantisation of the 100 ms velocity window.
`velocityOfHistory` walks back through the gesture history — one point per
frame, ~8.3 ms apart at 120 Hz — until the span exceeds `sampleWindowMs`, so the
span it settles on is either just over the boundary or one frame further back.
Every candidate run has the **same** history length (15) and the **same** number
of frames between the last move and the release (2); only the window length
differs, and the velocity, the fling and the travel follow it:

    mode A   windowDt 107.7–109.3 ms   velocity −3372..−3422 px/s   fling −337..−342 px
    mode B   windowDt 100.1–100.9 ms   velocity −3653..−3682 px/s   fling −365..−368 px

The fling is exactly velocity/10 in both modes. A ~7.5% shorter window gives a
~7.5% larger velocity and ~16 px more travel.

No source scheduling mismatch was found, so **no motion constant was touched** —
and none should be. The window duration, the fling multiplier and the spring
constants are the only things that could remove this mode, and removing it would
move the page *away* from the Target, which has it.

Detail, per-run, with the full release record: `flick-truth.json`.

### B. The orientation "36.7 px jump" is an estimator artefact — and the relayout is atomic

The pre-registered number compared 36.7 px against the Target's 4.5 px. Those
are not the same measurement. The estimator unwraps card positions with a
0.6 × pitch threshold (65.35 px), which **erases any axis component above it and
keeps whatever is below**. At the flip frame every sampled card moves hundreds of
pixels on both pages; what survives is arbitrary. Our card 3 moved
(723.90, −36.72) px, so X was erased and −36.72 survived. The Target's card 3
moved (247.24, −268.36) px, so both axes were erased and it scored 0.00.

Scored by its own rule on this round's runs, at five runs a side, **the Target
fails the gate too, and by more than the candidate does**: Target 38.13–44.40 px
against a 12.54 px limit, candidate 36.71–36.81 px. The pre-registered gate is
still reported as it falls, unchanged, in `orientation-truth.json`.

The measurement that a viewer could actually see is the raw frame-to-frame card
move, with nothing subtracted. Five runs a side, repeatable to 0.1 px:

| | on the flip frame | max on any other frame | discrete teleports |
|---|---|---|---|
| Target | 364.9 px | 530.5 px, 148–158 ms later | **2** |
| Candidate | 956.7 px | 3.2–3.8 px | **1** |

Neither page eases a rotation; on both, cards teleport to their new slots. The
candidate does it **once**, on the frame the viewport changes. The Target does it
**twice**, holding a partly-relaid-out state for about nine frames. §三 gate
item 4 asks for the absence of an intermediate wrong phase from two layout
applications; the candidate has none — `viewportApplies` reads exactly 1 per
distinct viewport. Which of the two patterns looks better at 1× is a product
call, not a metric one, and the side-by-side recording plus the frame-by-frame
inset in the private package are there to make it.

---

## The one product change

`GridAppV4` now applies the viewport **at most once per actual bounds change**.
The apply still happens inside the resize listener, where it always did.

The source basis is the Target's own resize semantics. Its `<Canvas>` measures
through react-use-measure, whose `calculate` ends in a bounds-equality guard:

    f.current && (e = c.current.lastBounds, t = p,
      !it.every(r => e[r] === t[r])) && u(c.current.lastBounds = p)

A measurement reporting the size the page is already laid out for produces no
state update and therefore no re-application. All three of the Target's arms —
window `resize` undebounced, `ResizeObserver` and `screen.orientation` at 50 ms —
pass through it.

What it removes: the old code applied the whole viewport pipeline immediately on
**every** resize event, and then once more 80 ms after the last one, with no
check that anything had changed. (The trailing apply was already coalesced — the
handler cleared its timer before re-arming — so a burst of N events cost N+1
applies, not 2N. An isolated resize, which is the single-flip case, cost exactly
two.) Measured: `viewportApplies` now reads 1 on a single-viewport rotation and
3 on the three-event settling rotation; under the old code those were 2 and 4.
The 80 ms timer is still there as the late-report safety net it always was, but
it now re-arms the guarded path. The guard keys on `[width, height, devicePixelRatio]`,
because `renderer.resize()` re-resolves the ratio and a window dragged between
displays of different scale fires `resize` with an unchanged CSS viewport.

What it does **not** do: it does not shorten the flip stall, and is not claimed
to. The before/after medians move by less than the spread within either arm.

**A second scheduling change was tried, measured, and rejected**: deferring the
whole apply to the next animation frame, which is where the Target does its
equivalent work. It reached Target parity on listener cost (0.0 ms) and made the
product number worse on both arms. Both arms are published in
`orientation-truth.json` so the rejection can be checked rather than taken.

§三 allows exactly one scheduling correction. This is it.

---

## §八 — the frozen regressions, re-run on this build

    source contract        PASS  36/36 viewports
    layout source          v5:target-layout-source PASS  14/14
    typography contract    PASS  29/29
    source-exact runtime   PASS  64/64   (slot identity + wrap continuity across resize)
    resize-walk regression PASS  9 steps, 0 errors
    route check            PASS  shipped default / ?review=current / ?review=target
    console + page errors  0
    TypeScript             clean
    Vite build             clean

The resize-walk regression is new this round and exists because of the change
above: a bounds-equality guard's own failure mode is a viewport change it fails
to notice, and that needs a *sequence* of resizes to show up. It walks nine
steps — including a repeat of the same size, a one-pixel change, a flip and a
return — and after each one checks the layout frame against the window, slot
identity, the material cache and the runtime assertions. Exactly one apply per
distinct bounds, zero for repeats, no stale layout.

Glass identity, material-cache constancy, label culling, render culling and
media fit are frozen by §一.10 and were not re-run as standalone gates. That is
not asserted on the strength of a diff alone: the source contract, the runtime
gate and the typography contract all read the same engine state those gates read
and all pass on this build, and the resize walk checks the material cache
directly after every step. See `frozen-regressions.json`.

## §七 — bounded perf smoke

Ten minutes on the candidate: five desktop at full speed, five on a touch phone
context under a 4× CPU throttle, with portrait↔landscape rotations added to the
mobile phase this round. Clean on every check — no black card rect in any
sampled still, no cache growth or churn, no heap retention, all three quality
levels actually exercised, media advancing on both phases, zero errors.

A headless run under a CPU-only throttle is **not** a real-device pass and is not
reported as one. `perf-smoke.json`.

---

## Files

| file | what |
|---|---|
| `orientation-truth.json` | Phase A: the estimator arithmetic, the raw single-frame measurement at 5 runs a side, all ten scheduling arms, the shipped correction and the rejected one |
| `flick-truth.json` | Phase B: 10 runs a side, per-release records, the mechanism, the 8-item gate |
| `frozen-regressions.json` | §八, each gate traced to the artifact that produced it |
| `perf-smoke.json` | §七 |
| `product-state.json` | §十一: the state, the three declared residuals, the declared deviation |
| `MANIFEST.json` | per-file SHA-256, commits, head SHAs, delivery limits |

Target pixels appear nowhere in this tree. The stills and side-by-side
recordings are in `qa-v5/private/v5-final-motion.zip`, which is **not tracked by
git** — `qa-v5/private/` is in `.gitignore`, as it was for the previous round.

## Declared residuals

1. **The fast-flick second mode remains.** Both pages have it; the rates are
   indistinguishable at n=10; the mechanism is published. Not fixable without
   touching constants §四 forbids, and fixing it would diverge from the Target.
2. **The orientation flip still stalls the main thread** — roughly 40 ms against
   the Target's 10 ms. Attribution by layer suppression says it is the mounted
   CSS3D card layer: hiding it immediately before the flip drops the block to
   0.0 ms. We keep 256 card elements mounted (4155 DOM nodes); the Target keeps
   57 (1423). The fix is a mount-on-draw label policy, which is Culling and
   Typography — both frozen this round. Recommended for the next round.
   §十一's three permitted state strings have no slot for this one, so it is
   declared here rather than folded into the fling line.
3. **§三's pre-registered gate item reports FAIL** on its own arithmetic, and is
   published that way. The same arithmetic fails the Target by more.

## Declared deviation

§三 says a Phase A failure stops the round before Phase B. Phase B was run. The
letter-fail is item 4's arithmetic, and the same arithmetic fails the Target;
stopping on it would have buried this round's one substantive finding behind a
number that does not measure the page. Both readings are published, and the
pre-registered one was reported as it falls, not replaced.
