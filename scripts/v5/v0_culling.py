#!/usr/bin/env python3
"""The Target's label coverage rule, replayed offline.

This module is the PYTHON TWIN of `src/ui/SourceExactLabelCulling.ts`, which
is itself a byte-anchored read of the Target's bundle
(`qa-v5/culling/target-culling-source.json`). Every three.js operation the
page-side verdict passes through -- quaternion from unit vectors, matrix
compose, column scale, lookAt, the perspective projection, `Vector3.project`'s
per-step w divide -- is ported here with the SAME operation order, so a
verdict replayed from a recorded truth agrees with the page's own verdict to
float precision, and any residual disagreement is flagged as
boundary-sensitive rather than absorbed by a tolerance.

Nothing here was fitted. The layout comes from the frozen source contract via
`source_layout.py`; the orbit gain and dolly law from the frozen motion
contract; the coverage formulas from the culling forensics.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SL = _load("source_layout", "source_layout.py")

MOTION = json.loads((REPO / "config/target-motion-source-v1.json").read_text())
POINTER_GAIN = MOTION["camera"]["orbit"]["pointerGain"]
MAX_ZOOM_Z_FACTOR = MOTION["camera"]["velocityDolly"]["maxZoomZFactor"]

# The Target's unit quad, in its order: BL, BR, TR, TL.
CORNERS = ((-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.5, 0.5, 0.0), (-0.5, 0.5, 0.0))
MARGIN_PX = 64.0


# --------------------------------------------------------------------------
# three.js math, ported operation for operation
# --------------------------------------------------------------------------

def quat_from_z_to(nx: float, ny: float, nz: float) -> tuple:
    """Quaternion.setFromUnitVectors((0,0,1), n), three's exact branch order."""
    r = nz + 1.0  # dot((0,0,1), n) + 1
    if r < sys.float_info.epsilon:
        # n is exactly opposite +z. from=(0,0,1): |x|>|z| is false.
        x, y, z, w = 0.0, -nz, ny, 0.0
    else:
        # cross((0,0,1), n) = (-ny, nx, 0)
        x, y, z, w = -ny, nx, 0.0, r
    n = math.sqrt(x * x + y * y + z * z + w * w)
    return (x / n, y / n, z / n, w / n)


def compose(px: float, py: float, pz: float, q: tuple,
            sx: float, sy: float, sz: float) -> list:
    """Matrix4.compose(position, quaternion, scale). Column-major, like three."""
    x, y, z, w = q
    x2, y2, z2 = x + x, y + y, z + z
    xx, xy, xz = x * x2, x * y2, x * z2
    yy, yz, zz = y * y2, y * z2, z * z2
    wx, wy, wz = w * x2, w * y2, w * z2
    return [
        (1 - (yy + zz)) * sx, (xy + wz) * sx, (xz - wy) * sx, 0.0,
        (xy - wz) * sy, (1 - (xx + zz)) * sy, (yz + wx) * sy, 0.0,
        (xz + wy) * sz, (yz - wx) * sz, (1 - (xx + yy)) * sz, 0.0,
        px, py, pz, 1.0,
    ]


def scale_columns(m: list, sx: float, sy: float, sz: float) -> list:
    """Matrix4.scale(v): multiply the basis columns in place, like three."""
    out = m[:]
    for i in range(4):
        out[i] *= sx
        out[4 + i] *= sy
        out[8 + i] *= sz
    return out


def apply_matrix4(v: tuple, m: list) -> tuple:
    """Vector3.applyMatrix4: full 4x4 with the w divide, exactly as three."""
    x, y, z = v
    w = 1.0 / (m[3] * x + m[7] * y + m[11] * z + m[15])
    return ((m[0] * x + m[4] * y + m[8] * z + m[12]) * w,
            (m[1] * x + m[5] * y + m[9] * z + m[13]) * w,
            (m[2] * x + m[6] * y + m[10] * z + m[14]) * w)


def look_at_view_inverse(eye: tuple) -> list:
    """The camera's matrixWorldInverse for position `eye`, lookAt origin, up +y.

    Built as [R^T | -R^T eye] from the lookAt basis. three routes this through
    quaternion + compose + invert; the two agree to float rounding, which the
    boundary flagging downstream absorbs.
    """
    ex, ey, ez = eye
    zl = math.sqrt(ex * ex + ey * ey + ez * ez)
    if zl == 0:
        zx, zy, zz = 0.0, 0.0, 1.0
    else:
        zx, zy, zz = ex / zl, ey / zl, ez / zl
    # x = normalize(cross(up, z)), up = (0,1,0)
    xx_, xy_, xz_ = zz, 0.0, -zx
    xl = math.sqrt(xx_ * xx_ + xz_ * xz_)
    if xl == 0:
        xx_, xy_, xz_, xl = 1.0, 0.0, 0.0, 1.0
    xx_, xy_, xz_ = xx_ / xl, xy_ / xl, xz_ / xl
    # y = cross(z, x)
    yx_ = zy * xz_ - zz * xy_
    yy_ = zz * xx_ - zx * xz_
    yz_ = zx * xy_ - zy * xx_
    tx = -(xx_ * ex + xy_ * ey + xz_ * ez)
    ty = -(yx_ * ex + yy_ * ey + yz_ * ez)
    tz = -(zx * ex + zy * ey + zz * ez)
    return [xx_, yx_, zx, 0.0,
            xy_, yy_, zy, 0.0,
            xz_, yz_, zz, 0.0,
            tx, ty, tz, 1.0]


