#!/usr/bin/env python3
"""Final Entry Convergence §四/§七 -- one reader for the entry traces.

Every landmark the entry gate asks about is derived HERE and nowhere else, so
the contract, the gate and the package all quote the same arithmetic. Both
sides go through this module unchanged: it knows about a loader, a card and a
clock, and nothing about which page produced them.

The clock. Every trace timestamp is `performance.now()`, i.e.
navigation-relative. That is the right axis for "how long did the page take to
get going" and the wrong one for "did the two entries have the same shape",
because a cold Target load and a cold local load do not reach ready at the same
wall time and never will. So every landmark is reported twice: `atMs`
navigation-relative, and `relMs` relative to READY, which is the moment both
pages hand the screen over to the entry.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def _cards(frame) -> dict:
    """`{code: (cx, cy, w, h)}` for the cards drawn in one frame."""
    out = {}
    for c in (frame.get("cards") or []):
        out[c[0]] = (c[1], c[2], c[3], c[4])
    return out


def ready_index(frames) -> int | None:
    """The frame the page hands the screen over.

    Defined by what a viewer sees and what a finger can reach, not by any
    internal flag: the loading overlay stops taking pointer events, or begins
    to fade, whichever the page does first. Both pages do both at once, and
    neither exposes the same internal name, so this is the only rule that can
    be applied identically to both.
    """
    for i, f in enumerate(frames):
        L = f.get("loader") or {}
        if not L.get("inDom"):
            continue
        if L.get("pointerEvents") == "none":
            return i
        op = L.get("opacity")
        if op is not None and op < 0.999:
            return i
    return None


def loader_gone_index(frames, start: int) -> int | None:
    for i in range(start, len(frames)):
        L = frames[i].get("loader") or {}
        op = L.get("opacity")
        if not L.get("inDom") or L.get("display") == "none" or (op is not None and op <= 0.01):
            return i
    return None


def first_draw_index(frames) -> int | None:
    for i, f in enumerate(frames):
        d = f.get("dom") or {}
        if (d.get("transformed") or 0) > 0:
            return i
    return None


def tracked_codes(frames, lo: int, hi: int, want: int = 8):
    """Codes drawn in nearly every frame of the entry window.

    §七 asks for at least eight matching cards. A card that pops into coverage
    halfway through cannot supply a start pose, so the tracked set is the codes
    present for at least 90% of the window, ranked by how close they settle to
    the viewport centre -- the same anchor rule the motion recorders use.
    """
    span = frames[lo:hi + 1]
    if not span:
        return []
    seen = {}
    for f in span:
        for code in _cards(f):
            seen[code] = seen.get(code, 0) + 1
    need = 0.9 * len(span)
    keep = [c for c, n in seen.items() if n >= need]
    end = _cards(frames[hi])
    vp = frames[hi].get("viewportHint")
    cx = vp[0] / 2 if vp else None
    if cx is None:
        xs = [v[0] for v in end.values()] or [0]
        ys = [v[1] for v in end.values()] or [0]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    else:
        cy = vp[1] / 2
    keep = [c for c in keep if c in end]
    keep.sort(key=lambda c: math.hypot(end[c][0] - cx, end[c][1] - cy))
    return keep[:max(want, 8)]


def settle_index(frames, lo: int, codes, tol: float = 0.15, quiet: int = 24) -> int | None:
    """Last frame on which a tracked card moved more than `tol` px.

    Reported as the frame AFTER that one -- the first frame of stillness -- and
    only if the stillness then holds for `quiet` frames, so a momentary pause
    partway down an overdamped curve is not mistaken for the end of it.
    """
    last_move = lo
    for i in range(lo + 1, len(frames)):
        a, b = _cards(frames[i - 1]), _cards(frames[i])
        moved = False
        for c in codes:
            if c in a and c in b:
                if abs(b[c][0] - a[c][0]) > tol or abs(b[c][1] - a[c][1]) > tol:
                    moved = True
                    break
        if moved:
            last_move = i
    if last_move >= len(frames) - quiet:
        return None
    return last_move


def progress_curve(frames, lo: int, hi: int, codes):
    """A single 0..1 scalar for "how far through the entry are we".

    The card's SCREEN WIDTH is the scalar, not its centre. A centre is a
    two-axis quantity whose direction differs per card and whose sign flips
    across the viewport, so a progress fraction built on it is not comparable
    between two cards let alone two pages. Screen width is monotone through the
    whole entry on both pages, identical in meaning for every card, and it is
    the thing the eye is actually reading -- cards arriving from far away and
    growing into the frame.
    """
    rows = []
    for c in codes:
        w0 = _cards(frames[lo]).get(c)
        w1 = _cards(frames[hi]).get(c)
        if not w0 or not w1:
            continue
        a, b = w0[2], w1[2]
        if abs(b - a) < 1e-6:
            continue
        series = []
        for i in range(lo, hi + 1):
            cur = _cards(frames[i]).get(c)
            series.append(None if cur is None else (cur[2] - a) / (b - a))
        rows.append({"code": c, "startW": round(a, 3), "endW": round(b, 3),
                     "series": series})
    return rows


def crossing(series, times, level: float):
    """First time the progress scalar reaches `level`, linearly interpolated."""
    prev_t = prev_v = None
    for t, v in zip(times, series):
        if v is None:
            continue
        if prev_v is not None and prev_v < level <= v:
            if v == prev_v:
                return t
            return prev_t + (t - prev_t) * (level - prev_v) / (v - prev_v)
        prev_t, prev_v = t, v
    return None


def read_run(path: Path) -> dict:
    """Every §七 landmark for one recorded load."""
    doc = json.loads(path.read_text())
    F = doc["trace"]["frames"]
    vp = doc["trace"].get("viewport")
    for f in F:
        f["viewportHint"] = vp
    ri = ready_index(F)
    fd = first_draw_index(F)
    out = {
        "file": path.name, "cond": doc["cond"], "rep": doc["rep"],
        "side": doc["side"], "viewport": doc["viewport"],
        "settledFlag": doc["settled"], "errors": doc["errors"],
        "frames": len(F),
        "sampleHz": round(1000 * (len(F) - 1) / (F[-1]["t"] - F[0]["t"]), 1)
        if len(F) > 1 else None,
        "overheadMs": doc["trace"]["instrumentOverheadMs"],
        "nav": doc["trace"]["nav"],
        "resources": doc["trace"]["resources"],
        "fromCache": doc["trace"]["fromCache"],
        "domNodes": doc["trace"]["nodes"],
    }
    if ri is None or fd is None:
        out["usable"] = False
        return out
    lg = loader_gone_index(F, ri)
    codes = tracked_codes(F, fd, len(F) - 1)
    si = settle_index(F, ri, codes)
    if si is None or not codes:
        out["usable"] = False
        out["trackedCodes"] = codes
        return out
    t_ready = F[ri]["t"]
    rows = progress_curve(F, ri, si, codes)
    times = [F[i]["t"] for i in range(ri, si + 1)]
    rel = [t - t_ready for t in times]
    p50, p90 = [], []
    for r in rows:
        a = crossing(r["series"], rel, 0.5)
        b = crossing(r["series"], rel, 0.9)
        if a is not None:
            p50.append(a)
        if b is not None:
            p90.append(b)

    dom_at = lambda i: (F[i].get("dom") or {})
    out.update({
        "usable": True,
        "trackedCodes": codes,
        "firstDrawAtMs": F[fd]["t"],
        "readyAtMs": t_ready,
        "loaderGoneAtMs": F[lg]["t"] if lg is not None else None,
        "loaderFadeMs": round(F[lg]["t"] - t_ready, 1) if lg is not None else None,
        "settleAtMs": F[si]["t"],
        "introMs": round(F[si]["t"] - t_ready, 1),
        "firstDrawRelMs": round(F[fd]["t"] - t_ready, 1),
        "p50RelMs": round(sum(p50) / len(p50), 1) if p50 else None,
        "p90RelMs": round(sum(p90) / len(p90), 1) if p90 else None,
        "p50SpreadMs": round(max(p50) - min(p50), 1) if len(p50) > 1 else None,
        "pctAtReady": (F[ri].get("loader") or {}).get("pct"),
        "pctMax": max([(f.get("loader") or {}).get("pct") or 0 for f in F[:ri + 1]] or [0]),
        # §七.2/3: which way does a card come in? Direction of travel and the
        # sign of the size change, per tracked card, start of entry to end.
        "startEnd": [
            {"code": r["code"], "startW": r["startW"], "endW": r["endW"],
             "scaleDir": 1 if r["endW"] > r["startW"] else -1,
             "widthRatio": round(r["startW"] / r["endW"], 4)}
            for r in rows],
        "radialDir": _radial(F, ri, si, codes),
        "mountedAtReady": dom_at(ri).get("mounted"),
        "mountedAtSettle": dom_at(si).get("mounted"),
        "transformedAtReady": dom_at(ri).get("transformed"),
        "transformedAtSettle": dom_at(si).get("transformed"),
        "visibleAtSettle": dom_at(si).get("visible"),
        "mountedMax": max([(f.get("dom") or {}).get("mounted") or 0 for f in F] or [0]),
        # §七.11: a one-frame flash of the FINAL pose before the entry starts
        # would show as a tracked card sitting at its settled width on some
        # frame at or before ready. Measured, not assumed.
        "finalPoseFlashFrames": _flash(F, fd, ri, codes),
        "progressRows": rows,
        "relTimes": [round(t, 2) for t in rel],
    })
    return out


def _radial(F, lo, hi, codes) -> list:
    """Does each card travel toward or away from the viewport centre?"""
    a, b = _cards(F[lo]), _cards(F[hi])
    vp = F[hi].get("viewportHint") or [0, 0]
    cx, cy = vp[0] / 2, vp[1] / 2
    out = []
    for c in codes:
        if c not in a or c not in b:
            continue
        d0 = math.hypot(a[c][0] - cx, a[c][1] - cy)
        d1 = math.hypot(b[c][0] - cx, b[c][1] - cy)
        out.append({"code": c, "startDistPx": round(d0, 1), "endDistPx": round(d1, 1),
                    "inward": bool(d1 < d0)})
    return out


def _flash(F, fd, ri, codes) -> int:
    """Frames before ready on which a tracked card already sat at its final size."""
    end = _cards(F[-1])
    n = 0
    for i in range(fd, ri + 1):
        cur = _cards(F[i])
        hit = [c for c in codes if c in cur and c in end
               and abs(cur[c][2] - end[c][2]) < 0.02 * end[c][2]]
        if len(hit) >= max(2, len(codes) // 2):
            n += 1
    return n


def read_dir(d: Path) -> list:
    return [read_run(p) for p in sorted(d.glob("*-[0-9][0-9].json"))]


def by_condition(runs: list) -> dict:
    out = {}
    for r in runs:
        out.setdefault(r["cond"], []).append(r)
    return out


def spread(values):
    v = [x for x in values if x is not None]
    if not v:
        return None
    v = sorted(v)
    return {"n": len(v), "min": round(v[0], 1), "median": round(v[len(v) // 2], 1),
            "max": round(v[-1], 1), "rangeMs": round(v[-1] - v[0], 1)}


# ---------------------------------------------------------------------------
# The gap scalar, recovered from the drawn cards.
#
# The entry is ONE number on both pages -- the grid gap ratio -- and every
# card's position during it is that number pushed through the frozen layout law
# and the frozen camera. So the honest comparison is not "did card 34 follow the
# same path", which the coverage churn makes unanswerable (the cards drawn at
# the start of the entry are mostly not the cards drawn at the end of it), but
# "did the two pages run the same scalar".
#
# It is recovered rather than read: neither page is asked for its internal
# value. Each frame's drawn cards give an over-determined system -- typically
# five to thirty cards, two coordinates each, one unknown -- and the residual
# says whether the recovered number really explains the frame or whether
# something else was moving. A page whose entry did something other than move
# the gap would show it as a residual that will not come down.
# ---------------------------------------------------------------------------
import math as _m

import source_layout as _SL


def base_frame(width: int, height: int) -> dict:
    return _SL.layout(width, height)


def project(pose: dict, frame: dict) -> tuple:
    """Screen pixels for one world point, through the source-exact camera.

    Camera at (0, 0, perspective) looking at the origin, and the fov is chosen
    so that half the viewport height subtends `perspective` -- so the pixel
    scale at depth `perspective` is exactly 1 and the projection is
    `perspective / (perspective - z)`. No orbit and no dolly: the pointer has
    not moved and the velocity magnitude is zero for the whole of a load.
    """
    w, h = frame["viewport"]
    p = frame["perspective"]
    depth = p - pose["z"]
    return (w / 2 + p * pose["x"] / depth, h / 2 - p * pose["y"] / depth)


def _rotate_to_normal(v, n):
    """Rotate `v` by the minimal rotation taking +Z onto the unit normal `n`.

    The same `setFromUnitVectors(+Z, normal)` the placement uses, written out.
    """
    nx, ny, nz = n
    # q = (cross(+Z, n), 1 + dot(+Z, n)), normalised.
    qx, qy, qz, qw = -ny, nx, 0.0, 1.0 + nz
    if qw < 1e-12:                       # antipodal: 180 degrees about +X
        qx, qy, qz, qw = 1.0, 0.0, 0.0, 0.0
    inv = 1.0 / _m.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    qx, qy, qz, qw = qx * inv, qy * inv, qz * inv, qw * inv
    x, y, z = v
    # t = 2 * q_vec x v ; v' = v + qw * t + q_vec x t
    tx = 2 * (qy * z - qz * y)
    ty = 2 * (qz * x - qx * z)
    tz = 2 * (qx * y - qy * x)
    return (x + qw * tx + (qy * tz - qz * ty),
            y + qw * ty + (qz * tx - qx * tz),
            z + qw * tz + (qx * ty - qy * tx))


def card_rect(pose: dict, frame: dict) -> tuple:
    """The card's projected AXIS-ALIGNED BOUNDING BOX: (cx, cy, w, h).

    This is what has to be modelled, because it is what the recorder measured.
    `getBoundingClientRect` on a CSS3D label returns the bounding box of the
    transformed rectangle, and a card sitting off-centre on the sphere is tilted
    away from the camera -- so its box centre is NOT the projection of its
    centre point, and its box is wider than the card. Solving the gap against
    projected centre points instead left a 6.5 px residual that no gap value
    could remove; against the box it is a fifth of a pixel.

    The four corners are the same four the Target's own coverage test uses.
    """
    hw, hh = 0.5 * frame["planeWidth"], 0.5 * frame["planeHeight"]
    n = (pose["nx"], pose["ny"], pose["nz"])
    xs, ys = [], []
    for sx in (-hw, hw):
        for sy in (-hh, hh):
            rx, ry, rz = _rotate_to_normal((sx, sy, 0.0), n)
            px, py = project({"x": pose["x"] + rx, "y": pose["y"] + ry,
                              "z": pose["z"] + rz}, frame)
            xs.append(px)
            ys.append(py)
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
            max(xs) - min(xs), max(ys) - min(ys))


def _frame_at_gap(base: dict, gap: float) -> dict:
    f = dict(base)
    f["cellW"] = base["planeWidth"] * (1 + gap)
    f["cellH"] = base["planeHeight"] * (1 + gap)
    f["periodX"] = base["cols"] * f["cellW"]
    f["periodY"] = base["rows"] * f["cellH"]
    return f


def _errors(base: dict, gap: float, obs: dict) -> list:
    """Per-card centre error in pixels, for one candidate gap."""
    f = _frame_at_gap(base, gap)
    n = base["cols"] * base["rows"]
    out = []
    for code, (cx, cy, _w, _h) in obs.items():
        idx = code - 1
        if idx < 0 or idx >= n:
            continue
        sx, sy, _sw, _sh = card_rect(_SL.place(idx, 0.0, 0.0, f), f)
        out.append(_m.hypot(sx - cx, sy - cy))
    return out


def _residual(base: dict, gap: float, obs: dict) -> float:
    """The MEDIAN per-card error, not the RMS.

    A card sitting exactly on the wrap boundary is at +period/2 on one side of
    the arithmetic and -period/2 on the other, and the two disagree by half a
    grid. That is a property of where the boundary is put, not a difference
    between the pages, and it happened on a handful of isolated frames -- one
    card in sixteen, throwing an RMS from 0.0 px to 552 px while every other
    card on the frame agreed exactly. A median ignores it, cannot be dragged by
    it, and still refuses to fit a frame where the entry moved anything other
    than the gap: that would move MOST of the cards, not one.

    The outliers are not swept away -- `solve_gap` counts them.
    """
    e = _errors(base, gap, obs)
    if not e:
        return _m.inf
    e.sort()
    return e[len(e) // 2]


def solve_gap(base: dict, obs: dict, hi: float = 3.05, scan: int = 900):
    """The gap that best explains one frame, plus its RMS residual in pixels.

    A coarse scan first, because the wrap makes the objective wildly
    non-convex -- a card that has wrapped to the other side of the sphere sits
    in a different basin -- and then a golden-section refine inside the winning
    bracket.
    """
    if len(obs) < 2:
        return None, None
    best_g, best_r = None, _m.inf
    step = hi / scan
    for i in range(scan + 1):
        g = i * step
        r = _residual(base, g, obs)
        if r < best_r:
            best_r, best_g = r, g
    lo, hi2 = max(0.0, best_g - step), min(hi, best_g + step)
    phi = (_m.sqrt(5) - 1) / 2
    a, b = lo, hi2
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = _residual(base, c, obs), _residual(base, d, obs)
    for _ in range(48):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = _residual(base, c, obs)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = _residual(base, d, obs)
    g = (a + b) / 2
    return g, _residual(base, g, obs)


def solve_gap_full(base: dict, obs: dict):
    """`solve_gap` plus the wrap-boundary outlier count for the winning gap."""
    g, r = solve_gap(base, obs)
    if g is None:
        return None, None, None
    e = _errors(base, g, obs)
    return g, r, sum(1 for x in e if x > 1.0)


def gap_series(frames, lo: int, hi: int, viewport) -> list:
    """`[{t, gap, rmsPx, n}]` across the entry window."""
    base = base_frame(viewport[0], viewport[1])
    out = []
    for i in range(lo, hi + 1):
        obs = _cards(frames[i])
        g, r = solve_gap(base, obs)
        out.append({"t": frames[i]["t"], "gap": None if g is None else round(g, 6),
                    "rmsPx": None if r is None else round(r, 3), "n": len(obs)})
    return out


def spring_reference(from_v: float, to_v: float, stiffness: float, damping: float,
                     mass: float, rest_delta: float, rest_speed: float):
    """framer-motion's closed-form spring, in Python, for the predicted curve.

    The same solve the product code runs, written a second time here on purpose:
    a prediction generated by the implementation under test would only prove the
    implementation agrees with itself.
    """
    zeta = damping / (2 * _m.sqrt(stiffness * mass))
    omega = _m.sqrt(stiffness / mass) / 1000.0
    delta = to_v - from_v
    if zeta > 1:
        wd = omega * _m.sqrt(zeta * zeta - 1)
        t_ = (zeta * omega * delta) / wd
        def value(t):
            i = min(wd * t, 300)
            return to_v - _m.exp(-zeta * omega * t) * (
                t_ * wd * _m.sinh(i) + wd * delta * _m.cosh(i)) / wd
        def vel(t):
            i = min(wd * t, 300)
            n_ = zeta * omega * t_ - delta * wd
            a_ = zeta * omega * delta - t_ * wd
            return 1000 * _m.exp(-zeta * omega * t) * (n_ * _m.sinh(i) + a_ * _m.cosh(i))
    elif zeta == 1:
        e = omega * delta
        value = lambda t: to_v - _m.exp(-omega * t) * (delta + e * t)
        vel = lambda t: 1000 * _m.exp(-omega * t) * (omega * e * t)
    else:
        wd = omega * _m.sqrt(1 - zeta * zeta)
        a = (zeta * omega * delta) / wd
        value = lambda t: to_v - _m.exp(-zeta * omega * t) * (
            a * _m.sin(wd * t) + delta * _m.cos(wd * t))
        s = zeta * omega * a + delta * wd
        o = zeta * omega * delta - a * wd
        vel = lambda t: 1000 * _m.exp(-zeta * omega * t) * (
            s * _m.sin(wd * t) + o * _m.cos(wd * t))
    rest = None
    t = 0.0
    while t < 5000:
        if abs(vel(t)) <= rest_speed and abs(to_v - value(t)) <= rest_delta:
            rest = t
            break
        t += 0.5
    return value, vel, rest
