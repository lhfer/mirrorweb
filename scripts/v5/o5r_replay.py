#!/usr/bin/env python3
"""CPU replay of the Target's card geometry and refraction.

§六 and §八 both need a Target-side prediction, and the Target has no QA views
to read one out of. This module replays the SOURCE FORMULA -- the same chain
transcribed in `src/materials/TargetOpticalBodyV5.ts` from
`qa-v5/optics-o5/target-optical-body-contract.json` -- through the LIVE layout
frame, card matrix and camera reported by `getCardBodyTruth()`.

Two things make that legitimate rather than circular:

  1. The replay is VALIDATED against the GPU. The candidate's
     `refraction-displacement` program computes the same quantity on the same
     geometry, so a disagreement between this port and that program is a
     defect in the port, and is reported as one rather than absorbed.

  2. The matrices are the ENGINE'S, not a second model of the layout. Our
     frozen frame reproduces the Target's L6 exactly at every O5 viewport
     (qa-v5/optics-o5/o5-architecture.json, layoutReproducesL6), which is what
     makes one set of matrices valid for both lanes. Re-deriving the layout
     here would introduce a second model whose disagreements with the engine
     would be indistinguishable from optical differences.

Everything is a literal port. Where the shader clamps, this clamps; where the
shader uses a floor, this uses the same floor; the anisotropic planeSize
multiply and its matching divide are both here because dropping either one
silently skews refraction on any card that is not square.
"""
from __future__ import annotations

import numpy as np

# three serialises a Matrix4 in COLUMN-major order.
def mat4(arr) -> np.ndarray:
    return np.asarray(arr, dtype=np.float64).reshape(4, 4).T


def sphere_z(px, py, radius, radicand_floor=1.0):
    """sqrt(max(R^2 - p.p, floor)) -- the shader's sphereZ, floor included."""
    return np.sqrt(np.maximum(radius * radius - (px * px + py * py),
                              radicand_floor))


def dome_z(px, py, radius, radicand_floor=1.0):
    return sphere_z(px, py, radius, radicand_floor) - radius


def sdf(px, py, half_x, half_y, corner_radius):
    """The Target's rounded-rect SDF, in card pixels."""
    r = min(corner_radius, half_x, half_y)
    qx = np.abs(px) - half_x + r
    qy = np.abs(py) - half_y + r
    outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
    return outside + np.minimum(np.maximum(qx, qy), 0.0) - r


def bevel(s, bevel_width, bevel_power, thickness):
    """Power-law bevel thickness profile."""
    t = np.clip(1.0 + s / max(bevel_width, 0.001), 0.0, 1.0)
    k = max(bevel_power, 1.0)
    return np.power(np.maximum(1.0 - np.power(t, k), 0.0), 1.0 / k) * thickness


def thickness_at(px, py, half_x, half_y, S):
    return bevel(sdf(px, py, half_x, half_y, S["cornerRadius"]),
                 S["bevelWidth"], S["bevelPower"], S["thickness"])


def analytic_normal(px, py, S, sphere_radius, face_direction=1.0):
    """The Target's analytic normal, in the anisotropic card-pixel metric.

    Numeric central-difference gradient of the thickness field, magnitude
    clamp (NOT a normalise -- the clamp preserves direction), plus the card's
    own tilt on the layout sphere.
    """
    eps = max(S["bevelWidth"] * S["gradientEpsilonRatio"],
              S["gradientEpsilonFloorPx"])
    hx, hy = S["halfX"], S["halfY"]
    gx = (thickness_at(px + eps, py, hx, hy, S)
          - thickness_at(px - eps, py, hx, hy, S)) / (2 * eps)
    gy = (thickness_at(px, py + eps, hx, hy, S)
          - thickness_at(px, py - eps, hx, hy, S)) / (2 * eps)
    slope = np.sqrt(gx * gx + gy * gy)
    k = np.minimum(slope, S["bevelMaxSlope"]) / np.maximum(slope, 1e-4)
    cgx, cgy = gx * k, gy * k
    sz = sphere_z(px, py, sphere_radius, S["sphereRadicandFloor"])
    nx = px / sz - cgx
    ny = py / sz - cgy
    nz = np.ones_like(nx)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / n) * face_direction, (ny / n) * face_direction, (nz / n) * face_direction


def refract(ix, iy, iz, nx, ny, nz, eta):
    """GLSL refract(), including its total-internal-reflection zero."""
    dot_ni = nx * ix + ny * iy + nz * iz
    k = 1.0 - eta * eta * (1.0 - dot_ni * dot_ni)
    ok = k >= 0.0
    s = np.sqrt(np.maximum(k, 0.0))
    f = eta * dot_ni + s
    rx = np.where(ok, eta * ix - f * nx, 0.0)
    ry = np.where(ok, eta * iy - f * ny, 0.0)
    rz = np.where(ok, eta * iz - f * nz, 0.0)
    return rx, ry, rz, ok


