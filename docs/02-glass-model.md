# 02 — Glass model

The slab is a convex superellipse volume. It does **not** use `MeshPhysical.transmission`.

## Layers

1. **Media pass** — video planes sit just behind each slab. Glass is hidden. The frame is written to a screen-sized render target.
2. **Glass pass** — one shared TSL material samples that target in screen space, then bends the UVs with the world-space normal, IOR, and rim thickness. Neighbors and gutters are visible where the rim looks aside.
3. **Typography** — CSS3D in front of the front face. Titles are not baked into the media.
4. **Highlight** — Fresnel and a top-edge spec live in the shader. The M2 key light still follows the pointer for the rest of the scene.

## Optical path

- Refract the view ray against `normalWorld`.
- Offset `screenUV` toward the interior so the photo folds into the rim.
- A weaker outward tap mixes neighboring tiles at the sidewall.
- RGB split and a 3-tap blur exist only where `rim` is high.
- No constant dark `face` mix. Side color comes from the background pass.

One extra full-frame pass, not one transmission pass per tile. The grid reuses 3 video textures plus 1 glass material.

## `/glass-lab`

`http://127.0.0.1:5280/glass-lab`

Same two-pass path. Backgrounds: checker, h-lines, v-lines, color, video, white, black, gradient.

Pass on a line or checker field:

- Lines continue through the outer 15–25% of the slab.
- Rim still shows the field, not a solid black hoop.
- Center stays relatively clear.
- Highlights move with pointer / camera.

## Main grid

`public/clips/*.mp4` are decoded into `VideoTexture`s before the loading overlay hides. Wrap remaps swap one of those three maps. They do not first-upload a new texture.
