# V5 Foundation Baseline — accepted

**Status: ACCEPTED by product review on 2026-08-20.**

Stage F0 (layout geometry) and Stage F1 (media cover/crop) are the V5 Foundation
baseline. Later stages measure against this, not against the pre-V5 build.

## What was accepted

| | |
| --- | --- |
| Branch | `rebuild/liquid-glass-v5-foundation` |
| Reviewed tree | `fd4af03` (`v5-f0-f1-evidence-path-hygiene`) |
| Code | `7f18314` `v5-f0-f1-code` |
| Evidence | `2767f90` `v5-f0-f1-evidence`, `7fa2b6d` `v5-f0-f1-followups`, `fd4af03` |
| Page | `/?optics=v4` |
| Gate | `qa-v5/f0/gate.json` — 20/20 PASS at 1440×900 DPR1 |

## The numbers this baseline pins

```
GRID.cellW   561.14      GRID.cellH   420.43
GRID.restY0  -209.97     GRID.radius  -4058.94   (convex; outer columns recede)
TILE.width   539.8       TILE.height  399.6      (aspect 1.351)
CAMERA       fov derived from perspectivePx=1000; 1 world unit = 1 CSS px at z=0
```

Worst measured error against the Target at 1440×900: landmark centres 0.389% of
viewport, card size 0.53%, gutters 2 px, edge slopes 0.46°, symmetry 0.0%.
The engine's projected quads match the analytic model to **0.0 px** at every
captured offset and at 1920×1080, 1440×900, 1100×720, 390×844 and 844×390.

## Media focus, as approved

| Clip | focusX | focusY | zoom |
| --- | --- | --- | --- |
| NL-01 牛来开场 | 0.50 | 0.50 | 1.00 |
| NL-02 Cursor 牛来 | 0.50 | 0.50 | 1.00 |
| NL-03 鹈鹕测 AI | 0.50 | **0.46** | **1.06** |

Applied in the follow-up commit that immediately follows this one.

## What acceptance does NOT cover

Accepting the baseline does not close any of the gaps in
[FOUNDATION_FIT.md](FOUNDATION_FIT.md). In particular the responsive scaling law
is still wrong, and it is the subject of Stage F2. Optics, motion and typography
remain untouched and out of scope.

No V5 source contract is established by this acceptance. Per the product
instruction, a V5 contract may only be cut after F2 passes.