class CardReplay:
    """One card's geometry, from the live truth blob."""

    def __init__(self, truth, card, face_direction=1.0):
        src = truth["source"]
        der = truth["derived"]
        frame = truth["frame"]
        self.plane_w = float(frame["planeWidth"])
        self.plane_h = float(frame["planeHeight"])
        self.sphere_radius = float(frame["sphereRadius"])
        self.S = {
            "cornerRadius": float(der["cornerRadius"]),
            "bevelWidth": float(der["bevelWidth"]),
            "thickness": float(der["thickness"]),
            "rimWidth": float(der["rimWidth"]),
            "bevelPower": float(src["bevelPower"]),
            "bevelMaxSlope": float(src["bevelMaxSlope"]),
            "gradientEpsilonRatio": float(src["gradientEpsilonRatio"]),
            "gradientEpsilonFloorPx": float(src["gradientEpsilonFloorPx"]),
            "sphereRadicandFloor": float(src["sphereRadicandFloor"]),
            "halfX": self.plane_w * 0.5,
            "halfY": self.plane_h * 0.5,
        }
        self.ior = float(src["ior"])
        self.refract_strength = float(src["refractStrength"])
        self.travel_z_floor = float(src["travelZFloor"])
        self.face_direction = face_direction
        self.model_world = mat4(card["matrixWorld"])
        self.model_world_inv = np.linalg.inv(self.model_world)
        self.cover_scale = np.asarray(card["coverScale"], float)
        self.cover_offset = np.asarray(card["coverOffset"], float)
        cam = truth["camera"]
        self.proj = mat4(cam["projectionMatrix"])
        self.view = mat4(cam["matrixWorldInverse"])
        self.cam_world = np.asarray(cam["position"], float)
        self.vw, self.vh = truth["viewportPx"]

    # ---------------------------------------------------------- geometry
    def local_to_screen(self, lx, ly):
        """Unit-plane local (x, y) in [-0.5, 0.5] -> screen pixels.

        The vertex stage's positionNode is vec3(positionLocal.xy,
        domeZ(positionLocal.xy * planeSize)), so the dome enters here and not
        as an afterthought.
        """
        lx = np.asarray(lx, float)
        ly = np.asarray(ly, float)
        pz = dome_z(lx * self.plane_w, ly * self.plane_h, self.sphere_radius,
                    self.S["sphereRadicandFloor"])
        pts = np.stack([lx, ly, pz, np.ones_like(lx)], axis=-1)
        world = pts @ self.model_world.T
        clip = world @ self.view.T @ self.proj.T
        w = np.where(np.abs(clip[..., 3]) < 1e-12, 1e-12, clip[..., 3])
        ndc = clip[..., :3] / w[..., None]
        return ((ndc[..., 0] + 1.0) * 0.5 * self.vw,
                (1.0 - ndc[..., 1]) * 0.5 * self.vh)

    def media_uv_to_local(self, u, v):
        """Media UV -> unit-plane local, inverting clamp-then-cover.

        Returns None for a coordinate the cover crop removed, which must be
        treated as "not measurable on this card" rather than clamped to an edge.
        """
        cu = (np.asarray(u, float) - self.cover_offset[0]) / self.cover_scale[0]
        cv = (np.asarray(v, float) - self.cover_offset[1]) / self.cover_scale[1]
        inside = (cu >= -1e-6) & (cu <= 1 + 1e-6) & (cv >= -1e-6) & (cv <= 1 + 1e-6)
        return cu - 0.5, cv - 0.5, inside

    # ---------------------------------------------------------- refraction
    def displacement(self, lx, ly):
        """Card-UV displacement at the BASE ior, the shader's expression.

        offset = r.xy * (thickness / max(|r.z|, floor)) * refractStrength
                 / planeSize
        """
        lx = np.asarray(lx, float)
        ly = np.asarray(ly, float)
        px, py = lx * self.plane_w, ly * self.plane_h
        nx, ny, nz = analytic_normal(px, py, self.S, self.sphere_radius,
                                     self.face_direction)
        cam_local = self.model_world_inv @ np.append(self.cam_world, 1.0)
        pz = dome_z(px, py, self.sphere_radius, self.S["sphereRadicandFloor"])
        tx = cam_local[0] - lx
        ty = cam_local[1] - ly
        tz = cam_local[2] - pz
        # The anisotropic multiply: directions are compared in the same metric
        # the normal is built in.
        vx, vy, vz = tx * self.plane_w, ty * self.plane_h, tz
        vn = np.sqrt(vx * vx + vy * vy + vz * vz)
        vx, vy, vz = vx / vn, vy / vn, vz / vn
        eta = 1.0 / max(self.ior, 1.0001)
        rx, ry, rz, ok = refract(-vx, -vy, -vz, nx, ny, nz, eta)
        travel = self.S["thickness"] / np.maximum(np.abs(rz), self.travel_z_floor)
        du = rx * travel * self.refract_strength / self.plane_w
        dv = ry * travel * self.refract_strength / self.plane_h
        return du, dv, ok

    def grid_local(self, n=96):
        """A regular unit-plane sample grid, for whole-card comparisons."""
        g = (np.arange(n) + 0.5) / n - 0.5
        return np.meshgrid(g, g, indexing="xy")


