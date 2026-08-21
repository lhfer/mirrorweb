#!/usr/bin/env bash
#
# M3 Final Motion Source Reconciliation: forensics, then code, then judgement.
#
# ORDER IS PART OF THE METHOD
# ---------------------------
# The writer-order forensics runs FIRST and against the Target's bundle alone.
# It settles which of the magnitude MotionValue's two writers runs last from
# twenty byte offsets in the bundle, before a single candidate frame is
# recorded. The Target is NOT re-captured and the scheduler-invariant baseline
# is NOT recomputed: it was sealed from the Target alone in M2 and every gate
# here recomputes its SHA-256 and refuses to run against a modified copy.
#
# M3_CAPTURED_AT IS REQUIRED
# --------------------------
# The commit the behaviour was captured at and the commit that carries the
# evidence are different facts. M2 defaulted the first to `git rev-parse HEAD`
# and so recorded the second -- the exact metadata defect that round was
# written to repair, reintroduced by its own sealing tool. There is no fallback
# here. A caller that does not say gets an error.
#
# Usage:
#   M3_CAPTURED_AT=<sha> scripts/v5/run-m3.sh [stage ...]
# Stages: forensics candidate gate dolly attribution frozen evidence hygiene
#         record package   (default: all but record/package, which need
#         M3_REVIEW_HEAD and therefore run after the evidence commit)

set -euo pipefail

: "${M3_CAPTURED_AT:?M3_CAPTURED_AT is required -- the commit the behaviour was captured at. There is no current-HEAD fallback.}"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

ART="$REPO/artifacts/motion"
OUT="$REPO/qa-v5/motion-final"
M2OUT="$REPO/qa-v5/motion-closure"
LOGS="${M3_LOG_DIR:-$ART/m3-logs}"
LOCAL_URL='http://127.0.0.1:5281/?qa=1&composition=sourceExact'
ORIGIN='http://127.0.0.1:5281'
PORT=5281
BUNDLE="$REPO/artifacts/f27/bundles/03lo820gl57km.js"
VIEWPORTS=(1440x900 390x844 844x390 700x700)
# Node holds every frame of a capture in memory until it writes, so each
# viewport gets its own process and its own file and the readers merge them.
export NODE_OPTIONS=--max-old-space-size=6144

mkdir -p "$LOGS" "$OUT"

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "--- stopping preview server (pid $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  # Any capture process this script started and did not reap.
  pkill -P $$ 2>/dev/null || true
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

target_args() {
  local flag="$1" out=()
  for vp in "${VIEWPORTS[@]}"; do out+=("--$flag=$ART/m2-target-$vp/trace.json"); done
  printf '%s\n' "${out[@]}"
}

stage_forensics() {
  say "STAGE forensics -- the magnitude writer order, read out of the Target's bundle"
  [ -s "$BUNDLE" ] || die "the Target bundle is missing: $BUNDLE"
  local t=()
  while IFS= read -r line; do t+=("$line"); done < <(target_args target)
  python3 scripts/v5/m3-writer-order-forensics.py "--bundle=$BUNDLE" \
    "${t[@]}" "--out=$OUT/magnitude-writer-order-source.json" \
    || die "m3-writer-order-forensics.py (a recorded byte offset did not match)"
  need_file "$OUT/magnitude-writer-order-source.json"
  say "STAGE forensics COMPLETE"
}

stage_candidate() {
  [ -s "$M2OUT/target-scheduler-invariant-baseline.sha256" ] \
    || die "the sealed M2 baseline must exist before the candidate is captured"
  start_server
  say "STAGE candidate -- our page, ${#VIEWPORTS[@]} viewports x 15 sequences x 3 repeats"
  for vp in "${VIEWPORTS[@]}"; do
    say "  candidate $vp"
    node scripts/v5/m3-motion-trace.mjs \
      "--url=$LOCAL_URL" "--out=artifacts/motion/m3-local-$vp" "--vps=$vp" \
      --repeat=3 --settle=7000 \
      > "$LOGS/local-$vp.log" 2>&1 \
      || { tail -30 "$LOGS/local-$vp.log"; die "candidate capture $vp"; }
    need_file "$ART/m3-local-$vp/trace.json"
    python3 scripts/v5/m2-attach-recovery.py \
      "--trace=$ART/m3-local-$vp/trace.json" || die "recovery sidecar local $vp"
    need_file "$ART/m3-local-$vp/recovery.json"
  done
  say "STAGE candidate COMPLETE"
}

