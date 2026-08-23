# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-23 (**Visual Convergence Sprint 2 — READY FOR MATCHED-CONTENT VISUAL PRODUCT REVIEW.** The round that made the two pages comparable and then fixed the one thing that was visible at 1×. §三 matched-content harness (`27a8304`): both pages served ONE locally generated asset per category through the O2 shared-media core (six §三A categories) and ONE injected copy set, then measured — decoded frames compared per pixel (five of six **bit-identical**; the sixth 60 of 1,080,000 px at ≤3/255), same copy hash both sides, same viewport/DPR/pointer class/card box/cover fit at four viewports → **MATCHED-CONTENT HARNESS PROVEN**. §五 card geometry truth: ten cards, seven scenarios, every frame, full CSS3D matrix + projected rect, ONE reader both sides, thresholds pre-registered per scenario from the Target's own three repeats and committed before any candidate trajectory was read. Static layout is **exact** (rest agrees to 0.000 on every observable; gutters 17.337/16.616 px); spacing under motion is not the problem. Two real divergences, both carried forward: the fling is **bimodal** (three candidate runs 815.55/815.76/815.55 px inside the Target's 814.75–817.18, two at 832.15/833.07 — ~2 runs in 5 overshoot ~17.4 px on identical input), and the portrait→landscape relayout makes **one ~36.7 px single-frame step** (36.72/36.72/36.79 across three runs) where the Target's largest is 4.5 px. `p0-decision.json` carries a dated correction: its first-draft motion numbers came from one pair and are superseded by the pair matrix. §六 P0 (`2081ca1`, committed before any product code): **C. Typography / Footer / Brand** — the Target paints a 144 px black-to-transparent scrim across the full width of every page, inside its footer container, over the cards and their labels, and we painted nothing. §七 change (`3046e92`, two files, one system): the scrim; the Target's own footer law (the row never stacks, only the wordmark link does, and only below its `lg` breakpoint); the wordmark box `min(26vw,148px)` with its drop shadow carrying **our own** ATELIER mark as inline SVG (the Target's logo is its own studio mark and is not reproduced); the CTA pill's missing top sheen. §八 all ten conditions PASS: bottom-144 luma delta **+13.19/+17.05/+14.49/+18.91 → +0.85/+0.54/+0.41/+0.76** at 1440x900/390x844/844x390/700x700, last screen row +43.22 → +0.37 at 700x700, footer geometry to under **0.05 px**, band tracks within ±1.1 luma across every frame of six real-input recordings, source contract **PASS 36/36**, typography **PASS 29/29**, route check PASS (shipped default boots V3; `?review=current` still pins the shipped optical default at exposure 1.05), tsc + vite PASS, zero console/page errors. Honest grade: **MATERIAL AND POINTABLE AT 1×**. §九 bounded smoke: 10 min, High/Medium/Low actually exercised, one phase under a **4× CPU throttle**, cache constant, no black cards, GC floor flat — and a throttled headless run is explicitly not reported as a real-device PASS. Evidence: [`qa-v5/visual-convergence/`](../../qa-v5/visual-convergence/README.md) (8 public files, no images) + `qa-v5/private/vc2-visual-convergence.zip` (16.5 MiB, 6 side-by-side videos, 24 stills, 12 sheets, per-file SHA-256, missing 0 / unlisted 0). Review: `npm run review` → `127.0.0.1:5293/?review=target` and `?review=current`. Target Visual PASS **NOT ASSERTED**; shipped optical default unchanged; main untouched; motion, layout and glass untouched. Earlier: **Integrated Visual Sprint 1 — READY FOR INTEGRATED VISUAL PRODUCT REVIEW.** The round that switched from band metrics to complete pages. §三 review routes shipped (`f013671`): `?review=target` boots the complete page on the leading candidate (sourceExact + `target-source-unclamped` + the Target device-tier law + labels/footer/motion/culling/adaptive, one query param), `?review=current` the same page on the shipped default; verified live on fine- and coarse-pointer contexts; the shipped no-query default is untouched. §四 Before evidence: 12 full-page stills + 12 real-input recordings (six scenarios × both sides, identical CDP input). §五 ranked four P0s. §七 Phase A (`5833dd6`): the bundle code-to-code audit found the card program **transcription-complete** — the real divergence sat OUTSIDE it: our renderer ran ACESFilmic at **exposure 1.05** (day-one import; the pre-V4 reference spec left exposure "missing as a numeric value") where the Target runs the r3f default ACESFilmic at the three.js default **1.0** (bundle offset 1235834, no flat/linear flag, no app-side exposure assignment) — a uniform applied after the card program, structurally invisible to every sealed in-program instrument. Fix: candidate lane renders at 1.0; control + sealed clamped lanes keep 1.05 — control verified **0 differing pixels at all four viewports**; the candidate settles page-wide with the exposure-through-ACES signature (mid-tone darkening peaking −3.4 bytes at luma 96–160), carrying the sealed dark-band residual's direction and closing roughly a third of it. Honest visibility grade: **SUBTLE-BUT-PAGE-WIDE**; the remaining gap stays declared. §八 Phase B (`a3748fd`): live dual-side re-read with a new loaded-face proof — **bit-equal glyph bounds** at matched size/weight, every text-carrying style equal at four viewports, text-plane depth exact, no system-ui fallback anywhere; **no code change needed**. §九 motion diagnosis (code frozen): trajectories align (flick glide 1.881 vs 1.840 s; wrap displacement exactly −1144 px both sides; zero >120 px discontinuities); **no visible motion P0 found**. §十 bounded smoke: fps pinned 120 both phases, heap ends below start, cache constant (2 sets; 5/3 samples by device law), darkest sampled card rect 59.8 luma — no black cards. Evidence: [`qa-v5/integrated-review/`](../../qa-v5/integrated-review/README.md) (8 public files, no images) + `qa-v5/private/ivr1-integrated-review.zip` (≤60 MB, 8 videos, 16 stills + contact sheets). Target Visual PASS **NOT ASSERTED**; main untouched; motion code untouched. Earlier: **O5F PAUSED BY USER — interim snapshot, no §十七 state asserted.** Phase A is COMPLETE and PASS: the finite material-set cache (`30b91f6`) retires the quality-step rebuild — §六 identity 35/35 + 35/35 exact zero with program hashes matched at both tiers, §七 stress **10/10** (1,200 quality steps, 0 pixel mismatches, creation constant at 6; session GC-trough rises **−1.46/−0.50/−0.87 MB** against threshold 5.68 where O5R rose +18.59/+20.03/+22.15), and a retired defect: the old quality path swapped in the control lane's convex geometry (977,083 differing px/cycle at baseline; exact 0 now). Phase B forensics COMPLETE at `68d9152`: the **§十B live probe proved the one source mismatch** — the Target's spectral tier is a device predicate (bundle byte 1968911), its coarse-pointer 390x844/844x390 programs compile **3 refract calls** where our candidate ran 5 (counting convention validated on the desktop control; live bundle sha == archive); the §九 decomposition finds **every readable term MATCHES at both viewports** (`firstDivergingTerm: null` — the transcription is faithful); §十A eliminates the frozen clip-2 crop (the residual is rect-anchored — per-rect pixels identical under occupant rotation — and the attribution reconciles the sealed gate means exactly); §十E quantifies the ring: masking off-silhouette pixels moves the worst-rect residual 13.83 → **19.15** (the ring DILUTED the sealed number). The **one §十一 correction** (`c545649`): the unclamped lane's body sample count follows `targetDeviceTierV5()` — desktop 5/5/5, mobile 3/3/3, sealed clamped lane and control untouched, Beauty program byte-identical to §六C. §十四 verification: `controlIdentityAfterFix` **PASS** (control 35/35 zero; sealed lanes 224 comparisons zero vs O5R; candidate desktop zero, candidate mobile changed by design 769–3,575 px/state); the quality-cycle re-run passed (1,200 steps, 0 mismatches, the pre-registered cross-tier flip observed); **the six §十四 sessions + stress score were interrupted by the pause** (`o5f-stress-postfix.py` is sealed and resumable). Measured on the sealed asset, the correction **does not move the sealed P0 band metrics** (the 3-vs-5 difference lands outside the scored bands on bw-split) — the tier hypothesis as the residual's cause is falsified by measurement; the correction stands on its own proof. NOT run at the pause: §十四 sessions/stress, the frozen-suite aggregate (`regressions.json`), recordings. If resumed and stress passes, the pre-registered tree resolves to READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT RESIDUAL. Earlier: **O5R REVIEWED — O5F opens.** Product review accepted the HDR audit and unclamp as a source correction (`target-source-unclamped` is now the only active optics candidate; the sealed clamped lane is retained for regression only), the structural environment-off program, the corrected refraction-compression instrument and its result, the reflection band, own-media isolation, temporal continuity, the mobile direction, control identity, sealed-lane identity and the 24/24 frozen regressions. NOT accepted: the default flip, the two 390x844 portrait residuals, candidate memory/resource stability, Target Visual PASS. The corrected gate stays sealed at **7/14 FAIL** and is not rewritten. Five evidence wording corrections are recorded in [`O5R_PRODUCT_REVIEW.md`](O5R_PRODUCT_REVIEW.md) — the pointer path has one readable row, full-frame readiness is not a visual verdict, the silhouette ring is contaminated and its PASS rows near-degenerate, the grayscale/saturated floors are scale-blind, and the O5R package's `reviewHead` should have been `445037e` (fixed in the next package only). **O5F has exactly two sequential objectives**: eliminate the quality-step material retention behind a finite material-set cache with an identity-then-stress gate, then locate the first source-level cause of the 390x844 portrait residual — at most one proven source-transcription correction, no constant tuning. Earlier: **O5R closed — TARGET-SOURCE BODY FAILED CORRECTED PRODUCT GATE**, evidence prepared for product review. The corrected gate returns **FAIL, 7 PASS / 7 FAIL / 0 UNREADABLE of 14**, with every instrument repaired and 66/66 unit tests sealed before capture. The round's substantive win is §六: a CPU replay of the source refraction formula, validated on the Target's own render to 1.4–1.6 px, puts the candidate's displacement field inside the Target's window at every readable viewport. §十's authorised unclamp **did not close the portrait residual** — dark luma 58.57 vs 51.28, white ratio 3.8676 vs 4.9035 — and no constant was tuned in response. §十二 found a **new, independent** failure: the candidate lane's GC trough rises ~2 MB/min where the shipped lane's is flat, with structural resource counts flat in both — and a five-arm diagnostic attributes it to the **quality-step material rebuild** (39.36 MB in six minutes against at most 2.06 MB in every other arm, ~68 KB per step), which disposes its previous materials and retains anyway. Sealed O5 evidence NOT rewritten; re-run unchanged to its own 8/14. Target Visual PASS **NOT ASSERTED**; default stays `opticalBody=current`. Earlier: **O5 reviewed** — the source contract, the whole target-source architecture, own-media refraction, the analytic normal, 35/35 control identity, 15/15 compiled audit and the reflection-band result are ACCEPTED. Two failures were candidate residuals at 390x844 only, four were unreadable instruments, and two PASS rows were degenerate. Earlier: **O5 built the Target's complete card optical body as one lane** and **FAILED its absolute gate 8/14** — but the band width now matches the Target at every viewport, which three rounds of single-term substitution never achieved. Earlier: **O4 reviewed** — the zero-normal defect, the Target body source contract and the adaptive-shaping attribution accepted; the candidate rejected; the gate count corrected 7/12 → 8/12. **O5 opens** one cohesive system: the Target's complete card optical body. Earlier: **O3 reviewed** — knowledge accepted, candidate rejected. **O4 attributed the frozen body floor** to local adaptive body shaping and **FAILED its absolute gate**: removing it takes the body floor *below* the Target's whole band while the shipped band barely moves. Both the support field and the body are constraints; neither round was permitted to change the other)

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-source-exact` |
| Source contract | [`config/target-layout-source-v2.json`](../../config/target-layout-source-v2.json), verified by `npm run v5:target-layout-source` |

### Commit semantics

Each field names what that commit contains. `reviewHeadAtDelivery` is the branch
tip this delivery was reviewed at; a file cannot contain its own hash, so it is
stated here and no further hygiene commit is created to chase it.

| field | value |
| --- | --- |
| `sourceContractCommit` | `42ac438` `v5-fsx-source-contract` |
| `codeCommit` | `62bb251` `v5-fsx-source-exact-code` |
| `evidenceCommit` | `6d313bc` `v5-fsx-source-exact-evidence` |
| `metadataCommit` | `4c48aba` `v5-fsx-manifest-hygiene` |
| `acceptanceCommit` | `750d476` `v5-fsx-composition-accept` |
| `hardeningCommit` | `5c24a60` `v5-fsx-integration-hardening` |
| `beautyEvidenceCommit` | `6d1d5bb` `v5-fsx-beauty-baseline-evidence` |
| `evidenceReproducibilityCommit` | `4c3f7ed` `v5-fsx-evidence-reproducibility` |
| `t0FixCommit` | `52afb05` `v5-t0-render-loop-evidence-fix` |
| `typographyCodeCommit` | `847347d` `v5-t1-source-exact-typography-code` |
| `typographyEvidenceCommit` | `39ff3de` `v5-t1-source-exact-typography-evidence` |
| `sourceContractRerunCommit` | `v5-t1-source-contract-tip-rerun` — the 36-viewport engineering contract re-run at `39ff3de` so the Typography gate's Source Contract row reads a verdict out of a file instead of asserting one. Evidence only; no product code. |
| `motionForensicsCommit` | `990bcce` `v5-m0-target-motion-forensics` — the motion source contract, read out of the Target's bundle and replayed against it. No product code. |
| `motionCodeCommit` | `655fda4` `v5-m1-source-exact-motion-code` — the source-exact motion model. Frozen files byte-identical to `7dc7cf1`. |
| `motionCorrectionsCommit` | `e97bc17` `v5-m1-source-exact-motion-code-corrections` — the first gate run FAILED and found four engine defects, four instrument faults and two contract errors. Not one of the four mandated commit names, and named rather than folded into one of them: it is product code, and a reviewer reading the ledger should see that the code commit was corrected before any evidence was captured against it. |
| `motionReleaseFixCommit` | `8e947b9` `v5-m1-source-exact-motion-release-and-instruments` — the release was applied out of band; three more instruments replaced. |
| `motionEvidenceCommit` | `788e6a7` `v5-m1-source-exact-motion-evidence` — captured at `8e947b9`. `d8447de` then removed the recordings from the public tree; the oversized blobs remain in this branch's history, because removing them needs a history rewrite and this branch does not permit one. |
| `m2InstrumentCommit` | `cff917b` `v5-m2-motion-instrument-and-gate-repair` — the ordering instrument, the direction-aware gate, and the Target-only baseline, sealed before the candidate was captured. No product code. |
| `m2CodeCommit` | `30dcf64` `v5-m2-motion-closure-code` — scheduling readbacks, the camera comments that contradicted the code they sat above, and the `labelCamera` → `css3dTransformCamera` rename. No motion behaviour changed. |
| `m2EvidenceCommit` | `v5-m2-motion-closure-evidence` — captured at `30dcf64`. |
| `typographyAcceptCommit` | `7dc7cf1` `v5-t1-source-exact-typography-accept` — product acceptance of T0 and T1, the typography freeze contract, and three evidence wording corrections. No product visual code. |
| `reviewHeadAtDelivery` | the branch tip after the commits above; resolve with `git rev-parse HEAD`. A file cannot contain its own hash and no hygiene commit is created to chase one. |

### Status

| | |
| --- | --- |
| SourceExact Composition Baseline | **ACCEPTED** |
| Engineering PASS | **YES** |
| Target Visual PASS | **NOT ASSERTED** |
| T0 Render Loop Repair | **ACCEPTED** |
| Typography | **ACCEPTED** — frozen, see the freeze contract below |
| Motion / Pointer / Touch | **ACCEPTED — FROZEN**, see [`MOTION_FREEZE_CONTRACT.md`](MOTION_FREEZE_CONTRACT.md). M0–M3 results below are history |
| V0 CSS3D label coverage culling | **ACCEPTED — FROZEN**, see [`CULLING_FREEZE_CONTRACT.md`](CULLING_FREEZE_CONTRACT.md). The V0 section below is history |
| V1 WebGL render culling | **ACCEPTED — FROZEN** (behaviour baseline `b625f90`, accepted review tip `5159cf8`), see [`RENDER_CULLING_FREEZE_CONTRACT.md`](RENDER_CULLING_FREEZE_CONTRACT.md) |
| Optics — O0 diagnosis | **ACCEPTED** as the current optics source baseline |
| Optics — O1 System A | **FAILED ABSOLUTE GATE**; commit `e01fb30` remains an EXPERIMENTAL LANE only — not an accepted baseline, not frozen. See the O0/O1 section and the wording correction below |
| Optics — O2 System B | **ACCEPTED** — behaviour baseline `e913aa6`, accepted review tip `fd12b97`; selected lane **A+B** (System A retained ONLY through the pre-registered O2 interaction gate, never from the failed O1 result). Mechanism frozen, reflection SUPPORT FIELD deliberately not frozen — see [`O2_OPTICS_FREEZE_CONTRACT.md`](O2_OPTICS_FREEZE_CONTRACT.md) |
| Optics — O3 Target analytic bevel reflection support | **REVIEWED**: candidate **REJECTED** (gate FAILED 11/20); source forensics, `TargetBevelFieldV4` transcription (ENGINEERING PASS), corrected instruments, the `target-sdf` diagnostic lane and the frozen-body-floor finding all **ACCEPTED**. See [`O3_PRODUCT_REVIEW.md`](O3_PRODUCT_REVIEW.md) |
| Optics — O4 frozen body floor | **REVIEWED**: selected candidate **FAILED ABSOLUTE GATE** (8/12). Attribution is accepted: local adaptive body shaping explains 141% of the desktop excess. Removing it drops the floor 9.7 → 1.7 px — *below* the Target's 3.3 — while the shipped band moves only 15.3 → 13.0. Shipped default stays `bodyFloorMode=current`. Factor A was `noRefractionOffset` and did NOT implement Target own-media/per-IOR refraction — see the wording correction in [`O4_PRODUCT_REVIEW.md`](O4_PRODUCT_REVIEW.md). Evidence: [`qa-v5/optics-o4/`](../../qa-v5/optics-o4/README.md) |
| Optics — O4A body-path audit | **AFFECTED** — the shipped Beauty refraction path consumes a ZERO normal: the geometry normal is unpacked once, inside the `normals` debug branch, and every other branch aliases a zero-initialised private. Explains GATE-005. Not repaired (O4 selected a different subsystem) |
| Optics — O5 source-exact card optical body | **REVIEWED**: gate sealed at **FAILED ABSOLUTE GATE** (8/14) and never rewritten. **ACCEPTED**: the source contract, the target-source architecture, the own-media pipeline, per-IOR spectral refraction, the analytic normal, the SDF silhouette *mechanism*, the no-scene-colour architecture, 35/35 control identity, 15/15 compiled audit, the reflection-band result (in the Target window at **all four** viewports) and the HF spectral-structure result. **NOT YET ACCEPTED**: the default flip, 390x844 dark-side luma, 390x844 white ratio, the gate verdict as a reading of the candidate, Target Visual PASS. Two failures are real candidate residuals at 390x844 only; four are instruments that cannot discriminate; two PASS rows (items 5 and 14's fringe sub-check) are degenerate and may not be cited. See [`O5_PRODUCT_REVIEW.md`](O5_PRODUCT_REVIEW.md) and [`qa-v5/optics-o5/`](../../qa-v5/optics-o5/README.md) |
| Integrated Visual Sprint 1 — product-driven review | **READY FOR INTEGRATED VISUAL PRODUCT REVIEW** (reviewed on complete pages, not band metrics). Review routes `?review=target` / `?review=current` shipped (`f013671`), shipped default untouched. Glass §七 (`5833dd6`): card program proven transcription-complete; the divergence was the renderer output exposure **1.05 vs the Target's 1.0** — candidate lane now renders at 1.0, control 0-diff at all four viewports; visibility honestly graded SUBTLE-BUT-PAGE-WIDE, remaining deep-dark gap declared. Typography §八 (`a3748fd`): live loaded-face proof, bit-equal glyph bounds, no fix needed. Motion §九: diagnosed only — no visible P0 found. Perf §十: bounded smoke clean (120 fps pinned, heap ends below start, no black cards). Target Visual PASS **NOT ASSERTED**. See [`qa-v5/integrated-review/`](../../qa-v5/integrated-review/README.md) |
| Optics — O5F material cache + portrait source reconciliation | **PAUSED BY USER — interim snapshot, no §十七 state asserted.** Phase A COMPLETE, PASS: finite material-set cache, §六 identity 35/35 + 35/35 exact zero (programs matched both tiers), §七 stress **10/10** — GC-trough rises **−1.46/−0.50/−0.87 MB** vs threshold 5.68 (O5R rose +18.6/+20.0/+22.2); retired defect: the old quality path swapped in the convex control geometry (977,083 px/cycle at baseline, exact 0 now). Phase B COMPLETE: **§十B proved the one source mismatch live** (Target device-tier predicate, bundle byte 1968911 — 3 refract calls at 390x844/844x390 vs our 5, counting convention validated on the desktop control); §九 decomposition — every readable term **MATCHES** at both viewports, `firstDivergingTerm: null`; §十A eliminates the frozen clip-2 crop (residual rect-anchored; reconciles the sealed means exactly); §十E: the background ring DILUTED the sealed number (13.83 → 19.15 silhouette-only). The **one §十一 correction** (`c545649`): unclamped lane samples follow `targetDeviceTierV5()` (desktop 5/5/5, mobile 3/3/3; sealed clamped lane + control untouched; Beauty program byte-identical to §六C). `controlIdentityAfterFix` **PASS** (control 35/35 zero, sealed lanes 224 zero vs O5R, candidate desktop zero / mobile changed by design). **Measured: the correction does NOT close the sealed P0 windows** — the 3-vs-5 difference lands outside the scored bands on the sealed asset; the tier hypothesis as residual cause is falsified by measurement. INCOMPLETE at pause: §十四 sessions + stress score (sealed, resumable via `o5f-stress-postfix.py`), frozen-suite aggregate, recordings. See [`qa-v5/optics-o5f/`](../../qa-v5/optics-o5f/README.md) |
| Optics — O5R corrected instruments + source environment | **REVIEWED — sealed at O5R TARGET-SOURCE BODY FAILED CORRECTED PRODUCT GATE**, reviewed at `445037e`; see [`O5R_PRODUCT_REVIEW.md`](O5R_PRODUCT_REVIEW.md) for what is accepted (the unclamp as a source correction, the corrected instruments, the reflection band, temporal continuity, both identities, 24/24 regressions), what is not (the default flip, the two portrait residuals, memory stability, Target Visual PASS), and the five evidence wording corrections. Corrected gate **FAIL, 7 PASS / 7 FAIL / 0 N/A / 0 UNREADABLE of 14**. The instruments are repaired: §六 refraction compression now replays the source formula through the real card matrix and is validated on the Target's own render to **1.4–1.6 px**, and the candidate's displacement field enters the Target's window at every readable viewport (vector Δ **0.79 / 1.04 / 1.08 px** against the shipped body's 8.88 / 4.86 / 5.05). §十's authorised change removed `envSampleCeiling` after an HDR audit found the asset finite (0 NaN, 0 Inf, max 3581.99, 0.99% of texels above 16) — and it **did not close the portrait residual**: dark-side luma 58.57 vs 51.28 (moved +0.11 of a 7.29 gap), white ratio 3.8676 vs 4.9035 (moved −0.0036 of a 1.0359 gap). §十二 found a **new** failure independent of the optics: the candidate lane's GC trough rises **18.6 / 20.0 / 22.2 MB per ten minutes** across three sessions where the shipped lane's falls 1.0 MB, with all structural resource counts flat. A five-arm diagnostic attributes it to the quality-step material rebuild (39.36 MB in six minutes against at most 2.06 MB in every other arm). Frozen regressions **24/24 PASS**. Sealed O5 gate re-run unchanged: 8/14, identical. Control identity 35/35 exact zero; sealed O5 lane 22/22 byte-identical. Target Visual PASS **NOT ASSERTED**. Default stays `opticalBody=current`. See [`qa-v5/optics-o5r/`](../../qa-v5/optics-o5r/README.md) |
| Media / Layout | unmodified, frozen |
| Main merge | **NOT AUTHORISED** |
| Old F0 layout baseline | Historical Accepted Baseline, superseded by SourceExact Composition |

### Preview

| | |
| --- | --- |
| Bare route | `http://127.0.0.1:5280/` — still V3, unchanged |
| Current F2.7 | `http://127.0.0.1:5280/?composition=v2` |
| Source-exact | `http://127.0.0.1:5280/?composition=sourceExact` |
| Source-exact foundation | `http://127.0.0.1:5280/?composition=sourceExact&foundation=layout&annotate=0` |
| Typography before | `http://127.0.0.1:5280/?composition=sourceExact` at `847347d^` |
| Typography candidate | `http://127.0.0.1:5280/?composition=sourceExact` at the branch tip |
| Evidence index | [`qa-v5/t1/README.md`](../../qa-v5/t1/README.md) |
| Private review package | `qa-v5/private/t1-review.zip` (git-ignored) |
| Superseded package | `qa-v5/private/fsx-a-review.zip` — captured against a frozen canvas, do not use |

