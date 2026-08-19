# Infinite Liquid Glass — Reference Spec (Phase 1)

Status: **evidence draft**. All numbers below come from captured screenshots, DOM, network, or pixel measurement. Items not captured are marked `missing` or `blocked`. This document does not claim a local replica exists.

Target: `https://infinite-liquid-glass.shader.se/?v=2`  
Local preview (later phases): `http://127.0.0.1:5280`  
Measurement script: `scripts/measure-landmarks.mjs` → `artifacts/reference/measurements/landmarks.json`

---

## 1. Capture environment

| Field | Value | Source |
| --- | --- | --- |
| Date/time (UTC) | 2026-08-18T18:09:30Z opened; A env written 2026-08-18T18:09:45.008Z | `A-1440x900-dpr1/environment.json`, `states.json` |
| Local time | 2026-08-18 11:09 PDT (UTC−7) | capture host |
| OS | macOS 27.0 (26A5378n) | environment.json |
| GPU (host) | Apple M5 Max, 40-core, Metal | environment.json / probe |
| Browser | Google Chrome 151.0.7922.138 (Playwright `channel: "chrome"`, headed) | environment.json |
| User-Agent | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36` | environment.json |
| WebGPU | `available: true`, `vendor=apple`, `architecture=metal-3`, `description=Apple M5 Max`, `device=0x0000`, `isFallbackAdapter=null` | environment.json |
| WebGL renderer (debug) | `ANGLE (Apple, ANGLE Metal Renderer: Apple M5 Max, Unspecified Version)` | environment.json |
| SwiftShader? | **No.** Adapter is Apple Metal, not SwiftShader | WebGPU info |
| Viewport A | CSS 1440×900, `devicePixelRatio=1` | environment.json |
| Screen (Playwright context) | 1440×900 | environment.json |
| Language | en-US | environment.json |
| Hardware | 18 threads, 32 GB `deviceMemory` | environment.json |
| Network | `navigator.onLine=true`; live Mux HLS + site origin | environment.json / console.json |
| Refresh | median rAF interval ≈ 8.3 ms → **estimated 120 Hz** | `estimatedRefreshHz: 120`, `frameIntervalsMs` |
| Full URL | `https://infinite-liquid-glass.shader.se/?v=2` | environment.json |
| Page title | Infinite Liquid Glass \| Shader Development Studio | environment.json |
| Load to first ready frame (A) | 17122 ms | `loadMs` |
| Scene ready | `ready: true`, loading `%` gone, canvas present | environment.json |

Capture notes:

- Probe pass earlier the same hour: `artifacts/reference/probe/` at 2026-08-18T18:07:10.957Z.
- Full pass: `scripts/capture-reference.mjs`. Viewports A–E screenshots + JSON succeeded.
- Named interaction videos (`artifacts/video/reference-*.mp4`) are **blocked**: Playwright ffmpeg binary missing after viewport capture. Do not invent motion curves from memory.
- Playwright traces (`artifacts/traces/`) are **missing** in the workspace after the failed video stage.

---

## 2. Five viewport results

All five used the same Chrome 151 + Apple M5 Max WebGPU path. Loading copy is black + SHADER mark + percent on every viewport.

### A — 1440×900 DPR 1 (primary)

| Item | Evidence |
| --- | --- |
| Canvas | `class=r3f-canvas`, CSS 1440×900, buffer **1440×900** |
| Engine attr (probe HTML) | `data-engine="three.js r185 webgpu"` |
| Console | React Three Fiber v10 ALPHA banner |
| Ready overlay IDs | ILG—33…37, 44…47, 54…56, 64 (DOM slice) |
| Visible glass rows | 3 (top clipped, mid brick, bottom) |
| Background gutter | median `#000417` / `rgb(0,4,23)` at y≈442 |
| Overlay | `AN EXPERIMENT BY` + Shader img at y=860.16; `BOOK A CALL ↗` at (1258.09, 832.41) 161.9×47.6 |
| Interaction set | 01–19 including drag, flick, wheel, 30s stress, resize 1100×720, blur/focus |
| Load | 01=0%, 02=25%, 03 **53%** (poll threshold was ≥50), then scene |

### B — 1920×1080 DPR 1

| Item | Evidence |
| --- | --- |
| Canvas | CSS 1920×1080, buffer **1920×1080** |
| Overlay IDs | same rest catalog as A (ILG—33…) |
| Brick x of mid tiles | nx≈0.311 and 0.688 (same normalized columns as A) |
| Mid unclipped size | 696×430 px = **0.363 × 0.398** of viewport |
| Bottom row pixel boxes | lower confidence (detector split a dark tile); DOM AABB still shows ILG—54/55/56 on a lower row with ILG—55 centered at x≈960 |
| Overlay | experiment link (20, 1040.16); CTA (1738.09, 1012.41) 161.9×47.6 |
| Interaction | **staticOnly** — no drag/flick/wheel on B |

