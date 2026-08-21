# Source-exact motion

The Target's motion was **read**, not fitted. Its application bundle carries the
whole model as literals, and the settings object those literals live in is a
React `useState` initial value whose setter is never called anywhere in the
bundle — there is no debug panel, no query-string override and no runtime
mutation path. So the constants below are the live values, and the live
measurements confirm it rather than establish it.

Everything is in [`config/target-motion-source-v1.json`](../../config/target-motion-source-v1.json),
read by [`SourceExactMotion.ts`](../../src/interaction/SourceExactMotion.ts) and by
[`source_motion.py`](../../scripts/v5/source_motion.py). Neither keeps its own copy.

## What the Target does

One full-viewport surface — `fixed inset-0 z-10 touch-none cursor-grab
active:cursor-grabbing` — with a framer-motion pan gesture on it, and a separate
`window` `pointermove` listener for the camera. That is the entire input
surface.

```
pan delta      ->  scrollTarget += 1.5 * delta          (both axes, both positive)
release        ->  scrollTarget += releaseVelocity * 0.1
scroll          =  spring(100, 16, 0.5)  chasing that target
|velocity|      =  spring(140, 24, 0.6)  chasing hypot(scroll spring velocities)
pointer         =  spring(80, 18, 0.8)   chasing clamp(client / size * 2 - 1)

camera          =  orbit at radius `perspective`, yaw = -0.05 * pointerX,
                   pitch = 0.05 * pointerY
camera z       += 3 * maxZoomZ * tanh(0.04 * |velocity| / (3 * maxZoomZ))
                   (both cameras: the render camera and the CSS3D camera)
```

All three springs are overdamped — damping ratios 1.131, 1.309, 1.125 — so
nothing overshoots. The springs are the whole dynamics: there is no inertia
integrator, no decay constant, no maximum speed and no stop threshold beyond
the spring's own rest test.

## What the Target does not do

Recorded as findings, because each of them is a thing our previous model had:

| absent from the Target | ours had |
| --- | --- |
| any wheel or trackpad handling | `wheelGain: 0.055`, wheel adding directly to velocity |
| a maximum velocity clamp | `maxSpeed: 1800` |
| a stop threshold | `stopThreshold: 70` |
| an exponential inertia decay | `damping: 11`, `exp(-damping * dt)` |
| a pointer-driven card tilt | `tiltDeg: 1.05` |
| a pointer-driven camera translation | `parallax: 0.016` |
| a pointer-driven light | `lightTravel: 120` |
| pointer capture on the drag surface | `canvas.setPointerCapture` |

The wheel finding is the strongest of them: the only `addEventListener("wheel")`
in the Target's entire bundle is inside three.js `OrbitControls`, which it never
mounts. Wheel and trackpad move the Target by exactly nothing, at any
`deltaMode`, and the live traces show a flat scroll trace under both a real
mouse wheel and synthetic `deltaMode` 1 and 2 events.

The light finding is nearly as strong: the Target's scene graph contains only
`group` and `mesh` — no light object of any kind. Its highlight moves because
the **camera orbits** against a fixed studio environment map. So there is no
pointer-to-light gain to reproduce, and the source-exact value is zero travel.
Our rig's own intensity, colour and base position are untouched; only what
drives it changed.

## Three details that are easy to miss and change the feel

**The gesture does not start until the pointer has moved 3 px**, and nothing is
pushed to the gesture history before that. So the first delta that does fire
carries the whole pre-threshold movement, and a tap moves nothing at all.

**The dispatch is scheduled with `keepAlive`, so it re-runs every frame** for as
long as the gesture is alive — not only on frames that carried a move. A
stationary finger keeps pushing the same point into the history with a fresh
timestamp, so after about 100 ms of stillness the velocity window holds only
identical points and the measured velocity is zero. **Hold still before letting
go and there is no fling at all.** This one is worth stating plainly because it
is invisible in the constants and obvious in the hand.

**The velocity is measured over the history *before* the current point is
pushed**, so it lags by one dispatch. The fling multiplies it, so the lag is
visible in where a flick lands.

## The camera that turned out to be one camera

This was read wrong, and the Target's own recording caught it.

The reading was: the render camera gets the velocity dolly on z, and a second
camera at the same orbit position **without** the dolly does the CSS3D
transform, so under fast motion the glass dollies and the labels do not — they
separate, on purpose. A whole gate was built on it: measure the label against
the *un-dollied* card plane, and assert that the two cameras separate.

