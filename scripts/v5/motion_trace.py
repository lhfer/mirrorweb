#!/usr/bin/env python3
"""
Recover a scroll trajectory from a card-matrix trace.

The Target's scroll lives in closed-over motion values that no page script can
reach. Every card's world position is an exact function of it, though, so the
trajectory can be recovered rather than guessed:

    normal   = (sin tx cos ty, sin ty, cos tx cos ty)
    position = normal * R - (0, 0, R)

so from a card's recorded position

    ty = asin(y / R),  tx = atan2(x / R, (z + R) / R)

and its arc coordinates are tx * R and ty * R. Every live card shares one
scrollX and one scrollY, so the per-frame change in arc is the per-frame change
in scroll -- modulo the wrap period, which is removed by taking the branch
nearest zero. The median over the live cards is the estimate; a card the page
has culled is excluded, because its matrix is stale rather than stationary.

Nothing here is fitted. R, cellW, cellH, cols and rows all come from the layout
source contract via source_layout.py.
"""
from __future__ import annotations

import importlib.util
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is None for an unregistered module.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SL = _load("source_layout", "source_layout.py")


def frame_for(width: float, height: float) -> dict:
    return SL.layout(width, height)


def arcs(sample_frame: dict, radius: float) -> dict[int, tuple[float, float]]:
    """Arc coordinates of every LIVE card in one recorded frame."""
    out: dict[int, tuple[float, float]] = {}
    for code, x, y, z in sample_frame["cards"]:
        if x is None:
            continue
        ny = max(-1.0, min(1.0, y / radius))
        theta_y = math.asin(ny)
        theta_x = math.atan2(x / radius, (z + radius) / radius)
        out[code] = (theta_x * radius, theta_y * radius)
    return out


def _nearest_branch(value: float, period: float) -> float:
    if period <= 0:
        return value
    return (value + period / 2.0) % period - period / 2.0


def _delta(a: dict, b: dict, period_x: float, period_y: float,
           min_cards: int = 4) -> tuple[float, float, int]:
    dxs, dys = [], []
    for code in a.keys() & b.keys():
        dxs.append(_nearest_branch(b[code][0] - a[code][0], period_x))
        dys.append(_nearest_branch(b[code][1] - a[code][1], period_y))
    if len(dxs) < min_cards:
        return 0.0, 0.0, len(dxs)
    return statistics.median(dxs), statistics.median(dys), len(dxs)


def trajectory(run: dict) -> dict:
    """Per-frame scroll for one recorded run, in world units."""
    width, height = run["viewport"]
    f = frame_for(width, height)
    radius, period_x, period_y = f["sphereRadius"], f["periodX"], f["periodY"]

    ts, xs, ys, live, spread = [], [], [], [], []
    scroll_x = scroll_y = 0.0
    frames = run["frames"]
    prev = arcs(frames[0], radius) if frames else {}
    prev_w, prev_h = (frames[0]["w"], frames[0]["h"]) if frames else (width, height)
    if frames:
        ts.append(frames[0]["t"]); xs.append(0.0); ys.append(0.0)
        live.append(len(prev)); spread.append(0.0)

    for sample in frames[1:]:
        # A resize re-tiles the grid: the arc period changes, and a delta taken
        # across that boundary is meaningless. Re-seed instead of integrating.
        if sample["w"] != prev_w or sample["h"] != prev_h:
            f = frame_for(sample["w"], sample["h"])
            radius, period_x, period_y = f["sphereRadius"], f["periodX"], f["periodY"]
            prev = arcs(sample, radius)
            prev_w, prev_h = sample["w"], sample["h"]
            ts.append(sample["t"]); xs.append(scroll_x); ys.append(scroll_y)
            live.append(len(prev)); spread.append(float("nan"))
            continue
        cur = arcs(sample, radius)
        d_x, d_y, n = _delta(prev, cur, period_x, period_y)
        # yArc = wrap(-rowTerm - scrollY), so a rise in scrollY LOWERS the arc.
        scroll_x += d_x
        scroll_y -= d_y
        shared = prev.keys() & cur.keys()
        if len(shared) >= 4:
            devs = [abs(_nearest_branch(cur[c][0] - prev[c][0], period_x) - d_x) for c in shared]
            spread.append(round(max(devs), 6))
        else:
            spread.append(float("nan"))
        ts.append(sample["t"]); xs.append(scroll_x); ys.append(scroll_y); live.append(n)
        prev = cur
        prev_w, prev_h = sample["w"], sample["h"]

    return {"t": ts, "scrollX": xs, "scrollY": ys, "liveCards": live,
            "perCardSpread": spread, "frame": f}