def perspective_projection(fov_deg: float, aspect: float, near: float, far: float) -> list:
    """PerspectiveCamera.updateProjectionMatrix, WebGL coordinate system."""
    top = near * math.tan(0.5 * fov_deg * math.pi / 180.0)
    height = 2.0 * top
    width = aspect * height
    left = -0.5 * width
    right, bottom = left + width, top - height
    x = 2.0 * near / (right - left)
    y = 2.0 * near / (top - bottom)
    a = (right + left) / (right - left)
    b = (top + bottom) / (top - bottom)
    c = -(far + near) / (far - near)
    d = -2.0 * far * near / (far - near)
    return [x, 0.0, 0.0, 0.0,
            0.0, y, 0.0, 0.0,
            a, b, c, -1.0,
            0.0, 0.0, d, 0.0]


# --------------------------------------------------------------------------
# the coverage camera
# --------------------------------------------------------------------------

def orbit(pointer_x: float, pointer_y: float, perspective: float) -> tuple:
    """The pointer orbit, the page's own operation order (SourceExactMotion)."""
    yaw = -(POINTER_GAIN * pointer_x)
    pitch = POINTER_GAIN * pointer_y
    return (math.sin(yaw) * math.cos(pitch) * perspective,
            math.sin(pitch) * perspective,
            math.cos(yaw) * math.cos(pitch) * perspective)


def coverage_camera(pointer_x: float, pointer_y: float, frame: dict) -> dict:
    """The dolly-free coverage camera for a layout frame and pointer state."""
    w, h = frame["viewport"]
    persp = frame["perspective"]
    fov = math.degrees(2.0 * math.atan(h / 2.0 / persp))
    aspect = w / max(h, 1)
    eye = orbit(pointer_x, pointer_y, persp)
    return {
        "eye": eye,
        "view": look_at_view_inverse(eye),
        "proj": perspective_projection(fov, aspect, 0.1, 1e4),
    }


def camera_from_recorded_position(pos: tuple, frame: dict) -> dict:
    """The coverage camera of a lane that publishes no truth (the Target).

    The recorded CSS3D camera matrix yields the RENDER camera's position
    (orbit + dolly on world z). The orbit angles are solved exactly --
    x = P sin(yaw) cos(pitch), y = P sin(pitch), z = P cos(yaw) cos(pitch)+d
    -- and the coverage camera is the orbit WITHOUT d.
    """
    x, y, z = pos
    p = frame["perspective"]
    pitch = math.asin(max(-1.0, min(1.0, y / p)))
    cp = math.cos(pitch)
    sy = x / (p * cp) if cp != 0 else 0.0
    yaw = math.asin(max(-1.0, min(1.0, sy)))
    dolly = z - p * math.cos(yaw) * cp
    eye = (math.sin(yaw) * cp * p, math.sin(pitch) * p, math.cos(yaw) * cp * p)
    w, h = frame["viewport"]
    fov = math.degrees(2.0 * math.atan(h / 2.0 / p))
    return {
        "eye": eye, "dollyRemoved": dolly,
        "yaw": yaw, "pitch": pitch,
        "view": look_at_view_inverse(eye),
        "proj": perspective_projection(fov, w / max(h, 1), 0.1, 1e4),
    }


# --------------------------------------------------------------------------
# the verdict
# --------------------------------------------------------------------------

def slot_matrix(slot_index: int, scroll_x: float, scroll_y: float, frame: dict) -> list:
    """matrixWorld * scale(planeW, planeH, 1) for one slot -- the page's own
    composition: T * R (group, scale 1) post-multiplied by the plane scale."""
    p = SL.place(slot_index, scroll_x, scroll_y, frame)
    q = quat_from_z_to(p["nx"], p["ny"], p["nz"])
    m = compose(p["x"], p["y"], p["z"], q, 1.0, 1.0, 1.0)
    return scale_columns(m, frame["planeWidth"], frame["planeHeight"], 1.0)


