# F2.7 — initial row phase and portrait vertical axis

Two model problems, one authorised round. What actually happened is that the
authorised read-only source forensics pass succeeded completely, so both
problems were answered from the Target's own arithmetic instead of from another
regression. See [`TARGET_RESPONSIVE_SOURCE_FORENSICS.md`](TARGET_RESPONSIVE_SOURCE_FORENSICS.md).

## A — initial row phase

### The quantity the brief asked me to recover does not exist

The brief asked for `initialScrollY`, an integer row branch, `originJ` and a
phase unwrapping across a viewport sweep. Measured against the Target's own
world transforms at 36 viewports: **the residual phase is zero everywhere**
(worst 0.0007 world units), so `originJ` is 0 and the k = 0 branch is the
continuous one at every viewport. Zero discontinuities along the brief's sweep.
Source confirms why: both of the Target's scroll springs are constructed at
zero and nothing seeds them.

### What actually carries the phase

The Target sizes its card pool from a coverage calculation and **forces both
counts even**. An even row count puts the viewport centre between two pool rows,
so the row just below the centre is `rows / 2`. Odd pool rows carry the half-cell
brick offset. That parity is the whole law.

```
restOffsetX = (targetRows(viewport) / 2) % 2 === 0 ? cellW / 2 : 0
```

No threshold, no breakpoint, no fitted constant. `src/scene/RowPhase.ts`
computes `targetRows` exactly as the Target does.

**Verified 36/36** against live DOM state at 36 distinct viewports, with a
lattice residual of 0.005 world units and a perspective agreement of 0.0004 px.

### Determinism

12 viewports x 5 cold loads, fresh browser context each time. Phase, visible
catalog codes, row lattice and focal length are **stable across every cold load**
(`target-phase-determinism.json`). The one non-deterministic thing in the Target
is which video lands in which cell — its clip list is shuffled with
`Math.random()` on load. Geometry is not random. That is exactly why multi-frame
consensus masking is needed on the Target side.

### Correction to the brief's premise

The brief named four phase mismatches: 667x375, 700x700, 780x470, 1440x1080.
**Three of them were not mismatches.** At 667x375, 780x470 and 1440x1080 the old
aspect rule and the new row-origin rule give the *same* answer, and the Target
agrees with both. Those three were a pixel-classifier error in F2.6, not a phase
disagreement, and the before/after frames for them are identical by construction.

Genuine disagreements between the two rules, all resolved in the row-origin
rule's favour: **700x700, 900x899, 700x900, 320x900**.

At 700x700 the effect is large and visible: card centres were 9.171% of viewport
out and three rows had the wrong parity. Both are gone.

1440x900 is unchanged under the new law (rows = 10, no shift), so the accepted
F0 baseline is preserved — verified by a **byte-identical PNG**.

## B — portrait-only vertical axis

Horizontal scale is frozen this round, so the only lever is vertical.

| model | what it is |
| --- | --- |
| V0 | control: P1 exactly as it ships |
| V1 | V0 + one shared vertical scale, `scaleY = 1.03883` |
| V2 | V1 + portrait row origin `restY0 = -cellH/2` |

`scaleY` is applied **in the projection**, not as a scene-root scale: focal
length x k with aspect x k scales Y alone and leaves X untouched. A non-uniform
root scale would perturb vertex normals, and the refraction reading them is
frozen. `runtimeTruth()` proves it by projecting a vertical world segment
through the live camera.

### How the constant was obtained

Median of the required ratio over five training viewports, measured with the
gate's own detector against a five-frame Target consensus. Card **width** was
never used: a card off the centre line is yawed, and yaw foreshortens width but
not height, so width would push a phase effect into a vertical parameter.

An entirely independent route agrees. Source forensics gives the Target's
portrait card height exactly — `0.72 * width / (4/3)` — and dividing it by what
our frozen geometry renders gives **1.03923**, which is 0.04% from the fitted
1.03883. Two instruments, one number.

### Result

Card height error, `V0 -> V1 -> V2`:

| viewport | role | V0 | V1 | V2 |
| --- | --- | --- | --- | --- |
| 390x844 | **hold-out** | 4.79% | 1.03% | 1.57% |
| 360x800 | train | 3.59% | 0.58% | 0.06% |
| 414x896 | train | 4.82% | 1.28% | 1.78% |
| 430x932 | train | 4.88% | 1.47% | 1.96% |
| 500x900 | train | 1.66% | 2.14% | 2.14% |
| 375x812 | validate | 5.07% | 1.16% | 1.71% |
| 393x852 | validate | 5.09% | 1.36% | 1.89% |
| 428x926 | validate | 2.80% | 0.72% | 0.72% |
| 1440x900 | landscape reference | 1.79% | 1.79% | 1.79% |

