# Round 1 · V4 multi-card grid preview

## Gate state

Human Card Quad / Optical Zone annotation is **SKIPPED BY PRODUCT OWNER**. Some
target cards in the Frozen frames are incomplete or clipped, and a non-expert
annotation risks producing a wrong Target Truth that would pull later
optimisation in the wrong direction.

| Track | State |
| --- | --- |
| Engineering QA | Runs automatically, every round |
| Human annotation | SKIPPED BY PRODUCT OWNER |
| Formal Pixel Truth | BLOCKED |
| Final Target Match | BLOCKED |
| Product Visual Acceptance | Product owner, from real previews |
| Final merge to `main` | Requires explicit human approval |

Reviewer Mode and the Advanced Inspector are retained as an **Optional
Diagnostic Tool**. They no longer block visual preview development, they never
write the annotation contract on their own, and nothing in this round may be
read as a pixel-level replica claim.

Still forbidden: deleting V3, defaulting V4 on `main`, claiming a pixel-level
replica, claiming a formal Golden PASS, presenting a screenshot or a video as a
live result, and merging a release without a human preview.

## What Round 1 changes

| System | Change |
| --- | --- |
| Route | `/grid-lab-v4` — the real page with V4 optics plus a review console (`?hud=0` removes it) |
| Main page | `?optics=v4` boots the V4 preview; anything else, including no query, boots V3 |
| Optics | V4 refraction body + energy-controlled reflection shell on the real 9×9 brick grid |
| Scene colour | Linear half-float target with mipmaps, rendered with 1.3× overscan |
| Video | Uploads follow decoded video frames instead of render frames |
| Typography | Unchanged V3 CSS3D layer |
| Motion | Unchanged V3 controller |

Deliberately untouched in Round 1: typography metrics, motion constants,
instancing, ring buffer, adaptive quality thresholds, and the V3 runtime.

## Why the scene target is overscanned

A card at the frame border refracts up to `maxRefractionUv` of the frame. With a
screen-sized scene target that sample clamps to the border texel and smears the
last column of pixels along the edge. The target is therefore rendered through a
widened camera and the material maps screen space into it with `sceneUvScale`,
whose default of `1` leaves `/glass-lab-v4` bit-for-bit unchanged.

`clampHeadroom = 0.5 - sceneUvScale × (0.5 + maxRefractionUv + dispersionUv +
adaptivityRadiusUv)` must stay positive; at 1.3× overscan it is `+0.0115`, so
screen-UV clamping cannot happen at all. The Round 1 gate asserts this, and
asserts that the same arithmetic is negative without overscan.

## Automated engineering gate

`npm run v4:round1:gate` (real Chrome, hardware WebGPU):

V3 page still runs · V4 normal path never samples media directly · no fixed
black body rim · pointer changes the reflection · no full-screen dispersion ·
no border-pixel streak · resource counts stable across ~2100 pool remaps ·
video uploads are not per render frame · no sustained memory growth over 60 s ·
zero console errors · zero GPU validation errors · desktop and mobile both run ·
V4 can always fall back to V3.

The dispersion and body-rim checks read the material's own debug views, because
saturated video content is chromatic on its own and says nothing about the
optics.

## Human review package

`npm run v4:round1:capture` then `npm run v4:round1:sheets` write, under the
ignored `qa-v4/review/round-1/`:

* 15 fixed review states, captured for V3 and V4 at identical offset, pointer
  and clip time;
* desktop and mobile session videos driven by real pointer input;
* `contact-v3-v4-split.jpg` — every state, V3 left of the seam, V4 right;
* `contact-target-current.jpg` — Frozen target card crops above the current V4
  cards, labelled as a look reference and explicitly not a match score.

Drag and flick stills are reproduced by setting the same offset and velocity on
both versions rather than by replaying raw mouse input, so the split sheet never
compares two different scroll positions. Real input is exercised in the videos.

Which grid cell plays the bright / dark / high-texture / low-texture state is
measured from the real frames, not assumed.

## Next round

Round 2 (typography) may not start until the product owner has reviewed this
round's preview, contact sheets and session videos and returned natural-language
feedback.