## T0 — render loop repair

The FSX-A round's `tick` contained `if (!this.adaptiveQuality) return;` above
`motion.step`, `grid.update`, `applyPose`, `labels.sync` and `drawFrame`. Every
FSX-A capture ran with the sampler off, so every one was taken against a frozen
canvas. That is why media-only and glass+media came out byte identical and the
24-frame recordings were 24 copies of one image.

| | |
| --- | --- |
| Render loop proof | **PASS 22/22** — 165 frames in 1200 ms with the sampler off; it was 0 |
| Hook redraw | every named hook advances a render stamp synchronously; with no QA hook called the explicit render stamp stays unchanged between two reads. The stamp counts `renderOnce()` calls, so it says the explicit draw path did not run -- not that the browser did not composite, which the stamp cannot see |
| Media-only vs glass+media | 70–84% of pixels differ, mean delta 11.6–18.1; was byte identical |
| Recordings | 24/24 unique frames desktop and mobile; offsets read back from the engine |
| Quality invariance | **PASS 57/57**, off the real mesh: bbox 656.64 x 492.48 (exactly 4:3), 5570/3242/1850 vertices, a new geometry per level, a redrawn silhouette each |

`qa-v5/fsx-a` is superseded for the media/glass comparison, the recordings and
the quality sweep. Its route proof and source contract stand.

