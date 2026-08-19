# 00 — Root Cause Audit

Status: **Phase 0 complete. Do not tune shaders yet.**  
Date: 2026-08-18  
Local: `http://127.0.0.1:5280`  
Frozen target: `https://infinite-liquid-glass.shader.se/?v=2` is secondary. The hashes below are the only visual/motion truth.

This audit is based on current source, a live WebGPU probe on Apple M5 Max / Chrome, frozen recordings, and prior auditor captures. It does **not** start a rebuild.

---

## 0. Golden Reference (read-only)

Hashes generated 2026-08-18T19:49:50Z. Manifest: `qa/reference/GOLDEN.json`.

| Role | Path | Bytes | SHA-256 |
| --- | --- | --- | --- |
| Frozen target video | `/Users/xiaoli/Downloads/案例.mp4` | 27,416,575 | `3fe0369d8983be0c7cc41b717d1a1df91c37ce64ea152aeafa5648cf697483bc` |
| Frozen local baseline video | `/Users/xiaoli/Downloads/我的.mp4` | 16,599,123 | `18131e787c52fadc24a6e4ce1c3e2bfc6162e935f732616242c8728983a9e5f9` |
| User current screenshot | `…/assets/image-9aedbe35-88fc-44f9-9658-78099c802f00.png` | 58,647 | `9ef94aac91f203e33cd38c1d0326434b7f64a7c5d098aed874b1a83bfd1045f6` |
| User target screenshot | `…/assets/image-db3f635a-00bd-4266-8e99-f2c73d204e87.png` | 183,830 | `b8389f6d2ee2fd7ab9ddb15b79ab6b3250fb3a3ae39e0c23b4dc587e3624c283` |
| Auditor origin rest | `artifacts/auditor/reference/A-1440x900-dpr1/01-rest.png` | 1,535,778 | `fe8059af241c172027f9b21aa698071b888768c4a0cf3600a2b766e49e3a5c43` |
| Auditor origin remasure | `artifacts/auditor/reference/A-1440x900-dpr1/01b-rest-remeasure.png` | 1,577,560 | `c6ef8d1665845e7d70a76514f906bdf56658b29db3e6d8396f1e611c41abe83a` |
| Auditor origin landmarks | `artifacts/auditor/reference/A-1440x900-dpr1/tiles-rest.json` | 14,184 | `9a3612a7da0624d166167e2c0fd860e62d2d0bd047405b0e0aa010124f0464cf` |
| Developer origin rest | `artifacts/reference/A-1440x900-dpr1/06-rest-5s.png` | 1,681,817 | `3a02a010d1b122fec3c656258da6637c045a2b3858bc98c086aa4612a3a6e2ad` |
| Auditor local rest (round 2, pre-video) | `artifacts/auditor/compare-local/A-1440x900-dpr1/01-rest.png` | 161,604 | `f0171438206aecabf0e12f6f4a7761fd5e7ecd6f53d849266953ecee3dbf5cbf` |
| Auditor origin rest (round 2) | `artifacts/auditor/compare-origin/A-1440x900-dpr1/01-rest.png` | 1,368,294 | `774b268d2b72e18d2f877ad84fb908ad4cbcc1b27eeaba99284325a0bd131f0d` |

Live Phase 0 recapture (not golden, current code):

| File | SHA-256 |
| --- | --- |
| `qa/local/phase0/01-rest.png` | `f053446c2b5b67a66e60096e82bfbf1e29893e5982e4729d52e2a30702b556dd` |
| `qa/local/phase0/probe.json` | see file |

Frozen video facts (`ffprobe`):

- Target: H.264, 2752×1580, 30 fps, 8.27 s.
- Local baseline: H.264, 2792×1600, 30 fps, 4.73 s.

Later origin-site updates must not replace these hashes.

Legal constraint: rebuild observable layout, motion, and optics only. Do not copy Shader branding, Mux streams, or origin media.

---

## 1. Page composition

