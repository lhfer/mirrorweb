#!/usr/bin/env bash
# V1 source-exact WebGL render culling -- stage runner.
#
#   forensics  byte-anchored source read of the render object + live SHA
#   trace      per-frame effective-visibility trace, all viewports/states
#   gate       effective visibility vs rule replay
#   pixels     culling ON/OFF A/B + V0-baseline comparison (needs V1_BASELINE_URL)
#   perf       A/B perf scenarios + heap cycles (run ALONE)
#   labelgate  the V0 label culling absolute gate, fresh candidate lane
#   frozen     source contract / layout / typography / clm / motion smoke / tsc / build
#   evidence   README + MANIFEST (needs V1_CAPTURED_AT)
#
# Stages are selectable by args; default runs nothing.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/qa-v5/render-culling"
ART="$REPO/artifacts/render-culling"
CART="$REPO/artifacts/culling"
LOGS="$ART/logs"
mkdir -p "$OUT" "$ART" "$LOGS"
PORT=5280
LOCAL_URL="http://127.0.0.1:$PORT/?composition=sourceExact&qa"
MOTION_URL="http://127.0.0.1:$PORT/?qa=1&composition=sourceExact"
LIVE_BUNDLE_URL='https://infinite-liquid-glass.shader.se/_next/static/immutable/chunks/03lo820gl57km.js'