### C — 1440×900 DPR 2

| Item | Evidence |
| --- | --- |
| CSS viewport | 1440×900, `dpr=2` |
| Canvas buffer | **2880×1800** (full 2×, not clamped) |
| Overlay CSS rects | identical to A (same CSS layout) |
| Screenshot pixels | 2880×1800 |
| Normalized bottom-center | nx=0.499, ny=0.727, box 1071×778 → CSS **535.5×389**, matches A Infinite City 536×389 |
| Normalized mid-left | nx=0.311, box 1040×776 → CSS **520×388** vs A 521×364 (height differs by detect scale; x/width agree) |
| Interaction | **staticOnly** |

### D — 390×844 mobile DPR 3

| Item | Evidence |
| --- | --- |
| CSS | 390×844, `isMobile=true`, `dpr=3` |
| Canvas buffer | **585×1266 = 1.5× CSS**, not 3× |
| Screenshot | 1170×2532 (Playwright still captures at context DPR) |
| Ready overlay IDs | ILG—27…29, 36–37, 43–45, 52–53, 59–61 (different window into the same catalog) |
| Visible | ~4 staggered rows; one dominant full tile near (0.50, 0.37) |
| Center tile (Outer Office) | 833×599 screenshot px → CSS ≈ **278×200**; nx=0.498, ny=0.371 |
| Edge yaw | left top-edge **+26.4°**, right **−29.1°** (same sign pattern as desktop, stronger) |
| Overlay | stacked column: experiment (20, 783.64) 115.8×39.5; logo under it (20, 809.56) 101.4×13.6; CTA (233.22, 782.80) 136.8×41.2 |
| Link class | `flex flex-col lg:items-center gap-3 lg:flex-row` — mobile column, `lg` row |
| Interaction | full drag/flick/wheel set captured |

### E — 844×390 mobile landscape DPR 3

| Item | Evidence |
| --- | --- |
| CSS | 844×390, `dpr=3` |
| Canvas buffer | **1266×585 = 1.5× CSS**, not 3× |
| Ready overlay IDs | ILG—24…27, 33…37, 44…47 |
| Visible | 2 primary rows; top-center nx=0.499, ny=0.238 |
| Overlay | experiment (20, 324.23) 148×45.8 stacked; CTA (687.22, 326.52) 136.8×41.2 |
| Interaction | **staticOnly** |

### Cross-viewport conclusions

- Desktop DPR 1 and 2: canvas buffer = CSS × min(dpr, 2) in this sample (C uses 2.0).
- Mobile DPR 3: canvas buffer = CSS × **1.5**. Exact clamp function not in captured JS (forbidden to read bundles). Record as observed only.
- Tile **normalized width** of a full mid/bottom tile is ≈ **0.36–0.37** on landscape desktop and landscape mobile; portrait mobile uses a much wider hero tile (≈0.71 of screenshot width).
- Rest pose on A/B/C starts at the same catalog window (ILG—33…). D/E open on a different window. Initial camera/grid offset is **viewport-dependent**.

---

## 3. Composition, geometry, curvature, nine landmarks

Primary frame: `A-1440x900-dpr1/06-rest-5s.png` (idle 5 s, tiles not translating). Pixel method: dark-navy gutter mask `R≤8, G≤14, maxRGB≤36`, split into row bands, then through-gutters. Debug overlay: `artifacts/reference/measurements/A06-debug.png`.

### 3.1 Composition

- Background is a dark navy void, **not** a photographic plate. Gutter median `#000417`.
- Glass tiles sit in a **brick / staggered grid**: odd visual rows have a tile on the vertical midline; the middle row straddles the midline.
- **Viewport center (0.50, 0.50) is a horizontal gutter**, not a tile center. y≈450 is 100% gap across the width.
- Visible structure at rest (A): 3 rows × (3 to 4) columns. Top row is a thin clipped cap. Middle row: 2 full tiles + 2 side clips. Bottom row: 1 full center + 2 side-clipped tiles.
- HTML overlay uses `perspective: 1000px` and a drei-style camera helper (`translateZ(1000px) matrix3d(1,0,0,0, 0,-1,0,0, 0,0,1,0, 0,0,-1000,1) translate(720px, 450px)`). That is **Perspective**, not Orthographic.

### 3.2 Camera estimate (from overlay, not guessed FOV)