## T1 — source-exact typography

| | |
| --- | --- |
| Typography contract | **PASS 29/29** measured Target properties, at all seven viewports |
| Container alignment | **PASS 47/47** — worst label corner error 0.011 px against the card mid-plane |
| Clipping / depth | **PASS 30/30** — Target's clip structure reproduced; 1199 sampled pixels, 0 wrong depth. **Scope:** `actualOverlappingCardPlaneSamples = 0`; with no two card planes observed overlapping on screen this establishes the clip structure and single-card interior ordering, not real occlusion ordering. Carried to the motion stage |
| Label ink outside card silhouettes | **0** at every viewport |
| Source contract, re-run at this tip | **PASS 36/36** — slot world 0.0, orientation 1.21e-6 deg, projected corner 0.0 px, engine vs Target DOM 0.005366 world; `npm run v5:target-layout-source` **PASS 14/14** |
| Viewport gate | **PASS 7/7 viewports, 13/13 engineering** |
| Title box bottom offset | `titleBoxBottomOffsetPct` -- card bottom to the bottom EDGE of the title box, as a percentage of card height -- matches the Target to three decimals at all seven viewports. Renamed from `titleBaseline`: the instrument reads boxes, not font metrics, so no baseline was ever measured |
| Build | PASS |

The defect: `TileLabelLayer` sized every label to the fixed `TILE` box while the
card is `frame.planeWidth` x `frame.planeHeight`, and every type size is a
container query against that box — so type was scaled against a card that did
not exist, by +113% at 667x375 down to −26% at 1920x1080. It was −1.4% at
1440x900, the viewport the layer was tuned at, which is why it went unseen.
See [`SOURCE_EXACT_TYPOGRAPHY.md`](SOURCE_EXACT_TYPOGRAPHY.md).

