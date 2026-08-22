# O4 product review — frozen body floor

Reviewed at `5a87751d348ebc626e8193d76af33957a1bdf664`. This is the product
record for the O4 round and the document that opens O5.

O4 asked one question: **what holds the frozen body floor up, and can it be
reduced?** It answered the first half and failed the second. Both halves are
recorded here, because the accepted half is what O5 is built on.

## ACCEPTED

### The O4A zero-normal diagnosis

The compiled-program audit is accepted as a **defect finding**, not a
hypothesis. Three's TSL unpacks a shared varying into only the first debug
branch that references it. `normalViewGeometry = normalize(v_normalViewGeometry)`
is emitted once, inside the `normals` branch; every other branch — the shipped
Beauty path included — aliases a `var<private>` that WGSL zero-initialises. The
shipped `refract()`, `projectedNormalOffset` and `facing` therefore consume a
**zero normal**.

The discriminator that makes this a finding rather than a suspicion: two debug
views read the same varying in different branches of one program, same frame,
same geometry. `normals` varies across the card (range 38/66/3); `fresnel` is
exactly constant (0/0/0). A normal that varies cannot produce a spatially
constant Fresnel term. The controls that read unshared vertex attributes vary
correctly.

This **explains** the long-standing GATE-005 anomaly — the refraction-offset
debug view moving by at most 2 of 255 levels while the beauty render moved on
34.9% of pixels — rather than merely reproducing it.

The defect is **still open**. O4 was not permitted to repair it (§三 of the O4
brief forbade fixing anything during the audit), and the subsystem O4 selected
was a different one. It exists in the O4 tree only as diagnostic factor N.

### The Target body source contract

17 sites, 0 failed, against bundle
`4983307288d9e6c544751d1f969a0bc5c4fdb86ebbe5c93ee97aa74ceb0b3754`. Absences —
which have no bytes to anchor — are established by a completeness span across
the whole body colour chain (bytes 1975111–1976472) rather than by pretended
byte offsets. Accepted as the factual basis for O5's contract.

### The factorial instruments

Sealed at `968e7ddfaa67` before the pixels they judged; 32/32 instrument tests
pass, each with a negative partner. The per-card-then-average band coding, the
control-derived true silhouette, the baseline-aware interior branch and the
bool-safe aggregator checks are accepted and carry into O5.

### The adaptive body shaping attribution — with the scope limitation below

Local adaptive body shaping (contrast shaping, adaptive edge lift, adaptive
internal shadow) is the dominant contributor to the **current screen-space
body's** broad internal floor: +141% of the desktop excess, interaction ratio
0.13, sign-stable across all four media. Removing it drops the System-B-OFF
floor 9.7 → 1.7 px desktop and 6.0 → 0.0 at both mobile viewports.

### Control-lane exact identity

The O4 control lane is **exactly zero** differing pixels against an `e913aa6`
worktree build at System B OFF, on every scored case. Every O4 comparison is
therefore against the accepted O2 body and not against something else. The
diagnostic factor machinery is byte-identical to the pre-O4 program at all
three quality levels when off.

### The candidate's failure

8 of 12 gate items passed. Items 2, 3, 5 and 9 failed. The verdict stands as
scored, at codings sealed before the pixels existed.

## REJECTED

### The `bodyFloorMode` default flip

`remove-adaptive-shaping` does not become the shipped default. The gate failed,
and no brief in this programme authorises an automatic flip.

### Reading 1.7 / 0.0 / 0.0 px as a Target match

It is not a match. It is an **undershoot**: the candidate takes the body floor
*below* the Target's whole band at every viewport (Target 3.3 / 1.5 / 2.0). Item
2 was sealed as a two-sided window precisely so that undershooting could not be
reported as success. A body that contributes nothing is not a body that behaves
like the Target's.

### Reading O4 Factor A as the Target's own-media refraction

**This is a required wording correction.** O4's factorial table listed §七's
candidate *names* against the diagnostic factors that stood in for them, and in
one row the label and the mechanism do not match.

Factor A was `noRefractionOffset`: a build-time branch that set **our**
screen-space refraction displacement to `vec2(0)`. It measured what our existing
screen-space offset contributes to our existing body. It did **not** implement
the Target's own-media, per-IOR refraction — that system was never built in O4
and therefore was never measured.

So A's ~3% effect is the contribution of *our screen-space displacement term*,
and nothing may be inferred from it about the Target's refraction system. In
particular it is **not** evidence that Target refraction is a small effect. The
same caution applies to the other rows: each factor measured a subtraction from
our body, not an installation of the Target's.

Factor C is unaffected by this correction — `noAdaptiveShaping` removes exactly
the subsystem §七's candidate A named, so label and mechanism agree there.

### Another isolated one-factor optics round

Three rounds have now replaced one term at a time while holding several
known-wrong terms frozen, and each has run into the same wall from a different
side:

- O3 showed the support field is not the binding constraint **given this body**.
- O4 showed the body is not the binding constraint **given this support**.

Both are true, and neither round was permitted to change the other's half. The
shipped band moves 15.3 → 13.0 px when the body is emptied out, because with the
body dark the O2 reflection support paints the band on its own. Continuing to
subtract single terms from a screen-space body cannot converge on a material
that was never screen-space to begin with.

O5 therefore authorises **one cohesive system**: the Target's complete card
optical body, restored together as one material chain.

## Canonical status correction

`CURRENT_STATUS.md` recorded the O4 gate as **7/12**. The scored artefact
(`qa-v5/optics-o4/body-floor-gate.json`) and the O4 README both record **8/12**,
with items 2, 3, 5 and 9 failing and 0 pending. 8/12 is correct; the status file
is corrected in this commit at both places it appeared.

The correction does not change the verdict — the gate is absolute, and 8/12 and
7/12 both FAIL. It changes only the count.

The O4 evidence tree itself is **not** rewritten. It is pushed history, its
per-file hashes are sealed in a private package manifest, and the factorial
table's label/mechanism conflation is corrected here rather than edited there.

## What O5 opens

O5 builds one isolated candidate lane, `opticalBody=target-source`, implementing
the Target's complete card optical body as a single coherent material system:
the plane/position model, the rounded-rect SDF alpha, the analytic bevel normal,
own-media sampling, per-IOR refraction, spectral accumulation, level-0 sampling,
no adaptive shaping, the accepted System B environment reflection in the same
body, the white SDF rim, and the Target's output-transform behaviour.

Default remains `opticalBody=current` until product review. Target Visual PASS
remains **NOT ASSERTED**.