At A, overlay `perspective = 1000px` and view height `900`:

```
tan(fov/2) = (height/2) / perspective = 450 / 1000 = 0.45
fov ≈ 48.5° vertical
```

This is consistent with a Three.js `fov` near **50°** (exact 50° would give perspective ≈ 965 px). B/D/E computed `perspective` was **not recaptured** (`missing`).

Camera distance in world units: **missing**. The HTML helper places the matching plane 1000 CSS-px from the camera; scene units may be scaled. Do not assume 1 world unit = 1 pixel until Phase A locks a scale.

Look-down: bottom unclipped tile (536×389) is slightly larger than mid unclipped tile (521×364). Compatible with a camera slightly above the grid, but the difference is also partly clipping/detect error. Treat as **weak**.

### 3.3 Tile size (A / 06)

| Tile | Role | Box (px) | Normalized size | Notes |
| --- | --- | --- | --- | --- |
| Slow Signal | mid-left full | **521×364** | **0.3617 × 0.4050** | best mid-row size reference; not clipped |
| Field Notes | mid-right full | 520×359 | 0.3609 × 0.3987 | cy biased down by dark video; use y=0.281 with Slow Signal |
| Infinite City | bottom-center full | **536×389** | **0.3719 × 0.4325** | on x midline; largest full tile |
| Free State / Glass House | bottom sides | 425×389 / 428×389 | — | left/right clipped; AABB narrower |
| Mid side clips | — | 164×364 | 0.114 × 0.405 | mostly glass sidewall + sliver |

Aspect of mid full tile: 521/364 = **1.43**. Bottom full: 536/389 = **1.38**.

QA primary size (Phase A): use **Slow Signal 521×364** as mid-row hero and **Infinite City 536×389** as midline-x tile. Tolerance later: width/height error < 3%.

### 3.4 Spacing (A / 06)

Through-gutters between bottom tiles: **25.9 px** (left gap) and **24.8 px** (right gap).  
Horizontal gutter band between mid and bottom rows: y=437–459 → **≈23 px**.

Use **24–26 px** gutter at 1440×900 (≈ **0.017–0.018** of viewport width, ≈ **4.8%** of mid-tile width).

B mid-row normalized columns match A, so gutter fraction should stay similar; B pixel gutter was not as cleanly isolated (`lower confidence`).

### 3.5 Corner radius, bevel, thickness

| Quantity | Measurement | Confidence |
| --- | --- | --- |
| Corner radius (Infinite City top-run method) | **61.3 px** ≈ 0.114 × width | medium (top-run under/over-shoots on glass rims) |
| Corner radius (Slow Signal) | 24.2 px | low; dark/bright mix shortens top run |
| Visual (screenshot, not pixel-fit) | large squircle, rim occupies a thick band | qualitative only |
| Rim / bevel band on Infinite City | **18 px** along mid scanline | medium |
| Bevel segment count | **missing** — cannot count subdivisions from a PNG | — |
| World thickness | **missing** — no calibrated units | — |
| Screen-space side wall | edge tiles show extra glass side; mid-left clip is 164 px of mostly sidewall | qualitative |
| Front convex / “puff” | highlights wrap the front; content bends into the rim. **Slight front convexity possible**, not proven by a depth buffer | weak |
| Shared geometry | every tile uses the same HTML card template (`@container` + identical type system). 3D mesh almost certainly instanced / shared | inferred from DOM, not from GL |

Do not implement “Apple Liquid Glass” from memory. Match **this** rim: dark navy behind, video inside, 18 px chromatic rim, sharp top-left/top-right spec highlights.

### 3.6 Grid curvature

Edge top-edge slopes on A / 06 (image y downward):

| Tile | Tilt | Meaning |
| --- | --- | --- |
| Mid-left clip | **+2.54°** | outer (left) end of top edge is higher |
| Slow Signal | −0.97° | nearly flat |
| Infinite City | **−0.15°** | face-on |
| Glass House | **−3.03°** | outer (right) end higher |
| Mid-right clip | −2.99° | same sign as right side |

Signs match **outer edges closer to the camera** (left tile top edge slants down toward center; right tile slants down toward center). Combined with visible side thickness, this is a **concave-from-camera** arrangement: cylindrical inner wall, shallow bowl, or yaw-only carousel — **not** a flat plane.

Vertical size change (bottom slightly larger than mid) is small. A **single-axis yaw cylinder** (vertical axis) is the best-supported model. Dual-axis / sphere is **not proven**. Orthographic is ruled out.

### 3.7 Nine landmark centers (A / 06, normalized)

