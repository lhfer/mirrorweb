# Implementation plan (draft)

Status: Phase 2+ implementation is running at **`http://127.0.0.1:5280`**. Never use 4173.  
Independent audit (Agent 2): **blocked** — see `qa/auditor-notes.md`.

---

## Goal

Rebuild the *observable* Infinite Liquid Glass experience from measurements: infinite brick grid on a concave-from-camera curve, thick refractive tiles, pointer/wheel/touch motion, overlay + loader. Real-time WebGPU (WebGL2 fallback later). No screenshots, no iframe, no hotlinked Mux/HDRI/JS.

Legal: original placeholder videos, official OFL Geist (or substitute), independently licensed HDRI, placeholder brand mark. See spec §11.

---

## Stack (suggested, pin at implement time)

| Piece | Choice | Why |
| --- | --- | --- |
| App | Vite + TypeScript, **no React** | Origin is R3F v10 alpha; we do not copy that app |
| Renderer | `three@0.185.x` `WebGPURenderer` | Canvas advertised `three.js r185 webgpu` |
| Glass | MeshPhysical / TSL first, custom TSL if needed | Spec §4 |
| Grid | InstancedMesh or equivalent | Many identical slabs |
| QA | Playwright 1.59.x, Chrome channel, port **5280** | Already in `package.json` |
| Fonts | Official Geist + Geist Mono, or documented substitute | Do not copy origin woff2 |

Suggested tree (create in Phase 2, not now):

```
src/
  main.ts
  app/App.ts
  rendering/RendererController.ts
  scene/InfiniteGlassGrid.ts
  scene/GlassTileGeometry.ts
  scene/GridCurvature.ts
  materials/LiquidGlassMaterial.ts
  interaction/InputController.ts
  interaction/MotionController.ts
  quality/AdaptiveQuality.ts
  ui/LoadingOverlay.ts
  ui/PageOverlay.ts
  debug/QAHooks.ts
tests/  visual, interaction, infinite-loop, responsive, performance
qa/     visual-qa.md motion-qa.md performance-qa.md final-qa.md
artifacts/  reference/ local/ diff/ video/ traces/
```

`package.json` already points `dev` and `preview` at **5280** with `--strictPort`.

---

## Pre-implementation chores

1. `npx playwright install ffmpeg` and re-run `npm run capture:reference` so motion videos exist. Update spec §6 with fitted damping.
2. Optional: add a capture that logs overlay card transforms every 50 ms during drag/flick (no JS bundle download).
3. Author 12–20 short placeholder looping videos (solid color + motion grain is enough for Phase A–B; real footage only if licensed).
4. Obtain HDRI independently (Polyhaven `studio_small_03` is the likely public match to their filename).
5. Placeholder SHADER mark (rainbow pill + italic word).

---

## Stage A — Geometry and composition only

**Material:** opaque light gray / white. **No glass.**

Build:

- Perspective camera, start **fov ≈ 48.5–50°** (spec §3.2). Confirm against overlay helper if we add one.
- Tile size locked to A rest: mid **521×364 CSS px** at 1440×900; bottom-center **536×389**. World units chosen so those project to those boxes.
- Gutter **24–26 px** at 1440×900.
- Brick lattice: odd rows on x midline, even rows straddling.
- Curvature: **vertical-axis cylinder / yaw carousel**, outer edges closer (left top-edge ≈ +2.5°, right ≈ −3°).
- Rounded-box geometry with large radius (start from 61 px at bottom-center width; refine by screenshot).
- Thickness: start from matching the 164 px side-clip silhouette; tune later.
- Resize: canvas and lattice follow CSS; same normalized landmarks.
- Infinite recycle: integer (i, j) + modulo catalog. Opaque tiles, no video yet.
- DPR: desktop up to 2; mobile cap **1.5** as observed.

Pass:

- Nine landmark centers vs spec table, error **< 2%** of viewport.
- Mid and bottom-center size error **< 3%**.
- Gutter error **< 3%**.
- Edge yaw sign correct (left +, right − in image space).
- 30 s continuous translate: no hole, no pop (`missing` origin video until ffmpeg re-capture; use still + debug IDs for now).

---

## Stage B — Motion only

Keep opaque materials.

One integrator for pointer drag, touch drag, wheel, trackpad, flick.

Rules (from brief + spec):

