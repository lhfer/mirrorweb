# qa-v5/f26 — Stage F2.6 evidence index

Stage: **F2.6 Final Composition Closure**
Gate: **FAIL** — 5/6
Status: **READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW**

Read [`docs/v5/CURRENT_STATUS.md`](../../docs/v5/CURRENT_STATUS.md) and
[`docs/v5/FINAL_COMPOSITION_CLOSURE.md`](../../docs/v5/FINAL_COMPOSITION_CLOSURE.md) first.

| viewport | verdict |
| --- | --- |
| 1100x720 | PASS |
| 1366x768 | PASS |
| 1440x900 | PASS |
| 1920x1080 | PASS |
| 390x844 | FAIL |
| 844x390 | PASS |

Contract coverage: `{"cardCentre": "PASS", "cardSize": "FAIL", "gutterPx": "PASS", "edgeYaw": "FAIL", "rowParity": "PASS", "centreDarkBand": "FAIL", "overlap": "PASS", "largeVoid": "FAIL", "f0Regression": "PASS"}` — thresholds unchanged.

| file | what it is |
| --- | --- |
| `gate.json` | Absolute-target contract, six viewports, shipping candidate (v2 / tangent / p1) |
| `portrait-crossval.json` | P0 / P1 / P2 with their fits, hold-out errors and parameters. The shipped numbers are the P1 entry verbatim. |
| `portrait-candidates/` | All three built and gated as runnable candidates, not compared on paper |
| `portrait-candidate-gates.json` | The three gate verdicts side by side |
| `landscape-phase.json` | Phase rule judged against the RUNTIME law, parity classified directly from row structure |
| `landscape-phase-sweep.png` | The sweep, ordered by aspect, agreement marked |
| `model-vs-engine.json` | Corner-by-corner, both phases, both vertical modes, six viewports |
| `target-consensus-measurements.json` | Five frames per viewport, 80% consensus, single-frame comparison kept |
| `long-scroll-runtime.json` | +/-0.49, +/-0.51, +/-10, +/-50, +/-100 cells |
| `runtime-assertions.json`, `session/` | Two resize sessions with the offset preserved |
| `local/`, `beauty/` | Frames the gate measured, and the shipping look |
| `MANIFEST.json` | Branch, HEAD, route, fixed capture conditions, SHA-256 of every file |

Preview:
- v1: `/?optics=v4&composition=v1`
- candidate: `/?optics=v4&composition=v2&verticalMode=tangent&portraitLaw=p1`