**Conclusion: one GPU canvas + DOM/CSS overlay hybrid. Not a multi-canvas GPU app. Not React.**

| Surface | What it is | Evidence |
| --- | --- | --- |
| `#viewport` canvas | Single `three.js r185 webgpu` canvas, CSS 1440×900, buffer 1440×900 at DPR 1 | Live probe `qa/local/phase0/probe.json` → `canvases[0].engine` |
| `#labels` | `CSS3DRenderer` DOM tree, `z-index: 5`, `pointer-events: none` | `src/ui/TileLabelLayer.ts` |
| `#page-overlay` | Footer chrome (ATELIER + Book a Call) | `src/ui/PageOverlay.ts`, `index.html` |
| `#loading-overlay` | Percent loader, hidden after `prepare()` | `src/ui/LoadingOverlay.ts`, `src/app/App.ts` |
| Hidden `<video>` × 3 | 2×2 CSS px, opacity 0.01, looped clips | Live probe `videoCount: 3`; `src/content/VideoClips.ts` |

Origin rest (auditor): also one WebGPU canvas, **0** DOM `<video>`, 16 HTML tile overlays, Mux HLS into the GPU. Local is structurally different on media: it parks real `<video>` elements in the document and blits them on the CPU.

No iframe. No screenshot disguise. GPU is real: `vendor=apple`, `architecture=metal-3`, `Apple M5 Max`, `isFallbackAdapter=null`.

There is no React render tree. Pointer motion does not set React state. That part is already correct.

---

## 2. Per-tile object count

Pool size is hard-coded `GRID.cols=5`, `GRID.rows=3` → **15 slots**.

| Object | Count per tile | Shared? | File |
| --- | --- | --- | --- |
| `Group` | 1 | no | `InfiniteGlassGrid.build` |
| Glass `Mesh` | 1 | geometry + material shared | `createGlassTileGeometry` + `createGlassMaterial` |
| Content `Mesh` | 1 | geometry shared; material per slot | `createContentGeometry` + `createContentMaterial` |
| Glass `Material` | 1 | **one for the whole pool** | `LiquidGlassMaterial.ts` |
| Content `Material` | 1 | **per slot** | `ContentMaterial.ts` |
| `Texture` | 0 unique | 3 `CanvasTexture`s reused by `clipIndex` | `VideoClips.ts` |
| CSS3D / DOM card | 1 `.tile-card` | no | `TileLabelLayer.attach` |
| Hidden `<video>` | 0 per tile | 3 global | `VideoClips.attachHiddenVideo` |

Live count: `tileCardCount: 15`, `slots: 15`, `textures: 3`, `videoCount: 3`, `canvasCount: 1`.

On wrap, the code does **not** create a new Mesh. It reassigns `material.map` and rewrites `innerHTML` on the existing CSS3D node (`InfiniteGlassGrid.update`, `TileLabelLayer.sync`).

That is a pool. It is the right *idea* and the wrong *size and placement*.

---

## 3. Card geometry: not a lens

**Conclusion: extruded rounded box + a smaller front plane. Not a thick convex volume.**

`GlassTileGeometry.ts`:

- Outline is a `Shape` with four `quadraticCurveTo` corners. That is a conventional rounded rectangle, not a superellipse / squircle.
- Body is `ExtrudeGeometry` with `bevelEnabled`, `bevelThickness=8`, `bevelSegments=4`, `curveSegments=8`.
- Front face is flat. There is no center-flat / rim-steep height field.
- Content is `PlaneGeometry(TILE.width * 0.9, TILE.height * 0.9, 1, 1)` — a 10% inset rectangle.

Node count (Three r185, same parameters):

| Mesh | Vertices | Triangles |
| --- | --- | --- |
| Glass extrude | 2,148 | 716 |
| Content plane | 4 | 2 |
| Per tile | — | 718 |
| Pool × 15 | — | 10,770 |

Renderer `info.triangles` at rest was **15,775**. The extra is consistent with transmissive extra passes / environment, not extra tile meshes.