def pointer_track(run: dict) -> list[tuple[float, float, float]]:
    """The applied pointer, recovered from the CSS3D camera transform.

    The camera element carries `matrix3d(camera.matrixWorldInverse)` with the y
    row negated. Its rotation part is the transpose of the camera's own basis,
    so the camera's world direction -- and with it the orbit angles -- comes
    straight out of the string. This is the SMOOTHED pointer, after the spring.
    """
    out = []
    for sample in run["frames"]:
        s = sample.get("camera")
        if not s or "matrix3d(" not in s:
            continue
        k = s.index("matrix3d(")
        m = [float(v) for v in s[k + 9:s.index(")", k)].split(",")]
        if len(m) != 16:
            continue
        # matrixWorldInverse columns 0..2 (with the y row negated by CSS3D):
        # basis row 2 of the inverse is the camera's forward axis in world space.
        fwd_x, fwd_y, fwd_z = m[2], -m[6], m[10]
        pitch = math.asin(max(-1.0, min(1.0, fwd_y)))
        yaw = math.atan2(fwd_x, fwd_z)
        out.append((sample["t"], yaw, pitch))
    return out


def pointer_settle_63(run: dict) -> float | None:
    """Time constant of the pointer smoothing, measured as a step response.

    The sweep moves the mouse to a corner in a burst of moves that all land
    inside one frame, then holds for half a second. To the page that is a STEP,
    so the settle time is readable directly: from the end of the burst, how
    long until the camera yaw has covered 63.2% of its way to the plateau.

    Read from the yaw rather than from any internal value, so the same
    instrument works on the Target -- which exposes nothing -- and on us.
    """
    track = pointer_track(run)
    if len(track) < 12:
        return None
    moves = [e for e in run["events"] if e["type"] == "pointermove"]
    if len(moves) < 4:
        return None
    bursts, cur = [], [moves[0]]
    for e in moves[1:]:
        if e["t"] - cur[-1]["t"] > 200.0:
            bursts.append(cur); cur = [e]
        else:
            cur.append(e)
    bursts.append(cur)

    def yaw_at(t):
        return min(track, key=lambda p: abs(p[0] - t))[1]

    times = []
    for k, b in enumerate(bursts):
        t_end = b[-1]["t"]
        nxt = bursts[k + 1][0]["t"] if k + 1 < len(bursts) else track[-1][0]
        plateau_t = nxt - 40.0
        if plateau_t - t_end < 220.0:
            continue
        y0, y1 = yaw_at(b[0]["t"]), yaw_at(plateau_t)
        if abs(y1 - y0) < 0.012:      # a step too small to time
            continue
        want = y0 + 0.632 * (y1 - y0)
        for t, yaw, _ in track:
            if t < t_end:
                continue
            if t > plateau_t:
                break
            if (yaw - want) * (1 if y1 > y0 else -1) >= 0:
                times.append(t - t_end)
                break
    if not times:
        return None
    times.sort()
    return round(times[len(times) // 2], 3)


def input_events(run: dict, kinds: tuple[str, ...]) -> list[dict]:
    return [e for e in run["events"] if e["type"] in kinds]


def drag_span(run: dict) -> tuple[float, float, float, float] | None:
    """Finger displacement and duration while the primary button is down."""
    downs = [e for e in run["events"] if e["type"] in ("pointerdown", "touchstart")]
    ups = [e for e in run["events"] if e["type"] in ("pointerup", "touchend", "pointercancel",
                                                     "touchcancel")]
    if not downs:
        return None
    t0 = downs[0]["t"]
    t1 = ups[-1]["t"] if ups else run["frames"][-1]["t"]
    moves = [e for e in run["events"]
             if e["type"] in ("pointermove", "touchmove") and t0 <= e["t"] <= t1
             and e["clientX"] is not None]
    if len(moves) < 2:
        return None
    return (moves[-1]["clientX"] - downs[0]["clientX"],
            moves[-1]["clientY"] - downs[0]["clientY"],
            t0, t1)
