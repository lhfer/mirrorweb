# qa-v5/f2 — Stage F2 evidence index

Stage: **F2 Responsive Composition Scaling**
Gate verdict: **FAIL**
Contract coverage: `{"cardCentre": "FAIL", "cardSize": "NOT_MEASURED", "gutterPx": "FAIL", "edgeYaw": "NOT_MEASURED", "rowParity": "FAIL", "centreDarkBand": "PASS", "overlap": "PASS", "largeVoid": "PASS", "f0Regression": "PASS"}`

Read [`docs/v5/CURRENT_STATUS.md`](../../docs/v5/CURRENT_STATUS.md) first.

## What is in here

| file | what it is |
| --- | --- |
| `gate.json` | The approved absolute-target contract, all six viewports. Card centre <= 2% of viewport, card size <= 3%, **gutter <= 3 px absolute**, edge yaw <= 0.75 deg, row parity, centre dark band, no overlap, no large void, F0 regression. Each item reports PASS / FAIL / NOT_MEASURED. |
| `target-measurements.json` | Independent per-viewport Target measurement: scale, scroll offsets, both camera/focal hypotheses with RMS and max error, row bands, row heights, gutter centres, capture time, DPR, UA/touch mode. **No value in it is produced by evaluating the shipped law.** |
| `cross-validation-v2.json` | Real cross-validation. Landscape leave-one-out; portrait trained on 360x800 / 414x896 / 430x932 with 390x844 genuinely held out, plus five further validation viewports. Replaces the withdrawn `cross-validation.json`. |
| `model-fit-summary.json` | Camera vs focal hypothesis, aggregate fit quality, and the measured scale/gain per viewport. |
| `orientation-boundary.json` | Does the Target really switch at width == height, and which side does a square take. Target and local side by side. |
| `orientation-boundary-target-metrics.json` | Raw Target metrics for the boundary sweep. |
| `orientation-boundary-local.mp4` | Local sweep through the corner. |
| `session/runtime-assertions.json` | Two resize sessions with the offset preserved, 15 runtime invariants each. |
| `session/rest/`, `session/nonzero-offset/` | Session videos, offset (0,0) and (260,180). |
| `local/`, `beauty/` | Local frames the gate measured, and the shipping look. |
| `MANIFEST.json` | Branch, HEAD, route, fixed capture conditions, SHA-256 of every file. |

## Result

Gate: **FAIL**. Failing contract items: cardCentre, gutterPx, rowParity.

Cross-validation, corrected:
- landscape gain **1.00288**, leave-one-out worst error **0.404%**
- portrait gain **1.86361** trained on ['360x800', '414x896', '430x932']; held-out 390x844 error **+0.444%**
- the **shipped** portrait gain is 1.8975, which is **1.8% above** the cross-validated value

Orientation: the switch at width == height is **real** (1.8385x across one pixel, confirmed at two corners), and a square takes the **landscape** side, which is what the shipped rule does.

Runtime: both resize sessions **PASS**, 15/15 assertions each, offset preserved across 45 steps.