local_args() {
  local flag="$1" out=()
  for vp in "${VIEWPORTS[@]:1}"; do out+=("--$flag=$ART/m3-local-$vp/trace.json"); done
  printf '%s\n' "${out[@]}"
}

stage_gate() {
  say "STAGE gate"
  local t="$ART/m2-target-${VIEWPORTS[0]}/trace.json"
  local l="$ART/m3-local-${VIEWPORTS[0]}/trace.json"
  [ -s "$t" ] || die "missing Target trace $t (the M2 capture is not re-taken here)"
  [ -s "$l" ] || die "missing candidate trace $l -- run the candidate stage first"
  local extra=()
  for vp in "${VIEWPORTS[@]:1}"; do
    extra+=("--targetExtra=$ART/m2-target-$vp/trace.json"
            "--localExtra=$ART/m3-local-$vp/trace.json")
  done
  set +e
  python3 scripts/v5/m3-motion-gate.py "--baseline=$M2OUT" "--target=$t" "--local=$l" \
    "${extra[@]}" "--out=$OUT"
  local rc=$?
  set -e
  # rc 1 is a FAIL verdict, which is a result. rc 2 is the baseline seal
  # refusing or an unreadable input, which is a crash.
  [ $rc -le 1 ] || die "m3-motion-gate.py exited $rc (baseline seal or bad input)"
  for f in gate-summary.json scheduler-invariant-gate.json engine-vs-contract-v3.json \
           raw-scheduler-metrics.json continuity-and-input.json; do
    need_file "$OUT/$f"
  done

  say "  release history proof"
  local locals=()
  for vp in "${VIEWPORTS[@]}"; do locals+=("--local=$ART/m3-local-$vp/trace.json"); done
  set +e
  python3 scripts/v5/m3-release-history.py "${locals[@]}" \
    "--out=$OUT/release-history-proof.json"
  local rc2=$?
  set -e
  [ $rc2 -le 1 ] || die "m3-release-history.py exited $rc2"
  need_file "$OUT/release-history-proof.json"

  say "  callback order proof"
  local tl=()
  for vp in "${VIEWPORTS[@]}"; do tl+=("--target=$ART/m2-target-$vp/trace.json"); done
  python3 scripts/v5/m3-callback-order.py "${locals[@]}" "${tl[@]}" \
    "--out=$OUT/callback-order-proof.json" || die "m3-callback-order.py"
  need_file "$OUT/callback-order-proof.json"

  say "  contract vs target, four columns per exact cell"
  python3 scripts/v5/m3-contract-vs-target.py "--baseline=$M2OUT" "--target=$t" \
    "--local=$l" "${extra[@]}" "--out=$OUT/contract-vs-target-v2.json" \
    || die "m3-contract-vs-target.py"
  need_file "$OUT/contract-vs-target-v2.json"
  say "STAGE gate COMPLETE (verdict rc=$rc)"
}