## M0 / M1 — source-exact motion

The Target's motion was read out of its bundle, not fitted to a recording. The
whole model, its absences and the two things that make it feel the way it does
are in [`SOURCE_EXACT_MOTION.md`](SOURCE_EXACT_MOTION.md); the contract itself
is [`config/target-motion-source-v1.json`](../../config/target-motion-source-v1.json).

What our previous model had and the Target does not: wheel handling of any
kind, a maximum velocity, a stop threshold, an exponential inertia decay, a
pointer-driven card tilt, a pointer-driven camera translation, a pointer-driven
light, and pointer capture on the drag surface. The Target's scene contains no
light object at all — its highlight moves because the camera orbits against a
fixed environment.

Our previous drag gain was 0.58 against the Target's 1.5, and the source-exact
path inverted `scrollX` at the layout boundary because the legacy model
subtracts the drag where the Target adds it. Both are gone: the model carries
the Target's own sign from the gesture onward.

### M1 result

| | |
| --- | --- |
| Motion gate | **FAIL — 806/870 landmarks.** 64 failures, in three related families plus eleven small travel rows |
| Contract vs Target | model replayed on the Target's own input: within the Target's own noise on **53/56**, raw and time-aligned |
| Recovery instrument | **exact** — 0.006–0.025 world units against our engine's own scroll over 20 runs |
| Wrap continuity | **0 visible teleports**, ours and Target, screen-space at the brief's 2 px |
| Wheel absence | **72/72**, deltaMode 0/1/2, both sides |
| Axis signs | **0 failures** |
| Card / label under motion | **PASS 34/34**, worst corner delta well inside 1 px |
| Typography regression | **PASS 4/4** — container alignment 47/47, depth 30/30, label ink 0 outside |
| Depth carry-forward | **PASS 37/37**; `actualOverlappingCardPlaneSamples = 0` → **NOT APPLICABLE — no overlapping card planes observed** |
| Source contract, re-run at this tip | **PASS 36/36**; `npm run v5:target-layout-source` **PASS 14/14** |
| v1 / v2 / bare | geometry identical to `7dc7cf1` on all six route-viewport pairs; the pixel comparison is provably incapable across origins and is reported, not gated |
| Console / page errors | **0** |
| Build | PASS |

The 64 failures are one fact three times over: the Target's scroll advances
12.7% off its local trend on a typical frame and ours advances 1.8% — two
independent rAF loops against our one. It surfaces as `frameStepJitterFraction`
(ours lower in 26/26), `maxFrameVelocityStep` (7/7) and the dolly peak, whose
magnitude source is a backward difference that jitter inflates.

### M2 result — the instrument was the largest single defect

The M1 replay decided which frame consumed an event with `event.t <= frame.t`.
Those are two different points in the frame pipeline: listener entry on
`performance.now()` against the rAF timestamp, which is when the frame STARTED.
Chrome dispatches input before the rAF block, so a median of 88% of all
recorded events were handed to the following frame — one dispatch late, always
the same direction. That is the whole of M1's "persistent final error": 0.1457
of travel on every reverse-flick row and 0.0527 on every fast-flick row,
identical across four viewports and three repeats.

M2 replaced the clock comparison with a monotone callback counter, sealed a
Target-only baseline by SHA-256 before capturing any candidate, and made the
one-sided gate direction-aware.

| | |
| --- | --- |
| Motion gate | **FAIL** — 149 failures of 2472 product-gated comparisons, 90 distinct cells across the 120 Hz and 60 Hz grids |
| Engine vs contract v2 | 180 rows, **175 exact to floating point**, 3 sub-frame race, 2 failures |
| Contract vs Target | the frozen contract on the Target's own input reproduced it in **1518/1576** |
| Dolly attribution | M1 blamed the Target's frame-step jitter. **Refuted by measurement**: feeding the magnitude spring the Target's own jittered scroll moved the peak by 0.3% while the Target stood 17.7% from the frozen law |
| Failure split | 92 dolly, 53 release velocity, 1 travel, 3 systematic sign |
| MOTION-EXC-01 | raised: the Target's raw frame-step scheduling irregularity is not reproduced |
| Baseline | sealed at `a0a5a1f6b95b685e18453d889a9a57798fd6f73e9e47d9edc9c2a087ddf29224` |

Evidence: [`qa-v5/motion-closure/`](../../qa-v5/motion-closure/). M2 recorded a
hypothesis it deliberately did not act on — that the magnitude source has two
writers that disagree by construction — because closing a residual by picking
whichever order fits is a fit and not a reading. M3 read it.

### M3 result — the magnitude has two writers and the Target's scheduler picks one

**ACCEPTED by product.** Motion behaviour baseline `4df03f2`, accepted review
tip `b99e5ce`. Motion / pointer / touch are frozen — the contract, the accepted
known deviation (release scroll retarget, +1 postRender frame), and the
standing items (two unresolved summary rows, eight `dollyPeakTimeMs` cells) are
in [`MOTION_FREEZE_CONTRACT.md`](MOTION_FREEZE_CONTRACT.md). M4 is not
authorised.

M2 recorded the two-writer hypothesis and refused to act on it. M3 read the
Target's frame scheduler and found which writer wins, so the order is a source
read rather than a fit.

| | |
| --- | --- |
| Writer order | `gestureLastWhileActive`, read from the bundle: `onPan` is scheduled with `immediate=true` into the update Set that is being iterated, so the gesture writer lands after every spring tick; `onPanEnd` is scheduled onto `postRender` from the pointerup listener, so it is first in that set, ahead of the spring's retarget |
| Dolly on the Target's own input | signed **1.0249**, median absolute **2.58%** — against **0.9514** / **17.82%** under the pre-M3 order. Both numbers are reported: the drag and flick residuals have opposite signs and the signed one cancels them |
| Dolly cells failing | **8 of 432**, from 92 of 432 under the M2 order |
| Engine vs contract | **180/180 exact to floating point**, 0 failures, worst final error 0.00e+00 against a 0.13276 gate |
| Release velocity | **132/132 exact to floating point** against the engine's own release record. 48 runs carry no release by design — 36 wheel, 12 pointer sweep |
| Landmark failures | **65** of 2570 comparisons, 2472 product-gated |
| Attribution | candidate-owned **0**; source contract 38, target input variation 18, instrument unreadable 7, unresolved **2** |
| Constants | unchanged. Drag gain 1.5, fling 0.1, both springs, 3 px threshold, 100 ms window, orbit ±0.05 rad, dolly formula, publication delay all frozen |
| MOTION-EXC-01 | still raised, unchanged, and still covers only the raw single-frame numbers |