Landscape is bit-for-bit untouched under all three models.

`restY0` in V2 is **not fitted**: the Target's rows sit at half-integer multiples
of cellH about the viewport centre, so the row origin is exactly `-cellH/2`. F2.5
had fitted it to `-200.99`, 9 world units off centre — which is the centre-dark-
band failure 390x844 has carried since F2. V2 fixes it at every portrait viewport.

`radiusY` was **not** opened. The brief allows it only if V1 cannot explain the
row-height falloff, and it can: at 390x844 V2's row heights are
`[186, 209, 207, 183]` against the Target's `[186, 207, 207, 184]`, and paired
row-band pitch agrees to 0.9%.

## Gate

14 mandatory viewports, contract unchanged, Target measured from 5-frame
consensus. Candidate **7/14 viewports, 107/118 checks**. The F2.6R configuration
measured identically scores **7/14 viewports, 96/113 checks**.

F2.7 removes these failures: 390x844 card height and centre band; 360x800 card
height and centre band; 700x700 card centres and row parity. It adds none of a
new kind; the void-blob excess at 390x844 and 360x800 gets worse (2.28→2.95,
2.99→3.59) because a centred seam merges two void regions into one blob.

### What still fails, and why

**Edge yaw** — 1100x720 (0.799 deg), 780x470 (1.23), 390x844 (1.248), 360x800
(1.444), against a 0.75 limit. **This is structural and it is now explained.**
The Target's sphere radius follows `max(width, height)` while our world is fixed
and scaled by a width-based S. Expressed in our units the Target's radius is
4166.67 at 1440x900 against our frozen −4058.94 (2.6% out), and **4815.6 at
390x844 against the same −4058.94 (18.6% out)**. Too small a radius yaws cards
too much. It cannot be fixed without unfreezing `GRID.radius` and the portrait
scale law.

The same cause closes our centre seam at 667x375: more curvature smears the seam
across the frame width until the detector can no longer resolve a full-width
band, so the Target shows a row band there and we show none.

**Centre dark band** — 667x375, 700x700, 780x470. This is the *landscape* half of
the same `restY0` defect V2 fixes in portrait, and F2.7 authorises a portrait-only
vertical change, so it was **not shipped**. It is runnable as
`?landscapeRowOrigin=centred` and measured: over 11 landscape viewports it takes
the gate from **7/11 to 9/11 with no regression at any currently-passing
viewport**, fixing 700x700 and 780x470's centre band, 780x470's edge yaw and
1100x720's edge yaw. `gate-diagnostic-landscape-row-origin.json`.

**Gutter width** — 780x470 (5 px), 500x900 (4 px), limit 3 px. Pre-existing,
unchanged by F2.7.

### Coverage holes, stated rather than hidden

At **1920x1080** and **667x375** no row pair survives the gate's conditioning, so
`cardCentre`, `cardSize`, `gutterPx` and `rowParity` are NOT_MEASURED there. At
1920x1080 both rows fail the mirror-symmetry test because our top row resolves
four cards where the Target resolves three; at 667x375 the local frame yields no
horizontal band at all, for the curvature reason above. 1920x1080's PASS is
therefore thinner than it looks and should be read as "nothing measurable
failed", not "everything was measured".

## A harness defect found and fixed this round

Multi-frame consensus, added because the brief requires it, initially made the
Target measurement **worse**: it fed one relaxed mask to both the strict
card-edge tracer and the relaxed band detector. Card edges truncated and their
slopes went wrong, which alone turned 1440x900 and 1100x720 from PASS into
edge-yaw failures. Both presets now get their own consensus mask. Recorded
because a reviewer comparing rounds would otherwise see a phantom regression at
the accepted baseline viewport.

## Runtime

**PASS 32/32** across four sessions: resize at rest, resize holding a (260, 180)
offset that is never reset, long scroll to +/-100 cells, and an orientation flip
with a deliberate crossing of the row-count boundary at 960x720 <-> 960x500.

A phase flip during a resize is **correct** — the Target's own row count steps
there and it re-phases too. The assertion is therefore not "never flips" but
"flips only where the row count parity steps", plus "never flips while only the
scroll offset moves". Both hold.