stage_dolly() {
  say "STAGE dolly -- the envelope, M2 control beside M3 candidate"
  local t="$ART/m2-target-${VIEWPORTS[0]}/trace.json"
  local l="$ART/m3-local-${VIEWPORTS[0]}/trace.json"
  local extra=()
  for vp in "${VIEWPORTS[@]:1}"; do
    extra+=("--targetExtra=$ART/m2-target-$vp/trace.json"
            "--localExtra=$ART/m3-local-$vp/trace.json")
  done
  local ctl=()
  for vp in "${VIEWPORTS[@]}"; do
    [ -s "$ART/m2-local-$vp/trace.json" ] && ctl+=("--control=$ART/m2-local-$vp/trace.json")
  done
  python3 scripts/v5/m3-dolly-envelope.py "--baseline=$M2OUT" "--target=$t" "--local=$l" \
    "${extra[@]}" "${ctl[@]}" "--out=$OUT/dolly-envelope.json" \
    || die "m3-dolly-envelope.py"
  need_file "$OUT/dolly-envelope.json"
  say "STAGE dolly COMPLETE"
}

stage_attribution() {
  say "STAGE attribution -- every failing cell, per cell"
  python3 scripts/v5/m3-attribution.py "--dir=$OUT" \
    "--out=$OUT/failure-attribution-v2.json" || die "m3-attribution.py"
  need_file "$OUT/failure-attribution-v2.json"
  say "STAGE attribution COMPLETE"
}

stage_frozen() {
  start_server
  say "STAGE frozen -- re-verifying the accepted contracts at this tip"
  say "  source contract (36 viewports, engine against model against Target DOM)"
  # The 36 viewports the source contract is defined on. Named rather than
  # defaulted: the dump's own default is an EMPTY list, so it exits 0 having
  # captured nothing and the comparison downstream then divides by zero.
  local vps
  vps=$(python3 scripts/v5/m2-contract-viewports.py)
  [ -n "$vps" ] || die "could not resolve the 36 source-contract viewports"
  node scripts/v5/fsx-engine-dump.mjs "--origin=$ORIGIN" \
    "--vps=$vps" "--out=$ART/m3-fsx" > "$LOGS/fsx-engine.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-engine.log"; die "fsx-engine-dump"; }
  need_file "$ART/m3-fsx/engine.json"
  # The Target's own DOM, captured in the fsx round. It measures a page we do
  # not control and does not change when our code does, so it is reused.
  local dom="$REPO/artifacts/fsx/dom-899/dom-state.json"
  [ -s "$dom" ] || die "Target DOM capture missing: $dom"
  python3 scripts/v5/fsx-source-contract.py "--engine=$ART/m3-fsx/engine.json" \
    "--dom=$dom" "--out=$OUT/source-contract.json" > "$LOGS/fsx-contract.log" 2>&1 \
    || { tail -20 "$LOGS/fsx-contract.log"; die "fsx-source-contract"; }
  need_file "$OUT/source-contract.json"
  say "  layout source verifier"
  npm run v5:target-layout-source > "$LOGS/layout-source.log" 2>&1 \
    || { tail -20 "$LOGS/layout-source.log"; die "v5:target-layout-source"; }
  tail -3 "$LOGS/layout-source.log"
  say "  container alignment, label ink, depth"
  mkdir -p "$ART/m3-typography"
  node scripts/v5/t1-container-alignment.mjs "--origin=$ORIGIN" \
    "--out=$ART/m3-typography/container-alignment.json" > "$LOGS/align.log" 2>&1 \
    || { tail -20 "$LOGS/align.log"; die "t1-container-alignment"; }
  # The four pointer extremes plus centre. Without them the script runs its
  # one-pointer default, the self-proving sweep block never executes, and the
  # depth carry-forward count is taken at a single on-axis pose.
  node scripts/v5/t1-depth-clipping.mjs "--origin=$ORIGIN" \
    '--pointers=0,0;-1,-1;1,-1;1,1;-1,1' \
    "--out=$ART/m3-typography/depth-clipping.json" \
    "--shots=$ART/m3-typography/shots" > "$LOGS/depth.log" 2>&1 \
    || { tail -20 "$LOGS/depth.log"; die "t1-depth-clipping"; }
  python3 scripts/v5/t1-label-ink.py "$ART/m3-typography/shots" \
    "$ART/m3-typography/label-ink.json" > "$LOGS/ink.log" 2>&1 \
    || { tail -20 "$LOGS/ink.log"; die "t1-label-ink"; }
  say "  card and label under motion"
  # Repo-RELATIVE output paths: the aggregator echoes its inputs into the
  # evidence, and an absolute path is a local username in a public file.
  node scripts/v5/m1-card-label-motion.mjs "--origin=$ORIGIN" \
    "--out=qa-v5/motion-final/card-label-motion.json" > "$LOGS/clm.log" 2>&1 \
    || { tail -20 "$LOGS/clm.log"; die "m1-card-label-motion"; }
  need_file "$OUT/card-label-motion.json"
  tail -2 "$LOGS/clm.log"
  python3 scripts/v5/m1-typography-regression.py \
    "--alignment=artifacts/motion/m3-typography/container-alignment.json" \
    "--ink=artifacts/motion/m3-typography/label-ink.json" \
    "--depth=artifacts/motion/m3-typography/depth-clipping.json" \
    "--out=qa-v5/motion-final/typography-regression.json" || die "typography regression"
  need_file "$OUT/typography-regression.json"
  npx tsc --noEmit > "$LOGS/tsc.log" 2>&1 || { tail -20 "$LOGS/tsc.log"; die "tsc"; }
  npm run build > "$LOGS/build.log" 2>&1 || { tail -20 "$LOGS/build.log"; die "vite build"; }
  say "STAGE frozen COMPLETE"
}

