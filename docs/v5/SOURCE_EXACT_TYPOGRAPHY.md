# SourceExact Typography

Status: **TYPOGRAPHY CANDIDATE — awaiting product review.** Nothing here is
accepted. Motion, optics, media focus and the frozen layout contract are
untouched.

## What was wrong

`TileLabelLayer` sized every label element to `TILE.width` x `TILE.height` --
539.8 x 399.6 px, fixed -- while the source-exact card is `frame.planeWidth` x
`frame.planeHeight`, which moves with the viewport. Every type size in the card
is a container query (`cqw`) against that element, so the whole type scale was
measured against a card that did not exist:

| viewport | card plane | label box | error |
| --- | --- | --- | --- |
| 1440x900 | 547.2 | 539.8 | −1.4% |
| 1920x1080 | 729.6 | 539.8 | −26.0% |
| 780x470 | 296.4 | 539.8 | +82.1% |
| 844x390 | 320.7 | 539.8 | +68.3% |
| 390x844 | 280.8 | 539.8 | +92.2% |
| 700x700 | 266.0 | 539.8 | +102.9% |
| 667x375 | 253.5 | 539.8 | +113.0% |

1440x900 is the viewport the type layer was tuned at. That is why the defect
was invisible for as long as it was.

## What the Target actually does

Read from the Target's own DOM at seven viewports, with the same reader pointed
at both pages (`scripts/v5/t1-target-typography.mjs`). Full contract, property
by property, in `qa-v5/t1/target-typography-contract.json`.

**Container.** The label element's computed width equals the card plane width
exactly at every viewport, and the basis columns of its `matrix3d` are unit
length -- so the CSS3D object scale is 1 and the ELEMENT is the thing that
resizes. Scheme A, decided by measurement rather than preference. Our boxes now
agree with the Target's to the digit: 547.188x410.391, 729.594x547.188,
280.797x210.594, 320.719x240.531, 266x199.5, 253.453x190.094, 296.391x222.297.

**Text plane depth.** Zero. Every Target label sits exactly on the sphere: the
radial distance from the sphere centre to the label's own world position is R to
within 1.2e-3 world units across 36 viewports, with no constant residual and no
term scaling with the responsive factor. Our `TYPE_Z` was
`TILE.thickness/2 + frontBulge + 6` = 49 world units of push-out along the
normal, invented rather than measured. The source-exact path now uses 0; the
legacy paths keep 49.

**Type scale.** One container-query scale, no responsive branch. All seven
viewports agree to the digit:

| property | Target | was ours |
| --- | --- | --- |
| card padding | 7cqw, all four sides | 8% 8% 11% |
| meta size / line-height / tracking | 1.7cqw / 1.5 / 0.18em | 1.7cqw / default / 0.18em |
| meta weight, family | 500, Geist Mono | 500, Geist Mono |
| category opacity | 0.75 | none |
| right meta group opacity | 0.65 | none |
| meta group gaps | 2.8cqw left, 1.2cqw right | 12px |
| dot separator | 0.4cqw round, currentColor | absent |
| title size / line-height | 12cqw / 0.82 | 9.2cqw / 0.84 |
| title weight / tracking | 600 / −0.085em | 600 / −0.085em |
| title max-width | 92% | none |
| title text-wrap | `wrap` | `balance` |
| rule | 0.2cqw tall, white/55, **above the title**, 3.3cqw below it | below the title, 10px |
| deck size / line-height | 2.5cqw / 1.25 | 2.5cqw / normal |
| deck weight / tracking | 500 / −0.01em | 400 / none |
| deck max-width | 58cqw | none |
| deck row margin-top | 3.5cqw | none |
| clip | one absolute layer at the card box, `overflow: hidden` | none |
| card backface-visibility | hidden | hidden |
| card transform-style | preserve-3d | flat |

The rule ordering is a structural difference, not a spacing one: the Target's
markup is rule, then title, then deck.

## What changed

Only `TileLabelLayer`, the card markup it writes, the typography CSS and the
footer caption. The new CSS is scoped to `.tile-card-se`, so compositions v1 and
v2 keep the rules they were accepted with.

* the label element is sized from `SourceExactLayoutFrame`, and `setFrame`
  re-points the whole layer on resize -- no element is recreated, nothing
  rebinds, and the ILG code stays on its pool slot;
* `TYPE_Z_SOURCE_EXACT = 0`;
* the card tree mirrors the Target's: clip layer, content layer at 7cqw, meta
  row, then rule / title / deck;
* `data-slot` and `data-ilg` on each element, because `innerText` is
  render-aware and comes back empty for a hidden label, so anything reading
  identity out of the DOM needs a marker that survives being invisible;
* footer caption to the Target's measured values -- Geist Mono, weight 500,
  `clamp(0.58rem, 0.8vw, 0.72rem)`, tracking 0.18em, uppercase, white at 70%.
  It was 16px Geist at full opacity.

## Not changed, and why

The Target's footer has a `h-36` black-to-transparent scrim behind it. That is a
background treatment, not typography, and this stage is scoped to typography, so
it is recorded here and left alone. Our wordmark is our own mark, not a Target
value; only its size was brought into the caption's band.

## Evidence

| file | what it settles |
| --- | --- |
| `qa-v5/t1/target-typography-contract.json` | PASS 29/29. Every measured Target property, per viewport, against ours |
| `qa-v5/t1/container-alignment.json` | PASS 47/47. Worst label corner error 0.011 px against the card mid-plane |
| `qa-v5/t1/depth-clipping.json` | PASS 30/30. Clip structure, title collisions, depth order |
| `qa-v5/t1/label-ink.json` | PASS. Zero label ink outside the card silhouettes at seven viewports |
| `qa-v5/t1/quality-invariance.json` | A quality step moves neither the mesh nor the type |
| `qa-v5/t1/render-loop-proof.json` | The T0 fix the rest of this evidence depends on |
