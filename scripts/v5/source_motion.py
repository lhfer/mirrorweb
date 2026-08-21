#!/usr/bin/env python3
"""
The Target's motion model, in Python, reading config/target-motion-source-v1.json.

Twin of src/interaction/SourceExactMotion.ts. Neither keeps its own copy of a
constant: two hand-maintained copies drift, and the drift is invisible until a
gate disagrees. This module exists so the model can be replayed OFFLINE against
a recorded Target trace -- the strongest available check, because it drives the
model with the Target's own input and compares against the Target's own output.

Everything here is a transcription of the bundled framer-motion code paths the
Target actually uses. Where the library has a branch the Target never reaches
(the underdamped spring, the duration-resolved spring) it is still written out,
because a model that silently handles only one branch is a model that will be
wrong the first time a constant changes.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "target-motion-source-v1.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())

SPRINGS = CONTRACT["springs"]
DRAG = CONTRACT["drag"]
GESTURE = CONTRACT["input"]["gesture"]
VELOCITY = CONTRACT["input"]["velocityEstimation"]
CAMERA = CONTRACT["camera"]


# --------------------------------------------------------------------------
# framer-motion's spring, transcribed
# --------------------------------------------------------------------------

class SpringSolver:
    """One closed-form solve, from `frm` to `to` with an initial velocity.

    Time is milliseconds, matching the library. `velocity0` is units per
    second, the unit the library reports and re-consumes on a retarget.
    """

    def __init__(self, frm: float, to: float, velocity0: float,
                 stiffness: float, damping: float, mass: float,
                 rest_speed: float, rest_delta: float):
        self.to = to
        self.rest_speed = rest_speed
        self.rest_delta = rest_delta
        # The library passes `-(velocity / 1000)` into the solver and reports
        # `1000 * i(t)` back out, so the internal sign is inverted on purpose.
        b = -(velocity0 / 1000.0)
        self.zeta = damping / (2.0 * math.sqrt(stiffness * mass))
        self.delta = to - frm
        self.omega = math.sqrt(stiffness / mass) / 1000.0
        z, S, w = self.zeta, self.delta, self.omega

        if z < 1.0:
            self.mode = "underdamped"
            self.wd = w * math.sqrt(1.0 - z * z)
            self.a = (b + z * w * S) / self.wd if self.wd else 0.0
            self.s = z * w * self.a + S * self.wd
            self.o = z * w * S - self.a * self.wd
        elif z == 1.0:
            self.mode = "critical"
            self.b = b
            self.e = b + w * S
        else:
            self.mode = "overdamped"
            self.wd = w * math.sqrt(z * z - 1.0)
            t_ = (b + z * w * S) / self.wd
            self.t_ = t_
            self.n_ = z * w * t_ - S * self.wd
            self.a_ = z * w * S - t_ * self.wd

    def value(self, t: float) -> float:
        z, S, w = self.zeta, self.delta, self.omega
        if self.mode == "underdamped":
            return self.to - math.exp(-z * w * t) * (self.a * math.sin(self.wd * t)
                                                     + S * math.cos(self.wd * t))
        if self.mode == "critical":
            return self.to - math.exp(-w * t) * (S + self.e * t)
        r = math.exp(-z * w * t)
        # The library caps the sinh/cosh argument at 300 and leaves the decaying
        # exponential uncapped; reproduced rather than tidied.
        i = min(self.wd * t, 300.0)
        return self.to - r * (self.t_ * self.wd * math.sinh(i) + self.wd * S * math.cosh(i)) / self.wd

    def velocity(self, t: float) -> float:
        """Units per second, the unit the library reports."""
        z, w = self.zeta, self.omega
        if self.mode == "underdamped":
            return 1000.0 * math.exp(-z * w * t) * (self.s * math.sin(self.wd * t)
                                                    + self.o * math.cos(self.wd * t))
        if self.mode == "critical":
            return 1000.0 * math.exp(-w * t) * (w * self.e * t - self.b)
        r = math.exp(-z * w * t)
        i = min(self.wd * t, 300.0)
        return 1000.0 * r * (self.n_ * math.sinh(i) + self.a_ * math.cosh(i))

    def done(self, t: float) -> bool:
        return (abs(self.velocity(t)) <= self.rest_speed
                and abs(self.to - self.value(t)) <= self.rest_delta)


@dataclass
class Spring:
    """A `useSpring`: an output value that chases a source, retargeting on change.

    On every source change the library starts a NEW solve from the current
    output value carrying the current generator velocity. Reproduced exactly --
    a single fixed solve, or a step integrator with its own damping, is a
    different animation.
    """
    stiffness: float
    damping: float
    mass: float
    rest_delta: float
    rest_speed: float
    value: float = 0.0
    target: float = 0.0
    _solver: SpringSolver | None = field(default=None, repr=False)
    _t0: float = 0.0
    _now: float = 0.0
    _velocity: float = 0.0

    @classmethod
    def from_contract(cls, name: str, value: float = 0.0) -> "Spring":
        s = SPRINGS[name]
        return cls(stiffness=s["stiffness"], damping=s["damping"], mass=s["mass"],
                   rest_delta=s["restDelta"], rest_speed=s["restSpeed"],
                   value=value, target=value)

    def set_target(self, target: float, now_ms: float) -> None:
        # Tick to NOW before retargeting. The library's animation ticks in the
        # frame's update step and the retarget is scheduled at postRender of
        # the same frame, so the new solve always starts from the value and
        # velocity the animation just produced -- never from a stale one. A
        # retarget from a stale value silently freezes the spring on every
        # frame that carries input, which is most of them during a drag.
        self.advance(now_ms)
        if target == self.target and self._solver is not None:
            return
        self.target = target
        if target == self.value:
            self._solver = None
            self._velocity = 0.0
            return
        self._solver = SpringSolver(self.value, target, self._velocity,
                                    self.stiffness, self.damping, self.mass,
                                    self.rest_speed, self.rest_delta)
        self._t0 = now_ms
        self._now = now_ms

    def advance(self, now_ms: float) -> float:
        self._now = now_ms
        if self._solver is None:
            return self.value
        t = now_ms - self._t0
        if self._solver.done(t):
            self.value = self._solver.to
            self._velocity = 0.0
            self._solver = None
            return self.value
        self.value = self._solver.value(t)
        self._velocity = self._solver.velocity(t)
        return self.value

    @property
    def velocity(self) -> float:
        return self._velocity


# --------------------------------------------------------------------------
# framer-motion's PanSession, transcribed
# --------------------------------------------------------------------------

@dataclass
class PanSession:
    """Threshold, per-frame dispatch, and the 100 ms velocity window."""
    distance_threshold: float = GESTURE["distanceThresholdPx"]
    window_ms: float = VELOCITY["sampleWindowMs"]
    history: list[tuple[float, float, float]] = field(default_factory=list)
    started: bool = False
    active: bool = False
    _origin: tuple[float, float] = (0.0, 0.0)
    _pending: tuple[float, float] | None = None

    def down(self, x: float, y: float, t: float) -> None:
        self.active = True
        self.started = False
        self._origin = (x, y)
        self.history = [(x, y, t)]
        self._pending = None

    def move(self, x: float, y: float) -> None:
        """Stored only. The library dispatches on the frame, not on the event."""
        self._pending = (x, y)

    def frame(self, t: float) -> dict | None:
        """One frame's dispatch. Returns pan info, or None if nothing fires.

        The dispatch is scheduled with keepAlive, so it re-runs EVERY frame for
        as long as the gesture is alive -- not only on frames that carried a
        move. A stationary finger therefore keeps pushing the same point into
        the history with a fresh timestamp, and after ~100 ms of stillness the
        velocity window contains only identical points and the measured
        velocity is zero. Hold still before releasing and there is no fling at
        all. That is a feel property, not an edge case, and a model that only
        dispatches on new events does not have it.
        """
        if not self.active or self._pending is None:
            return None
        x, y = self._pending
        offset = (x - self.history[0][0], y - self.history[0][1])
        if not self.started and math.hypot(offset[0], offset[1]) < self.distance_threshold:
            # Below the threshold nothing is pushed to history, so the first
            # delta that does fire carries the whole pre-threshold movement.
            return None
        last = self.history[-1]
        # The library builds the info from the history BEFORE pushing this
        # point, so the reported velocity is measured over the history alone
        # and lags the current point by one dispatch. Reproduced, because a
        # velocity that includes the current point is a different number and
        # the fling multiplies it.
        info = {"point": (x, y), "delta": (x - last[0], y - last[1]),
                "offset": offset, "velocity": self._velocity_of_history()}
        self.history.append((x, y, t))
        self.started = True
        return info

    def up(self, x: float, y: float, t: float, cancelled: bool = False) -> dict | None:
        """Release info. A pan that never started produces nothing at all."""
        if not self.active:
            return None
        self.active = False
        if not self.started:
            return None
        if cancelled and self.history:
            # pointercancel uses the last MOVE info, not the cancel point.
            x, y, t = self.history[-1]
        last = self.history[-1]
        info = {"point": (x, y), "delta": (x - last[0], y - last[1]),
                "offset": (x - self.history[0][0], y - self.history[0][1]),
                "velocity": self._velocity_of_history()}
        return info

    def _velocity_of_history(self) -> tuple[float, float]:
        hist = self.history
        if len(hist) < 2:
            return (0.0, 0.0)
        newest = hist[-1]
        i = len(hist) - 1
        oldest = None
        while i >= 0:
            oldest = hist[i]
            if newest[2] - oldest[2] > self.window_ms:
                break
            i -= 1
        if oldest is None:
            return (0.0, 0.0)
        if oldest is hist[0] and len(hist) > 2 and newest[2] - oldest[2] > 2 * self.window_ms:
            oldest = hist[1]
        dt = (newest[2] - oldest[2]) / 1000.0
        if dt == 0:
            return (0.0, 0.0)
        vx = (newest[0] - oldest[0]) / dt
        vy = (newest[1] - oldest[1]) / dt
        return (0.0 if math.isinf(vx) else vx, 0.0 if math.isinf(vy) else vy)


# --------------------------------------------------------------------------
# the model
# --------------------------------------------------------------------------

class MotionValueVelocity:
    """`MotionValue.getVelocity()`: a BACKWARD DIFFERENCE, not the spring's own.

    The bundle feeds the dolly magnitude from `f.getVelocity()` /
    `p.getVelocity()` on the two scroll MotionValues, and getVelocity there is
    `(current - prevFrameValue) / min(updatedAt - prevUpdatedAt, 30) * 1000`,
    returning zero once more than 30 ms have passed since the value last
    changed. Not the analytic spring velocity.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self, value: float = 0.0) -> None:
        self.current = value
        self.prev_frame_value: float | None = None
        self.updated_at = 0.0
        self.prev_updated_at = 0.0

    def update(self, value: float, now_ms: float) -> None:
        if value == self.current:
            return
        self.prev_frame_value = self.current
        self.prev_updated_at = self.updated_at
        self.current = value
        self.updated_at = now_ms

    def velocity(self, now_ms: float) -> float:
        if self.prev_frame_value is None or now_ms - self.updated_at > 30.0:
            return 0.0
        dt = min(self.updated_at - self.prev_updated_at, 30.0)
        if dt <= 0:
            return 0.0
        return (self.current - self.prev_frame_value) / dt * 1000.0


