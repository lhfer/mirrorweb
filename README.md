# v1.0.0 release-review evidence

This branch exists for one reason: a GitHub PR body can only show an image it
can fetch from a URL, and the release branch must not carry captured images.
So the four product screenshots the release PR links to live here.

**It is an orphan branch with a single commit, it is not merged into anything,
and it should be deleted once the release PR is reviewed.**

## screenshots/

The release build on its naked `/` route — no query, no debug overlay, no
status readout — at the four review viewports. This is what a visitor gets
after the §七 default-route change.

## data/

| file | what |
| --- | --- |
| `acceptance-smoke-summary.json` | the §三 acceptance smoke, all three contexts, one table |
| `smoke-120hz.json` | 120 Hz-capable headless context, 10 minute soak |
| `smoke-60hz-frame-budget.json` | 60 Hz frame-budget emulation, 5 minute soak |
| `smoke-120hz-headed.json` | a real Chrome window. Run believing it was the 60 Hz context; it is not, and it is reported as what it turned out to be |
| `smoke-release-build.json` | the same instrument against the release build's naked route |
| `routes-release.json` | all three routes read off the built release preview |
| `visual-identity-vs-8de671f.json` | fixed-state stills, release build vs the accepted development build |
| `black-card-luma.json` | card-plane luma on 90 stills, 50 of them taken the instant a clip reported itself not decodable |
| `release-file-manifest.json` | a copy of the manifest that ships on the release branch |
| `fe-package-reviewhead.patch` | the packager change that moved the private package's `reviewHead` to the accepted development HEAD. Deliberately NOT committed to the research branch, which is frozen at `8de671f` |

## data/review-round/

Evidence for the four P2 fixes on PR #1 (`d995d20`).

| file | what |
| --- | --- |
| `routes-before-fixes.json` / `routes-after-fixes.json` | seven routes read off the built preview on either side of the fix commit |
| `pixel-identity.json` | fixed-state stills: `/` before vs after (max delta 1/255), `/` vs the accepted dev build, and `?review=current` before vs after (max delta 223 — the shell returning) |
| `smoke-naked.json` | the acceptance instrument against the fixed build's naked route |
| `smoke-gl1-webgl2.json` | the same against `?gl=1`, confirming the WebGL2 backend, entry and gestures |
| `black-card-luma.json` | card-plane luma on 56 stills, 35 taken on a readyState dip |

`screenshots/review-current-before-1440x900.png` and `-after-` are the rollback
route on either side of fix 1; the reflection shell is the difference.

Nothing here contains Target pixels. Every image is our own render.
