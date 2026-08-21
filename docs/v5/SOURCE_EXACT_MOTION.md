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
render camera z += 3 * maxZoomZ * tanh(0.04 * |velocity| / (3 * maxZoomZ))
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

## The two cameras

The Target builds its camera pose once and uses it twice. The render camera
gets the velocity dolly on z; a second camera at the same orbit position
**without** the dolly does the CSS3D transform, the projection and the culling.

So during fast motion the Target's glass dollies and its labels do not: the two
separate, on purpose. A reproduction that dollied the label camera as well
would be wrong, and a gate that measured label rects against the dollied glass
silhouette would fail a faithful reproduction *for being faithful*. The
invariant the Target maintains is label-to-card-plane through the label camera,
and that is what
[`m1-card-label-motion.mjs`](../../scripts/v5/m1-card-label-motion.mjs) gates —
with the separation itself recorded beside it as contract behaviour.

Both cameras are identical at rest, which is where the layout contract measures,
so the source contract is untouched.

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
