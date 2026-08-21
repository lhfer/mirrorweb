#!/usr/bin/env bash
#
# M2 Motion Closure: capture, seal the baseline, then judge the candidate.
#
# WHY THIS FILE EXISTS AT ALL
# ---------------------------
# The M1 round was driven by an ad-hoc shell script that was never committed.
# It contained an unquoted URL, so zsh tried to glob the `?` in
# `--url=http://127.0.0.1:5281/?qa=1&composition=sourceExact`, failed to match,
# and `set -e` exited. The stage died silently and was not noticed for nearly
# two hours, because the thing waiting on it was watching for a success string
# and an error string, and neither appeared.
#
# So: every URL is quoted, every stage announces its start, its finish and the
# file it produced, every stage that produces no file is a failure, and there
# is no unbounded wait anywhere. A stage that dies must say so on the line it
# dies on.
#
# ORDER IS PART OF THE METHOD, NOT A CONVENIENCE
# ----------------------------------------------
# The Target is captured first and the baseline is written and hashed from the
# Target ALONE, before a single candidate frame is recorded. The gate then
# recomputes that hash and refuses to run against a modified copy. "The floors
# were not moved after seeing the candidate" is enforced here, in this order,
# rather than asserted afterwards.
#
# Usage:
#   scripts/v5/run-m2.sh [stage ...]
# Stages: target baseline candidate gate evidence  (default: all)

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

ART="$REPO/artifacts/motion"
OUT="$REPO/qa-v5/motion-closure"
LOGS="${M2_LOG_DIR:-$ART/m2-logs}"
LOCAL_URL='http://127.0.0.1:5281/?qa=1&composition=sourceExact'
PORT=5281
VIEWPORTS=(1440x900 390x844 844x390 700x700)
# Node holds every frame of a capture in memory until it writes. Four viewports
# in one process exhausted the heap at run 168 of 180 last round, so each
# viewport gets its own process and its own file, and they are merged by the
# readers.
export NODE_OPTIONS=--max-old-space-size=6144

mkdir -p "$LOGS" "$OUT"

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "--- stopping preview server (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

say()  { echo "=== $(date +%H:%M:%S)  $*"; }
die()  { echo "!!! $(date +%H:%M:%S)  FAILED: $*" >&2; exit 1; }

need_file() {
  [ -s "$1" ] || die "expected output missing or empty: $1"
  echo "    -> $1  ($(wc -c < "$1" | tr -d ' ') bytes)"
}

# A bounded wait. Never `while true`.
wait_for_url() {
  local url="$1" tries=60
  while [ $tries -gt 0 ]; do
    if curl -fsS -o /dev/null --max-time 5 "$url"; then return 0; fi
    tries=$((tries - 1)); sleep 1
  done
  die "server did not answer $url within 60s"
}

start_server() {
  if curl -fsS -o /dev/null --max-time 3 "$LOCAL_URL"; then
    say "a server is already answering on port $PORT; using it"
    return 0
  fi
  say "building"
  npm run build > "$LOGS/build.log" 2>&1 || { tail -30 "$LOGS/build.log"; die "npm run build"; }
  say "starting preview server on $PORT"
  npx vite preview --host 127.0.0.1 --port "$PORT" --strictPort > "$LOGS/preview.log" 2>&1 &
  SERVER_PID=$!
  wait_for_url "$LOCAL_URL"
  say "server up (pid $SERVER_PID)"
}

stage_target() {
  say "STAGE target -- capturing the Target, ${#VIEWPORTS[@]} viewports x 15 sequences x 3 repeats"
  for vp in "${VIEWPORTS[@]}"; do
    say "  target $vp"
    node scripts/v5/m2-motion-trace.mjs \
      "--out=artifacts/motion/m2-target-$vp" "--vps=$vp" --repeat=3 --settle=7000 \
      > "$LOGS/target-$vp.log" 2>&1 \
      || { tail -30 "$LOGS/target-$vp.log"; die "target capture $vp"; }
    need_file "$ART/m2-target-$vp/trace.json"
    python3 scripts/v5/m2-attach-recovery.py \
      "--trace=$ART/m2-target-$vp/trace.json" || die "recovery sidecar target $vp"
    need_file "$ART/m2-target-$vp/recovery.json"
  done
  say "STAGE target COMPLETE"
}

