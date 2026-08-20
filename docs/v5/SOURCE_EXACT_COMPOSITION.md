# Source-exact composition (F2-SX)

Not another parameter fit. The Target's layout initialisation was recovered in
full during F2.7's authorised read-only forensics pass, so this stage
transcribes it and runs it, instead of regressing toward it.

Rollback is total: `?composition=v1` and `?composition=v2` are untouched and
render byte for byte as before, and the bare route still resolves to v1.

## One contract, read by everyone

`config/target-layout-source-v2.json` holds every Target constant exactly once.
`src/layout/SourceExactLayout.ts` and `scripts/v5/source_layout.py` both READ it;
neither keeps a copy. `src/scene/RowPhase.ts` and `scripts/v5/f27_target_model.py`,
which each used to carry their own hand-written duplicate, now read it too.

`npm run v5:target-layout-source` checks the contract is still true:

1. the Target's app bundle still hashes to the recorded SHA-256,
2. TypeScript, Python and the live Target DOM agree,
3. the contract hash reaches the running app.

It reads TypeScript **from the running app**, not by re-importing the module in
Node — re-importing verifies a copy, driving the app verifies what ships. On a
bundle-hash change it FAILS and asks for fresh forensics; it never edits the
contract and never relaxes a tolerance. The failure branch is exercised for real
(`--contract=` against a mutated file) and exits 1.

## The law

```
s            = max(width, height) / 1728
perspective  = 1200 * s
sphereRadius = 5000 * s
planeWidth   = width * (height > width ? 0.72 : 0.38)
planeHeight  = planeWidth / (4/3)
cellW        = planeWidth  * 1.045
cellH        = planeHeight * 1.045
cols, rows   = coverage bisection, clamped to [4,16], forced EVEN
```

Camera: `(0, 0, perspective)` looking at the origin,
`fov = 2*atan(height/2/perspective)`, near 0.1, far 10000, **no pitch**. One world
unit is therefore exactly one CSS pixel at z = 0 — measured through the live
camera as 1.0 with a delta of 0, where every earlier path carried a fixed 3.2e-5
residual from `CAMERA.y = 8`.

Placement is **one sphere**, not a cylinder plus a separate `radiusY`:

```
xArc = wrap((col - (cols-1)/2)*cellW + scrollX + (poolRow % 2)*cellW/2, cols*cellW)
yArc = wrap(-(poolRow - (rows-1)/2)*cellH - scrollY,                    rows*cellH)
normal   = (sin(θx)cos(θy), sin(θy), cos(θx)cos(θy))       θ = arc / sphereRadius
position = normal*sphereRadius - (0, 0, sphereRadius)
orientation = the quaternion taking local +Z to normal
```

There is no rest offset and no phase rule on this path. An even column count
already puts a seam on the centre line for even pool rows, so the phase is a
consequence of the geometry rather than a parameter laid on top of it.

## Card size and the pool

Card ASPECT is a constant 4/3, so only card SIZE moves with the viewport. The
glass volume is therefore built once at a reference 4:3 size and scaled
**uniformly** by `cardScale = planeWidth / (1728*0.38)` — the Target's own
`cardScale`, which it also applies to thickness and rim width. A uniform scale
leaves surface normals pointing where they did, so the frozen refraction is
untouched; a non-uniform one would not be. The foundation slab is a unit plane
scaled to `(planeWidth, planeHeight)`.

The pool is preallocated at **16 x 16 = 256** slots, the most the Target's clamp
can ever ask for. A resize changes `activeSlotCount` and the per-slot scales and
nothing else: no mesh is created or destroyed, no material is rebuilt, no
texture or video is touched. Clip binding is by slot and is set once at build,
so a resize cannot reload a video. Unlike the Target, which shuffles its clip
list with `Math.random()` on load, ours is deterministic and therefore
reproducible for QA.

Label data is bound to the POOL SLOT, as the Target binds it: `ILG code =
slotIndex + 1`, kept through wrapping and through every resize. No typography
style or parameter changed.

## Source-exact engineering gate — PASS 36/36

Three things had to agree at every one of the 36 captured viewports:

| | worst over 36 viewports | tolerance |
| --- | --- | --- |
| every active slot world position, engine vs model | **0.0** world | 0.1 |
| every active slot orientation, engine vs model | **1.21e-6** deg | 0.05 |
| projected card corners, engine vs model | **0.0** px | 0.5 |
| every visible Target card matched by an engine slot | **0.005366** world | 0.1 |
| perspective, sphereRadius, planeWidth/Height, cellW/H | exact | 0.01 |
| cols, rows, active slot count, phase, initial scroll | exact | — |