stage_record() {
  say "STAGE record -- the M3 candidate lane for the private review package"
  start_server
  local plan='1440x900:slow-horizontal-drag,fast-flick,reverse-flick;390x844:touch-drag-release,long-drag-multi-wrap'
  mkdir -p "$ART/m3-recordings"
  node scripts/v5/m2-recording.mjs "--url=$LOCAL_URL" --label=m3Candidate \
    "--out=artifacts/motion/m3-recordings" "--plan=$plan" --settle=7000 \
    > "$LOGS/record-m3.log" 2>&1 \
    || { tail -30 "$LOGS/record-m3.log"; die "m3 candidate recording"; }
  need_file "$ART/m3-recordings/m3Candidate-index.json"
  # The Target and the M2 control are NOT re-recorded: the M2 lanes are the
  # right pixels for both, and re-recording the Target would mean pointing a
  # browser at it again for no new information.
  for pair in "target:target" "candidate:m2Control"; do
    local src="${pair%%:*}" dst="${pair##*:}"
    [ -s "$ART/m2-recordings/$src-index.json" ] \
      || die "the M2 $src recording lane is missing; the package needs it"
    cp "$ART/m2-recordings/$src-index.json" "$ART/m3-recordings/$dst-index.json"
  done
  say "STAGE record COMPLETE"
}

stage_package() {
  say "STAGE package -- the private visual review package"
  : "${M3_REVIEW_HEAD:?M3_REVIEW_HEAD is required -- the commit this package reviews. Build the package AFTER the evidence commit.}"
  mkdir -p "$REPO/qa-v5/private"
  python3 scripts/v5/m3-package.py "--rec=$ART/m3-recordings" "--closure=$OUT" \
    "--out=$REPO/qa-v5/private/motion-final-review.zip" \
    "--capturedAt=$M3_CAPTURED_AT" "--reviewHead=$M3_REVIEW_HEAD" \
    || die "m3-package.py"
  need_file "$REPO/qa-v5/private/motion-final-review.zip"
  say "STAGE package COMPLETE"
}

stage_evidence() {
  say "STAGE evidence -- README and manifest, captured at $M3_CAPTURED_AT"
  python3 scripts/v5/m3-evidence.py "--dir=$OUT" "--capturedAt=$M3_CAPTURED_AT" \
    || die "m3-evidence.py"
  need_file "$OUT/README.md"
  need_file "$OUT/MANIFEST.json"
  say "STAGE evidence COMPLETE"
}

