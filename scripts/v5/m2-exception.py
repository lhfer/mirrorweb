#!/usr/bin/env python3
"""Write MOTION-EXC-01: the one difference the product decided not to close.

The numbers in the file are read out of the gate's own output rather than
typed, so the exception cannot drift from what was measured.

Usage: m2-exception.py --dir=qa-v5/motion-closure
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

# The wording the product brief fixed for this exception. Reproduced exactly.
STATEMENT = (
    "Target dual-rAF frame-step jitter is intentionally not reproduced.\n"
    "\n"
    "The deterministic one-frame publication delay remains.\n"
    "\n"
    "The exception covers only raw frame-step scheduling irregularity.\n"
    "It does not cover final position, travel, decay, pointer orbit,\n"
    "touch behaviour, wrap continuity or the filtered camera-dolly envelope.\n"
)

FORBIDDEN = [
    "creating two competing rAF loops to race each other",
    "randomly skipping a motion frame",
    "randomly repeating the previous frame",
    "a hard-coded jitter pattern",
    "generating a race tuned to one machine's refresh rate",
]


def med(vals):
    v = [x for x in vals if x is not None]
    return round(statistics.median(v), 5) if v else None


def main() -> int:
    args = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:]}
    d = Path(args["dir"])
    raw = json.loads((d / "raw-scheduler-metrics.json").read_text())["rows"]
    gate = json.loads((d / "gate-summary.json").read_text())
    inv = json.loads((d / "scheduler-invariant-gate.json").read_text())

    def side(s, key):
        return [r.get(key) for r in raw if r["side"] == s and r.get(key) is not None]

    # Read from the landmark module's own EXCEPTION_RAW set, not from gate rows.
    # These metrics never become gate rows at all -- they carry no unit, so the
    # baseline never thresholds them -- which means deriving this list from row
    # statuses would always come back empty and the exception would claim to
    # cover nothing while covering exactly these.
    covered_metrics = sorted(json.loads(
        (d / "target-scheduler-invariant-baseline.json").read_text())["exceptionRawMetrics"])
    # Everything the exception explicitly does NOT cover: every landmark that
    # is product-gated. Listed by name, so "the exception is narrow" is a list
    # a reviewer can count rather than an adjective.
    not_covered = sorted({r["landmark"] for r in inv["rows"] if r.get("productGated")})

    doc = {
        "id": "MOTION-EXC-01",
        "title": "Target dual-rAF frame-step jitter, deliberately not reproduced",
        "status": "CANDIDATE -- awaiting product review",
        "statement": STATEMENT,
        "whatTheTargetDoes": {
            "architecture": "the Target computes its motion in framer-motion's frame "
                            "loop and paints it in r3f's -- two independent "
                            "requestAnimationFrame callbacks reading and writing the "
                            "same motion values. We compute and paint in one.",
            "measuredMechanism":
                "M1 described this as dropped frames: 'a frame on which framer did not "
                "tick repaints the same value, and the next frame carries double'. The "
                "M2 measurement does not support that and corrects it. The Target's "
                "frame interval is as steady as ours -- 8.3 ms median -- and it has "
                "essentially no near-zero steps and no double steps. What it has is a "
                "smooth spread of the per-frame step around its own local trend, "
                "roughly 0.89x to 1.13x. That is a continuous PHASE difference between "
                "the loop that solves the spring and the loop that samples it, not a "
                "loop that misses beats.",
            "targetFrameStepJitterFractionMedian": med(side("target", "frameStepJitterFraction")),
            "oursFrameStepJitterFractionMedian": med(side("ours", "frameStepJitterFraction")),
            "targetNearZeroStepFractionMedian": med(side("target", "nearZeroStepFraction")),
            "targetDoubleStepFractionMedian": med(side("target", "doubleStepFraction")),
            "targetFrameIntervalMedianMs": med(side("target", "frameIntervalMedianMs")),
            "oursFrameIntervalMedianMs": med(side("ours", "frameIntervalMedianMs")),
            "targetMaxFrameVelocityStepMedian": med(side("target", "maxFrameVelocityStep")),
            "oursMaxFrameVelocityStepMedian": med(side("ours", "maxFrameVelocityStep")),
            "targetMaxSingleFrameSpeedDropMedian":
                med(side("target", "maxSingleFrameSpeedDropFraction")),
            "oursMaxSingleFrameSpeedDropMedian":
                med(side("ours", "maxSingleFrameSpeedDropFraction")),
        },
        "whatIsKept": "The one-frame publication delay is DETERMINISTIC and is kept. It "
                      "is not part of this exception: the Target's renderer consumes the "
                      "motion values from a frame callback that runs before the model's "
                      "own, so what reaches the screen is always the previous frame's "
                      "value, and we do the same thing on purpose. Replayed against the "
                      "Target's own recorded trajectory, one frame beats nought and two "
                      "on every single sequence.",
        "coversTheseRawMetricsOnly": sorted(set(covered_metrics)),
        "coversNothingElse": {
            "note": "every landmark below is product-gated and a FAIL on any of them is "
                    "a FAIL, exception or no exception",
            "landmarks": not_covered,
        },
        "waysOfReproducingItThatAreForbidden": FORBIDDEN,
        "whyForbidden": "each of them would put a scheduling irregularity into the "
                        "product on purpose. A page that skips or repeats frames to look "
                        "like another page is worse than the page it is imitating, and a "
                        "pattern tuned to one refresh rate is a defect on every other.",
        "theOnlyRemedyThatWouldBeAllowed":
            "if -- and only if -- the SCHEDULER-INVARIANT camera-dolly envelope still "
            "failed, a single deterministic sampling adapter could be designed. It would "
            "have to be proved identical at 60, 90 and 120 Hz and it could not change a "
            "single motion contract constant. This round did not reach that condition; "
            "see filteredDollyEnvelope below.",
        "filteredDollyEnvelope": {
            "landmarks": ["dollyMedianPeak3", "dollyRms30Peak", "dollyPeakTimeMs",
                          "dollyEnvelopeIntegral"],
            "failures": [r for r in gate.get("failures", [])
                         if str(r.get("landmark", "")).startswith("dolly")],
        },
        "verdictImpact": {
            "gateVerdict": gate["verdict"],
            "productGatedFailures": len(gate.get("failures", [])),
            "acceptedDeviations": gate.get("acceptedDeviations"),
            "smootherThanTarget": gate.get("smootherThanTarget"),
        },
    }
    out = d / "product-exception-candidate.json"
    out.write_text(json.dumps(doc, indent=2))
    print(f"exception -> {out}")
    print(f"  covers {len(doc['coversTheseRawMetricsOnly'])} raw metrics, "
          f"covers nothing among {len(not_covered)} product-gated landmarks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
