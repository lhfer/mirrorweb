# qa-v5/f26r — Evidence integrity hotfix

Status: **READY FOR PRODUCT REVIEW AFTER EVIDENCE CORRECTION**

Harness and evidence only. No visual parameter was changed this round.

## What was wrong

`portraitLaw` reached `compositionScale` but not `viewZoom` or
`effectivePerspectivePx`. The shipping mechanism is focal, so the camera took
the DEFAULT law while the reported scale followed the requested one. p0 and p1
rendered byte identically at 390x844 — the F2.6 comparison measured one
candidate twice and called it two.

**`qa-v5/f26/portrait-candidate-gates.json` is superseded and must not be used
as a p0-vs-p1 runtime comparison.**

## Proof it is fixed

390x844 PNG SHA-256, after the fix:

```
p0  13bd864c5657dccf309afe5db34e7d40db111f3ec0e748bfe7af67795506995b
p1  8a0c03285d23a7d8f74ae0d0da6c0da6d690fd60ae8138d7cb035bbac7d800e0
p2  0c1a2f4a87fe8f175362c4bfafd4ace6ffff8bc8df94e7cc81c0e872b331a691
```

Scale derived from the LIVE camera projection at 390x844 — measured by
projecting a known world segment through the running camera, not read back from
config:

```
p0  0.5304246143616345
p1  0.5071253885584227
p2  0.5071253885584227
```

`runtime-law-proof.json`: **PASS**, 12/12 checks. Projected card width at
390x844 moves 278.823 px (p0) against 266.576 px (p1) — a 12.2 px difference
that no amount of JSON could fake.

1440x900 is kept as a control: p0 and p1 stay byte identical there, because
landscape never uses the portrait gain. That is the correct result and it shows
the portrait difference comes from the law rather than capture noise.

## Corrected comparison

| candidate | gate | scale hold-out | 390x844 failures |
| --- | --- | --- | --- |
| p0 | 5/6 | +5.088% | unclipped card width, bottom edge slope, gutter centre, largest void blob excess |
| p1 | 5/6 | +0.472% | unclipped card height, bottom edge slope, viewport centre in a horizontal gutter, largest void blob excess |
| p2 | 4/6 | +0.472% | unclipped card height, bottom edge slope, largest void blob excess |

**p0 and p1 tie at 5/6.** F2.6 reported p1 as the better of the two on the gate;
with both actually rendering, they tie and fail 390x844 in different ways. p1
still ships, but on the cross-validation alone (+0.472% against
+5.088%), not on a gate advantage it does not have.

## Files

| file | what it is |
| --- | --- |
| `runtime-law-proof.json` | SHAs, live camera scales, projected card sizes, propagation assertions |
| `portrait-candidate-gates.json` | The corrected three-way comparison |
| `model-vs-engine.json` | Now includes the portrait-law axis: 21 combinations, worst corner error 0.0 px |
| `gates/` | Full six-viewport gate per candidate |
| `portrait-candidates/` | The four recapture viewports per candidate |
| `phase-mismatch/` | Local frames for the four viewports where the aspect phase rule disagrees |
| `MANIFEST.json` | Branch, HEAD, route, fixed capture conditions, SHA-256 of every file |
