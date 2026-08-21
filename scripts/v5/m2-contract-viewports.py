#!/usr/bin/env python3
"""The 36 viewports the source-exact engineering contract is defined on.

Read out of the accepted contract result rather than restated, so the M2 re-run
cannot silently cover a different set from the one that was accepted. A shell
one-liner was tried first and could not be quoted through two layers without
losing its f-string; this is the same three lines in a file that needs no
quoting at all.
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
d = json.loads((REPO / "qa-v5/motion/source-contract.json").read_text())
print(",".join(f"{r['viewport'][0]}x{r['viewport'][1]}" for r in d["results"]))