say() { printf '%s\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
need_file() { [ -s "$1" ] || die "missing or empty: $1"; }

start_server() {
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null && return 0
  (cd "$REPO" && nohup npx vite preview --port "$PORT" --strictPort \
    > "$LOGS/server.log" 2>&1 &)
  sleep 3
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/" || die "server did not start"
}

stage_forensics() {
  say "STAGE forensics"
  curl -sf --max-time 60 "$LIVE_BUNDLE_URL" -o "$ART/live-bundle.js" \
    || die "live bundle download"
  python3 "$HERE/v1-render-forensics.py" "--live-bundle=$ART/live-bundle.js" \
    "--out=$OUT/target-render-culling-source.json" || die "v1-render-forensics"
  say "STAGE forensics COMPLETE"
}

stage_trace() {
  say "STAGE trace"
  start_server
  node "$HERE/v1-render-trace.mjs" "--url=$LOCAL_URL" \
    "--out=$ART/candidate" > "$LOGS/trace.log" 2>&1 \
    || { tail -20 "$LOGS/trace.log"; die "v1-render-trace"; }
  need_file "$ART/candidate/render-trace.json"
  tail -3 "$LOGS/trace.log"
  say "STAGE trace COMPLETE"
}

stage_gate() {
  say "STAGE gate"
  set +e
  python3 "$HERE/v1-render-gate.py" "--trace=$ART/candidate/render-trace.json" \
    "--outdir=$OUT" | tee "$LOGS/gate.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v1-render-gate exited $rc"
  need_file "$OUT/render-culling-truth.json"
  say "STAGE gate COMPLETE (rc=$rc)"
}

stage_pixels() {
  say "STAGE pixels"
  start_server
  : "${V1_BASELINE_URL:?V1_BASELINE_URL is required -- the V0-accepted build}"
  node "$HERE/v1-pixel-gate.mjs" "--candidate=$LOCAL_URL" \
    "--baseline=$V1_BASELINE_URL" "--out=$ART/pixels" > "$LOGS/pixels.log" 2>&1 \
    || { tail -20 "$LOGS/pixels.log"; die "v1-pixel-gate capture"; }
  set +e
  python3 "$HERE/v1-pixel-diff.py" "--dir=$ART/pixels" \
    "--out=$OUT/pixel-invariance.json" | tee "$LOGS/pixel-diff.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v1-pixel-diff exited $rc"
  say "STAGE pixels COMPLETE (rc=$rc)"
}

stage_perf() {
  say "STAGE perf -- run ALONE"
  start_server
  node "$HERE/v1-perf-trace.mjs" "--url=$LOCAL_URL" --culling=off \
    "--out=$ART/perf-off.json" > "$LOGS/perf-off.log" 2>&1 \
    || { tail -20 "$LOGS/perf-off.log"; die "perf off"; }
  node "$HERE/v1-perf-trace.mjs" "--url=$LOCAL_URL" --culling=on \
    "--out=$ART/perf-on.json" > "$LOGS/perf-on.log" 2>&1 \
    || { tail -20 "$LOGS/perf-on.log"; die "perf on"; }
  node "$HERE/v1-perf-trace.mjs" "--url=$LOCAL_URL" --cycles=2 \
    "--out=$ART/perf-cycles.json" > "$LOGS/perf-cycles.log" 2>&1 \
    || { tail -20 "$LOGS/perf-cycles.log"; die "perf cycles"; }
  set +e
  python3 "$HERE/v1-performance.py" "--on=$ART/perf-on.json" \
    "--off=$ART/perf-off.json" "--cycles=$ART/perf-cycles.json" \
    "--out=$OUT/performance.json" | tee "$LOGS/perf.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v1-performance exited $rc"
  say "STAGE perf COMPLETE (rc=$rc)"
}

stage_labelgate() {
  say "STAGE labelgate -- the V0 absolute gate at the V1 build"
  start_server
  rm -f "$CART/candidate-v1/culling-trace.json"
  node "$HERE/v0-culling-trace.mjs" --lane=candidate "--url=$LOCAL_URL" \
    "--out=$CART/candidate-v1" > "$LOGS/labelgate-trace.log" 2>&1 \
    || { tail -20 "$LOGS/labelgate-trace.log"; die "candidate culling trace"; }
  set +e
  python3 "$HERE/v0-coverage-truth.py" \
    "--target=$CART/target/culling-trace.json" \
    "--before=$CART/before/culling-trace.json" \
    "--candidate=$CART/candidate-v1/culling-trace.json" \
    "--outdir=$ART/labelgate" | tee "$LOGS/labelgate.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v0-coverage-truth exited $rc"
  python3 - "$ART/labelgate" "$OUT/label-culling-regression.json" <<'PYEOF'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
cov = json.loads((d / "coverage-truth.json").read_text())
sv = json.loads((d / "slot-verdicts.json").read_text())
pop = json.loads((d / "edge-pop-in.json").read_text())
w = json.loads((d / "transform-writes.json").read_text())
crc = cov["candidateRuleConsistency"]
doc = {
    "what": "the V0 label culling absolute gate, re-run with a FRESH "
            "candidate lane captured at the V1 build against the SEALED V0 "
            "target and before traces. Proof V1 did not move the frozen "
            "label culling.",
    "framesChecked": crc["framesChecked"],
    "slotMismatches": crc["slotMismatches"],
    "beyondBoundary": crc["beyondBoundary"],
    "lostLabels": crc["lostLabels"],
    "intrudingLabels": crc["intrudingLabels"],
    "identity": f"{sv['identical']}/{sv['comparisons']}",
    "snapshotBitExact": cov["candidateSnapshotBitExactness"]["pass"],
    "staleRects": cov["staleRectCheck"]["pass"],
    "edgePopIn": pop["pass"],
    "writes": w["pass"],
    "errors": cov["consoleAndPageErrors"],
    "pass": (crc["beyondBoundary"] == 0 and crc["slotMismatches"] == 0
             and sv["pass"] and cov["candidateSnapshotBitExactness"]["pass"]
             and cov["staleRectCheck"]["pass"] and pop["pass"] and w["pass"]),
}
Path(sys.argv[2]).write_text(json.dumps(doc, indent=1) + chr(10))
print("label culling regression:", "PASS" if doc["pass"] else "FAIL")
PYEOF
  say "STAGE labelgate COMPLETE (rc=$rc)"
}

stage_frozen() {
  say "STAGE frozen"
  start_server
  local ORIGIN="http://127.0.0.1:$PORT"
  say "  source contract"
  local vps
  vps=$(python3 "$HERE/m2-contract-viewports.py")
  node "$HERE/fsx-engine-dump.mjs" "--origin=$ORIGIN" "--vps=$vps" \
    "--out=$ART/fsx" > "$LOGS/fsx-engine.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-engine.log"; die "fsx-engine-dump"; }
  local dom="$REPO/artifacts/fsx/dom-899/dom-state.json"
  [ -s "$dom" ] || die "Target DOM capture missing: $dom"
  python3 "$HERE/fsx-source-contract.py" "--engine=$ART/fsx/engine.json" \
    "--dom=$dom" "--out=$OUT/source-contract.json" > "$LOGS/fsx-contract.log" 2>&1 \
    || { tail -10 "$LOGS/fsx-contract.log"; die "source contract"; }
  say "  layout source"
  (cd "$REPO" && npm run -s v5:target-layout-source > "$LOGS/layout.log" 2>&1) \
    || { tail -10 "$LOGS/layout.log"; die "layout source"; }
  say "  typography"
  mkdir -p "$ART/typography"
  node "$HERE/t1-container-alignment.mjs" "--origin=$ORIGIN" \
    "--out=$ART/typography/container-alignment.json" > "$LOGS/t1a.log" 2>&1 \
    || { tail -10 "$LOGS/t1a.log"; die "container alignment"; }
  node "$HERE/t1-depth-clipping.mjs" "--origin=$ORIGIN" \
    '--pointers=0,0;-1,-1;1,-1;1,1;-1,1' \
    "--out=$ART/typography/depth-clipping.json" \
    "--shots=$ART/typography/shots" > "$LOGS/t1d.log" 2>&1 \
    || { tail -10 "$LOGS/t1d.log"; die "depth clipping"; }
  python3 "$HERE/t1-label-ink.py" "$ART/typography/shots" \
    "$ART/typography/label-ink.json" > "$LOGS/t1i.log" 2>&1 \
    || { tail -10 "$LOGS/t1i.log"; die "label ink"; }
  python3 "$HERE/m1-typography-regression.py" \
    "--alignment=$ART/typography/container-alignment.json" \
    "--ink=$ART/typography/label-ink.json" \
    "--depth=$ART/typography/depth-clipping.json" \
    "--out=$OUT/typography-regression.json" || die "typography regression"
  say "  card and label under motion"
  node "$HERE/m1-card-label-motion.mjs" "--origin=$ORIGIN" \
    "--out=$ART/card-label-motion.json" > "$LOGS/clm.log" 2>&1 \
    || { tail -20 "$LOGS/clm.log"; die "m1-card-label-motion"; }
  say "  motion freeze smoke"
  rm -f "$ART/motion-smoke/trace.json"
  node "$HERE/m3-motion-trace.mjs" "--url=$MOTION_URL" \
    "--out=$ART/motion-smoke" --vps=1440x900 --repeat=1 --settle=7000 \
    > "$LOGS/motion-smoke.log" 2>&1 \
    || { tail -20 "$LOGS/motion-smoke.log"; die "motion smoke capture"; }
  python3 "$HERE/m2-attach-recovery.py" "--trace=$ART/motion-smoke/trace.json" \
    || die "recovery sidecar"
  mkdir -p "$ART/motion-smoke-gate"
  set +e
  python3 "$HERE/m3-motion-gate.py" "--baseline=$REPO/qa-v5/motion-closure" \
    "--target=$REPO/artifacts/motion/m2-target-1440x900/trace.json" \
    "--local=$ART/motion-smoke/trace.json" "--out=$ART/motion-smoke-gate" \
    > "$LOGS/motion-gate.log" 2>&1
  local rc=$?
  set -e
  [ "$rc" -le 1 ] || { tail -20 "$LOGS/motion-gate.log"; die "m3-motion-gate exited $rc"; }
  set +e
  python3 "$HERE/m3-release-history.py" "--local=$ART/motion-smoke/trace.json" \
    "--out=$ART/motion-smoke-gate/release-history-proof.json" \
    > "$LOGS/release-history.log" 2>&1
  local rc2=$?
  set -e
  [ "$rc2" -le 1 ] || { tail -20 "$LOGS/release-history.log"; die "m3-release-history exited $rc2"; }
  python3 "$HERE/v0-motion-regression.py" "--gate=$ART/motion-smoke-gate" \
    "--release=$ART/motion-smoke-gate/release-history-proof.json" \
    "--clm=$ART/card-label-motion.json" \
    "--out=$OUT/motion-regression.json" || die "motion freeze regression FAILED"
  say "  typescript and build"
  (cd "$REPO" && npx tsc --noEmit > "$LOGS/tsc.log" 2>&1) \
    || { tail -20 "$LOGS/tsc.log"; die "tsc"; }
  (cd "$REPO" && npm run -s build > "$LOGS/build.log" 2>&1) \
    || { tail -20 "$LOGS/build.log"; die "build"; }
  say "STAGE frozen COMPLETE"
}

stage_evidence() {
  say "STAGE evidence"
  : "${V1_CAPTURED_AT:?V1_CAPTURED_AT is required -- the commit the captures were taken at}"
  python3 "$HERE/v1-evidence.py" "--outdir=$OUT" \
    "--capturedAtHead=$V1_CAPTURED_AT" || die "v1-evidence"
  need_file "$OUT/README.md"
  need_file "$OUT/MANIFEST.json"
  say "STAGE evidence COMPLETE"
}

for stage in "$@"; do
  case "$stage" in
    forensics) stage_forensics ;;
    trace) stage_trace ;;
    gate) stage_gate ;;
    pixels) stage_pixels ;;
    perf) stage_perf ;;
    labelgate) stage_labelgate ;;
    frozen) stage_frozen ;;
    evidence) stage_evidence ;;
    *) die "unknown stage: $stage" ;;
  esac
done
say "run-v1 COMPLETE"
