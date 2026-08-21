# V1 — source-exact WebGL render culling

The Target culls its WebGL card with the SAME coverage verdict that culls
its CSS3D label: `s.visible = o.draw`, one loop iteration, two surfaces.
V0 recorded that wiring and deliberately did not act on it. V1 read what
`s` actually is — a plain THREE.Mesh whose one node material carries the
refracted media, the environment reflection, the fresnel and the rim, with
no scene-colour pass, no reflection shell and no per-slot group — and
mapped the rule onto our render objects with the layered visibility this
round requires: no system writes `.visible` on a slot mesh directly; the
pipeline's per-pass flips, the QA layer requests, the shell and debug
modes, the active window and the coverage verdict each set a flag, and one
applier composes them.

The media plane is deliberately NOT coverage-culled: it is the input of
the scene-colour target — our architecture's equivalent of the Target's
per-card texture binds, which the Target does not cull either (its
refraction samples the card's OWN texture, so hiding a card never changes
another card's pixels; source-read). Coverage-culling the scene input
would break exactly that invariant, because edge glass samples the target
beyond the 64 px margin.

## Verdicts

| gate | result |
| --- | --- |
| Target source object mapping | **PASS** — 22 byte-anchored sites, live bundle byte-identical |
| Effective visibility vs rule replay | **PASS** — 20177 frames, 0 slot mismatches |
| Label / mesh agreement | **PASS** — 0 disagreeing frames (one verdict, two surfaces) |
| Strict-viewport completeness | **PASS** — 0 frames with a missing on-screen card |
| Pass-state integrity | **PASS** — 0 media leaks, 0 shell mismatches |
| Pixel invariance, culling A/B | **PASS** — 15 comparisons, worst 0 differing pixels (requirement: identical, no tolerance) |
| Pixel invariance vs V0 baseline | **PASS** — 15 comparisons, worst 0 differing pixels |
| Performance | **PASS** — see below |
| Label culling absolute gate (V0, re-run) | **PASS** — 20294 frames, 0 mismatches, identity 40/40 |
| Source contract | **PASS** — 36/36 viewports |
| Typography regression | **PASS** — 4/4 |
| Card / label under motion | **PASS** — 34 assertions |
| Motion freeze smoke | **PASS** — engine vs contract 15 rows / 0 failed, release history 11/11 exact |
| Console / page errors | **PASS** — 0 across the capture |

## Performance, measured

An A/B on ONE build: coverage culling ON (candidate) vs OFF (the accepted
pre-V1 behaviour — proven byte-identical to the V0 baseline by the pixel
gate). drag-10s at 1440x900:

| metric | culling off | culling on |
| --- | --- | --- |
| final-pass draw calls p95 | 39 | 35 |
| final-pass triangles p95 | reduction 10.5% | |
| scene-colour pass | unchanged: True (deliberately not culled) |
| glass meshes visible p95 | 100 | 17 |

GPU frame time: not instrumentable at this build: the renderer is created without timestamp tracking.

Heap over repeated 5-minute drag cycles:
- cycle 1: 16.35 -> 34.32 MB (delta 17.97 MB)
- cycle 2: 33.25 -> 38.67 MB (delta 5.42 MB)

Videos keep playing and advancing in both lanes; the adaptive quality
level did not move in either. Frame-time percentiles are statistically
identical — the page is GPU-bound and the win is submitted work (draw
calls and vertex load), stated as such.

## What the source settles

`target-render-culling-source.json` answers every object question with
byte offsets: `s` is created by the card field's JSX (`<mesh ref=...>`),
it is a THREE.Mesh with no children, its material is one
MeshBasicNodeMaterial per media clip, hiding it removes exactly one draw
call from the single forward pass, and nothing else exists — no
scene-colour pass, no reflection shell, no media plane, no layer-debug
mode. Mesh poses update every frame regardless of visibility (the
opposite of the label freeze, both now frozen behaviours).

## Files

| file | what |
| --- | --- |
| `target-render-culling-source.json` | the render-object source mapping, 22 sites |
| `render-culling-truth.json` | effective visibility vs rule replay, per frame |
| `pixel-invariance.json` | culling A/B + V0-baseline pixel comparisons |
| `performance.json` | A/B scenarios, heap cycles, media and adaptive state |
| `label-culling-regression.json` | the V0 label gate re-run at the V1 build |
| `source-contract.json` | the 36-viewport layout source contract |
| `typography-regression.json` | container alignment, label ink, depth carry-forward |
| `motion-regression.json` | motion freeze smoke + card/label corner delta |
