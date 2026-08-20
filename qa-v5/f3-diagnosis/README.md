# qa-v5/f3-diagnosis — vertical curvature, diagnosis only

**No product code is changed by this stage and no `radiusY` is implemented.**

The accepted V5 Foundation geometry gives every row the same projected height.
Tall Target viewports disagree. Three models were fitted to the same
observations with **one shared parameter set across all viewports** -- only each
viewport's own vertical rest offset is free -- and one portrait viewport
(414x896) was held out of every fit.

| model | what it adds | train RMS | train max | held-out RMS |
| --- | --- | --- | --- | --- |
| M0 | nothing (accepted baseline) | 10.763 px | 37.805 px | 11.701 px |
| **M1** | **vertical curvature radius** | **4.908 px** | **17.355 px** | **4.968 px** |
| M2 | camera pitch + vertical scale | 10.387 px | 34.46 px | 11.388 px |

M1 halves the error on training **and** on the held-out viewport, and its
held-out RMS matches its training RMS, so it generalises rather than absorbing
noise. M2 -- the simplest alternative explanation -- barely improves on doing
nothing, so a camera pitch does not explain the falloff.

Fitted shared parameter: `radiusY = 2053.4186` world units,
against the accepted horizontal radius of -4058.94.

See [`docs/v5/VERTICAL_CURVATURE_DIAGNOSIS.md`](../../docs/v5/VERTICAL_CURVATURE_DIAGNOSIS.md).

| file | what it is |
| --- | --- |
| `model-comparison.json` | Full M0/M1/M2 fit, shared parameters, per-viewport RMS, desktop regression |
| `held-out-results.json` | The held-out viewport under each model |
| `row-height-curves.json` | Observed vs modelled row heights and centres, per viewport |
| `local-diagnostic-sheet.png` | Visual: observed vs modelled row-height curves |