The Target's own CSS3D camera matrix refutes it. Solve the camera's world
position out of the recorded inverse matrix and take its distance from the
origin, at 1440×900:

| sequence | camera distance from origin |
| --- | --- |
| at rest | exactly 1000.000 |
| pointer sweep, whole run | exactly 1000.000 |
| fast flick | 1000.000 → **1158.13** |
| long drag across wraps | 1000.000 → **1223.01** |

A dolly-free CSS3D camera cannot do that. And the pointer sweep is the control:
it moves the camera all over the orbit and never moves the page, so it produces
no velocity and no dolly — and the distance never leaves 1000.000. What varies
is velocity, not pointer.

So the Target's CSS3D camera carries the dolly, and there is no separation to
allow for. The dolly-free camera in the bundle drives projection and culling,
not the transform. Ours now carries it too, the gate in
[`m1-card-label-motion.mjs`](../../scripts/v5/m1-card-label-motion.mjs)
measures the label against the card plane through the camera that paints both,
and the assertion is inverted: the two cameras must **agree** at every frame,
with the peak gap reported so a regression to two cameras cannot pass quietly.

The dolly is zero at rest, which is where the layout contract measures, so the
source contract is untouched either way.

## How the model was checked

Not by eye, and not by fitting. The check drives the model with the **Target's
own recorded input events** and compares the predicted scroll trajectory against
the trajectory recovered from the Target's own card matrices, frame by frame.

The Target's scroll lives in closed-over motion values that no page script can
reach, but every card's world position is an exact function of it:

```
normal   = (sin tx cos ty, sin ty, cos tx cos ty)
position = normal * R - (0, 0, R)
```

so `ty = asin(y / R)` and `tx = atan2(x / R, (z + R) / R)` recover the arc
coordinates from a recorded matrix, and the per-frame change in arc — median
over the live cards, modulo the wrap period — is the per-frame change in scroll.
Cards the page has culled are excluded: their matrices are stale rather than
stationary, and a median taken over the whole pool is a median over frozen
cards.

Thresholds come from the Target's spread against **itself**: the same trajectory
is run three times and the pointwise spread of those runs is what the model
residual is judged against. The repeatability is computed and written before any
model residual is looked at.

## The frame the Target is behind

The single largest correction this stage. A first implementation painted the
model's *current* frame; the Target paints its model's *previous* one.

In the bundle, framer-motion runs its own frame loop, and that loop is started
lazily — by the first `schedule()` call, which does not happen until the first
gesture arrives. The renderer that consumes the motion values was registered
when the canvas mounted, long before. Two `requestAnimationFrame` callbacks,
consumer first: what reaches the screen is always one frame old.

It was not found by reading, though. It was found by measuring, and the reading
came after. The gate's own `latencyMs` row showed our page starting to move
**7.75 ms sooner than the Target**, as a mean over forty viewport-sequence
pairs, negative in every single one, while the Target's own repeatability on
that landmark is 0.1–1.4 ms. Both pages run at ~120 Hz, so 7.75 ms is one
frame — and the floor for that row was written as "two frames at 60 Hz", which
is four frames at the rate the pages actually run. A perfectly systematic
one-frame difference sailed through forty rows.

The M0 acceptance had the same blind spot from the other side: it accepted the
model on the **time-aligned** peak error, and the shift it aligned away was
+10.5 ms — positive for every one of the ten sequences. A number that is
systematic in sign across every sequence is not phase noise.

Replaying the model against the Target's own recorded trajectory, 120 non-wheel
runs at four viewports, at zero, one and two frames of output delay:

| output delay | median raw peak error, as a fraction of travel | median best-fit time shift |
| --- | --- | --- |
| 0 frames | 3.36% | +10.5 ms |
| **1 frame** | **0.76%** | **+2.0 ms** |
| 2 frames | 2.16% | −6.0 ms |

One frame wins on every sequence; two frames overshoots on every sequence. It is
one structural change with a discrete answer, not a fitted constant — there was
nothing to tune.

Recorded in the contract as `renderDelay`, implemented as
`SourceExactMotion.beginFrame()` in both twins: the pose applied on a frame is
the snapshot taken before that frame's input was processed. A QA jump
(`setScroll`, `jumpPointer`) re-snapshots immediately, because a fixed state is
not a frame of motion and a paused page never takes the next one.

