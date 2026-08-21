# WebGL render culling freeze contract

V1 passed its absolute gate. This file is the record of what that freezes,
at which heads. The findings live in
[`qa-v5/render-culling/README.md`](../../qa-v5/render-culling/README.md);
this file is the decision.

## Acceptance record

| | |
| --- | --- |
| V1 Render Culling Absolute Gate | **PASS** |
| Product acceptance | **ACCEPTED / FROZEN** (O2 round brief) — accepted review tip `5159cf8` |
| Render culling behaviour baseline | `b625f90` — the V1 code commit every capture was taken at |
| Evidence | `04cff37` |
| SourceExact WebGL Render Culling | **FROZEN** |
| Target Visual PASS | **NOT ASSERTED** |
| Main merge / force push | **NOT AUTHORISED** |

## What is frozen

- the layered visibility model: no system writes `.visible` on a slot mesh
  directly — the scene-colour pipeline's per-pass flips, the QA layer
  requests, the shell mode, the debug mode, the active window and the
  coverage verdict each set a flag, and `applyEffectiveVisibility` composes
  them (`InfiniteGlassGridV4`)
- one verdict, two surfaces: the SAME `SourceExactLabelCulling` array the
  label layer consumed drives the meshes in the same sync
  (`GridAppV4.syncLabels`)
- glass and shell follow `active AND coverage AND pass` — the Target's
  `s.visible = o.draw`, mapped per object
- the media plane is NOT coverage-culled: the scene-colour target is our
  equivalent of the Target's per-card texture binds, which the Target does
  not cull either (source-read: its refraction samples the card's OWN
  texture, so hiding a card never changes another card's pixels)
- mesh poses update every frame regardless of visibility (source-read: the
  Target poses hidden meshes too; the CSS3D label freeze is the opposite
  and is frozen in V0)
- pixel invariance: culling ON vs OFF byte-identical; candidate vs the
  V0-accepted baseline identical

QA-only readbacks (`setRenderCulling`, `getRenderCullingTruth`,
`getRenderPassStats`, the per-pass stats collector) may be extended for
later regressions; they must not change any behaviour above.

## What later rounds may not do

- write mesh visibility from any new system instead of a composed flag
- coverage-cull the scene-colour input, or split the coverage state
  between passes
- re-tune the verdict against a draw-call count
