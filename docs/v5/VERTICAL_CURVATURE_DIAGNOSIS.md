# V5 — Vertical curvature: diagnosis

**Diagnosis only. No product code is changed, and `radiusY` is not implemented.**
This exists so the product owner can decide whether F3 is worth opening, since
fixing it means reopening the accepted F0 Foundation baseline.

## The observation

The accepted geometry is a vertical-axis cylinder, so depth is a function of
horizontal position only and every row projects to the same height. Tall Target
viewports contradict that. Rows fully inside the frame, so not clipped:

| viewport | inner rows | outer rows | falloff |
| --- | --- | --- | --- |
| 390x844 | 207 px | 185 px | -10.6% |
| 414x896 | 219 px | 196 px | -10.4% |
| 430x932 | 227 px | 197 px | -13.2% |

Desktop viewports cannot see it: at 1440x900 the visible rows sit within about
+/-210 world units of the axis, where the predicted falloff is under 2%.

## Models compared

All three were fitted to the **same** observations with **one shared parameter
set across every viewport** -- only each viewport's own vertical rest offset is
free. Per-viewport shape parameters would fit anything. `414x896` was held
out of every fit.

Viewports: 1440x900, 1100x720, 1920x1080, 360x800, 390x844, 414x896, 430x932

| model | adds | train RMS | train max | held-out RMS |
| --- | --- | --- | --- | --- |
| M0 | nothing (accepted baseline) | 10.763 px | 37.805 px | 11.701 px |
| **M1** | **vertical curvature radius** | **4.908 px** | **17.355 px** | **4.968 px** |
| M2 | camera pitch (lookY) + vertical scale | 10.387 px | 34.46 px | 11.388 px |

## Reading

**M1 wins, and not narrowly.** It halves the residual against the baseline on
training data, and — the part that matters — its held-out RMS
(4.968 px) is essentially identical to its training RMS
(4.908 px). A model that only memorised its training viewports
would not do that.

**M2 is rejected.** A camera pitch plus a vertical composition scale is the
simplest alternative that could plausibly produce a row-height falloff, and it
improves on doing nothing by 3%
— within noise. The falloff is not a camera artefact.

Fitted shared parameter: **`radiusY = 2053.4186`** world units,
against the accepted horizontal radius of -4058.94. The vertical curvature is
roughly twice as tight as the horizontal one.

Desktop regression under M1 (must not get worse):

- 1440x900: RMS 1.244 px, max 1.976 px
- 1100x720: RMS 0.806 px, max 1.483 px
- 1920x1080: RMS 5.727 px, max 8.063 px

## Recommendation

The evidence clears the bar the product brief set: M1 is significantly better
than both M0 and the alternative, and it generalises to a viewport it never saw.
**F3 product work is worth opening.** It would change `GRID`, which is the
accepted F0 Foundation baseline, so it needs an explicit product decision to
reopen that baseline — it is not something this stage may do on its own.

Residual caveat: M1 still leaves 17.355 px of maximum error, so
the dual-axis cylinder is probably an approximation of whatever the Target
actually does rather than an exact match. That is worth knowing before treating
a fitted `radiusY` as ground truth.
