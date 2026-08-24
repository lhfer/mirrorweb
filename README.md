# MirrorWeb

A local replica of the Infinite Liquid Glass grid: an infinite, curved plane of
glass cards over live video, rendered on WebGPU through three.js, with the card
labels in a CSS3D layer above it.

## Run it

```
npm ci
npm run build      # tsc --noEmit && vite build
npm run preview    # serves the built site on 127.0.0.1:5280
```

`npm run review` builds and serves on `127.0.0.1:5293`; `npm run review:lan`
serves the same build on `0.0.0.0:5293` so a phone on the same network can open
it.

## Routes

| URL | What it is |
| --- | --- |
| `/` | the product. Boots the accepted candidate. |
| `/?review=target` | the same page, named explicitly. This is the review link, and it resolves to exactly what `/` resolves to. |
| `/?review=current` | the rollback: the same composition on the previously shipped optical default, for side-by-side comparison. |

Both routes expand into `?composition=sourceExact&opticalBody=…` before the app
boots, and the expansion stays on the URL. That is deliberate rather than
cosmetic: the configuration readers parse `location.search` again on later
events such as a resize, so a URL cleaned up after boot would silently revert
the page mid-session.

Appending `&qa` publishes the QA introspection API on `window.__ILG_QA__`. It is
off in a production build unless asked for.

## Where the rest of it went

This branch is the production tree only. The capture harnesses, the measurement
scripts, the frozen contracts and the several hundred evidence files that
produced the accepted candidate live on the research branch
`rebuild/liquid-glass-v5-source-exact` and in the archive bundle taken from it.
Nothing here depends on them.

The `config/*.json` files are the exception and are production files: the
layout, motion and entry constants are read from them at runtime, so they ship.

## Asset licences

`public/hdri/studio_small_03_1k.hdr` is CC0 1.0 (Poly Haven, author Sergej
Majboroda). Full provenance in `public/hdri/PROVENANCE.md`.
