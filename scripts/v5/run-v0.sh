#!/usr/bin/env bash
# V0 -- source-exact CSS3D label coverage culling: capture, gate, evidence.
#
# Stages (run all, or name them: bash scripts/v5/run-v0.sh gate perf ...):
#   forensics  byte-anchored source read + live-bundle SHA comparison
#   target     Target lane culling capture (network)
#   before     Before lane culling capture (requires V0_BEFORE_URL serving
#              the ACCEPTED pre-V0 build -- see the lane fingerprint note)
#   candidate  Candidate lane culling capture
#   gate       coverage truth, slot verdicts, pop-in, writes
#   perf       sustained-input perf runs, both lanes + analysis
#   frozen     regressions: source contract, layout, typography, card/label,
#              motion freeze smoke, tsc, build
#   overlays   PNG overlay panels (private package material)
#   record     screen recordings (private package material)
#   evidence   qa-v5/culling README + MANIFEST
#   hygiene    tree checks
#
# V0_CAPTURED_AT is REQUIRED for the evidence stage: the commit the captures
# were taken at. There is no current-HEAD fallback -- a default here makes the
# evidence commit look like the capture commit.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
ART="$REPO/artifacts/culling"
OUT="$REPO/qa-v5/culling"
LOGS="${V0_LOG_DIR:-$ART/logs}"
BUNDLE="$REPO/artifacts/f27/bundles/03lo820gl57km.js"
LIVE_BUNDLE_URL='https://infinite-liquid-glass.shader.se/_next/static/immutable/chunks/03lo820gl57km.js'
PORT=5280
ORIGIN="http://127.0.0.1:$PORT"
LOCAL_URL="$ORIGIN/?composition=sourceExact&qa"
MOTION_URL="$ORIGIN/?qa=1&composition=sourceExact"

