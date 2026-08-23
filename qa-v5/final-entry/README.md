# MirrorWeb V5 — Final Experience Convergence

    Candidate  http://127.0.0.1:5293/?review=target
    Current    http://127.0.0.1:5293/?review=current
    Serve      npm run review

For a real device on the same network: `npm run review:lan` serves the same
build on `0.0.0.0:5293`, and `npm run review:lan:url` prints the addresses.
Adding `&status=1` mounts a live readout — FPS, frame p95/p99, longest frame,
quality, device sample tier, CSS3D mounted/visible/transform-writes,
material-cache size, black-frame count, and the entry's state and progress. It
is a QA surface: it does not exist without that query, and it was off for every
capture in this round except the one clip whose subject it is. **No real-device
result is asserted here.**

**Final product state: READY FOR ENTRY AND FRAME-PACING PRODUCT REVIEW.**

Target Visual PASS is **not** asserted. The shipped optical default is
unchanged (`opticalBody=current`), the shipped no-query default is still V3 and
reaches none of this round's code, and `main` was not merged, not force-pushed
and not touched.

---

## The defect, and what the Target actually does

The page finished loading and the cards were already sitting at their final
poses behind a percentage that faded out over 480 ms. There was no entry at
all: no convergence, no scale, no opacity, no stagger, no input gate.

The Target's entry is **one spring, on one number**. Read out of its bundle:

    b0 = mY(3)                                   // the grid gap ratio
    useEffect(() => { if (!ready) return
                      const a = animate(b0, grid.gapRatio,
                                        {type:"spring", stiffness:100,
                                         damping:18, mass:.7, restDelta:2e-4})
                      return () => a.stop() }, [ready, grid.gapRatio])

At gap 3 the cell pitch is four times the card width, so the columns either
side of centre are off the edges of the screen and what remains visible is a
handful of cards from far around the sphere — small because they are far away.
The gap collapses to the layout contract's 0.045 and everything sweeps inward
and grows into place. There is **no per-card stagger** in the source, no
opacity ramp and no scale animation; the apparent growth is the spacing, seen
through a perspective camera.

It is not a change to the frozen layout. The Target computes `cols`, `rows`,
`planeWidth`, `sphereRadius`, `cardScale` and the camera from `L6` with the
**static** gap ratio and multiplies only the pitch at placement time
(`A = d*(1+m)`, `E = f*A`). The pool never resizes, and the spring's rest value
*is* the contract's gap ratio — so the entry ends at the frozen layout exactly.

### The measurement does not take the source's word for it

Neither page is asked for its gap. It is **recovered**: each drawn card's ILG
code gives its pool slot, the frozen layout law and camera give where that slot
would project for a candidate gap, and the gap that best explains the whole
frame is solved for. Every frame is over-determined — five to thirty cards, two
coordinates each, one unknown — so a page whose entry moved anything *other*
than the gap could not be fitted by a single number, and the residual would say
so.

Recovered from the live Target and from the candidate, at all four review
viewports:

| | gap at ready | gap at settle | min gap | worst residual |
|---|---|---|---|---|
| Target | 3.00000 | 0.04500 | 0.04500 | 0.001 px |
| Candidate | 3.00000 | 0.04500 | 0.04500 | 0.001 px |

Over 22 000 to 56 000 individual card solves per viewport per side. The gap
never goes below the rest value on either page, which is what an overdamped
spring (damping ratio 1.076) must do.

---

## §七 — the entry visual gate

**PASS, 11 of 11 self-scorable items.** Items 12 and 13 — "reads as cards
gathering at normal speed" and "clearly visible at 1×" — are judgements at 1×
and are left to the product owner, with six recordings and four contact sheets
to make them on.

Matched on both sides: one locally generated media asset, one injected copy set
read back off the DOM afterwards, same viewport, DPR 1, labels on, footer on,
no debug overlay, cold cache, five runs per viewport per side.

The rule was registered before the candidate was scored: **the candidate's
median must fall inside the Target's own min–max for the same viewport.** The
Target's run-to-run spread is the threshold — a tighter rule would fail the
Target, and a rule picked afterwards would not be a rule.

| viewport | 50% crossing | 90% crossing | visible settle | mounted labels |
|---|---|---|---|---|
| 1440×900 | 146.7 → 147.5 ms | 358.6 → 358.0 ms | 908 → 900 ms | 100 = 100 |
| 390×844 | 147.5 → 147.3 ms | 358.5 → 358.7 ms | 851 → 850 ms | 96 = 96 |
| 844×390 | 147.3 → 147.2 ms | 358.2 → 358.6 ms | 834 → 842 ms | 80 = 80 |
| 700×700 | 147.5 → 147.4 ms | 358.4 → 359.1 ms | 833 → 1174 ms | 120 = 120 |

*(Target → Candidate, medians of five runs, all relative to ready.)*