- Velocity in world units / second, **delta-time** only.
- Pointer capture; no lost-drag while inside the canvas.
- Release must not reset velocity.
- Start damping as `v *= exp(-k * dt)` and **fit k** to A flick 10–14 once videos exist. Until then use a placeholder k such that motion dies in **1.0–1.5 s** (still-based bound).
- Drag gain start **0.80** world-screen (spec 0.77–0.82 on −400 px).
- X and Y both enabled; diagonal normalize = unknown — implement unnormalized first, compare to a new capture.
- Wheel: do **not** guess. Start with a tiny gain or map wheel-y to the same axis as drag-x only after a dedicated wheel capture. Current stills show ~0 move for delta 900 @ 80 ms.
- No snap, no spring unless a later capture shows it.
- Same code path for mouse and touch.

Pass:

- Same recorded pointer script vs origin: final offset error **< 5%** (needs videos).
- Inertia half-life error **< 10%** (needs videos).
- Stop time error **< 10%**.
- Flick does not reverse.
- Recycle has no visible jump.

---

## Stage C — Glass

Still no extra lights beyond a neutral env until Stage D.

1. `MeshPhysicalNodeMaterial` (or current r185 equivalent): transmission, thickness, ior ≈ 1.5, low roughness, light dispersion.
2. Compare A/06 stills. Failures typical: milky plastic, no side wall, uniform glow, full-frame rainbow.
3. Only then custom TSL: sample scene/video behind the face, offset by normal × thickness, RGB split **on the rim only**, Fresnel on the bevel.

Content plane: video texture (placeholders) inset behind the front face so the rim magnifies it.

Pass: rim band ≈ 18 px at 1440, rim-only CA, sharp top specks, readable face, navy gaps.

---

## Stage D — Lights and background

Change **one** knob per capture.

- Clear color `#000417` (A gutter).
- Environment: our licensed studio HDRI, not their URL.
- No contact shadow, no drop shadow, no vignette, no heavy bloom (spec §5).
- Tone mapping: try Neutral / ACES and keep whichever matches highlight roll-off; record the choice.

---

## Stage E — Overlay and loader

- Loader: centered cluster at (0.50, 0.50), black `#0a0a0a`, placeholder mark, integer percent. Hold until textures + HDRI + first tiles ready. Fade timing TBD (`missing`).
- Footer: left experiment link + placeholder mark; right pill CTA. Desktop row (`lg`), mobile column. Boxes from spec §8.4.
- Tile labels: HTML 3D overlay (origin method) *or* canvas text. Prefer HTML so type stays sharp. Copy must be **ours**.
- Fonts: official Geist / Geist Mono. Record any substitute in QA.
- CTA hover: `border-white/38`, `bg-white/12`, `active:scale-[0.98]` from computed class names.

---

## Stage F — Adaptive quality

| Tier | GPU | DPR | Glass |
| --- | --- | --- | --- |
| High | WebGPU | up to 2 desktop | full refraction + rim dispersion |
| Medium | WebGPU | cap 1.5 | fewer samples, fewer bevel segments |
| Low | WebGL2 | cap 1–1.25 | keep thickness + mild refraction; drop expensive CA |

Hysteresis on FPS so the tier does not chatter. WebGPU-missing path is **untested** on this host — must be QA’d on a forced-WebGL profile.

---

## QA skeleton (Phase 2+)

Commands already reserved in `package.json`:

```
npm run dev          # http://127.0.0.1:5280
npm run preview      # http://127.0.0.1:5280
npm run capture:local
npm run test:visual
npm run test:interaction
npm run test:performance
npm run test:responsive
npm run qa
```

Compare local vs `artifacts/reference/` at the same five viewports, same Chrome channel, same GPU. Diffs go to `artifacts/diff/`. Local stills to `artifacts/local/`.

Do not score `final result: passed` while any P0–P2 remains, or while Mux/brand assets are hotlinked.

---

## Phase order and stop rules

```
A geometry → B motion → C glass → D light → E UI → F quality
```

If a stage fails its pass table, **do not** start the next stage. If a fix in C/D breaks A landmarks, revert and re-measure before continuing.

---

## Immediate next actions (still Phase 1-legal)

1. Install Playwright ffmpeg and finish origin videos.
2. Fit flick damping from those videos; patch spec §6.
3. Only then open Phase 2 (`src/main.ts` and friends).
