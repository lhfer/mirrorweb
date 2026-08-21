#!/usr/bin/env bash
# O1 first optics candidate -- stage runner.
#
#   rendergate  the V1 render culling absolute gate re-run at the O1 build
#   labelgate   the V0 label culling absolute gate re-run at the O1 build
#   frozen      source contract / layout / typography / clm / motion / tsc / build
#   measure     target + before + candidate ROI captures (beauty/media-only/glass-only)
#   evidence    qa-v5/optics README + MANIFEST (needs O1_CAPTURED_AT)
#
# Every output goes under artifacts/optics/o1-regressions or qa-v5/optics.
# The SEALED V0/V1 evidence trees are never written.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/qa-v5/optics"
ART="$REPO/artifacts/optics/o1-regressions"
CART="$REPO/artifacts/culling"
LOGS="$ART/logs"
mkdir -p "$OUT" "$ART" "$LOGS"
PORT=5280
LOCAL_URL="http://127.0.0.1:$PORT/?composition=sourceExact&qa"
MOTION_URL="http://127.0.0.1:$PORT/?qa=1&composition=sourceExact"

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

stage_rendergate() {
  say "STAGE rendergate -- the V1 absolute gate at the O1 build"
  start_server
  node "$HERE/v1-render-trace.mjs" "--url=$LOCAL_URL" \
    "--out=$ART/render" > "$LOGS/render-trace.log" 2>&1 \
    || { tail -20 "$LOGS/render-trace.log"; die "v1-render-trace"; }
  need_file "$ART/render/render-trace.json"
  set +e
  python3 "$HERE/v1-render-gate.py" "--trace=$ART/render/render-trace.json" \
    "--outdir=$ART/render" | tee "$LOGS/render-gate.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v1-render-gate exited $rc"
  need_file "$ART/render/render-culling-truth.json"
  say "STAGE rendergate COMPLETE (rc=$rc)"
}

stage_labelgate() {
  say "STAGE labelgate -- the V0 absolute gate at the O1 build"
  start_server
  rm -f "$CART/candidate-o1/culling-trace.json"
  node "$HERE/v0-culling-trace.mjs" --lane=candidate "--url=$LOCAL_URL" \
    "--out=$CART/candidate-o1" > "$LOGS/labelgate-trace.log" 2>&1 \
    || { tail -20 "$LOGS/labelgate-trace.log"; die "candidate culling trace"; }
  set +e
  python3 "$HERE/v0-coverage-truth.py" \
    "--target=$CART/target/culling-trace.json" \
    "--before=$CART/before/culling-trace.json" \
    "--candidate=$CART/candidate-o1/culling-trace.json" \
    "--outdir=$ART/labelgate" | tee "$LOGS/labelgate.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v0-coverage-truth exited $rc"
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
    "--dom=$dom" "--out=$ART/source-contract.json" > "$LOGS/fsx-contract.log" 2>&1 \
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
    "--out=$ART/typography-regression.json" || die "typography regression"
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
    "--out=$ART/motion-regression.json" || die "motion freeze regression FAILED"
  say "  typescript and build"
  (cd "$REPO" && npx tsc --noEmit > "$LOGS/tsc.log" 2>&1) \
    || { tail -20 "$LOGS/tsc.log"; die "tsc"; }
  (cd "$REPO" && npm run -s build > "$LOGS/build.log" 2>&1) \
    || { tail -20 "$LOGS/build.log"; die "build"; }
  say "STAGE frozen COMPLETE"
}

stage_measure() {
  say "STAGE measure"
  start_server
  : "${O1_BEFORE_URL:?O1_BEFORE_URL is required -- the pre-O1 build origin}"
  node "$HERE/o1-optics-measure.mjs" "--candidate=http://127.0.0.1:$PORT" \
    "--before=$O1_BEFORE_URL" \
    "--out=$REPO/artifacts/optics/o1-final" > "$LOGS/measure.log" 2>&1 \
    || { tail -20 "$LOGS/measure.log"; die "o1-optics-measure"; }
  say "STAGE measure COMPLETE"
}

stage_evidence() {
  say "STAGE evidence"
  : "${O1_CAPTURED_AT:?O1_CAPTURED_AT is required -- the commit the captures were taken at}"
  python3 "$HERE/o1-evidence.py" "--outdir=$OUT" \
    "--capturedAtHead=$O1_CAPTURED_AT" || die "o1-evidence"
  need_file "$OUT/README.md"
  need_file "$OUT/MANIFEST.json"
  say "STAGE evidence COMPLETE"
}

for stage in "$@"; do
  case "$stage" in
    rendergate) stage_rendergate ;;
    labelgate) stage_labelgate ;;
    frozen) stage_frozen ;;
    measure) stage_measure ;;
    evidence) stage_evidence ;;
    *) die "unknown stage: $stage" ;;
  esac
done
say "run-o1 COMPLETE"