Eleven of the twelve timing landmarks agree closely — the two gap crossings to
within 0.8 ms everywhere, and visible settle to within 8.6 ms — on Target
windows a few milliseconds wide.

**The twelfth is the exception and is flagged rather than buried.** At 700×700
the visible-settle landmark sits 340 ms above the Target's median, and passes
only because the Target's own window there is 418 ms wide — half its own median.
That landmark is a threshold on visible pixel movement, and the last cards to
stop moving are the ones furthest off-centre, so both pages are noisy on it at a
square viewport. It is a weaker statement than the p50/p90 agreement, not a
stronger one, and it is the one number in this gate a reviewer should look at
the recordings for rather than take on the table.

Two measurement definitions were replaced during the round, identically on both
pages, and both changes are recorded because they moved numbers:

- The **progress crossings** were originally per-card screen width. That
  returned nothing at all at 844×390 — it needs a card drawn at both ready and
  settle, and at a landscape phone the cards on screen when the entry starts
  are not the cards on screen when it ends. They now come from the recovered
  gap, which is defined on any frame with three drawn cards. There is one
  implementation of it, in `fe_entry_geom.read_run`, so the contract, the gate
  and the pacing reader cannot hold three definitions of one landmark — and the
  contract's windows and the gate's, computed from two independent Target run
  sets, agree to a couple of milliseconds.
- The **settle** landmark originally fired on the first of a *tracked* card set
  to exceed 0.15 px. The two pages do not produce the same size of tracked set
  from that rule — five on the Target and three on ours at a portrait phone —
  and since it fires on the first card, a bigger set settles later. It was
  scoring the two sides on detectors of different sensitivity: 75 ms of
  apparent difference in a quantity where the gap curves agreed to under a
  millisecond. It now reads every card drawn on both of a pair of consecutive
  frames.

The pre-registered **rule** never changed. Detail: `entry-gate.json`.

---

## §六 — the CSS3D mount lifecycle

**The Target does not recycle a bounded pool.** It mounts one element per pool
slot — `cols × rows` — and recycles nothing:

    Pd:  const c = useSyncExternalStore(Pl, Pu, Pc)   // Pu = () => b1.get()
         <div…><div…>{Array.from({length: c}, Ph)}</div></div>
    the grid's layout effect:  b1.set(e.cols * e.rows)
    Ph:  style {transformStyle, willChange, visibility:"hidden",
                backfaceVisibility}   — and no transform

An element belongs to one slot index for as long as it is mounted; a cols/rows
change adds or removes elements at the end of the array; a label gets its
transform the first time coverage draws it. §十二 says the CSS3D commit is
NONE if forensics disproves recycling. Forensics disproved recycling **and**
found the actual policy — and that policy has a mount count which is bounded,
derived from source rather than chosen, and which §八's "mounted CSS3D nodes
materially approach the Target" cannot be met without. It is implemented, and
isolated in its own commit so it can be dropped.

### Correcting the previous round's record

That round reported "Target 57 card elements against our 256" and read it as a
mount-policy difference. **57 was the count of elements carrying a `matrix3d`
transform** — the harness's card predicate requires one — which on the Target is
the number of labels *ever drawn*, not the number mounted. The Target's mounted
count at that viewport was 96. Both numbers are real; only one of them is the
mount policy.

### What it cost the main thread

Same instrument and the same block window as the previous round, so the numbers
compare directly: ±140/+260 ms around the page's first resize listener, gaps
over 6 ms, a 390×844 → 844×390 flip, five runs.

| | worst block | total blocked | DOM nodes | mounted labels |
|---|---|---|---|---|
| Target | 10.3 ms | 26.1 ms | 1423 | 96 |
| Before | 39.7 ms | 47.9 ms | 4155 | 256 |
| **After** | **13.3 ms** | **26.1 ms** | **1339** | **96** |

A reviewer re-deriving this with the maximum beat gap over a whole run will get
about 85 ms and should not be surprised: that number is dominated by the
pre-ready shader compile, which happens once, behind an opaque overlay, and was
not measured by either round. The window above is the published definition.

---

## §八 — frame pacing, never an average

There is no average FPS anywhere in this round's evidence. Through the entry
window — every frame of which is on screen and moving:

| | p50 | p95 | p99 | longest | frames > 16.7 ms |
|---|---|---|---|---|---|
| Target (desktop cold) | 8.3 ms | 9.2 | 9.4 | 9.4 ms | 0 |
| Candidate (desktop cold) | 8.3 ms | 8.5 | 9.2 | 9.3 ms | 0 |
| Target (mobile cold) | 8.3 ms | 9.3 | 9.4 | 9.4 ms | 0 |
| Candidate (mobile cold) | 8.3 ms | 8.8 | 9.2 | 9.3 ms | 0 |

The recorder samples every drawn card's bounding box every frame, which is real
work; it is paid identically on both pages and is reported per run rather than
hidden. Both raw and instrument-corrected distributions are in
`frame-pacing.json`.