## Two things a bundle read cannot settle

**How fast the pointer smoothing is.** The orbit amplitude and the smoothing
constant are different facts, and the amplitude row passes for a page that
reaches the same extremes at a completely different speed. The Target's sweep
moves the mouse to a corner in a burst of moves that all land inside one frame
and then holds for half a second, so to the page each corner is close to a
*step*. The settle time is read off the camera yaw — the same instrument on
both sides, since the Target exposes nothing — as the time to cover 63.2% of it.
The Target's own answer is 183.8 ms, repeatable to a few ms across four
viewports.

That is *not* the analytic step response, and an earlier draft of this file said
it was. For stiffness 80, damping 18, mass 0.8 the ideal step from rest reaches
63.2% at **234.7 ms**; 180.1 ms is the 50% time, which is the number that got
mislabelled. The measured 183.8 ms is shorter than the ideal because the sweep
is not an instantaneous step — the sixteen sub-moves take time and the spring is
already chasing during them. The landmark compares two pages under the *same*
stimulus; it is not a check against an ideal, and it should not be read as one.

The landmark is also confined to the sweep. On a drag the pointer travels as a
continuous ramp, the burst detector finds a "step" that is really the whole
drag, and the number it returns is not a time constant — one and the same spring
came back as 0.70 ms on one sequence and 297 ms on another. Restricting it would
have dropped coverage, so it did not go alone: `pointerModelResidualRad` drives
the contract's pointer spring with each side's own recorded pointermove stream
and compares the predicted yaw against the yaw recovered from that side's own
camera. It asks the same question without needing a step, so every drag, flick
and sweep answers it.

The orbit angles behind both are recovered from the camera's **position** with
the dolly solved out, not from its forward axis. The dolly is added to the
camera's world z and the camera then looks at the origin, so with an off-centre
pointer and a moving page the forward axis is tilted by the dolly — which is
most of the drag sequences. On a sweep, where nothing moves, the two readings
agree exactly.

**Where the highlight goes.** The Target has no light object, so the highlight
moves only because the camera orbits against a fixed environment — that is a
scene-graph fact from the bundle, and the orbit itself is measured on both sides
from the CSS3D camera matrix. The highlight *pixels* are measured too, but the
honest version is narrower than it looks: our page freezes its media for a fixed
state and the Target's video cannot be turned off, so a whole-frame luminance
centroid has moving video in it on one side only. The candidate rows are gated
on a sweep taken with the media layer off, where the highlight is the only bright
thing in frame; the cross-side correlation is reported and not gated, and how far
the highlight travels and how bright it is are left to the optics stage, which
has not run.

## The difference that is left, and what it is

The gate fails, and after four engine fixes what remains is one thing wearing
three hats.

**The Target's motion is jittery frame to frame and ours is smooth.** Measured
as each frame's step against the average of its two neighbours — so the decay
envelope cancels and only the frame-to-frame irregularity is left — at
1440×900:

| sequence | Target | ours | ratio |
| --- | --- | --- | --- |
| slow horizontal drag | 0.1424 | 0.0189 | 7.5× |
| medium drag | 0.1286 | 0.0191 | 6.7× |
| diagonal drag | 0.1318 | 0.0184 | 7.2× |
| fast flick | 0.1325 | 0.0136 | 9.8× |
| reverse flick | 0.1251 | 0.0149 | 8.4× |
| long drag across wraps | 0.1143 | 0.0166 | 6.9× |
| touch drag + release | 0.1009 | 0.0182 | 5.5× |
| pointercancel | 0.1054 | 0.0213 | 4.9× |
| **median** | **0.127** | **0.018** | **6.9×** |

The Target's scroll advances by 12.7% more or less than its local trend on a
typical frame; ours advances by 1.8%. It is not measurement noise: the
per-frame agreement *between cards* is 0.001–0.011 world units on both sides,
and our own recovery was checked against the engine's own scroll to 0.025.
Both pages are steady at ~8.3 ms per frame.

The mechanism is the same one that produced the one-frame delay. The Target
computes in framer-motion's frame loop and paints in r3f's — two independent
rAF callbacks. A frame on which framer did not tick between two r3f paints
repaints the same value, and the next frame carries double. We compute and
paint in one callback, so our steps are even.