`content.position.z = TILE.thickness * 0.5 + 1` places the media **in front of** the glass slab, toward the camera. The glass therefore cannot refract the media. It can only wrap a dark transmissive rim around an opaque billboard.

This is the architecture that must be replaced. Parameter tweaks on `MeshPhysicalNodeMaterial` cannot turn this into the target lens.

---

## 4. Where the black frame comes from

**Conclusion: architecture, not a CSS stroke and not a painted border mesh.**

Reproduction (current page, rest, 1440×900):

1. Open `http://127.0.0.1:5280`.
2. Wait for `__LIQUID_GLASS_QA__.getState().ready`.
3. Screenshot. Every tile shows a glossy dark rim around a flat inset movie.

Causal chain:

1. Clear / background color is `#000417` (`config.ts` `CLEAR_COLOR`, `RendererController`).
2. Glass uses `transmission = 1`, `ior = 1.45`, `thickness = 2.2`, `dispersion = 0.9`, `DoubleSide`, `depthWrite = true` (`LiquidGlassMaterial.ts`).
3. The only bright thing near the tile is the **smaller front plane**. The extruded rim therefore transmits the navy void and picks up studio-light specks.
4. The rim reads as a thick black bezel. Highlights sit on the bevel, not on a convex front.

Evidence:

- Live rest PNG `qa/local/phase0/01-rest.png`: inset video, hard inner rectangle, glossy dark surround, undistorted CSS titles.
- User current screenshot: same sandwich, plus a 14 px full-width near-black cap at the top (1024×588 capture).
- Auditor glass metrics (round 2, even before video): local landmark `|R−B|` median **6 / 6 / 6**; origin **21 / 5 / 28**. Local interior luminance ~156 on all three boxes; origin 143 / 101 / 9.
- Rest MAE origin vs local (round 2): **85.7**.
- Target / origin stills: no solid bezel. Dark rim is an optical pinch of the media into the edge.

There is no CSS `border` on `.tile-card`. There is no separate frame mesh. The “frame” is the extruded transmissive shell around an inset plane.

---

## 5. Media, type, and glass are not one texture

They are three independent layers, stacked in the wrong optical order.

| Layer | Implementation | In the glass volume? |
| --- | --- | --- |
| Media | `MeshBasicMaterial.map = CanvasTexture` | No. In front of the slab. |
| Glass | `MeshPhysicalNodeMaterial` | Yes, but it refracts the void, not the media. |
| Type | CSS3D HTML, `12cqw` title | No. In front of both. `bindCard` writes innerHTML. |

`catalogAt()` then **overwrites** every catalog title / code / deck with `CLIPS[index % 3]`. That is why the live grid only shows “牛来开场 / Cursor 牛来 / 鹈鹕测 AI” instead of the 24-item catalog. File: `src/content/catalog.ts`.

Origin (auditor, no bundle download): video is sampled inside the WebGPU canvas; HTML overlays exist for type; **0** DOM `<video>`. Type on the origin also looks HTML-sharp, but it sits on a refracted photographic face. Local type sits on a flat billboard.

Do not bake media + title + glass into one plane texture. The current split is directionally right and optically inverted.

---

## 6. Camera, grid, and tile transforms

### Camera

`RendererController`:

- `PerspectiveCamera`, `near=10`, `far=8000`.
- Position `(0, CAMERA.y=8, CAMERA.z=1000)`, `lookAt(0, 0, 0)`.
- FOV is derived from `perspectivePx=1000`: `fov = 2*atan((h/2)/1000)` → ~48.5° at 900 px. That matches the origin overlay helper.
- **Pointer never moves the camera.** There is no camera rig group.

### Grid group

`InfiniteGlassGrid.root` is an identity `Group`. It is never rotated or translated. All motion is per-tile `position` / `rotation`.

### Tile

`GridCurvature.placeTile`:

```
u = brickColumn(i,j) * cellW - scrollX
v = j * cellH + restY0 - scrollY
theta = u / radius
phi = v / radius
x = r sinθ cosφ
y = r sinφ
z = r (1 - cosθ cosφ)
rotY = -θ
rotX = φ
```

