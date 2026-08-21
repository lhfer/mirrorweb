# Motion freeze contract

M3 passed final motion product review. This file is the record of what that
freezes, at which heads, and of the one deviation the product accepted with
open eyes. It contains no new findings — the findings live in
[`SOURCE_EXACT_MOTION.md`](SOURCE_EXACT_MOTION.md) and
[`qa-v5/motion-final/`](../../qa-v5/motion-final/README.md); this file is the
decision.

## Acceptance record

| | |
| --- | --- |
| M3 Motion Product Review | **ACCEPTED** |
| Motion behaviour baseline | `4df03f22f5f0868a53227e4a906a6d5e4942dcbf` — the commit whose captures scored the accepted gate |
| Accepted review tip | `b99e5ce1eec8e1f4fc4a84a9c51e44fa6134909d` |
| Motion / Pointer / Touch | **FROZEN** |
| MOTION-EXC-01 | **ACCEPTED**, scope unchanged — raw single-frame step values only |
| The two `UNRESOLVED_ATTRIBUTION` summary rows | kept as reported. The p threshold stays at 0.05; the 0.10 relaxation that would report zero was named and refused |
| The 8 `dollyPeakTimeMs` cells | recorded as a cross-capture input duration difference — our 31-step drag dispatched 3.4 ms/step slower than the Target's capture. No motion product code changes for it |
| M4 | **NOT AUTHORISED** |
| Main merge / force push | **NOT AUTHORISED** |

## What is frozen

The source-exact motion product behaviour, in full:

- `config/target-motion-source-v1.json`
- the SourceExactMotion product path
- the MotionController source-exact branch
- the InputController source-exact branch
- `gestureLastWhileActive` — the magnitude writer order
- the scroll, pointer and magnitude springs (stiffness / damping / mass)
- drag gain 1.5 and fling 0.1
- the PanSession threshold (3 px), history and velocity window (strict > 100 ms)
- pointer orbit ±0.05 rad
- the velocity dolly formula
- the one-frame publication delay
- the source-exact `applyPose`
- the CSS3D transform camera dolly — the transform camera carries the dolly,
  and may not be made dolly-free again
- touch and pointer cancel handling
- no wheel response
- no pointer capture
- the wrap–motion relation

QA-only readbacks may still be extended for later regressions. They must not
change any behaviour above.

## Known source deviation — release scroll retarget, +1 postRender frame

Read from the bundle in M3, recorded, and **not patched**: `onPanEnd` runs at
`postRender`, so its `d.set(target + velocity * 0.1)` schedules the scroll
retarget into the *next* frame's postRender — one frame later than a drag frame
does. The private video review found no perceptible blocking difference from
it. The product accepts it as a known deviation; no patch is authorised and no
MOTION-EXC-02 exists.

## What a later round may not do

- re-fit or re-derive any frozen constant or scheduling semantic;
- teach a motion gate to forgive the release-velocity quantisation
  (`SOURCE_EXACT_MOTION.md` → "The release velocity is quantised");
- create MOTION-EXC-02 or widen MOTION-EXC-01;
- reopen the two unresolved summary rows by moving the p threshold.