`nx = cx / 1440`, `ny = cy / 900`. Top row from the y=0–25 gutter split on the same PNG. Mid/bottom from `landmarks.json`.

| Name | nx | ny | px center | Identity / note |
| --- | --- | --- | --- | --- |
| 左上 upLeft | **0.1392** | **0.0144** | (200, 13) | top row, heavily clipped |
| 上 up | **0.4990** | **0.0144** | (719, 13) | top row, heavily clipped |
| 右上 upRight | **0.8594** | **0.0144** | (1238, 13) | top row, heavily clipped |
| 左 left | **0.3098** | **0.2809** | (446.2, 252.8) | Slow Signal, 521×364 |
| 中心 center | **empty at (0.50, 0.50)** | — | gutter | see nearest midline tile below |
| 右 right | **0.6912** | **0.2809** | (995, 253) | Field Notes; **report y=0.2809** (row band), not the biased 0.335 detect cy |
| 左下 downLeft | **0.1428** | **0.7052** | (205.6, 634.7) | Free State, left-clipped |
| 下 down | **0.4991** | **0.7272** | (718.7, 654.4) | Infinite City, 536×389 |
| 右下 downRight | **0.8522** | **0.7271** | (1227.1, 654.4) | Glass House, right-clipped |

Extra (not in the nine, but measured):

| Name | nx | ny | note |
| --- | --- | --- | --- |
| midFarLeft | 0.0563 | 0.2718 | 164×364 clip |
| midFarRight | 0.9433 | 0.2783 | 164×364 clip |
| nearestMidlineTile | 0.4991 | 0.7272 | Infinite City — closest full tile to x=0.5 |

Phase A pass rule (from product brief): nine centers within **2% of viewport**. Use the table above as the rest-pose truth for A.

Idle 04 vs 06: the same seven boxes stay put (Δn < 0.01 except Free State cy noise). **Tiles do not drift at rest**; MAE≈20 is video playback inside the glass.

---

## 4. Glass material estimate

Observed on A 04/05/06 and interaction frames. Not reverse-engineered from JS.

| Parameter | Estimate | Evidence | Confidence |
| --- | --- | --- | --- |
| Transmission | High on the glass shell; **content is a video plane inside/behind the shell**, not the navy void | video readable in the face; navy shows in gaps | high |
| Opacity of face | Face is clear; not a milky card | screenshots | high |
| Roughness | Low: sharp white spec streaks on upper rims | screenshots | high |
| IOR | Glass-like (start ~1.45–1.5 in Phase C) | edge magnification of video into the rim | medium |
| Thickness | Real 3D slab, not a plane + backdrop-filter | side walls on edge tiles; inner content recedes | high |
| Attenuation | Weak / not obvious (no heavy colored glass body) | screenshots | low |
| Fresnel | Rim brighter than face; grazing edges pick up env | rim Luma P95 ≈ 20–60 vs dark gutters | medium |
| Dispersion | **Present, rim-only** | `rimChromaRB` 18–29 on full tiles vs lower interior; RGB fringe in screenshots | high |
| RGB split direction | Along the rim / curvature, not a full-screen CA pass | screenshots | high |
| Rim highlight width | ≈ **18 px** on Infinite City at 1440×900 | scanline | medium |
| Rim highlight intensity | Near-white streaks, especially top-left and top-right | screenshots + `highlightOffset` toward top | high |
| Interior blur | Face is sharp; blur lives in the thick rim | screenshots | high |
| Background refraction | Navy void has little to refract; **neighbor tiles and inner video bend in the rim** | screenshots | high |
| Double rim | Possible inner content plane + outer bevel; not isolated as two meshes | screenshots | low |
| Internal reflection | Not isolated | — | missing |
| Tone mapping | HDRI + unclipped-but-controlled highlights | HDRI fetch + screenshots | low |
| Environment reflection | **Yes** | `GET /hdri/studio_small_03_1k.hdr` | high |

Do **not** ship a white translucent card, a CSS `backdrop-filter` fake, uniform alpha, or full-frame chromatic aberration.

Baseline for Phase C: Three.js physical / TSL transmission + thickness + ior + dispersion + the captured HDRI (own licensed copy). Custom TSL only if the baseline misses the rim.

---

## 5. Lighting and background