say() { printf '%s\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 2; }
need_file() { [ -s "$1" ] || die "expected output missing or empty: $1"; }

mkdir -p "$ART" "$LOGS" "$OUT"

start_server() {
  if curl -sf -o /dev/null "$ORIGIN"; then return; fi
  say "  building and serving the candidate on :$PORT"
  (cd "$REPO" && npm run build > "$LOGS/build.log" 2>&1) \
    || { tail -30 "$LOGS/build.log"; die "npm run build"; }
  (cd "$REPO" && npx vite preview --host 127.0.0.1 --port "$PORT" --strictPort \
    > "$LOGS/preview.log" 2>&1 &)
  for _ in $(seq 1 40); do
    curl -sf -o /dev/null "$ORIGIN" && return
    sleep 0.5
  done
  die "the preview server did not come up on :$PORT"
}

stage_forensics() {
  say "STAGE forensics -- the culling rules, read out of the Target's bundle"
  [ -s "$BUNDLE" ] || die "the Target bundle is missing: $BUNDLE"
  curl -sf --max-time 60 "$LIVE_BUNDLE_URL" -o "$ART/live-bundle.js" \
    || die "could not download the live Target bundle for the SHA comparison"
  python3 "$HERE/v0-culling-forensics.py" "--bundle=$BUNDLE" \
    "--live-bundle=$ART/live-bundle.js" "--out=$OUT/target-culling-source.json" \
    || die "v0-culling-forensics.py (a recorded byte offset did not match)"
  need_file "$OUT/target-culling-source.json"
  say "STAGE forensics COMPLETE"
}

stage_target() {
  say "STAGE target -- the Target lane, 5 viewports x 13 states"
  node "$HERE/v0-culling-trace.mjs" --lane=target "--out=$ART/target" \
    > "$LOGS/target.log" 2>&1 || { tail -20 "$LOGS/target.log"; die "target capture"; }
  need_file "$ART/target/culling-trace.json"
  say "STAGE target COMPLETE"
}

stage_before() {
  say "STAGE before -- the accepted pre-V0 build"
  : "${V0_BEFORE_URL:?V0_BEFORE_URL is required -- an origin serving the pre-V0 build (a worktree at the accept commit). The lane fingerprint in the trace must show qaHasLabelSyncProbe=false.}"
  node "$HERE/v0-culling-trace.mjs" --lane=before "--url=$V0_BEFORE_URL" \
    --settle=4500 "--out=$ART/before" > "$LOGS/before.log" 2>&1 \
    || { tail -20 "$LOGS/before.log"; die "before capture"; }
  need_file "$ART/before/culling-trace.json"
  python3 - "$ART/before/culling-trace.json" <<'PY' || die "the before lane is not the before build (fingerprint)"
import json, sys
d = json.load(open(sys.argv[1]))
f = d["runs"][0]["found"]
assert f.get("qaHasLabelSyncProbe") is False, "probe present: this is the candidate build"
assert f.get("qaPublishesCullingVerdicts") is False, "culling verdicts present: candidate build"
PY
  say "STAGE before COMPLETE"
}

stage_candidate() {
  say "STAGE candidate -- the V0 build"
  start_server
  node "$HERE/v0-culling-trace.mjs" --lane=candidate "--url=$LOCAL_URL" \
    --settle=4500 "--out=$ART/candidate" > "$LOGS/candidate.log" 2>&1 \
    || { tail -20 "$LOGS/candidate.log"; die "candidate capture"; }
  need_file "$ART/candidate/culling-trace.json"
  say "STAGE candidate COMPLETE"
}

stage_gate() {
  say "STAGE gate -- coverage truth, slot identity, pop-in, writes"
  set +e
  python3 "$HERE/v0-coverage-truth.py" "--target=$ART/target/culling-trace.json" \
    "--before=$ART/before/culling-trace.json" \
    "--candidate=$ART/candidate/culling-trace.json" "--outdir=$OUT" \
    | tee "$LOGS/gate.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v0-coverage-truth.py exited $rc"
  for f in coverage-truth.json slot-verdicts.json edge-pop-in.json transform-writes.json; do
    need_file "$OUT/$f"
  done
  say "STAGE gate COMPLETE (rc=$rc)"
}

stage_perf() {
  say "STAGE perf -- sustained input, before and candidate"
  : "${V0_BEFORE_URL:?V0_BEFORE_URL is required for the before perf lane}"
  start_server
  node "$HERE/v0-perf-trace.mjs" --lane=before "--url=$V0_BEFORE_URL" \
    "--out=$ART/perf-before.json" > "$LOGS/perf-before.log" 2>&1 \
    || { tail -20 "$LOGS/perf-before.log"; die "perf before"; }
  node "$HERE/v0-perf-trace.mjs" --lane=candidate "--url=$LOCAL_URL" \
    "--out=$ART/perf-candidate.json" > "$LOGS/perf-candidate.log" 2>&1 \
    || { tail -20 "$LOGS/perf-candidate.log"; die "perf candidate"; }
  set +e
  python3 "$HERE/v0-performance.py" "--before=$ART/perf-before.json" \
    "--candidate=$ART/perf-candidate.json" "--out=$OUT/performance.json" \
    | tee "$LOGS/perf.log"
  local rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" -le 1 ] || die "v0-performance.py exited $rc"
  need_file "$OUT/performance.json"
  say "STAGE perf COMPLETE (rc=$rc)"
}

stage_frozen() {
  say "STAGE frozen -- everything V0 must NOT have changed"
  start_server
  say "  source contract (36 viewports)"
  local vps
  vps=$(python3 "$HERE/m2-contract-viewports.py")
  [ -n "$vps" ] || die "could not resolve the 36 source-contract viewports"
  node "$HERE/fsx-engine-dump.mjs" "--origin=$ORIGIN" \
    "--vps=$vps" "--out=$ART/fsx" > "$LOGS/fsx-engine.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-engine.log"; die "fsx-engine-dump"; }
  local dom="$REPO/artifacts/fsx/dom-899/dom-state.json"
  [ -s "$dom" ] || die "Target DOM capture missing: $dom"
  python3 "$HERE/fsx-source-contract.py" "--engine=$ART/fsx/engine.json" \
    "--dom=$dom" "--out=$OUT/source-contract.json" > "$LOGS/fsx-contract.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-contract.log"; die "fsx-source-contract"; }
  need_file "$OUT/source-contract.json"

  say "  layout source verifier"
  (cd "$REPO" && npm run v5:target-layout-source > "$LOGS/layout-source.log" 2>&1) \
    || { tail -20 "$LOGS/layout-source.log"; die "v5:target-layout-source"; }
  tail -3 "$LOGS/layout-source.log"

  say "  typography: container alignment, depth, ink"
  mkdir -p "$ART/typography"
  node "$HERE/t1-container-alignment.mjs" "--origin=$ORIGIN" \
    "--out=$ART/typography/container-alignment.json" > "$LOGS/align.log" 2>&1 \
    || { tail -20 "$LOGS/align.log"; die "t1-container-alignment"; }
  node "$HERE/t1-depth-clipping.mjs" "--origin=$ORIGIN" \
    '--pointers=0,0;-1,-1;1,-1;1,1;-1,1' \
    "--out=$ART/typography/depth-clipping.json" \
    "--shots=$ART/typography/shots" > "$LOGS/depth.log" 2>&1 \
    || { tail -20 "$LOGS/depth.log"; die "t1-depth-clipping"; }
  python3 "$HERE/t1-label-ink.py" "$ART/typography/shots" \
    "$ART/typography/label-ink.json" > "$LOGS/ink.log" 2>&1 \
    || { tail -20 "$LOGS/ink.log"; die "t1-label-ink"; }
  python3 "$HERE/m1-typography-regression.py" \
    "--alignment=artifacts/culling/typography/container-alignment.json" \
    "--ink=artifacts/culling/typography/label-ink.json" \
    "--depth=artifacts/culling/typography/depth-clipping.json" \
    "--out=qa-v5/culling/typography-regression.json" || die "typography regression"
  need_file "$OUT/typography-regression.json"

  # The corner-delta gate itself; its raw report stays under artifacts/ and
  # is folded into motion-regression.json -- the brief enumerates the public
  # tree exactly, and card-label-motion is not on the list.
  say "  card and label under motion"
  node "$HERE/m1-card-label-motion.mjs" "--origin=$ORIGIN" \
    "--out=$ART/card-label-motion.json" > "$LOGS/clm.log" 2>&1 \
    || { tail -20 "$LOGS/clm.log"; die "m1-card-label-motion"; }
  need_file "$ART/card-label-motion.json"
  tail -2 "$LOGS/clm.log"

  say "  motion freeze smoke"
  [ -s "$ART/motion-smoke/trace.json" ] || {
    node "$HERE/m3-motion-trace.mjs" "--url=$MOTION_URL" \
      "--out=$ART/motion-smoke" --vps=1440x900 --repeat=1 --settle=7000 \
      > "$LOGS/motion-smoke.log" 2>&1 \
      || { tail -20 "$LOGS/motion-smoke.log"; die "motion smoke capture"; }
  }
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
  need_file "$OUT/motion-regression.json"

  say "  typescript and build"
  (cd "$REPO" && npx tsc --noEmit > "$LOGS/tsc.log" 2>&1) \
    || { tail -20 "$LOGS/tsc.log"; die "tsc"; }
  (cd "$REPO" && npm run build > "$LOGS/build2.log" 2>&1) \
    || { tail -20 "$LOGS/build2.log"; die "vite build"; }
  say "STAGE frozen COMPLETE"
}