@dataclass
class SourceExactMotion:
    """Scroll, magnitude and pointer, exactly as the Target composes them."""
    scroll_x: Spring = field(default_factory=lambda: Spring.from_contract("scroll"))
    scroll_y: Spring = field(default_factory=lambda: Spring.from_contract("scroll"))
    magnitude: Spring = field(default_factory=lambda: Spring.from_contract("magnitude"))
    pointer_x: Spring = field(default_factory=lambda: Spring.from_contract("pointer"))
    pointer_y: Spring = field(default_factory=lambda: Spring.from_contract("pointer"))
    target_x: float = 0.0
    target_y: float = 0.0
    target_mag: float = 0.0
    session: PanSession = field(default_factory=PanSession)
    mv_x: MotionValueVelocity = field(default_factory=MotionValueVelocity)
    mv_y: MotionValueVelocity = field(default_factory=MotionValueVelocity)
    published: dict = field(default_factory=lambda: {
        "scrollX": 0.0, "scrollY": 0.0, "magnitude": 0.0,
        "pointerX": 0.0, "pointerY": 0.0, "velocityX": 0.0, "velocityY": 0.0})

    def begin_frame(self) -> dict:
        """What the Target's renderer paints THIS frame: last frame's model.

        The Target's motion values and the renderer that consumes them are
        driven by two different frame callbacks, and the consumer's runs first
        -- it was registered when the canvas mounted, long before the first
        gesture started framer-motion's loop. So what reaches the screen is
        always the value the model produced on the PREVIOUS frame.

        This is not a detail that could be left out and called close enough.
        Replaying the model against the Target's own recorded trajectory over
        all 120 non-wheel runs: without the delay the median raw peak error is
        3.36% of travel and the best-fit time shift is a systematic +10.5 ms;
        with one frame it is 0.76% and +2.0 ms; with two it is 2.16% and
        -6.0 ms. One frame wins on every single sequence and two frames
        overshoots on every single sequence.
        """
        self.published = {
            "scrollX": self.scroll_x.value, "scrollY": self.scroll_y.value,
            "magnitude": self.magnitude.value,
            "pointerX": self.pointer_x.value, "pointerY": self.pointer_y.value,
            "velocityX": self.scroll_x.velocity, "velocityY": self.scroll_y.velocity}
        return self.published

    def on_pan(self, info: dict, now_ms: float) -> None:
        self.target_x += DRAG["gain"] * info["delta"][0]
        self.target_y += DRAG["gain"] * info["delta"][1]
        self.target_mag = math.hypot(*info["velocity"])
        self._retarget(now_ms)

    def on_pan_end(self, info: dict, now_ms: float) -> None:
        self.target_x += info["velocity"][0] * DRAG["fling"]
        self.target_y += info["velocity"][1] * DRAG["fling"]
        self.target_mag = math.hypot(*info["velocity"])
        self._retarget(now_ms)

    def set_pointer(self, ndc_x: float, ndc_y: float, now_ms: float) -> None:
        self.pointer_x.set_target(max(-1.0, min(1.0, ndc_x)), now_ms)
        self.pointer_y.set_target(max(-1.0, min(1.0, ndc_y)), now_ms)

    def _retarget(self, now_ms: float) -> None:
        self.scroll_x.set_target(self.target_x, now_ms)
        self.scroll_y.set_target(self.target_y, now_ms)
        self.magnitude.set_target(self.target_mag, now_ms)

    def advance(self, now_ms: float) -> dict:
        sx = self.scroll_x.advance(now_ms)
        sy = self.scroll_y.advance(now_ms)
        # The magnitude source is refreshed from the scroll VALUES' own
        # velocities on every change, not only from the gesture -- and by the
        # MotionValue backward difference the bundle reads, not the spring's
        # analytic velocity.
        self.mv_x.update(sx, now_ms)
        self.mv_y.update(sy, now_ms)
        self.target_mag = math.hypot(self.mv_x.velocity(now_ms), self.mv_y.velocity(now_ms))
        self.magnitude.set_target(self.target_mag, now_ms)
        mag = self.magnitude.advance(now_ms)
        px = self.pointer_x.advance(now_ms)
        py = self.pointer_y.advance(now_ms)
        return {"scrollX": sx, "scrollY": sy, "magnitude": mag,
                "pointerX": px, "pointerY": py,
                "velocityX": self.scroll_x.velocity, "velocityY": self.scroll_y.velocity}


def orbit(pointer_x: float, pointer_y: float, perspective: float) -> tuple[float, float, float]:
    g = CAMERA["orbit"]["pointerGain"]
    yaw = -(g * pointer_x)
    pitch = g * pointer_y
    return (math.sin(yaw) * math.cos(pitch) * perspective,
            math.sin(pitch) * perspective,
            math.cos(yaw) * math.cos(pitch) * perspective)


def dolly(magnitude: float, max_zoom_z: float) -> float:
    if max_zoom_z <= 0:
        return 0.0
    r = 3.0 * max_zoom_z
    return r * math.tanh(0.04 * magnitude / r)