stage_baseline() {
  say "STAGE baseline -- Target only, no candidate is read"
  local first="$ART/m2-target-${VIEWPORTS[0]}/trace.json"
  local extra=()
  for vp in "${VIEWPORTS[@]:1}"; do extra+=("--extra=$ART/m2-target-$vp/trace.json"); done
  python3 scripts/v5/m2-baseline.py "--target=$first" "${extra[@]}" "--out=$OUT" \
    || die "m2-baseline.py"
  need_file "$OUT/target-scheduler-invariant-baseline.json"
  need_file "$OUT/target-scheduler-invariant-baseline.sha256"
  say "STAGE baseline COMPLETE -- seal this before capturing the candidate"
}

stage_candidate() {
  [ -s "$OUT/target-scheduler-invariant-baseline.sha256" ] \
    || die "the baseline must exist and be sealed before the candidate is captured"
  start_server
  say "STAGE candidate -- capturing our page on the same 15 x 3 x 4"
  for vp in "${VIEWPORTS[@]}"; do
    say "  candidate $vp"
    node scripts/v5/m2-motion-trace.mjs \
      "--url=$LOCAL_URL" "--out=artifacts/motion/m2-local-$vp" "--vps=$vp" \
      --repeat=3 --settle=7000 \
      > "$LOGS/local-$vp.log" 2>&1 \
      || { tail -30 "$LOGS/local-$vp.log"; die "candidate capture $vp"; }
    need_file "$ART/m2-local-$vp/trace.json"
    python3 scripts/v5/m2-attach-recovery.py \
      "--trace=$ART/m2-local-$vp/trace.json" || die "recovery sidecar local $vp"
    need_file "$ART/m2-local-$vp/recovery.json"
  done
  say "STAGE candidate COMPLETE"
}

stage_gate() {
  say "STAGE gate"
  local t="$ART/m2-target-${VIEWPORTS[0]}/trace.json"
  local l="$ART/m2-local-${VIEWPORTS[0]}/trace.json"
  local extra=()
  for vp in "${VIEWPORTS[@]:1}"; do
    extra+=("--targetExtra=$ART/m2-target-$vp/trace.json"
            "--localExtra=$ART/m2-local-$vp/trace.json")
  done
  set +e
  python3 scripts/v5/m2-motion-gate.py "--baseline=$OUT" "--target=$t" "--local=$l" \
    "${extra[@]}" "--out=$OUT"
  local rc=$?
  set -e
  # rc 1 is a FAIL verdict, which is a result and not a crash. rc 2 is the
  # baseline seal refusing, which IS a crash.
  [ $rc -le 1 ] || die "m2-motion-gate.py exited $rc (baseline seal or bad input)"
  for f in gate-summary.json scheduler-invariant-gate.json engine-vs-contract-v2.json \
           raw-scheduler-metrics.json continuity-and-input.json; do
    need_file "$OUT/$f"
  done
  say "STAGE gate COMPLETE (verdict rc=$rc)"
}

stage_dolly() {
  say "STAGE dolly -- attributing the camera-dolly difference between law, jitter and engine"
  local t="$ART/m2-target-${VIEWPORTS[0]}/trace.json"
  local extra=()
  for vp in "${VIEWPORTS[@]:1}"; do extra+=("--targetExtra=$ART/m2-target-$vp/trace.json"); done
  local loc=()
  for vp in "${VIEWPORTS[@]}"; do
    [ -s "$ART/m2-local-$vp/trace.json" ] && loc+=("--local=$ART/m2-local-$vp/trace.json")
  done
  python3 scripts/v5/m2-dolly-attribution.py "--target=$t" "${extra[@]}" "${loc[@]}" \
    "--out=$OUT/dolly-attribution.json" || die "m2-dolly-attribution.py"
  need_file "$OUT/dolly-attribution.json"
  say "STAGE dolly COMPLETE"
}