stage_overlays() {
  say "STAGE overlays -- coverage panels for the private package"
  python3 "$HERE/v0-overlays.py" "--target=$ART/target/culling-trace.json" \
    "--before=$ART/before/culling-trace.json" \
    "--candidate=$ART/candidate/culling-trace.json" \
    "--outdir=$ART/overlays" || die "v0-overlays.py"
  say "STAGE overlays COMPLETE"
}

stage_record() {
  say "STAGE record -- clips for the private package"
  start_server
  local plan='1440x900:slow-horizontal-drag,fast-flick;390x844:touch-drag-release,long-drag-multi-wrap,orientation-flip'
  node "$HERE/m2-recording.mjs" "--url=$LOCAL_URL" --label=v0Candidate \
    "--out=$ART/recordings" "--plan=$plan" --settle=7000 \
    > "$LOGS/record-candidate.log" 2>&1 \
    || { tail -20 "$LOGS/record-candidate.log"; die "candidate recording"; }
  node "$HERE/m2-recording.mjs" --label=v0Target \
    "--out=$ART/recordings" "--plan=$plan" --settle=7000 \
    > "$LOGS/record-target.log" 2>&1 \
    || { tail -20 "$LOGS/record-target.log"; die "target recording"; }
  : "${V0_BEFORE_URL:?V0_BEFORE_URL is required for the before recording lane}"
  node "$HERE/m2-recording.mjs" "--url=$V0_BEFORE_URL" --label=v0Before \
    "--out=$ART/recordings" "--plan=$plan" --settle=7000 \
    > "$LOGS/record-before.log" 2>&1 \
    || { tail -20 "$LOGS/record-before.log"; die "before recording"; }
  say "STAGE record COMPLETE"
}