| Item | Finding | Confidence |
| --- | --- | --- |
| Background color | Gutter `#000417` (A/C/E), `#000418` (B), `#00010a` (D). Loading `#0a0a0a` | high |
| Background gradient | No strong vignette in corners (corners are tiles). Navy is even in gutters | high |
| Environment map | **Yes**: `https://infinite-liquid-glass.shader.se/hdri/studio_small_03_1k.hdr` (Polyhaven-style name). **Do not hotlink or copy from the target host.** Use an independently obtained licensed HDRI | high |
| Extra image lights | Not counted. Sharp rectangular specks on rims are consistent with a studio HDRI | medium |
| Key / highlight direction | Above and slightly in front; top-left and top-right rim streaks | high |
| Fill / ambient | Dark; tiles are the bright objects | high |
| Shadows on the void | **None** visible | high |
| Contact shadow | **None** visible | high |
| Bloom | At most a weak halo on the brightest rims; no crushed bloom | low |
| Vignette | **Not observed** | medium |
| Full-frame chromatic aberration | **Not observed** (rim only) | high |
| Tone mapping / exposure | **missing** as a numeric value | — |

Implement only what is observed: navy clear color, studio HDRI reflections, no drop shadows, no heavy bloom, no vignette.

---

## 6. Interaction and motion fit

Inputs exercised on A (and D): center hover, slow left drag −400 px / 40 steps, diagonal −180/−140, flick −520 x, wheel (0,900) then (900,0), 30 s stress, resize, blur/focus.

### 6.1 Rest and hover

| Pair | MAE | Phase shift | Read |
| --- | --- | --- | --- |
| 04→05, 05→06 | ≈20.5 | (0,0), peak≈568 | video plays; **grid does not translate** |
| 06→07 mouse to (720,450) | 11.2 | (0,0), peak≈681 | **no whole-grid hover parallax** |
| 06 vs 19 blur/focus | captured | — | screenshot exists; no obvious freeze artifact in the still. Motion-during-blur is **missing** (no video) |

Per-tile hover scale: **missing** (no isolated hover-on-tile vs hover-on-gap pair).

### 6.2 Slow drag (A 07→08, input −400 px x, still held)

Field Notes (unclipped mid-right) nx **0.691 → 0.463**, Δnx = **−0.228** → **Δx ≈ −328 px**.

Infinite City nx **0.499 → 0.286**, Δnx = **−0.213** → **Δx ≈ −307 px**.

**Screen follow ratio ≈ 0.77–0.82** (not 1:1). Perspective makes rows disagree slightly.

Direction: drag left → tiles move left → new tiles enter from the right. Content follows the pointer.

07→08 phase correlation failed (peak 39) because the move is not a pure 2D translation.

### 6.3 Diagonal drag (A 09)

After release + 1800 ms, a new drag −180/−140 from center. Tiles appear at new nx **and** ny (e.g. a full tile at ny=0.624 vs rest 0.727). **X and Y are both live.**

Clean gain for this stroke is **missing**: there is no screenshot of the settled-after-08 pose, so 09 cannot be subtracted from a known origin.

Whether diagonal input is normalized to unit length: **missing**.

### 6.4 Flick (A 10–14)

Gesture: fast move −520 x, 4 steps, then release.

| t from flick still | File | MAE vs previous | Grid |
| --- | --- | --- | --- |
| 0 ms | 10 | — | new catalog (Glass House / Echo Chamber / Second Nature) |
| +424 ms | 11 | 71.9 | still moving |
| +850 ms | 12 | 54.6 | still moving |
| +1517 ms | 13 | 22.1 | near idle-video MAE |
| +4190 ms | 14 | 21.0, peak 837 | **settled**; Drift State at nx=0.465, ny=0.504 |

Inertia lasts about **1.0–1.5 s** after this flick. Half-life is **not fitted** (no tracked landmark time series, no video). Mark `missing` for exact `damping` and `v *= exp(-k Δt)` constants.

13→14 MAE matches idle video: no snap-back, no oscillation visible in stills. **Spring/snap-to-tile: not observed.** Stop threshold reached by ~1.5 s.

Max speed: **missing** (no video / no timestamped centroid trail during the 4-step flick).

### 6.5 Wheel (A 14→15→16)

| Input | Result |
| --- | --- |
| wheel (0, 900), wait 80 ms | tile nx/ny **unchanged** at 0.001; MAE 10 | 
| wait 1200 ms + wheel (900, 0), wait 80 ms | Drift State 0.465→0.463; MAE 20 |

Wheel gain is **very small in these stills**, delayed beyond 80 ms, or mapped weakly. **Do not invent a wheel-to-world ratio.** Re-capture with larger deltas and longer waits (`missing`).

Trackpad pixel-delta vs wheel: **missing**.

### 6.6 Pointer model (DOM / CSS)