stage_exception() {
  say "STAGE exception -- MOTION-EXC-01, numbers read out of the gate's own output"
  python3 scripts/v5/m2-exception.py "--dir=$OUT" || die "m2-exception.py"
  need_file "$OUT/product-exception-candidate.json"
  say "STAGE exception COMPLETE"
}

# The frozen systems, re-verified rather than inferred. A file-level freeze
# cannot see a regression that arrives from somewhere else, and this round moved
# the camera the label layer projects through.
stage_frozen() {
  start_server
  say "STAGE frozen -- re-verifying the accepted contracts at this tip"
  say "  source contract (36 viewports, engine against model against Target DOM)"
  # The 36 viewports the source contract is defined on. Named here rather than
  # defaulted, because the dump's own default is an EMPTY list -- it exits 0
  # having captured nothing, and the comparison downstream then divides by zero.
  local vps
  vps=$(python3 scripts/v5/m2-contract-viewports.py)
  [ -n "$vps" ] || die "could not resolve the 36 source-contract viewports"
  node scripts/v5/fsx-engine-dump.mjs '--origin=http://127.0.0.1:5281' \
    "--vps=$vps" "--out=$ART/m2-fsx" > "$LOGS/fsx-engine.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-engine.log"; die "fsx-engine-dump"; }
  need_file "$ART/m2-fsx/engine.json"
  # The Target's own DOM, captured in the fsx round. It is a measurement of a
  # page we do not control and does not change when our code does, so it is
  # reused rather than re-fetched.
  local dom="$REPO/artifacts/fsx/dom-899/dom-state.json"
  [ -s "$dom" ] || die "Target DOM capture missing: $dom"
  python3 scripts/v5/fsx-source-contract.py "--engine=$ART/m2-fsx/engine.json" \
    "--dom=$dom" "--out=$OUT/source-contract.json" > "$LOGS/fsx-contract.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-contract.log"; die "fsx-source-contract"; }
  need_file "$OUT/source-contract.json"
  say "  layout source verifier"
  npm run v5:target-layout-source > "$LOGS/layout-source.log" 2>&1 \
    || { tail -20 "$LOGS/layout-source.log"; die "v5:target-layout-source"; }
  tail -3 "$LOGS/layout-source.log"
  say "  container alignment, label ink, depth"
  mkdir -p "$ART/m2-typography"
  node scripts/v5/t1-container-alignment.mjs '--origin=http://127.0.0.1:5281' \
    "--out=$ART/m2-typography/container-alignment.json" > "$LOGS/align.log" 2>&1 \
    || { tail -20 "$LOGS/align.log"; die "t1-container-alignment"; }
  # The four pointer extremes plus centre. Without them the script runs its
  # one-pointer default, the self-proving sweep block never executes, and the
  # depth carry-forward count is taken at a single on-axis pose -- which is the
  # exact fault M1 found and fixed. Named here so it cannot be defaulted away.
  node scripts/v5/t1-depth-clipping.mjs '--origin=http://127.0.0.1:5281' \
    '--pointers=0,0;-1,-1;1,-1;1,1;-1,1' \
    "--out=$ART/m2-typography/depth-clipping.json" \
    "--shots=$ART/m2-typography/shots" > "$LOGS/depth.log" 2>&1 \
    || { tail -20 "$LOGS/depth.log"; die "t1-depth-clipping"; }
  python3 scripts/v5/t1-label-ink.py "$ART/m2-typography/shots" \
    "$ART/m2-typography/label-ink.json" > "$LOGS/ink.log" 2>&1 \
    || { tail -20 "$LOGS/ink.log"; die "t1-label-ink"; }
  # Repo-RELATIVE paths: the aggregator echoes its inputs into the evidence, and
  # an absolute path is a local username in a public file. The hygiene stage
  # fails on one; this is what keeps it from having to.
  say "  card and label under motion"
  node scripts/v5/m1-card-label-motion.mjs '--origin=http://127.0.0.1:5281' \
    "--out=qa-v5/motion-closure/card-label-motion.json" > "$LOGS/clm.log" 2>&1 \
    || { tail -20 "$LOGS/clm.log"; die "m1-card-label-motion"; }
  need_file "$OUT/card-label-motion.json"
  tail -2 "$LOGS/clm.log"
  python3 scripts/v5/m1-typography-regression.py \
    "--alignment=artifacts/motion/m2-typography/container-alignment.json" \
    "--ink=artifacts/motion/m2-typography/label-ink.json" \
    "--depth=artifacts/motion/m2-typography/depth-clipping.json" \
    "--out=qa-v5/motion-closure/typography-regression.json" || die "typography regression"
  need_file "$OUT/typography-regression.json"
  say "STAGE frozen COMPLETE"
}

