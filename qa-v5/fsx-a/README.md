# qa-v5/fsx-a — FSX acceptance and integration hardening

| | |
| --- | --- |
| SourceExact Composition Baseline | **ACCEPTED** |
| Engineering PASS | **YES** |
| Target Visual PASS | **NOT ASSERTED** |
| Typography / Motion / Optics | **NOT STARTED** (Typography authorised next) |
| Main merge | **NOT AUTHORISED** |

Full write-up: [`docs/v5/FSX_ACCEPTANCE.md`](../../docs/v5/FSX_ACCEPTANCE.md).
LOCAL pixels and Target-derived NUMBERS only; anything alongside Target pixels is
in `qa-v5/private/`, which is git-ignored.

The composition itself did not change this round. Every frozen item — the
constants under `grid`, `sourceExactLayout()`, sphere placement, the perspective
and radius formulas, the plane width ratios, the cell pitch formula, the
rows/cols coverage law, pool slot phase and slot identity — is untouched.

## Three integration defects, all fixed

**`?composition=sourceExact` booted V3.** `src/main.ts` routed to V4 on
`optics=v4`, `foundation=layout` or `composition=v2` only, so the route named in
the brief and in every preview link needed `optics=v4` beside it to work at all.
`route-proof.json` now loads all six routes and reports what actually booted:
**6/6**, with the bare route still V3 and `sourceExact` still not the default.

**Adaptive quality had never fired.** `AdaptiveQuality.sample()` wrote
`this.level` and returned it; the caller compared the two. Always false, so
`grid.setQuality()` and `pipeline.setQuality()` were only ever reachable through
the manual QA hook. It now returns `{ level, changed }`, and with it live an idle
page climbs from `low` back to `high` on its own — two spontaneous changes at
3.59 s and 6.09 s, recorded by the sampler, not injected.

**A quality step would have destroyed the source-exact card.**
`setQuality()` rebuilt the glass volume with no geometry override, which on this
path swaps the contract's 4:3 reference plane for TILE's 1.3508 aspect and TILE's
width. Invisible until now, because the rebuild never ran automatically.

## Quality invariance — PASS 43/43

`high → medium → low → high` at 1440x900, 390x844, 700x700, beauty route.

| | |
| --- | --- |
| worst projected card-corner delta | **0 px** (limit 0.5) |
| worst world-position delta | **0** |
| card aspect | exactly 4/3 at every level |
| active slot count | unchanged |
| meshes created / destroyed | **0 / 0** |
| material / texture / video counts | constant, video reload 0 |
| source contract at high / medium / low | **PASS / PASS / PASS** |
| console and page errors | 0 |

## Beauty baseline

Seven viewports x four render states: foundation, media-only (glass and labels
off), glass + media (labels off), full beauty. Quality high with the sampler off,
media frozen at t=2, motion paused, pointer (0,0), DPR 1, source-exact defaults.
Zero capture errors. Nothing in typography, motion or optics was modified — this
only records where the gap is and who owns it.

**Typography owns the dominant gap.** `TileLabelLayer` still sizes the CSS3D
label element to the fixed `TILE.width` (539.8) while the source-exact card is
`frame.planeWidth`. Every type size in `style.css` is `cqw` against that
container, so the label block is scaled for the wrong card everywhere except
1440x900 — the one viewport where TILE happens to match, and the viewport the
type layer was tuned at:

| viewport | card | label element | too wide by |
| --- | --- | --- | --- |
| 1440x900 | 547.2 | 539.8 | −1.4% |
| 1920x1080 | 729.6 | 539.8 | −26.0% |
| 667x375 | 253.5 | 539.8 | **+113.0%** |
| 700x700 | 266.0 | 539.8 | **+102.9%** |
| 390x844 | 280.8 | 539.8 | **+92.2%** |
| 780x470 | 296.4 | 539.8 | **+82.1%** |
| 844x390 | 320.7 | 539.8 | **+68.3%** |

Titles overflow their card and run across the gutter onto neighbours; adjacent
labels collide. Also typography: labels are not clipped to their card and have no
depth relationship with the WebGPU cards.

**Optics** owns the stronger-than-Target cyan/magenta edge fringing and the
higher saturation of media inside the glass. MediaFit and the accepted F1 focus
values are not the cause.

**Motion** is unobservable here — every capture is at rest.

**Performance**: 120 fps, p95 8.7–10.3 ms everywhere. Headless developer
machine, not a device-class claim.

## Detector residual — correction

The F2-SX delivery reply quoted "max centre 2.67 px, max width 71.89 px". Those
were the maxima of an earlier six-viewport run; the file's own top-level fields
by then read **35.02 px** and **118.75 px**, and the reply did not carry the
update. `detector-residual-v2.json` reports every bucket under rules fixed in
advance:

| | centre | width |
| --- | --- | --- |
| all pairs | **132.49 px** | **280.50 px** |
| high-confidence only | **14.17 px** | **67.51 px** |

Pairing confidence **0.357** (30 of 84 detections survive). Phantom gutters: 18
on Target frames, 16 on ours. The instrument's error is larger and far less clean
than the earlier reply implied. It still exceeds the 3.5–6.5 px gutter-centre
residual the pixel gate fails on, and our gutter reading is still at least as
close to the Target's own DOM truth as the Target's own frame is at all nine
viewports — but this bounds the pixel instrument only. It cannot substitute for
the source contract and it asserts nothing about beauty.

## Files

| file | what it is |
| --- | --- |
| `route-proof.json` | Six routes loaded for real, with the app and composition each resolved to. |
| `quality-invariance.json` | The high/medium/low/high sweep, the adaptive sampler's own recorded changes, and the source contract at every level. |
| `detector-residual-v2.json` | All-pair and high-confidence buckets, pairing confidence, exclusion rules, phantom gutters. |
| `attribution.json` | Every beauty-baseline finding, attributed to typography, optics, motion or performance. |
| `beauty/` | 7 viewports x 4 render states, plus capture metrics. |
| `session/` | Per-level source-contract results and the quality sweep trace. |