Two results that are worth carrying forward on their own:

- **The release velocity is quantised.** framer-motion's window is a strict
  `> 100 ms` over a history fed at frame rate, so a release measures over N or
  N+1 points and nothing between. The Target's own three repeats of one scripted
  gesture land on opposite sides in **33 of its 44 cells**, spreading its own
  release velocity by a median 7.78%. No implementation can close that; the gate
  was deliberately NOT taught to forgive it.
- **The eight dolly cells that still fail are all `dollyPeakTimeMs` on slow
  drags**, with a candidate residual of **0.0 ms** on every one. Our capture's
  31-step drag ran 1106 ms against the Target's 1003 ms, and a flat dolly peak
  sitting at the release moves with it. Reported per §8 and not excepted.

Evidence: [`qa-v5/motion-final/`](../../qa-v5/motion-final/).

## V0 — source-exact CSS3D label coverage culling

**ACCEPTED by product.** Culling behaviour baseline `820cd92`, accepted review
tip `b4a4450`; the freeze is recorded in
[`CULLING_FREEZE_CONTRACT.md`](CULLING_FREEZE_CONTRACT.md). The Target keeps ~16 labels alive
at 1440x900 where our page kept 81 — its only test was a JS backface
dot-product. V0 read the Target's culling out of its bundle byte by byte
(30 anchored sites, live bundle byte-identical) and implemented it in
[`SourceExactLabelCulling.ts`](../../src/ui/SourceExactLabelCulling.ts):
a dedicated dolly-free coverage camera (`Py.position.set(d,h,f)` against the
render camera's `(d,h,f+p)` in one source statement), the four projected card
corners, the NDC z skip, the 1 px² minimum area, the exact 64 px margin.
Visibility / culling only; every frozen system untouched.

| | |
| --- | --- |
| Target rule source verification | **PASS** — 20,131 Target frames replayed slot-for-slot; 0 beyond boundary; 363 wrap-seam rows, every one with the flip demonstrated under ±1e-3 perturbation |
| Candidate rule consistency | **PASS** — 20,372 frames, 0 mismatches; snapshots bit-exact to 9.1e-13 px |
| Settled slot identity vs Target | **40/40 states identical, by ILG code** (incl. resize and orientation flip) |
| Lost / intruding / stale labels | 0 / 0 / 0 — stale-rect check worst delta 0.0135 px over 2,456 drawn labels |
| Edge pop-in | candidate 171.7 px vs Target's own 171.0 px worst entry overlap — comparable, PASS |
| DOM pressure | transform writes p95/frame 120 → 36 (Target 36); sustained-input p95 100 → 17 |
| Performance | labels.sync 0.3 ms p95, frame time unchanged (GPU-bound), heap bounded, quality untouched |
| Depth | **NOT APPLICABLE on screen, measured**: 0 front-facing overlaps inside the strict viewport; 30 pairs live only in the 64 px margin band |
| Motion freeze smoke | PASS — engine vs contract 15/15 exact, release history 11/11, wrap teleports 0; card/label corner delta 34/34 |
| Regressions | source contract 36/36, layout 14/14, typography 4/4, tsc + build PASS, console/page errors 0 |

Observed in source and deliberately NOT applied: the Target drives its WebGL
glass-mesh `visible` from the same verdict. Outside V0's label mandate;
flagged for a product decision. Evidence:
[`qa-v5/culling/README.md`](../../qa-v5/culling/README.md); private package
`qa-v5/private/culling-review.zip`.

## O0 / O1 — first Liquid Glass optics candidate

**O1 FAILED ITS ABSOLUTE GATE**, by its own pre-registered failure
condition. Everything below is measured, committed evidence:
[`qa-v5/optics/README.md`](../../qa-v5/optics/README.md).

O0 read the Target's complete glass shader out of its bundle (17
byte-anchored sites: 5-sample IOR-spread refraction inside the card's OWN
media with per-channel tent weights, fresnel-capped LERP toward a white
equirect env reflection, white rim, NO scene-colour pass, NO tone mapping)
and measured both pages' edge bands. System A (edge energy / dispersion /
saturation) was selected and its failure conditions pre-registered in
[`o1-selected-system.json`](../../qa-v5/optics/o1-selected-system.json)
BEFORE any candidate code.

The candidate implemented a screen-space ANALOGUE of the Target's
dispersion (commit `v5-o1-first-optics-candidate-code`) — product wording
correction: the 5 spectral samples and per-channel-normalised tent
weights are source-read, but the implementation scales an EXISTING
screen-space refraction offset per sample rather than recomputing
`refract()` for each Target IOR sample. Do not describe it as "verbatim
Target dispersion"; earlier commit messages and the sealed O1 evidence
README predate this correction (the sealed tree is not edited because its
MANIFEST seals file hashes). Every touched metric moved in the
pre-registered direction on desktop AND mobile (edge chroma 63.1 → 59.6
desktop rest, fringe R-B down in all 4 states, bright/dark cohorts both
falling 4/4, media-only bit-identical to pre-O1, every frozen suite PASS)
— and the **floor experiment** ended the round: rebuilt with
`dispersionSpread=0`, the page measures edge chroma 59.04 vs Before's
63.13. The entire dispersion mechanism is worth **4.09 edge-chroma
points on our own page**; its share of the gap to the Target is
**9.5–15% depending on the Target's media draw**. The white reflection
ratio at spread 0.3 differs from the floor's by **+0.001**: the system's
one tunable lever cannot move the white band at all. The pre-registered
condition "white reflection ratio does not move (wrong root cause →
System B next)" fired.

The corrected attribution, forward-written into
[`o0-source-diagnosis.json`](../../qa-v5/optics/o0-source-diagnosis.json)
(`attributionCorrectedByFloorExperiment`): the Target's edge is
desaturated by System B's mechanism — a fresnel-capped LERP toward the
white studio env reflection — while our shell ADDS white over a
still-saturated refracted edge. The Target's bright/dark edge cohorts are
nearly equal (18.9 / 21.7) where ours diverge (75 / 28): its edge chroma
is luminance-independent, ours is media-dominated. O2 must select System
B and must read the `targetLaneVariance` warning: the Target's absolute
band statistics swing with its per-load media shuffle by 20–50× the
deltas under judgment, so O2's gate must lean on within-page controls and
source reads, not cross-page absolutes.

The screen-space dispersion analogue visibly reduces the synthetic
cyan/magenta fringe lines and regresses nothing; it stays in the tree as
an EXPERIMENTAL LANE only (product decision). It re-enters the product
path only if the O2 A+B lane wins the pre-registered interaction gate —
never retroactively from the failed O1 result.

## O2 — System B: White Studio Reflection / fresnel-capped LERP

**ACCEPTED by product review.** Behaviour baseline
`e913aa6a33e384ba4fc80eb28b9a8718fb20e5b9`, accepted review tip
`fd12b97c4d9a28b732d3611035d98446a0201c68`; selected lane **A+B** by the
pre-registered rule (all six strict criteria — the exact path §四
authorised for System A to re-enter the product). What acceptance freezes,
and what it deliberately leaves open for O3, is
[`O2_OPTICS_FREEZE_CONTRACT.md`](O2_OPTICS_FREEZE_CONTRACT.md).
Evidence: [`qa-v5/optics-o2/`](../../qa-v5/optics-o2/README.md) + private
`qa-v5/private/o2-optics-review.zip`.

The round ran in the pre-registered order. First the deterministic
shared-media harness (10/10 PASS: byte-anchored HLS/mp4 renditions with
identical elementary streams served to BOTH pages, frozen at 4.0s,
decoded-frame hashes EQUAL cross-page, cover law verified three ways) —
every scored number is a same-media, mostly same-page number. Then the
System B source contract (14/14 byte-anchored sites, live bundle
identical; env = the Target-identical CC0 `studio_small_03_1k.hdr` with
recorded provenance, NOT copied from the Target). Then the sealed
pre-registration (`o2-selected-system.json`, committed before any
candidate code). Then the code, the scoring, the gates.

Findings a reviewer should read in order:

1. **A latent V1 shader state was discovered and worked around, not
   silently fixed.** three's TSL emits the shared `normalView` varying
   unpack only into the FIRST debug-select branch that references it, so
   the beauty path has always read the shared normal globals as zeros —
   V1's `facing` term (which only ever fed the QA shell opacity and a
   debug view) has always been 0. V1's frozen pixels are untouched;
   System B reads the interpolated geometry normal through its OWN
   varying and mirrors the Target's law in view space (rotations
   preserve dot products and commute with reflect — mathematically the
   Target's world-space form). Proven by compiled-shader dumps; recorded
   in the README and the code commit.
2. **Lane integrity is proven structurally at EXACT ZERO.** `?systemB=off`
   builds the pre-O2 shader byte-for-byte; both lanes are pixel-identical
   to worktree builds of `5159cf8` / `62d3ac4`, cross-origin and
   cross-build, both viewports. The registered runtime-neutralised proof
   carries a deterministic 1px/1-step FMA artifact (desktop only) —
   adjudicated with both codings in `lane-equivalence.json`; the FMA
   explanation is scope-bounded (media-only and A/B gates stay
   exact-zero, and measured exactly zero).
3. **The gates.** F1 white lever +44 dark-side edge luma (≥6 required);
   F4 saturated edge-chroma mean drop 18.0 (≥8 required, 2× the whole O1
   lever was the floor); A+B achromatic edge chroma 3.56/3.68 vs the
   Target's own 3.33/3.58; media-only 0 differing pixels everywhere; all
   frozen suites PASS. Three registered codings fired on instrument
   degeneracies (F5 zero-baseline division on achromatic media, F10
   neighbour-card mask pollution, F11 title-ink domination) — each gate
   JSON records BOTH codings with primary evidence; no threshold was
   edited after capture.
4. **One recorded instrument update:** the V1 render gate's shell law is
   mode-aware since O2 (shell defaults OFF in Beauty on source-exact —
   pre-registered; the gate now asserts ZERO shells in that mode, which
   catches shell ink leaking into Beauty, and re-passed 20204/20204
   frames clean).
5. **Observed, not gated:** the reflection band on black media is wider
   than the Target's (~15px vs 3.3px mean) — the geometry bevel spreads
   the white band more than the Target's analytic bevel. Recorded for
   product review.

Product review accepted the mechanism and, on finding 5, opened O3: the
reflection law is right and the field it is evaluated on is too wide, so
the support field — the geometry normal and the `strongLensRim` mask — is
NOT frozen. Every accepted parameter above is. O1's own verdict stays
FAILED; System A is in the product only through the O2 interaction gate.

## O3 — Target analytic bevel reflection support: FAILED ABSOLUTE GATE

O3 transcribed the Target's own support field from the byte-anchored
source contract (29 sites, 0 failed) into
[`TargetBevelFieldV4.ts`](../../src/materials/TargetBevelFieldV4.ts) and
swapped exactly two inputs to the frozen System B block: the analytic
bevel normal for `v_o2NormalView`, and the rounded-rect SDF rim
(`smoothstep(-rimWidth, 0, sdf) × 0.11`, 8.3 px) for the `strongLensRim`
attribute (≈31.7 px). Two lanes, one build, one page, selected by
`?reflectionSupport`; no parameter tuned, no threshold moved.

**11 of 20 items passed, 9 failed, none pending.** Full record in
[`qa-v5/optics-o3/`](../../qa-v5/optics-o3/README.md).

The candidate moves every measurand toward the Target — band width
15.3 → 8.7 px, dark-side luma 95.1 → 77.6, dark/bright ratio
0.5006 → 0.4388 — and passes the two items scored on that movement (6, 7),
plus the same-direction item (15), the pop item (16, worst adjacent-frame
change 2.1% against a 40% ceiling), every structural item (1, 2, 12, 17,
18: the control lane is still bit-for-bit the e913aa6 program) and all
sixteen frozen suites (19).

It fails because the support field is not the binding constraint. Captured
at the registered floor states, with `envMixScale=0, rimScale=0` the two
lanes are **identical** and the frozen refraction / dispersion /
adaptive-contrast composition alone paints:

| Viewport | Frozen base, System B off | O3 candidate | Target |
| --- | --- | --- | --- |
| 1440x900 | **9.7 px** | 8.7 px | 3.3 px |
| 390x844 | **6.0 px** | 3.0 px | 1.5 px |
| 844x390 | **6.0 px** | 3.0 px | 2.0 px |

At every viewport the base alone exceeds the Target's entire band. No
change to the reflection support — the Target's own included — can go
below a floor that exists with the reflection switched off. The residual
lives in `adaptiveEdgeLift` / `contrastShaped` and the refraction edge
treatment, which O3 was forbidden to touch. That boundary is the round's
result.

Two failures need reading rather than tallying. Item 13 (gutter) scores
+0.020 against a 0.006 ceiling, but outside the **true** glass silhouette
the two lanes are bit-identical — the delta lives entirely between the
flat layout quad the instrument masks and the larger silhouette the
bulged lens projects. Items 8–10 (edge chroma) rise partly because the
analytic normal samples more chromatic HDR at its 60° slope clamp, and
partly because removing O2's over-wide white rim stops it diluting the
chroma mean — `fringeWidthPxMean` falls on every saturated asset.

The sealed default-flip rule's negative branch executed: the shipped
default stays `reflectionSupport=geometry`. Every O2 parameter, and the
O2 acceptance, are untouched.

Product review then **accepted** the source forensics, the
`TargetBevelFieldV4` transcription (engineering pass), the corrected
instruments, the `target-sdf` diagnostic lane and the frozen-body-floor
finding, and **rejected** the candidate as shipped default, the default
flip, and any further rim / fresnel / env tuning. O3 is neither "no
progress" nor product accepted: the candidate failed its own gate and
the knowledge the round produced was accepted. See
[`O3_PRODUCT_REVIEW.md`](O3_PRODUCT_REVIEW.md).

## O4 — frozen body floor attribution: candidate FAILED, attribution accepted

**O4A found a live defect.** The shipped Beauty refraction path consumes a
**zero normal**. The geometry normal is unpacked exactly once in the
generated WGSL, inside the `normals` debug branch; every other branch —
Beauty included — aliases a zero-initialised `var<private>`. Two debug
views reading it in different branches of one program disagree: `normals`
varies, `fresnel` is exactly constant. This is the same TSL codegen hazard
O2 root-caused for System B, and it explains GATE-005 — the
refraction-offset view was reporting a real zero, because
`projectedNormalOffset` is identically zero. **Recorded, not repaired**:
§三 forbade fixing during the audit, and the factorial then selected a
different subsystem. It remains an open, precisely-located defect.

**The attribution.** A 2^5 factorial over refraction displacement, blur,
adaptive shaping, dispersion and output transform, replicated at both
states of the normal repair — 260 desktop captures over four media, plus
OFAT and pairwise at both mobile viewports. Exactly one factor is eligible
under the rule sealed beforehand: **local adaptive body shaping**
(`contrastShaped`, `adaptiveEdgeLift`, `adaptiveInternalShadow`), which
explains 141% of the desktop excess with an interaction ratio of 0.13 and
is the largest contributor on all four media.

**The candidate failed 4 of 12 gate items**, and the reason is worth more
than the verdict:

| Viewport | control floor | candidate floor | control shipped | candidate shipped | Target |
| --- | --- | --- | --- | --- | --- |
| 1440x900 | 9.7 px | **1.7 px** | 15.3 px | 13.0 px | 3.3 px |
| 390x844 | 6.0 px | **0.0 px** | 8.0 px | 7.0 px | 1.5 px |
| 844x390 | 6.0 px | **0.0 px** | 8.0 px | 7.0 px | 2.0 px |

Removing the body shaping takes the floor to essentially nothing — past
the Target, which is why the two-sided window item fails — and the shipped
band still barely moves, because with the body dark the O2 reflection
support paints the band on its own.

**O3 showed the support field is not the binding constraint given this
body. O4 shows the body is not the binding constraint given this support.**
Both are constraints. Neither round was permitted to change the other, so
neither could pass alone. That is the finding a combined decision now has
in hand.

The §十 support re-test was **not run**: it is authorised only after the
body candidate passes its own gate, and running it anyway would be the
search for a passing combination that §七 and §八 exist to prevent.

The control lane is **exactly zero** differing pixels against an e913aa6
build at System B OFF, and the all-off diagnostic program is
byte-identical to the pre-O4 program at every quality level. Shipped
default stays `bodyFloorMode=current`.

## FSX-A integration hardening

| | |
| --- | --- |
| Route proof | **PASS 6/6** — `?composition=sourceExact` reaches V4 without `optics=v4` |
| Quality invariance | **PASS 43/43** — corner delta 0 px across high/medium/low/high, contract PASS at every level |
| Adaptive quality | now fires: 2 spontaneous changes recorded by the running sampler |
| Beauty baseline | 7 viewports x 4 render states, 0 capture errors |
| Detector residual | **corrected**: all pairs 132.49 px / 280.50 px, high-confidence 14.17 px / 67.51 px, pairing confidence 0.357 |
| Build | PASS |

