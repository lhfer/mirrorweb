# CSS3D label culling freeze contract

V0 passed CSS3D culling product review. This file is the record of what that
freezes, at which heads. It contains no new findings — the findings live in
[`qa-v5/culling/README.md`](../../qa-v5/culling/README.md); this file is the
decision.

## Acceptance record

| | |
| --- | --- |
| V0 CSS3D Culling Product Review | **ACCEPTED** |
| Culling behaviour baseline | `820cd92dcc9b6bf29237114ff2f8a44603964f36` — the commit whose captures scored the accepted gate |
| Accepted review tip | `b4a44509471f791fde6ec9192d1fc98339e071c4` |
| SourceExact CSS3D Label Coverage Culling | **FROZEN** |
| Package hygiene fix | **ACCEPTED** — every private package's `numbers/` tree must carry the complete 11-file public tree, `README.md` included |
| Target Visual PASS | **NOT ASSERTED** |
| Main merge / force push | **NOT AUTHORISED** |

## What is frozen

The source-exact label coverage culling behaviour, in full:

- `SourceExactLabelCulling` — the module and its verdict semantics
- the dolly-free coverage camera (`sourceExactCoverageCamera`): render-camera
  lens, pointer orbit, NO velocity dolly, used for coverage projection only
- the four-corner projection of the unit card quad (±0.5, order BL BR TR TL)
  through the coverage camera
- the NDC z skip — a corner with z outside [−1, 1] is dropped; zero surviving
  corners reject the slot
- the AABB minimum area — area ≤ 1 px² rejects
- the exact 64 px coverage margin — `draw` requires strictly positive overlap
  with the viewport expanded 64 px per side
- the strict-viewport half-area flag — `interactive` = strict overlap > 0 AND
  overlapArea/aabbArea ≥ 0.5, published, read by nothing (as in the Target)
- inline `backface-visibility: hidden` on every label element — the backface
  test is CSS, not JS; the JS dot-product remains a QA diagnostic only
- the stale transform on culled labels — a hidden label stops receiving
  transform writes and keeps its last matrix, exactly as the Target does
- guarded visibility writes — visibility is written only when it changes
- slot identity — verdicts are keyed by stable slot index; culling never
  rebinds slot content, including across wraps and pool re-entry
- legacy route behaviour — the non-source-exact label path is unchanged and
  stays unchanged

QA-only readbacks (`getLabelTruth` culling verdicts, `setLabelSyncProbe`,
`getLabelSyncStats`) may still be extended for later regressions. They must
not change any behaviour above.

## What later rounds may not do

- re-tune any constant above against a visible count or a performance number
- give the coverage camera a dolly, or make the CSS3D transform camera
  dolly-free (see [`MOTION_FREEZE_CONTRACT.md`](MOTION_FREEZE_CONTRACT.md))
- move label visibility decisions out of the verdict, or write label
  visibility from any other system
- apply the label verdict to WebGL objects without the V1 source mapping —
  the Target's `s.visible = o.draw` wiring is V1's mandate, not V0's