- `html, body { overflow: hidden }`
- `body { user-select: none }`
- `touch-action: auto` (not `none`)
- `overscroll-behavior: auto`
- Canvas container is `pointer-events: auto`; tile HTML overlay is `pointer-events: none`; footer links are `pointer-events: auto`
- Buttons array empty; CTA is an `<a>`
- Pointer capture / lost-pointer recovery: **missing** (not instrumented)

### 6.7 Refresh independence

All samples are ~120 Hz. 30 Hz / 60 Hz comparative motion: **missing**. Implementation must still use delta-time damping.

### 6.8 Touch vs mouse

D captured a drag/flick set. A dedicated `touchscreen` video is **blocked** (ffmpeg). Whether touch uses the same integrator: **not proven**. Treat as the same model until a touch video exists.

### 6.9 Resize and stress

- `18-resize-1100x720.png`: layout still brick glass; overlay remains. Tile CSS size reflows. Pixel nine-set for 1100×720 not promoted to QA truth yet.
- `17-stress-30s.png`: still exists after 30 s of fast drags — page did not crash in this capture. Seam/jump during the 30 s is **missing** without video.

---

## 7. Infinite-loop logic

| Question | Judgment | Evidence |
| --- | --- | --- |
| What moves? | **The tile field**, not a camera orbit. Overlay cards are parented to a camera-matched CSS 3D layer; their AABB travel with the grid | drag stills; `will-change: transform` cards |
| Recycle / wrap | **Catalog reuse is proven; spatial modulo is not fully proven** | ILG—34 and ILG—64 share title “New Rituals”; HTML starts at ILG—01; flick reaches ILG—59/60/69. A full return to the A-rest pose was **not** captured |
| Modulo | Likely logical (i,j) + modulo into a finite catalog | inferred from repeating titles and dense ID space; **not** read from JS |
| Logical vs display coords | Overlay IDs stay attached to cards as they move; new IDs enter from the incoming edge | 08/10/14 titles |
| High-speed seams | **missing** (no 30 s video) | stress still only |
| Float drift | Idle 5 s: no centroid drift | 04 vs 06 |
| Content remap | Each cell has its own Mux stream + HTML copy. Recycled cells must swap video + text together | network + overlay |
| Empty holes | Not seen during drag/flick stills | 08, 10, 14 |

Working hypothesis for Phase A: 2D integer lattice on a curved surface, wrap with modulo over a finite item list, recycle meshes, never wait on Mux in the local build (placeholders).

---

## 8. DOM / Canvas / Overlay / Loading / Fonts

### 8.1 Document

- Next.js (Turbopack chunks, `_next/static`)
- `html` classes: `geist_*` variable fonts, `h-full antialiased`
- `body`: `m-0 h-full overflow-hidden select-none`
- `theme-color` `#000000`, `color-scheme: dark`
- Viewport meta: `width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover`

### 8.2 Canvas

- One canvas: `class="r3f-canvas"` inside `.r3f-canvas-container`
- Style `display:block;width:100%;height:100%`
- Probe: `data-engine="three.js r185 webgpu"`
- Console: `React Three Fiber v10 is in ALPHA`
- Stack implication: **R3F v10 + Three r185 WebGPU**. Local rebuild should **not** copy their app; vanilla Three + WebGPURenderer is the planned stack.

### 8.3 Tile HTML overlay (not in the canvas)

Fixed layer `pointer-events-none fixed inset-0 z-5` with `transform-style: preserve-3d; perspective: 1000px`.

Each tile card (`@container absolute …`):

- Type: mono meta `text-[1.7cqw] tracking-[0.18em] uppercase`
- ID color is per-tile (examples from probe HTML: ILG—01 `rgb(215,255,63)`, ILG—02 `rgb(255,154,213)`, ILG—03 `rgb(143,247,255)`, ILG—04 `rgb(255,204,102)`)
- Title: `text-[12cqw] leading-[0.82] font-semibold tracking-[-0.085em]`
- Deck: `text-[2.5cqw] text-white/82`
- Padding `p-[7cqw]`; hairline `h-[0.2cqw] bg-white/55`
- Off-screen / back-facing cards: `visibility: hidden; backface-visibility: hidden`

Local Phase E may recreate this as HTML-over-WebGPU (same as origin) or as in-mesh text. Origin uses **HTML**.

### 8.4 Footer overlay (measured)

**A 1440×900**

| Control | Box | Type |
| --- | --- | --- |
| “AN EXPERIMENT BY” | (20, 860.16) 303.8×19.8 (link); Geist 16/400, color `rgb(237,237,237)` | `<a href="https://shader.se/">` |
| Shader wordmark `<img alt="Shader">` | (175.77, 860.16) 148×19.8 | brand asset — **placeholder only** |
| “BOOK A CALL ↗” | (1258.09, 832.41) 161.9×47.6 | `<a href="https://cal.com/simon-hedlund-kglzne">` |

