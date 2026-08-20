#!/usr/bin/env bash
# Stage F2: capture the local build at the six gated viewports and gate it
# against the Target frames captured from the live site.
#
# Foundation frames are what the gate measures (no media, no glass, no type);
# beauty frames are captured alongside as the shipping-look evidence.
set -euo pipefail
cd "$(dirname "$0")/../.."

OUT=${1:-qa-v5/f2}
ROUTE_FOUND='/?optics=v4&foundation=layout&annotate=0'
ROUTE_BEAUTY='/?optics=v4'
VIEWPORTS="1100x720 1366x768 1440x900 1920x1080 390x844 844x390"

for VP in $VIEWPORTS; do
  W=${VP%x*}; H=${VP#*x}
  ILG_CAPTURE_HEADLESS=1 node scripts/v5/capture-layout.mjs \
    --route="$ROUTE_FOUND" --out="$OUT/local/$VP" --width="$W" --height="$H" --states=01-rest >/dev/null
  ILG_CAPTURE_HEADLESS=1 node scripts/v5/capture-layout.mjs \
    --route="$ROUTE_BEAUTY" --out="$OUT/beauty/$VP" --width="$W" --height="$H" --states=01-rest >/dev/null
  echo "captured $VP"
done

python3 - "$OUT" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
pairs = []
for vp in ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390"]:
    pairs.append({
        "id": vp,
        "targetPng": f"artifacts/v5-target/{vp}-dpr1.png",
        "localPng": f"{out}/local/{vp}/01-rest.png",
        "targetDpr": 1, "localDpr": 1,
    })
(out / "pairs.json").write_text(json.dumps(pairs, indent=2))
print(f"wrote {out}/pairs.json")
PY

python3 scripts/v5/f2-gate.py --pairs="$OUT/pairs.json" --out="$OUT"