Three integration defects fixed, none of them in the composition:
`?composition=sourceExact` routed to V3; `AdaptiveQuality.sample()` compared its
return value with the field it had just written, so the adaptive path had never
fired; and the quality rebuild dropped the source-exact 4:3 geometry override.
See [`FSX_ACCEPTANCE.md`](FSX_ACCEPTANCE.md).

## Commit ledger

**Accepted by product**
- `62f5772` F0/F1 Foundation baseline · `b524dc5` NL-03 media focus
- M3 motion source reconciliation: `b8cbbd2` writer-order forensics · `4df03f2` writer-order code (motion behaviour baseline) · `8f906f1` evidence · `b99e5ce` hygiene (accepted review tip) · `17fcaca` acceptance record (docs)
- V0 label coverage culling: `820cd92` code (culling behaviour baseline) · `7f9e0ef` evidence · `b4a4450` package hygiene (accepted review tip)

- V1 render culling: `cba2e72` forensics · `b625f90` code (render culling behaviour baseline) · `04cff37` evidence · `5159cf8` accept record — GATE PASS, frozen
- O2 optics: `62498e5` shared-media harness (10/10 PASS) · `8147156` System B source contract + pre-registration (sealed before candidate code) · `e913aa6` System B code (behaviour baseline; branch-safe implementation, structural lane proof EXACT 0) · `fd12b97` evidence (accepted review tip) · the product-accept record — **ACCEPTED**, selected lane A+B; mechanism frozen, support field open

- O5 optics: source-exact card optical body — `5439e99` O4 product review + O5 open · `68b022a` source contract + architecture + sealed instruments · `b11051a` candidate code + control identity + compiled audit · `c940a31` evidence — **FAILED ABSOLUTE GATE** (8/14), sealed and not rewritten. **REVIEWED**: architecture, source contract, own-media refraction, control identity, compiled audit, band width and spectral structure ACCEPTED; the default flip and Target Visual PASS NOT YET ACCEPTED. See [`O5_PRODUCT_REVIEW.md`](O5_PRODUCT_REVIEW.md). Shipped default `opticalBody=current`