This is a shallow **sphere**, radius 3600. Origin evidence (`docs/reference-spec.md` §3.6, auditor tiles) is a **vertical-axis cylinder / yaw carousel**: outer edges closer, top-edge slopes about +2.5° / −3.0°. Dual-axis sphere is not proven on the origin.

`restY0 = -211.05` parks `j=0` on the bottom row and `j=1` on the mid row. `j=-1` projects to `ny ≈ 1.25–1.52` — **below the viewport**. The third row of the pool is wasted under the screen. The origin’s clipped top row (`cy ≈ -140 to -155`) has **no local counterpart**.

---

## 7. How input enters motion

`InputController` binds **both** Pointer and Mouse events on `window`, capture phase:

- `pointerdown/move/up/cancel`
- `mousedown/mousemove/mouseup`
- `wheel` (`passive: false`)

Touch rides on Pointer. There is no separate flick recognizer. Resize is a window listener + 80 ms timeout in `App.bindWindow`. Visibility only gates the tick body.

Critical path:

1. `pointermove` / `mousemove` call `motion.applyDrag(dx, dy, dt)` **immediately**.
2. `applyDrag` writes `scrollX/Y` and overwrites `velocityX/Y` from the last event interval.
3. `wheel` writes `scroll` and adds to velocity immediately.
4. `MotionController.step(dt)` runs in the RAF, but **returns while `dragging`**. During a drag, the RAF does not integrate. The event stream *is* the integrator.

This violates the required model: events only set targets; one RAF owns transforms.

There is **no hover pointer**. `onPointerMove` returns if `!dragging`. A synthetic `pointermove` to (80,80) after `reset()` left every landmark unchanged (`probe.json` → `hover`).

Missing motion layers (all absent in code):

1. Grid translation — present.
2. Root / camera-rig tilt — absent.
3. Camera XY parallax — absent.
4. View / light direction into glass — absent. Lights are baked once in `StudioEnvironment.addStudioLights`.

QA name is `__LIQUID_GLASS_QA__`, not `__ILG_QA__`. Missing: `setPointer`, `getAssetState`, `getPoolState`. `setTime` only stores `elapsed`; it does not seek video.

---

## 8. Per-frame work

| Mechanism | Present? | File |
| --- | --- | --- |
| Single RAF | Yes, `App.tick` | `App.ts` |
| Extra RAF per tile | No | — |
| `setInterval` | No | — |
| `setTimeout` | Resize debounce 80 ms; loader hide 480 ms | `App.ts`, `LoadingOverlay.ts` |
| React state | No | vanilla TS |
| Layout reads in the loop | No `getBoundingClientRect` | CSS3D uses object transforms |
| CSS3D render | Every frame | `RenderPipeline.draw` |
| CPU video blit | Every frame, 3× 960×540 `drawImage` + `needsUpdate` | `ClipReel.pump` |
| Adaptive quality apply | **Sampled, never applied** | `App.tick` calls `quality.sample`; never `grid.setQuality` |
| Allocations in tick | `frameTimes.push/shift`; `AdaptiveQuality` copies and sorts the frame array | `App.ts`, `AdaptiveQuality.ts` |

`AdaptiveQuality` can flip `level`, but the grid keeps the high-quality extrude and material until a QA hook calls `setQuality`. The hysteresis exists only on paper.

---

## 9. When media becomes a texture

`ClipReel.load` (`VideoClips.ts`):

1. Create a hidden `<video src=/clips/… preload=auto>`.
2. Wait for `loadeddata` or `canplay` (`readyState >= HAVE_CURRENT_DATA`).
3. `play()`.
4. Create a 960×540 2D canvas, `drawImage` once, wrap in `CanvasTexture`.
5. Advance the loader percent.
6. `App.start` then `grid.build`, one `grid.update`, one `labels.sync`, then `loading.hide()`.

Not waited:

- `video.decode()` / first-frame decode beyond `HAVE_CURRENT_DATA`
- GPU upload of the canvas
- Shader / pipeline compile
- A warmup `render()`
- Per-visible-tile `ready`

So the overlay can disappear on “element has some data,” not “the overscan set is on the GPU.”

Clip files (local, not golden):

| File | Size | Video | FPS | Duration | SHA-256 |
| --- | --- | --- | --- | --- | --- |
| `public/clips/niulai-intro.mp4` | 614,135 | 960×540 H.264 | 24 | 5.0 s | `bf0a8c05af950e9381653c155ccb5fc37497ae91c04f841d483628b7c894b404` |
| `public/clips/cursor-niulai.mp4` | 1,346,708 | 960×556 H.264 | 30 | 5.0 s | `d13233b63e2fd5f07e1de92311cbee3630d13455428edd5e84009f2121afb8c6` |
| `public/clips/pelican-ai.mp4` | 678,999 | 960×540 H.264 | 30 | 5.0 s | `f99086ad8abbd22c3bc5e9fd1654a3ccf798b87195506f4cee621d170f1798e1` |

Three clips for fifteen tiles. After wrap, `material.map` is swapped to another of the same three textures. No new download on drag in the Phase 0 probe (`networkHosts: ["127.0.0.1:5280"]`, 9 media requests, all during load, all three URLs).

Origin (auditor network, no bytes saved): 19 Mux playback IDs, 116 video chunks. Local must not copy those.

`tests/visual.spec.ts` still asserts `document.querySelectorAll("video").length === 0`. That test is already false against current code.

---

## 10. Tile create / destroy during motion

Short drag probe (−400 px, then coast):

- Slot count before: 15. After: 15.
- Logical indices shifted (`-2…2` → `-1…3` on wrap). That is modulo remapping, not mount/unmount.
- No React tree, so no React remount.
- Geometry is not recreated on wrap.
- Labels **are** rewritten (`innerHTML`) when `(i,j)` changes.
- Content material `map` is replaced when `clipIndex` changes.

This is not “spawn when entering the viewport.” It is a fixed pool that is **too small and biased downward**, so the top of the screen still goes empty.

---

## 11. Live GPU / frame numbers (this machine)

Device: Apple M5 Max, Chrome, WebGPU metal-3, viewport 1440×900 DPR 1. Not SwiftShader.

| Metric | Rest (after reset) | After drag + coast |
| --- | --- | --- |
| Display | ~120 Hz (median 8.3 ms) | same |
| RAF P50 | 8.30 ms | 8.30 ms |
| RAF P95 | 9.40 ms | 9.30 ms |
| RAF P99 | 9.40 ms | 9.40 ms |
| Draw calls | **491** | **1,329** |
| Triangles (`info`) | 15,775 | 15,773 |
| Texture objects | 3 | 3 |
| JS heap / GC / Long Task | **not captured this phase** | — |
| GPU time | **not captured** | — |

`renderer.info.reset()` runs every frame, so draw-call counts are per-frame, not cumulative.

491 → 1,329 draw calls for 15 transmissive `MeshPhysical` tiles is the smoking gun for hitch risk. Three.js transmission re-renders the scene per object. A 60 s random drag was not run in Phase 0; the 4 s coast already shows the call count exploding while mesh count stays 15.

Origin P95/P99 on the same box is **missing**. `qa/performance-qa.md` says so. Local 8.3 ms only proves vsync-limited idle on M5 Max. It does not prove the path will hold when glass is real.

VRAM: not queried. Lower bound from code: 3 × 960 × 540 × 4 ≈ 6.2 MB of canvas textures, plus PMREM, plus video decoder surfaces. Not a 4K-per-tile problem yet. The problem is **upload every frame**, not resolution.

---

## 12. Layout vs origin landmarks (A 1440×900)

Origin truth: `artifacts/auditor/reference/A-1440x900-dpr1/tiles-rest.json`.  
Local truth: live `probe.json` projected centers + CSS3D `getBoundingClientRect`.

