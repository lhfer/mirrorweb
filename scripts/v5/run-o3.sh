#!/usr/bin/env bash
# O3 analytic bevel reflection -- frozen-regression stage runner (§十一).
#
#   rendergate   the V1 render culling absolute gate re-run at the O2 build
#   labelgate    the V0 label culling absolute gate re-run at the O2 build
#   frozen       source contract / layout / typography / clm / motion / tsc / build
#   regressions  aggregate everything into qa-v5/optics-o3/regressions.json
#
# Every output goes under artifacts/optics-o3/regressions or qa-v5/optics-o3.
# The SEALED V0/V1/O1 evidence trees are never written.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$REPO/qa-v5/optics-o3"
ART="$REPO/artifacts/optics-o3/regressions"
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
  say "STAGE rendergate -- the V1 absolute gate at the O3 build"
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
  say "STAGE labelgate -- the V0 absolute gate at the O3 build"
  start_server
  rm -f "$CART/candidate-o3/culling-trace.json"
  node "$HERE/v0-culling-trace.mjs" --lane=candidate "--url=$LOCAL_URL" \
    "--out=$CART/candidate-o3" > "$LOGS/labelgate-trace.log" 2>&1 \
    || { tail -20 "$LOGS/labelgate-trace.log"; die "candidate culling trace"; }
  set +e
  python3 "$HERE/v0-coverage-truth.py" \
    "--target=$CART/target/culling-trace.json" \
    "--before=$CART/before/culling-trace.json" \
    "--candidate=$CART/candidate-o3/culling-trace.json" \
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

stage_o2suites() {
  say "STAGE o2suites -- the O2 suites §十一 requires to keep passing"
  start_server
  mkdir -p "$ART/harness"
  node "$HERE/o2-harness.mjs" "--local=http://127.0.0.1:$PORT" \
    "--out=$ART/harness" > "$LOGS/harness.log" 2>&1 \
    || { tail -20 "$LOGS/harness.log"; die "o2-harness"; }
  python3 "$HERE/o2-harness-verify.py" "--raw=$ART/harness/harness-raw.json" \
    "--out=$ART/harness/harness-verify.json" > "$LOGS/harness-verify.log" 2>&1 \
    || { tail -20 "$LOGS/harness-verify.log"; die "o2-harness-verify"; }
  say "  media-only controls (from the O3 measure captures)"
  python3 - "$REPO/artifacts/optics-o3/measure" "$ART/media-only-controls.json" <<'MOC'
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
md, out = Path(sys.argv[1]), Path(sys.argv[2])
man = json.loads((md / "measure-manifest.json").read_text())
def find(**kw):
    return [r for r in man["records"] if all(r.get(k) == v for k, v in kw.items())]
pairs = []
for rec in find(kind="media-only", lane="candidate"):
    ctl = find(kind="media-only", lane="control", asset=rec["asset"], vp=rec["vp"])
    if not ctl:
        continue
    a = np.asarray(Image.open(md / rec["file"]).convert("RGB")).astype(int)
    b = np.asarray(Image.open(md / ctl[0]["file"]).convert("RGB")).astype(int)
    d = np.abs(a - b).max(axis=2)
    pairs.append({"asset": rec["asset"], "vp": rec["vp"],
                  "differingPixels": int((d > 0).sum()),
                  "maxChannelDelta": int(d.max())})
doc = {"what": "with the glass layer hidden the two reflection-support lanes "
               "must render the same media exactly -- the support field is "
               "not in the media path at all.",
       "pairs": pairs,
       "pass": bool(pairs) and all(p["differingPixels"] == 0 for p in pairs)}
out.write_text(json.dumps(doc, indent=1))
print("media-only controls:", "PASS" if doc["pass"] else "FAIL", f"({len(pairs)} pairs)")
MOC
  say "STAGE o2suites COMPLETE"
}

stage_regressions() {
  say "STAGE regressions -- aggregate"
  python3 "$HERE/o3-regressions.py" "--art=$ART" \
    "--out=$ART/regressions.json" "--public=$OUT/regressions.json" \
    || die "regressions aggregate FAILED"
  need_file "$ART/regressions.json"
  need_file "$OUT/regressions.json"
  say "STAGE regressions COMPLETE"
}

for stage in "$@"; do
  case "$stage" in
    rendergate) stage_rendergate ;;
    labelgate) stage_labelgate ;;
    frozen) stage_frozen ;;
    o2suites) stage_o2suites ;;
    regressions) stage_regressions ;;
    *) die "unknown stage: $stage" ;;
  esac
done
say "run-o3 COMPLETE"