- O5F optics: material cache + portrait source reconciliation — `9935bf4` O5R product review + O5F open · `30b91f6` material-cache code (finite keyed sets, switch+rebind, the convex-geometry quality defect retired) · `68d9152` portrait source forensics (six QA-only term views, Beauty program byte-unchanged; §六 identity + §七 stress both PASS ride in the commit so the §八 ordering is a git fact) · `c545649` the one §十一 correction (`targetDeviceTierV5()` drives the unclamped lane's sample count; §十四 addendum sealed in the same commit) · `<evidence>` interim closure evidence — **ROUND PAUSED BY USER before §十四 sessions completed; no §十七 state asserted.** Phase A PASS 10/10; the tier mismatch proven live and corrected; the correction measured NOT to close the sealed P0 windows; chain term-faithful; crop eliminated; ring quantified
- O5R optics closure: corrected instruments + source environment — `8c26630` O5 product review + O5R open · `3169a23` instrument contract (definitions and the HDR radiance audit, sealed before any O5R candidate pixel) · `726ee02` source-environment code (`envSampleCeiling` removed from the target-source lane; `environmentMode=source|off` structural programs; QA-only refraction and silhouette views) · `445037e` product closure evidence — **corrected gate FAIL (7/14)**, and the sealed O5 gate re-run unchanged to its own 8/14. The portrait residual did **not** close, and §十二 found a candidate-lane heap retention the shipped lane does not have. **O5R TARGET-SOURCE BODY FAILED CORRECTED PRODUCT GATE** — **REVIEWED** in [`O5R_PRODUCT_REVIEW.md`](O5R_PRODUCT_REVIEW.md): the source-environment correction accepted, `target-source-unclamped` the only active candidate, the sealed clamped lane regression-only; shipped default stays `opticalBody=current`. O5F opened on the material retention and the portrait source reconciliation

**Candidate, not accepted**
- O0/O1 optics: `03676b1` O0 source diagnosis + pre-registered system selection · `e01fb30` O1 candidate code (the Target's dispersion law, System A only) · the O1 evidence commit — **O1 FAILED ABSOLUTE GATE**; attribution corrected to System B. System A ships only through the O2 interaction gate; that verdict is not overturned
- O4 optics: frozen body floor — `968e7dd` O3 product review + O4 open · `a1ad929` O4A audit + Target body source + sealed instruments · `3894369` factorial + attribution + selection · `66684dd` selected candidate code · `df467ed` gate coding addendum · `5a87751` evidence — **candidate FAILED ABSOLUTE GATE** (8/12); attribution and the O4A zero-normal finding accepted, reviewed in [`O4_PRODUCT_REVIEW.md`](O4_PRODUCT_REVIEW.md). Shipped default `bodyFloorMode=current`
- O3 optics: Target analytic bevel reflection support — `b4dbb16` O2 product-accept record · `b7fe128` source contract + sealed pre-registration (before candidate code) · `669046e` candidate code (the Target's field, two swapped inputs) · the O3 evidence commit — **O3 FAILED ABSOLUTE GATE**, 11/20 items. The mechanism is correct and the transcription is exact; the frozen base is what binds. Shipped default stays `reflectionSupport=geometry`
- `dd6d7bf` / `4ca597f` F2 · `b5cff63` F2 audit · `730beb7` F3 diagnosis
- `f56f55e` / `ba4ba32` F2.5 · this delivery's three F2.6 commits

**Superseded / withdrawn**
- F2's `cross-validation.json` — gain stored as scale, hold-out not held out.
- F2's gate revision that replaced the 3 px absolute gutter threshold with a percentage.
- F3's `radiusY = -2053.4` — a parabolic diagnostic seed.
- F2.5's portrait law `1.9468 / -0.31` — **misses the held-out scale by +5.09%**. Replaced by the cross-validated `1.87715 / +0.12204`, still selectable as `?portraitLaw=p0`.
- F2.5's rest-phase scale switch at 0.674 — **23/39 against the runtime law**. Replaced by the aspect rule.
- **F2.6's `portrait-candidate-gates.json` — INVALID.** `portraitLaw` never reached the camera, so p0 and p1 rendered byte identically and that file compared one candidate with itself. Superseded by `qa-v5/f26r/portrait-candidate-gates.json`.

## Verdicts (F2-SX source-exact)

| | |
| --- | --- |
| Engineering result | **READY FOR PREVIEW-FIRST PRODUCT REVIEW** |
| Source contract | **PASS 36/36** — slot world 0.0, orientation 1.21e-6 deg, projected corner 0.0 px, engine vs Target DOM 0.005366 world |
| `npm run v5:target-layout-source` | **PASS 14/14**; failure branch exercised against a mutated contract and exits 1 |
| Pixel gate | **8/14** viewports, **115/122** checks. F2.7 measured identically: 7/14, 112/123. |
| Runtime | **PASS 64/64** |
| F0 regression | **PASS 20/20**, baseline frame byte-identical |
| v1 / v2 / bare route | byte-identical to before; `sourceExact` is NOT the default |
| Build | PASS |
| Target visual result | Not asserted |

Every remaining pixel failure is **gutter centre** (3.5-6.5 px against 3 px).
Card size, card centre, edge yaw, row parity, centre dark band, overlap and
large void pass at every viewport. Two independent measurements show the
residual is the detector meeting a video-filled glass card: reading the Target's
own frame, the detector places card centres up to 2.67 px and widths up to
71.89 px away from the Target's OWN DOM geometry, and our frame reads closer to
that truth than the Target's own frame does at all nine viewports tested.

### Old verdicts (F2.7, on the foundation branch)

| | |
| --- | --- |
| Engineering result | **READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW** — see the caveat in `qa-v5/f27/README.md` |
| Absolute Target Gate | **FAIL** — 7/14 viewports, 107/118 checks. Same measurement scores the F2.6R config 7/14 and 96/113. |
| Target phase determinism | **STABLE** — 12 viewports x 5 cold loads, no variation |
| Row-origin phase law | **36/36** viewports against live Target DOM state, no fitted constant |
| Portrait vertical hold-out | 390x844 card height **4.79% → 1.03%** (V1), 1.57% (V2 with the centre seam fixed) |
| Runtime | **PASS** 32/32 |
| F0 regression | **PASS** 20/20, baseline frame byte-identical |
| Build | PASS |
| Target visual result | Not asserted |

Contract coverage:

```json
{
  "cardCentre": "NOT_MEASURED",
  "cardSize": "NOT_MEASURED",
  "gutterPx": "FAIL",
  "edgeYaw": "FAIL",
  "rowParity": "NOT_MEASURED",
  "centreDarkBand": "FAIL",
  "overlap": "PASS",
  "largeVoid": "FAIL",
  "f0Regression": "PASS"
}
```

NOT_MEASURED comes from 1920x1080 and 667x375, where no row pair survives the
gate's conditioning. Stated, not hidden: 1920x1080's PASS means "nothing
measurable failed".

## F2.7 — the Target's layout is no longer inferred

The authorised read-only source forensics pass recovered the Target's entire
layout initialisation. See
[`TARGET_RESPONSIVE_SOURCE_FORENSICS.md`](TARGET_RESPONSIVE_SOURCE_FORENSICS.md).

- Initial scroll is **(0, 0) at every viewport**; there is no row branch to unwrap.
- The rest phase is the **parity of the Target's pool row count**, not aspect
  ratio. `restOffsetX = (rows/2) % 2 === 0 ? cellW/2 : 0`, 36/36, no free parameter.
- The responsive law is **`max(width, height)`** and is continuous at
  `width == height`. The 1.84x orientation step F2 recorded does not exist.
- The grid is a **sphere**, one radius for both axes, not a cylinder plus a
  separate `radiusY`.
- Three of the four phase mismatches the F2.7 brief named — 667x375, 780x470,
  1440x1080 — **were not mismatches**; F2.6's pixel classifier was wrong there.
- Video assignment is shuffled with `Math.random()` per load. Geometry is not.

### Frozen parameters the source disagrees with

`TILE.width` −1.35%, `TILE.height` −2.63%, `GRID.cellW` −1.87%, `GRID.radius`
−2.59% at 1440x900 and **−18.6% at 390x844**, `restY0` +6.3%, `CAMERA.y` 8 against
0. All frozen by the F2.7 brief and therefore unchanged. The 390x844 edge-yaw
failure is a direct consequence of the radius entry.

## F2.6R correction

A harness defect, not a visual one: `portraitLaw` reached `compositionScale` but
not `viewZoom` or `effectivePerspectivePx`, so with the focal mechanism the
camera used the default law. p0 and p1 rendered byte identically at 390x844.
Fixed, and proven fixed by SHA, by projected card size (278.823 px against
266.576 px) and by a scale derived from the live camera projection rather than
from config. `runtime-law-proof.json` passes 12/12.

Consequence for the record: **p0 and p1 tie at 5/6 on the gate.** F2.6 claimed
p1 was better there. p1 still ships, on the cross-validation alone. No visual
parameter changed in this round.

## Shipping parameters

```
composition   v2   verticalMode tangent   portraitLaw p1
phaseModel    rowOrigin        portraitVertical v2
radiusY -4707.6   cellH 419.95
restY0  landscape -200.99      portrait -209.975  ( = -cellH/2 )
portraitGain      1.87715 + 0.12204 * (aspect - 0.5)     [frozen]
landscapeScale    S = width / 1440                        [frozen]
portrait scaleY   1.03883, applied in the projection, landscape untouched
restOffsetX       (targetRows(viewport) / 2) % 2 === 0 ? cellW/2 : 0
tangentStrength   1.0
```

`scaleY` appears in `qa-v5/f27/portrait-vertical-models.json`; the phase law has
no constant to verify. Not shipped, default off: `?landscapeRowOrigin=centred`,
the landscape half of the `restY0` correction — 9/11 against 7/11 with no
regression, in `qa-v5/f27/gate-diagnostic-landscape-row-origin.json`.

## P0 / P1 / P2

**P0 — 390x844 fails four contract checks.** Card height 4.905% (limit 3), edge
yaw 1.231 deg (limit 0.75), viewport centre not in a horizontal gutter where the
Target has one, largest void excess 2.423% (limit 2). This is not a rounding
residual: card height is 63% over and the centre-band miss is structural.

**P1 — the aspect phase rule has a fragile boundary.** 16:9 sits at 0.5625,
about 0.01 above the 0.5525 threshold. Four sweep viewports disagree
(667x375, 700x700, 780x470, 1440x1080).

**P1 — drag feel varies with viewport**; `dragGain` maps input px to world units
while world-to-screen no longer does. Motion is frozen.

**P1 — glass rim eats the gutter on yawed cards** (11 px rendered vs 19 px).

**P2 — some Target scale fits do not converge** and are excluded by a fixed RMS
threshold, listed rather than dropped.

**P2 — cyan/magenta rim fringing; typography 9.2cqw vs 12cqw; TILE.radius 58 vs ~61.5.**

**P2 — `npm run v4:source` fails**, four checks from the baseline and three from
V5. Not re-baselined; the product owner's call.

## Next stage

F2-SX is delivered. `sourceExact` is a separate, non-default path; v1 and v2 are
untouched and the old F0 layout baseline is a **Historical Accepted Baseline,
superseded only for the source-exact path**. Not merged to main.

The open product decision is whether to adopt `sourceExact` as the composition
baseline. Adopting it retires the fitted portrait gain, the portrait vertical
scale, `radiusY`, the aspect phase threshold, the fitted `restY0` and the fixed
9x9 world grid, and makes `TILE`, `GRID.cellW` and `GRID.radius` irrelevant to
layout: the source contract replaces all of them.

Typography is **ACCEPTED and frozen**; Motion is **ACCEPTED and frozen**;
label and render culling are frozen. Optics: the O1 System A candidate
**FAILED its absolute gate**; the O2 selection must read the corrected
attribution (System B) and the Target-lane variance warning in
`qa-v5/optics/o0-source-diagnosis.json`. The O2 round answered exactly
that: System B scored under the deterministic shared-media harness
(cross-page Target numbers secondary by design), candidate **A+B** won
the pre-registered interaction rule on all six strict criteria, and
product review **ACCEPTED** it — freezing the mechanism and opening O3 on
the reflection support field (see the O2 section and
[`O2_OPTICS_FREEZE_CONTRACT.md`](O2_OPTICS_FREEZE_CONTRACT.md)).

### Superseded F2.7 decisions

1. Whether to accept the remaining 390x844 residual as an explicit exception. It
   is **structural**, not a rounding residual: our frozen curvature radius is
   18.6% too small there because the Target's radius follows `max(w, h)` while
   our world is fixed and scaled by width.
2. Whether to ship the landscape half of the `restY0` correction, which is
   measured, runnable and regression-free but outside F2.7's portrait-only scope.
3. Whether to unfreeze `TILE`, `GRID.cellW`, `GRID.radius` and the scale laws so
   the composition can be rebuilt on the Target's own numbers rather than fitted
   to them. Forensics makes that a transcription job rather than a fit.

## Typography freeze contract

Accepted by the product owner at `34ad481` and frozen from that commit. Each
line names the artefact that holds it, so a later change is a diff and not an
argument. Changing any of these needs a new product authorisation.

| frozen | where it lives | what fixes it |
| --- | --- | --- |
| SourceExact `TileLabelLayer` plumbing | [`src/ui/TileLabelLayer.ts`](../../src/ui/TileLabelLayer.ts) | `attach(grid, mode, frame)` / `setFrame(frame)` / `applyBox()`; the frame is the single source of the label box |
| Scheme A: element = `frame.planeWidth` x `frame.planeHeight`, object scale = 1 | `applyBox()` | the Target's label element width equals the card plane width and its `matrix3d` basis columns are unit length, at all seven viewports |
| SourceExact `TYPE_Z = 0` | `TYPE_Z_SOURCE_EXACT` | radial distance from the sphere centre to each Target label = R within 1.2e-3 world units, across 36 viewports |
| `.tile-card-se` / `.se-*` typography CSS | [`src/style.css`](../../src/style.css) | 29/29 measured Target properties, at seven viewports, one instrument both sides |
| Rule / title / deck DOM order | `bindSlotCard` | the Target's rule PRECEDES the title; our earlier markup had title, rule, deck |
| Clip layer | `.se-clip` | one absolute layer at the card box, `overflow: hidden`, no clip-path, no radius |
| Footer typography | `.experiment-link`, `.cta-link`, `.cta-arrow`, `.brand-word` | the Target's own footer computed styles |

Scope carried forward rather than claimed: `actualOverlappingCardPlaneSamples`
is **0**, so the depth result establishes the clip structure and single-card
interior ordering only. Motion moves the planes; the count is re-taken there.

## Frozen systems

TileLabelLayer plumbing, the typography CSS above, LiquidGlassMaterialV4,
refraction, dispersion, blur, reflection, environment, video focus and MediaFit,
grid pool structure, TILE.width, TILE.height, GRID.cellW, the horizontal radius,
and the accepted F1 are all unchanged.

`MotionController`, `InputController`, `MOTION` and the source-exact pointer /
pose mapping are **UNFROZEN** for the authorised Motion stage. Nothing else is.