stage_evidence() {
  say "STAGE evidence -- README and MANIFEST"
  : "${V0_CAPTURED_AT:?V0_CAPTURED_AT is required -- the commit the captures were taken at. No current-HEAD fallback exists.}"
  python3 "$HERE/v0-evidence.py" "--outdir=$OUT" "--capturedAtHead=$V0_CAPTURED_AT" \
    || die "v0-evidence.py"
  need_file "$OUT/README.md"
  need_file "$OUT/MANIFEST.json"
  say "STAGE evidence COMPLETE"
}

stage_hygiene() {
  say "STAGE hygiene"
  # No video and no GIF in the public tree that THIS round added; pre-existing
  # media from accepted earlier rounds is reported, not deleted.
  V0_COMMITS="${V0_COMMITS:-}"
  local media
  media=$(find "$REPO/qa-v5" -type f \( -name '*.mp4' -o -name '*.gif' -o -name '*.webm' \) \
          -not -path "*/private/*" 2>/dev/null || true)
  if [ -n "$media" ]; then
    while IFS= read -r m; do
      local rel="${m#"$REPO"/}"
      local added
      added=$(cd "$REPO" && git log --diff-filter=A --format=%h -1 -- "$rel" 2>/dev/null || true)
      [ -n "$added" ] || die "untracked media in the public tree: $rel"
      for c in $V0_COMMITS; do
        [ "$added" = "$c" ] && die "V0 added media to the public tree: $rel"
      done
      say "  note: pre-existing media from commit $added: $rel"
    done <<< "$media"
  fi
  # No single public file over 20 MB.
  local big
  big=$(find "$REPO/qa-v5/culling" -type f -size +20M 2>/dev/null || true)
  [ -z "$big" ] || die "public file over 20 MB: $big"
  # Manifest heads: capturedAtHead present, reviewHead never in the public one.
  python3 - "$OUT/MANIFEST.json" <<'PY' || die "public manifest heads"
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("capturedAtHead"), "capturedAtHead missing"
assert "reviewHead" not in d, "reviewHead does not belong in the public manifest"
PY
  # The private package, when present, must carry real heads.
  local pz="$REPO/qa-v5/private/culling-review.zip"
  if [ -f "$pz" ]; then
    unzip -p "$pz" PACKAGE-MANIFEST.json > "$ART/.pm.json" \
      || die "the private package carries no PACKAGE-MANIFEST.json"
    python3 - "$ART/.pm.json" <<'PY' || die "private manifest heads"
import json, re, sys
d = json.load(open(sys.argv[1]))
for k in ("capturedAtHead", "reviewHead"):
    v = d.get(k)
    assert v and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{7,12}", v), f"{k} bad: {v!r}"
assert re.fullmatch(r"[0-9a-f]{40}", d["reviewHead"]), "reviewHead must be a full SHA"
PY
    rm -f "$ART/.pm.json"
    local sz
    sz=$(stat -f%z "$pz" 2>/dev/null || stat -c%s "$pz")
    [ "$sz" -le $((50 * 1024 * 1024)) ] || die "private package over 50 MB: $sz bytes"
  else
    say "  note: private package not built yet; its checks are skipped"
  fi
  say "STAGE hygiene COMPLETE"
}

STAGES=("$@")
[ ${#STAGES[@]} -gt 0 ] || STAGES=(forensics target before candidate gate perf frozen overlays record evidence hygiene)
for s in "${STAGES[@]}"; do "stage_$s"; done
say "run-v0 COMPLETE"