It shows up as three failing families, and they are the same fact three times:

- `frameStepJitterFraction` — 27 rows, ours lower in **26 of 26**;
- `maxFrameVelocityStep` — 8 rows, ours lower in **7 of 7**. Jitter is what a
  frame-to-frame velocity step *is*;
- `cameraDistanceOverPerspectivePeak` — 17 rows. **This attribution was wrong
  and is corrected below.** It is not jitter. It was the magnitude
  MotionValue's two writers, and which of them the frame lets write last.

The `systematicSign` row catches all three by sign alone, which is what it was
added for.

Reproducing it would mean reproducing a scheduling race rather than a motion
constant — running our own model and our own paint in two rAF callbacks and
letting the interleaving fall where it may. That is a product decision about
how far "source-exact" reaches, not an engineering one, and it is not taken
here.

## The magnitude has TWO writers, and the frame decides between them

The value the camera dolly is driven from, `g` in the bundle, is written from
two places:

```js
// the gesture, in onPan and onPanEnd
g.set(Math.hypot(t.velocity.x, t.velocity.y))

// the scroll springs, in their own change handlers
g.set(Math.hypot(f.getVelocity(), p.getVelocity()))
```

They are not two estimates of one quantity. The first is the FINGER's velocity,
straight out of PanSession's 100 ms history window. The second is the SPRING's
— `MotionValue.getVelocity()`, a one-frame backward difference of the spring's
own output — which while a finger is down is the finger's velocity times the
1.5 drag gain, minus the spring's lag. They differ by about the drag gain, and
whichever writes last in a frame is the one the magnitude spring retargets to
at that frame's `postRender`.

Two lines of the bundle settle which:

```js
let Sy = e => (t,r) => { e && mH.update(() => e(t,r), !1, !0) }
```

Every pan handler is wrapped in this. The third argument is `immediate`, and
with the step already being processed it adds the callback to the Set that is
being iterated *right now* — `Set.forEach` visits entries added during
iteration. So the application's `onPan` runs after every callback already
queued in the update step, including all three spring ticks, whatever order
they were registered in. And:

```js
onEnd: (e,t) => { delete this.session; i && mH.postRender(() => i(e,t)) }
```

`onPanEnd` is not wrapped. It is scheduled straight onto `postRender` from
inside the pointerup listener, which runs in the input-dispatch phase — so it
is the first entry in that frame's postRender set, ahead of the spring's own
retarget in the same pass.

**The gesture writer wins every frame that carries a pan dispatch, and the
release frame. The scroll writer stands alone on every frame that carries
neither**, which is every frame after the release.

That is what the dolly residual was. It was never a scale factor: it changed
SIGN with the phase of the gesture. The Target dollied *less* than the frozen
law during a drag (0.80 on the slow drags) and *more* during a fling (1.17 to
1.20). Two writers that disagree by the drag gain, with the gesture one winning
while the finger is down, is exactly that shape — and it is what a constant
fitted to the residual could never be, because such a constant would be wrong
in both phases at once.

Replayed on the Target's own recorded input over 124 runs, changing nothing but
which writer the magnitude spring retargets to:

| order | signed median ratio | median absolute residual |
|---|---|---|
| scroll writer last, always | 0.955 (−4.5%) | 17.7% |
| gesture writer last while the gesture is alive | 0.984 (−1.6%) | 1.6% |

Both numbers are quoted because they say different things. The signed ratio is
much the smaller of the two under the old order **because the drag and flick
residuals had opposite signs and cancelled**; quoting only −4.5% understates
what any single sequence showed.

The derivation, with twenty byte offsets into the bundle and the verbatim text
at each, is in `qa-v5/motion-final/magnitude-writer-order-source.json`.

### What that also implies, and what was not done about it

`onPanEnd` running at `postRender` means its `d.set(target + velocity * 0.1)`
schedules the SCROLL retarget into the *next* frame's postRender, one frame
later than a drag frame does. That is a real asymmetry in the scroll path, read
from the same two lines. It is recorded and NOT implemented: the product
re-authorised two scheduling semantics for this round — the release history
window and the magnitude writer order — and this is neither.

## The release velocity is quantised, and the Target disagrees with itself

framer-motion measures the release velocity over a window it defines with a
strict `>`:

```
while (i >= 0) { p = history[i]; if (timestamp - p.timestamp > 100) break; i-- }
```