| Slot | Origin center | Local projected center | Δ viewport | 2% pass |
| --- | --- | --- | --- | --- |
| Top L / C / R | cy ≈ −140 to −155 | **no pool row** | — | **FAIL** |
| Mid L | (441.1, 237.2) | (436.6, 233.5) | −0.32%, −0.42% | pass |
| Mid R | (998.9, 237.2) | (1003.4, 233.5) | +0.32%, −0.42% | pass |
| Mid L clip | (−49.1, 245.8) | (−204.3, 213.5) | −10.8%, −3.6% | **FAIL** |
| Bot L | (181.4, 660.4) | (137.8, 671.9) | −3.03%, +1.28% | **FAIL** |
| Bot C | (720.0, 661.0) | (720.0, 661.9) | 0.00%, +0.10% | pass |
| Bot R | (1258.6, 660.4) | (1302.2, 671.9) | +3.03%, +1.28% | **FAIL** |

Overlay box sizes (CSS3D AABB, not glass pixels):

| Slot | Origin | Local | Δ size | 3% pass |
| --- | --- | --- | --- | --- |
| Mid L / R | 533.9 × 408.1 | 569.1 × 421.8 | +6.6% W, +3.4% H | **FAIL** |
| Bot C | 550.0 × 403.2 | 548.0 × 405.6 | −0.4% W, +0.6% H | pass |

Spacing:

| Gap | Origin | Local | Notes |
| --- | --- | --- | --- |
| Mid overlay 45→46 | 23.81 px | 17.54 px | −26% |
| World cell − tile | — | X 17.72, Y 23.80 | `cellW/H` in `config.ts` |
| Visual PNG gutter (origin) | ~16 px | — | overlay ≠ glass |

Dark full-width bands (near-black ≥90% of row):

| Image | Bands |
| --- | --- |
| User target screenshot | **none** |
| Auditor origin rest 1440×900 | **none** |
| User current screenshot | top 14 px; mid-gutter cluster 15+3+2+11 px |
| Live local rest 1440×900 | y=420 h=18; y=447 h=6; y=461 h=16 |
| Auditor local rest (round 2) | same mid-gutter cluster |

Milestone 1 gate (“no >4 px continuous near-black full-width band”) **fails today**.

Coverage: origin keeps a clipped top row and a clipped bottom row at rest. Local mid row starts at `y ≈ 16` (almost fully on screen) and has **no** tile whose center is above the viewport. Requirement “permanent 2-row / 2-col overscan” is not met. A 5×3 pool cannot do it.

---

## 13. Motion vs origin (same −400 px script)

Local (`qa/local/phase0/probe.json`):

| t | `scrollX` | `velocityX` |
| --- | --- | --- |
| Hold end (−400 px, 40 steps) | 312 | 941 |
| Release | 312 | 941 |
| +250 ms | 512 | 502 |
| +1000 ms | 698 | 99 |
| Settled (~3.3 s after release) | 740 | 0 |

Configured `damping=2.15` → theoretical half-life 322 ms. Measured half-life from the 0–250 ms pair: **276 ms**. `k` fitted 2.51 then 2.26 — not a single exponential, because velocity is stamped from the last event `dt` and then damped.

Origin stills (`docs/reference-spec.md` §6, auditor flick set):

- −400 px held: Field Notes Δx ≈ −328 px (follow ratio 0.77–0.82). Local world `scrollX=312` is in the same ballpark for *translation amount*, but there is no camera tilt to compare.
- Flick coast ≈ 1.0–1.5 s, no snap, no reverse. Local coast from this drag is ~2–3 s to `velocity=0`.
- Origin hover to center: MAE 11.2, **no grid translation**. Local hover: also no translation — and also no tilt, so the “four-layer” target is missing on both the idle-hover stills *and* the current code. Frozen target video / target screenshot still show view-dependent rim highlights and perspective. Those must be fitted in Milestone 2 from the **video**, not from the still-only “no parallax” note.

