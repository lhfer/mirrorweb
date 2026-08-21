#!/usr/bin/env python3
"""The Target's CSS3D label coverage culling, read out of its bundle.

WHY THIS FILE EXISTS
--------------------
At 1440x900 the Target keeps ~16 labels alive per frame; our page keeps ~81,
because our TileLabelLayer has only a backface test. V0's brief is to restore
the Target's culling as a SOURCE READ -- which camera projects, what the exact
formulas are, in what order the DOM is written -- and explicitly NOT by tuning
a visible count until it matches. Every rule below is anchored to a byte
offset in the Target's application bundle and the verbatim text at it;
`verify()` re-finds each one, so a bundle that ever changes makes this file
fail rather than quietly describe a different program.

The bundle is the SAME file the running Target serves: the runner compares the
SHA-256 of the captured copy against a fresh download of
/_next/static/immutable/chunks/03lo820gl57km.js before this script is trusted.

Usage: v0-culling-forensics.py --bundle=<js> --out=<json>
                               [--live-bundle=<js downloaded this round>]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

# Minified module-scope names, so the claims below can be read:
#   Py  the coverage camera        L7  label DOM elements, by slot index
#   Pg  the unit quad corners      Pe  per-label {width,height} style cache
#   Pm/Pt/Pr scratch               Pn/Pi outer/inner CSS3D containers
#   PA/Pv    interactive slot set  Pa  cached container perspective px
#   PB  the camera component       PP  the grid + label sync component
#   bK/bX scrollX/scrollY          bZ  velocity magnitude   b0 gap ratio
#   b4  the interactive-set MotionValue
SITES = [
    ("coverageCameraDecl", 1968846,
     "Py=new eF.PerspectiveCamera(50,1,.1,1e4)",
     "A DEDICATED module-level camera exists for coverage. Its constructor "
     "lens is a placeholder; the real lens is copied from the render camera "
     "every frame (lensSync)."),
    ("lensSync", 1978083,
     '"PerspectiveCamera"===n.type&&(Py.fov=n.fov,Py.aspect=n.aspect,'
     "Py.near=n.near,Py.far=n.far,Py.updateProjectionMatrix())",
     "Same fov / aspect / near / far as the render camera, re-copied every "
     "frame before the coverage loop uses it."),
    ("orbitAngles", 1982196,
     "i=-(.05*u.get()),n=.05*c.get(),a=r.perspective,d=Math.sin(i)*"
     "Math.cos(n)*a,h=Math.sin(n)*a,f=Math.cos(i)*Math.cos(n)*a",
     "The pointer orbit: +-0.05 rad from the pointer springs, on a sphere of "
     "radius `perspective`. (d,h,f) is the orbit position WITHOUT dolly."),
    ("dollyFormula", 1982315,
     "p=function(e,t){if(t<=0)return 0;let r=3*t;return r*Math.tanh("
     ".04*e/r)}(bZ.get(),r.maxZoomZ)",
     "The velocity dolly `p`, computed from the magnitude value. It is about "
     "to be applied to ONE camera only."),
    ("coverageCameraPose", 1982727,
     "Py.position.set(d,h,f),Py.lookAt(0,0,0),Py.updateMatrixWorld(),"
     "t.position.set(d,h,f+p),t.lookAt(0,0,0)",
     "THE DECIDING LINE. The coverage camera Py sits at the orbit (d,h,f) -- "
     "pointer orbit included, dolly EXCLUDED. The render camera `t` sits at "
     "(d,h,f+p) -- the same orbit plus the dolly. Coverage is dolly-free."),
    ("quadCorners", 1968711,
     "Pg=[new eF.Vector3(-.5,-.5,0),new eF.Vector3(.5,-.5,0),"
     "new eF.Vector3(.5,.5,0),new eF.Vector3(-.5,.5,0)]",
     "The four projected points are the CARD CORNERS: a unit quad "
     "(BL, BR, TR, TL in local y-up space) that the mesh's world matrix "
     "carries to the card plane, because the mesh scale is the plane size."),
    ("meshPose", 1979622,
     "t.position.set(PT.x*u,PT.y*u,PT.z*u-u),t.quaternion."
     "setFromUnitVectors(P_,PT),t.scale.set(d,h,1)",
     "The mesh world transform: position on the sphere (radius u, centre "
     "z=-u), quaternion from +z to the sphere normal, scale = "
     "(planeWidth, planeHeight, 1). matrixWorld * Pg[k] = card corner."),
    ("cornerProject", 1979923,
     "Pm.copy(Pg[l]).applyMatrix4(e.matrixWorld).project(Py),"
     "Pm.z<-1||Pm.z>1)continue",
     "Each corner is projected THROUGH Py -- the dolly-free camera. The NDC "
     "z condition: a corner with z < -1 or z > 1 is SKIPPED (not clamped); "
     "z exactly -1 or 1 survives. No per-corner x/y test exists."),
    ("ndcToPx", 1980003,
     "let u=(.5*Pm.x+.5)*t,c=(-(.5*Pm.y)+.5)*r;",
     "NDC to CSS pixels: x -> (0.5x+0.5)*viewportWidth, "
     "y -> (-0.5y+0.5)*viewportHeight (y flipped). The AABB is the min/max "
     "over the surviving corners only."),
    ("zeroCornerReject", 1980113,
     "if(0===o)return{draw:!1,interactive:!1};",
     "If NO corner survives the z condition, the card is rejected outright."),
    ("minArea", 1980153,
     "let l=(a-i)*(s-n);if(l<=1)return{draw:!1,interactive:!1};",
     "Minimum area: the AABB area must be STRICTLY GREATER than 1 px^2. "
     "l <= 1 rejects."),
    ("margin64", 1980210,
     "let u=Math.min(a,t+64)-Math.max(i,-64),c=Math.min(s,r+64)-"
     "Math.max(n,-64),d=Math.min(a,t)-Math.max(i,0),h=Math.min(s,r)-"
     "Math.max(n,0);return{draw:u>0&&c>0,interactive:d>0&&h>0&&d*h/l>=.5}",
     "The whole verdict. draw: the AABB must overlap the viewport EXPANDED "
     "BY EXACTLY 64 CSS px on every side, with strictly positive extent on "
     "both axes -- no area fraction. interactive: strictly positive overlap "
     "with the STRICT (unexpanded) viewport AND overlapArea/aabbArea >= 0.5 "
     "-- the 'at least half' rule, on AABB areas, only ever gates "
     "`interactive`, never `draw`."),
    ("verdictWiring", 1980406,
     "s.visible=o.draw,o.draw?i(a,s):n(a),o.interactive&&PA.push(a)",
     "One verdict drives THREE things, in this order per slot: the WebGL "
     "glass mesh's own `visible` flag, then the label DOM write (draw -> "
     "transform writer, otherwise -> guarded hide), then the interactive "
     "set."),
    ("hideGuarded", 1965055,
     'function Po(e){let t=L7[e];t&&"hidden"!==t.style.visibility&&'
     '(t.style.visibility="hidden")}',
     "The hide path is GUARDED: visibility:hidden is written only when the "
     "inline style is not already hidden. Nothing else is touched -- the "
     "transform is left stale."),
    ("drawWriterScaleGuard", 1980681,
     "if(t.updateWorldMatrix(!0,!1),Pt.copy(t.matrixWorld),"
     "Pr.setFromMatrixScale(Pt),0===Pr.x||0===Pr.y||0===Pr.z)"
     '{a.style.visibility="hidden";return}',
     "The draw path first refreshes the mesh world matrix, then rejects a "
     "degenerate matrix (any scale component exactly 0) by hiding."),
    ("drawWriterVisible", 1980825,
     'Pt.scale(Pr.set(1/Pr.x,1/Pr.y,1/Pr.z)),a.style.visibility="visible"',
     "The scale is stripped from the matrix (the element is sized in px "
     "instead), and visibility:visible is assigned UNCONDITIONALLY on every "
     "drawn frame -- the visible side has no guard, unlike Po."),
    ("sizeCache", 1980893,
     "let s=Pe[e];(!s||s.width!==r||s.height!==i)&&(a.style.width="
     "`${r}px`,a.style.height=`${i}px`,s&&(s.width=r,s.height=i))",
     "Width/height writes ARE cached: written only when the plane size "
     "changed. The transform write below it is unconditional per drawn "
     "frame."),
    ("labelInitialStyle", 1966319,
     'style:{transformStyle:"preserve-3d",willChange:"transform",'
     'visibility:"hidden",backfaceVisibility:"hidden"}',
     "Every label element is BORN hidden, and carries "
     "backface-visibility:hidden INLINE. There is no JS backface test "
     "anywhere in the culling: backface hiding is pure CSS, applied by the "
     "compositor, and does not affect the DOM visibility state."),
    ("containerTransform", 1979071,
     ",Pa=n),Pi.style.transform=`translateZ(${n}px)${i="
     "e.matrixWorldInverse.elements,",
     "The CSS3D CONTAINER transform is built from the RENDER camera's "
     "inverse world matrix -- the camera WITH the dolly -- exactly as the "
     "motion round found. Coverage alone uses the dolly-free Py."),
    ("perspectiveWrite", 1978980,
     "let n=.5*r/Math.tan(eF.MathUtils.degToRad(.5*e.fov));Pa!==n&&"
     "(Pn.style.perspective=`${n}px`",
     "The container perspective write is cached on Pa -- written only when "
     "the derived px value changes."),
    ("frameReadsLiveSize", 1977922,
     "p7(()=>{let r=i.width,s=i.height,l=L6(r,s,t),u=l.sphereRadius,"
     "d=l.planeWidth,h=l.planeHeight,m=b0.get(),A=d*(1+m),y=h*(1+m),"
     "E=f*A,S=p*y,_=bK.get(),T=bX.get();",
     "The per-frame sync reads the LIVE viewport size, layout frame, gap, "
     "and scroll values every frame -- after a resize, coverage uses the "
     "new viewport on the very next frame, with no debounce."),
    ("cameraLensOnResize", 1982506,
     "t.fov=eF.MathUtils.radToDeg(2*Math.atan(o.height/2/r.perspective)),"
     "t.aspect=o.width/Math.max(o.height,1),t.near=.1,t.far=1e4,"
     "t.updateProjectionMatrix()",
     "The render camera lens is rebuilt in the same frame a size or "
     "perspective change is seen (guarded by a cached width/height/"
     "perspective triple), and Py copies it via lensSync."),
    ("resizeDebounce", 1972991,
     "let r=window.setTimeout(e,150);return()=>window.clearTimeout(r)",
     "Only the POOL (cols x rows) recalculation is debounced -- 150 ms, "
     "except the very first run. Coverage and the camera are not."),
    ("poolResize", 1965555,
     "if(L7.length>e){L7.length=e,Pe.length=e;return}for(;L7.length<e;)"
     "L7.push(null),Pe.push({width:0,height:0})",
     "Pool shrink truncates the element and cache registries; growth "
     "appends nulls and React mounts fresh labels, which are born hidden "
     "(labelInitialStyle)."),
    ("nullMeshSkip", 1979740,
     "PA.length=0;for(let a=0;a<e.length;a+=1){let s=e[a];if(!s)continue;",
     "A slot with no mesh (not yet mounted / just unmounted) is SKIPPED "
     "entirely: its label element, if any, keeps its previous state."),
    ("interactivePublish", 1980576,
     "(PA,Pv)&&(Pv=PA.slice(),b4.set(Pv))",
     "The interactive set is published to the MotionValue b4 only when it "
     "changed (array-equality guard)."),
    ("b4Decl", 1304449,
     "b4=mY([])",
     "b4's declaration. See measured.b4NeverRead: the bundle contains "
     "exactly these two references -- the interactive flag drives nothing "
     "user-visible in the shipped Target."),
    ("componentOrderPB", 1983734,
     "t=(0,eP.jsx)(PB,{grid:u})",
     "PB -- the camera component -- is the FIRST child."),
    ("componentOrderPP", 1983802,
     "r=(0,eP.jsx)(PP,{settings:s,grid:u})",
     "PP -- the grid, container transform, mesh poses and the coverage "
     "loop -- is the SECOND child. Camera updates run first (see "
     "inferredRows for the one inference this relies on)."),
    ("gapIntro", 1988916,
     'e=bG(b0,E,{type:"spring",...b$})',
     "The gap MotionValue b0 starts at 3 and springs to the grid gapRatio "
     "on load: an intro fly-in. Coverage reads the live b0 each frame, so "
     "during the intro the same rule culls against the spread-out grid."),
]


def verify(bundle_text: str) -> list:
    rows = []
    for key, offset, text, why in SITES:
        found = bundle_text.find(text)
        rows.append({
            "id": key,
            "recordedByteOffset": offset,
            "foundAtByteOffset": found,
            "occurrences": bundle_text.count(text),
            "matches": found == offset,
            "verbatim": text,
            "whatItSettles": why,
            "confidence": "SOURCE_READ",
        })
    return rows


def measured(bundle_text: str) -> dict:
    py = [m.start() for m in re.finditer(r"\bPy\b", bundle_text)]
    b4 = [m.start() for m in re.finditer(r"\bb4\b", bundle_text)]
    return {
        "coverageCameraRendersNothing": {
            "claim": "Py appears exactly 10 times in the bundle: 1 "
                     "declaration, 5 lens-sync writes, 3 pose writes, and "
                     "ONE .project(Py) call. It is never handed to a "
                     "renderer, never used for the CSS3D container, never "
                     "used for hit testing.",
            "occurrences": len(py),
            "byteOffsets": py,
            "confidence": "MEASURED",
        },
        "b4NeverRead": {
            "claim": "b4 appears exactly twice: its declaration and the one "
                     ".set() in the coverage loop. The interactive verdict "
                     "is computed and published but read by nothing.",
            "occurrences": len(b4),
            "byteOffsets": b4,
            "confidence": "MEASURED",
        },
    }


QUESTIONS = {
    "whichCameraProjectsCoverage": {
        "answer": "A dedicated module-level PerspectiveCamera (minified "
                  "`Py`), used for nothing else.",
        "sites": ["coverageCameraDecl", "lensSync", "cornerProject"],
        "alsoSee": "measured.coverageCameraRendersNothing",
        "confidence": "SOURCE_READ",
    },
    "isDollyFreeCamera": {
        "answer": "YES. Py sits at (d,h,f); the render camera sits at "
                  "(d,h,f+p) where p is the velocity dolly. Same line.",
        "sites": ["coverageCameraPose", "dollyFormula"],
        "confidence": "SOURCE_READ",
    },
    "carriesPointerOrbit": {
        "answer": "YES. (d,h,f) is the +-0.05 rad pointer orbit at radius "
                  "`perspective`; Py and the render camera share it exactly.",
        "sites": ["orbitAngles", "coverageCameraPose"],
        "confidence": "SOURCE_READ",
    },
    "cornerProjection": {
        "answer": "The four card corners: unit quad (+-0.5, +-0.5, 0) "
                  "through the mesh matrixWorld (scale = plane size), then "
                  ".project(Py). Order BL, BR, TR, TL.",
        "sites": ["quadCorners", "meshPose", "cornerProject"],
        "confidence": "SOURCE_READ",
    },
    "ndcZCondition": {
        "answer": "Per corner: skipped when z < -1 or z > 1 (strict). A "
                  "skipped corner contributes nothing to the AABB. Zero "
                  "surviving corners rejects the card.",
        "sites": ["cornerProject", "zeroCornerReject"],
        "confidence": "SOURCE_READ",
    },
    "aabb": {
        "answer": "Min/max over the SURVIVING corners' pixel positions, "
                  "x=(0.5nx+0.5)w, y=(-0.5ny+0.5)h. Not clipped to the "
                  "viewport.",
        "sites": ["ndcToPx"],
        "confidence": "SOURCE_READ",
    },
    "minimumArea": {
        "answer": "AABB area must be strictly > 1 px^2; area <= 1 rejects.",
        "sites": ["minArea"],
        "confidence": "SOURCE_READ",
    },
    "viewportMargin": {
        "answer": "The draw test intersects the AABB with the viewport "
                  "expanded 64 px on every side and requires strictly "
                  "positive extent on both axes.",
        "sites": ["margin64"],
        "confidence": "SOURCE_READ",
    },
    "marginExactly64px": {
        "answer": "YES -- the literals are t+64, -64, r+64, -64. CSS px, "
                  "both axes, draw test only. The strict test uses 0/t/r "
                  "with no margin.",
        "sites": ["margin64"],
        "confidence": "SOURCE_READ",
    },
    "strictViewportFlag": {
        "answer": "`interactive`: strictly positive overlap with the "
                  "UNexpanded viewport on both axes AND the half-area rule. "
                  "Published to b4; nothing reads it in the shipped build.",
        "sites": ["margin64", "interactivePublish", "b4Decl"],
        "confidence": "SOURCE_READ",
    },
    "halfAreaRuleExactFormula": {
        "answer": "(min(maxX,w)-max(minX,0)) * (min(maxY,h)-max(minY,0)) "
                  "/ ((maxX-minX)*(maxY-minY)) >= 0.5 -- AABB areas, not "
                  "true quad areas; >= not >; applies ONLY to interactive, "
                  "never to draw.",
        "sites": ["margin64"],
        "confidence": "SOURCE_READ",
    },
    "visibilityVsTransformWriteOrder": {
        "answer": "Per slot, in one pass: verdict -> mesh.visible -> (if "
                  "draw) refresh world matrix, degenerate-scale guard, "
                  "visibility:visible ASSIGNED unconditionally, cached "
                  "width/height, transform written -- visibility BEFORE "
                  "transform; (if not draw) guarded visibility:hidden and "
                  "NOTHING else. The container transform was already "
                  "written earlier in the same frame callback, before the "
                  "mesh poses and the coverage loop.",
        "sites": ["verdictWiring", "drawWriterScaleGuard",
                  "drawWriterVisible", "sizeCache", "hideGuarded",
                  "containerTransform"],
        "confidence": "SOURCE_READ",
    },
    "hiddenLabelStopsTransformUpdates": {
        "answer": "YES. The hide path writes at most visibility:hidden "
                  "(guarded). A culled label keeps its STALE transform -- "
                  "the motion round measured exactly this on the Target's "
                  "recorded card matrices.",
        "sites": ["hideGuarded"],
        "confidence": "SOURCE_READ",
    },
    "resizeRecalc": {
        "answer": "Coverage viewport + camera lens: the very next frame, no "
                  "debounce. The POOL (cols x rows) alone is debounced 150 "
                  "ms (immediate on first run). Label width/height styles "
                  "follow on each label's next drawn frame via the size "
                  "cache.",
        "sites": ["frameReadsLiveSize", "cameraLensOnResize",
                  "resizeDebounce", "sizeCache"],
        "confidence": "SOURCE_READ",
    },
    "activeInactiveSlots": {
        "answer": "A slot with no mesh is skipped -- its label keeps its "
                  "previous state (born hidden). Pool shrink truncates the "
                  "registries and React unmounts the extra labels; growth "
                  "mounts fresh hidden labels. Label content is bound to "
                  "the SLOT INDEX at mount and never rebinds.",
        "sites": ["nullMeshSkip", "poolResize", "labelInitialStyle"],
        "confidence": "SOURCE_READ",
    },
}

OBSERVED_NOT_APPLIED = {
    "glassMeshCulledBySameVerdict": {
        "observation": "The Target sets the GLASS MESH's `visible` flag "
                       "from the same draw verdict (verdictWiring). V0's "
                       "brief authorises Label visibility/culling only; "
                       "changing what the WebGL renderer draws is neither "
                       "Label nor Visibility-of-labels, so this is "
                       "recorded and NOT implemented. Flagged for a "
                       "product decision in a later round.",
        "sites": ["verdictWiring"],
    },
    "noJsBackfaceTest": {
        "observation": "The Target has NO JS backface test; backface "
                       "hiding is inline CSS on the label element, so a "
                       "back-facing drawn card is visibility:visible in "
                       "the DOM and hidden only at paint. Our page's JS "
                       "dot-product test is therefore NOT source-exact "
                       "DOM behaviour; V0 moves the source-exact path to "
                       "the Target's semantics (inline backface-visibility"
                       ":hidden, no JS test in the visibility decision) "
                       "and keeps the backface dot product as a QA "
                       "diagnostic only.",
        "sites": ["labelInitialStyle"],
    },
    "visibleAssignedUnconditionally": {
        "observation": "The Target assigns visibility:visible on EVERY "
                       "drawn frame (no guard), while hiding is guarded. "
                       "Our implementation guards both directions -- the "
                       "brief's own DOM-write-hygiene requirement -- which "
                       "is observationally identical (the assigned value "
                       "never differs from the current one) and is "
                       "declared here rather than silently.",
        "sites": ["drawWriterVisible", "hideGuarded"],
    },
    "transformRewrittenEveryDrawnFrame": {
        "observation": "The Target rewrites style.transform on every drawn "
                       "frame even at rest. Our CSS3DRenderer keeps a "
                       "per-object style cache and skips the DOM write "
                       "when the string is unchanged -- fewer writes at "
                       "rest, identical rendered output. Declared here.",
        "sites": ["sizeCache"],
    },
}

INFERRED = [
    {
        "id": "cameraBeforeCoverageSameFrame",
        "claim": "PB's frame callback (which poses Py and the render "
                 "camera) runs BEFORE PP's (which runs the coverage loop) "
                 "in the same rAF frame.",
        "anchoredPart": "PB is the first child and PP the second "
                        "(componentOrderPB/PP), so PB's effects subscribe "
                        "first.",
        "inferredPart": "@react-three/fiber runs same-priority useFrame "
                        "subscribers in subscription order. Library "
                        "semantics, not re-derived from this bundle.",
        "confidence": "INFERRED",
    },
]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v

    bundle = Path(args["bundle"])
    text = bundle.read_text(encoding="utf-8", errors="replace")
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    sites = verify(text)
    bad = [r["id"] for r in sites if not r["matches"] or r["occurrences"] != 1]

    live = None
    if args.get("live-bundle"):
        lp = Path(args["live-bundle"])
        live = {
            "url": "https://infinite-liquid-glass.shader.se/_next/static/"
                   "immutable/chunks/03lo820gl57km.js",
            "sha256": hashlib.sha256(lp.read_bytes()).hexdigest(),
            "bytes": lp.stat().st_size,
        }
        live["matchesCapturedBundle"] = live["sha256"] == sha

    doc = {
        "what": "the Target's CSS3D label coverage culling -- camera, "
                "formulas, thresholds and DOM write order -- read out of "
                "its application bundle byte by byte",
        "notFitted": "no rule below was derived from a visible count. "
                     "Every formula is a byte-anchored read; the gate "
                     "replays these formulas against the Target's own "
                     "recorded frames as a CHECK, not as a source.",
        "bundle": {
            "path": str(bundle.relative_to(REPO)) if bundle.is_absolute()
                    else str(bundle),
            "sha256": sha,
            "bytes": bundle.stat().st_size,
        },
        "liveBundle": live,
        "questions": QUESTIONS,
        "sites": sites,
        "measured": measured(text),
        "observedNotApplied": OBSERVED_NOT_APPLIED,
        "inferredRows": INFERRED,
        "verification": {
            "allSitesFoundAtRecordedOffsets": not bad,
            "sitesRequiredUniqueAndMatching": True,
            "failures": bad,
        },
    }

    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    if bad:
        print(f"FAIL: {len(bad)} site(s) did not match: {bad}")
        return 1
    if live and not live["matchesCapturedBundle"]:
        print("FAIL: the live bundle differs from the captured one")
        return 1
    print(f"OK: {len(sites)} sites verified at their recorded offsets; "
          f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