The gesture history is fed from the frame callback, so its points are one frame
apart. A release therefore measures over either N or N+1 of them, and the span
of the window it actually used is either about 100.1 ms or about 108.3 ms —
never a value in between. One extra 8.3 ms sample inside a 100 ms window moves
the computed velocity by roughly 8%, and which side a release lands on is
decided by sub-millisecond dispatch timing that nothing in either page controls.

This is not a statement about our engine. **The Target's own three repeats of
the same scripted gesture land on opposite sides of that boundary in 33 of its
44 cells — 75% — with a median repeat-to-repeat release-velocity spread of 7.78%
and a maximum of 8.81%.** The gesture is identical each time; the answer is not.

It was found while checking whether one candidate capture was noisier than
another. On the fast gestures, where the releases live, it was not: those two
captures have identical move counts, identical median inter-event intervals to
0.05 ms, and identical frame cadence. (The slow multi-step drags are a separate
and real difference — one capture dispatches them 3.4 ms slower per step, which
accumulates into a gesture 103 ms longer. That does not touch the release
velocity; it moves the dolly peak TIME, and it is the whole of what is left
failing in the dolly.) Their
per-run release velocities agree to 0.00% on every run where both landed on the
same side of the boundary, and differ by 6.7% to 7.6% on every run where they
did not. There is no continuum between those two populations, which is what
rules out noise and identifies a quantum.

Three consequences, all of them recorded rather than acted on:

- The release-velocity landmark family carries an irreducible one-sample
  quantum. No implementation of this contract can close it, because the source
  of it disagrees with itself by the same amount.
- A candidate-vs-Target difference on those landmarks is only meaningful above
  that quantum. Below it, it is the boundary, and the frozen attribution sends
  it to `TARGET_INPUT_VARIATION` on the strength of the input-stream residual
  rather than on this argument.
- Nothing was added to the gate to make it boundary-aware. Discovering a
  quantisation and then teaching the scorer to forgive it is the same move as
  fitting, one step removed.

`qa-v5/motion-final/capture-acceptance-rule.json` carries the three falsification
tests — event stream, raw clock, release record — that got here, in the order
they were run.

## A defect found in a frozen file, and left alone

Motion made it visible, so it is recorded here rather than left for someone to
rediscover.

Our page keeps roughly **81 label elements un-hidden per frame** at 1440×900
where the Target keeps about **16**. The reason is that `TileLabelLayer` has
exactly one visibility rule — a back-face test, `_toCam.dot(_dir) > 0` — while
the Target culls on screen coverage. Its rule is spelled out corner by corner in
the bundle: project the card's four quad corners through the **dolly-free**
camera, discard any corner outside `-1 < z < 1`, reject the card if the screen
AABB area is ≤ 1, and draw only if that AABB overlaps the viewport inflated by
**64 px**. It computes a second flag in the same pass — a strict-viewport
overlap requiring at least half the AABB area — which we do not compute at all.

This is not a motion defect and it is not fixed here. `TileLabelLayer` is
frozen by the product decision that opened this stage, and the right response to
finding a defect in a frozen file is to say so, not to reach into it. Two
consequences are worth stating plainly, because both touch this stage's numbers:

- a five-fold difference in how many DOM elements have their transform written
  and their style recomputed every frame, on exactly the frames whose timing
  this gate measures;
- the world-unit wrap check counted "un-hidden" cards, and un-hidden means
  something different on the two pages — which is part of why it read 309 on
  our side and 14 on the Target's before it was replaced by the screen-space
  test.

## Resize

The Target's scroll, velocity and pointer are module-scope motion values that
nothing ever resets. A resize recomputes the layout frame only; the first layout
runs immediately and every later one is debounced by 150 ms before the column
count, the row count and the slot count change. Motion state therefore survives
a resize, including a resize taken mid-flick.

## Out of scope, recorded anyway

A one-shot intro spring — stiffness 100, damping 18, mass 0.7, restDelta 2e-4 —
animates the grid gap ratio from 3 down to the contract value once the scene is
ready. It is a load-in animation rather than motion input, and it is recorded
here only because it is a spring in the same settings file and would otherwise
look like a missing constant.

The Target also publishes its raw per-axis gesture velocities to two motion
values that nothing in the bundle ever reads. Only the smoothed magnitude is
consumed, by the dolly.
