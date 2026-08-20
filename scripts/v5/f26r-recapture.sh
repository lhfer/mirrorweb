#!/usr/bin/env bash
# F2.6R: recapture the three portrait candidates with the propagation fix in
# place, and gate them. Same viewports, same fixed capture conditions.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=${1:-qa-v5/f26r}
VIEWPORTS="390x844 360x800 500x900 1440x900"
for L in p0 p1 p2; do
  for VP in $VIEWPORTS; do
    W=${VP%x*}; H=${VP#*x}
    ILG_CAPTURE_HEADLESS=1 node scripts/v5/capture-layout.mjs \
      --route="/?optics=v4&composition=v2&verticalMode=tangent&portraitLaw=${L}&foundation=layout&annotate=0" \
      --out="$OUT/portrait-candidates/$L/local/$VP" --width="$W" --height="$H" --states=01-rest >/dev/null
  done
  echo "captured $L"
done