The bounded perf smoke — five desktop runs at full speed and five on a touch
phone context under a 4× CPU throttle, with rotations, drag, flick and reverse
flick — is clean: no black card rect in any sampled still, no material-cache
growth or churn, no heap retention, all three quality levels exercised, media
advancing on both phases, zero errors. **60 Hz emulation was not run** and is
not reported.

---

## §十 — the bounded final smoke

    source contract          PASS  36/36 viewports
    layout source            PASS  14/14   (also fails if the Target bundle moves; it did not)
    typography contract      PASS  container 47/47, depth/clipping 37/37, ink PASS
    source-exact runtime     PASS  64/64   (slot identity + wrap continuity across resize)
    render + label culling   PASS  20164 frames, 0 slot mismatches, 0 label/mesh disagreements
    card + label under motion PASS  34/34
    motion freeze smoke      PASS  15/15 runs exact to floating point vs our frozen contract
    touch / pointer cancel   PASS  pointercancel + lostpointercapture, release velocity exact
    resize-walk regression   PASS  9 steps, 0 errors, material cache constant
    route check              PASS  shipped default / ?review=current / ?review=target
    console + page errors    0
    TypeScript               clean
    Vite build               clean

The motion freeze smoke is the one that had to be run rather than reasoned
about. The intro shares the `Spring` solver, `tick()` now advances it before
placement, and `pause`/`setOffset`/`reset` gained `finishIntro()` — so this gate
is the proof those insertions did not move motion. It reproduces our frozen
motion contract **exactly to floating point on all 15 runs**, with 11/11 exact
release velocities and 0 stranded gestures.

Read the raw report honestly: `m3-motion-gate.py`'s Target-landmark comparison
reports FAIL, at 40 failures over 2570 comparisons. So does the frozen baseline
`qa-v5/motion-closure` that §一.5 accepted, over the identical 2570 comparisons
— at 149. That comparison scores our frozen motion contract against the Target,
which §一.5 froze with those deviations standing; it is not the freeze verdict,
and the scoring rule was not changed for this run (`run-o5r.sh` has always taken
rc 0 or 1 there, and the O2 round recorded this gate the same way).

The two cancel sequences are new this round, not carried over: the O5R render
trace never ran them. Both terminate the gesture on the exact engine step the
listener saw and hand the spring the exact release velocity.

Glass identity and exposure are frozen by §一 and were not re-run as standalone
gates. That is not asserted on a diff alone: the source contract, the runtime
gate, the typography contract and the render gate all read the same engine state
those gates read, all pass on this build, and no file under `src/materials`,
`src/rendering` or `src/scene` was touched. `frozen-regressions.json`.

---

## Declared deviations

Six, all in `product-state.json` with their basis. The three that change what a
reviewer sees:

1. **Input unlocks at ready, not at settle.** The Target's drag surface is never
   gated on ready; the loading overlay is what blocks input, and it drops
   pointer events on the first frame of its exit. So the page is draggable while
   the cards are still converging — on both pages. §五.6 reads naturally as a
   lock tied to entry completion; the Target has none and this does not add one.
2. **`prefers-reduced-motion` is not honoured.** There is none in the Target's
   source. §五.13 says to record the deviation rather than copy or silently fix
   it. Recommended as its own product decision.
3. **The last percentage on screen is ~44% locally against the Target's ~90%.**
   Same rule — a spring chasing a monotonic value, with the loader removed
   before it catches up, so neither page ever shows 100 — but three local mp4s
   reach ready far sooner than three HLS streams.

---

## Files

| file | what |
|---|---|
| `target-entry-contract.json` | §四: the Target's entry, every statement labelled SOURCE_READ / RUNTIME_MEASURED / INFERRED, with the gap recovered from its live DOM |
| `entry-gate.json` | §七: the thirteen items, the pre-registered rule, the timing windows and which passes are tight |
| `css3d-lifecycle.json` | §六: the Target's real mount policy, the 57-vs-256 correction, and what the change cost the main thread |
| `frame-pacing.json` | §八: distributions across three windows, never an average |
| `frozen-regressions.json` | §十, each gate traced to the artifact that produced it |
| `product-state.json` | §十三: the state, its basis, six declared deviations, what is open next |
| `MANIFEST.json` | per-file SHA-256, commits, head SHAs, delivery limits |

Target pixels appear nowhere in this tree. The stills, contact sheets and
side-by-side recordings are in `qa-v5/private/v5-final-entry.zip`, which is
**not tracked by git** — `qa-v5/private/` is in `.gitignore`.

That package also carries a repair §十一 asked for: the previous round's private
package recorded a `reviewHead` its own evidence commit's amend cycle had
orphaned — a SHA no ref reaches and `git push` never transferred. Its manifest is
rewritten in place to the commit that actually carries that round's evidence,
with a note saying what was wrong.