Dual Pointer+Mouse listeners are a landmine: on a browser that emits both, `applyDrag` can run twice per move. Playwright’s mouse path in this probe produced `400 * 0.8 = 320` ≈ 312, so it did not double on this host. The code is still wrong.

---

## 14. The four known issues → files

### Issue 1 — “Black frame around flat media,” not one glass volume

**Class: architecture.**

| Piece | File | Function |
| --- | --- | --- |
| Inset front plane | `src/scene/InfiniteGlassGrid.ts` | `build` (`content.position.z = thickness/2+1`) |
| 90% plane | `src/scene/GlassTileGeometry.ts` | `createContentGeometry` |
| Quadratic extrude, flat face | `src/scene/GlassTileGeometry.ts` | `roundedRect`, `createGlassTileGeometry` |
| Stock transmission, no media sample | `src/materials/LiquidGlassMaterial.ts` | `createGlassMaterial` |
| Opaque blit | `src/materials/ContentMaterial.ts` | `createContentMaterial` |
| Undistorted HTML type | `src/ui/TileLabelLayer.ts` | `bindCard`, `sync` |

Replacement, not a roughness tweak. Milestone 3 must start from `/glass-lab`, not from this sandwich.

### Issue 2 — No continuous tilt / parallax / highlight

**Class: architecture + implementation.**

| Piece | File | Function |
| --- | --- | --- |
| Hover ignored | `src/interaction/InputController.ts` | `onPointerMove` early return |
| State is 2D only | `src/interaction/MotionController.ts` | entire class |
| Camera frozen | `src/rendering/RendererController.ts` | `init` / `resize` |
| Lights frozen | `src/rendering/StudioEnvironment.ts` | `addStudioLights` |
| No view-dependent glass uniforms | `src/materials/LiquidGlassMaterial.ts` | — |
| Tick never tilts | `src/app/App.ts` | `tick` |

### Issue 3 — Drag / inertia feels stepped or heavy

**Class: implementation + performance.**

| Piece | File | Function |
| --- | --- | --- |
| Transform written on the event | `src/interaction/InputController.ts` | `onPointerMove`, `onWheel` |
| Dual Pointer+Mouse | same | constructor |
| Velocity = last event Δ / Δt | `src/interaction/MotionController.ts` | `applyDrag` |
| Hard stop | same | `stopThreshold` |
| CPU blit + GPU upload ×3 / frame | `src/content/VideoClips.ts` | `pump` |
| Transmission draw-call storm | `LiquidGlassMaterial` + 15 meshes | live 491 → 1329 calls |
| CSS3D + `innerHTML` on wrap | `src/ui/TileLabelLayer.ts` | `sync` |

### Issue 4 — Black bands / tiles that look like they load late

**Class: architecture (coverage) + resource (ready gate) + parameter (gaps).**

| Piece | File | Function |
| --- | --- | --- |
| Only 3 rows / 5 cols | `src/config.ts` | `GRID` |
| Extra row parked *below* the screen | `src/config.ts` `restY0` + `GridCurvature.placeTile` | live `j=-1` `ny>1.2` |
| No top overscan | same | missing origin top row |
| Mid-gutter near-black 18–40 px | live + user current PNG | `qa/baseline/screenshot-metrics.json` |
| Loader ≠ GPU ready | `src/content/VideoClips.ts`, `src/app/App.ts` | `waitForFrame`, `loading.hide` |
| Three clips, title clobber | `src/content/catalog.ts` | `catalogAt` |
| Map swap on wrap | `src/scene/InfiniteGlassGrid.ts` | `update` |

The pool does not spawn on enter-view. The *holes* are empty navy because the pool does not cover the origin overscan, and because the 90% inset plus transmissive rim plus `cellH-tileH=23.8` open a full-width dark band between rows.

---

## 15. Classification

### Parameter problems

