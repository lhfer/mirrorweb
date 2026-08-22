# External Glass Reference Map (Integrated Visual Sprint 1, §二)

One page. Read before any product code this round. None of the three sources
below replaces the frozen source contract; B and C are methodology quarries.

## A. Target developer public record

The Target (`infinite-liquid-glass.shader.se/?v=2`) is by **Shader Development
Studio** (Simon Hedlund, shader.se, Sweden). Public record checked 2026-08-22:
the demo page carries only the studio credit — no technical text; the studio's
one published technical article (Codrops 2026-05-19, "Inside Shader.se's
Scroll-Driven WebGPU Pipeline", author Filip Kantedal) covers their agency
site, not this demo, and confirms only their stack practice: React Three
Fiber + **TSL node materials compiled to WebGPU**, selective scene rendering.
**No published breakdown of the liquid glass demo was found** (Codrops, X,
blogs searched). The authoritative "developer explanation" therefore remains
the shipped TSL bundle itself, which the frozen source contract transcribed.
Where each brief-listed technique lives in that transcription:

| Technique (brief §二A) | Source-contract anchor |
| --- | --- |
| Custom TSL plane (not MeshPhysical) | 16x12 tessellated plane + custom node material — `TargetOpticalBodyV5.ts` |
| Rounded-box SDF | 2D rounded-rect distance term driving every edge falloff |
| Bevel height field | height profile over SDF distance near the rim |
| Grid sphere curvature + bevel slope normal | vertex dome (sphere curvature) + normal rebuilt from bevel slope |
| Own video texture | each card refracts its OWN media — never screen-space capture |
| Per-IOR refraction + edge dispersion | spectral loop, one refract per sample tier, per-sample IOR offset |
| Fresnel + HDRI | white studio HDR, equirect sample, fresnel-weighted mix |
| Tight mirror highlight | narrow white-rim scalar on top of the env mix |

## B. ybouane/liquidglass — screen-space, NOT an architecture donor

WebGL library; captures the page DOM to a canvas (`html-to-image`) and
refracts that capture. **It is screen-space background capture, not the
Target's own-media TSL body — must not be adopted as a replacement
architecture.** Core: `src/shaders.ts`, `GlassRenderer.ts`, `HtmlCapture.ts`.
Reusable methods: (1) static-vs-dynamic texture split — static content
captured once, `<video>`/`<canvas>` auto-detected as per-frame; (2)
per-element dirty tracking with a render loop that short-circuits when
nothing changed; (3) an explicit invalidation hook (`markChanged`) for
updates the observer cannot see. Our material cache already gives us (1);
(2)/(3) are candidates for a later perf round, not this one.

## C. OverShifted/LiquidGlass — a single-card refraction lab, not source

C++/OpenGL squircle demo (`src/App.cpp` entry, `LiquidGlass.cpp` +
`BlurPass.h`). **Not Target source; no direct port.** Refraction is an
explicit height profile `f(x) = 1 − b·(ce)^(−dx−a)` over SDF distance with
live ImGui sliders. Reusable methods: (1) parameter-visualisation discipline —
one card, live sliders, the profile function shown next to the render; (2)
ablation stills — full effect vs refraction-only vs inverted-refraction
side-by-sides; (3) blur at reduced resolution. This round borrows exactly
one habit from it: judge a glass change by **full-frame ablation pairs**,
not by band metrics.
