#!/usr/bin/env python3
"""Consistency check for the v2 sample dataset (datasets/samples/v2)."""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent / "datasets" / "samples" / "v2"
errs = []
for d in sorted(ROOT.iterdir()):
    if not d.is_dir():
        continue
    cid = d.name
    files = {f.stem: json.loads(f.read_text()) for f in d.glob("*.json")}
    for req in ["case", "evidence", "obligations", "trace", "proposal", "reference"]:
        if req not in files:
            errs.append(f"{cid}: missing {req}")
    if not all(k in files for k in ["evidence","trace","proposal","reference","case"]):
        continue
    ev, tr, pr, ref, case = (files[k] for k in ["evidence","trace","proposal","reference","case"])
    docvers = {}
    for dd in ev["documents"]:
        docvers.setdefault(dd["id"], set()).add(dd["version"])
    for r in ev["computed_results"]:
        for did, dv in r.get("inputs", {}).items():
            if dv not in docvers.get(did, set()):
                errs.append(f"{cid}: result {r['id']} cites {did} v{dv} not in evidence")
    if [e["seq"] for e in tr["events"]] != sorted(e["seq"] for e in tr["events"]):
        errs.append(f"{cid}: trace seq not sorted")
    var = case["variation"]
    if var in ("V2","V3") and "injection" not in files:
        errs.append(f"{cid}: {var} missing injection.json")
    if var == "V0" and "injection" in files:
        errs.append(f"{cid}: V0 has injection.json")
    if "ground_truth" not in ref:
        errs.append(f"{cid}: reference missing ground_truth")
    if var != "V0" and ref.get("ground_truth") in ("HOLD","DENY") and not ref.get("no_single_culprit"):
        errs.append(f"{cid}: {var} defect missing no_single_culprit")
    for dc in pr["package"].get("documents_cited", []):
        if dc not in docvers:
            errs.append(f"{cid}: package cites unknown doc {dc}")
if errs:
    print("PROBLEMS:")
    for e in errs:
        print(" -", e)
    sys.exit(1)
n = len([d for d in ROOT.iterdir() if d.is_dir()])
print(f"all consistency checks passed on {n} sample cases")