- `GRID.cellW/cellH`, `restY0`, `radius=3600` (sphere vs origin cylinder).
- `TILE` 540×400 vs origin mid ~534×408 overlay / ~521×364 pixel glass.
- Content inset `0.9` (creates the bezel well).
- `MOTION.damping=2.15`, `dragGain=0.8`, `wheelGain=0.22` — not fitted to the frozen target video.
- Corner `quadraticCurveTo` radius 58 vs origin ~61 px squircle.

These can be retuned **after** the architecture below is replaced. Tuning them first will not pass Milestone 1 overscan or Milestone 3 glass.

### Implementation problems

- Pointer and Mouse both bound; drag applied on the event thread.
- No normalized pointer `(-1,-1)…(1,1)`.
- `AdaptiveQuality.sample` never drives `grid.setQuality`.
- `catalogAt` overwrites the catalog with three clip titles.
- Loader completion criteria are too weak.
- QA surface is the wrong name and missing methods.
- `visual.spec.ts` asserts zero `<video>` elements; current code has three.
- `bindCard` uses `innerHTML` on wrap.

### Architecture problems (must replace)

1. Card = extruded rounded box + front billboard + CSS type. Cannot produce target refraction.
2. Motion = 2D scroll only. Missing rig tilt, camera parallax, and view-dependent lighting.
3. Glass = stock `MeshPhysical` transmission against a navy void. No media-behind-lens, no rim-only dispersion, no thickness-from-curvature.
4. Coverage = 5×3 pool with the spare row under the fold. Cannot keep two rows / two columns of overscan.
5. Curvature = shallow sphere. Origin is a yaw cylinder / inner wall.
6. Video path = DOM `<video>` + 2D canvas blit + `CanvasTexture.needsUpdate` every frame. Origin has no DOM video.

### Resource problems

- Only three 5-second 960-wide clips for the whole infinite field.
- Ready = `HAVE_CURRENT_DATA`, not decode + GPU + shader + warmup.
- Per-frame blit of three 960×540 canvases is a standing upload tax.
- Origin Mux assets must stay out of the repo.

### Performance problems

- 491 draw calls at rest, 1,329 after a short drag, for 15 tiles: transmission multipass.
- Per-frame CPU `drawImage` × 3 and texture upload.
- CSS3D full-tree render every frame.
- Tick allocates (`frameTimes`, quality sort copy).
- No Long Task / GC / GPU-time trace yet. Idle 8.3 ms on M5 Max is **not** a pass against origin.
- Quality scaler does not change the scene.

---

## 16. What already exists and must not be mistaken for done

Present and useful:

- Vanilla TS, one RAF, WebGPU path, no Mux hotlink.
- Integer lattice + brick stagger + modulo catalog.
- Shared glass geometry / material.
- Footer overlay separated from the canvas.
- QA hook skeleton.

Not done, despite earlier `qa/final-qa.md` Playwright “passed”:

- Independent auditor score was **42 / blocked** (`qa/auditor-notes.md`).
- Current live page is the video-blit sandwich, not even the older gray plates.
- No `?debug=coverage|geometry|pool`.
- No `/glass-lab`.
- No `__ILG_QA__` contract.

---

## 17. Phase 0 verdict

The four reported defects are real and are not material-parameter bugs.

| Defect | Root cause | Next legal stage |
| --- | --- | --- |
| Black bezel, flat media | Front plane + transmissive extrude | Replace card pipeline in Milestone 3 **after** Milestone 1 gray slabs |
| No scene-wide pointer feel | No pointer state, no rig, no light coupling | Milestone 2 Motion Controller |
| Uneven drag / hitch | Event-time integration + blit + transmission calls | Milestone 2 input, then Milestone 5 |
| Black bands / late tiles | 5×3 pool, `restY0` bias, inset gutters, weak ready gate | Milestone 1 coverage + Milestone 4 preload |

**Stop.** Do not edit `LiquidGlassMaterial` next. Milestone 1 must freeze glass to opaque gray, enlarge the pool, invert coverage so the top and bottom are permanently clipped, measure gutters from the golden stills, and add `?debug=coverage|geometry|pool`.