def verdict(m: list, cam: dict, width: float, height: float) -> dict:
    """One slot's coverage verdict -- the Target's formulas, term for term.

    Also reports `boundaryMarginPx`: the smallest |distance| between any
    deciding quantity and its threshold, so a reader can tell a robust verdict
    from one that a float ulp could flip.
    """
    quad = [None, None, None, None]
    min_x = min_y = math.inf
    max_x = max_y = -math.inf
    survived = 0
    z_margin = math.inf
    for k, c in enumerate(CORNERS):
        wpt = apply_matrix4(c, m)
        vx, vy, vz = apply_matrix4(wpt, cam["view"])
        nx, ny, nz = apply_matrix4((vx, vy, vz), cam["proj"])
        z_margin = min(z_margin, abs(nz + 1.0), abs(1.0 - nz))
        if nz < -1.0 or nz > 1.0:
            continue
        px = (0.5 * nx + 0.5) * width
        py = (-(0.5 * ny) + 0.5) * height
        quad[k] = (px, py)
        min_x, max_x = min(min_x, px), max(max_x, px)
        min_y, max_y = min(min_y, py), max(max_y, py)
        survived += 1

    if survived == 0:
        return {"draw": False, "interactive": False,
                "rejectionReason": "zeroCornersInNdcZ", "quad": quad,
                "aabb": None, "area": 0.0, "overlap": 0.0,
                "boundaryMarginPx": z_margin}

    area = (max_x - min_x) * (max_y - min_y)
    if area <= 1.0:
        return {"draw": False, "interactive": False,
                "rejectionReason": "aabbAreaAtMostOnePx", "quad": quad,
                "aabb": [min_x, min_y, max_x, max_y], "area": area,
                "overlap": 0.0, "boundaryMarginPx": abs(area - 1.0)}

    mu = min(max_x, width + 64.0) - max(min_x, -64.0)
    mc = min(max_y, height + 64.0) - max(min_y, -64.0)
    su = min(max_x, width) - max(min_x, 0.0)
    sc = min(max_y, height) - max(min_y, 0.0)
    draw = mu > 0 and mc > 0
    overlap = su * sc if (su > 0 and sc > 0) else 0.0
    interactive = su > 0 and sc > 0 and (su * sc) / area >= 0.5
    boundary = min(abs(mu), abs(mc), abs(area - 1.0))
    return {"draw": draw, "interactive": interactive,
            "rejectionReason": None if draw else "outsideMarginViewport",
            "quad": quad, "aabb": [min_x, min_y, max_x, max_y],
            "area": area, "overlap": overlap,
            "boundaryMarginPx": boundary}


def frame_verdicts(scroll_x: float, scroll_y: float, cam: dict, frame: dict) -> dict:
    """draw/interactive per ACTIVE slot code. Codes are slotIndex + 1."""
    w, h = frame["viewport"]
    out = {}
    for n in range(frame["activeSlotCount"]):
        m = slot_matrix(n, scroll_x, scroll_y, frame)
        out[n + 1] = verdict(m, cam, w, h)
    return out


# --------------------------------------------------------------------------
# absolute scroll recovery for the truthless lane
# --------------------------------------------------------------------------

def recover_scroll(pool: list, labels: list, frame: dict) -> tuple | None:
    """Absolute (scrollX, scrollY) from the visible labels' world positions.

    Inverts the slot placement per live card -- arc coordinates from the world
    position, minus the slot's own column/row/brick terms, wrapped -- and takes
    the median over the live set. Exact up to float noise in the recorded
    matrix; the caller flags boundary-sensitive cells rather than trusting the
    last decimal.
    """
    R = frame["sphereRadius"]
    xs, ys = [], []
    for i, rec in enumerate(labels):
        if rec is None or rec[0] is None:
            continue
        code = pool[i]
        n = code - 1
        if n >= frame["activeSlotCount"]:
            continue
        x, y, z = rec[0], rec[1], rec[2]
        tx = math.atan2(x / R, (z + R) / R)
        ty = math.asin(max(-1.0, min(1.0, y / R)))
        x_arc, y_arc = tx * R, ty * R
        cols = frame["cols"]
        pool_row, pool_col = n // cols, n % cols
        brick = (pool_row % 2) * frame["cellW"] * 0.5
        sx = SL.wrap(x_arc - (pool_col - (cols - 1) / 2) * frame["cellW"] - brick,
                     frame["periodX"])
        sy = SL.wrap(-y_arc - (pool_row - (frame["rows"] - 1) / 2) * frame["cellH"],
                     frame["periodY"])
        xs.append(sx)
        ys.append(sy)
    if not xs:
        return None
    xs.sort()
    ys.sort()
    return (xs[len(xs) // 2], ys[len(ys) // 2])


def parse_camera_position(camera_style: str) -> tuple | None:
    """Camera world position out of a recorded CSS3D camera transform.

    Both spellings -- the Target's `translateZ(p) matrix3d(...)` and three's
    `perspective(p) scale(1) translateZ(p) matrix3d(...)` -- carry
    `matrix3d(camera.matrixWorldInverse)` with the y row negated. Undo the
    negation; position = -R^T t.
    """
    if not camera_style or "matrix3d(" not in camera_style:
        return None
    k = camera_style.index("matrix3d(")
    m = [float(v) for v in camera_style[k + 9:camera_style.index(")", k)].split(",")]
    if len(m) != 16:
        return None
    r = [[m[0], m[4], m[8]], [-m[1], -m[5], -m[9]], [m[2], m[6], m[10]]]
    t = [m[12], -m[13], m[14]]
    return (-(r[0][0] * t[0] + r[1][0] * t[1] + r[2][0] * t[2]),
            -(r[0][1] * t[0] + r[1][1] * t[1] + r[2][1] * t[2]),
            -(r[0][2] * t[0] + r[1][2] * t[1] + r[2][2] * t[2]))
