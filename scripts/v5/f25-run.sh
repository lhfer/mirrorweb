#!/usr/bin/env bash
# F2.5: capture the six gated viewports for a composition variant and gate it.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=$1; COMP=$2; MODE=${3:-tangent}
VIEWPORTS="1100x720 1366x768 1440x900 1920x1080 390x844 844x390"
Q="composition=${COMP}&verticalMode=${MODE}"
for VP in $VIEWPORTS; do
  W=${VP%x*}; H=${VP#*x}
  ILG_CAPTURE_HEADLESS=1 node scripts/v5/capture-layout.mjs \
    --route="/?optics=v4&${Q}&foundation=layout&annotate=0" \
    --out="$OUT/local/$VP" --width="$W" --height="$H" --states=01-rest >/dev/null
  ILG_CAPTURE_HEADLESS=1 node scripts/v5/capture-layout.mjs \
    --route="/?optics=v4&${Q}" --out="$OUT/beauty/$VP" --width="$W" --height="$H" --states=01-rest >/dev/null
done
python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
(out / "pairs.json").write_text(json.dumps([
    {"id": vp, "targetPng": f"artifacts/v5-target/{vp}-dpr1.png",
     "localPng": f"{out}/local/{vp}/01-rest.png", "targetDpr": 1, "localDpr": 1}
    for vp in ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390"]], indent=2))
PY
python3 scripts/v5/f2-gate.py --pairs="$OUT/pairs.json" --out="$OUT" --f0=qa-v5/f0/gate.json || true