CTA computed style (A): Geist Mono 11.52px, tracking 1.84px, pill `border-radius` huge, `py-2 pr-2 pl-4`, `bg-white/8`, `border-white/22`, `backdrop-blur-2xl`, hover `border-white/38 bg-white/12`, `active:scale-[0.98]`. Hover stills: **missing**.

**D 390×844**: column stack, 20 px inset, CTA moves left (not a far-right desktop pill).

### 8.5 Loading

Frames 01–03 on every viewport.

| Item | Measurement (A) |
| --- | --- |
| Background | `#0a0a0a` (corners), plus a faint center glow |
| Cluster bbox | (654, 387) 132×126 |
| Cluster center | **(720, 450)** nx=0.500, ny=0.500 |
| Mark | rainbow-striped pill + italic serif **SHADER** |
| Percent | 0% → 25% → **53%** (not a clean 50). 75% and 100% isolated frames: **missing** |
| Exit | percent node disappears; canvas + overlays appear. Fade timing: **missing** (no video) |

Loading DOM was collected **after** ready, so the loader markup is **missing** from `dom.json`.

### 8.6 Fonts

Network: 2 woff2

- `/_next/static/immutable/media/caa3a2e1cccd8315-s.p.0zr6hhvz-h9nw.woff2` (29288 B)
- `/_next/static/immutable/media/797e433ab948586e-s.p.1v5bejj26fx9h.woff2` (23108 B)

`document.fonts`: **Geist** and **Geist Mono** (variable 100–900) + fallbacks.

**Do not copy those woff2 files from the target host.** Geist is OFL; Phase E should pull an official licensed distribution (or a documented substitute). SHADER wordmark is a **serif italic brand face**, separate from Geist — treat as placeholder art.

---

## 9. Resources

| Kind | Origin evidence | Local rule |
| --- | --- | --- |
| Tile motion pictures | **19 unique Mux HLS playback IDs** (see below). Chunks from Fastly/Cloudflare Mux | **Must not copy or hotlink.** Local tiles use original placeholder video or generated loops |
| HDRI | `/hdri/studio_small_03_1k.hdr` | Independently obtain a licensed studio HDRI (Polyhaven `studio_small_03` is the likely public counterpart). **Do not fetch from shader.se** |
| Brand logo | `/logo.svg?dpl=…` | Placeholder rainbow-pill + “SHADER” stand-in |
| Favicon | `/icon.svg?icon.…` | Placeholder |
| OG image | `/og2.webp` 1200×630 (meta only) | Do not copy |
| Fonts | 2 woff2 Geist / Geist Mono | Official OFL build or substitute |
| CSS | one Next stylesheet | Restyle from measurements, do not copy |
| JS | 9 script requests | URLs recorded as `[script omitted]`. **Never download** |
| Procedural bg | Navy clear color; no second canvas | Recreate as clear color / tiny gradient if needed |
| Static tile photos | **None** in the rest network log | Do not substitute stills for a live texture unless quality tier Low |

Mux playback IDs observed on A (do not download):

```
3008Q00vG00WGS5IhJHhRkubiv00N7nbe00m9IDXrVD6Z01wI
600So4lU8EZDnUNUix3ct012OBmBLTLSMMoUoo02IUL02xU
8oWIbkfWIAWVGpd5mg5Meq7LxmJMChthdjv2YIeHH2Q
K1vWSoscB4tOmAKwKXLo7g1dNtfWRsFiNYS02tcEvUsc
Ohb3WcOspOgsZVc2Cwg9kZHe3wXWhUk00tmU58517dAg
SqmDcr700VRNWzZvew8jKGLKNayH472UU7kl02gAq6148
W2E02Ix66PEIAJcojVS7l1Qx01uWGHR00PAY2BlKpyYSEc
Y2wyYBsXzu4HwxmCuDU00wcjTKYKoCLfOK73ABab3LpY
Yhir8UDUrYPAQGN5iSjPQNgue02DFBW00vD5g2F9ga01Gc
adxYxwpRqr01ZiGtLNBMR02VFkNTuK101qIEg18lHjk8xU
b6NK9RZb59brkSX7trHXlFGqS2YCi4XTjAATtFuihbM
dRQc0202Rpk6WnvqSZFnETJvNIVi14HbkVHxWmKdeG7sI
hmLvA2vFgorNF1eLx01f1zAU00yZB5nLYYjqRK4breAO8
jbhP2TH9zUlFZVQ8udy8a2e3vKW5K2R23LEPbEGSg01Q
lWU9u01zkH02ycxnHlMLTdWh88ogfAEmbmn1Zu89FbjUU
mj702yexPh8lE76CkwfpbfDucX8TvixPHJho3WN165Is
sFSxFQmzcKGQ8csHrIDBlvBEGxDoZ1IxDvb3QAciEvY
sr5tcJQBZWP00IcHxTM29KVn1tpagnwATNw6LALqPmNo
zATEd1gHlsmUr3O8upcB01w02HBh5ocysNQb01GxxmmKjg
```