def source_ny_to_media_v(ny: float) -> float:
    """Source image y-from-top -> media UV v.

    three's UV origin is bottom-left and `MediaFit` says so in as many words
    ("three's UV origin is bottom-left; focusY is measured from the top"), so
    the flip is a documented convention rather than an inference. It is still
    tested against the render in o5r-refraction.py, both ways, because a
    convention that is only asserted is the kind of thing that is wrong once.
    """
    return 1.0 - ny


def predict_disc_images(replay, discs, source_wh, refracted=True, n=384):
    """Where each calibration disc's IMAGE lands on screen, and how big it is.

    Forward-mapped, not point-projected, and the difference matters. A disc
    inside the bevel is not merely displaced -- it is SMEARED, because the
    displacement field varies steeply across it. The centroid of that smeared
    image is not the refracted position of the disc's centre, so predicting the
    centre and measuring the centroid would compare two different quantities
    and report the difference as an optical error.

    So this does what the shader does: for every fragment of the card, compute
    which source texel it samples, and collect the fragments that land inside
    each disc. The centroid of that set is the same measurand a blob detector
    reads off the render, by construction.

    Fragments outside the rounded-rect silhouette are excluded -- the card does
    not draw them -- and the clamp before the cover transform is applied here
    exactly where the shader applies it.
    """
    lx, ly = replay.grid_local(n)
    inside_card = sdf(lx * replay.plane_w, ly * replay.plane_h,
                      replay.S["halfX"], replay.S["halfY"],
                      replay.S["cornerRadius"]) <= 0.0
    if refracted:
        du, dv, _ok = replay.displacement(lx, ly)
        u = np.clip(lx + 0.5 + du, 0.0, 1.0)
        v = np.clip(ly + 0.5 + dv, 0.0, 1.0)
    else:
        u = np.clip(lx + 0.5, 0.0, 1.0)
        v = np.clip(ly + 0.5, 0.0, 1.0)
    mu = u * replay.cover_scale[0] + replay.cover_offset[0]
    mv = v * replay.cover_scale[1] + replay.cover_offset[1]
    sw, sh = source_wh
    src_x = mu * sw
    src_y = (1.0 - mv) * sh          # media v is bottom-up; see MediaFit
    sx, sy = replay.local_to_screen(lx, ly)
    # Grid cells are not screen pixels. The sample grid is n x n over the card
    # regardless of how many pixels the card covers, so a raw fragment count is
    # in grid units and comparing it to a measured pixel count would be off by
    # the ratio between the two -- about 1.5 at 1440x900, which is exactly the
    # size of a systematic error that looks like a real one. Convert here.
    quad_x, quad_y = replay.local_to_screen(np.array([-.5, .5, .5, -.5]),
                                            np.array([.5, .5, -.5, -.5]))
    card_area_px = 0.5 * abs(
        sum(quad_x[i] * quad_y[(i + 1) % 4] - quad_x[(i + 1) % 4] * quad_y[i]
            for i in range(4)))
    px_per_cell = card_area_px / float(n * n)
    out = []
    for d in discs:
        sel = inside_card & (((src_x - d["sourceX"]) ** 2
                              + (src_y - d["sourceY"]) ** 2)
                             <= d["radiusPx"] ** 2)
        k = int(sel.sum())
        if k < 8:
            out.append({"id": d["id"], "fragments": k, "predictedAreaPx": 0.0,
                        "x": None, "y": None})
            continue
        xs, ys = sx[sel], sy[sel]
        out.append({"id": d["id"], "fragments": k,
                    "predictedAreaPx": k * px_per_cell,
                    "x": float(xs.mean()), "y": float(ys.mean()),
                    # The predicted FOOTPRINT, not just its centre. The
                    # measurement side needs it: a disc that refraction has
                    # stretched can be split into two connected components by
                    # the reflection band crossing it, and a component-based
                    # detector would then see two half-discs where there is
                    # one image. Measuring inside the predicted footprint
                    # keeps the two sides talking about the same object.
                    "bbox": [float(xs.min()), float(ys.min()),
                             float(xs.max()), float(ys.max())]})
    return out
