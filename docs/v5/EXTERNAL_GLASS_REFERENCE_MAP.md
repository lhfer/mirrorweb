# External Glass Reference Map (V5 §二)

One page. Read before any product code. None of the three sources below
replaces the frozen source contract; B and C are methodology quarries.
*Corrected in Visual Convergence Sprint 2: the developer's own public
breakdown exists and is recorded below.*

## A. Target developer public record

The Target (`infinite-liquid-glass.shader.se/?v=2`) is by **Shader Development
Studio** (Simon Hedlund, shader.se, Sweden). Two public records:

1. **The developer's own technique post** —
   <https://x.com/shadersweden/status/2087846599535796464>. Supplied by the
   project owner and attested by them as the developer's public description of
   this demo; the post itself is behind x.com's login wall (HTTP 402 to an
   unauthenticated fetch on 2026-08-22), so what is recorded here is the
   owner-supplied enumeration, not a scrape. **Sprint 1's line "no published
   breakdown exists" was wrong and is withdrawn.**
2. Codrops 2026-05-19, "Inside Shader.se's Scroll-Driven WebGPU Pipeline"
   (Filip Kantedal) — covers the studio's agency site, not this demo;
   corroborates the stack only: React Three Fiber + **TSL node materials
   compiled to WebGPU**, selective scene rendering.

Every technique the developer names is already in the transcription — the post
is confirmation of the source contract, not new information, and it names
nothing the contract lacks:

| Developer's public statement | Source-contract anchor (`TargetOpticalBodyV5.ts` unless noted) |
| --- | --- |
| no MeshPhysicalMaterial | `MeshBasicNodeMaterial` + a hand-built node chain; transparent, `alphaTest .001`, FrontSide, `toneMapped: false` |
| no transmission | no transmission node anywhere; the "see-through" is a manual UV offset of the card's own media |
| custom TSL on a plane | one 16x12 tessellated plane per card, dome applied in the vertex stage |
| rounded-box SDF | 2D rounded-rect distance `s`, `cornerRadiusRatio .163` — drives every edge falloff |
| bevel height field | `pow(max(1 − t^k, 0), 1/k) · thickness`, `t = clamp(1 + s/max(bevelWidth, .001))`, `bevelPower 3.9` |
| grid sphere curvature + bevel slope normal | `normalize(vec3(p/sphereZ − clampedGrad, 1)) · faceDirection`; gradient eps `max(bevelWidth·.06, .35)`, slope clamped at `bevelMaxSlope 1.74` |
| own video texture below surface | each card samples its OWN media texture (clamp-then-cover), never a screen-space capture |
| refracted view ray | `refract()` on the local view vector, `eta = 1/max(ior + dispersion·offset, 1.0001)`, `ior 2.3` |
| UV offset by travel through plate | `travel = thickness/max(abs(r.z), .05)`, `uv += r.xy · travel · refractStrength .7` |
| several IOR samples | the spectral loop — sample count set by the device tier (coarse 3 / fine 5) |
| channel-separated dispersion | per-sample IOR offset, R/G/B weighted separately, `dispersion .32` |
| Fresnel + HDRI reflection | Schlick^5 `F` (`fresnelF0 .045`), `reflect` → `envRotation −2` → equirect UV; `envMix = min(saturate(F·envIntensity 1.93), envMaxMix .27)` |
| tight mirror highlight | `rim = smoothstep(−rimWidth, 0, sdf) · rimIntensity .11`, added after the env mix |
| coloured edge light | `mix(rimColor, rimColorTop, F)` — the capability is in the chain; the **shipped settings set both to `#ffffff`** (bundle offset 1303603), so on this demo the edge light is white |

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