### Catalog (partial, from probe body + overlays + still titles)

HTML preview includes ILG—01 Afterimage, 02 Night Index, 03 Soft Power, 04…. Body at A rest includes 33 Soft Power, 34 New Rituals, 35 Elsewhere, 36 Common Sky, 37 Future Folklore, 44 Outer Office, 45 Slow Signal, 46 Field Notes, 47 No Fixed Form, 54 Free State, 55 Infinite City, 56 Glass House, 64 New Rituals (repeat), 65 Elsewhere, 66 Common Sky, 67 Future Folklore. Later stills: Echo Chamber, Second Nature, Drift State (ILG—59), Hard Light (ILG—60), Public Dream, Low Gravity, Afterimage, Deep Surface, Unfinished, Near Future, Outer Office, etc.

Local catalog should be **original placeholder copy**, not their case-study text, unless legal review says otherwise. IDs may be remapped.

---

## 10. Locked-dependency plan (suggestions only)

Do **not** pin in `package.json` until Phase 2 implementation. Observed vs suggested:

| Package | Observed on target | Suggested local start |
| --- | --- | --- |
| three | **r185** + WebGPU (`data-engine`) | `three@0.185.x` (match r185) |
| react-three-fiber | v10 ALPHA | **do not take** — vanilla Three |
| Next.js | yes (theirs) | **no** — Vite + TypeScript |
| Vite | — | Vite 6 or 7 |
| TypeScript | — | 5.8+ |
| Playwright | — | already `^1.59.1` |
| TSL / NodeMaterial | implied by r185 WebGPU glass | use Three TSL when implementing glass |
| ffmpeg (Playwright) | needed for official videos | `npx playwright install ffmpeg` before re-capture |

Quality switch later: WebGPU high / WebGL2 low. Fallback behavior on a machine **without** WebGPU: **missing** (this host has WebGPU).

---

## 11. Authorization boundary — must replace

| Asset | Action |
| --- | --- |
| All target JS / CSS bundles | Never download, never vendor, never cite URLs except `[script omitted]` |
| Mux videos and signed chunk URLs | Never copy, never hotlink |
| `/logo.svg`, `/icon.svg`, SHADER wordmark | Placeholder |
| `/og2.webp` | Do not copy |
| Hosted Geist woff2 | Do not copy from shader.se; use official OFL source or substitute |
| `/hdri/studio_small_03_1k.hdr` on their origin | Do not hotlink; obtain independently |
| Case-study videos, photography, and their marketing copy | Replace with original placeholders |
| Cal.com / shader.se link targets | May keep equivalent footer *behavior* with our own URLs if product wants; do not scrape their booking page |

Allowed: observe, measure, reimplement; licensed fonts/HDRI/video we own.

---

## 12. Missing / blocked checklist

1. Named reference videos (`reference-desktop-slow.mp4`, `reference-desktop-fast.mp4`, `reference-mobile.mp4`) — **blocked** (Playwright ffmpeg missing).
2. Playwright traces — **missing** on disk after the failed video stage.
3. Loading 75% and isolated 100% / fade-out timing.
4. Loading DOM structure (collected only after ready).
5. Book a Call hover / active stills.
6. Per-tile hover scale.
7. Wheel and trackpad gain (80 ms stills show ~0 translation).
8. Diagonal drag gain (no pre-stroke settle frame).
9. Damping / half-life / max speed numeric fit (needs video or high-fps centroid log).
10. 30 Hz / 60 Hz vs 120 Hz motion equality.
11. Touch vs mouse integrator proof (mobile video blocked).
12. Spatial wrap all the way back to the A-rest pose.
13. 30 s stress seam video.
14. WebGPU-unavailable fallback.
15. B/D/E CSS `perspective` computed value.
16. Bevel segment count, world thickness, IOR/roughness numbers from the engine.
17. Tone mapping name / exposure.
18. `capture-summary.json` — not written (script crashed after E).

---

## 13. Phase 1 non-goals

This spec is not a replica. No `src/` scene, no Three mesh/material/motion implementation, no hotlinked assets. Next document: `docs/implementation-plan.md`.
