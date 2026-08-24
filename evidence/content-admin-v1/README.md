# Content Admin v1 pixel-identity evidence

This package compares the accepted `v1.0.0` product at `8d893cd` with the
manifest-driven v1.1 public renderer. Both sides use the real production
SourceExact layout, target-source optical body, typography, motion code and
video textures.

The renderer is made deterministic before every image: finish the entry,
pause, seek all media to 1.25 seconds, place the pointer at zero, apply one of
three fixed grid offsets and render synchronously. Two independent baseline
runs were byte-identical across all twelve cells, so the observed run-to-run
noise for this harness is zero.

Result: **12/12 PASS**, maximum channel delta **0**, changed pixels **0**.

- `baseline/`: accepted v1.0.0 pixels.
- `candidate/`: v1.1 bundled-manifest pixels.
- `pixel-identity.json`: capture contract and machine-readable verdict.
- `admin-desktop.png`: 1440×900 production-build Cards editor.
- `admin-mobile-cards.png`: 390×844 production-build Cards list.
- `admin-mobile.png`: 390×844 admin-only draft view using the real renderer.
- `admin-browser-qa.json`: local CRUD, safe-text, navigation, preview geometry,
  fallback and console verdicts.

This proves seeded-content product identity. It does not claim live Supabase,
RLS, Storage or Magic Link completion; those require an authenticated project
connection and separate backend test evidence.
