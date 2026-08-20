# qa-v5/f25 — Stage F2.5 evidence index

Stage: **F2.5 Joint Responsive & Vertical Composition Recovery**
Gate verdict: **FAIL** — 5/6 viewports pass
Status: **CANDIDATE FAILED ABSOLUTE GATE**

Read [`docs/v5/CURRENT_STATUS.md`](../../docs/v5/CURRENT_STATUS.md) and
[`docs/v5/JOINT_COMPOSITION_RECOVERY.md`](../../docs/v5/JOINT_COMPOSITION_RECOVERY.md) first.

| viewport | verdict |
| --- | --- |
| 1100x720 | PASS |
| 1366x768 | PASS |
| 1440x900 | PASS |
| 1920x1080 | PASS |
| 390x844 | FAIL |
| 844x390 | PASS |

Contract coverage: `{"cardCentre": "PASS", "cardSize": "FAIL", "gutterPx": "FAIL", "edgeYaw": "FAIL", "rowParity": "PASS", "centreDarkBand": "PASS", "overlap": "PASS", "largeVoid": "FAIL", "f0Regression": "PASS"}`
Thresholds are the approved ones and were not relaxed.

| file | what it is |
| --- | --- |
| `gate.json` | Absolute-target contract, six viewports, Candidate T (shipped) |
| `depth/gate.json`, `depth/local/` | Candidate D, same gate, for comparison |
| `model-comparison.json` | The joint fit: D and T, with and without the portrait aspect term, shared parameters, held-out scores |
| `cross-validation.json` | Portrait scale law refitted after the vertical candidate, 390x844 held out; landscape leave-one-out; non-converged fits listed |
| `landscape-parity-law.json` | Rest-phase / row-parity rule with its agreement record across the nine required landscape viewports |
| `landscape-sweep-measurements.json` | Raw independent Target measurements for that sweep |
| `runtime-assertions.json` | Two resize sessions on `composition=v2`, offset preserved, 15 invariants each |
| `session/` | Session videos |
| `local/`, `beauty/` | Local frames the gate measured, and the shipping look |
| `MANIFEST.json` | Branch, HEAD, route, fixed capture conditions, SHA-256 of every file |

Preview:
- v1 (F2 candidate, kept): `/?optics=v4&composition=v1`
- v2 (this candidate): `/?optics=v4&composition=v2&verticalMode=tangent`
