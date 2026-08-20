# FSX acceptance and integration hardening

The source-exact composition is accepted. This round changes nothing about the
composition itself — every layout constant, formula, phase rule and slot
identity listed as frozen is untouched. What it does is fix the integration
around it, and show honestly what the page looks like with the glass and the
type actually on.

| | |
| --- | --- |
| SourceExact Composition Baseline | **ACCEPTED** |
| Engineering PASS | **YES** |
| Target Visual PASS | **NOT ASSERTED** |
| Typography / Motion / Optics | **NOT STARTED** |
| Main merge | **NOT AUTHORISED** |
| Old F0 layout baseline | Historical Accepted Baseline, superseded by SourceExact Composition |

## Three integration defects, all found by running the thing

### 1. `?composition=sourceExact` did not reach the source-exact build

`src/main.ts` routed to V4 on `optics=v4`, `foundation=layout` or
`composition=v2`. `sourceExact` was not in that list, so the route named in the
brief, in the docs and in every preview link booted **V3** unless `optics=v4`
was passed beside it. Any V5 composition now selects V4. V4 stays opt-in: no
composition and no optics still boots V3, and `sourceExact` is still not the
bare-page default.

Proved by loading each route rather than by reading the condition —
`route-proof.json`, **6/6**.

### 2. Adaptive quality had never once fired

`AdaptiveQuality.sample()` wrote `this.level` and then returned it. The single
caller asked `level !== this.quality.level` — comparing the returned value with
the field it had just been assigned from. Always false. `grid.setQuality()` and
`pipeline.setQuality()` were therefore only ever reachable through the manual QA
hook, and the entire adaptive path was dead.

`sample()` now returns `{ level, changed }`. With it live, an idle page climbs
back from `low` to `high` on its own: two spontaneous changes recorded at 3.59 s
and 6.09 s in `quality-invariance.json`, by the running sampler, not injected.

A consequence worth stating: with the sampler working it will fight any manual
level, so a QA-only `setAdaptiveQuality(false)` was added to hold a level still.
It changes no product behaviour. Skipping `sample()` entirely when disabled
matters too — calling it and ignoring the answer still mutates its internal
level, which would drift away from the quality the grid is actually running.

### 3. A quality step would have destroyed the source-exact card

`InfiniteGlassGridV4.setQuality()` rebuilt the glass volume with
`createConvexGlassGeometryV4(quality)` and **no override**. On the source-exact
path that would have replaced the contract's 4:3 reference plane with TILE's
1.3508 aspect and TILE's width, changing the shape and the size of every card.
It was never seen because defect 2 meant the rebuild never ran automatically.

The rebuild now keeps the override and re-applies the current layout frame.

## Quality invariance — PASS 43/43

`high → medium → low → high` at 1440x900, 390x844 and 700x700, on the beauty
route, with the sampler held off so each level actually holds.

| | |
| --- | --- |
| worst projected card-corner delta across all four levels | **0 px** (limit 0.5) |
| worst world-position delta across all four levels | **0** |
| card aspect | exactly 4/3 at every level |
| active slot count | unchanged at every level |
| meshes created / destroyed by a quality step | **0 / 0** |
| material, texture, video counts | constant; video reload 0 |
| source contract at high / medium / low | **PASS / PASS / PASS**, 3/3 viewports each |
| console and page errors | 0 |

## Beauty baseline

Seven viewports, four render states each: foundation, media-only with glass and
labels off, glass plus media with labels off, and full beauty. Quality pinned
high with the sampler off, media frozen at t = 2, motion paused, pointer (0, 0),
DPR 1, source-exact defaults. Zero capture errors.

This round only attributes what it finds. Nothing in typography, motion or
optics was modified.

**Typography, dominant.** The CSS3D label element is still sized to the fixed
TILE: `TileLabelLayer` sets `el.style.width = TILE.width` (539.8) while the
source-exact card is `frame.planeWidth`. Every type size in `style.css` is `cqw`
against that container, so the whole label block is scaled for the wrong card:

| viewport | card plane width | label element width | label container too wide by |
| --- | --- | --- | --- |
| 1440x900 | 547.2 | 539.8 | −1.4% |
| 1920x1080 | 729.6 | 539.8 | −26.0% |
| 780x470 | 296.4 | 539.8 | **+82.1%** |
| 844x390 | 320.7 | 539.8 | **+68.3%** |
| 390x844 | 280.8 | 539.8 | **+92.2%** |
| 700x700 | 266.0 | 539.8 | **+102.9%** |
| 667x375 | 253.5 | 539.8 | **+113.0%** |

1440x900 is the one viewport where TILE happens to match the card, which is why
this was never visible: the type layer was tuned at exactly the viewport where
the bug has no effect. Everywhere else titles overflow their card and run across
the gutter onto neighbours, and adjacent labels collide — plainly visible at
390x844 as overlapping ILG codes. This is layout plumbing rather than a style
value, and it is the first thing the authorised Typography stage should fix.

**Typography, high.** Labels are not clipped to their card and have no depth
relationship with the WebGPU cards, so text from a card behind can draw over a
card in front.

**Optics, medium.** Cyan/magenta fringing along card edges is stronger than the
Target's, and media inside the glass reads more saturated and higher contrast.
MediaFit and the accepted F1 focus values are not the cause — the cover matrix
is correct and the tone response is not.

**Motion.** Every capture is at rest, so this baseline says nothing about drag
feel. The known dragGain mismatch is unchanged and unmeasured here.

**Performance, observation.** 120 fps and p95 8.7–10.3 ms at every viewport and
every state. Draw calls 1182 in beauty against 776–778 in foundation for a
100–120 slot active pool through a two-pass pipeline; the 256-slot preallocation
costs nothing at draw time because inactive slots are hidden. Headless capture on
a developer machine — not a device-class claim.

## Detector residual — correction

The F2-SX delivery reply quoted "max centre 2.67 px, max width 71.89 px". That
was wrong. Those were the maxima of an earlier six-viewport run; once 700x700 and
667x375 were added, `detector-residual.json`'s own top-level fields read
**35.02 px** and **118.75 px**, and the reply did not carry the update.

`detector-residual-v2.json` reports every bucket, under rules stated before the
numbers were looked at — mutual nearest match, runner-up at least twice as far,
detected width within 25% of truth width, unclipped on both sides:

| | centre | width |
| --- | --- | --- |
| all pairs | **132.49 px** | **280.50 px** |
| high-confidence pairs only | **14.17 px** | **67.51 px** |

Pairing confidence is **0.357** — only 30 of 84 detections survive those rules.
Phantom gutters: 18 on Target frames, 16 on ours.

So the instrument's error is larger and much less clean than the corrected reply
implied. It still exceeds the 3.5–6.5 px gutter-centre residual the pixel gate
fails on, and our gutter reading remains at least as close to the Target's own
DOM truth as the Target's own frame is at all nine viewports. But this bounds the
pixel instrument only: it cannot substitute for the source contract and it
asserts nothing about beauty.

## Frozen this round

Every layout constant in `target-layout-source-v2.json`, `sourceExactLayout()`,
sphere placement, the perspective and radius formulas, the plane width ratio,
the cell pitch formula, the rows/cols coverage law, pool slot phase and slot
identity. Typography styles, motion parameters and optics parameters.