Model-vs-engine catches an implementation that drifted from the contract;
engine-vs-Target catches a contract transcribed wrongly. Neither alone is
enough, and comparing the model with itself proves nothing.

This is an **engineering** gate. Passing it does not assert a Target visual result.

## Pixel gate — 8/14 viewports, 115/122 checks

Thresholds unchanged. Target measured from 5-frame consensus.

Against the F2.7 candidate measured identically (7/14, 112/123), source-exact
gains 390x844, 700x700, 667x375, 360x800 and 500x900, and loses nothing that was
passing on merit. Card size, card centre, edge yaw, row parity, centre dark band,
overlap and large void now pass at **every** viewport.

Every remaining failure is **gutter centre** (3.5–6.5 px against a 3 px limit) at
1366x768, 1440x900, 1440x1080, 780x470, 960x500 and 960x720, plus one gutter
width at 780x470.

### That residual is the instrument, and it is measured

The source contract already shows the engine matches the Target's own DOM
geometry to 0.005 world units, so the geometry cannot be what is wrong. Two
independent measurements say what is:

**1. The detector disagrees with the Target about the Target.** Projecting the
Target's own DOM card corners through the Target's own camera and comparing them
with what the detector reads off the Target's own frame: card centres differ by
up to **2.67 px** and card widths by up to **71.89 px**, always reading smaller.
Nothing we render is involved in that comparison.

**2. Our frame reads CLOSER to the Target's true geometry than the Target's own
frame does.** At all nine viewports tested, the gutter centres detected on the
source-exact frame are at least as close to the Target's DOM ground truth as the
gutter centres detected on the Target's own frame — usually much closer
(1440x900: 11.88 px against 21.38 px; 667x375: 1.12 px against 23.50 px).

A flat opaque slab has a crisp edge. A video-filled glass card does not: its rim
refracts the background and its dark content reads as void, so the detector
places its edges a few pixels inside where they really are. `detector-residual.json`.

## Two harness defects found and fixed

**The void preset was chosen by an absolute pixel count.** `pick_void` selected
the navy preset only when a frame contained at least 20 000 void pixels — about
1.5% of a 1440x900 frame but 8% of a 667x375 one. 667x375 has 16 588 void pixels,
a perfectly normal 6.6% of the frame and 3 412 short of the threshold, so it fell
through to a black preset that matches nothing and the entire frame read as one
solid card: no gutters, no bands, nothing measurable. The test is now a fraction
of the frame. This had silently degraded every small-viewport measurement since
F0, and fixing it can only make more structure measurable — no gate threshold moved.

**The overlap check assumed a cylinder.** It treated any two overlapping
projected quads as a fault. On a sphere a lower row curves away and legitimately
passes *behind* the row above, so overlapping projections are correct. Measured
against the Target's own DOM geometry at 899x900, the only viewport in the sweep
where it happens: the Target produces 21 overlapping pairs and 3 same-depth
collisions; the engine produces 21 and 3. The assertion is now
Target-referenced — no collision the Target does not also have — and the strict
zero-overlap count is still reported beside it. `sphere-occlusion.json`.

## Runtime — PASS 64/64

Rest, a (260, 180) offset that is never reset, +/-100 cells, orientation flips,
the square boundary, resize during a drag, and every reachable pool-size
transition.

Pool coverage is derived from the model rather than guessed. Enumerated over
320..2600 in both axes, the Target's own formula only ever produces **rows in
{8, 10, 12, 14, 16}** and **cols in {8, 10}**: the `+ 4` floor plus the coverage
term never lands below 8, and cols is bounded because planeWidth is a fixed
fraction of viewport width. Counts of 4 and 6, and cols above 10, are therefore
**unreachable** and are reported as such rather than silently skipped. Every
reachable transition is exercised in both directions.

Across all of it: zero meshes created after the initial build, zero destroyed,
material, geometry, texture and video counts constant, no video reload, active
slot count always exactly `cols x rows`, slot identity intact, camera on axis at
the focal distance, one world unit one CSS pixel, never blank, no console or page
errors.

## Not shipped

`sourceExact` is not the default. The bare route resolves to v1 and renders the
accepted F0 baseline frame byte-identically; v2 renders the F2.7 gated frames
byte-identically at both 1440x900 and 390x844. `default-proof.json`.