stage_evidence() {
  say "STAGE evidence"
  # The commit the TRACES were captured at, not the tip when this runs.
  # REQUIRED. There is no current-HEAD fallback: the capture head and the
  # commit that carries the evidence are different facts and a default makes
  # the wrong one look right.
  : "${M2_CAPTURED_AT:?M2_CAPTURED_AT is required -- the commit the behaviour was captured at}"
  local cap="$M2_CAPTURED_AT"
  python3 scripts/v5/m2-evidence.py "--dir=$OUT" "--capturedAt=$cap" \
    || die "m2-evidence.py"
  need_file "$OUT/MANIFEST.json"
  need_file "$OUT/README.md"
  say "STAGE evidence COMPLETE"
}

# --- hygiene the last round needed and did not have -----------------------
stage_hygiene() {
  say "STAGE hygiene -- what must never enter the public tree"
  local big
  big=$(git diff --cached --name-only --diff-filter=ACM | while read -r f; do
          [ -f "$f" ] && [ "$(wc -c < "$f")" -gt 20971520 ] && echo "$f"
        done || true)
  [ -z "$big" ] && echo "    no staged file over 20 MB" || die "staged file over 20 MB: $big"
  local media
  media=$(git diff --cached --name-only --diff-filter=ACM \
          | grep -Ei '\.(gif|mp4|webm|mov)$' || true)
  [ -z "$media" ] && echo "    no video or GIF staged" || die "video/GIF staged: $media"
  local total
  total=$(git diff --cached --numstat -- qa-v5 | awk '{s+=$1} END {print s+0}')
  echo "    qa-v5 staged line delta: $total"
  local leaks
  leaks=$(grep -rl "/Users/" "$OUT" 2>/dev/null || true)
  [ -z "$leaks" ] && echo "    no absolute local paths in $OUT" || die "absolute path leak: $leaks"
  say "STAGE hygiene COMPLETE"
}

STAGES=("$@")
if [ ${#STAGES[@]} -eq 0 ]; then
  STAGES=(target baseline candidate gate dolly exception frozen evidence hygiene)
fi
START=$SECONDS
for s in "${STAGES[@]}"; do
  case "$s" in
    target)    stage_target ;;
    baseline)  stage_baseline ;;
    candidate) stage_candidate ;;
    gate)      stage_gate ;;
    dolly)     stage_dolly ;;
    exception) stage_exception ;;
    frozen)    stage_frozen ;;
    evidence)  stage_evidence ;;
    hygiene)   stage_hygiene ;;
    *) die "unknown stage: $s" ;;
  esac
done
say "ALL DONE in $((SECONDS - START))s -- stages: ${STAGES[*]}"