stage_hygiene() {
  say "STAGE hygiene -- what the public tree is allowed to contain"

  # Every file the brief names must exist and be non-empty.
  for f in README.md MANIFEST.json callback-order-proof.json release-history-proof.json \
           magnitude-writer-order-source.json engine-vs-contract-v3.json \
           contract-vs-target-v2.json failure-attribution-v2.json \
           scheduler-invariant-gate.json dolly-envelope.json source-contract.json \
           typography-regression.json card-label-motion.json; do
    need_file "$OUT/$f"
  done

  # No video, no GIF, anywhere in the public evidence tree.
  local media
  media="$(find "$REPO/qa-v5" -type f \( -iname '*.gif' -o -iname '*.mp4' -o -iname '*.webm' \
            -o -iname '*.mov' \) -not -path "$REPO/qa-v5/private/*" | head -20)"
  [ -z "$media" ] || die "video or GIF in the public tree:
$media"

  # No single committed file over 20 MB.
  local big
  big="$(find "$REPO/qa-v5" -type f -size +20M -not -path "$REPO/qa-v5/private/*" | head -20)"
  [ -z "$big" ] || die "a public evidence file exceeds 20MB:
$big"

  # The manifest must hash what is actually on disk.
  python3 - "$OUT" <<'PY' || die "manifest SHA mismatch"
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1]); repo = d.parents[1]
m = json.loads((d / "MANIFEST.json").read_text())
listed = {e["path"] for e in m["files"]}
actual = {str(p.relative_to(repo)) for p in d.iterdir()
          if p.is_file() and p.name != "MANIFEST.json"}
if listed != actual:
    print("unlisted or missing files:", sorted(listed ^ actual)); raise SystemExit(1)
for e in m["files"]:
    h = hashlib.sha256((repo / e["path"]).read_bytes()).hexdigest()
    if h != e["sha256"]:
        print("sha mismatch:", e["path"]); raise SystemExit(1)
if not m.get("capturedAtHead"):
    print("capturedAtHead is empty"); raise SystemExit(1)
print(f"manifest verified: {len(m['files'])} files, capturedAtHead {m['capturedAtHead']}")
PY

  # The private package, if it has been built, must carry real SHAs and not prose.
  local pm="$REPO/qa-v5/private/motion-final-review"
  if [ -f "$pm/PACKAGE-MANIFEST.json" ]; then
    python3 - "$pm/PACKAGE-MANIFEST.json" <<'PY' || die "private manifest heads"
import json, re, sys
m = json.loads(open(sys.argv[1]).read())
for k in ("capturedAtHead", "reviewHead"):
    v = m.get(k)
    if not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{7,12}", v):
        print(f"{k} is not a SHA: {v!r}"); raise SystemExit(1)
print("private manifest heads are SHAs")
PY
  fi

  # CURRENT_STATUS must have been brought to this round.
  grep -q "M3" "$REPO/docs/v5/CURRENT_STATUS.md" \
    || die "docs/v5/CURRENT_STATUS.md still describes an earlier round"
  grep -q "806/870" "$REPO/docs/v5/CURRENT_STATUS.md" && {
    grep -q "M1 result" "$REPO/docs/v5/CURRENT_STATUS.md" \
      || die "CURRENT_STATUS still shows 806/870 as the CURRENT state"
  }
  say "STAGE hygiene COMPLETE"
}

STAGES=("$@")
if [ ${#STAGES[@]} -eq 0 ]; then
  STAGES=(forensics candidate gate dolly attribution frozen evidence hygiene)
fi
for s in "${STAGES[@]}"; do
  case "$s" in
    forensics)   stage_forensics ;;
    record)      stage_record ;;
    package)     stage_package ;;
    candidate)   stage_candidate ;;
    gate)        stage_gate ;;
    dolly)       stage_dolly ;;
    attribution) stage_attribution ;;
    frozen)      stage_frozen ;;
    evidence)    stage_evidence ;;
    hygiene)     stage_hygiene ;;
    *)           die "unknown stage: $s" ;;
  esac
done
say "run-m3.sh COMPLETE: ${STAGES[*]}"
