# 03 — Motion model

Milestone 2. Layout from Milestone 1 is unchanged. Glass shaders stay off.

## Architecture

Every input writes **targets** only:

| Input | Writes |
| --- | --- |
| Pointer move | `pointerTargetX/Y` in NDC |
| Pointer drag | queued `dx/dy` + sample `dt` |
| Wheel / trackpad | queued `deltaX/Y` |
| `setPointer` / `setOffset` / `reset` | QA targets |
| Resize | cached view size for NDC |
| Visibility | pause the integrator clock |

The RAF `MotionController.step(dt)` is the only writer of:

- `scrollX/Y` and `velocityX/Y`
- eased `pointerX/Y`
- `rotX/Y`, `camX/Y`, key-light XY

Banned: pointermove writing mesh/camera transforms, a second RAF, React state, layout reads in the tick, competing tweens, per-tile wobble.

Mouse listeners are gone. Pointer Events cover mouse and touch.

## Pointer space

Top-left `(-1,-1)`, center `(0,0)`, bottom-right `(1,1)`:

```
x = clientX / width * 2 - 1
y = clientY / height * 2 - 1
```

Hover does **not** translate the grid. Origin rest vs mouse-at-center has no scroll; only tilt / parallax / light.

## Four layers

1. **Grid translation** — drag and inertia, same gain as M1 (`dragGain 0.8`).
2. **Root tilt** — `rotX = pointerY * 2.6°`, `rotY = -pointerX * 2.6°` on `grid.root`. The pointed-at side comes closer. No per-tile extra rotation.
3. **Camera XY parallax** — `4.5%` of `cellW/H`. Camera stays at `z = 1000` and looks along `-Z` (`lookAt(camX, lookY+camY, 0)`), so the offset is a shift, not an orbit around the origin.
4. **Key light** — rest `(-420, 720, 1100)`, slides with pointer so highlights travel. View-dependent glass is Milestone 3.

## Integrator

- During drag, queued deltas apply in the same RAF. Follow stays tight; the event stream is not the integrator.
- After release, `v *= exp(-2.15 * dt)`. Half-life ≈ 322 ms. Coast ≈ 1.0–1.5 s. No snap, no reverse.
- Pointer ease: `k = 1 - exp(-6 * dt)`. About 90% in ~380 ms, inside the 250–700 ms settle window. No hard stop.
- Wheel is queued and applied in the same step (`wheelGain 0.22`).
- `dt` is clamped to 50 ms. Speed is clamped to `4200`.

## QA

`__LIQUID_GLASS_QA__` / `__ILG_QA__`:

- `setPointer(x, y)` sets the NDC target.
- `getState()` reports `pointer*`, `rotX/Y`, `camX/Y`, `milestone: 2`.
- Landmarks project **world** positions so tilt is visible to tests.

## Pass bars

Same recorded pointer script vs origin when a paired capture exists:

| Metric | Bar |
| --- | --- |
| Final displacement | ≤ 5% |
| Tilt amplitude | ≤ 10% |
| Settle time | ≤ 15% |
| Half-life | ≤ 10% |
| Shape | no reverse / step / instant dump |
