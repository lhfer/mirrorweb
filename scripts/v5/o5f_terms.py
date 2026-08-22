#!/usr/bin/env python3
"""O5F §九 -- CPU replay of the Target source formula, term by term.

Extends the O5R displacement replay (o5r_replay.py, validated on the
Target's own render to 1.4-1.6 px) through the REST of the source chain:
world reflection vector, environment rotations, equirect UV, the raw HDR
texel, Schlick Fresnel, the env mix factor and the white rim -- each exactly
as the bundle-anchored contract writes it, evaluated per pixel through the
LIVE card matrix and camera from the same truth blob the O5R instrument
used.

Every convention that could silently be wrong -- the equirect atan2 axes,
the HDR flipY, the rotation signs, the anisotropic normal metric -- is not
trusted: the term scorer VALIDATES each term against the engine's own
measurement view at the passing viewport before any failing-viewport number
is read. A term whose replay cannot reproduce the engine where the result
is known good is INSTRUMENT_UNREADABLE, never a divergence.

Fixed conventions (from three 0.185 sources, quoted so a reviewer can check
them against the build):
  equirectUV(d):  u = atan2(d.z, d.x) / 2pi + 0.5
                  v = asin(clamp(d.y, -1, 1)) / pi + 0.5
  HDRLoader:      texData.flipY = true  (examples/jsm/loaders/HDRLoader.js)
  env wrap:       ClampToEdgeWrapping (texture default; only mapping is set)
  env filter:     LinearFilter (bilinear)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


R = _load("o5f_terms_replay", "o5r_replay.py")
H = _load("o5f_terms_hdr", "o5r-hdr-audit.py")

# The Target's tent table, byte 1959836 -- the same construction
# spectralSamplesV5 bakes into the shader.


def spectral_samples(count: int):
    n = max(3, round(count))
    rows, sums = [], [0.0, 0.0, 0.0]
    for i in range(n):
        t = i / (n - 1)
        w = [max(0.0, 1 - abs(t - c) / 0.5) for c in (0.0, 0.5, 1.0)]
        for k in range(3):
            sums[k] += w[k]
        rows.append({"offset": t - 0.5, "weight": w})
    return [{"offset": r["offset"],
             "weight": [r["weight"][k] / sums[k] for k in range(3)]}
            for r in rows]


# ---------------------------------------------------------------- encodings

def srgb_encode(linear):
    linear = np.clip(np.asarray(linear, float), 0.0, 1.0)
    lo = linear * 12.92
    hi = 1.055 * np.power(np.maximum(linear, 1e-12), 1 / 2.4) - 0.055
    return np.where(linear <= 0.0031308, lo, hi)


def srgb_decode(encoded):
    encoded = np.asarray(encoded, float)
    lo = encoded / 12.92
    hi = np.power(np.maximum((encoded + 0.055) / 1.055, 0.0), 2.4)
    return np.where(encoded <= 0.04045, lo, hi)


def reinhard(c):
    c = np.asarray(c, float)
    return c / (1.0 + c)


# ---------------------------------------------------------------- HDR

def load_hdr(path: Path):
    """The asset as float RGB rows in FILE ORDER (row 0 = first scanline)."""
    raw = Path(path).read_bytes()
    w, h, off = H.read_header(raw)
    rgbe = H.read_rle(raw, off, w, h)
    rgb = H.to_float(rgbe)
    # three's RGBE decode clamps each channel at 65504 before packing the
    # half float; the sampled texture cannot exceed it (the unclamp audit's
    # structural fact), so the replay applies the same bound.
    return np.minimum(rgb, 65504.0)


def sample_equirect(rgb, u, v, flip_y=True):
    """Bilinear sample with clamp-to-edge, honouring the upload flipY."""
    h, w = rgb.shape[:2]
    u = np.clip(np.asarray(u, float), 0.0, 1.0)
    v = np.clip(np.asarray(v, float), 0.0, 1.0)
    if flip_y:
        v = 1.0 - v
    # GL_LINEAR with normalised coordinates: texel centres at (i + 0.5) / n.
    x = u * w - 0.5
    y = v * h - 0.5
    x0 = np.clip(np.floor(x).astype(int), 0, w - 1)
    y0 = np.clip(np.floor(y).astype(int), 0, h - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fx = np.clip(x - x0, 0.0, 1.0)[..., None]
    fy = np.clip(y - y0, 0.0, 1.0)[..., None]
    top = rgb[y0, x0] * (1 - fx) + rgb[y0, x1] * fx
    bot = rgb[y1, x0] * (1 - fx) + rgb[y1, x1] * fx
    return top * (1 - fy) + bot * fy


# ---------------------------------------------------------------- the chain

class TermReplay:
    """Every §九 term at unit-plane local (lx, ly), one card."""

    def __init__(self, truth, card, hdr_rgb, env_constants):
        self.card = R.CardReplay(truth, card)
        self.hdr = hdr_rgb
        self.E = env_constants   # fresnelF0, envIntensity, envMaxMix,
        #                          envRotation, envRotationX, rimIntensity
        src = truth["source"]
        self.dispersion = float(src["dispersion"])
        self.eta_floor = float(src["etaFloor"])

    # -- shared geometry ----------------------------------------------------
    def _NV(self, lx, ly):
        c = self.card
        lx = np.asarray(lx, float)
        ly = np.asarray(ly, float)
        px, py = lx * c.plane_w, ly * c.plane_h
        nx, ny, nz = R.analytic_normal(px, py, c.S, c.sphere_radius,
                                       c.face_direction)
        cam_local = c.model_world_inv @ np.append(c.cam_world, 1.0)
        pz = R.dome_z(px, py, c.sphere_radius, c.S["sphereRadicandFloor"])
        tx, ty, tz = cam_local[0] - lx, cam_local[1] - ly, cam_local[2] - pz
        vx, vy, vz = tx * c.plane_w, ty * c.plane_h, tz
        vn = np.sqrt(vx * vx + vy * vy + vz * vz)
        return (nx, ny, nz), (vx / vn, vy / vn, vz / vn), (px, py)

    def _to_world(self, dx, dy, dz):
        """toWorld: modelWorld * vec4(d.xy / planeSize, d.z, 0), normalised."""
        c = self.card
        vec = np.stack([np.asarray(dx, float) / c.plane_w,
                        np.asarray(dy, float) / c.plane_h,
                        np.asarray(dz, float),
                        np.zeros_like(np.asarray(dx, float))], axis=-1)
        world = vec @ c.model_world.T
        n = np.linalg.norm(world[..., :3], axis=-1, keepdims=True)
        return world[..., :3] / np.maximum(n, 1e-12)

    # -- terms --------------------------------------------------------------
    def analytic_normal_view(self, lx, ly):
        (nx, ny, nz), _, _ = self._NV(lx, ly)
        return np.stack([nx, ny, nz], axis=-1) * 0.5 + 0.5

    def reflection_vector(self, lx, ly):
        """World reflected view direction, BEFORE the env rotations."""
        N, V, _ = self._NV(lx, ly)
        Nw = self._to_world(*N)
        Vw = self._to_world(*V)
        neg = -Vw
        dot = np.sum(neg * Nw, axis=-1, keepdims=True)
        r = neg - Nw * (dot * 2.0)
        n = np.linalg.norm(r, axis=-1, keepdims=True)
        return r / np.maximum(n, 1e-12)

    def rotated_reflection(self, lx, ly):
        r = self.reflection_vector(lx, ly)
        cy, sy = np.cos(self.E["envRotation"]), np.sin(self.E["envRotation"])
        rot_y = np.stack([r[..., 0] * cy - r[..., 2] * sy,
                          r[..., 1],
                          r[..., 0] * sy + r[..., 2] * cy], axis=-1)
        cx, sx = np.cos(self.E["envRotationX"]), np.sin(self.E["envRotationX"])
        return np.stack([rot_y[..., 0],
                         rot_y[..., 1] * cx - rot_y[..., 2] * sx,
                         rot_y[..., 1] * sx + rot_y[..., 2] * cx], axis=-1)

    def equirect_uv(self, lx, ly):
        d = self.rotated_reflection(lx, ly)
        u = np.arctan2(d[..., 2], d[..., 0]) / (2 * np.pi) + 0.5
        v = np.arcsin(np.clip(d[..., 1], -1.0, 1.0)) / np.pi + 0.5
        return np.stack([u, v], axis=-1)

    def raw_env_sample(self, lx, ly):
        uv = self.equirect_uv(lx, ly)
        return sample_equirect(self.hdr, uv[..., 0], uv[..., 1])

    def fresnel(self, lx, ly):
        N, V, _ = self._NV(lx, ly)
        d = np.clip(N[0] * V[0] + N[1] * V[1] + N[2] * V[2], 0.0, 1.0)
        f0 = self.E["fresnelF0"]
        return f0 + (1 - f0) * np.power(np.clip(1 - d, 0.0, 1.0), 5)

    def env_mix(self, lx, ly):
        f = self.fresnel(lx, ly)
        return np.minimum(np.clip(f * self.E["envIntensity"], 0.0, 1.0),
                          self.E["envMaxMix"]) * self.E["envMixScale"]

    def rim(self, lx, ly):
        c = self.card
        _, _, (px, py) = self._NV(lx, ly)
        s = R.sdf(px, py, c.S["halfX"], c.S["halfY"], c.S["cornerRadius"])
        t = np.clip((s - (-c.S["rimWidth"])) / c.S["rimWidth"], 0.0, 1.0)
        smooth = t * t * (3 - 2 * t)
        return smooth * self.E["rimIntensity"] * self.E["rimScale"]

    def sdf_at(self, lx, ly):
        c = self.card
        px = np.asarray(lx, float) * c.plane_w
        py = np.asarray(ly, float) * c.plane_h
        return R.sdf(px, py, c.S["halfX"], c.S["halfY"], c.S["cornerRadius"])


# ---------------------------------------------------------------- bins

def bin_masks(term_replay, lx, ly):
    """The §九 card-local bins: SDF-distance bands split upper/lower.

    Label-excluded by construction: the type block lives in the lower
    interior of the card, so the interior bin is split and the bands are
    where the residual instruments read. The exact text boxes are proven
    disjoint from the edge bands in roi-isolation.json.
    """
    c = term_replay.card
    s = term_replay.sdf_at(lx, ly)
    bevel_w = c.S["bevelWidth"]
    inside = s < 0
    # Local +y is UP (three's plane convention), so upper = ly > 0. The type
    # block sits in the card's lower half.
    bins = {
        "interior-upper": inside & (s < -bevel_w) & (np.asarray(ly) > 0),
        "interior-lower": inside & (s < -bevel_w) & (np.asarray(ly) <= 0),
        "bevel-upper": inside & (s >= -bevel_w) & (np.asarray(ly) > 0),
        "bevel-lower": inside & (s >= -bevel_w) & (np.asarray(ly) <= 0),
        "bevel-left": inside & (s >= -bevel_w) & (np.asarray(lx) < -0.25),
        "bevel-right": inside & (s >= -bevel_w) & (np.asarray(lx) > 0.25),
    }
    return bins
